# 📖 paper_trader.py

> **The main entry point — this is the file you run to start the bot.**

When you run `python paper_trader.py`, this file presents you with a menu of options and routes you to the appropriate trading mode.

---

## 🎯 What This File Does

1. **Shows the interactive menu** (options 1-7)
2. **Collects user input** (dates, leverage, timeframe)
3. **Launches the appropriate bot** based on your selection

This is the "front door" to the entire application. All the actual trading logic lives in other files — this just asks you what you want to do and hands off to the right handler.

---

## 🔧 Main Function

### `main()`
The entry point. Calls `get_user_mode()` to get user preferences, then launches the appropriate bot:

```python
if mode == 'live':
    PaperTradingBot().run()          # Option 1
elif mode == 'futures_live':
    FuturesPaperTradingBot().run()   # Option 7
elif mode == 'futures':
    FuturesStrategyComparer().run()  # Option 6
# ... etc
```

---

### `get_user_mode()`
Interactive menu that returns a tuple of `(mode, parameters)`:

| User Choice | Returns |
|-------------|---------|
| Option 1 | `('live', None)` |
| Option 2 | `('backtest', datetime)` |
| Option 3-5 | `('compare', {days/dates, timeframe})` |
| Option 6 | `('futures', {dates, timeframe, leverage})` |
| Option 7 | `('futures_live', {leverage})` |

---

## 📋 Menu Breakdown

```
1. Live trading           → PaperTradingBot (spot, real-time)
2. Backtest               → BacktestBot (spot, historical)
3. Compare (N days)       → StrategyComparer (spot, last N days)
4. Compare (daily)        → StrategyComparer (spot, date range, daily)
5. Compare (hourly)       → StrategyComparer (spot, date range, hourly)
6. Futures backtest       → FuturesStrategyComparer (longs+shorts)
7. Futures live           → FuturesPaperTradingBot (longs+shorts, real-time)
```

---

## 💡 How to Use

```bash
# Run the bot
python paper_trader.py

# Follow the prompts:
# - Select mode (1-7)
# - Enter dates if needed
# - Enter leverage for futures (1-10x)
# - Watch it trade!
```

Press **Ctrl+C** anytime to stop a running bot gracefully.
