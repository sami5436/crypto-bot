"""
Backtest bot for historical data simulation.
"""

import ccxt
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

from config import (
    EXCHANGE, SYMBOL, TIMEFRAME, STARTING_CAPITAL, STRATEGY,
    BB_PERIOD, BB_STD, COOLDOWN_MINUTES
)
from src.core.models import Signal
from src.strategies.indicators import calculate_bollinger_bands, calculate_atr
from src.core.account import PaperAccount
from src.strategies.strategies import SignalGenerator
from src.core.executor import KillSwitch, OrderExecutor, TradeLogger, check_stop_loss_take_profit
from src.bots.base import BaseBot


class BacktestBot(BaseBot):
    """Backtest the strategy on historical data."""
    
    def __init__(self, backtest_date: datetime):
        super().__init__()
        self.backtest_date = backtest_date
        self.account = PaperAccount(STARTING_CAPITAL)
        self.kill_switch = KillSwitch(self.account)
        self.signal_generator = SignalGenerator(strategy=STRATEGY)
        self.executor = OrderExecutor()
        self.logger = TradeLogger(f"logs/backtest_{backtest_date.strftime('%Y%m%d')}.csv")
    
    def fetch_historical_data(self) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV data for backtest date."""
        try:
            start_of_day = self.backtest_date.replace(hour=0, minute=0, second=0)
            end_of_day = self.backtest_date.replace(hour=23, minute=59, second=59)
            
            warmup_start = start_of_day - timedelta(days=2)
            since = int(warmup_start.timestamp() * 1000)
            
            print(f"Fetching {TIMEFRAME} data from {warmup_start.strftime('%Y-%m-%d')} to {end_of_day.strftime('%Y-%m-%d')}...")
            
            all_candles = []
            current_since = since
            end_ms = int(end_of_day.timestamp() * 1000)
            
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
                print("[ERROR] No historical data available for this date")
                return None
            
            df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
            df = df[df['timestamp'] <= end_of_day]
            
            return df
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch historical data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def print_status(self, *args, **kwargs):
        """Not used in backtest mode."""
        pass
    
    def run(self):
        """Run backtest simulation."""
        print("\n" + "=" * 60)
        print("BACKTEST MODE")
        print(f"Date: {self.backtest_date.strftime('%Y-%m-%d')}")
        print(f"Symbol: {SYMBOL}")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print(f"Strategy: {STRATEGY.upper().replace('_', ' ')} (BB{BB_PERIOD}, {BB_STD}s)")
        print("=" * 60 + "\n")
        
        days_ago = (datetime.now() - self.backtest_date).days
        if days_ago > 14:
            print(f"WARNING: Date is {days_ago} days ago. Kraken only keeps ~2 weeks of 15-min data.")
            print("   Try a more recent date (within last 2 weeks) or switch to 1h timeframe.\n")
        
        df = self.fetch_historical_data()
        if df is None or len(df) == 0:
            print("[ERROR] No data available for this date. Try a more recent date.")
            return
        
        print(f"Loaded {len(df)} candles from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
        print("\n" + "=" * 60)
        print("SIMULATING TRADES...")
        print("=" * 60 + "\n")
        
        for i in range(BB_PERIOD + 5, len(df)):
            current_candle = df.iloc[i]
            current_time = current_candle['timestamp']
            
            if current_time.date() != self.backtest_date.date():
                continue
            
            window_df = df.iloc[:i+1].copy()
            current_price = current_candle['close']
            
            atr = calculate_atr(window_df['high'], window_df['low'], window_df['close'])
            current_atr = atr.iloc[-1]
            
            kill_status = self.kill_switch.check(current_price, current_atr)
            if kill_status.should_halt:
                print(f"[{current_time}] KILL SWITCH: {kill_status.reason}")
                break
            
            signal, signal_reason = self.signal_generator.generate_signal(
                window_df, current_price, self.account.position is not None
            )
            
            sl_tp_signal = check_stop_loss_take_profit(self.account, current_price)
            if sl_tp_signal:
                signal = sl_tp_signal
                signal_reason = f"STOP LOSS/TAKE PROFIT triggered"
            
            trade = None
            if signal != Signal.NONE:
                can_trade, _ = self.account.can_trade()
                if can_trade or sl_tp_signal:
                    self.account.last_trade_time = current_time - timedelta(minutes=COOLDOWN_MINUTES + 1)
                    
                    trade = self.executor.execute(
                        self.account, signal, SYMBOL, current_price
                    )
                    if trade:
                        trade.timestamp = current_time
                        self.logger.log_trade(trade)
                        self.account.last_trade_time = current_time
                        
                        equity = self.account.get_equity(current_price)
                        print(f"[{current_time.strftime('%H:%M')}] ${current_price:,.2f} | "
                              f"{signal.value.upper()} {trade.qty:.6f} @ ${trade.price:,.2f} | "
                              f"Equity: ${equity:,.2f} | PnL: ${trade.realized_pnl:+.2f}")
            
            if trade is None:
                closes = window_df['close']
                upper, middle, lower = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD)
                bb_lower = lower.iloc[-1]
                bb_upper = upper.iloc[-1]
                
                equity = self.account.get_equity(current_price)
                pos_str = f"{self.account.position.qty:.6f}" if self.account.position else "No pos"
                
                if current_price < bb_lower:
                    status = "BELOW LOWER"
                elif current_price > bb_upper:
                    status = "ABOVE UPPER"
                else:
                    status = "IN RANGE"
                
                print(f"[{current_time.strftime('%H:%M')}] ${current_price:,.2f} | BB: {bb_lower:.2f}-{bb_upper:.2f} | {status} | {pos_str}")
        
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
