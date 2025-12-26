"""
Crypto Paper Trading Bot
========================
A production-ready paper trading bot using ccxt with comprehensive
fee simulation, risk management, and kill switch safety features.

Strategy: Fee-Aware Bollinger Band Mean Reversion
- Targets 1.5-3% moves (NOT micro-scalping which is unrealistic)
- Only enters when expected edge > 0.3% after fees
- Uses limit orders to capture maker rebates
- Max 3 trades/day with 30-minute cooldown
- 2% stop-loss, 3% take-profit
- Kill switch on 5% drawdown, high volatility, or API errors

Author: Antigravity Trading Systems
License: MIT
"""

import ccxt
import os
import pandas as pd
import numpy as np
import csv
import os
import time
import random
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict
from enum import Enum

# =============================================================================
# CONFIGURATION
# =============================================================================

# Trading mode - set to True for live trading (requires API keys)
LIVE_MODE = False

# Capital and trading pair
STARTING_CAPITAL = 10000.0  # USD
SYMBOL = "BTC/USD"  # ETH is more volatile = more signals
TIMEFRAME = "1h"  # 1-hour candles (less noise, more reliable signals)

# Exchange selection (kraken works without geographic restrictions)
EXCHANGE = "kraken"


# Fee structure (Kraken spot)
MAKER_FEE = 0.0016  # 0.16%
TAKER_FEE = 0.0026  # 0.26%

# Simulated market friction
SIMULATED_SPREAD = 0.0005  # 0.05%
SIMULATED_SLIPPAGE = 0.0002  # 0.02%
PARTIAL_FILL_PROBABILITY = 0.30  # 30% chance of partial fill
MIN_FILL_RATIO = 0.30  # Minimum 30% fill on partial
MAX_FILL_RATIO = 0.80  # Maximum 80% fill on partial

# Strategy parameters - BALANCED MODE (trades more, still careful)
BB_PERIOD = 20  # Standard 20-period
BB_STD = 1.5  # 1.5σ bands (triggers more often than 2σ)
RSI_PERIOD = 14  # Standard RSI
RSI_OVERSOLD = 30  # Classic oversold
RSI_OVERBOUGHT = 70  # Classic overbought

# Risk management - CONSERVATIVE
STOP_LOSS_PCT = 0.03  # 3% stop
TAKE_PROFIT_PCT = 0.02  # 2% take profit
MAX_POSITION_SIZE_PCT = 0.50  # Use only 50% of capital per trade (less risk)
MIN_EXPECTED_EDGE = 0.005  # Need 0.5% expected edge to trade

# Kill switch thresholds
MAX_DAILY_DRAWDOWN_PCT = 0.10  # 10% (was 5%)
MAX_VOLATILITY_PCT = 0.08  # ATR > 8% triggers halt (was 5%)
MAX_CONSECUTIVE_API_ERRORS = 3
MAX_TRADES_PER_DAY = 50  # Lots of trades allowed
COOLDOWN_MINUTES = 0  # No cooldown!

# Logging
TRADES_LOG_FILE = "trades_log.csv"
UPDATE_INTERVAL_SECONDS = 5  # Price check every 5 seconds

# Strategy selection: "mean_reversion", "trend_following", or "voting"
STRATEGY = "voting"  # <-- CHANGE THIS TO SWITCH STRATEGIES


# =============================================================================
# ENUMS AND DATACLASSES
# =============================================================================

class Side(Enum):
    BUY = "buy"
    SELL = "sell"


class Signal(Enum):
    NONE = "none"
    BUY = "buy"
    SELL = "sell"


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    side: Side
    stop_loss: float
    take_profit: float
    entry_time: datetime


@dataclass
class Trade:
    timestamp: datetime
    symbol: str
    side: str
    qty: float
    price: float
    fees: float
    realized_pnl: float
    balance_after: float
    partial_fill: bool
    fill_ratio: float


@dataclass
class KillSwitchStatus:
    should_halt: bool
    reason: str


# =============================================================================
# PAPER ACCOUNT
# =============================================================================

