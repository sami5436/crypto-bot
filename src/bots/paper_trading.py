"""
Paper trading bot for live spot trading.
"""

import ccxt
import pandas as pd
import time
from datetime import datetime
from typing import Optional

from config import (
    EXCHANGE, SYMBOL, TIMEFRAME, STARTING_CAPITAL, STRATEGY,
    BB_PERIOD, BB_STD, RSI_PERIOD,
    LIVE_MODE, TRADES_LOG_FILE, UPDATE_INTERVAL_SECONDS,
    MAX_TRADES_PER_DAY
)
from src.core.models import Signal, KillSwitchStatus
from src.strategies.indicators import calculate_bollinger_bands, calculate_rsi, calculate_atr
from src.core.account import PaperAccount
from src.strategies.strategies import SignalGenerator
from src.core.executor import KillSwitch, OrderExecutor, TradeLogger, check_stop_loss_take_profit
from src.bots.base import BaseBot


class PaperTradingBot(BaseBot):
    """Main paper trading bot for live spot trading."""
    
    def __init__(self):
        super().__init__()
        self.account = PaperAccount(STARTING_CAPITAL)
        self.kill_switch = KillSwitch(self.account)
        self.signal_generator = SignalGenerator(strategy=STRATEGY)
        self.executor = OrderExecutor()
        self.logger = TradeLogger(TRADES_LOG_FILE)
    
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
        
        closes = df['close']
        upper, middle, lower = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD)
        rsi = calculate_rsi(closes, RSI_PERIOD)
        atr = calculate_atr(df['high'], df['low'], df['close'])
        
        print("\n" + "=" * 60)
        print(f"PAPER TRADING BOT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print(f"{SYMBOL} @ ${current_price:,.2f}")
        print(f"   BB: Lower=${lower.iloc[-1]:,.2f} | Mid=${middle.iloc[-1]:,.2f} | Upper=${upper.iloc[-1]:,.2f}")
        print(f"   RSI: {rsi.iloc[-1]:.1f} | ATR: ${atr.iloc[-1]:,.2f} ({atr.iloc[-1]/current_price*100:.2f}%)")
        print("-" * 60)
        print(f"ACCOUNT")
        print(f"   Cash: ${self.account.cash_balance:,.2f}")
        print(f"   Equity: ${equity:,.2f} (Starting: ${STARTING_CAPITAL:,.2f})")
        print(f"   Realized PnL: ${self.account.realized_pnl:,.2f}")
        print(f"   Unrealized PnL: ${unrealized:,.2f}")
        print(f"   Daily Drawdown: {drawdown:.2%}")
        print("-" * 60)
        
        if self.account.position:
            pos = self.account.position
            pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100
            print(f"POSITION")
            print(f"   {pos.side.value.upper()} {pos.qty:.6f} {pos.symbol}")
            print(f"   Entry: ${pos.entry_price:,.2f} | Current: ${current_price:,.2f} ({pnl_pct:+.2f}%)")
            print(f"   Stop: ${pos.stop_loss:,.2f} | Target: ${pos.take_profit:,.2f}")
        else:
            print(f"POSITION: None")
        print("-" * 60)
        print(f"SIGNAL: {signal_reason}")
        print(f"Trades Today: {self.account.trades_today}/{MAX_TRADES_PER_DAY}")
        
        can_trade, trade_reason = self.account.can_trade()
        if not can_trade:
            print(f"Trading paused: {trade_reason}")
        
        if kill_status.should_halt:
            print(f"KILL SWITCH: {kill_status.reason}")
        else:
            print(f"Kill Switch: OK")
        
        print("=" * 60)
    
    def run(self):
        """Main trading loop."""
        print("\n" + "=" * 60)
        print("STARTING PAPER TRADING BOT")
        print(f"Mode: {'LIVE' if LIVE_MODE else 'PAPER'}")
        print(f"Symbol: {SYMBOL}")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print(f"Strategy: {STRATEGY.upper().replace('_', ' ')} (BB{BB_PERIOD}, {BB_STD}s)")
        print("=" * 60 + "\n")
        
        while self.running:
            try:
                df = self.fetch_ohlcv()
                if df is None:
                    time.sleep(UPDATE_INTERVAL_SECONDS)
                    continue
                
                current_price = df['close'].iloc[-1]
                atr = calculate_atr(df['high'], df['low'], df['close'])
                current_atr = atr.iloc[-1]
                
                kill_status = self.kill_switch.check(current_price, current_atr)
                
                signal, signal_reason = self.signal_generator.generate_signal(
                    df, current_price, self.account.position is not None
                )
                
                sl_tp_signal = check_stop_loss_take_profit(self.account, current_price)
                if sl_tp_signal:
                    signal = sl_tp_signal
                    signal_reason = f"STOP LOSS/TAKE PROFIT triggered at ${current_price:,.2f}"
                
                trade = None
                if not kill_status.should_halt and signal != Signal.NONE:
                    can_trade, _ = self.account.can_trade()
                    if can_trade or sl_tp_signal:
                        trade = self.executor.execute(
                            self.account, signal, SYMBOL, current_price
                        )
                        if trade:
                            self.logger.log_trade(trade)
                            signal_reason += f" [EXECUTED: {trade.qty:.6f} @ ${trade.price:,.2f}]"
                            if trade.partial_fill:
                                signal_reason += f" [PARTIAL: {trade.fill_ratio:.0%}]"
                
                self.print_status(df, signal_reason, kill_status)
                
                if kill_status.should_halt:
                    print("\nBOT HALTED BY KILL SWITCH")
                    self.running = False
                    break
                
                time.sleep(UPDATE_INTERVAL_SECONDS)
                
            except KeyboardInterrupt:
                print("\n\nShutting down gracefully...")
                self.running = False
                break
            except Exception as e:
                print(f"\n[ERROR] Unexpected error: {e}")
                self.account.consecutive_api_errors += 1
                time.sleep(UPDATE_INTERVAL_SECONDS)
        
        print("\n" + "=" * 60)
        print("FINAL ACCOUNT STATUS")
        print("=" * 60)
        print(f"Final Cash Balance: ${self.account.cash_balance:,.2f}")
        print(f"Total Realized PnL: ${self.account.realized_pnl:,.2f}")
        print(f"Total Trades: {len(self.account.trades)}")
        print(f"Trades logged to: {TRADES_LOG_FILE}")
        print("=" * 60)
