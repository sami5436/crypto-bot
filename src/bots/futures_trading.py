"""
Futures paper trading bot with longs and shorts.
"""

import ccxt
import os
import pandas as pd
import random
import time
from datetime import datetime
from typing import Optional

from config import (
    EXCHANGE, SYMBOL, STARTING_CAPITAL, STRATEGY,
    RSI_PERIOD, UPDATE_INTERVAL_SECONDS, MAX_TRADES_PER_DAY,
    LEVERAGE
)
from src.core.models import Signal, KillSwitchStatus, PositionSide
from src.strategies.indicators import calculate_rsi, calculate_atr
from src.core.account import FuturesAccount
from src.strategies.strategies import FuturesSignalGenerator
from src.core.executor import (
    KillSwitch, FuturesOrderExecutor, TradeLogger,
    check_stop_loss_take_profit, check_futures_liquidation
)
from src.bots.base import BaseBot


class FuturesPaperTradingBot(BaseBot):
    """Live futures paper trading bot with longs and shorts."""
    
    def __init__(self, leverage: int = LEVERAGE):
        super().__init__()
        self.leverage = leverage
        self.account = FuturesAccount(STARTING_CAPITAL, leverage=leverage)
        self.kill_switch = KillSwitch(self.account)
        self.signal_generator = FuturesSignalGenerator(strategy=STRATEGY)
        self.executor = FuturesOrderExecutor()
        self.logger = TradeLogger("logs/futures_trades.csv")
        
        # Session tracking for detailed log
        self.start_time = datetime.now()
        self.session_log = []
    
    def fetch_ohlcv(self) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data from exchange."""
        try:
            # Use daily candles for more stable signals
            ohlcv = self.exchange.fetch_ohlcv(SYMBOL, "1d", limit=100)
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
        print(f"    Funding Paid     ${self.account.total_funding_paid:+,.2f}")
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
        print("\n" + "=" * 60)
        print("STARTING FUTURES PAPER TRADING BOT")
        print(f"Mode: PAPER (Futures)")
        print(f"Symbol: {SYMBOL}")
        print(f"Leverage: {self.leverage}x")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print(f"Strategy: {STRATEGY.upper().replace('_', ' ')}")
        print(f"Timeframe: DAILY candles")
        print(f"Funding Rate: Simulated every 8 hours")
        print("=" * 60 + "\n")
        
        df = None
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
                        print("\nPOSITION LIQUIDATED!")
                
                # Process funding rate every 8 hours
                now = datetime.now()
                if self.account.position and (
                    self.account.last_funding_time is None or 
                    (now - self.account.last_funding_time).total_seconds() >= 8 * 3600
                ):
                    funding_rate = random.uniform(-0.0001, 0.0003)
                    funding_payment = self.account.process_funding(current_price, funding_rate, now)
                    if funding_payment:
                        self.session_log.append(
                            f"{now}: FUNDING - Rate: {funding_rate:.4%}, Payment: ${funding_payment.payment:+.4f}"
                        )
                
                # Get current position side
                if self.account.position is None:
                    position_side = 'none'
                else:
                    position_side = self.account.position.side.value
                
                # Generate signal
                signal, signal_reason = self.signal_generator.generate_signal(
                    df, current_price, position_side
                )
                
                # Profit/loss threshold - don't close on tiny moves
                MIN_CLOSE_THRESHOLD = 0.0015
                if signal in [Signal.CLOSE_LONG, Signal.CLOSE_SHORT] and self.account.position:
                    pos = self.account.position
                    move_pct = abs(current_price - pos.entry_price) / pos.entry_price
                    if move_pct < MIN_CLOSE_THRESHOLD:
                        signal = Signal.NONE
                        signal_reason = f"HOLDING (move {move_pct:.3%} < {MIN_CLOSE_THRESHOLD:.2%} threshold)"
                
                # Check stop loss / take profit
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
                    print("\nBOT HALTED BY KILL SWITCH")
                    self.running = False
                    break
                
                time.sleep(60)
                
            except KeyboardInterrupt:
                print("\n\nShutting down gracefully...")
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
        
        self._write_session_log(final_price)
    
    def _write_session_log(self, final_price: float):
        """Write detailed session log to file."""
        log_filename = f"logs/session_log_{self.start_time.strftime('%Y%m%d_%H%M%S')}.txt"
        
        final_equity = self.account.get_equity(final_price)
        total_return = (final_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100
        session_duration = datetime.now() - self.start_time
        
        with open(log_filename, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("FUTURES PAPER TRADING SESSION LOG\n")
            f.write("=" * 70 + "\n\n")
            
            f.write("SESSION OVERVIEW\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Start Time:        {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  End Time:          {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  Duration:          {str(session_duration).split('.')[0]}\n")
            f.write(f"  Symbol:            {SYMBOL}\n")
            f.write(f"  Leverage:          {self.leverage}x\n")
            f.write(f"  Strategy:          {STRATEGY}\n")
            f.write("\n")
            
            f.write("ACCOUNT SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Starting Capital:  ${STARTING_CAPITAL:,.2f}\n")
            f.write(f"  Final Equity:      ${final_equity:,.2f}\n")
            f.write(f"  Total Return:      {total_return:+.2f}%\n")
            f.write(f"  Realized PnL:      ${self.account.realized_pnl:+,.2f}\n")
            f.write("\n")
            
            f.write("TRADE SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Total Trades:      {len(self.account.trades)}\n")
            
            if self.account.trades:
                winning = sum(1 for t in self.account.trades if t.realized_pnl > 0)
                losing = sum(1 for t in self.account.trades if t.realized_pnl < 0)
                flat = len(self.account.trades) - winning - losing
                win_rate = winning / len(self.account.trades) * 100
                f.write(f"  Winning Trades:    {winning}\n")
                f.write(f"  Losing Trades:     {losing}\n")
                f.write(f"  Flat Trades:       {flat}\n")
                f.write(f"  Win Rate:          {win_rate:.1f}%\n")
            f.write("\n")
            
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
            
            if self.session_log:
                f.write("SESSION EVENTS\n")
                f.write("-" * 40 + "\n")
                for event in self.session_log:
                    f.write(f"  {event}\n")
                f.write("\n")
            
            f.write("NOTES\n")
            f.write("-" * 40 + "\n")
            f.write("  - Close threshold: 0.15% (prevents oscillation)\n")
            f.write("  - All trades logged to: futures_trades.csv\n")
            f.write("  - This is PAPER TRADING - no real money\n")
            f.write("\n")
            f.write("=" * 70 + "\n")
        
        print(f"\nDetailed session log written to: {log_filename}")