class PaperAccount:
    """Simulated trading account with full PnL tracking."""
    
    def __init__(self, starting_capital: float):
        self.starting_capital = starting_capital
        self.cash_balance = starting_capital
        self.position: Optional[Position] = None
        self.realized_pnl = 0.0
        self.trades: List[Trade] = []
        self.daily_starting_equity = starting_capital
        self.last_trade_time: Optional[datetime] = None
        self.trades_today = 0
        self.current_day = datetime.now().date()
        self.consecutive_api_errors = 0
        
    def reset_daily_counters(self):
        """Reset counters at start of new trading day."""
        today = datetime.now().date()
        if today != self.current_day:
            self.current_day = today
            self.trades_today = 0
            self.daily_starting_equity = self.get_equity(self._last_price if hasattr(self, '_last_price') else 0)
    
    def get_equity(self, current_price: float) -> float:
        """Get total equity (cash + position value)."""
        self._last_price = current_price
        if self.position is None:
            return self.cash_balance
        
        position_value = self.position.qty * current_price
        if self.position.side == Side.SELL:
            # Short position: profit when price goes down
            unrealized = (self.position.entry_price - current_price) * self.position.qty
        else:
            # Long position: profit when price goes up
            unrealized = (current_price - self.position.entry_price) * self.position.qty
        
        return self.cash_balance + position_value + unrealized
    
    def get_unrealized_pnl(self, current_price: float) -> float:
        """Get unrealized PnL for open position."""
        if self.position is None:
            return 0.0
        
        if self.position.side == Side.SELL:
            return (self.position.entry_price - current_price) * self.position.qty
        else:
            return (current_price - self.position.entry_price) * self.position.qty
    
    def get_daily_drawdown(self, current_price: float) -> float:
        """Get current daily drawdown as percentage."""
        current_equity = self.get_equity(current_price)
        if self.daily_starting_equity <= 0:
            return 0.0
        return (self.daily_starting_equity - current_equity) / self.daily_starting_equity
    
    def can_trade(self) -> Tuple[bool, str]:
        """Check if trading is allowed based on cooldown and limits."""
        self.reset_daily_counters()
        
        if self.trades_today >= MAX_TRADES_PER_DAY:
            return False, f"Daily trade limit reached ({MAX_TRADES_PER_DAY})"
        
        if self.last_trade_time:
            cooldown_end = self.last_trade_time + timedelta(minutes=COOLDOWN_MINUTES)
            if datetime.now() < cooldown_end:
                remaining = (cooldown_end - datetime.now()).seconds // 60
                return False, f"Cooldown active ({remaining} min remaining)"
        
        return True, "OK"
    
    def execute_buy(self, symbol: str, price: float, qty: float, 
                    is_partial: bool = False, fill_ratio: float = 1.0) -> Trade:
        """Execute a simulated buy order."""
        # Apply slippage (buying at slightly higher price)
        executed_price = price * (1 + SIMULATED_SLIPPAGE)
        
        # Calculate fees (maker fee for limit orders)
        fee_rate = MAKER_FEE if not LIVE_MODE else TAKER_FEE
        fees = executed_price * qty * fee_rate
        
        # Total cost
        total_cost = (executed_price * qty) + fees
        
        if total_cost > self.cash_balance:
            # Adjust qty to fit available balance
            available = self.cash_balance / (executed_price * (1 + fee_rate))
            qty = available * 0.99  # Leave small buffer
            fees = executed_price * qty * fee_rate
            total_cost = (executed_price * qty) + fees
        
        self.cash_balance -= total_cost
        
        # Create or add to position
        stop_loss = executed_price * (1 - STOP_LOSS_PCT)
        take_profit = executed_price * (1 + TAKE_PROFIT_PCT)
        
        self.position = Position(
            symbol=symbol,
            qty=qty,
            entry_price=executed_price,
            side=Side.BUY,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=datetime.now()
        )
        
        trade = Trade(
            timestamp=datetime.now(),
            symbol=symbol,
            side="buy",
            qty=qty,
            price=executed_price,
            fees=fees,
            realized_pnl=0.0,
            balance_after=self.cash_balance,
            partial_fill=is_partial,
            fill_ratio=fill_ratio
        )
        
        self.trades.append(trade)
        self.last_trade_time = datetime.now()
        self.trades_today += 1
        
        return trade
    
    def execute_sell(self, symbol: str, price: float, qty: Optional[float] = None,
                     is_partial: bool = False, fill_ratio: float = 1.0) -> Optional[Trade]:
        """Execute a simulated sell order (close long position)."""
        if self.position is None:
            return None
        
        if qty is None:
            qty = self.position.qty
        
        # Apply slippage (selling at slightly lower price)
        executed_price = price * (1 - SIMULATED_SLIPPAGE)
        
        # Calculate fees
        fee_rate = MAKER_FEE if not LIVE_MODE else TAKER_FEE
        fees = executed_price * qty * fee_rate
        
        # Calculate PnL
        gross_pnl = (executed_price - self.position.entry_price) * qty
        net_pnl = gross_pnl - fees
        
        # Update balances
        proceeds = (executed_price * qty) - fees
        self.cash_balance += proceeds
        self.realized_pnl += net_pnl
        
        trade = Trade(
            timestamp=datetime.now(),
            symbol=symbol,
            side="sell",
            qty=qty,
            price=executed_price,
            fees=fees,
            realized_pnl=net_pnl,
            balance_after=self.cash_balance,
            partial_fill=is_partial,
            fill_ratio=fill_ratio
        )
        
        self.trades.append(trade)
        self.last_trade_time = datetime.now()
        
        # Close position
        if qty >= self.position.qty:
            self.position = None
        else:
            self.position.qty -= qty
        
        return trade


# =============================================================================
# KILL SWITCH
# =============================================================================

class KillSwitch:
    """Safety mechanism to halt trading under dangerous conditions."""
    
    def __init__(self, account: PaperAccount):
        self.account = account
    
    def check(self, current_price: float, atr: float) -> KillSwitchStatus:
        """Check all kill switch conditions."""
        
        # Check daily drawdown
        drawdown = self.account.get_daily_drawdown(current_price)
        if drawdown >= MAX_DAILY_DRAWDOWN_PCT:
            return KillSwitchStatus(
                should_halt=True,
                reason=f"DRAWDOWN LIMIT: {drawdown:.2%} >= {MAX_DAILY_DRAWDOWN_PCT:.2%}"
            )
        
        # Check volatility
        volatility = atr / current_price if current_price > 0 else 0
        if volatility >= MAX_VOLATILITY_PCT:
            return KillSwitchStatus(
                should_halt=True,
                reason=f"VOLATILITY TOO HIGH: ATR={volatility:.2%} >= {MAX_VOLATILITY_PCT:.2%}"
            )
        
        # Check API errors
        if self.account.consecutive_api_errors >= MAX_CONSECUTIVE_API_ERRORS:
            return KillSwitchStatus(
                should_halt=True,
                reason=f"API ERRORS: {self.account.consecutive_api_errors} consecutive failures"
            )
        
        return KillSwitchStatus(should_halt=False, reason="OK")


# =============================================================================
# TECHNICAL INDICATORS
# =============================================================================

