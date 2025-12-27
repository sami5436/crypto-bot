"""
Trading bot classes: Live trading, Backtest, and Strategy Comparison.
"""

import ccxt
import os
import pandas as pd
import time
from datetime import datetime, timedelta
from typing import Optional

from config import (
    EXCHANGE, SYMBOL, TIMEFRAME, STARTING_CAPITAL, STRATEGY,
    BB_PERIOD, BB_STD, RSI_PERIOD,
    LIVE_MODE, TRADES_LOG_FILE, UPDATE_INTERVAL_SECONDS,
    MAX_TRADES_PER_DAY, COOLDOWN_MINUTES, HOURLY_COOLDOWN_MINUTES,
    FUTURES_MODE, LEVERAGE, FUTURES_SYMBOL
)
from models import Signal, KillSwitchStatus, PositionSide
from indicators import calculate_bollinger_bands, calculate_rsi, calculate_atr
from account import PaperAccount, FuturesAccount
from strategies import SignalGenerator, HourlySignalGenerator, FuturesSignalGenerator
from executor import (
    KillSwitch, OrderExecutor, FuturesOrderExecutor, TradeLogger, 
    check_stop_loss_take_profit, check_futures_liquidation
)


class PaperTradingBot:
    """Main paper trading bot for live trading."""
    
    def __init__(self):
        exchange_class = getattr(ccxt, EXCHANGE)
        self.exchange = exchange_class({'enableRateLimit': True})
        
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
                    print("\n❌ BOT HALTED BY KILL SWITCH")
                    self.running = False
                    break
                
                time.sleep(UPDATE_INTERVAL_SECONDS)
                
            except KeyboardInterrupt:
                print("\n\n👋 Shutting down gracefully...")
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


