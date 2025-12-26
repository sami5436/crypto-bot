"""
Trading strategies and signal generation.
Includes both daily and hourly optimized signal generators.
"""

import pandas as pd
from typing import Tuple

from config import (
    BB_PERIOD, BB_STD, RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT,
    MAKER_FEE, SIMULATED_SPREAD, SIMULATED_SLIPPAGE, ATR_VOLATILITY_THRESHOLD,
    HOURLY_BB_PERIOD, HOURLY_BB_STD, HOURLY_RSI_PERIOD, 
    HOURLY_RSI_OVERSOLD, HOURLY_RSI_OVERBOUGHT, HOURLY_ATR_VOLATILITY_THRESHOLD
)
from models import Signal
from indicators import (
    calculate_bollinger_bands, calculate_rsi, calculate_ema,
    calculate_macd, calculate_volume_sma, calculate_atr
)


class SignalGenerator:
    """Generate trading signals using multiple strategies (for DAILY candles)."""
    
    def __init__(self, strategy: str = "voting"):
        self.strategy = strategy
        self.last_signal = Signal.NONE
        # Use daily config
        self.bb_period = BB_PERIOD
        self.bb_std = BB_STD
        self.rsi_period = RSI_PERIOD
        self.rsi_oversold = RSI_OVERSOLD
        self.rsi_overbought = RSI_OVERBOUGHT
        self.atr_threshold = ATR_VOLATILITY_THRESHOLD
    
    def calculate_expected_friction(self, price: float) -> float:
        """Calculate total expected friction for a round trip."""
        total_friction = (
            (MAKER_FEE * 2) +
            (SIMULATED_SPREAD * 2) +
            (SIMULATED_SLIPPAGE * 2)
        )
        return price * total_friction
    
    def _check_volatility_filter(self, df: pd.DataFrame, current_price: float) -> Tuple[bool, float]:
        """Check if volatility is too high for trading."""
        atr = calculate_atr(df['high'], df['low'], df['close'])
        current_atr = atr.iloc[-1]
        volatility_pct = current_atr / current_price
        is_too_volatile = volatility_pct > self.atr_threshold
        return is_too_volatile, volatility_pct
    
    def _mean_reversion_signal(self, df: pd.DataFrame, current_price: float, 
                                has_position: bool) -> Tuple[Signal, str, dict]:
        """Strategy 1: Mean Reversion - buy dips when RSI oversold, sell at mean."""
        closes = df['close']
        upper, middle, lower = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        rsi = calculate_rsi(closes, self.rsi_period)
        ema_20 = calculate_ema(closes, 20)
        
        bb_lower = lower.iloc[-1]
        bb_middle = middle.iloc[-1]
        bb_upper = upper.iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_ema20 = ema_20.iloc[-1]
        
        strong_downtrend = current_price < current_ema20 * 0.97
        
        votes = {
            'bb_oversold': current_price < bb_lower,
            'rsi_oversold': current_rsi < self.rsi_oversold,
            'not_strong_downtrend': not strong_downtrend,
            'bb_overbought': current_price > bb_upper,
            'rsi_overbought': current_rsi > self.rsi_overbought,
        }
        
        if not has_position:
            if current_price < bb_lower and current_rsi < self.rsi_oversold and not strong_downtrend:
                return Signal.BUY, f"MEAN_REV BUY: BB oversold + RSI={current_rsi:.0f}", votes
        
        if has_position:
            if current_price >= bb_middle:
                return Signal.SELL, f"MEAN_REV SELL: Price ${current_price:.2f} >= BB_Mid ${bb_middle:.2f}", votes
        
        trend_str = "📉STRONG DOWN" if strong_downtrend else "OK"
        return Signal.NONE, f"MEAN_REV: Waiting (RSI: {current_rsi:.0f}, Trend: {trend_str})", votes
    
    def _trend_following_signal(self, df: pd.DataFrame, current_price: float,
                                 has_position: bool) -> Tuple[Signal, str, dict]:
        """Strategy 2: Trend Following - buy breakouts, ride the trend."""
        closes = df['close']
        
        ema_fast = calculate_ema(closes, 10)
        ema_slow = calculate_ema(closes, 30)
        macd_line, signal_line, histogram = calculate_macd(closes)
        upper, middle, lower = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        
        current_ema_fast = ema_fast.iloc[-1]
        current_ema_slow = ema_slow.iloc[-1]
        current_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]
        bb_upper = upper.iloc[-1]
        
        uptrend = current_ema_fast > current_ema_slow
        macd_bullish = current_hist > 0 and current_hist > prev_hist
        
        votes = {
            'ema_uptrend': uptrend,
            'macd_bullish': macd_bullish,
            'breakout_up': current_price > bb_upper,
            'ema_downtrend': not uptrend,
            'macd_bearish': current_hist < 0,
        }
        
        if not has_position:
            if uptrend and macd_bullish:
                return Signal.BUY, f"TREND BUY: EMA↑ + MACD↑ @ ${current_price:.2f}", votes
        
        if has_position:
            if not uptrend and current_hist < prev_hist:
                return Signal.SELL, f"TREND SELL: Trend reversal @ ${current_price:.2f}", votes
        
        return Signal.NONE, f"TREND: Waiting (EMA trend: {'UP' if uptrend else 'DOWN'})", votes
    
    def _voting_signal(self, df: pd.DataFrame, current_price: float,
                       has_position: bool) -> Tuple[Signal, str, dict]:
        """Strategy 3: Multi-Signal Voting - require multiple confirmations."""
        closes = df['close']
        volumes = df['volume']
        
        upper, middle, lower = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        rsi = calculate_rsi(closes, self.rsi_period)
        ema_20 = calculate_ema(closes, 20)
        ema_50 = calculate_ema(closes, 50)
        macd_line, signal_line, histogram = calculate_macd(closes)
        vol_sma = calculate_volume_sma(volumes, 20)
        
        bb_lower = lower.iloc[-1]
        bb_middle = middle.iloc[-1]
        bb_upper = upper.iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_ema50 = ema_50.iloc[-1]
        current_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]
        current_vol = volumes.iloc[-1]
        avg_vol = vol_sma.iloc[-1]
        
        # BUY votes
        buy_votes = {
            'bb_oversold': current_price < bb_lower,
            'rsi_oversold': current_rsi < 35,
            'macd_turning': current_hist > prev_hist,
            'above_ema50': current_price > current_ema50,
            'volume_spike': current_vol > avg_vol * 1.2,
        }
        
        # SELL votes
        sell_votes = {
            'bb_overbought': current_price > bb_upper,
            'rsi_overbought': current_rsi > 65,
            'macd_weakening': current_hist < prev_hist,
            'at_middle_band': current_price >= bb_middle,
        }
        
        buy_count = sum(buy_votes.values())
        sell_count = sum(sell_votes.values())
        
        all_votes = {**buy_votes, **sell_votes}
        
        if not has_position:
            if buy_count >= 3:
                signals_str = ", ".join([k for k, v in buy_votes.items() if v])
                return Signal.BUY, f"VOTING BUY ({buy_count}/5): {signals_str}", all_votes
        
        if has_position:
            if sell_count >= 2 or current_price >= bb_middle:
                signals_str = ", ".join([k for k, v in sell_votes.items() if v])
                return Signal.SELL, f"VOTING SELL ({sell_count}/4): {signals_str}", all_votes
        
        return Signal.NONE, f"VOTING: {buy_count}/5 buy votes, {sell_count}/4 sell votes", all_votes
    
    def generate_signal(self, df: pd.DataFrame, current_price: float, 
                        has_position: bool) -> Tuple[Signal, str]:
        """Generate trading signal based on selected strategy."""
        
        min_periods = max(self.bb_period, 50) + 5
        if len(df) < min_periods:
            return Signal.NONE, "Insufficient data"
        
        if self.strategy == "mean_reversion":
            signal, reason, votes = self._mean_reversion_signal(df, current_price, has_position)
        elif self.strategy == "trend_following":
            signal, reason, votes = self._trend_following_signal(df, current_price, has_position)
        else:
            signal, reason, votes = self._voting_signal(df, current_price, has_position)
        
        return signal, reason


