"""
Order execution, kill switch, and trade logging.
Supports both SPOT and FUTURES trading modes.
"""

import csv
import os
import random
from typing import Optional, Tuple, Union

from config import (
    PARTIAL_FILL_PROBABILITY, MIN_FILL_RATIO, MAX_FILL_RATIO,
    SIMULATED_SPREAD, MAX_POSITION_SIZE_PCT,
    MAX_DAILY_DRAWDOWN_PCT, MAX_VOLATILITY_PCT, MAX_CONSECUTIVE_API_ERRORS,
    FUTURES_MODE, LIQUIDATION_BUFFER_PCT
)
from src.core.models import Signal, Side, Trade, KillSwitchStatus, PositionSide
from src.core.account import PaperAccount, FuturesAccount


class KillSwitch:
    """Safety mechanism to halt trading under dangerous conditions."""
    
    def __init__(self, account: Union[PaperAccount, FuturesAccount]):
        self.account = account
    
    def check(self, current_price: float, atr: float) -> KillSwitchStatus:
        """Check all kill switch conditions."""
        
        # Check daily drawdown
        drawdown = self.account.get_daily_drawdown(current_price)
        if drawdown >= MAX_DAILY_DRAWDOWN_PCT:
            return KillSwitchStatus(
                should_halt=True,
                reason=f"DRAWDOWN LIMIT: {drawdown:.2%} >= {MAX_DAILY_DRAWDOWN_PCT:.2%}"
            )
        
        # Check volatility
        volatility = atr / current_price if current_price > 0 else 0
        if volatility >= MAX_VOLATILITY_PCT:
            return KillSwitchStatus(
                should_halt=True,
                reason=f"VOLATILITY TOO HIGH: ATR={volatility:.2%} >= {MAX_VOLATILITY_PCT:.2%}"
            )
        
        # Check API errors
        if self.account.consecutive_api_errors >= MAX_CONSECUTIVE_API_ERRORS:
            return KillSwitchStatus(
                should_halt=True,
                reason=f"API ERRORS: {self.account.consecutive_api_errors} consecutive failures"
            )
        
        # Futures-specific: Check margin ratio
        if isinstance(self.account, FuturesAccount) and self.account.position:
            margin_ratio = self.account.get_margin_ratio(current_price)
            if margin_ratio >= 0.8:  # 80% margin used = danger zone
                return KillSwitchStatus(
                    should_halt=True,
                    reason=f"MARGIN DANGER: {margin_ratio:.1%} margin ratio"
                )
        
        return KillSwitchStatus(should_halt=False, reason="OK")


class OrderExecutor:
    """Simulate order execution with realistic fills (SPOT mode)."""
    
    def simulate_fill(self) -> Tuple[bool, float]:
        """Determine if order is partial fill and fill ratio."""
        is_partial = random.random() < PARTIAL_FILL_PROBABILITY
        if is_partial:
            fill_ratio = random.uniform(MIN_FILL_RATIO, MAX_FILL_RATIO)
        else:
            fill_ratio = 1.0
        return is_partial, fill_ratio
    
    def execute(self, account: PaperAccount, signal: Signal, 
                symbol: str, price: float) -> Optional[Trade]:
        """Execute order based on signal (spot mode)."""
        
        if signal == Signal.BUY:
            available = account.cash_balance * MAX_POSITION_SIZE_PCT
            ask_price = price * (1 + SIMULATED_SPREAD / 2)
            qty = available / ask_price
            
            is_partial, fill_ratio = self.simulate_fill()
            actual_qty = qty * fill_ratio
            
            if actual_qty * ask_price < 1.0:
                return None
            
            return account.execute_buy(
                symbol=symbol,
                price=ask_price,
                qty=actual_qty,
                is_partial=is_partial,
                fill_ratio=fill_ratio
            )
        
        elif signal == Signal.SELL and account.position is not None:
            bid_price = price * (1 - SIMULATED_SPREAD / 2)
            is_partial, fill_ratio = self.simulate_fill()
            actual_qty = account.position.qty * fill_ratio
            
            return account.execute_sell(
                symbol=symbol,
                price=bid_price,
                qty=actual_qty,
                is_partial=is_partial,
                fill_ratio=fill_ratio
            )
        
        return None


