# 📖 executor.py

> **The doer — executes trades, enforces safety rules, and logs everything.**

When the strategy says "BUY", this file actually does it (simulated). It also contains the kill switch that stops trading when things go wrong.

---

## 🎯 What This File Does

- **Execute orders**: Turn signals into trades
- **Simulate reality**: Add fees, slippage, partial fills
- **Safety checks**: Kill switch for emergencies
- **Logging**: Record every trade to CSV

---

## 📦 Classes

### `KillSwitch`
**Purpose:** Emergency stop when things go wrong

The kill switch monitors for dangerous conditions and halts trading:

| Check | Threshold | What Triggers It |
|-------|-----------|------------------|
| Daily Drawdown | 10% | Lost too much today |
| Volatility | 8% ATR | Market too choppy |
| API Errors | 3 consecutive | Exchange connection issues |
| Margin Ratio | 80% | (Futures) Near liquidation |

```python
kill_switch = KillSwitch(account)
status = kill_switch.check(current_price, atr)
if status.should_halt:
    print(f"HALTED: {status.reason}")
```

---

### `OrderExecutor`
**Purpose:** Execute spot trades (BUY/SELL)

```python
executor = OrderExecutor()
trade = executor.execute(account, Signal.BUY, "BTC/USD", 88000.0)
```

**Simulates:**
- Slippage (you get a slightly worse price)
- Fees (deducted from balance)
- Partial fills (30% chance of only partial fill)

---

### `FuturesOrderExecutor`
**Purpose:** Execute futures trades (LONG/SHORT/CLOSE)

```python
executor = FuturesOrderExecutor()
trade = executor.execute(account, Signal.LONG, "BTC/USD", 88000.0)
```

**Handles:**
- Opening LONG positions
- Opening SHORT positions
- Closing positions (with realized P&L)

---

### `TradeLogger`
**Purpose:** Log every trade to CSV

```python
logger = TradeLogger("futures_trades.csv")
logger.log_trade(trade)
```

**Logged fields:**
- timestamp, symbol, side, qty, price
- fees, realized_pnl, balance_after
- leverage, margin_used

---

## 🔧 Helper Functions

### `check_stop_loss_take_profit(account, price)`
Checks if the current position has hit its stop loss or take profit level.

```python
signal = check_stop_loss_take_profit(account, current_price)
if signal:
    # Will return SELL (spot) or CLOSE_LONG/CLOSE_SHORT (futures)
```

---

### `check_futures_liquidation(account, price)`
Checks if a futures position would be liquidated at the current price.

```python
signal = check_futures_liquidation(account, current_price)
if signal:
    print(" LIQUIDATION TRIGGERED")
```

---

## 🛡️ Safety Features

1. **Kill Switch**: Automatic halt on drawdown/volatility
2. **Stop Loss**: Every position has a stop loss price
3. **Take Profit**: Every position has a target price
4. **Liquidation Check**: Prevent total loss on futures

---

##  Why Simulate Fees and Slippage?

Real trading has friction:
- **Fees**: Exchanges charge 0.1-0.3% per trade
- **Slippage**: Large orders move the price against you

By simulating these, backtests are more realistic. A strategy that looks amazing without fees might be unprofitable with them.
