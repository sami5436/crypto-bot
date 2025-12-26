# 📖 bots.py

Trading bot classes for live trading and backtesting.

---

## Classes

### `PaperTradingBot`
Real-time spot paper trading.

```python
bot = PaperTradingBot()
bot.run()  # Starts live trading loop
```

#### What it does:
1. Fetches live OHLCV data from exchange every 5 seconds
2. Generates signals using configured strategy
3. Executes simulated trades
4. Prints status to console
5. Logs trades to CSV

---

### `FuturesPaperTradingBot`
Real-time futures paper trading with longs and shorts.

```python
bot = FuturesPaperTradingBot(leverage=3)
bot.run()
```

#### Features:
- Opens LONG positions (profit when price rises)
- Opens SHORT positions (profit when price falls)
- Checks for liquidation on each tick
- Shows margin, liquidation price, ROE

---

### `BacktestBot`
Backtest on a specific historical date.

```python
bot = BacktestBot(backtest_date=datetime(2025, 12, 20))
bot.run()
```

#### Features:
- Uses historical hourly data for the given date
- Simulates entire day's trading
- Reports final PnL

---

### `StrategyComparer`
Compare multiple strategies over a date range.

```python
comparer = StrategyComparer(
    start_date=datetime(2025, 1, 1),
    end_date=datetime(2025, 12, 25),
    timeframe='daily'
)
comparer.run()
```

#### Features:
- Tests mean_reversion, trend_following, voting
- Loads data from local CSV files
- Ranks strategies by return
- Shows trade log for winner

---

### `FuturesStrategyComparer`
Compare futures strategies with longs + shorts.

```python
comparer = FuturesStrategyComparer(
    start_date=datetime(2025, 12, 20),
    end_date=datetime(2025, 12, 25),
    timeframe='hourly',
    leverage=3
)
comparer.run()
```

#### Features:
- Tests all strategies with LONG and SHORT signals
- Simulates leverage (1-10x)
- Shows round trips (open + close pairs)
- Auto-closes open positions at backtest end
- Reports liquidations if any

#### Output Columns

| Column | Description |
|--------|-------------|
| Strategy | Strategy name |
| Return | % return |
| Trips | Round trips (completed trades) |
| Long | Number of long positions |
| Short | Number of short positions |
| Win% | Win rate |
| Final $ | Final equity |

---

## Data Loading

All comparers can load from local CSV files:
- `historical_data/btc_usd_daily.csv`
- `historical_data/btc_usd_hourly.csv`
- `historical_data/eth_usd_daily.csv`
- `historical_data/eth_usd_hourly.csv`

Use `data_collector.py` to refresh these files.
