# 📖 indicators.py

> **The math — calculates technical indicators from price data.**

Technical analysis uses math formulas on price history to predict future moves. This file implements those formulas.

---

## 🎯 What This File Does

Takes raw price data (OHLCV) and calculates:
- **RSI** (Relative Strength Index) — Is it overbought or oversold?
- **Bollinger Bands** — Is price at the extremes?
- **MACD** — Is momentum shifting?
- **ATR** (Average True Range) — How volatile is the market?
- **EMA** (Exponential Moving Average) — Trend direction

All strategies use these indicators to make decisions.

---

## 📊 Functions

### `calculate_rsi(closes, period=14)`
**What it measures:** Momentum — is something overbought or oversold?

| RSI Value | Meaning |
|-----------|---------|
| < 30 | Oversold (might bounce up) |
| 30-70 | Normal range |
| > 70 | Overbought (might drop) |

```python
rsi = calculate_rsi(df['close'], period=14)
print(rsi.iloc[-1])  # Current RSI value
```

---

### `calculate_bollinger_bands(closes, period=20, std_dev=2)`
**What it measures:** Volatility bands around the average price.

Returns: `(upper, middle, lower)`

| Condition | Meaning |
|-----------|---------|
| Price < Lower band | Unusually low, might bounce |
| Price > Upper band | Unusually high, might drop |
| Price near Middle | Normal |

```python
upper, middle, lower = calculate_bollinger_bands(df['close'])
```

---

### `calculate_macd(closes, fast=12, slow=26, signal=9)`
**What it measures:** Momentum and trend changes.

Returns: `(macd_line, signal_line, histogram)`

| Condition | Meaning |
|-----------|---------|
| MACD crosses above Signal | Bullish (go long) |
| MACD crosses below Signal | Bearish (go short) |
| Histogram growing | Momentum increasing |

---

### `calculate_ema(closes, period)`
**What it measures:** Smoothed average that weighs recent prices more.

```python
ema_9 = calculate_ema(df['close'], 9)
ema_21 = calculate_ema(df['close'], 21)
if ema_9.iloc[-1] > ema_21.iloc[-1]:
    print("Uptrend")
```

---

### `calculate_atr(high, low, close, period=14)`
**What it measures:** Volatility — how much does price move?

| ATR | Meaning |
|-----|---------|
| High | Market is volatile, bigger moves |
| Low | Market is calm, smaller moves |

Used by the kill switch to halt trading when markets are too volatile.

---

## 💡 How Strategies Use These

```
Mean Reversion:
  → RSI < 25 AND Price < Lower BB → BUY

Trend Following:
  → EMA-9 crosses above EMA-21 AND MACD > Signal → BUY

Voting:
  → Checks all of the above, counts votes
```
