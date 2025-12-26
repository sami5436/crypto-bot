# 📖 executor.py

Order execution, kill switch, and trade logging.

---

## Classes

### `KillSwitch`
Safety mechanism to halt trading under dangerous conditions.

```python
kill_switch = KillSwitch(account)
status = kill_switch.check(current_price, atr)
if status.should_halt:
    print(status.reason)
```

#### Checks

| Check | Threshold | Description |
|-------|-----------|-------------|
| Daily Drawdown | 6% | Equity dropped too much today |
| Volatility | 8% | ATR too high (market too volatile) |
| API Errors | 5 consecutive | Too many exchange errors |
| Margin Ratio | 80% | (Futures) Near liquidation |

---

### `OrderExecutor`
Simulates spot order execution.

```python
executor = OrderExecutor()
trade = executor.execute(account, signal, symbol, price)
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `simulate_fill()` | `(bool, float)` | Simulate partial fills |
| `execute(account, signal, symbol, price)` | `Trade` | Execute order |

#### Features
- Simulates slippage (worse price)
- Simulates partial fills (random chance)
- Handles BUY and SELL signals

---

### `FuturesOrderExecutor`
Executes futures orders with longs and shorts.

```python
executor = FuturesOrderExecutor()
trade = executor.execute(account, signal, symbol, price)
```

#### Supported Signals

| Signal | Action |
|--------|--------|
| `LONG` | Open long position |
| `SHORT` | Open short position |
| `CLOSE_LONG` | Close long position |
| `CLOSE_SHORT` | Close short position |
| `BUY` | (Legacy) Opens long |
| `SELL` | (Legacy) Closes position |

---

### `TradeLogger`
Logs all trades to CSV file.

```python
logger = TradeLogger("trades.csv")
logger.log_trade(trade)
```

#### CSV Columns
- timestamp, symbol, side, qty, price
- fees, realized_pnl, balance_after
- partial_fill, fill_ratio
- leverage, margin_used

---

## Helper Functions

### `check_stop_loss_take_profit(account, price)`
Check if SL/TP is triggered.

**Returns:** `Signal` or `None`
- For spot: returns `SELL` if triggered
- For futures: returns `CLOSE_LONG` or `CLOSE_SHORT`

---

### `check_futures_liquidation(account, price)`
Check if futures position should be liquidated.

**Returns:** `Signal` or `None`
- Returns `CLOSE_LONG` or `CLOSE_SHORT` if liquidated
