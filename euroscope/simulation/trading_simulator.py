"""
Trading Simulation Engine

Provides real-time paper trading simulation using BiQuote data.
Simulates trade execution, tracking, and performance reporting.
"""

import asyncio
import logging
import threading
from datetime import datetime, UTC
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass, field
from enum import Enum
from ..trading.execution_simulator import ExecutionSimulator

logger = logging.getLogger("euroscope.simulation")


class TradeDirection(Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(Enum):
    OPEN = "OPEN"
    CLOSED_WIN = "CLOSED_WIN"
    CLOSED_LOSS = "CLOSED_LOSS"
    CLOSED_BREAK_EVEN = "CLOSED_BREAK_EVEN"


@dataclass
class Trade:
    """Represents a single trade."""
    id: int
    direction: TradeDirection
    entry_price: float
    stop_loss: float
    take_profit: float
    units: float = 10000  # 0.1 lot
    entry_cost_pips: float = 0.0
    exit_cost_pips: float = 0.0
    entry_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    close_time: Optional[datetime] = None
    close_price: Optional[float] = None
    status: TradeStatus = TradeStatus.OPEN
    pnl: float = 0.0
    
    def _execution_cost(self) -> float:
        """Convert pip costs to dollar equivalent."""
        return (self.entry_cost_pips + self.exit_cost_pips) * self.units * 0.0001
    
    def update_pnl(self, current_price: float):
        """Update PnL based on current price and execution costs."""
        if self.direction == TradeDirection.BUY:
            self.pnl = (current_price - self.entry_price) * self.units - self._execution_cost()
        else:
            self.pnl = (self.entry_price - current_price) * self.units - self._execution_cost()
    
    def check_exit(self, current_price: float) -> bool:
        """Check if trade should be closed (SL/TP hit). Returns True if exit triggered."""
        if self.direction == TradeDirection.BUY:
            if current_price <= self.stop_loss:
                return True
            if current_price >= self.take_profit:
                return True
        else:
            if current_price >= self.stop_loss:
                return True
            if current_price <= self.take_profit:
                return True
        return False
    
    def exit_reason(self, current_price: float) -> Optional[str]:
        """Determine exit reason without closing the trade."""
        if self.direction == TradeDirection.BUY:
            if current_price <= self.stop_loss:
                return "stop_loss"
            if current_price >= self.take_profit:
                return "take_profit"
        else:
            if current_price >= self.stop_loss:
                return "stop_loss"
            if current_price <= self.take_profit:
                return "take_profit"
        return None
    
    def close(self, close_price: float, status: TradeStatus):
        """Close the trade."""
        self.close_price = close_price
        self.close_time = datetime.now(UTC)
        self.status = status
        self.update_pnl(close_price)


class TradingSimulator:
    """
    Real-time trading simulator using BiQuote data.
    
    Features:
    - Live price feed
    - Paper trade execution
    - Automatic SL/TP management
    - Performance tracking
    """
    
    def __init__(self, initial_balance: float = 100000.0,
                 execution_simulator: Optional[ExecutionSimulator] = None,
                 minimum_balance: float = 0.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.minimum_balance = minimum_balance
        self.is_bankrupt = False
        self.open_trades: List[Trade] = []
        self.closed_trades: List[Trade] = []
        self.trade_counter = 0
        self.is_running = False
        self.execution_simulator = execution_simulator
        
        # Callbacks
        self.on_price_update: Optional[Callable] = None
        self.on_trade_opened: Optional[Callable] = None
        self.on_trade_closed: Optional[Callable] = None
        self.on_bankruptcy: Optional[Callable] = None
        
        # Data provider
        self._provider = None
        self._lock = threading.Lock()
    
    def set_provider(self, provider):
        """Set the data provider (BiQuoteProvider or MultiSourceProvider)."""
        self._provider = provider
    
    def _generate_trade_id(self) -> int:
        """Generate unique trade ID."""
        self.trade_counter += 1
        return self.trade_counter
    
    def open_trade(self, direction: TradeDirection, entry_price: float,
                   stop_loss: float, take_profit: float, units: float = 10000) -> Trade:
        """Open a new trade."""
        if self.is_bankrupt:
            raise RuntimeError(f"Cannot open trade: bankrupt (balance={self.current_balance:.2f})")
        if direction not in (TradeDirection.BUY, TradeDirection.SELL):
            raise ValueError(f"Invalid direction: {direction}")
        if entry_price <= 0:
            raise ValueError(f"entry_price must be > 0, got {entry_price}")
        if stop_loss <= 0:
            raise ValueError(f"stop_loss must be > 0, got {stop_loss}")
        if take_profit <= 0:
            raise ValueError(f"take_profit must be > 0, got {take_profit}")
        if units <= 0:
            raise ValueError(f"units must be > 0, got {units}")
        if direction == TradeDirection.BUY:
            if not (stop_loss < entry_price < take_profit):
                raise ValueError(
                    f"For BUY: stop_loss ({stop_loss}) < entry_price ({entry_price}) < take_profit ({take_profit})"
                )
        else:
            if not (stop_loss > entry_price > take_profit):
                raise ValueError(
                    f"For SELL: stop_loss ({stop_loss}) > entry_price ({entry_price}) > take_profit ({take_profit})"
                )

        # Apply execution simulation on entry
        entry_cost_pips = 0.0
        if self.execution_simulator and self.execution_simulator.config.enabled:
            result = self.execution_simulator.simulate_entry(direction.value, entry_price)
            if not result.filled:
                logger.warning(f"Entry REJECTED: {direction.value} @ {entry_price} (simulated)")
                raise RuntimeError(f"Entry not filled: {direction.value} @ {entry_price}")
            entry_cost_pips = result.total_cost_pips

        with self._lock:
            trade = Trade(
                id=self._generate_trade_id(),
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                units=units,
                entry_cost_pips=entry_cost_pips,
            )
            
            self.open_trades.append(trade)
        
        logger.info(f"Trade opened: {direction.value} @ {entry_price}, SL: {stop_loss}, TP: {take_profit}, entry_cost={entry_cost_pips:.1f}pips")
        
        if self.on_trade_opened:
            self.on_trade_opened(trade)
        
        return trade
    
    def update_trades(self, current_price: float):
        """Update all open trades with current price."""
        trades_to_close = []
        
        with self._lock:
            for trade in self.open_trades:
                trade.update_pnl(current_price)
                if trade.check_exit(current_price):
                    trades_to_close.append(trade)
            
            for trade in trades_to_close:
                self.open_trades.remove(trade)
                
                reason = trade.exit_reason(current_price) or "manual"
                is_loss = reason == "stop_loss"
                exit_status = TradeStatus.CLOSED_LOSS if is_loss else TradeStatus.CLOSED_WIN
                
                # Apply execution simulation on exit
                if self.execution_simulator and self.execution_simulator.config.enabled:
                    result = self.execution_simulator.simulate_exit(
                        trade.direction.value, current_price, reason
                    )
                    if result.filled:
                        trade.exit_cost_pips = result.total_cost_pips
                        trade.close(result.fill_price, exit_status)
                    else:
                        logger.warning(f"Exit NOT filled for trade {trade.id}, using raw price")
                        trade.close(current_price, exit_status)
                else:
                    trade.close(current_price, exit_status)
                
                self.closed_trades.append(trade)
                self.current_balance += trade.pnl
                
                if self.on_trade_closed:
                    self.on_trade_closed(trade)
            
            if self.current_balance <= self.minimum_balance:
                self.is_bankrupt = True
                self.is_running = False
                if self.on_bankruptcy:
                    self.on_bankruptcy(self.current_balance)
        
        for trade in trades_to_close:
            logger.info(f"Trade closed: {trade.status.value}, PnL: {trade.pnl:.2f}, exit_cost={trade.exit_cost_pips:.1f}pips")
        
        if self.is_bankrupt:
            logger.warning(
                f"BANKRUPTCY: balance {self.current_balance:.2f} <= minimum {self.minimum_balance:.2f}. "
                f"Simulation stopped."
            )
    
    def get_status(self) -> Dict:
        """Get current simulation status."""
        with self._lock:
            total_pnl = sum(t.pnl for t in self.closed_trades)
            unrealized_pnl = sum(t.pnl for t in self.open_trades)
            winning_trades = len([t for t in self.closed_trades if t.pnl > 0])
            losing_trades = len([t for t in self.closed_trades if t.pnl < 0])
            total_closed = len(self.closed_trades)
            win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0
        
        return {
            "balance": round(self.current_balance, 2),
            "initial_balance": self.initial_balance,
            "total_pnl": round(total_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "equity": round(self.current_balance + unrealized_pnl, 2),
            "open_trades": len(self.open_trades),
            "closed_trades": total_closed,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 1),
            "is_bankrupt": self.is_bankrupt,
            "trades": [self._trade_to_dict(t) for t in self.open_trades + self.closed_trades]
        }
    
    def _trade_to_dict(self, trade: Trade) -> Dict:
        """Convert trade to dictionary."""
        return {
            "id": trade.id,
            "direction": trade.direction.value,
            "entry_price": trade.entry_price,
            "current_price": trade.close_price or trade.entry_price,
            "stop_loss": trade.stop_loss,
            "take_profit": trade.take_profit,
            "pnl": round(trade.pnl, 2),
            "status": trade.status.value,
            "entry_time": trade.entry_time.isoformat(),
            "close_time": trade.close_time.isoformat() if trade.close_time else None,
            "entry_cost_pips": trade.entry_cost_pips,
            "exit_cost_pips": trade.exit_cost_pips,
            "total_cost_pips": round(trade.entry_cost_pips + trade.exit_cost_pips, 1),
        }
    
    async def start(self, signal_generator: Optional[Callable] = None):
        """
        Start the trading simulation.
        
        Args:
            signal_generator: Async function that returns trade signals.
                             Should return: {"action": "BUY"/"SELL"/"WAIT", ...}
        """
        if not self._provider:
            logger.error("No data provider set. Use set_provider() first.")
            return
        
        self.is_running = True
        logger.info("Trading simulation started.")
        
        while self.is_running:
            try:
                # Get current price
                result = await self._provider.get_price()
                
                if "error" in result:
                    logger.warning(f"Price fetch error: {result['error']}")
                    await asyncio.sleep(5)
                    continue
                
                current_price = result["price"]
                
                # Update existing trades
                self.update_trades(current_price)
                
                # Generate signal if generator provided
                if signal_generator:
                    signal = await signal_generator(current_price)
                    
                    if signal and signal.get("action") != "WAIT":
                        direction = TradeDirection.BUY if signal["action"] == "BUY" else TradeDirection.SELL
                        self.open_trade(
                            direction=direction,
                            entry_price=current_price,
                            stop_loss=signal["stop_loss"],
                            take_profit=signal["take_profit"],
                            units=signal.get("units", 10000)
                        )
                
                # Notify price update
                if self.on_price_update:
                    self.on_price_update(current_price, self.get_status())
                
                # Wait before next update
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Simulation error: {e}")
                await asyncio.sleep(5)
    
    def stop(self):
        """Stop the trading simulation."""
        self.is_running = False
        logger.info("Trading simulation stopped.")
