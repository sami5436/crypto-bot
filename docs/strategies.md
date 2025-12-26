# 📖 strategies.py

> **The decision maker — contains all the logic for WHEN to buy, sell, go long, or go short.**

This is where the trading "brain" lives. Given price data, these classes analyze indicators and decide what action to take.

---

## 🎯 What This File Does

The bot doesn't buy/sell randomly — it uses **strategies**. Each strategy has specific rules:

| Strategy | Core Idea |
|----------|-----------|
| **Mean Reversion** | "Prices return to average" — buy when price drops too low, sell when it recovers |
| **Trend Following** | "Ride the wave" — buy when uptrend starts, sell when it reverses |
| **Voting** | "Committee decision" — check 6 indicators, trade when 4+ agree |

---

## 🧠 How Signals Work

### For Spot Trading (buy/sell only):
```
Signal.BUY  → Open a position (buy crypto)
Signal.SELL → Close position (sell crypto)
Signal.NONE → Do nothing
```

### For Futures Trading (longs + shorts):
```
Signal.LONG        → Open long position (bet price goes UP)
Signal.SHORT       → Open short position (bet price goes DOWN)
Signal.CLOSE_LONG  → Close long position
Signal.CLOSE_SHORT → Close short position
Signal.NONE        → Do nothing
```

---

## 📦 Classes

### `SignalGenerator`
**Purpose:** Generate BUY/SELL signals for spot trading

```python
gen = SignalGenerator(strategy="voting")
signal, reason = gen.generate_signal(df, price, has_position=False)
# Returns: (Signal.BUY, "VOTING: 4/6 buy votes")
```

---

### `HourlySignalGenerator`
**Purpose:** Optimized for hourly candles (uses longer indicator periods)

Same as SignalGenerator but with settings tuned for hourly data:
- Bollinger Bands: 48 periods (instead of 20)
- RSI: 24 periods (instead of 14)
- Wider bands to filter noise

---

### `FuturesSignalGenerator`
**Purpose:** Generate LONG/SHORT signals for futures trading

```python
gen = FuturesSignalGenerator(strategy="voting")
signal, reason = gen.generate_signal(df, price, position_side='none')
# Returns: (Signal.LONG, "VOTING: 3 long votes") when no position
# Returns: (Signal.CLOSE_LONG, "Price recovered to mean") when holding long
```

---

## 🔧 Strategy Details

### Mean Reversion
**Theory:** Prices always return to the mean. Buy when too low, sell when back to normal.

| Condition | Signal |
|-----------|--------|
| Price < Lower BB AND RSI < 35 | BUY / LONG |
| Price > Middle BB | SELL / CLOSE |
| Price > Upper BB AND RSI > 65 | SHORT |

---

### Trend Following
**Theory:** Trends persist. Jump on a trend and ride it.

| Condition | Signal |
|-----------|--------|
| EMA-9 crosses above EMA-21 AND MACD > Signal | BUY / LONG |
| EMA-9 crosses below EMA-21 AND MACD < Signal | SELL / SHORT |

---

### Voting
**Theory:** Multiple indicators are better than one.

Checks these indicators:
1. RSI oversold/overbought
2. Price vs Bollinger Bands
3. MACD crossover
4. EMA crossover
5. Volume spike
6. Price momentum

**Action:** Trade when 4+ votes agree on direction.

---

## 💡 Important Notes

- All strategies have a **volatility filter** — won't trade if ATR > threshold (too choppy)
- Strategies return a **reason string** explaining why they made the decision
- The 0.5% threshold (preventing rapid closes) is applied in `bots.py`, not here