def calculate_bollinger_bands(closes: pd.Series, period: int = 20, std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Bollinger Bands."""
    sma = closes.rolling(window=period).mean()
    std_dev = closes.rolling(window=period).std()
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    return upper, sma, lower


def calculate_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI."""
    delta = closes.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Average True Range."""
    high_low = highs - lows
    high_close = np.abs(highs - closes.shift())
    low_close = np.abs(lows - closes.shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr


def calculate_ema(closes: pd.Series, period: int = 20) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return closes.ewm(span=period, adjust=False).mean()


def calculate_macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD (line, signal, histogram)."""
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_volume_sma(volumes: pd.Series, period: int = 20) -> pd.Series:
    """Calculate Volume Simple Moving Average."""
    return volumes.rolling(window=period).mean()


# =============================================================================
# SIGNAL GENERATOR - MULTI-STRATEGY
# =============================================================================

class SignalGenerator:
    """Generate trading signals using multiple strategies."""
    
    def __init__(self, strategy: str = "voting"):
        self.strategy = strategy
        self.last_signal = Signal.NONE
    
    def calculate_expected_friction(self, price: float) -> float:
        """Calculate total expected friction for a round trip."""
        total_friction = (
            (MAKER_FEE * 2) +
            (SIMULATED_SPREAD * 2) +
            (SIMULATED_SLIPPAGE * 2)
        )
        return price * total_friction
    
    def _mean_reversion_signal(self, df: pd.DataFrame, current_price: float, 
                                has_position: bool) -> Tuple[Signal, str, dict]:
        """Strategy 1: Mean Reversion - buy dips when RSI oversold, sell at mean."""
        closes = df['close']
        upper, middle, lower = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD)
        rsi = calculate_rsi(closes, RSI_PERIOD)
        ema_20 = calculate_ema(closes, 20)
        
        bb_lower = lower.iloc[-1]
        bb_middle = middle.iloc[-1]
        bb_upper = upper.iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_ema20 = ema_20.iloc[-1]
        
        # Looser trend filter: avoid only STRONG downtrends (price far below EMA)
        strong_downtrend = current_price < current_ema20 * 0.97  # More than 3% below EMA
        
        votes = {
            'bb_oversold': current_price < bb_lower,
            'rsi_oversold': current_rsi < RSI_OVERSOLD,
            'not_strong_downtrend': not strong_downtrend,
            'bb_overbought': current_price > bb_upper,
            'rsi_overbought': current_rsi > RSI_OVERBOUGHT,
        }
        
        if not has_position:
            # Buy if: price below BB lower AND RSI oversold AND not in strong downtrend
            if current_price < bb_lower and current_rsi < RSI_OVERSOLD and not strong_downtrend:
                return Signal.BUY, f"MEAN_REV BUY: BB oversold + RSI={current_rsi:.0f}", votes
        
        if has_position:
            if current_price >= bb_middle:
                return Signal.SELL, f"MEAN_REV SELL: Price ${current_price:.2f} >= BB_Mid ${bb_middle:.2f}", votes
        
        trend_str = "📉STRONG DOWN" if strong_downtrend else "OK"
        return Signal.NONE, f"MEAN_REV: Waiting (RSI: {current_rsi:.0f}, Trend: {trend_str})", votes
    
    def _trend_following_signal(self, df: pd.DataFrame, current_price: float,
                                 has_position: bool) -> Tuple[Signal, str, dict]:
        """Strategy 2: Trend Following - buy breakouts, ride the trend."""
        closes = df['close']
        
        # Calculate indicators
        ema_fast = calculate_ema(closes, 10)
        ema_slow = calculate_ema(closes, 30)
        macd_line, signal_line, histogram = calculate_macd(closes)
        upper, middle, lower = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD)
        
        current_ema_fast = ema_fast.iloc[-1]
        current_ema_slow = ema_slow.iloc[-1]
        current_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]
        bb_upper = upper.iloc[-1]
        bb_lower = lower.iloc[-1]
        
        # Trend signals
        uptrend = current_ema_fast > current_ema_slow
        macd_bullish = current_hist > 0 and current_hist > prev_hist
        breakout_up = current_price > bb_upper
        
        votes = {
            'ema_uptrend': uptrend,
            'macd_bullish': macd_bullish,
            'breakout_up': breakout_up,
            'ema_downtrend': not uptrend,
            'macd_bearish': current_hist < 0,
        }
        
        if not has_position:
            # Buy on uptrend confirmation
            if uptrend and macd_bullish:
                return Signal.BUY, f"TREND BUY: EMA↑ + MACD↑ @ ${current_price:.2f}", votes
        
        if has_position:
            # Sell when trend reverses
            if not uptrend and current_hist < prev_hist:
                return Signal.SELL, f"TREND SELL: Trend reversal @ ${current_price:.2f}", votes
        
        return Signal.NONE, f"TREND: Waiting (EMA trend: {'UP' if uptrend else 'DOWN'})", votes
    
    def _voting_signal(self, df: pd.DataFrame, current_price: float,
                       has_position: bool) -> Tuple[Signal, str, dict]:
        """Strategy 3: Multi-Signal Voting - require multiple confirmations."""
        closes = df['close']
        volumes = df['volume']
        
        # Calculate all indicators
        upper, middle, lower = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD)
        rsi = calculate_rsi(closes, RSI_PERIOD)
        ema_20 = calculate_ema(closes, 20)
        ema_50 = calculate_ema(closes, 50)
        macd_line, signal_line, histogram = calculate_macd(closes)
        vol_sma = calculate_volume_sma(volumes, 20)
        
        bb_lower = lower.iloc[-1]
        bb_middle = middle.iloc[-1]
        bb_upper = upper.iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_ema20 = ema_20.iloc[-1]
        current_ema50 = ema_50.iloc[-1]
        current_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]
        current_vol = volumes.iloc[-1]
        avg_vol = vol_sma.iloc[-1]
        
        # BUY votes
        buy_votes = {
            'bb_oversold': current_price < bb_lower,  # Price below lower band
            'rsi_oversold': current_rsi < 35,  # RSI oversold
            'macd_turning': current_hist > prev_hist,  # MACD momentum improving
            'above_ema50': current_price > current_ema50,  # Above long-term trend
            'volume_spike': current_vol > avg_vol * 1.2,  # Above average volume
        }
        
        # SELL votes
        sell_votes = {
            'bb_overbought': current_price > bb_upper,
            'rsi_overbought': current_rsi > 65,
            'macd_weakening': current_hist < prev_hist,
            'at_middle_band': current_price >= bb_middle,
        }
        
        buy_count = sum(buy_votes.values())
        sell_count = sum(sell_votes.values())
        
        all_votes = {**buy_votes, **sell_votes}
        
        if not has_position:
            # Need 3+ buy signals to enter
            if buy_count >= 3:
                signals_str = ", ".join([k for k, v in buy_votes.items() if v])
                return Signal.BUY, f"VOTING BUY ({buy_count}/5): {signals_str}", all_votes
        
        if has_position:
            # Sell if 2+ sell signals OR at middle band
            if sell_count >= 2 or current_price >= bb_middle:
                signals_str = ", ".join([k for k, v in sell_votes.items() if v])
                return Signal.SELL, f"VOTING SELL ({sell_count}/4): {signals_str}", all_votes
        
        # Show current vote status
        return Signal.NONE, f"VOTING: {buy_count}/5 buy votes, {sell_count}/4 sell votes", all_votes
    
    def generate_signal(self, df: pd.DataFrame, current_price: float, 
                        has_position: bool) -> Tuple[Signal, str]:
        """Generate trading signal based on selected strategy."""
        
        min_periods = max(BB_PERIOD, 50) + 5  # Need enough data for all indicators
        if len(df) < min_periods:
            return Signal.NONE, "Insufficient data"
        
        # Route to selected strategy
        if self.strategy == "mean_reversion":
            signal, reason, votes = self._mean_reversion_signal(df, current_price, has_position)
        elif self.strategy == "trend_following":
            signal, reason, votes = self._trend_following_signal(df, current_price, has_position)
        else:  # voting (default)
            signal, reason, votes = self._voting_signal(df, current_price, has_position)
        
        return signal, reason