class HourlySignalGenerator(SignalGenerator):
    """Generate trading signals optimized for HOURLY candles.
    
    Uses stricter thresholds, volatility filter, and longer indicator periods.
    """
    
    def __init__(self, strategy: str = "voting"):
        super().__init__(strategy)
        # Override with hourly config
        self.bb_period = HOURLY_BB_PERIOD
        self.bb_std = HOURLY_BB_STD
        self.rsi_period = HOURLY_RSI_PERIOD
        self.rsi_oversold = HOURLY_RSI_OVERSOLD
        self.rsi_overbought = HOURLY_RSI_OVERBOUGHT
        self.atr_threshold = HOURLY_ATR_VOLATILITY_THRESHOLD
    
    def _mean_reversion_signal(self, df: pd.DataFrame, current_price: float, 
                                has_position: bool) -> Tuple[Signal, str, dict]:
        """Mean Reversion with volatility filter for hourly."""
        closes = df['close']
        upper, middle, lower = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        rsi = calculate_rsi(closes, self.rsi_period)
        ema_50 = calculate_ema(closes, 50)
        
        bb_lower = lower.iloc[-1]
        bb_middle = middle.iloc[-1]
        bb_upper = upper.iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_ema50 = ema_50.iloc[-1]
        
        # Volatility filter
        is_volatile, vol_pct = self._check_volatility_filter(df, current_price)
        strong_downtrend = current_price < current_ema50 * 0.95
        
        votes = {
            'bb_oversold': current_price < bb_lower,
            'rsi_oversold': current_rsi < self.rsi_oversold,
            'not_strong_downtrend': not strong_downtrend,
            'low_volatility': not is_volatile,
        }
        
        if not has_position:
            if is_volatile:
                return Signal.NONE, f"MEAN_REV: Skipping (volatility {vol_pct:.2%})", votes
            if current_price < bb_lower and current_rsi < self.rsi_oversold and not strong_downtrend:
                return Signal.BUY, f"MEAN_REV BUY: BB oversold + RSI={current_rsi:.0f}", votes
        
        if has_position:
            if current_price >= bb_middle:
                return Signal.SELL, f"MEAN_REV SELL: Price >= BB_Mid", votes
        
        return Signal.NONE, f"MEAN_REV: Waiting (RSI: {current_rsi:.0f})", votes
    
    def _trend_following_signal(self, df: pd.DataFrame, current_price: float,
                                 has_position: bool) -> Tuple[Signal, str, dict]:
        """Trend Following with longer EMAs for hourly."""
        closes = df['close']
        
        # Longer EMAs for hourly
        ema_fast = calculate_ema(closes, 24)  # 1 day
        ema_slow = calculate_ema(closes, 72)  # 3 days
        macd_line, signal_line, histogram = calculate_macd(closes)
        rsi = calculate_rsi(closes, self.rsi_period)
        
        current_ema_fast = ema_fast.iloc[-1]
        current_ema_slow = ema_slow.iloc[-1]
        current_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]
        prev_prev_hist = histogram.iloc[-3] if len(histogram) > 2 else prev_hist
        current_rsi = rsi.iloc[-1]
        
        uptrend = current_ema_fast > current_ema_slow
        ema_spread = (current_ema_fast - current_ema_slow) / current_ema_slow
        strong_uptrend = uptrend and ema_spread > 0.01
        macd_bullish = current_hist > 0 and current_hist > prev_hist and prev_hist > prev_prev_hist
        rsi_bullish = current_rsi > 50 and current_rsi < 70
        
        votes = {
            'strong_uptrend': strong_uptrend,
            'macd_bullish': macd_bullish,
            'rsi_bullish': rsi_bullish,
        }
        
        if not has_position:
            if strong_uptrend and macd_bullish and rsi_bullish:
                return Signal.BUY, f"TREND BUY: Strong signals @ ${current_price:.2f}", votes
        
        if has_position:
            if not uptrend and current_hist < prev_hist:
                return Signal.SELL, f"TREND SELL: Reversal @ ${current_price:.2f}", votes
        
        return Signal.NONE, f"TREND: Waiting", votes
    
    def _voting_signal(self, df: pd.DataFrame, current_price: float,
                       has_position: bool) -> Tuple[Signal, str, dict]:
        """Voting with stricter thresholds for hourly."""
        closes = df['close']
        volumes = df['volume']
        
        upper, middle, lower = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        rsi = calculate_rsi(closes, self.rsi_period)
        ema_72 = calculate_ema(closes, 72)
        macd_line, signal_line, histogram = calculate_macd(closes)
        vol_sma = calculate_volume_sma(volumes, 24)
        
        bb_lower = lower.iloc[-1]
        bb_middle = middle.iloc[-1]
        bb_upper = upper.iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_ema72 = ema_72.iloc[-1]
        current_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]
        current_vol = volumes.iloc[-1]
        avg_vol = vol_sma.iloc[-1]
        
        is_volatile, _ = self._check_volatility_filter(df, current_price)
        
        # Stricter buy votes
        buy_votes = {
            'bb_oversold': current_price < bb_lower,
            'rsi_oversold': current_rsi < self.rsi_oversold,
            'macd_turning': current_hist > prev_hist and current_hist > 0,
            'above_ema72': current_price > current_ema72,
            'volume_spike': current_vol > avg_vol * 1.5,
            'low_volatility': not is_volatile,
        }
        
        sell_votes = {
            'bb_overbought': current_price > bb_upper,
            'rsi_overbought': current_rsi > self.rsi_overbought,
            'macd_weakening': current_hist < prev_hist and current_hist < 0,
            'above_middle_band': current_price >= bb_middle * 1.01,
        }
        
        buy_count = sum(buy_votes.values())
        sell_count = sum(sell_votes.values())
        all_votes = {**buy_votes, **sell_votes}
        
        if not has_position:
            # Need 4+ buy signals (stricter)
            if buy_count >= 4:
                signals_str = ", ".join([k for k, v in buy_votes.items() if v])
                return Signal.BUY, f"VOTING BUY ({buy_count}/6): {signals_str}", all_votes
        
        if has_position:
            # Need 3+ sell signals (stricter)
            if sell_count >= 3 or current_price >= bb_middle * 1.02:
                signals_str = ", ".join([k for k, v in sell_votes.items() if v])
                return Signal.SELL, f"VOTING SELL ({sell_count}/4): {signals_str}", all_votes
        
        return Signal.NONE, f"VOTING: {buy_count}/6 buy, {sell_count}/4 sell", all_votes


