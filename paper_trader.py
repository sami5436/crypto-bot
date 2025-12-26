#!/usr/bin/env python3
"""
Crypto Paper Trading Bot - Main Entry Point
============================================
A production-ready paper trading bot using ccxt with comprehensive
fee simulation, risk management, and kill switch safety features.

Run this file to start the trading bot.
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple, Union

from bots import PaperTradingBot, BacktestBot, StrategyComparer, FuturesStrategyComparer
from config import LEVERAGE


def get_user_mode() -> Tuple[str, any]:
    """Prompt user for trading mode."""
    print("\n" + "=" * 60)
    print("🤖 CRYPTO PAPER TRADING BOT")
    print("=" * 60)
    print("\nChoose mode:")
    print("  1. Live trading (real-time paper trading)")
    print("  2. Backtest (simulate on historical date)")
    print("  3. Compare strategies (last N days, daily candles)")
    print("  4. Compare strategies (date range, daily candles)")
    print("  5. Compare strategies (date range, 1-hour candles)")
    print("  6. 🔮 FUTURES: Compare with longs + shorts (date range)")
    print()
    
    while True:
        choice = input("Enter choice (1-6): ").strip()
        if choice in ['1', '2', '3', '4', '5', '6']:
            break
        print("Invalid choice. Please enter 1-6.")
    
    if choice == '1':
        return 'live', None
    
    if choice == '3':
        print("\nHow many days to backtest?")
        print("  (Max: 730 days with current CSV data)")
        while True:
            days_input = input("Days [365]: ").strip()
            if days_input == '':
                return 'compare', {'days': 365, 'timeframe': 'daily'}
            try:
                days = int(days_input)
                if days < 1:
                    print("Please enter a positive number.")
                    continue
                if days > 730:
                    print("Warning: You only have ~730 days of data. Using 730.")
                    days = 730
                return 'compare', {'days': days, 'timeframe': 'daily'}
            except ValueError:
                print("Please enter a valid number.")
    
    if choice in ['4', '5']:
        timeframe = 'hourly' if choice == '5' else 'daily'
        
        print(f"\nEnter date range for {timeframe} candles (format: YYYY-MM-DD)")
        print("  Data available: ~2024-01-01 to today")
        
        while True:
            start_input = input("Start date: ").strip()
            try:
                start_date = datetime.strptime(start_input, '%Y-%m-%d')
                break
            except ValueError:
                print("Invalid format. Use YYYY-MM-DD (e.g., 2024-06-01)")
        
        while True:
            end_input = input("End date [today]: ").strip()
            if end_input == '':
                end_date = datetime.now()
                break
            try:
                end_date = datetime.strptime(end_input, '%Y-%m-%d')
                if end_date < start_date:
                    print("End date must be after start date.")
                    continue
                break
            except ValueError:
                print("Invalid format. Use YYYY-MM-DD (e.g., 2025-12-01)")
        
        return 'compare', {'start_date': start_date, 'end_date': end_date, 'timeframe': timeframe}
    
    if choice == '6':
        # FUTURES mode
        print("\n🔮 FUTURES MODE: Longs + Shorts with Leverage")
        print("=" * 50)
        
        # Get leverage
        print(f"\nLeverage (1-10, default: {LEVERAGE}x):")
        while True:
            lev_input = input(f"Leverage [{LEVERAGE}]: ").strip()
            if lev_input == '':
                leverage = LEVERAGE
                break
            try:
                leverage = int(lev_input)
                if leverage < 1 or leverage > 10:
                    print("Please enter a number between 1 and 10.")
                    continue
                break
            except ValueError:
                print("Please enter a valid number.")
        
        # Get timeframe
        print("\nTimeframe:")
        print("  1. Daily candles")
        print("  2. Hourly candles")
        tf_choice = input("Choice [1]: ").strip()
        timeframe = 'hourly' if tf_choice == '2' else 'daily'
        
        # Get date range
        print(f"\nEnter date range for {timeframe} candles (format: YYYY-MM-DD)")
        print("  Data available: ~2024-01-01 to today")
        
        while True:
            start_input = input("Start date: ").strip()
            try:
                start_date = datetime.strptime(start_input, '%Y-%m-%d')
                break
            except ValueError:
                print("Invalid format. Use YYYY-MM-DD (e.g., 2024-06-01)")
        
        while True:
            end_input = input("End date [today]: ").strip()
            if end_input == '':
                end_date = datetime.now()
                break
            try:
                end_date = datetime.strptime(end_input, '%Y-%m-%d')
                if end_date < start_date:
                    print("End date must be after start date.")
                    continue
                break
            except ValueError:
                print("Invalid format. Use YYYY-MM-DD (e.g., 2025-12-01)")
        
        return 'futures', {
            'start_date': start_date, 
            'end_date': end_date, 
            'timeframe': timeframe,
            'leverage': leverage
        }
    
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
            
            if backtest_date.date() > datetime.now().date():
                print("Error: Cannot backtest future dates!")
                continue
            
            min_date = datetime.now() - timedelta(days=365)
            if backtest_date < min_date:
                print(f"Warning: Date may be too old. Exchange might not have data before {min_date.strftime('%Y-%m-%d')}")
            
            return 'backtest', backtest_date
            
        except ValueError:
            print("Invalid date format. Please use YYYY-MM-DD (e.g., 2025-12-20)")


def main():
    """Main entry point."""
    mode, value = get_user_mode()
    
    if mode == 'live':
        bot = PaperTradingBot()
        bot.run()
    elif mode == 'compare':
        timeframe = value.get('timeframe', 'daily')
        if 'days' in value:
            comparer = StrategyComparer(days=value['days'], timeframe=timeframe)
        else:
            comparer = StrategyComparer(
                start_date=value['start_date'], 
                end_date=value['end_date'],
                timeframe=timeframe
            )
        comparer.run()
    elif mode == 'futures':
        comparer = FuturesStrategyComparer(
            start_date=value['start_date'],
            end_date=value['end_date'],
            timeframe=value['timeframe'],
            leverage=value['leverage']
        )
        comparer.run()
    else:
        bot = BacktestBot(value)
        bot.run()


if __name__ == "__main__":
    main()
