# 🤖 Crypto Paper Trading Bot

A modular cryptocurrency paper trading bot with **spot** and **perpetual futures** support. Backtest strategies, paper trade in real-time, and compare performance — all without risking real money.

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python paper_trader.py
```

## 📋 Menu Options

| Option | Description |
|--------|-------------|
| **1** | Live spot paper trading (real-time) |
| **2** | Backtest on a specific date |
| **3-5** | Compare strategies (daily/hourly) |
| **6** | 🔮 Futures backtest (longs + shorts) |
| **7** | 🔮 Futures live paper trading |

## 📁 Project Structure

| File | Purpose | Documentation |
|------|---------|---------------|
| [`paper_trader.py`](paper_trader.py) | Entry point & menu | [📖 docs/paper_trader.md](docs/paper_trader.md) |
| [`config.py`](config.py) | All settings | [📖 docs/config.md](docs/config.md) |
| [`models.py`](models.py) | Data classes | [📖 docs/models.md](docs/models.md) |
| [`indicators.py`](indicators.py) | Technical indicators | [📖 docs/indicators.md](docs/indicators.md) |
| [`strategies.py`](strategies.py) | Signal generation | [📖 docs/strategies.md](docs/strategies.md) |
| [`account.py`](account.py) | Account management | [📖 docs/account.md](docs/account.md) |
| [`executor.py`](executor.py) | Order execution | [📖 docs/executor.md](docs/executor.md) |
| [`bots.py`](bots.py) | Trading bots | [📖 docs/bots.md](docs/bots.md) |

## ⚙️ Key Features

### Spot Trading
- Long-only positions (buy low, sell high)
- Bollinger Bands, RSI, MACD indicators
- Stop-loss and take-profit orders

### Futures Trading
- **Long** AND **Short** positions
- Configurable leverage (1-10x)
- Liquidation simulation
- Funding rate tracking (simulated)

### Risk Management
- Kill switch (drawdown limits, volatility)
- Cooldown between trades
- Max daily trade limits

## 📊 Strategies

| Strategy | Description |
|----------|-------------|
| `mean_reversion` | Buy oversold, sell overbought (BB + RSI) |
| `trend_following` | Trade with the trend (EMA + MACD) |
| `voting` | Combines multiple indicators |

## 💡 Important Notes

- **Paper trading = fake money**, real market prices
- No API keys needed for paper trading
- All trades logged to CSV files
- Set `LIVE_MODE = True` in config.py ONLY for real trading (requires API keys)

## 📈 Example Output

```
🔮 FUTURES STRATEGY COMPARISON
Leverage: 3x | Period: 2025-01-01 to 2025-12-25

Strategy          Return  Trips  Win%     Final $
--------------------------------------------------
Trend Following  +24.78%    37   29.7%    $62.39
Mean Reversion   +21.35%     9   38.9%    $60.68
Voting           +15.77%    46   30.4%    $57.88
```

---

📖 **See individual module docs in the [`docs/`](docs/) folder for function-level details.**