class FuturesSignalGenerator:
    """Generate LONG/SHORT signals for perpetual futures trading.
    
    Key difference from spot:
    - Can go LONG (profit when price goes up)
    - Can go SHORT (profit when price goes down)
    - Always in a position or flat (no holding spot)
    """
    
    def __init__(self, strategy: str = "voting"):
        self.strategy = strategy
        self.bb_period = BB_PERIOD
        self.bb_std = BB_STD
        self.rsi_period = RSI_PERIOD
        self.rsi_oversold = RSI_OVERSOLD
        self.rsi_overbought = RSI_OVERBOUGHT
        self.atr_threshold = ATR_VOLATILITY_THRESHOLD
    
    def _check_volatility_filter(self, df: pd.DataFrame, current_price: float) -> Tuple[bool, float]:
        """Check if volatility is too high for trading."""
        atr = calculate_atr(df['high'], df['low'], df['close'])
        current_atr = atr.iloc[-1]
        volatility_pct = current_atr / current_price
        is_too_volatile = volatility_pct > self.atr_threshold
        return is_too_volatile, volatility_pct
    
    def _mean_reversion_signal(self, df: pd.DataFrame, current_price: float,
                                position_side: str) -> Tuple[Signal, str, dict]:
        """Mean reversion for futures: long oversold, short overbought."""
        closes = df['close']
        upper, middle, lower = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        rsi = calculate_rsi(closes, self.rsi_period)
        
        bb_lower = lower.iloc[-1]
        bb_middle = middle.iloc[-1]
        bb_upper = upper.iloc[-1]
        current_rsi = rsi.iloc[-1]
        
        is_volatile, vol_pct = self._check_volatility_filter(df, current_price)
        
        votes = {
            'bb_oversold': current_price < bb_lower,
            'rsi_oversold': current_rsi < self.rsi_oversold,
            'bb_overbought': current_price > bb_upper,
            'rsi_overbought': current_rsi > self.rsi_overbought,
            'low_volatility': not is_volatile,
        }
        
        # No position - look for entry
        if position_side == 'none':
            if is_volatile:
                return Signal.NONE, f"Skipping (volatility {vol_pct:.2%})", votes
            
            # Long when oversold
            if current_price < bb_lower and current_rsi < self.rsi_oversold:
                return Signal.LONG, f"LONG: BB oversold + RSI={current_rsi:.0f}", votes
            
            # Short when overbought
            if current_price > bb_upper and current_rsi > self.rsi_overbought:
                return Signal.SHORT, f"SHORT: BB overbought + RSI={current_rsi:.0f}", votes
        
        # Close long at middle band
        elif position_side == 'long':
            if current_price >= bb_middle:
                return Signal.CLOSE_LONG, f"Close LONG: Price at BB middle", votes
        
        # Close short at middle band
        elif position_side == 'short':
            if current_price <= bb_middle:
                return Signal.CLOSE_SHORT, f"Close SHORT: Price at BB middle", votes
        
        return Signal.NONE, f"MEAN_REV: RSI={current_rsi:.0f}", votes
    
    def _trend_following_signal(self, df: pd.DataFrame, current_price: float,
                                 position_side: str) -> Tuple[Signal, str, dict]:
        """Trend following for futures: long uptrends, short downtrends."""
        closes = df['close']
        
        ema_fast = calculate_ema(closes, 10)
        ema_slow = calculate_ema(closes, 30)
        macd_line, signal_line, histogram = calculate_macd(closes)
        rsi = calculate_rsi(closes, self.rsi_period)
        
        current_ema_fast = ema_fast.iloc[-1]
        current_ema_slow = ema_slow.iloc[-1]
        current_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]
        current_rsi = rsi.iloc[-1]
        
        uptrend = current_ema_fast > current_ema_slow
        downtrend = current_ema_fast < current_ema_slow
        macd_bullish = current_hist > 0 and current_hist > prev_hist
        macd_bearish = current_hist < 0 and current_hist < prev_hist
        
        votes = {
            'uptrend': uptrend,
            'downtrend': downtrend,
            'macd_bullish': macd_bullish,
            'macd_bearish': macd_bearish,
        }
        
        if position_side == 'none':
            # Long on uptrend
            if uptrend and macd_bullish and current_rsi > 50:
                return Signal.LONG, f"LONG: Uptrend + MACD↑", votes
            
            # Short on downtrend
            if downtrend and macd_bearish and current_rsi < 50:
                return Signal.SHORT, f"SHORT: Downtrend + MACD↓", votes
        
        elif position_side == 'long':
            # Close long on trend reversal
            if not uptrend and current_hist < prev_hist:
                return Signal.CLOSE_LONG, f"Close LONG: Trend reversal", votes
        
        elif position_side == 'short':
            # Close short on trend reversal
            if not downtrend and current_hist > prev_hist:
                return Signal.CLOSE_SHORT, f"Close SHORT: Trend reversal", votes
        
        return Signal.NONE, f"TREND: {'UP' if uptrend else 'DOWN'}", votes
    
    def _voting_signal(self, df: pd.DataFrame, current_price: float,
                       position_side: str) -> Tuple[Signal, str, dict]:
        """Voting strategy for futures: combines multiple indicators."""
        closes = df['close']
        volumes = df['volume']
        
        upper, middle, lower = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        rsi = calculate_rsi(closes, self.rsi_period)
        ema_20 = calculate_ema(closes, 20)
        ema_50 = calculate_ema(closes, 50)
        macd_line, signal_line, histogram = calculate_macd(closes)
        vol_sma = calculate_volume_sma(volumes, 20)
        
        bb_lower = lower.iloc[-1]
        bb_middle = middle.iloc[-1]
        bb_upper = upper.iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_ema20 = ema_20.iloc[-1]
        current_ema50 = ema_50.iloc[-1]
        current_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]
        current_vol = volumes.iloc[-1]
        avg_vol = vol_sma.iloc[-1]
        
        is_volatile, _ = self._check_volatility_filter(df, current_price)
        
        # LONG votes
        long_votes = {
            'bb_oversold': current_price < bb_lower,
            'rsi_oversold': current_rsi < 35,
            'macd_turning_up': current_hist > prev_hist,
            'above_ema50': current_price > current_ema50,
            'volume_spike': current_vol > avg_vol * 1.2,
        }
        
        # SHORT votes
        short_votes = {
            'bb_overbought': current_price > bb_upper,
            'rsi_overbought': current_rsi > 65,
            'macd_turning_down': current_hist < prev_hist,
            'below_ema50': current_price < current_ema50,
            'volume_spike': current_vol > avg_vol * 1.2,
        }
        
        # Close LONG votes
        close_long_votes = {
            'at_upper_band': current_price >= bb_upper,
            'rsi_overbought': current_rsi > 70,
            'macd_weakening': current_hist < prev_hist,
        }
        
        # Close SHORT votes
        close_short_votes = {
            'at_lower_band': current_price <= bb_lower,
            'rsi_oversold': current_rsi < 30,
            'macd_strengthening': current_hist > prev_hist,
        }
        
        long_count = sum(long_votes.values())
        short_count = sum(short_votes.values())
        close_long_count = sum(close_long_votes.values())
        close_short_count = sum(close_short_votes.values())
        
        all_votes = {**long_votes, **short_votes}
        
        if position_side == 'none':
            if is_volatile:
                return Signal.NONE, f"Skipping (volatile)", all_votes
            
            # Open long with 3+ votes
            if long_count >= 3:
                signals_str = ", ".join([k for k, v in long_votes.items() if v])
                return Signal.LONG, f"LONG ({long_count}/5): {signals_str}", all_votes
            
            # Open short with 3+ votes
            if short_count >= 3:
                signals_str = ", ".join([k for k, v in short_votes.items() if v])
                return Signal.SHORT, f"SHORT ({short_count}/5): {signals_str}", all_votes
        
        elif position_side == 'long':
            if close_long_count >= 2 or current_price >= bb_middle * 1.01:
                return Signal.CLOSE_LONG, f"Close LONG ({close_long_count}/3)", all_votes
        
        elif position_side == 'short':
            if close_short_count >= 2 or current_price <= bb_middle * 0.99:
                return Signal.CLOSE_SHORT, f"Close SHORT ({close_short_count}/3)", all_votes
        
        return Signal.NONE, f"VOTING: L={long_count}/5, S={short_count}/5", all_votes
    
    def generate_signal(self, df: pd.DataFrame, current_price: float,
                        position_side: str = 'none') -> Tuple[Signal, str]:
        """Generate trading signal for futures.
        
        Args:
            df: OHLCV DataFrame
            current_price: Current market price
            position_side: 'none', 'long', or 'short'
        
        Returns:
            Tuple of (Signal, reason string)
        """
        min_periods = max(self.bb_period, 50) + 5
        if len(df) < min_periods:
            return Signal.NONE, "Insufficient data"
        
        if self.strategy == "mean_reversion":
            signal, reason, _ = self._mean_reversion_signal(df, current_price, position_side)
        elif self.strategy == "trend_following":
            signal, reason, _ = self._trend_following_signal(df, current_price, position_side)
        else:
            signal, reason, _ = self._voting_signal(df, current_price, position_side)
        
        return signal, reason

