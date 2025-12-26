# 📖 paper_trader.py

Entry point and interactive menu for the bot.

---

## Functions

### `main()`
Main entry point. Runs the interactive menu and launches the selected mode.

```bash
python paper_trader.py
```

---

### `get_user_mode()`
Interactive menu that returns the selected mode and parameters.

**Returns:** `Tuple[str, Any]`

| Mode | Value | Description |
|------|-------|-------------|
| `'live'` | `None` | Real-time spot paper trading |
| `'backtest'` | `datetime` | Backtest on specific date |
| `'compare'` | `dict` | Strategy comparison |
| `'futures'` | `dict` | Futures backtest |
| `'futures_live'` | `dict` | Futures live paper trading |

---

## Menu Options

```
1. Live trading (real-time paper trading)
2. Backtest (simulate on historical date)
3. Compare strategies (last N days, daily candles)
4. Compare strategies (date range, daily candles)
5. Compare strategies (date range, 1-hour candles)
6. 🔮 FUTURES: Compare with longs + shorts (date range)
7. 🔮 FUTURES: Live paper trading (longs + shorts)
```

---

## Option Details

### Option 1: Live Spot Trading
- Uses `PaperTradingBot`
- Fetches live prices from Kraken
- Updates every 5 seconds
- Press Ctrl+C to stop

### Option 2: Backtest
- Uses `BacktestBot`
- Enter date like `2025-12-20`
- Simulates that day's trading

### Options 3-5: Strategy Comparison
- Uses `StrategyComparer`
- Choose date range or last N days
- Daily or hourly candles
- Compares 3 strategies, shows winner

### Option 6: Futures Backtest
- Uses `FuturesStrategyComparer`
- Enter leverage (1-10x)
- Choose timeframe (daily/hourly)
- Enter date range
- Shows longs, shorts, round trips

### Option 7: Futures Live Trading
- Uses `FuturesPaperTradingBot`
- Enter leverage (1-10x)
- Real-time with longs and shorts
- Shows margin, liquidation price

---

## Example Usage

```bash
$ python paper_trader.py

Choose mode: 6

Leverage [3]: 5
Timeframe: 2  (hourly)
Start date: 2025-12-20
End date: (today)

# Runs futures backtest with 5x leverage on hourly candles
```
