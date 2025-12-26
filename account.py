"""
Paper trading account with position tracking and PnL management.
Supports both SPOT and FUTURES trading modes.
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple, List

from config import (
    LIVE_MODE, MAKER_FEE, TAKER_FEE, SIMULATED_SLIPPAGE,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, MAX_TRADES_PER_DAY, COOLDOWN_MINUTES,
    FUTURES_MODE, LEVERAGE, FUTURES_MAKER_FEE, FUTURES_TAKER_FEE,
    LIQUIDATION_BUFFER_PCT, DEFAULT_FUNDING_RATE
)
from models import Side, Position, Trade, PositionSide, FuturesPosition, FundingPayment


class PaperAccount:
    """Simulated trading account with full PnL tracking (spot mode)."""
    
    def __init__(self, starting_capital: float):
        self.starting_capital = starting_capital
        self.cash_balance = starting_capital
        self.position: Optional[Position] = None
        self.realized_pnl = 0.0
        self.trades: List[Trade] = []
        self.daily_starting_equity = starting_capital
        self.last_trade_time: Optional[datetime] = None
        self.trades_today = 0
        self.current_day = datetime.now().date()
        self.consecutive_api_errors = 0
        
    def reset_daily_counters(self):
        """Reset counters at start of new trading day."""
        today = datetime.now().date()
        if today != self.current_day:
            self.current_day = today
            self.trades_today = 0
            self.daily_starting_equity = self.get_equity(self._last_price if hasattr(self, '_last_price') else 0)
    
    def get_equity(self, current_price: float) -> float:
        """Get total equity (cash + position value)."""
        self._last_price = current_price
        if self.position is None:
            return self.cash_balance
        
        position_value = self.position.qty * current_price
        if self.position.side == Side.SELL:
            unrealized = (self.position.entry_price - current_price) * self.position.qty
        else:
            unrealized = (current_price - self.position.entry_price) * self.position.qty
        
        return self.cash_balance + position_value + unrealized
    
    def get_unrealized_pnl(self, current_price: float) -> float:
        """Get unrealized PnL for open position."""
        if self.position is None:
            return 0.0
        
        if self.position.side == Side.SELL:
            return (self.position.entry_price - current_price) * self.position.qty
        else:
            return (current_price - self.position.entry_price) * self.position.qty
    
    def get_daily_drawdown(self, current_price: float) -> float:
        """Get current daily drawdown as percentage."""
        current_equity = self.get_equity(current_price)
        if self.daily_starting_equity <= 0:
            return 0.0
        return (self.daily_starting_equity - current_equity) / self.daily_starting_equity
    
    def can_trade(self) -> Tuple[bool, str]:
        """Check if trading is allowed based on cooldown and limits."""
        self.reset_daily_counters()
        
        if self.trades_today >= MAX_TRADES_PER_DAY:
            return False, f"Daily trade limit reached ({MAX_TRADES_PER_DAY})"
        
        if self.last_trade_time:
            cooldown_end = self.last_trade_time + timedelta(minutes=COOLDOWN_MINUTES)
            if datetime.now() < cooldown_end:
                remaining = (cooldown_end - datetime.now()).seconds // 60
                return False, f"Cooldown active ({remaining} min remaining)"
        
        return True, "OK"
    
    def execute_buy(self, symbol: str, price: float, qty: float, 
                    is_partial: bool = False, fill_ratio: float = 1.0) -> Trade:
        """Execute a simulated buy order."""
        executed_price = price * (1 + SIMULATED_SLIPPAGE)
        fee_rate = MAKER_FEE if not LIVE_MODE else TAKER_FEE
        fees = executed_price * qty * fee_rate
        total_cost = (executed_price * qty) + fees
        
        if total_cost > self.cash_balance:
            available = self.cash_balance / (executed_price * (1 + fee_rate))
            qty = available * 0.99
            fees = executed_price * qty * fee_rate
            total_cost = (executed_price * qty) + fees
        
        self.cash_balance -= total_cost
        
        stop_loss = executed_price * (1 - STOP_LOSS_PCT)
        take_profit = executed_price * (1 + TAKE_PROFIT_PCT)
        
        self.position = Position(
            symbol=symbol,
            qty=qty,
            entry_price=executed_price,
            side=Side.BUY,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=datetime.now()
        )
        
        trade = Trade(
            timestamp=datetime.now(),
            symbol=symbol,
            side="buy",
            qty=qty,
            price=executed_price,
            fees=fees,
            realized_pnl=0.0,
            balance_after=self.cash_balance,
            partial_fill=is_partial,
            fill_ratio=fill_ratio
        )
        
        self.trades.append(trade)
        self.last_trade_time = datetime.now()
        self.trades_today += 1
        
        return trade
    
    def execute_sell(self, symbol: str, price: float, qty: Optional[float] = None,
                     is_partial: bool = False, fill_ratio: float = 1.0) -> Optional[Trade]:
        """Execute a simulated sell order (close long position)."""
        if self.position is None:
            return None
        
        if qty is None:
            qty = self.position.qty
        
        executed_price = price * (1 - SIMULATED_SLIPPAGE)
        fee_rate = MAKER_FEE if not LIVE_MODE else TAKER_FEE
        fees = executed_price * qty * fee_rate
        
        gross_pnl = (executed_price - self.position.entry_price) * qty
        net_pnl = gross_pnl - fees
        
        proceeds = (executed_price * qty) - fees
        self.cash_balance += proceeds
        self.realized_pnl += net_pnl
        
        trade = Trade(
            timestamp=datetime.now(),
            symbol=symbol,
            side="sell",
            qty=qty,
            price=executed_price,
            fees=fees,
            realized_pnl=net_pnl,
            balance_after=self.cash_balance,
            partial_fill=is_partial,
            fill_ratio=fill_ratio
        )
        
        self.trades.append(trade)
        self.last_trade_time = datetime.now()
        
        if qty >= self.position.qty:
            self.position = None
        else:
            self.position.qty -= qty
        
        return trade


class FuturesAccount:
    """Perpetual futures trading account with margin, leverage, and liquidation tracking."""
    
    def __init__(self, starting_capital: float, leverage: int = LEVERAGE):
        self.starting_capital = starting_capital
        self.wallet_balance = starting_capital  # Total USDT in wallet
        self.available_balance = starting_capital  # Balance not used as margin
        self.leverage = min(leverage, 10)  # Cap at 10x for safety
        
        self.position: Optional[FuturesPosition] = None
        self.realized_pnl = 0.0
        self.total_funding_paid = 0.0
        self.trades: List[Trade] = []
        self.funding_payments: List[FundingPayment] = []
        
        self.daily_starting_equity = starting_capital
        self.last_trade_time: Optional[datetime] = None
        self.last_funding_time: Optional[datetime] = None
        self.trades_today = 0
        self.current_day = datetime.now().date()
        self.consecutive_api_errors = 0
    
    def get_equity(self, current_price: float) -> float:
        """Get total equity (wallet balance + unrealized PnL)."""
        if self.position is None:
            return self.wallet_balance
        
        unrealized = self.position.calculate_pnl(current_price)
        return self.wallet_balance + unrealized
    
    def get_unrealized_pnl(self, current_price: float) -> float:
        """Get unrealized PnL for open position."""
        if self.position is None:
            return 0.0
        return self.position.calculate_pnl(current_price)
    
    def get_margin_ratio(self, current_price: float) -> float:
        """Get current margin ratio (maintenance margin / equity)."""
        if self.position is None:
            return 0.0
        equity = self.get_equity(current_price)
        if equity <= 0:
            return 1.0  # 100% = liquidation
        # Maintenance margin is typically 0.5% of position value
        position_value = self.position.size * current_price
        maintenance_margin = position_value * 0.005
        return maintenance_margin / equity
    
    def calculate_liquidation_price(self, side: PositionSide, entry_price: float, 
                                     leverage: int, margin: float) -> float:
        """Calculate liquidation price for a position."""
        # Simplified formula for isolated margin
        # Liquidation happens when losses = margin
        position_value = margin * leverage
        size = position_value / entry_price
        
        if side == PositionSide.LONG:
            # Long is liquidated when price drops enough that loss = margin
            # Loss = size * (entry - liq_price) = margin
            # liq_price = entry - (margin / size)
            liq_price = entry_price * (1 - 1/leverage + 0.005)  # 0.5% maintenance
        else:
            # Short is liquidated when price rises enough
            liq_price = entry_price * (1 + 1/leverage - 0.005)
        
        return liq_price
    
    def can_trade(self) -> Tuple[bool, str]:
        """Check if trading is allowed based on cooldown and limits."""
        today = datetime.now().date()
        if today != self.current_day:
            self.current_day = today
            self.trades_today = 0
        
        if self.trades_today >= MAX_TRADES_PER_DAY:
            return False, f"Daily trade limit reached ({MAX_TRADES_PER_DAY})"
        
        if self.last_trade_time:
            from config import FUTURES_COOLDOWN_MINUTES
            if FUTURES_COOLDOWN_MINUTES > 0:
                cooldown_end = self.last_trade_time + timedelta(minutes=FUTURES_COOLDOWN_MINUTES)
                if datetime.now() < cooldown_end:
                    remaining = (cooldown_end - datetime.now()).seconds // 60
                    return False, f"Cooldown active ({remaining} min remaining)"
        
        return True, "OK"
    
    def check_liquidation(self, current_price: float) -> bool:
        """Check if position should be liquidated."""
        if self.position is None:
            return False
        return self.position.is_liquidated(current_price)
    
    def process_funding(self, current_price: float, funding_rate: float = DEFAULT_FUNDING_RATE,
                        current_time: Optional[datetime] = None) -> Optional[FundingPayment]:
        """Process funding rate payment every 8 hours."""
        if self.position is None:
            return None
        
        if current_time is None:
            current_time = datetime.now()
        
        position_value = self.position.size * current_price
        
        # Longs pay shorts when funding is positive
        if self.position.side == PositionSide.LONG:
            payment = -position_value * funding_rate  # Pay
        else:
            payment = position_value * funding_rate  # Receive
        
        self.wallet_balance += payment
        self.total_funding_paid -= payment  # Track net paid (positive = paid out)
        self.position.funding_paid -= payment
        
        funding_payment = FundingPayment(
            timestamp=current_time,
            symbol=self.position.symbol,
            position_side=self.position.side,
            position_size=self.position.size,
            funding_rate=funding_rate,
            payment=payment
        )
        self.funding_payments.append(funding_payment)
        self.last_funding_time = current_time
        
        return funding_payment
    
    def open_long(self, symbol: str, price: float, margin_amount: Optional[float] = None,
                  is_partial: bool = False, fill_ratio: float = 1.0) -> Trade:
        """Open a long position."""
        executed_price = price * (1 + SIMULATED_SLIPPAGE)
        
        # Use FIXED position size based on starting capital (no compounding!)
        # This prevents unrealistic exponential growth
        from config import MAX_POSITION_SIZE_PCT
        base_margin = self.starting_capital * MAX_POSITION_SIZE_PCT
        
        if margin_amount is None:
            margin_amount = base_margin
        
        # Cap at available balance
        margin_amount = min(margin_amount, self.available_balance * 0.95)
        
        # Calculate position size based on leverage
        position_value = margin_amount * self.leverage
        size = position_value / executed_price
        
        # Calculate fees
        fees = position_value * FUTURES_TAKER_FEE
        
        # Calculate stop loss and take profit
        stop_loss = executed_price * (1 - STOP_LOSS_PCT)
        take_profit = executed_price * (1 + TAKE_PROFIT_PCT)
        
        # Calculate liquidation price
        liq_price = self.calculate_liquidation_price(
            PositionSide.LONG, executed_price, self.leverage, margin_amount
        )
        
        # Update balances
        self.wallet_balance -= fees
        self.available_balance -= margin_amount
        
        # Create position
        self.position = FuturesPosition(
            symbol=symbol,
            side=PositionSide.LONG,
            size=size,
            entry_price=executed_price,
            leverage=self.leverage,
            margin=margin_amount,
            liquidation_price=liq_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=datetime.now()
        )
        
        trade = Trade(
            timestamp=datetime.now(),
            symbol=symbol,
            side="long",
            qty=size,
            price=executed_price,
            fees=fees,
            realized_pnl=0.0,
            balance_after=self.wallet_balance,
            partial_fill=is_partial,
            fill_ratio=fill_ratio,
            position_side=PositionSide.LONG,
            leverage=self.leverage,
            margin_used=margin_amount
        )
        
        self.trades.append(trade)
        self.last_trade_time = datetime.now()
        self.trades_today += 1
        
        return trade
    
    def open_short(self, symbol: str, price: float, margin_amount: Optional[float] = None,
                   is_partial: bool = False, fill_ratio: float = 1.0) -> Trade:
        """Open a short position."""
        executed_price = price * (1 - SIMULATED_SLIPPAGE)
        
        # Use FIXED position size based on starting capital (no compounding!)
        from config import MAX_POSITION_SIZE_PCT
        base_margin = self.starting_capital * MAX_POSITION_SIZE_PCT
        
        if margin_amount is None:
            margin_amount = base_margin
        
        # Cap at available balance
        margin_amount = min(margin_amount, self.available_balance * 0.95)
        
        position_value = margin_amount * self.leverage
        size = position_value / executed_price
        
        fees = position_value * FUTURES_TAKER_FEE
        
        # For shorts: stop loss is above entry, take profit is below
        stop_loss = executed_price * (1 + STOP_LOSS_PCT)
        take_profit = executed_price * (1 - TAKE_PROFIT_PCT)
        
        liq_price = self.calculate_liquidation_price(
            PositionSide.SHORT, executed_price, self.leverage, margin_amount
        )
        
        self.wallet_balance -= fees
        self.available_balance -= margin_amount
        
        self.position = FuturesPosition(
            symbol=symbol,
            side=PositionSide.SHORT,
            size=size,
            entry_price=executed_price,
            leverage=self.leverage,
            margin=margin_amount,
            liquidation_price=liq_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=datetime.now()
        )
        
        trade = Trade(
            timestamp=datetime.now(),
            symbol=symbol,
            side="short",
            qty=size,
            price=executed_price,
            fees=fees,
            realized_pnl=0.0,
            balance_after=self.wallet_balance,
            partial_fill=is_partial,
            fill_ratio=fill_ratio,
            position_side=PositionSide.SHORT,
            leverage=self.leverage,
            margin_used=margin_amount
        )
        
        self.trades.append(trade)
        self.last_trade_time = datetime.now()
        self.trades_today += 1
        
        return trade
    
    def close_position(self, price: float, is_liquidation: bool = False,
                       is_partial: bool = False, fill_ratio: float = 1.0) -> Optional[Trade]:
        """Close the current position."""
        if self.position is None:
            return None
        
        if self.position.side == PositionSide.LONG:
            executed_price = price * (1 - SIMULATED_SLIPPAGE)
        else:
            executed_price = price * (1 + SIMULATED_SLIPPAGE)
        
        # Calculate PnL
        pnl = self.position.calculate_pnl(executed_price)
        
        # Calculate fees
        position_value = self.position.size * executed_price
        fees = position_value * FUTURES_TAKER_FEE
        
        # Net PnL after fees
        net_pnl = pnl - fees
        
        # If liquidation, lose all margin
        if is_liquidation:
            net_pnl = -self.position.margin
        
        # Update balances
        # Note: margin was subtracted from available_balance on open (not wallet)
        # So we only add net_pnl to wallet, and restore available_balance
        self.wallet_balance += net_pnl
        self.available_balance += self.position.margin  # Restore available margin
        self.realized_pnl += net_pnl
        
        trade = Trade(
            timestamp=datetime.now(),
            symbol=self.position.symbol,
            side=f"close_{self.position.side.value}",
            qty=self.position.size,
            price=executed_price,
            fees=fees,
            realized_pnl=net_pnl,
            balance_after=self.wallet_balance,
            partial_fill=is_partial,
            fill_ratio=fill_ratio,
            position_side=self.position.side,
            leverage=self.position.leverage,
            margin_used=self.position.margin,
            is_liquidation=is_liquidation
        )
        
        self.trades.append(trade)
        self.last_trade_time = datetime.now()
        
        # Clear position
        self.position = None
        
        return trade
    
    def get_daily_drawdown(self, current_price: float) -> float:
        """Get current daily drawdown as percentage."""
        current_equity = self.get_equity(current_price)
        if self.daily_starting_equity <= 0:
            return 0.0
        return (self.daily_starting_equity - current_equity) / self.daily_starting_equity
