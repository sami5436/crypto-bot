# 🤖 Crypto Paper Trading Bot

> **A fully-featured cryptocurrency trading simulator that lets you test algorithmic trading strategies with fake money and real market prices.**

This bot is designed for learning and experimentation. It connects to real exchanges (Kraken, Bybit) to get live prices, but all trades are simulated — you never risk real money. Think of it as a "flight simulator" for crypto trading.

---

## 🎯 What Can This Bot Do?

### Paper Trading (Fake Money, Real Prices)
Run the bot and watch it trade in real-time using your chosen strategy. It'll show you what trades it would make, track your simulated P&L, and log everything to CSV files.

### Backtesting (Test on Historical Data)
Pick any date range and see how a strategy would have performed. Did mean reversion beat trend following last month? Find out in seconds.

### Strategy Comparison
Run all strategies side-by-side and see which one wins. The bot tests mean reversion, trend following, and a voting ensemble, then crowns a winner.

### Futures Trading with Leverage
Go beyond simple buy/hold — open **long** positions (bet price goes up) or **short** positions (bet price goes down) with up to 10x leverage. The bot simulates margin, liquidation prices, and funding rates.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Interactive mode
python paper_trader.py

# Or use command line arguments:
python paper_trader.py 6 --start 2024-01-01 --end 2024-12-01 --leverage 3
```

### Command Line Usage

```bash
# Futures backtest (Option 6)
python paper_trader.py 6 --start 2024-01-01 --end 2024-12-01 --leverage 3

# Futures live (Option 7)
python paper_trader.py 7 --leverage 5

# Strategy comparison (Option 4)
python paper_trader.py 4 --start 2024-06-01 --end 2024-12-01

# Hourly comparison (Option 5)
python paper_trader.py 5 --days 30 --timeframe hourly

# Show help
python paper_trader.py --help
```

| Argument | Description |
|----------|-------------|
| `mode` | 1-7 (required) - see menu options below |
| `--start` | Start date YYYY-MM-DD |
| `--end` | End date (default: today) |
| `--days` | Days back (default: 30) |
| `--leverage` / `-l` | Leverage 1-10 |
| `--timeframe` / `-t` | daily or hourly |

---

## 📋 Menu Options

| Option | Mode | Description |
|--------|------|-------------|
| **1** | Live Spot | Real-time paper trading, long-only (buy/sell) |
| **2** | Backtest | Simulate a specific historical date |
| **3** | Compare (N days) | Compare strategies over last N days |
| **4** | Compare (daily) | Compare strategies on daily candles |
| **5** | Compare (hourly) | Compare strategies on hourly candles |
| **6** | 🔮 Futures Backtest | Test longs + shorts with leverage |
| **7** | 🔮 Futures Live | Real-time futures paper trading |

---

## 📁 Project Structure

| File | What It Does | Details |
|------|--------------|---------|
| [`paper_trader.py`](paper_trader.py) | Entry point — the menu you see when you run the bot | [📖 Docs](docs/paper_trader.md) |
| [`config.py`](config.py) | All settings: leverage, fees, thresholds, strategies | [📖 Docs](docs/config.md) |
| [`models.py`](models.py) | Data structures: Position, Trade, Signal enums | [📖 Docs](docs/models.md) |
| [`indicators.py`](indicators.py) | Technical analysis: RSI, Bollinger Bands, MACD, ATR | [📖 Docs](docs/indicators.md) |
| [`strategies.py`](strategies.py) | Signal generation: when to buy, sell, go long, go short | [📖 Docs](docs/strategies.md) |
| [`account.py`](account.py) | Account management: balance, positions, P&L tracking | [📖 Docs](docs/account.md) |
| [`executor.py`](executor.py) | Order execution: simulates fills, fees, slippage | [📖 Docs](docs/executor.md) |
| [`bots.py`](bots.py) | Bot classes that tie everything together | [📖 Docs](docs/bots.md) |

---

## 📊 Available Strategies

| Strategy | How It Works | Best For |
|----------|--------------|----------|
| **Mean Reversion** | Buys when price drops below Bollinger Band (oversold), sells when it returns to middle | Sideways/ranging markets |
| **Trend Following** | Follows the momentum using EMA crossovers and MACD | Strong trending markets |
| **Voting** | Combines 6 indicators and takes action when 4+ agree | All-around balanced approach |

---

## ⚠️ Important Concepts

### Paper Trading vs Live Trading
- **Paper trading** = fake money, real prices (what this bot does by default)
- **Live trading** = real money (requires `LIVE_MODE = True` in config + API keys)

### Spot vs Futures
- **Spot** = Buy and hold actual crypto. You profit only when price goes UP.
- **Futures** = Trade contracts with leverage. You can profit when price goes UP (long) OR DOWN (short).

### Leverage
With 3x leverage, a 1% price move = 3% gain (or loss) on your margin. Higher leverage = higher risk.

### Liquidation
If your futures position loses too much, the exchange closes it automatically. This bot simulates liquidation.

---

## 💡 Tips for Getting Started

1. **Start with Option 6** (Futures Backtest) to see how strategies perform historically
2. **Then try Option 7** (Futures Live) to watch the bot trade in real-time
3. **Check `futures_trades.csv`** to see all executed trades
4. **Adjust settings in `config.py`** to tune the strategy

---

## 📈 Example Output (Futures Backtest)

```
╔════════════════════════════════════════════════════════════╗
║  🔮 FUTURES PAPER TRADING    2025-12-26 11:25:00           ║
╠════════════════════════════════════════════════════════════╣
║  BTC/USD       $88,950.00    RSI:  45.2    3x LEV          ║
╠════════════════════════════════════════════════════════════╣
║  💰 EQUITY     $    52.50    🟢  +5.00%                    ║
║  📊 REALIZED   $    +2.50    UNREALIZED $   +0.00          ║
╠════════════════════════════════════════════════════════════╣
║  📈 LONG    Entry: $ 88,500.00   Move: +0.51%              ║
║  🟢 PnL: $   +0.45 ( +1.8% ROE)   Liq: $ 59,000.00         ║
╠════════════════════════════════════════════════════════════╣
║  🎯 VOTING: L=3/5, S=1/5 - HOLDING                         ║
║  ✅ ACTIVE    Trades: 5/20                                 ║
╚════════════════════════════════════════════════════════════╝
```

---

## 📖 Documentation

Click any link in the project structure table above, or browse the [`docs/`](docs/) folder for detailed documentation on each module.

---

**Happy paper trading! 🚀**
