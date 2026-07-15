"""
Trading Simulation Engine

Provides real-time paper trading simulation using BiQuote data.
Simulates trade execution, tracking, and performance reporting.
"""

import asyncio
import logging
from datetime import datetime, UTC
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass, field
from enum import Enum

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
    entry_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    close_time: Optional[datetime] = None
    close_price: Optional[float] = None
    status: TradeStatus = TradeStatus.OPEN
    pnl: float = 0.0
    
    def update_pnl(self, current_price: float):
        """Update PnL based on current price."""
        if self.direction == TradeDirection.BUY:
            self.pnl = (current_price - self.entry_price) * self.units
        else:
            self.pnl = (self.entry_price - current_price) * self.units
    
    def check_exit(self, current_price: float) -> bool:
        """Check if trade should be closed (SL/TP hit)."""
        if self.direction == TradeDirection.BUY:
            if current_price <= self.stop_loss:
                self.close(current_price, TradeStatus.CLOSED_LOSS)
                return True
            if current_price >= self.take_profit:
                self.close(current_price, TradeStatus.CLOSED_WIN)
                return True
        else:  # SELL
            if current_price >= self.stop_loss:
                self.close(current_price, TradeStatus.CLOSED_LOSS)
                return True
            if current_price <= self.take_profit:
                self.close(current_price, TradeStatus.CLOSED_WIN)
                return True
        return False
    
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
    
    def __init__(self, initial_balance: float = 100000.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.open_trades: List[Trade] = []
        self.closed_trades: List[Trade] = []
        self.trade_counter = 0
        self.is_running = False
        
        # Callbacks
        self.on_price_update: Optional[Callable] = None
        self.on_trade_opened: Optional[Callable] = None
        self.on_trade_closed: Optional[Callable] = None
        
        # Data provider
        self._provider = None
    
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
        trade = Trade(
            id=self._generate_trade_id(),
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            units=units
        )
        
        self.open_trades.append(trade)
        logger.info(f"Trade opened: {direction.value} @ {entry_price}, SL: {stop_loss}, TP: {take_profit}")
        
        if self.on_trade_opened:
            self.on_trade_opened(trade)
        
        return trade
    
    def update_trades(self, current_price: float):
        """Update all open trades with current price."""
        trades_to_close = []
        
        for trade in self.open_trades:
            trade.update_pnl(current_price)
            
            if trade.check_exit(current_price):
                trades_to_close.append(trade)
        
        # Close trades that hit SL/TP
        for trade in trades_to_close:
            self.open_trades.remove(trade)
            self.closed_trades.append(trade)
            self.current_balance += trade.pnl
            
            logger.info(f"Trade closed: {trade.status.value}, PnL: {trade.pnl:.2f}")
            
            if self.on_trade_closed:
                self.on_trade_closed(trade)
    
    def get_status(self) -> Dict:
        """Get current simulation status."""
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
            "close_time": trade.close_time.isoformat() if trade.close_time else None
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
                            take_profit=signal["take_profit"]
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
