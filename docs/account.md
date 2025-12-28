# 📖 account.py

> **The wallet — tracks your balance, positions, P&L, and enforces trading rules.**

This file manages all the "money" stuff. It knows how much fake cash you have, what positions you're holding, and whether you're allowed to trade right now.

---

## 🎯 What This File Does

Think of this as a simulated brokerage account:

- Track **cash balance** and **equity**
- Store **open positions** (what you're holding)
- Calculate **unrealized P&L** (paper gains/losses)
- Enforce **trading rules** (cooldown, daily limits)
- For futures: manage **margin**, **leverage**, and **liquidation**

---

## 📦 Classes

### `PaperAccount`
**Purpose:** Simulated spot trading account (buy/hold/sell)

```python
account = PaperAccount(starting_capital=10000.0)
print(account.cash_balance)  # 10000.0
print(account.position)      # None (no open position)
```

**What it tracks:**
- Cash balance (your USD)
- Current position (if any)
- Realized P&L (locked in profits/losses)
- Trade history
- Trades today (for daily limits)

---

### `FuturesAccount`
**Purpose:** Simulated futures account with margin and leverage

```python
account = FuturesAccount(starting_capital=50.0, leverage=3)
```

**Additional features over spot:**
- **Margin tracking**: How much collateral is locked
- **Leverage**: 1-10x multiplier on positions
- **Liquidation price**: Where you'd get wiped out
- **Funding payments**: Simulated (futures pay/receive funding every 8 hours)

---

## 🔧 Key Methods

### For Both Account Types

| Method | What It Returns |
|--------|-----------------|
| `get_equity(price)` | Total value: cash + position value |
| `get_unrealized_pnl(price)` | Paper profit/loss on open position |
| `can_trade()` | `(True, "OK")` or `(False, "Cooldown active")` |

---

### FuturesAccount Specific

| Method | What It Does |
|--------|--------------|
| `open_long(symbol, price)` | Open a LONG position |
| `open_short(symbol, price)` | Open a SHORT position |
| `close_position(price)` | Close the current position |
| `check_liquidation(price)` | Returns True if position would be liquidated |
| `calculate_liquidation_price(...)` | Calculate where liquidation would occur |

---

##  Position Sizing

**How much of your balance is used per trade?**

Set by `MAX_POSITION_SIZE_PCT` in config (default: 85%)

```python
# With $50 starting capital and 85% position size:
margin_used = 50 * 0.85 = $42.50 per trade
```

**Important:** The bot uses **fixed sizing** based on starting capital, NOT current balance. This prevents compounding bugs where tiny gains become astronomical.

---

## ️ Trading Rules Enforced

| Rule | Config Setting | Effect |
|------|----------------|--------|
| Max trades per day | `MAX_TRADES_PER_DAY = 20` | Prevents overtrading |
| Cooldown after trade | `FUTURES_COOLDOWN_MINUTES = 0` | (Disabled for futures) |
| Daily drawdown limit | `MAX_DAILY_DRAWDOWN_PCT = 10%` | Kill switch triggers |

---

##  Balance Flow Example (Futures)

```
Starting: $50.00 wallet, $50.00 available

1. OPEN LONG ($42.50 margin):
   - Wallet: $50.00 - $0.07 fees = $49.93
   - Available: $50.00 - $42.50 = $7.50
   - Position: 0.00048 BTC @ $88,000

2. PRICE RISES to $89,000:
   - Unrealized PnL: $0.48
   - Equity: $49.93 + $0.48 = $50.41

3. CLOSE POSITION:
   - Net PnL: $0.48 - $0.07 fees = $0.41
   - Wallet: $49.93 + $0.41 = $50.34
   - Available: $50.34 (all available again)
```

---

##  Why Separate Accounts?

- **PaperAccount** is simpler — just tracks buy/sell with no leverage
- **FuturesAccount** has complex margin math, liquidation, funding rates

Both inherit common patterns but futures has the extra complexity needed for leveraged trading.
