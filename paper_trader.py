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
STARTING_CAPITAL = 50.0  # USD
SYMBOL = "BTC/USD"  # Kraken uses USD not USDT
TIMEFRAME = "1h"

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

# Strategy parameters - AGGRESSIVE MODE
BB_PERIOD = 20
BB_STD = 1.5  # Tighter bands = more signals (was 2.5)
RSI_PERIOD = 14
RSI_OVERSOLD = 40  # Relaxed from 30 = more buy signals
RSI_OVERBOUGHT = 60  # Relaxed from 70 = more sell signals

# Risk management
STOP_LOSS_PCT = 0.02  # 2%
TAKE_PROFIT_PCT = 0.025  # 2.5% (tighter for faster exits)
MAX_POSITION_SIZE_PCT = 0.90  # Use max 90% of capital per trade
MIN_EXPECTED_EDGE = 0.001  # 0.1% minimum edge (was 0.3%)

# Kill switch thresholds
MAX_DAILY_DRAWDOWN_PCT = 0.10  # 10% (was 5%)
MAX_VOLATILITY_PCT = 0.08  # ATR > 8% triggers halt (was 5%)
MAX_CONSECUTIVE_API_ERRORS = 3
MAX_TRADES_PER_DAY = 8  # More trades allowed (was 3)
COOLDOWN_MINUTES = 5  # Much shorter cooldown (was 30)

# Logging
TRADES_LOG_FILE = "trades_log.csv"
UPDATE_INTERVAL_SECONDS = 5  # Price check every 5 seconds


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


# =============================================================================
# SIGNAL GENERATOR
# =============================================================================

class SignalGenerator:
    """Generate trading signals using Bollinger Band mean reversion."""
    
    def __init__(self):
        self.last_signal = Signal.NONE
    
    def calculate_expected_friction(self, price: float) -> float:
        """Calculate total expected friction for a round trip."""
        # Entry fee + exit fee + spread + slippage (both ways)
        total_friction = (
            (MAKER_FEE * 2) +  # Entry and exit fees
            (SIMULATED_SPREAD * 2) +  # Bid-ask spread both ways
            (SIMULATED_SLIPPAGE * 2)  # Slippage both ways
        )
        return price * total_friction
    
    def generate_signal(self, df: pd.DataFrame, current_price: float, 
                        has_position: bool) -> Tuple[Signal, str]:
        """Generate trading signal based on Bollinger Bands and RSI."""
        
        if len(df) < BB_PERIOD + 5:
            return Signal.NONE, "Insufficient data"
        
        # Calculate indicators
        closes = df['close']
        upper, middle, lower = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD)
        rsi = calculate_rsi(closes, RSI_PERIOD)
        
        current_upper = upper.iloc[-1]
        current_lower = lower.iloc[-1]
        current_middle = middle.iloc[-1]
        current_rsi = rsi.iloc[-1]
        prev_close = closes.iloc[-2]
        
        # Calculate expected move to middle band
        if current_price < current_lower:
            expected_move = (current_middle - current_price) / current_price
        elif current_price > current_upper:
            expected_move = (current_price - current_middle) / current_price
        else:
            expected_move = 0
        
        # Calculate friction
        friction = self.calculate_expected_friction(current_price) / current_price
        expected_net_edge = expected_move - friction
        
        # Check for BUY signal
        if not has_position:
            # Price crossed below lower band + RSI oversold + sufficient edge
            if (current_price < current_lower and 
                prev_close >= lower.iloc[-2] and
                current_rsi < RSI_OVERSOLD and
                expected_net_edge >= MIN_EXPECTED_EDGE):
                
                return Signal.BUY, (
                    f"BUY: Price {current_price:.2f} < BB_Lower {current_lower:.2f}, "
                    f"RSI={current_rsi:.1f}, Expected edge={expected_net_edge:.2%}"
                )
            
            # Price crossed above upper band (potential short, but we're spot only)
            # We reject this as we can't short in spot trading
            if current_price > current_upper and current_rsi > RSI_OVERBOUGHT:
                return Signal.NONE, "Short signal rejected (spot only)"
        
        # Check for SELL signal (exit long position)
        if has_position:
            # Take profit at middle band or above
            if current_price >= current_middle:
                return Signal.SELL, f"SELL: Price {current_price:.2f} >= BB_Middle {current_middle:.2f}"
        
        # No signal - check why
        if current_price >= current_lower and current_price <= current_upper:
            return Signal.NONE, f"Price in neutral zone (BB: {current_lower:.2f} - {current_upper:.2f})"
        
        if expected_net_edge < MIN_EXPECTED_EDGE:
            return Signal.NONE, f"Edge too low: {expected_net_edge:.2%} < {MIN_EXPECTED_EDGE:.2%}"
        
        return Signal.NONE, "No valid signal"


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
        self.signal_generator = SignalGenerator()
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
        print(f"Strategy: Bollinger Band Mean Reversion (BB{BB_PERIOD}, {BB_STD}σ)")
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
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    bot = PaperTradingBot()
    bot.run()
