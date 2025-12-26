# 📖 indicators.py

Technical indicator calculations using pandas.

---

## Functions

### `calculate_bollinger_bands(closes, period, std_dev)`

Calculate Bollinger Bands.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `closes` | `pd.Series` | Close prices |
| `period` | `int` | Moving average period (default: 20) |
| `std_dev` | `float` | Standard deviation multiplier (default: 2) |

**Returns:** `Tuple[pd.Series, pd.Series, pd.Series]`
- `upper` - Upper band (SMA + std_dev * STD)
- `middle` - Middle band (SMA)
- `lower` - Lower band (SMA - std_dev * STD)

---

### `calculate_rsi(closes, period)`

Calculate Relative Strength Index.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `closes` | `pd.Series` | Close prices |
| `period` | `int` | RSI period (default: 14) |

**Returns:** `pd.Series` - RSI values (0-100)
- RSI < 30 = Oversold
- RSI > 70 = Overbought

---

### `calculate_ema(closes, period)`

Calculate Exponential Moving Average.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `closes` | `pd.Series` | Close prices |
| `period` | `int` | EMA period |

**Returns:** `pd.Series` - EMA values

---

### `calculate_macd(closes, fast, slow, signal)`

Calculate MACD indicator.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `closes` | `pd.Series` | - | Close prices |
| `fast` | `int` | 12 | Fast EMA period |
| `slow` | `int` | 26 | Slow EMA period |
| `signal` | `int` | 9 | Signal line period |

**Returns:** `Tuple[pd.Series, pd.Series, pd.Series]`
- `macd_line` - MACD line (fast EMA - slow EMA)
- `signal_line` - Signal line (EMA of MACD)
- `histogram` - MACD histogram (MACD - signal)

---

### `calculate_atr(high, low, close, period)`

Calculate Average True Range (volatility).

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `high` | `pd.Series` | High prices |
| `low` | `pd.Series` | Low prices |
| `close` | `pd.Series` | Close prices |
| `period` | `int` | ATR period (default: 14) |

**Returns:** `pd.Series` - ATR values (higher = more volatile)

---

### `calculate_volume_sma(volume, period)`

Calculate Simple Moving Average of volume.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `volume` | `pd.Series` | Volume data |
| `period` | `int` | SMA period (default: 20) |

**Returns:** `pd.Series` - Volume SMA values