class FuturesPaperTradingBot:
    """Live futures paper trading bot with longs and shorts."""
    
    def __init__(self, leverage: int = LEVERAGE):
        exchange_class = getattr(ccxt, EXCHANGE)
        self.exchange = exchange_class({'enableRateLimit': True})
        
        self.leverage = leverage
        self.account = FuturesAccount(STARTING_CAPITAL, leverage=leverage)
        self.kill_switch = KillSwitch(self.account)
        self.signal_generator = FuturesSignalGenerator(strategy=STRATEGY)
        self.executor = FuturesOrderExecutor()
        self.logger = TradeLogger("futures_trades.csv")
        self.running = True
        
        # Session tracking for detailed log
        self.start_time = datetime.now()
        self.session_log = []  # List of events for detailed logging
    
    def fetch_ohlcv(self) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data from exchange."""
        try:
            # Use 1-minute candles for fastest signals in live trading
            ohlcv = self.exchange.fetch_ohlcv(SYMBOL, "1m", limit=100)
            self.account.consecutive_api_errors = 0
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
            
        except Exception as e:
            self.account.consecutive_api_errors += 1
            print(f"[ERROR] API error ({self.account.consecutive_api_errors}): {e}")
            return None
    
    def print_status(self, df: pd.DataFrame, signal_reason: str, kill_status: KillSwitchStatus):
        """Print current status to console - simple, clean format."""
        import os
        os.system('clear' if os.name != 'nt' else 'cls')
        
        current_price = df['close'].iloc[-1]
        equity = self.account.get_equity(current_price)
        unrealized = self.account.get_unrealized_pnl(current_price)
        total_return = (equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100
        
        closes = df['close']
        rsi = calculate_rsi(closes, RSI_PERIOD)
        
        print("=" * 60)
        print(f"FUTURES PAPER TRADING  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print()
        print(f"  MARKET")
        print(f"    {SYMBOL}         ${current_price:,.2f}")
        print(f"    RSI              {rsi.iloc[-1]:.1f}")
        print(f"    Leverage         {self.leverage}x")
        print()
        print(f"  ACCOUNT")
        print(f"    Equity           ${equity:,.2f}  ({total_return:+.2f}%)")
        print(f"    Realized PnL     ${self.account.realized_pnl:+,.2f}")
        print(f"    Unrealized PnL   ${unrealized:+,.2f}")
        print()
        
        if self.account.position:
            pos = self.account.position
            pnl = pos.calculate_pnl(current_price)
            roe = pos.calculate_roe(current_price)
            pct_move = (current_price - pos.entry_price) / pos.entry_price * 100
            side_str = "LONG" if pos.side == PositionSide.LONG else "SHORT"
            
            print(f"  POSITION [{side_str}]")
            print(f"    Entry            ${pos.entry_price:,.2f}")
            print(f"    Current          ${current_price:,.2f}  ({pct_move:+.2f}%)")
            print(f"    PnL              ${pnl:+,.2f}  ({roe:+.1%} ROE)")
            print(f"    Liquidation      ${pos.liquidation_price:,.2f}")
        else:
            print(f"  POSITION")
            print(f"    No open position")
        print()
        
        print(f"  SIGNAL")
        print(f"    {signal_reason}")
        print()
        
        status = "HALTED: " + kill_status.reason if kill_status.should_halt else "ACTIVE"
        print(f"  STATUS: {status}  |  Trades: {self.account.trades_today}/{MAX_TRADES_PER_DAY}")
        print()
        print("=" * 60)
    
    def run(self):
        """Main futures trading loop."""
        print("\n" + "🔮" * 20)
        print("STARTING FUTURES PAPER TRADING BOT")
        print(f"Mode: PAPER (Futures)")
        print(f"Symbol: {SYMBOL}")
        print(f"Leverage: {self.leverage}x")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print(f"Strategy: {STRATEGY.upper().replace('_', ' ')}")
        print("🔮" * 20 + "\n")
        
        while self.running:
            try:
                df = self.fetch_ohlcv()
                if df is None:
                    time.sleep(UPDATE_INTERVAL_SECONDS)
                    continue
                
                current_price = df['close'].iloc[-1]
                atr = calculate_atr(df['high'], df['low'], df['close'])
                current_atr = atr.iloc[-1]
                
                # Check kill switch
                kill_status = self.kill_switch.check(current_price, current_atr)
                
                # Check liquidation
                liq_signal = check_futures_liquidation(self.account, current_price)
                if liq_signal:
                    trade = self.executor.execute(self.account, liq_signal, SYMBOL, current_price)
                    if trade:
                        trade.is_liquidation = True
                        self.logger.log_trade(trade)
                        print("\n💀 POSITION LIQUIDATED!")
                
                # Get current position side
                if self.account.position is None:
                    position_side = 'none'
                else:
                    position_side = self.account.position.side.value
                
                # Generate signal
                signal, signal_reason = self.signal_generator.generate_signal(
                    df, current_price, position_side
                )
                
                # OPTION D: Profit/loss threshold - don't close on tiny moves
                # Only close if position has moved at least 0.15% (prevents oscillation but allows profit-taking)
                MIN_CLOSE_THRESHOLD = 0.0015  # 0.15% move required to close
                if signal in [Signal.CLOSE_LONG, Signal.CLOSE_SHORT] and self.account.position:
                    pos = self.account.position
                    move_pct = abs(current_price - pos.entry_price) / pos.entry_price
                    if move_pct < MIN_CLOSE_THRESHOLD:
                        signal = Signal.NONE
                        signal_reason = f"HOLDING (move {move_pct:.3%} < {MIN_CLOSE_THRESHOLD:.2%} threshold)"
                
                # Check stop loss / take profit (these override the threshold)
                sl_tp_signal = check_stop_loss_take_profit(self.account, current_price)
                if sl_tp_signal:
                    signal = sl_tp_signal
                    signal_reason = f"STOP LOSS/TAKE PROFIT @ ${current_price:,.2f}"
                
                # Execute trade
                trade = None
                if not kill_status.should_halt and signal != Signal.NONE:
                    can_trade, _ = self.account.can_trade()
                    if can_trade or sl_tp_signal:
                        trade = self.executor.execute(
                            self.account, signal, SYMBOL, current_price
                        )
                        if trade:
                            self.logger.log_trade(trade)
                            signal_reason += f" [EXECUTED: {trade.side.upper()}]"
                
                self.print_status(df, signal_reason, kill_status)
                
                if kill_status.should_halt:
                    print("\n❌ BOT HALTED BY KILL SWITCH")
                    self.running = False
                    break
                
                # Update every 60 seconds (once per minute)
                time.sleep(60)
                
            except KeyboardInterrupt:
                print("\n\n👋 Shutting down gracefully...")
                self.running = False
                break
            except Exception as e:
                print(f"\n[ERROR] Unexpected error: {e}")
                self.account.consecutive_api_errors += 1
                self.session_log.append(f"{datetime.now()}: ERROR - {e}")
                time.sleep(60)
        
        # Final status
        final_price = df['close'].iloc[-1] if df is not None else 0
        final_equity = self.account.get_equity(final_price)
        total_return = (final_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100
        
        print("\n" + "=" * 60)
        print("SESSION ENDED")
        print("=" * 60)
        print(f"  Final Equity:      ${final_equity:,.2f}")
        print(f"  Total Return:      {total_return:+.2f}%")
        print(f"  Realized PnL:      ${self.account.realized_pnl:+,.2f}")
        print(f"  Total Trades:      {len(self.account.trades)}")
        print("=" * 60)
        
        # Write detailed session log
        self._write_session_log(final_price)
    
    def _write_session_log(self, final_price: float):
        """Write detailed session log to file."""
        log_filename = f"session_log_{self.start_time.strftime('%Y%m%d_%H%M%S')}.txt"
        
        final_equity = self.account.get_equity(final_price)
        total_return = (final_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100
        session_duration = datetime.now() - self.start_time
        
        with open(log_filename, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("FUTURES PAPER TRADING SESSION LOG\n")
            f.write("=" * 70 + "\n\n")
            
            # Session Overview
            f.write("SESSION OVERVIEW\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Start Time:        {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  End Time:          {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  Duration:          {str(session_duration).split('.')[0]}\n")
            f.write(f"  Symbol:            {SYMBOL}\n")
            f.write(f"  Leverage:          {self.leverage}x\n")
            f.write(f"  Strategy:          {STRATEGY}\n")
            f.write("\n")
            
            # Account Summary
            f.write("ACCOUNT SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Starting Capital:  ${STARTING_CAPITAL:,.2f}\n")
            f.write(f"  Final Equity:      ${final_equity:,.2f}\n")
            f.write(f"  Total Return:      {total_return:+.2f}%\n")
            f.write(f"  Realized PnL:      ${self.account.realized_pnl:+,.2f}\n")
            f.write("\n")
            
            # Trade Summary
            f.write("TRADE SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Total Trades:      {len(self.account.trades)}\n")
            
            if self.account.trades:
                winning = sum(1 for t in self.account.trades if t.realized_pnl > 0)
                losing = sum(1 for t in self.account.trades if t.realized_pnl < 0)
                flat = len(self.account.trades) - winning - losing
                win_rate = winning / len(self.account.trades) * 100 if self.account.trades else 0
                f.write(f"  Winning Trades:    {winning}\n")
                f.write(f"  Losing Trades:     {losing}\n")
                f.write(f"  Flat Trades:       {flat}\n")
                f.write(f"  Win Rate:          {win_rate:.1f}%\n")
            f.write("\n")
            
            # Trade Log
            f.write("TRADE LOG\n")
            f.write("-" * 70 + "\n")
            if self.account.trades:
                for i, trade in enumerate(self.account.trades, 1):
                    f.write(f"  {i}. {trade.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"     Side: {trade.side.upper()}  |  Price: ${trade.price:,.2f}  |  Qty: {trade.qty:.6f}\n")
                    f.write(f"     Fees: ${trade.fees:.4f}  |  PnL: ${trade.realized_pnl:+,.2f}\n")
                    f.write("\n")
            else:
                f.write("  No trades executed during this session.\n")
            f.write("\n")
            
            # Open Position (if any)
            f.write("FINAL POSITION STATE\n")
            f.write("-" * 40 + "\n")
            if self.account.position:
                pos = self.account.position
                pnl = pos.calculate_pnl(final_price)
                f.write(f"  Side:              {pos.side.value.upper()}\n")
                f.write(f"  Entry Price:       ${pos.entry_price:,.2f}\n")
                f.write(f"  Current Price:     ${final_price:,.2f}\n")
                f.write(f"  Unrealized PnL:    ${pnl:+,.2f}\n")
                f.write(f"  Liquidation:       ${pos.liquidation_price:,.2f}\n")
            else:
                f.write("  No open position at session end.\n")
            f.write("\n")
            
            # Session Events
            if self.session_log:
                f.write("SESSION EVENTS\n")
                f.write("-" * 40 + "\n")
                for event in self.session_log:
                    f.write(f"  {event}\n")
                f.write("\n")
            
            # Notes
            f.write("NOTES\n")
            f.write("-" * 40 + "\n")
            f.write("  - Close threshold: 0.15% (prevents oscillation)\n")
            f.write("  - All trades logged to: futures_trades.csv\n")
            f.write("  - This is PAPER TRADING - no real money\n")
            f.write("\n")
            f.write("=" * 70 + "\n")
        
        print(f"\nDetailed session log written to: {log_filename}")


class BacktestBot:
    """Backtest the strategy on historical data."""
    
    def __init__(self, backtest_date: datetime):
        exchange_class = getattr(ccxt, EXCHANGE)
        self.exchange = exchange_class({'enableRateLimit': True})
        
        self.backtest_date = backtest_date
        self.account = PaperAccount(STARTING_CAPITAL)
        self.kill_switch = KillSwitch(self.account)
        self.signal_generator = SignalGenerator(strategy=STRATEGY)
        self.executor = OrderExecutor()
        self.logger = TradeLogger(f"backtest_{backtest_date.strftime('%Y%m%d')}.csv")
    
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
    
    def run(self):
        """Run backtest simulation."""
        print("\n" + "📊" * 20)
        print("BACKTEST MODE")
        print(f"Date: {self.backtest_date.strftime('%Y-%m-%d')}")
        print(f"Symbol: {SYMBOL}")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print(f"Strategy: {STRATEGY.upper().replace('_', ' ')} (BB{BB_PERIOD}, {BB_STD}σ)")
        print("📊" * 20 + "\n")
        
        days_ago = (datetime.now() - self.backtest_date).days
        if days_ago > 14:
            print(f"⚠️  WARNING: Date is {days_ago} days ago. Kraken only keeps ~2 weeks of 15-min data.")
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
                print(f"[{current_time}] 🛑 KILL SWITCH: {kill_status.reason}")
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
                pos_str = f"📈 {self.account.position.qty:.6f}" if self.account.position else "No pos"
                
                if current_price < bb_lower:
                    status = "⬇️ BELOW LOWER"
                elif current_price > bb_upper:
                    status = "⬆️ ABOVE UPPER"
                else:
                    status = "➡️ IN RANGE"
                
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


class StrategyComparer:
    """Compare all strategies over multiple days."""
    
    STRATEGIES = ["mean_reversion", "trend_following", "voting"]
    
    CSV_FILES_DAILY = {
        'BTC/USD': 'historical_data/btc_usd_daily.csv',
        'ETH/USD': 'historical_data/eth_usd_daily.csv',
    }
    
    CSV_FILES_HOURLY = {
        'BTC/USD': 'historical_data/btc_usd_hourly.csv',
        'ETH/USD': 'historical_data/eth_usd_hourly.csv',
    }
    
    def __init__(self, days: int = None, start_date: datetime = None, end_date: datetime = None, timeframe: str = 'daily'):
        self.days = days
        self.start_date = start_date
        self.end_date = end_date
        self.timeframe = timeframe  # 'daily' or 'hourly'
        exchange_class = getattr(ccxt, EXCHANGE)
        self.exchange = exchange_class({'enableRateLimit': True})
    
    def load_from_csv(self) -> Optional[pd.DataFrame]:
        """Try to load historical data from CSV file."""
        # Select correct CSV based on timeframe
        if self.timeframe == 'hourly':
            csv_files = self.CSV_FILES_HOURLY
        else:
            csv_files = self.CSV_FILES_DAILY
            
        csv_path = csv_files.get(SYMBOL)
        
        if not csv_path or not os.path.exists(csv_path):
            return None
        
        try:
            print(f"📂 Loading {self.timeframe} data from {csv_path}...")
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
        
        df = self.load_from_csv()
        if df is not None and len(df) > 0:
            return df
        
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
        
        # Use appropriate signal generator based on timeframe
        if self.timeframe == 'hourly':
            signal_gen = HourlySignalGenerator(strategy=strategy_name)
            cooldown_mins = HOURLY_COOLDOWN_MINUTES
        else:
            signal_gen = SignalGenerator(strategy=strategy_name)
            cooldown_mins = COOLDOWN_MINUTES
        
        executor = OrderExecutor()
        
        trades_count = 0
        winning_trades = 0
        losing_trades = 0
        trade_log = []
        
        for i in range(50, len(df)):
            current_candle = df.iloc[i]
            current_time = current_candle['timestamp']
            
            if current_time < start_date or current_time > end_date:
                continue
            
            window_df = df.iloc[:i+1].copy()
            current_price = current_candle['close']
            
            signal, reason = signal_gen.generate_signal(window_df, current_price, account.position is not None)
            
            sl_tp_signal = check_stop_loss_take_profit(account, current_price)
            if sl_tp_signal:
                signal = sl_tp_signal
                reason = "SL/TP triggered"
            
            if signal != Signal.NONE:
                # Check cooldown (respect it in backtesting too!)
                if account.last_trade_time:
                    time_since_last = (current_time - account.last_trade_time).total_seconds() / 60
                    if time_since_last < cooldown_mins and not sl_tp_signal:
                        continue  # Skip this trade, still in cooldown
                
                trade = executor.execute(account, signal, SYMBOL, current_price)
                if trade:
                    trade.timestamp = current_time
                    account.last_trade_time = current_time
                    trades_count += 1
                    
                    if trade.realized_pnl > 0:
                        winning_trades += 1
                        result = "✅ WIN"
                    elif trade.realized_pnl < 0:
                        losing_trades += 1
                        result = "❌ LOSS"
                    else:
                        result = "➖ FLAT"
                    
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
            'trade_log': trade_log
        }
    
    def run(self):
        """Run comparison of all strategies."""
        # Determine period description
        if self.start_date and self.end_date:
            period_str = f"{self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}"
        else:
            period_str = f"Last {self.days} days"
        
        print("\n" + "🔬" * 20)
        print("STRATEGY COMPARISON MODE")
        print(f"Testing: {', '.join(self.STRATEGIES)}")
        print(f"Period: {period_str}")
        print(f"Timeframe: {self.timeframe.upper()} candles")
        print(f"Symbol: {SYMBOL}")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print("🔬" * 20 + "\n")
        
        df = self.fetch_multi_day_data()
        if df is None or len(df) == 0:
            print("[ERROR] No data available")
            return
        
        print(f"Loaded {len(df)} candles from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
        
        # Determine date range for backtesting
        if self.start_date and self.end_date:
            start_date = self.start_date
            end_date = self.end_date
        else:
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
        
        results.sort(key=lambda x: x['return_pct'], reverse=True)
        
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
        
        best = results[0]
        
        print("\n" + "=" * 60)
        print("🏆 WINNER: " + best['strategy'].upper().replace('_', ' '))
        print("=" * 60)
        print(f"Return: {best['return_pct']:+.2f}%")
        print(f"Final Equity: ${best['final_equity']:.2f}")
        print(f"Total Trades: {best['trades']}")
        print(f"Win Rate: {best['win_rate']:.1f}%")
        
        # Print trade logs
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
        
        for r in results[1:]:
            if r['trade_log'] and len(r['trade_log']) > 0:
                print("\n" + "-" * 70)
                print(f"📋 TRADE LOG ({r['strategy'].upper()}): {len(r['trade_log'])} trades")
                print("-" * 70)
                print(f"{'Date/Time':<20} {'Side':<5} {'Price':>12} {'PnL':>10} {'Result':<8} {'Equity':>10}")
                print("-" * 70)
                
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
        
        # Analysis
        print("\n" + "=" * 60)
        print("📈 ANALYSIS & RECOMMENDATIONS")
        print("=" * 60)
        
        if best['return_pct'] > 0:
            print(f"\n✅ {best['strategy'].upper()} made money! Key insights:")
        else:
            print(f"\n⚠️ All strategies lost money. This indicates:")
            print("   - Market may be trending strongly (bad for mean reversion)")
            print("   - Consider wider stop losses or smaller position sizes")
            print("   - May need different timeframe (hourly instead of 15-min)")
        
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
        
        print("\n" + "-" * 60)
        print("💡 RECOMMENDED SETTINGS FOR LIVE TRADING:")
        print("-" * 60)
        
        if best['return_pct'] > 0:
            # Calculate number of days for expected daily return
            if self.start_date and self.end_date:
                num_days = (self.end_date - self.start_date).days or 1
            else:
                num_days = self.days or 1
            print(f"   Strategy: {best['strategy']}")
            print(f"   Expected daily return: ~{best['return_pct']/num_days:.2f}%")
        else:
            print("   ⚠️ Consider waiting for better market conditions")
            print("   OR use trend_following in trending markets")
            print("   OR increase BB_STD to 1.5+ for mean_reversion")
        
        print("\n" + "=" * 60)


class FuturesStrategyComparer:
    """Compare all strategies for FUTURES trading (longs + shorts)."""
    
    STRATEGIES = ["mean_reversion", "trend_following", "voting"]
    
    CSV_FILES_DAILY = {
        'BTC/USD': 'historical_data/btc_usd_daily.csv',
        'ETH/USD': 'historical_data/eth_usd_daily.csv',
    }
    
    CSV_FILES_HOURLY = {
        'BTC/USD': 'historical_data/btc_usd_hourly.csv',
        'ETH/USD': 'historical_data/eth_usd_hourly.csv',
    }
    
    def __init__(self, days: int = None, start_date: datetime = None, 
                 end_date: datetime = None, timeframe: str = 'daily', leverage: int = LEVERAGE):
        self.days = days
        self.start_date = start_date
        self.end_date = end_date
        self.timeframe = timeframe
        self.leverage = leverage
    
    def load_from_csv(self) -> Optional[pd.DataFrame]:
        """Try to load historical data from CSV file."""
        if self.timeframe == 'hourly':
            csv_files = self.CSV_FILES_HOURLY
        else:
            csv_files = self.CSV_FILES_DAILY
            
        csv_path = csv_files.get(SYMBOL)
        
        if not csv_path or not os.path.exists(csv_path):
            return None
        
        try:
            print(f"📂 Loading {self.timeframe} data from {csv_path}...")
            df = pd.read_csv(csv_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            print(f"   ✅ Loaded {len(df)} candles from CSV")
            return df
        except Exception as e:
            print(f"   ⚠️ Error loading CSV: {e}")
            return None
    
    def run_strategy_backtest(self, df: pd.DataFrame, strategy_name: str,
                               start_date: datetime, end_date: datetime) -> dict:
        """Run a single strategy with futures (longs + shorts)."""
        account = FuturesAccount(STARTING_CAPITAL, leverage=self.leverage)
        signal_gen = FuturesSignalGenerator(strategy=strategy_name)
        executor = FuturesOrderExecutor()
        
        trades_count = 0
        winning_trades = 0
        losing_trades = 0
        long_trades = 0
        short_trades = 0
        liquidations = 0
        trade_log = []
        
        cooldown_mins = COOLDOWN_MINUTES
        
        for i in range(75, len(df)):  # Need more warmup for futures
            current_candle = df.iloc[i]
            current_time = current_candle['timestamp']
            
            if current_time < start_date or current_time > end_date:
                continue
            
            window_df = df.iloc[:i+1].copy()
            current_price = current_candle['close']
            
            # Check liquidation first
            liq_signal = check_futures_liquidation(account, current_price)
            if liq_signal:
                trade = executor.execute(account, liq_signal, SYMBOL, current_price)
                if trade:
                    trade.timestamp = current_time
                    trade.is_liquidation = True
                    liquidations += 1
                    losing_trades += 1
                    trades_count += 1
                    trade_log.append({
                        'time': current_time,
                        'side': '💀 LIQUIDATED',
                        'price': trade.price,
                        'pnl': trade.realized_pnl,
                        'result': '💀 LIQ',
                        'equity': account.get_equity(current_price)
                    })
                continue
            
            # Get current position side
            if account.position is None:
                position_side = 'none'
            else:
                position_side = account.position.side.value
            
            # Generate signal
            signal, reason = signal_gen.generate_signal(window_df, current_price, position_side)
            
            # Check stop loss / take profit
            sl_tp_signal = check_stop_loss_take_profit(account, current_price)
            if sl_tp_signal:
                signal = sl_tp_signal
                reason = "SL/TP triggered"
            
            if signal != Signal.NONE:
                # Check cooldown
                if account.last_trade_time:
                    time_since_last = (current_time - account.last_trade_time).total_seconds() / 60
                    if time_since_last < cooldown_mins and not sl_tp_signal:
                        continue
                
                trade = executor.execute(account, signal, SYMBOL, current_price)
                if trade:
                    trade.timestamp = current_time
                    account.last_trade_time = current_time
                    trades_count += 1
                    
                    if signal in [Signal.LONG, Signal.BUY]:
                        long_trades += 1
                    elif signal in [Signal.SHORT]:
                        short_trades += 1
                    
                    if trade.realized_pnl > 0:
                        winning_trades += 1
                        result = "✅ WIN"
                    elif trade.realized_pnl < 0:
                        losing_trades += 1
                        result = "❌ LOSS"
                    else:
                        result = "➖ FLAT"
                    
                    trade_log.append({
                        'time': current_time,
                        'side': trade.side.upper(),
                        'price': trade.price,
                        'pnl': trade.realized_pnl,
                        'result': result,
                        'equity': account.get_equity(current_price)
                    })
        
        # Force close any open position at end of backtest
        # Use the last price from the backtest period, not the entire CSV
        if account.position is not None:
            # Find the last candle in the test range
            test_df = df[df['timestamp'] <= end_date]
            if len(test_df) > 0:
                last_backtest_price = test_df['close'].iloc[-1]
            else:
                last_backtest_price = df['close'].iloc[-1]
            
            # Close the position
            close_signal = Signal.CLOSE_LONG if account.position.side == PositionSide.LONG else Signal.CLOSE_SHORT
            trade = executor.execute(account, close_signal, SYMBOL, last_backtest_price)
            if trade:
                trades_count += 1
                if trade.realized_pnl > 0:
                    winning_trades += 1
                elif trade.realized_pnl < 0:
                    losing_trades += 1
                trade_log.append({
                    'time': end_date,
                    'side': f"[AUTO-CLOSE] {trade.side.upper()}",
                    'price': trade.price,
                    'pnl': trade.realized_pnl,
                    'result': '📍 END',
                    'equity': account.wallet_balance
                })
        
        # Final equity = wallet balance (all positions closed)
        final_equity = account.wallet_balance
        total_return = (final_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100
        
        return {
            'strategy': strategy_name,
            'final_equity': final_equity,
            'return_pct': total_return,
            'realized_pnl': account.realized_pnl,
            'trades': trades_count,
            'winning': winning_trades,
            'losing': losing_trades,
            'long_trades': long_trades,
            'short_trades': short_trades,
            'liquidations': liquidations,
            'win_rate': (winning_trades / trades_count * 100) if trades_count > 0 else 0,
            'trade_log': trade_log
        }
    
    def run(self):
        """Run comparison of all strategies for futures."""
        if self.start_date and self.end_date:
            period_str = f"{self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}"
        else:
            period_str = f"Last {self.days} days"
        
        print("\n" + "🔮" * 20)
        print("FUTURES STRATEGY COMPARISON")
        print(f"Testing: {', '.join(self.STRATEGIES)}")
        print(f"Period: {period_str}")
        print(f"Timeframe: {self.timeframe.upper()} candles")
        print(f"Leverage: {self.leverage}x")
        print(f"Symbol: {SYMBOL}")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print("🔮" * 20 + "\n")
        
        df = self.load_from_csv()
        if df is None or len(df) == 0:
            print("[ERROR] No data available")
            return
        
        print(f"Loaded {len(df)} candles from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
        
        if self.start_date and self.end_date:
            start_date = self.start_date
            end_date = self.end_date
        else:
            end_date = df['timestamp'].iloc[-1]
            start_date = end_date - timedelta(days=self.days)
        
        print(f"\nTesting period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        print("\n" + "=" * 60)
        print("RUNNING FUTURES STRATEGIES...")
        print("=" * 60)
        
        results = []
        for strategy in self.STRATEGIES:
            print(f"\n📊 Testing {strategy.upper().replace('_', ' ')}...")
            result = self.run_strategy_backtest(df, strategy, start_date, end_date)
            results.append(result)
            print(f"   {result['long_trades'] + result['short_trades']} round trips (📈{result['long_trades']}L 📉{result['short_trades']}S) | "
                  f"Return: {result['return_pct']:+.2f}% | Win Rate: {result['win_rate']:.1f}%")
            if result['liquidations'] > 0:
                print(f"   ⚠️ Liquidations: {result['liquidations']}")
        
        results.sort(key=lambda x: x['return_pct'], reverse=True)
        
        print("\n\n" + "=" * 70)
        print("📊 FUTURES STRATEGY COMPARISON RESULTS")
        print("=" * 70)
        print(f"\n{'Strategy':<20} {'Return':>10} {'Trips':>6} {'Long':>5} {'Short':>6} {'Win%':>8} {'Final $':>12}")
        print("-" * 70)
        
        for r in results:
            trips = r['long_trades'] + r['short_trades']
            print(f"{r['strategy'].replace('_', ' ').title():<20} "
                  f"{r['return_pct']:>+9.2f}% "
                  f"{trips:>6} "
                  f"{r['long_trades']:>5} "
                  f"{r['short_trades']:>6} "
                  f"{r['win_rate']:>7.1f}% "
                  f"${r['final_equity']:>10.2f}")
        
        best = results[0]
        
        print("\n" + "=" * 70)
        print("🏆 WINNER: " + best['strategy'].upper().replace('_', ' '))
        print("=" * 70)
        print(f"Return: {best['return_pct']:+.2f}%")
        print(f"Final Equity: ${best['final_equity']:.2f}")
        trips = best['long_trades'] + best['short_trades']
        print(f"Round Trips: {trips} (📈{best['long_trades']} long, 📉{best['short_trades']} short)")
        print(f"Win Rate: {best['win_rate']:.1f}%")
        print(f"Leverage: {self.leverage}x")
        
        if best['liquidations'] > 0:
            print(f"⚠️ Liquidations: {best['liquidations']}")
        
        # Show trade log summary
        if best['trade_log']:
            print("\n" + "-" * 70)
            print(f"📋 TRADE LOG ({best['strategy'].upper()}):")
            print("-" * 70)
            for t in best['trade_log'][:15]:  # Show first 15
                print(f"  {t['time'].strftime('%Y-%m-%d %H:%M')} | {t['side']:<12} @ ${t['price']:>10,.2f} | "
                      f"PnL: ${t['pnl']:>+8.2f} | {t['result']}")
            if len(best['trade_log']) > 15:
                print(f"  ... ({len(best['trade_log']) - 15} more trades)")
        
        print("\n" + "=" * 70)

