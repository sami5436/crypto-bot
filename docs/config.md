# 📖 config.py

Configuration constants for the entire bot. Edit this file to customize behavior.

## Trading Mode

| Setting | Default | Description |
|---------|---------|-------------|
| `LIVE_MODE` | `False` | `True` = real trading, `False` = paper trading |
| `FUTURES_MODE` | `True` | `True` = perpetual futures, `False` = spot only |

## Capital & Symbol

| Setting | Default | Description |
|---------|---------|-------------|
| `STARTING_CAPITAL` | `50.0` | Initial USD balance |
| `SYMBOL` | `"BTC/USD"` | Trading pair for spot |
| `FUTURES_SYMBOL` | `"BTC/USDT:USDT"` | Trading pair for futures |
| `TIMEFRAME` | `"1h"` | Candle timeframe (`1h`, `1d`, `15m`, etc.) |

## Exchanges

| Setting | Default | Description |
|---------|---------|-------------|
| `SPOT_EXCHANGE` | `"kraken"` | Exchange for spot trading |
| `FUTURES_EXCHANGE` | `"bybit"` | Exchange for futures trading |
| `EXCHANGE` | (alias) | Backward compatibility alias |

## Futures Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `LEVERAGE` | `3` | Default leverage (1-10x) |
| `MARGIN_TYPE` | `"isolated"` | `"isolated"` or `"cross"` |
| `FUNDING_RATE_INTERVAL_HOURS` | `8` | Funding payment frequency |
| `DEFAULT_FUNDING_RATE` | `0.0001` | Fallback funding rate (0.01%) |

## Strategy Parameters

### Daily Candles
| Setting | Default | Description |
|---------|---------|-------------|
| `BB_PERIOD` | `20` | Bollinger Bands period |
| `BB_STD` | `1.0` | Bollinger Bands std deviation |
| `RSI_PERIOD` | `14` | RSI calculation period |
| `RSI_OVERSOLD` | `35` | RSI oversold threshold |
| `RSI_OVERBOUGHT` | `65` | RSI overbought threshold |

### Hourly Candles
| Setting | Default | Description |
|---------|---------|-------------|
| `HOURLY_BB_PERIOD` | `48` | Longer for hourly noise |
| `HOURLY_BB_STD` | `1.2` | Wider bands for hourly |
| `HOURLY_RSI_PERIOD` | `24` | Longer RSI for hourly |

## Risk Management

| Setting | Default | Description |
|---------|---------|-------------|
| `STOP_LOSS_PCT` | `0.03` | 3% stop loss |
| `TAKE_PROFIT_PCT` | `0.05` | 5% take profit |
| `MAX_POSITION_SIZE_PCT` | `0.50` | Use 50% of capital per trade |
| `MAX_TRADES_PER_DAY` | `20` | Daily trade limit |
| `COOLDOWN_MINUTES` | `240` | Minutes between trades (daily) |
| `HOURLY_COOLDOWN_MINUTES` | `60` | Minutes between trades (hourly) |

## Kill Switch

| Setting | Default | Description |
|---------|---------|-------------|
| `MAX_DAILY_DRAWDOWN_PCT` | `0.06` | 6% daily drawdown limit |
| `MAX_VOLATILITY_PCT` | `0.08` | 8% ATR volatility limit |
| `MAX_CONSECUTIVE_API_ERRORS` | `5` | API error limit before halt |

## Fee Simulation

| Setting | Default | Description |
|---------|---------|-------------|
| `MAKER_FEE` | `0.0016` | 0.16% maker fee (spot) |
| `TAKER_FEE` | `0.0026` | 0.26% taker fee (spot) |
| `FUTURES_MAKER_FEE` | `0.0001` | 0.01% maker fee (futures) |
| `FUTURES_TAKER_FEE` | `0.0006` | 0.06% taker fee (futures) |
| `SIMULATED_SLIPPAGE` | `0.0005` | 0.05% slippage simulation |
