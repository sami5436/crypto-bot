# 📖 models.py

> **The blueprints — defines the data structures used throughout the bot.**

This file contains **enums** (like Signal.BUY) and **dataclasses** (like Position, Trade) that represent concepts in trading.

---

## 🎯 What This File Does

Every trade, position, and signal needs a structured representation. This file defines:
- **Enums**: Named constants like `Signal.LONG`, `Side.BUY`
- **Dataclasses**: Structured data like `Position`, `Trade`, `FuturesPosition`

Think of these as the "vocabulary" the bot uses to talk about trades.

---

## 📊 Enums

### `Side`
Which direction is a spot order?
```python
Side.BUY   # Buying crypto
Side.SELL  # Selling crypto
```

### `PositionSide`
What direction is a futures position?
```python
PositionSide.LONG   # Betting price goes UP
PositionSide.SHORT  # Betting price goes DOWN
PositionSide.NONE   # No position
```

### `Signal`
What should the bot do right now?
```python
Signal.NONE         # Do nothing
Signal.BUY          # Open spot buy
Signal.SELL         # Close spot position
Signal.LONG         # Open futures long
Signal.SHORT        # Open futures short
Signal.CLOSE_LONG   # Close futures long
Signal.CLOSE_SHORT  # Close futures short
```

---

## 📦 Dataclasses

### `Position` (Spot)
Represents a spot position (you bought and are holding crypto).

| Field | Meaning |
|-------|---------|
| `symbol` | "BTC/USD" |
| `qty` | 0.001 BTC |
| `entry_price` | $88,000 |
| `stop_loss` | $85,000 |
| `take_profit` | $92,000 |

---

### `FuturesPosition`
Represents a leveraged futures position.

| Field | Meaning |
|-------|---------|
| `side` | LONG or SHORT |
| `size` | Position size in BTC |
| `entry_price` | $88,000 |
| `leverage` | 3x |
| `margin` | $42.50 (collateral) |
| `liquidation_price` | $59,000 |

**Methods:**
- `calculate_pnl(price)` → Current profit/loss
- `calculate_roe(price)` → Return on equity (leveraged return)
- `is_liquidated(price)` → Would this price liquidate you?

---

### `Trade`
Represents an executed trade (what actually happened).

| Field | Meaning |
|-------|---------|
| `timestamp` | When it happened |
| `side` | "long", "short", "close_long", etc. |
| `qty` | Amount traded |
| `price` | Execution price |
| `fees` | Fees paid |
| `realized_pnl` | Profit/loss realized |
| `leverage` | Leverage used |

---

### `KillSwitchStatus`
Result of a kill switch check.

```python
status = KillSwitchStatus(should_halt=True, reason="Daily drawdown exceeded")
if status.should_halt:
    print(f"HALTED: {status.reason}")
```

---

### `FundingPayment`
Records a funding rate payment (futures exchanges charge/pay every 8 hours).

| Field | Meaning |
|-------|---------|
| `payment` | Amount paid (negative) or received (positive) |
| `funding_rate` | The rate applied (e.g., 0.01%) |
