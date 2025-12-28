"""
Data models (enums and dataclasses) for the trading bot.
Supports both SPOT and FUTURES trading modes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(Enum):
    """Order side for spot trading."""
    BUY = "buy"
    SELL = "sell"


class PositionSide(Enum):
    """Position side for futures trading."""
    LONG = "long"
    SHORT = "short"
    NONE = "none"


class Signal(Enum):
    """Trading signal - supports both spot and futures."""
    NONE = "none"
    # Spot signals
    BUY = "buy"
    SELL = "sell"
    # Futures signals
    LONG = "long"  # Open long position
    SHORT = "short"  # Open short position
    CLOSE_LONG = "close_long"  # Close long position
    CLOSE_SHORT = "close_short"  # Close short position


@dataclass
class Position:
    """Represents an open position (spot or futures)."""
    symbol: str
    qty: float
    entry_price: float
    side: Side  # For spot
    stop_loss: float
    take_profit: float
    entry_time: datetime
    # Futures-specific fields
    position_side: PositionSide = PositionSide.NONE
    leverage: int = 1
    margin: float = 0.0  # Collateral used
    liquidation_price: float = 0.0
    unrealized_pnl: float = 0.0
    funding_paid: float = 0.0  # Total funding paid/received


@dataclass
class FuturesPosition:
    """Represents a perpetual futures position."""
    symbol: str
    side: PositionSide
    size: float  # Contract size in base currency (e.g., 0.1 BTC)
    entry_price: float
    leverage: int
    margin: float  # Initial margin (collateral)
    liquidation_price: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    unrealized_pnl: float = 0.0
    funding_paid: float = 0.0
    
    def calculate_pnl(self, current_price: float) -> float:
        """Calculate unrealized PnL based on current price."""
        if self.side == PositionSide.LONG:
            return self.size * (current_price - self.entry_price)
        else:  # SHORT
            return self.size * (self.entry_price - current_price)
    
    def calculate_roe(self, current_price: float) -> float:
        """Calculate Return on Equity (leveraged return)."""
        pnl = self.calculate_pnl(current_price)
        if self.margin == 0:
            return 0.0
        return pnl / self.margin
    
    def is_liquidated(self, current_price: float) -> bool:
        """Check if position would be liquidated at current price."""
        if self.side == PositionSide.LONG:
            return current_price <= self.liquidation_price
        else:  # SHORT
            return current_price >= self.liquidation_price


@dataclass
class Trade:
    """Represents an executed trade."""
    timestamp: datetime
    symbol: str
    side: str
    qty: float
    price: float
    fees: float
    realized_pnl: float
    balance_after: float
    partial_fill: bool
    fill_ratio: float
    # Futures-specific fields
    position_side: PositionSide = PositionSide.NONE
    leverage: int = 1
    margin_used: float = 0.0
    is_liquidation: bool = False


@dataclass
class KillSwitchStatus:
    """Status returned by kill switch check."""
    should_halt: bool
    reason: str


@dataclass
class FundingPayment:
    """Record of a funding rate payment."""
    timestamp: datetime
    symbol: str
    position_side: PositionSide
    position_size: float
    funding_rate: float
    payment: float  # Positive = received, Negative = paid