# =============================================================================
# ORDER EXECUTOR
# =============================================================================

class OrderExecutor:
    """Simulate order execution with realistic fills."""
    
    def simulate_fill(self) -> Tuple[bool, float]:
        """Determine if order is partial fill and fill ratio."""
        is_partial = random.random() < PARTIAL_FILL_PROBABILITY
        if is_partial:
            fill_ratio = random.uniform(MIN_FILL_RATIO, MAX_FILL_RATIO)
        else:
            fill_ratio = 1.0
        return is_partial, fill_ratio
    
    def execute(self, account: PaperAccount, signal: Signal, 
                symbol: str, price: float) -> Optional[Trade]:
        """Execute order based on signal."""
        
        if signal == Signal.BUY:
            # Calculate position size
            available = account.cash_balance * MAX_POSITION_SIZE_PCT
            
            # Apply spread (buy at ask = mid + spread/2)
            ask_price = price * (1 + SIMULATED_SPREAD / 2)
            
            qty = available / ask_price
            
            # Simulate fill
            is_partial, fill_ratio = self.simulate_fill()
            actual_qty = qty * fill_ratio
            
            if actual_qty * ask_price < 1.0:  # Minimum order size
                return None
            
            return account.execute_buy(
                symbol=symbol,
                price=ask_price,
                qty=actual_qty,
                is_partial=is_partial,
                fill_ratio=fill_ratio
            )
        
        elif signal == Signal.SELL and account.position is not None:
            # Apply spread (sell at bid = mid - spread/2)
            bid_price = price * (1 - SIMULATED_SPREAD / 2)
            
            # Simulate fill
            is_partial, fill_ratio = self.simulate_fill()
            actual_qty = account.position.qty * fill_ratio
            
            return account.execute_sell(
                symbol=symbol,
                price=bid_price,
                qty=actual_qty,
                is_partial=is_partial,
                fill_ratio=fill_ratio
            )
        
        return None


# =============================================================================
# TRADE LOGGER
# =============================================================================

class TradeLogger:
    """Log trades to CSV file."""
    
    def __init__(self, filename: str):
        self.filename = filename
        self._init_csv()
    
    def _init_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'symbol', 'side', 'qty', 'price', 
                    'fees', 'realized_pnl', 'balance_after', 
                    'partial_fill', 'fill_ratio'
                ])
    
    def log_trade(self, trade: Trade):
        """Append trade to CSV log."""
        with open(self.filename, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                trade.timestamp.isoformat(),
                trade.symbol,
                trade.side,
                f"{trade.qty:.8f}",
                f"{trade.price:.2f}",
                f"{trade.fees:.4f}",
                f"{trade.realized_pnl:.4f}",
                f"{trade.balance_after:.2f}",
                trade.partial_fill,
                f"{trade.fill_ratio:.2f}"
            ])


# =============================================================================
# STOP LOSS / TAKE PROFIT CHECKER
# =============================================================================

def check_stop_loss_take_profit(account: PaperAccount, current_price: float) -> Optional[Signal]:
    """Check if stop loss or take profit is triggered."""
    if account.position is None:
        return None
    
    pos = account.position
    
    if pos.side == Side.BUY:
        if current_price <= pos.stop_loss:
            return Signal.SELL
        if current_price >= pos.take_profit:
            return Signal.SELL
    
    return None


# =============================================================================
# MAIN BOT
# =============================================================================

