"""
Strategy comparison classes for backtesting multiple strategies.
"""

import os
import pandas as pd
import random
from datetime import datetime, timedelta
from typing import Optional

from config import (
    SYMBOL, STARTING_CAPITAL, STRATEGY,
    COOLDOWN_MINUTES, HOURLY_COOLDOWN_MINUTES, LEVERAGE
)
from src.core.models import Signal, PositionSide
from src.core.account import PaperAccount, FuturesAccount
from src.strategies.strategies import SignalGenerator, HourlySignalGenerator, FuturesSignalGenerator
from src.core.executor import (
    OrderExecutor, FuturesOrderExecutor, TradeLogger,
    check_stop_loss_take_profit, check_futures_liquidation
)


class StrategyComparer:
    """Compare all strategies over multiple days (spot trading)."""
    
    STRATEGIES = ["mean_reversion", "trend_following", "voting"]
    
    CSV_FILES_DAILY = {
        'BTC/USD': 'data/historical/btc_usd_daily.csv',
        'ETH/USD': 'data/historical/eth_usd_daily.csv',
    }
    
    CSV_FILES_HOURLY = {
        'BTC/USD': 'data/historical/btc_usd_hourly.csv',
        'ETH/USD': 'data/historical/eth_usd_hourly.csv',
    }
    
    def __init__(self, days: int = None, start_date: datetime = None, 
                 end_date: datetime = None, timeframe: str = 'daily'):
        self.days = days
        self.start_date = start_date
        self.end_date = end_date
        self.timeframe = timeframe
    
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
            print(f"Loading {self.timeframe} data from {csv_path}...")
            df = pd.read_csv(csv_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            print(f"   Loaded {len(df)} candles from CSV")
            return df
        except Exception as e:
            print(f"   Error loading CSV: {e}")
            return None
    
    def run_strategy_backtest(self, df: pd.DataFrame, strategy_name: str, 
                               start_date: datetime, end_date: datetime, verbose: bool = False) -> dict:
        """Run a single strategy over the date range."""
        account = PaperAccount(STARTING_CAPITAL)
        
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
                if account.last_trade_time:
                    time_since_last = (current_time - account.last_trade_time).total_seconds() / 60
                    if time_since_last < cooldown_mins and not sl_tp_signal:
                        continue
                
                trade = executor.execute(account, signal, SYMBOL, current_price)
                if trade:
                    trade.timestamp = current_time
                    account.last_trade_time = current_time
                    trades_count += 1
                    
                    if trade.realized_pnl > 0:
                        winning_trades += 1
                        result = "WIN"
                    elif trade.realized_pnl < 0:
                        losing_trades += 1
                        result = "LOSS"
                    else:
                        result = "FLAT"
                    
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
        if self.start_date and self.end_date:
            period_str = f"{self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}"
        else:
            period_str = f"Last {self.days} days"
        
        print("\n" + "=" * 60)
        print("STRATEGY COMPARISON MODE")
        print(f"Testing: {', '.join(self.STRATEGIES)}")
        print(f"Period: {period_str}")
        print(f"Timeframe: {self.timeframe.upper()} candles")
        print(f"Symbol: {SYMBOL}")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print("=" * 60 + "\n")
        
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
        print("RUNNING STRATEGIES...")
        print("=" * 60)
        
        results = []
        for strategy in self.STRATEGIES:
            print(f"\nTesting {strategy.upper().replace('_', ' ')}...")
            result = self.run_strategy_backtest(df, strategy, start_date, end_date)
            results.append(result)
            print(f"   Trades: {result['trades']} | Return: {result['return_pct']:+.2f}% | "
                  f"Win Rate: {result['win_rate']:.1f}%")
        
        results.sort(key=lambda x: x['return_pct'], reverse=True)
        
        print("\n\n" + "=" * 60)
        print("STRATEGY COMPARISON RESULTS")
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
        print("WINNER: " + best['strategy'].upper().replace('_', ' '))
        print("=" * 60)
        print(f"Return: {best['return_pct']:+.2f}%")
        print(f"Final Equity: ${best['final_equity']:.2f}")
        print(f"Total Trades: {best['trades']}")
        print(f"Win Rate: {best['win_rate']:.1f}%")
        
        if best['trade_log']:
            print("\n" + "-" * 70)
            print(f"TRADE LOG ({best['strategy'].upper()}):")
            print("-" * 70)
            for t in best['trade_log'][:15]:
                print(f"  {t['time'].strftime('%Y-%m-%d %H:%M')} | {t['side'].upper():<5} @ ${t['price']:>10,.2f} | "
                      f"PnL: ${t['pnl']:>+8.2f} | {t['result']}")
            if len(best['trade_log']) > 15:
                print(f"  ... ({len(best['trade_log']) - 15} more trades)")
        
        print("\n" + "=" * 60)


class FuturesStrategyComparer:
    """Compare all strategies for FUTURES trading (longs + shorts)."""
    
    STRATEGIES = ["mean_reversion", "trend_following", "voting"]
    
    CSV_FILES_DAILY = {
        'BTC/USD': 'data/historical/btc_usd_daily.csv',
        'ETH/USD': 'data/historical/eth_usd_daily.csv',
    }
    
    CSV_FILES_HOURLY = {
        'BTC/USD': 'data/historical/btc_usd_hourly.csv',
        'ETH/USD': 'data/historical/eth_usd_hourly.csv',
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
            print(f"Loading {self.timeframe} data from {csv_path}...")
            df = pd.read_csv(csv_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            print(f"   Loaded {len(df)} candles from CSV")
            return df
        except Exception as e:
            print(f"   Error loading CSV: {e}")
            return None
    
    def run_strategy_backtest(self, df: pd.DataFrame, strategy_name: str,
                               start_date: datetime, end_date: datetime) -> dict:
        """Run a single strategy with futures (longs + shorts)."""
        account = FuturesAccount(STARTING_CAPITAL, leverage=self.leverage)
        signal_gen = FuturesSignalGenerator(strategy=strategy_name)
        executor = FuturesOrderExecutor()
        logger = TradeLogger("logs/current_futures_backtest.csv")
        
        trades_count = 0
        winning_trades = 0
        losing_trades = 0
        long_trades = 0
        short_trades = 0
        liquidations = 0
        trade_log = []
        
        cooldown_mins = COOLDOWN_MINUTES
        
        for i in range(75, len(df)):
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
                    logger.log_trade(trade)
                    trade_log.append({
                        'time': current_time,
                        'side': 'LIQUIDATED',
                        'price': trade.price,
                        'pnl': trade.realized_pnl,
                        'result': 'LIQ',
                        'equity': account.get_equity(current_price)
                    })
                continue
            
            # Process funding rate every 8 hours
            if account.position and (
                account.last_funding_time is None or
                (current_time - account.last_funding_time).total_seconds() >= 8 * 3600
            ):
                funding_rate = random.uniform(-0.0001, 0.0003)
                account.process_funding(current_price, funding_rate, current_time)
            
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
                        result = "WIN"
                    elif trade.realized_pnl < 0:
                        losing_trades += 1
                        result = "LOSS"
                    else:
                        result = "FLAT"
                    
                    logger.log_trade(trade)
                    trade_log.append({
                        'time': current_time,
                        'side': trade.side.upper(),
                        'price': trade.price,
                        'pnl': trade.realized_pnl,
                        'result': result,
                        'equity': account.get_equity(current_price)
                    })
        
        # Force close any open position at end of backtest
        if account.position is not None:
            test_df = df[df['timestamp'] <= end_date]
            if len(test_df) > 0:
                last_backtest_price = test_df['close'].iloc[-1]
            else:
                last_backtest_price = df['close'].iloc[-1]
            
            close_signal = Signal.CLOSE_LONG if account.position.side == PositionSide.LONG else Signal.CLOSE_SHORT
            trade = executor.execute(account, close_signal, SYMBOL, last_backtest_price)
            if trade:
                trades_count += 1
                if trade.realized_pnl > 0:
                    winning_trades += 1
                elif trade.realized_pnl < 0:
                    losing_trades += 1
                logger.log_trade(trade)
                trade_log.append({
                    'time': end_date,
                    'side': f"[AUTO-CLOSE] {trade.side.upper()}",
                    'price': trade.price,
                    'pnl': trade.realized_pnl,
                    'result': 'END',
                    'equity': account.wallet_balance
                })
        
        final_equity = account.wallet_balance
        total_return = (final_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100
        
        return {
            'strategy': strategy_name,
            'final_equity': final_equity,
            'return_pct': total_return,
            'realized_pnl': account.realized_pnl,
            'funding_paid': account.total_funding_paid,
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
        
        print("\n")
        print("FUTURES STRATEGY COMPARISON")
        print(f"Testing: {', '.join(self.STRATEGIES)}")
        print(f"Period: {period_str}")
        print(f"Timeframe: {self.timeframe.upper()} candles")
        print(f"Leverage: {self.leverage}x")
        print(f"Symbol: {SYMBOL}")
        print(f"Starting Capital: ${STARTING_CAPITAL}")
        print("\n")
        
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
            print(f"\nTesting {strategy.upper().replace('_', ' ')}...")
            result = self.run_strategy_backtest(df, strategy, start_date, end_date)
            results.append(result)
            print(f"   {result['long_trades'] + result['short_trades']} round trips ({result['long_trades']}L {result['short_trades']}S) | "
                  f"Return: {result['return_pct']:+.2f}% | Win Rate: {result['win_rate']:.1f}%")
            if result['liquidations'] > 0:
                print(f"   Liquidations: {result['liquidations']}")
        
        results.sort(key=lambda x: x['return_pct'], reverse=True)
        
        print("\n\n" + "=" * 70)
        print("FUTURES STRATEGY COMPARISON RESULTS")
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
        print("WINNER: " + best['strategy'].upper().replace('_', ' '))
        print("=" * 70)
        print(f"Return: {best['return_pct']:+.2f}%")
        print(f"Final Equity: ${best['final_equity']:.2f}")
        trips = best['long_trades'] + best['short_trades']
        print(f"Round Trips: {trips} ({best['long_trades']} long, {best['short_trades']} short)")
        print(f"Win Rate: {best['win_rate']:.1f}%")
        print(f"Leverage: {self.leverage}x")
        print(f"Funding Paid: ${best['funding_paid']:+.2f}")
        
        if best['liquidations'] > 0:
            print(f"Liquidations: {best['liquidations']}")
        
        if best['trade_log']:
            print("\n" + "-" * 70)
            print(f"TRADE LOG ({best['strategy'].upper()}):")
            print("-" * 70)
            for t in best['trade_log'][:15]:
                print(f"  {t['time'].strftime('%Y-%m-%d %H:%M')} | {t['side']:<12} @ ${t['price']:>10,.2f} | "
                      f"PnL: ${t['pnl']:>+8.2f} | {t['result']}")
            if len(best['trade_log']) > 15:
                print(f"  ... ({len(best['trade_log']) - 15} more trades)")
        
        print("\n" + "=" * 70)
