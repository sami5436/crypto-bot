"""
Bots module - exported classes for trading bots.
"""

from src.bots.paper_trading import PaperTradingBot
from src.bots.futures_trading import FuturesPaperTradingBot
from src.bots.backtest import BacktestBot
from src.bots.strategy_comparer import StrategyComparer, FuturesStrategyComparer

__all__ = [
    'PaperTradingBot',
    'FuturesPaperTradingBot', 
    'BacktestBot',
    'StrategyComparer',
    'FuturesStrategyComparer',
]
