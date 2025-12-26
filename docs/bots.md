# 📖 bots.py

> **The brain of the operation — contains all the bot classes that actually run trading loops.**

This file has the main "engines" that fetch data, generate signals, execute trades, and print status updates. When you select an option from the menu, one of these bots gets instantiated and runs.

---

## 🎯 What This File Does

- **PaperTradingBot**: Live spot trading (buy/sell only)
- **FuturesPaperTradingBot**: Live futures trading (longs/shorts with leverage)
- **BacktestBot**: Simulate trading on a historical date
- **StrategyComparer**: Compare all strategies on spot trading
- **FuturesStrategyComparer**: Compare all strategies with futures (longs/shorts)

Each bot follows the same basic loop:
1. Fetch price data from exchange
2. Calculate indicators
3. Generate signal (buy/sell/long/short/hold)
4. Execute trade if conditions met
5. Update display
6. Sleep and repeat

---

## 📦 Bot Classes

### `PaperTradingBot`
**Purpose:** Real-time spot paper trading

```python
bot = PaperTradingBot()
bot.run()  # Starts trading loop
```

- Fetches live OHLCV data from Kraken
- Uses hourly candles by default
- Long-only (can only buy, then sell)
- Updates every 5 seconds

---

### `FuturesPaperTradingBot`
**Purpose:** Real-time futures paper trading with leverage

```python
bot = FuturesPaperTradingBot(leverage=3)
bot.run()
```

- Fetches 1-minute candles for fast signals
- Can go LONG (profit when price rises) or SHORT (profit when price falls)
- Simulates margin, liquidation, fees
- **0.5% threshold**: Won't close positions on tiny moves to prevent oscillation
- Updates every 60 seconds with clean terminal display

---

### `BacktestBot`
**Purpose:** Test strategy on a specific historical date

```python
from datetime import datetime
bot = BacktestBot(backtest_date=datetime(2025, 12, 20))
bot.run()
```

- Fetches hourly data for that specific day
- Simulates what would have happened
- Shows final P&L

---

### `StrategyComparer`
**Purpose:** Compare mean_reversion, trend_following, voting on spot trading

```python
comparer = StrategyComparer(
    start_date=datetime(2025, 1, 1),
    end_date=datetime(2025, 12, 25),
    timeframe='daily'
)
comparer.run()
```

- Backtests all 3 strategies on the same data
- Ranks by return percentage
- Shows winner and trade log

---

### `FuturesStrategyComparer`
**Purpose:** Compare strategies with futures (longs + shorts)

```python
comparer = FuturesStrategyComparer(
    start_date=datetime(2025, 12, 20),
    end_date=datetime(2025, 12, 25),
    timeframe='hourly',
    leverage=3
)
comparer.run()
```

- Tests all strategies with LONG and SHORT signals
- Simulates leverage
- Shows "round trips" (open→close pairs)
- Auto-closes positions at end of backtest period

---

## 🔧 Key Methods (FuturesPaperTradingBot)

| Method | What It Does |
|--------|--------------|
| `fetch_ohlcv()` | Gets latest 100 candles from exchange |
| `print_status()` | Displays clean terminal UI with position info |
| `run()` | Main trading loop |

---

## 📁 Data Files Used

The comparers load data from CSV files in `historical_data/`:
- `btc_usd_daily.csv` — Daily BTC/USD candles
- `btc_usd_hourly.csv` — Hourly BTC/USD candles
- `eth_usd_daily.csv` — Daily ETH/USD candles
- `eth_usd_hourly.csv` — Hourly ETH/USD candles

Use `data_collector.py` to refresh these files with latest data.
