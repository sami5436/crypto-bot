"""
Technical indicator calculations.
"""

import pandas as pd
import numpy as np
from typing import Tuple


def calculate_bollinger_bands(closes: pd.Series, period: int = 20, std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Bollinger Bands.
    
    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    sma = closes.rolling(window=period).mean()
    std_dev = closes.rolling(window=period).std()
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    return upper, sma, lower


def calculate_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
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
    """Calculate MACD (line, signal, histogram).
    
    Returns:
        Tuple of (macd_line, signal_line, histogram)
    """
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_volume_sma(volumes: pd.Series, period: int = 20) -> pd.Series:
    """Calculate Volume Simple Moving Average."""
    return volumes.rolling(window=period).mean()