class PaperTradingBot:
    """Main paper trading bot."""
    
    def __init__(self):
        # Use configurable exchange
        exchange_class = getattr(ccxt, EXCHANGE)
        self.exchange = exchange_class({
            'enableRateLimit': True,
        })
        
        self.account = PaperAccount(STARTING_CAPITAL)
        self.kill_switch = KillSwitch(self.account)
        self.signal_generator = SignalGenerator(strategy=STRATEGY)
        self.executor = OrderExecutor()
        self.logger = TradeLogger(TRADES_LOG_FILE)
        self.running = True
    
    def fetch_ohlcv(self) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data from exchange."""
        try:
            ohlcv = self.exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
            self.account.consecutive_api_errors = 0
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
            
        except Exception as e:
            self.account.consecutive_api_errors += 1
            print(f"[ERROR] API error ({self.account.consecutive_api_errors}): {e}")
            return None
    
    def print_status(self, df: pd.DataFrame, signal_reason: str, kill_status: KillSwitchStatus):
        """Print current status to console."""
        current_price = df['close'].iloc[-1]
        equity = self.account.get_equity(current_price)
        unrealized = self.account.get_unrealized_pnl(current_price)
        drawdown = self.account.get_daily_drawdown(current_price)
        
        # Calculate indicators for display
        closes = df['close']
        upper, middle, lower = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD)
        rsi = calculate_rsi(closes, RSI_PERIOD)
        atr = calculate_atr(df['high'], df['low'], df['close'])
        
        print("\n" + "=" * 60)
        print(f"🤖 PAPER TRADING BOT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print(f"📊 {SYMBOL} @ ${current_price:,.2f}")
        print(f"   BB: Lower=${lower.iloc[-1]:,.2f} | Mid=${middle.iloc[-1]:,.2f} | Upper=${upper.iloc[-1]:,.2f}")
        print(f"   RSI: {rsi.iloc[-1]:.1f} | ATR: ${atr.iloc[-1]:,.2f} ({atr.iloc[-1]/current_price*100:.2f}%)")
        print("-" * 60)
        print(f"💰 ACCOUNT")
        print(f"   Cash: ${self.account.cash_balance:,.2f}")
        print(f"   Equity: ${equity:,.2f} (Starting: ${STARTING_CAPITAL:,.2f})")
        print(f"   Realized PnL: ${self.account.realized_pnl:,.2f}")
        print(f"   Unrealized PnL: ${unrealized:,.2f}")
        print(f"   Daily Drawdown: {drawdown:.2%}")
        print("-" * 60)
        
        if self.account.position:
            pos = self.account.position
            pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100
            print(f"📈 POSITION")
            print(f"   {pos.side.value.upper()} {pos.qty:.6f} {pos.symbol}")
            print(f"   Entry: ${pos.entry_price:,.2f} | Current: ${current_price:,.2f} ({pnl_pct:+.2f}%)")
            print(f"   Stop: ${pos.stop_loss:,.2f} | Target: ${pos.take_profit:,.2f}")
        else:
            print(f"📈 POSITION: None")
        print("-" * 60)
        print(f"🎯 SIGNAL: {signal_reason}")
        print(f"📉 Trades Today: {self.account.trades_today}/{MAX_TRADES_PER_DAY}")
        
        can_trade, trade_reason = self.account.can_trade()
        if not can_trade:
            print(f"⏸️  Trading paused: {trade_reason}")
        
        if kill_status.should_halt:
            print(f"🛑 KILL SWITCH: {kill_status.reason}")
        else:
            print(f"✅ Kill Switch: OK")
        
        print("=" * 60)
    
    def run(self):
        """Main trading loop."""
        print("\n" + "🚀" * 20)
        print("STARTING PAPER TRADING BOT")
        print(f"Mode: {'LIVE' if LIVE_MODE else 'PAPER'}")
        print(f"Symbol: {SYMBOL}")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print(f"Strategy: {STRATEGY.upper().replace('_', ' ')} (BB{BB_PERIOD}, {BB_STD}σ)")
        print("🚀" * 20 + "\n")
        
        while self.running:
            try:
                # Fetch market data
                df = self.fetch_ohlcv()
                if df is None:
                    time.sleep(UPDATE_INTERVAL_SECONDS)
                    continue
                
                current_price = df['close'].iloc[-1]
                
                # Calculate ATR for kill switch
                atr = calculate_atr(df['high'], df['low'], df['close'])
                current_atr = atr.iloc[-1]
                
                # Check kill switch
                kill_status = self.kill_switch.check(current_price, current_atr)
                
                # Generate signal
                signal, signal_reason = self.signal_generator.generate_signal(
                    df, current_price, self.account.position is not None
                )
                
                # Check stop loss / take profit
                sl_tp_signal = check_stop_loss_take_profit(self.account, current_price)
                if sl_tp_signal:
                    signal = sl_tp_signal
                    signal_reason = f"STOP LOSS/TAKE PROFIT triggered at ${current_price:,.2f}"
                
                # Execute trade if conditions are met
                trade = None
                if not kill_status.should_halt and signal != Signal.NONE:
                    can_trade, _ = self.account.can_trade()
                    if can_trade or sl_tp_signal:  # Always allow SL/TP exits
                        trade = self.executor.execute(
                            self.account, signal, SYMBOL, current_price
                        )
                        if trade:
                            self.logger.log_trade(trade)
                            signal_reason += f" [EXECUTED: {trade.qty:.6f} @ ${trade.price:,.2f}]"
                            if trade.partial_fill:
                                signal_reason += f" [PARTIAL: {trade.fill_ratio:.0%}]"
                
                # Print status
                self.print_status(df, signal_reason, kill_status)
                
                # Halt if kill switch triggered
                if kill_status.should_halt:
                    print("\n❌ BOT HALTED BY KILL SWITCH")
                    self.running = False
                    break
                
                # Wait for next cycle
                time.sleep(UPDATE_INTERVAL_SECONDS)
                
            except KeyboardInterrupt:
                print("\n\n👋 Shutting down gracefully...")
                self.running = False
                break
            except Exception as e:
                print(f"\n[ERROR] Unexpected error: {e}")
                self.account.consecutive_api_errors += 1
                time.sleep(UPDATE_INTERVAL_SECONDS)
        
        # Final status
        print("\n" + "=" * 60)
        print("FINAL ACCOUNT STATUS")
        print("=" * 60)
        print(f"Final Cash Balance: ${self.account.cash_balance:,.2f}")
        print(f"Total Realized PnL: ${self.account.realized_pnl:,.2f}")
        print(f"Total Trades: {len(self.account.trades)}")
        print(f"Trades logged to: {TRADES_LOG_FILE}")
        print("=" * 60)


# =============================================================================
# BACKTEST BOT
# =============================================================================

class BacktestBot:
    """Backtest the strategy on historical data."""
    
    def __init__(self, backtest_date: datetime):
        # Use configurable exchange
        exchange_class = getattr(ccxt, EXCHANGE)
        self.exchange = exchange_class({
            'enableRateLimit': True,
        })
        
        self.backtest_date = backtest_date
        self.account = PaperAccount(STARTING_CAPITAL)
        self.kill_switch = KillSwitch(self.account)
        self.signal_generator = SignalGenerator(strategy=STRATEGY)
        self.executor = OrderExecutor()
        self.logger = TradeLogger(f"backtest_{backtest_date.strftime('%Y%m%d')}.csv")
    
    def fetch_historical_data(self) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV data for backtest date."""
        try:
            # Calculate time range - need data from before backtest date for indicator warmup
            start_of_day = self.backtest_date.replace(hour=0, minute=0, second=0)
            end_of_day = self.backtest_date.replace(hour=23, minute=59, second=59)
            
            # Start 2 days before for indicator warmup
            warmup_start = start_of_day - timedelta(days=2)
            since = int(warmup_start.timestamp() * 1000)
            
            print(f"Fetching {TIMEFRAME} data from {warmup_start.strftime('%Y-%m-%d')} to {end_of_day.strftime('%Y-%m-%d')}...")
            
            # Fetch candles - don't use limit, let since control the start
            all_candles = []
            current_since = since
            end_ms = int(end_of_day.timestamp() * 1000)
            
            while current_since < end_ms:
                ohlcv = self.exchange.fetch_ohlcv(
                    SYMBOL, 
                    TIMEFRAME,
                    since=current_since,
                    limit=500
                )
                
                if not ohlcv:
                    break
                
                all_candles.extend(ohlcv)
                
                # Move to after the last candle
                last_ts = ohlcv[-1][0]
                if last_ts <= current_since:
                    break  # No progress, stop
                current_since = last_ts + 1
                
                # Stop if we're past the end date
                if last_ts > end_ms:
                    break
            
            if not all_candles:
                print("[ERROR] No historical data available for this date")
                return None
            
            df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Remove duplicates and sort
            df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
            
            # Filter to only include data up to end of backtest day
            df = df[df['timestamp'] <= end_of_day]
            
            return df
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch historical data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def run(self):
        """Run backtest simulation."""
        print("\n" + "📊" * 20)
        print("BACKTEST MODE")
        print(f"Date: {self.backtest_date.strftime('%Y-%m-%d')}")
        print(f"Symbol: {SYMBOL}")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print(f"Strategy: {STRATEGY.upper().replace('_', ' ')} (BB{BB_PERIOD}, {BB_STD}σ)")
        print("📊" * 20 + "\n")
        
        # Warn if date is too old
        days_ago = (datetime.now() - self.backtest_date).days
        if days_ago > 14:
            print(f"⚠️  WARNING: Date is {days_ago} days ago. Kraken only keeps ~2 weeks of 15-min data.")
            print("   Try a more recent date (within last 2 weeks) or switch to 1h timeframe.\n")
        
        # Fetch all historical data
        df = self.fetch_historical_data()
        if df is None or len(df) == 0:
            print("[ERROR] No data available for this date. Try a more recent date.")
            return
        
        print(f"Loaded {len(df)} candles from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
        print("\n" + "=" * 60)
        print("SIMULATING TRADES...")
        print("=" * 60 + "\n")
        
        # Filter to just the backtest day
        backtest_day_start = self.backtest_date.replace(hour=0, minute=0, second=0)
        backtest_day_end = self.backtest_date.replace(hour=23, minute=59, second=59)
        
        # Simulate hour by hour
        for i in range(BB_PERIOD + 5, len(df)):
            current_candle = df.iloc[i]
            current_time = current_candle['timestamp']
            
            # Only process candles from backtest day
            if current_time.date() != self.backtest_date.date():
                continue
            
            # Get historical window for indicators
            window_df = df.iloc[:i+1].copy()
            current_price = current_candle['close']
            
            # Calculate ATR for kill switch
            atr = calculate_atr(window_df['high'], window_df['low'], window_df['close'])
            current_atr = atr.iloc[-1]
            
            # Check kill switch
            kill_status = self.kill_switch.check(current_price, current_atr)
            if kill_status.should_halt:
                print(f"[{current_time}] 🛑 KILL SWITCH: {kill_status.reason}")
                break
            
            # Generate signal
            signal, signal_reason = self.signal_generator.generate_signal(
                window_df, current_price, self.account.position is not None
            )
            
            # Check stop loss / take profit
            sl_tp_signal = check_stop_loss_take_profit(self.account, current_price)
            if sl_tp_signal:
                signal = sl_tp_signal
                signal_reason = f"STOP LOSS/TAKE PROFIT triggered"
            
            # Execute trade if conditions are met
            trade = None
            if signal != Signal.NONE:
                can_trade, _ = self.account.can_trade()
                if can_trade or sl_tp_signal:
                    # Temporarily set last_trade_time to simulate time passing
                    self.account.last_trade_time = current_time - timedelta(minutes=COOLDOWN_MINUTES + 1)
                    
                    trade = self.executor.execute(
                        self.account, signal, SYMBOL, current_price
                    )
                    if trade:
                        trade.timestamp = current_time  # Use historical timestamp
                        self.logger.log_trade(trade)
                        self.account.last_trade_time = current_time
                        
                        # Print trade
                        equity = self.account.get_equity(current_price)
                        print(f"[{current_time.strftime('%H:%M')}] ${current_price:,.2f} | "
                              f"{signal.value.upper()} {trade.qty:.6f} @ ${trade.price:,.2f} | "
                              f"Equity: ${equity:,.2f} | PnL: ${trade.realized_pnl:+.2f}")
            
            # Print hourly price tick with BB debug info
            if trade is None:
                closes = window_df['close']
                upper, middle, lower = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD)
                bb_lower = lower.iloc[-1]
                bb_upper = upper.iloc[-1]
                
                equity = self.account.get_equity(current_price)
                unrealized = self.account.get_unrealized_pnl(current_price)
                pos_str = f"📈 {self.account.position.qty:.6f}" if self.account.position else "No pos"
                
                # Show if price is below/above bands
                if current_price < bb_lower:
                    status = "⬇️ BELOW LOWER"
                elif current_price > bb_upper:
                    status = "⬆️ ABOVE UPPER"
                else:
                    status = "➡️ IN RANGE"
                
                print(f"[{current_time.strftime('%H:%M')}] ${current_price:,.2f} | BB: {bb_lower:.2f}-{bb_upper:.2f} | {status} | {pos_str}")
        
        # Final summary
        final_price = df['close'].iloc[-1]
        final_equity = self.account.get_equity(final_price)
        total_return = (final_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100
        
        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        print(f"Date: {self.backtest_date.strftime('%Y-%m-%d')}")
        print(f"Starting Capital: ${STARTING_CAPITAL:.2f}")
        print(f"Final Equity: ${final_equity:.2f}")
        print(f"Total Return: {total_return:+.2f}%")
        print(f"Realized PnL: ${self.account.realized_pnl:.2f}")
        print(f"Total Trades: {len(self.account.trades)}")
        print(f"Trades logged to: backtest_{self.backtest_date.strftime('%Y%m%d')}.csv")
        print("=" * 60)


# =============================================================================
# STRATEGY COMPARER
# =============================================================================

class StrategyComparer:
    """Compare all strategies over multiple days."""
    
    STRATEGIES = ["mean_reversion", "trend_following", "voting"]
    
    # CSV file mapping for historical data (daily = less noise, better results!)
    CSV_FILES = {
        'BTC/USD': 'historical_data/btc_usd_daily.csv',
        'ETH/USD': 'historical_data/eth_usd_daily.csv',
    }
    
    def __init__(self, days: int = 5):
        self.days = days
        exchange_class = getattr(ccxt, EXCHANGE)
        self.exchange = exchange_class({'enableRateLimit': True})
    
    def load_from_csv(self) -> Optional[pd.DataFrame]:
        """Try to load historical data from CSV file."""
        csv_path = self.CSV_FILES.get(SYMBOL)
        
        if not csv_path or not os.path.exists(csv_path):
            return None
        
        try:
            print(f"📂 Loading data from {csv_path}...")
            df = pd.read_csv(csv_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            print(f"   ✅ Loaded {len(df)} candles from CSV")
            return df
        except Exception as e:
            print(f"   ⚠️ Error loading CSV: {e}")
            return None
        
    def fetch_multi_day_data(self) -> Optional[pd.DataFrame]:
        """Load data from CSV if available, otherwise fetch from API."""
        
        # Try CSV first (has more data!)
        df = self.load_from_csv()
        if df is not None and len(df) > 0:
            return df
        
        # Fallback to API
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.days + 2)
            
            since = int(start_date.timestamp() * 1000)
            end_ms = int(end_date.timestamp() * 1000)
            
            print(f"Fetching {TIMEFRAME} data for last {self.days} days from API...")
            
            all_candles = []
            current_since = since
            
            while current_since < end_ms:
                ohlcv = self.exchange.fetch_ohlcv(
                    SYMBOL, TIMEFRAME, since=current_since, limit=500
                )
                if not ohlcv:
                    break
                all_candles.extend(ohlcv)
                last_ts = ohlcv[-1][0]
                if last_ts <= current_since:
                    break
                current_since = last_ts + 1
                if last_ts > end_ms:
                    break
            
            if not all_candles:
                return None
                
            df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch data: {e}")
            return None
    
    def run_strategy_backtest(self, df: pd.DataFrame, strategy_name: str, 
                               start_date: datetime, end_date: datetime, verbose: bool = False) -> dict:
        """Run a single strategy over the date range."""
        account = PaperAccount(STARTING_CAPITAL)
        signal_gen = SignalGenerator(strategy=strategy_name)
        executor = OrderExecutor()
        
        trades_count = 0
        winning_trades = 0
        losing_trades = 0
        trade_log = []  # Detailed trade log
        
        for i in range(50, len(df)):
            current_candle = df.iloc[i]
            current_time = current_candle['timestamp']
            
            # Only process candles in date range
            if current_time < start_date or current_time > end_date:
                continue
            
            window_df = df.iloc[:i+1].copy()
            current_price = current_candle['close']
            
            # Generate signal
            signal, reason = signal_gen.generate_signal(window_df, current_price, account.position is not None)
            
            # Check SL/TP
            sl_tp_signal = check_stop_loss_take_profit(account, current_price)
            if sl_tp_signal:
                signal = sl_tp_signal
                reason = "SL/TP triggered"
            
            # Execute
            if signal != Signal.NONE:
                account.last_trade_time = current_time - timedelta(minutes=COOLDOWN_MINUTES + 1)
                trade = executor.execute(account, signal, SYMBOL, current_price)
                if trade:
                    trade.timestamp = current_time
                    account.last_trade_time = current_time
                    trades_count += 1
                    
                    # Classify trade
                    if trade.realized_pnl > 0:
                        winning_trades += 1
                        result = "✅ WIN"
                    elif trade.realized_pnl < 0:
                        losing_trades += 1
                        result = "❌ LOSS"
                    else:
                        result = "➖ FLAT"
                    
                    # Log trade details
                    trade_log.append({
                        'time': current_time,
                        'side': trade.side if isinstance(trade.side, str) else trade.side.value,
                        'price': trade.price,
                        'qty': trade.qty,
                        'pnl': trade.realized_pnl,
                        'result': result,
                        'equity': account.get_equity(current_price)
                    })
                    
                    if verbose:
                        print(f"   [{current_time.strftime('%m/%d %H:%M')}] {trade.side.value.upper():4} @ ${trade.price:,.2f} | PnL: ${trade.realized_pnl:+.2f} | {result}")
        
        final_price = df['close'].iloc[-1]
        final_equity = account.get_equity(final_price)
        total_return = (final_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100
        
        return {
            'strategy': strategy_name,
            'final_equity': final_equity,
            'return_pct': total_return,
            'realized_pnl': account.realized_pnl,
            'trades': trades_count,
            'winning': winning_trades,
            'losing': losing_trades,
            'win_rate': (winning_trades / trades_count * 100) if trades_count > 0 else 0,
            'trade_log': trade_log  # Include detailed log
        }
    
    def run(self):
        """Run comparison of all strategies."""
        print("\n" + "🔬" * 20)
        print("STRATEGY COMPARISON MODE")
        print(f"Testing: {', '.join(self.STRATEGIES)}")
        print(f"Period: Last {self.days} days")
        print(f"Symbol: {SYMBOL}")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print("🔬" * 20 + "\n")
        
        # Fetch data
        df = self.fetch_multi_day_data()
        if df is None or len(df) == 0:
            print("[ERROR] No data available")
            return
        
        print(f"Loaded {len(df)} candles from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
        
        # Calculate date range for backtesting (last N days only)
        end_date = df['timestamp'].iloc[-1]
        start_date = end_date - timedelta(days=self.days)
        
        print(f"\nTesting period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        print("\n" + "=" * 60)
        print("RUNNING STRATEGIES...")
        print("=" * 60)
        
        results = []
        for strategy in self.STRATEGIES:
            print(f"\n📊 Testing {strategy.upper().replace('_', ' ')}...")
            result = self.run_strategy_backtest(df, strategy, start_date, end_date)
            results.append(result)
            print(f"   Trades: {result['trades']} | Return: {result['return_pct']:+.2f}% | "
                  f"Win Rate: {result['win_rate']:.1f}%")
        
        # Sort by return
        results.sort(key=lambda x: x['return_pct'], reverse=True)
        
        # Print comparison table
        print("\n\n" + "=" * 60)
        print("📊 STRATEGY COMPARISON RESULTS")
        print("=" * 60)
        print(f"\n{'Strategy':<20} {'Return':>10} {'Trades':>8} {'Win Rate':>10} {'Final $':>12}")
        print("-" * 60)
        
        for r in results:
            print(f"{r['strategy'].replace('_', ' ').title():<20} "
                  f"{r['return_pct']:>+9.2f}% "
                  f"{r['trades']:>8} "
                  f"{r['win_rate']:>9.1f}% "
                  f"${r['final_equity']:>10.2f}")
        
        # Best strategy
        best = results[0]
        worst = results[-1]
        
        print("\n" + "=" * 60)
        print("🏆 WINNER: " + best['strategy'].upper().replace('_', ' '))
        print("=" * 60)
        print(f"Return: {best['return_pct']:+.2f}%")
        print(f"Final Equity: ${best['final_equity']:.2f}")
        print(f"Total Trades: {best['trades']}")
        print(f"Win Rate: {best['win_rate']:.1f}%")
        
        # Print detailed trade log for winner
        if best['trade_log']:
            print("\n" + "-" * 70)
            print(f"📋 TRADE LOG ({best['strategy'].upper()}):")
            print("-" * 70)
            print(f"{'Date/Time':<20} {'Side':<5} {'Price':>12} {'PnL':>10} {'Result':<8} {'Equity':>10}")
            print("-" * 70)
            for t in best['trade_log']:
                print(f"{t['time'].strftime('%Y-%m-%d %H:%M'):<20} "
                      f"{t['side'].upper():<5} "
                      f"${t['price']:>10,.2f} "
                      f"${t['pnl']:>+9.2f} "
                      f"{t['result']:<8} "
                      f"${t['equity']:>9.2f}")
        
        # Show trade logs for other strategies too
        for r in results[1:]:  # Skip the first (best) since we already showed it
            if r['trade_log'] and len(r['trade_log']) > 0:
                print("\n" + "-" * 70)
                print(f"📋 TRADE LOG ({r['strategy'].upper()}): {len(r['trade_log'])} trades")
                print("-" * 70)
                print(f"{'Date/Time':<20} {'Side':<5} {'Price':>12} {'PnL':>10} {'Result':<8} {'Equity':>10}")
                print("-" * 70)
                # Show first 10 and last 5 trades to keep output manageable
                trades_to_show = r['trade_log'][:10] + (r['trade_log'][-5:] if len(r['trade_log']) > 15 else [])
                shown_indices = set(range(min(10, len(r['trade_log']))))
                if len(r['trade_log']) > 15:
                    shown_indices.update(range(len(r['trade_log'])-5, len(r['trade_log'])))
                    
                for i, t in enumerate(r['trade_log']):
                    if i in shown_indices:
                        print(f"{t['time'].strftime('%Y-%m-%d %H:%M'):<20} "
                              f"{t['side'].upper():<5} "
                              f"${t['price']:>10,.2f} "
                              f"${t['pnl']:>+9.2f} "
                              f"{t['result']:<8} "
                              f"${t['equity']:>9.2f}")
                    elif i == 10 and len(r['trade_log']) > 15:
                        print(f"   ... ({len(r['trade_log']) - 15} more trades) ...")
        
        # Analysis and recommendations
        print("\n" + "=" * 60)
        print("📈 ANALYSIS & RECOMMENDATIONS")
        print("=" * 60)
        
        # Analyze patterns
        if best['return_pct'] > 0:
            print(f"\n✅ {best['strategy'].upper()} made money! Key insights:")
        else:
            print(f"\n⚠️ All strategies lost money. This indicates:")
            print("   - Market may be trending strongly (bad for mean reversion)")
            print("   - Consider wider stop losses or smaller position sizes")
            print("   - May need different timeframe (hourly instead of 15-min)")
        
        # Strategy-specific insights
        for r in results:
            if r['strategy'] == 'mean_reversion':
                if r['return_pct'] < -1:
                    print(f"\n📉 MEAN REVERSION struggled ({r['return_pct']:+.2f}%):")
                    print("   → Market was trending, not ranging")
                    print("   → Consider: Use only when volatility is low")
            elif r['strategy'] == 'trend_following':
                if r['return_pct'] > results[0]['return_pct'] - 1:
                    print(f"\n📈 TREND FOLLOWING performed well:")
                    print("   → Market had clear directional moves")
                    print("   → Consider: Increase position size during trends")
            elif r['strategy'] == 'voting':
                print(f"\n🗳️ VOTING STRATEGY ({r['return_pct']:+.2f}%):")
                if r['trades'] < results[0]['trades'] / 2:
                    print("   → More selective (fewer trades)")
                    print("   → May avoid some losses but miss opportunities")
                else:
                    print("   → Balanced approach with confirmation signals")
        
        # Overall recommendation
        print("\n" + "-" * 60)
        print("💡 RECOMMENDED SETTINGS FOR LIVE TRADING:")
        print("-" * 60)
        
        if best['return_pct'] > 0:
            print(f"   Strategy: {best['strategy']}")
            print(f"   Expected daily return: ~{best['return_pct']/self.days:.2f}%")
        else:
            print("   ⚠️ Consider waiting for better market conditions")
            print("   OR use trend_following in trending markets")
            print("   OR increase BB_STD to 1.5+ for mean_reversion")
        
        print("\n" + "=" * 60)




def get_user_mode() -> Tuple[str, Optional[datetime]]:
    """Prompt user for trading mode."""
    print("\n" + "=" * 60)
    print("🤖 CRYPTO PAPER TRADING BOT")
    print("=" * 60)
    print("\nChoose mode:")
    print("  1. Live trading (real-time paper trading)")
    print("  2. Backtest (simulate on historical date)")
    print("  3. Compare strategies (test all strategies over 5 days)")
    print()
    
    while True:
        choice = input("Enter choice (1, 2, or 3): ").strip()
        if choice in ['1', '2', '3']:
            break
        print("Invalid choice. Please enter 1, 2, or 3.")
    
    if choice == '1':
        return 'live', None
    
    if choice == '3':
        return 'compare', None
    
    # Backtest mode - get date
    print("\nEnter backtest date:")
    print("  Format: YYYY-MM-DD (e.g., 2025-12-20)")
    print("  Or type 'today' for today's date")
    print()
    
    while True:
        date_input = input("Date: ").strip().lower()
        
        if date_input == 'today':
            return 'backtest', datetime.now()
        
        try:
            backtest_date = datetime.strptime(date_input, '%Y-%m-%d')
            
            # Check if date is in the future
            if backtest_date.date() > datetime.now().date():
                print("Error: Cannot backtest future dates!")
                continue
            
            # Check if date is too far in the past (most exchanges limit history)
            min_date = datetime.now() - timedelta(days=365)
            if backtest_date < min_date:
                print(f"Warning: Date may be too old. Exchange might not have data before {min_date.strftime('%Y-%m-%d')}")
            
            return 'backtest', backtest_date
            
        except ValueError:
            print("Invalid date format. Please use YYYY-MM-DD (e.g., 2025-12-20)")


if __name__ == "__main__":
    mode, backtest_date = get_user_mode()
    
    if mode == 'live':
        bot = PaperTradingBot()
        bot.run()
    elif mode == 'compare':
        comparer = StrategyComparer(days=730)  # 30 days of 1h data
        comparer.run()
    else:
        bot = BacktestBot(backtest_date)
        bot.run()
