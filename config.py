"""
Configuration constants for the Crypto Paper Trading Bot.
Supports both SPOT and FUTURES trading modes.
"""

# =============================================================================
# TRADING MODE
# =============================================================================

LIVE_MODE = False  # Set to True for live trading (requires API keys)
FUTURES_MODE = True  # True = Perpetual Futures (longs/shorts), False = Spot only

# Capital and trading pair
STARTING_CAPITAL = 500.0  # USD
SYMBOL = "BTC/USD"  # For spot (Kraken)
FUTURES_SYMBOL = "BTC/USDT:USDT"  # For futures (Bybit)
TIMEFRAME = "1h"

# Exchange selection
SPOT_EXCHANGE = "kraken"
FUTURES_EXCHANGE = "bybit"
EXCHANGE = SPOT_EXCHANGE  # Backward compatibility


# =============================================================================
# FUTURES CONFIGURATION
# =============================================================================

LEVERAGE = 3  # Default leverage (1-10x recommended, max 20x)
MARGIN_TYPE = "isolated"  # "isolated" or "cross"
FUNDING_RATE_INTERVAL_HOURS = 8  # Funding paid every 8 hours
DEFAULT_FUNDING_RATE = 0.0001  # 0.01% default (actual rate fetched from API)

# Futures fee structure (Bybit)
FUTURES_MAKER_FEE = 0.0001  # 0.01%
FUTURES_TAKER_FEE = 0.0006  # 0.06%


# =============================================================================
# FEE STRUCTURE (Spot - Kraken)
# =============================================================================

MAKER_FEE = 0.0016  # 0.16%
TAKER_FEE = 0.0026  # 0.26%


# =============================================================================
# SIMULATED MARKET FRICTION
# =============================================================================

# Toggle between idealized (optimistic) and realistic (conservative) friction
REALISTIC_MODE = True  # Set to False for idealized backtest, True for realistic

# Idealized settings (optimistic backtest)
IDEALIZED_SLIPPAGE = 0.0005  # 0.05%
IDEALIZED_FEE_MULTIPLIER = 1.0  # Use base fees
IDEALIZED_PRICE_NOISE = 0.0  # No noise
IDEALIZED_TRADE_REJECTION_RATE = 0.0  # All trades execute
IDEALIZED_USE_NEXT_OPEN = False  # Enter at close price (unrealistic but common)

# Realistic settings (conservative, closer to live trading)
REALISTIC_SLIPPAGE = 0.003  # 0.3% - much worse in volatile markets
REALISTIC_FEE_MULTIPLIER = 1.5  # 50% higher fees (hidden costs, wider spreads)
REALISTIC_PRICE_NOISE = 0.002  # ±0.2% random noise on entry/exit
REALISTIC_TRADE_REJECTION_RATE = 0.10  # 10% of orders fail
REALISTIC_USE_NEXT_OPEN = True  # Enter at NEXT candle open (simulates delay)

# Funding rate ranges
IDEALIZED_FUNDING_MIN = -0.0001  # -0.01%
IDEALIZED_FUNDING_MAX = 0.0003   # +0.03%
REALISTIC_FUNDING_MIN = -0.001   # -0.1%
REALISTIC_FUNDING_MAX = 0.001    # +0.1%

# Select active settings based on mode
if REALISTIC_MODE:
    SIMULATED_SLIPPAGE = REALISTIC_SLIPPAGE
    FEE_MULTIPLIER = REALISTIC_FEE_MULTIPLIER
    PRICE_NOISE = REALISTIC_PRICE_NOISE
    TRADE_REJECTION_RATE = REALISTIC_TRADE_REJECTION_RATE
    USE_NEXT_CANDLE_OPEN = REALISTIC_USE_NEXT_OPEN
    FUNDING_RATE_MIN = REALISTIC_FUNDING_MIN
    FUNDING_RATE_MAX = REALISTIC_FUNDING_MAX
else:
    SIMULATED_SLIPPAGE = IDEALIZED_SLIPPAGE
    FEE_MULTIPLIER = IDEALIZED_FEE_MULTIPLIER
    PRICE_NOISE = IDEALIZED_PRICE_NOISE
    TRADE_REJECTION_RATE = IDEALIZED_TRADE_REJECTION_RATE
    USE_NEXT_CANDLE_OPEN = IDEALIZED_USE_NEXT_OPEN
    FUNDING_RATE_MIN = IDEALIZED_FUNDING_MIN
    FUNDING_RATE_MAX = IDEALIZED_FUNDING_MAX

# Other friction settings (same for both modes)
SIMULATED_SPREAD = 0.0005  # 0.05%
PARTIAL_FILL_PROBABILITY = 0.30  # 30% chance of partial fill
MIN_FILL_RATIO = 0.30  # Minimum 30% fill on partial
MAX_FILL_RATIO = 0.80  # Maximum 80% fill on partial


# =============================================================================
# STRATEGY PARAMETERS - DAILY CANDLES (default)
# =============================================================================

BB_PERIOD = 20  # Bollinger Band period
BB_STD = 1.5  # Bollinger Band standard deviation
RSI_PERIOD = 14  # RSI period
RSI_OVERSOLD = 25  # RSI oversold threshold
RSI_OVERBOUGHT = 75  # RSI overbought threshold
ATR_VOLATILITY_THRESHOLD = 0.05  # Skip if ATR > 5% of price


# =============================================================================
# STRATEGY PARAMETERS - HOURLY CANDLES (used when timeframe=hourly)
# =============================================================================

HOURLY_BB_PERIOD = 72  # 3 days of hourly data
HOURLY_BB_STD = 2.0  # Wider bands for noise filtering
HOURLY_RSI_PERIOD = 24  # 1 full day
HOURLY_RSI_OVERSOLD = 20  # More extreme
HOURLY_RSI_OVERBOUGHT = 80  # More extreme
HOURLY_ATR_VOLATILITY_THRESHOLD = 0.025  # Stricter for hourly


# =============================================================================
# RISK MANAGEMENT
# =============================================================================

STOP_LOSS_PCT = 0.03  # 3% stop loss (on position value, not margin)
TAKE_PROFIT_PCT = 0.02  # 2% take profit
MAX_POSITION_SIZE_PCT = 0.85  # Use 85% of capital per trade
MIN_EXPECTED_EDGE = 0.005  # Need 0.5% expected edge to trade

# Futures-specific risk
MAX_LEVERAGE = 10  # Hard cap on leverage
LIQUIDATION_BUFFER_PCT = 0.10  # Close position if within 10% of liquidation


# =============================================================================
# KILL SWITCH THRESHOLDS
# =============================================================================

MAX_DAILY_DRAWDOWN_PCT = 0.10  # 10% daily drawdown limit
MAX_VOLATILITY_PCT = 0.08  # ATR > 8% triggers halt
MAX_CONSECUTIVE_API_ERRORS = 3
MAX_TRADES_PER_DAY = 20  # Trade limit
COOLDOWN_MINUTES = 60  # 1-hour cooldown (for daily)
HOURLY_COOLDOWN_MINUTES = 360  # 6-hour cooldown (for hourly)
FUTURES_COOLDOWN_MINUTES = 0  # No cooldown for futures paper trading


# =============================================================================
# LOGGING & TIMING
# =============================================================================

TRADES_LOG_FILE = "logs/trades_log.csv"
UPDATE_INTERVAL_SECONDS = 5

# Strategy selection: "mean_reversion", "trend_following", or "voting"
STRATEGY = "voting"
