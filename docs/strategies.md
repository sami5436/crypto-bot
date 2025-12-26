# 📖 strategies.py

Signal generation strategies for both spot and futures trading.

---

## Classes

### `SignalGenerator`
Generates BUY/SELL signals for **spot trading** using **daily candles**.

```python
signal_gen = SignalGenerator(strategy="voting")
signal, reason = signal_gen.generate_signal(df, price, has_position=False)
```

#### Constructor
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `strategy` | `str` | `"voting"` | Strategy name |

#### Methods

| Method | Description |
|--------|-------------|
| `generate_signal(df, price, has_position)` | Generate a trading signal |
| `calculate_expected_friction(price)` | Calculate total round-trip friction |

#### Strategies

| Strategy | Logic |
|----------|-------|
| `"mean_reversion"` | Buy when oversold (BB lower + RSI < 35), sell at middle band |
| `"trend_following"` | Buy on uptrend (EMA crossover + MACD), sell on reversal |
| `"voting"` | Combines 6 buy votes, 4 sell votes; needs 4+ to trigger |

---

### `HourlySignalGenerator`
Inherits from `SignalGenerator`. Optimized for **hourly candles** with:
- Longer indicator periods (BB: 48, RSI: 24)
- Wider bands (1.2 std)
- Stricter volatility filter

---

### `FuturesSignalGenerator`
Generates LONG/SHORT signals for **futures trading**.

```python
signal_gen = FuturesSignalGenerator(strategy="voting")
signal, reason = signal_gen.generate_signal(df, price, position_side='none')
```

#### Key Difference from Spot
- Returns `Signal.LONG` or `Signal.SHORT` for entries
- Returns `Signal.CLOSE_LONG` or `Signal.CLOSE_SHORT` for exits
- Can profit in both directions

#### Methods

| Method | Description |
|--------|-------------|
| `generate_signal(df, price, position_side)` | Generate futures signal |
| `_mean_reversion_signal(...)` | Mean reversion for futures |
| `_trend_following_signal(...)` | Trend following for futures |
| `_voting_signal(...)` | Voting strategy for futures |

#### Signal Mapping

| Condition | Signal |
|-----------|--------|
| Oversold + no position | `LONG` |
| Overbought + no position | `SHORT` |
| Long position + target hit | `CLOSE_LONG` |
| Short position + target hit | `CLOSE_SHORT` |

---

## Internal Methods (all strategies)

| Method | Description |
|--------|-------------|
| `_check_volatility_filter(df, price)` | Skip trading if ATR > threshold |
| `_mean_reversion_signal(...)` | Bollinger + RSI mean reversion |
| `_trend_following_signal(...)` | EMA + MACD trend following |
| `_voting_signal(...)` | Multi-indicator voting system |