class FuturesOrderExecutor:
    """Execute orders for perpetual futures with longs and shorts."""
    
    def simulate_fill(self) -> Tuple[bool, float]:
        """Determine if order is partial fill and fill ratio."""
        is_partial = random.random() < PARTIAL_FILL_PROBABILITY
        if is_partial:
            fill_ratio = random.uniform(MIN_FILL_RATIO, MAX_FILL_RATIO)
        else:
            fill_ratio = 1.0
        return is_partial, fill_ratio
    
    def execute(self, account: FuturesAccount, signal: Signal,
                symbol: str, price: float) -> Optional[Trade]:
        """Execute futures order based on signal."""
        
        is_partial, fill_ratio = self.simulate_fill()
        
        # Open LONG position
        if signal == Signal.LONG:
            if account.position is not None:
                return None  # Already in a position
            
            return account.open_long(
                symbol=symbol,
                price=price,
                is_partial=is_partial,
                fill_ratio=fill_ratio
            )
        
        # Open SHORT position
        elif signal == Signal.SHORT:
            if account.position is not None:
                return None  # Already in a position
            
            return account.open_short(
                symbol=symbol,
                price=price,
                is_partial=is_partial,
                fill_ratio=fill_ratio
            )
        
        # Close LONG position
        elif signal == Signal.CLOSE_LONG:
            if account.position is None or account.position.side != PositionSide.LONG:
                return None
            
            return account.close_position(
                price=price,
                is_partial=is_partial,
                fill_ratio=fill_ratio
            )
        
        # Close SHORT position
        elif signal == Signal.CLOSE_SHORT:
            if account.position is None or account.position.side != PositionSide.SHORT:
                return None
            
            return account.close_position(
                price=price,
                is_partial=is_partial,
                fill_ratio=fill_ratio
            )
        
        # Handle legacy BUY/SELL signals
        elif signal == Signal.BUY:
            if account.position is not None:
                return None
            return account.open_long(
                symbol=symbol,
                price=price,
                is_partial=is_partial,
                fill_ratio=fill_ratio
            )
        
        elif signal == Signal.SELL:
            if account.position is None:
                return None
            return account.close_position(
                price=price,
                is_partial=is_partial,
                fill_ratio=fill_ratio
            )
        
        return None


class TradeLogger:
    """Log trades to CSV file."""
    
    def __init__(self, filename: str):
        self.filename = filename
        self._init_csv()
    
    def _init_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'symbol', 'side', 'qty', 'price', 
                    'fees', 'realized_pnl', 'balance_after', 
                    'partial_fill', 'fill_ratio', 'leverage', 'margin_used'
                ])
    
    def log_trade(self, trade: Trade):
        """Append trade to CSV log."""
        with open(self.filename, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                trade.timestamp.isoformat(),
                trade.symbol,
                trade.side,
                f"{trade.qty:.8f}",
                f"{trade.price:.2f}",
                f"{trade.fees:.4f}",
                f"{trade.realized_pnl:.4f}",
                f"{trade.balance_after:.2f}",
                trade.partial_fill,
                f"{trade.fill_ratio:.2f}",
                trade.leverage,
                f"{trade.margin_used:.2f}"
            ])


def check_stop_loss_take_profit(account: Union[PaperAccount, FuturesAccount], 
                                 current_price: float) -> Optional[Signal]:
    """Check if stop loss or take profit is triggered."""
    if account.position is None:
        return None
    
    pos = account.position
    
    # Handle spot account
    if isinstance(account, PaperAccount):
        if pos.side == Side.BUY:
            if current_price <= pos.stop_loss:
                return Signal.SELL
            if current_price >= pos.take_profit:
                return Signal.SELL
    
    # Handle futures account
    elif isinstance(account, FuturesAccount):
        if pos.side == PositionSide.LONG:
            if current_price <= pos.stop_loss:
                return Signal.CLOSE_LONG
            if current_price >= pos.take_profit:
                return Signal.CLOSE_LONG
        elif pos.side == PositionSide.SHORT:
            if current_price >= pos.stop_loss:
                return Signal.CLOSE_SHORT
            if current_price <= pos.take_profit:
                return Signal.CLOSE_SHORT
    
    return None


def check_futures_liquidation(account: FuturesAccount, current_price: float) -> Optional[Signal]:
    """Check if futures position should be liquidated."""
    if account.position is None:
        return None
    
    if account.check_liquidation(current_price):
        if account.position.side == PositionSide.LONG:
            return Signal.CLOSE_LONG
        else:
            return Signal.CLOSE_SHORT
    
    return None
