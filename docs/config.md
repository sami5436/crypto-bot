# 📖 config.py

> **The control panel — every setting lives here. Change behavior without touching code.**

Want to adjust leverage? Change the strategy? Tweak the stop loss? This is where you do it.

---

## 🎯 What This File Does

This file holds **all configurable parameters** for the bot:
- Trading mode (paper vs live)
- Which exchange to use
- Leverage and position sizing
- Indicator parameters (RSI period, BB width, etc.)
- Risk management thresholds
- Fees and slippage simulation

**Pro tip:** Start conservative, then tune based on backtest results.

---

## ⚡ Quick Reference

### The Most Important Settings

| Setting | Current Value | What It Does |
|---------|---------------|--------------|
| `LIVE_MODE` | `False` | `False` = paper trading, `True` = REAL money |
| `FUTURES_MODE` | `True` | `True` = longs+shorts, `False` = spot only |
| `STARTING_CAPITAL` | `50.0` | How much fake money to start with |
| `LEVERAGE` | `3` | Futures leverage multiplier (1-10x) |
| `MAX_POSITION_SIZE_PCT` | `0.85` | Use 85% of capital per trade |
| `STRATEGY` | `"voting"` | Which strategy to use |

---

## 📋 All Settings

### Trading Mode
```python
LIVE_MODE = False        # NEVER set True unless you know what you're doing!
FUTURES_MODE = True      # Enable longs + shorts
```

### Capital & Symbol
```python
STARTING_CAPITAL = 50.0  # Starting USD balance
SYMBOL = "BTC/USD"       # What to trade (spot)
FUTURES_SYMBOL = "BTC/USDT:USDT"  # What to trade (futures)
TIMEFRAME = "1h"         # Candle timeframe (used by spot bot)
```

### Exchanges
```python
SPOT_EXCHANGE = "kraken"    # For spot trading
FUTURES_EXCHANGE = "bybit"  # For futures trading
```

### Leverage & Margin
```python
LEVERAGE = 3               # Default leverage (adjustable 1-10)
MAX_LEVERAGE = 10          # Hard cap
MARGIN_TYPE = "isolated"   # "isolated" or "cross"
```

### Strategy Parameters
```python
STRATEGY = "voting"        # Options: "mean_reversion", "trend_following", "voting"

# Bollinger Bands
BB_PERIOD = 20             # How many candles to calculate BB
BB_STD = 1.5               # Width of bands (higher = wider)

# RSI
RSI_PERIOD = 14            # How many candles for RSI
RSI_OVERSOLD = 25          # Below this = oversold
RSI_OVERBOUGHT = 75        # Above this = overbought
```

### Risk Management
```python
STOP_LOSS_PCT = 0.03       # 3% stop loss
TAKE_PROFIT_PCT = 0.02     # 2% take profit
MAX_POSITION_SIZE_PCT = 0.85  # Use 85% of capital

# Kill Switch Thresholds
MAX_DAILY_DRAWDOWN_PCT = 0.10  # 10% daily loss = halt trading
MAX_VOLATILITY_PCT = 0.08      # ATR > 8% = too volatile
MAX_TRADES_PER_DAY = 20        # Trade limit
```

### Cooldowns
```python
COOLDOWN_MINUTES = 60           # Wait time between spot trades
HOURLY_COOLDOWN_MINUTES = 360   # Wait time for hourly strategy
FUTURES_COOLDOWN_MINUTES = 0    # No cooldown for futures (but we have 0.5% threshold)
```

### Fee Simulation
```python
# Spot (Kraken)
MAKER_FEE = 0.0016   # 0.16%
TAKER_FEE = 0.0026   # 0.26%

# Futures (Bybit)
FUTURES_MAKER_FEE = 0.0001  # 0.01%
FUTURES_TAKER_FEE = 0.0006  # 0.06%

# Slippage (simulated price impact)
SIMULATED_SLIPPAGE = 0.0002  # 0.02%
```

---

## 💡 Common Adjustments

### Want more aggressive trading?
```python
MAX_POSITION_SIZE_PCT = 0.95  # Use 95% of capital
LEVERAGE = 5                  # 5x leverage
RSI_OVERSOLD = 30             # Trigger earlier
```

### Want safer trading?
```python
MAX_POSITION_SIZE_PCT = 0.50  # Use only 50% of capital
LEVERAGE = 2                  # Low leverage
STOP_LOSS_PCT = 0.02          # Tighter stop loss
```

### Want different strategy?
```python
STRATEGY = "mean_reversion"   # Or "trend_following"
```

---

## ⚠️ Warning

The `LIVE_MODE = True` setting would connect to real exchanges with real money. **This is not implemented/tested** — paper trading only!
