"""
Base bot class with shared functionality.
All trading bots inherit from this class.
"""

import ccxt
import pandas as pd
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from config import EXCHANGE, SYMBOL


class BaseBot(ABC):
    """Abstract base class for all trading bots."""
    
    def __init__(self):
        """Initialize exchange connection."""
        exchange_class = getattr(ccxt, EXCHANGE)
        self.exchange = exchange_class({'enableRateLimit': True})
        self.running = True
    
    def fetch_ohlcv(self, symbol: str = SYMBOL, timeframe: str = "1d", 
                    limit: int = 100) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data from exchange.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USD')
            timeframe: Candle timeframe ('1m', '1h', '1d')
            limit: Number of candles to fetch
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
            
        except Exception as e:
            print(f"[ERROR] API error: {e}")
            return None
    
    @abstractmethod
    def print_status(self, *args, **kwargs):
        """Print current bot status. Must be implemented by child classes."""
        pass
    
    @abstractmethod
    def run(self):
        """Main bot loop. Must be implemented by child classes."""
        pass
    
    def stop(self):
        """Stop the bot gracefully."""
        self.running = False
