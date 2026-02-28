"""
Offline Executor for Backtesting

Simulates order execution and tracks positions during historical backtests,
bypassing the asynchronous SQLite storage used in live trading.
Integrates `ExecutionSimulator` for realistic slippage and spread modeling.
"""

from typing import Dict, List, Optional
from datetime import datetime

from ..trading.execution_simulator import ExecutionSimulator, ExecutionResult
from dataclasses import dataclass

@dataclass
class TradeSignal:
    direction: str
    entry_price: float
    sl_price: float
    tp_price: float
    position_size: float
    strategy: str
    timeframe: str
    confidence: float
    reasoning: str


class OfflinePosition:
    def __init__(self, ticket: str, direction: str, size: float, entry_price: float, 
                 sl: float, tp: float, open_time: datetime, entry_result: ExecutionResult):
        self.ticket = ticket
        self.direction = direction
        self.size = size
        self.entry_price = entry_price  # This is the simulated fill price
        self.sl = sl
        self.tp = tp
        self.open_time = open_time
        self.entry_result = entry_result
        
        self.is_open = True
        self.close_price = 0.0
        self.close_time: Optional[datetime] = None
        self.exit_reason = ""
        self.exit_result: Optional[ExecutionResult] = None
        self.pnl_pips = 0.0
        
    def close(self, price: float, time: datetime, reason: str, exit_result: ExecutionResult):
        self.is_open = False
        self.close_price = price
        self.close_time = time
        self.exit_reason = reason
        self.exit_result = exit_result
        
        # Calculate PnL in pips
        if self.direction == "BUY":
            self.pnl_pips = (self.close_price - self.entry_price) * 10000
        else:
            self.pnl_pips = (self.entry_price - self.close_price) * 10000


class OfflineExecutor:
    """Manages virtual trades during backtesting."""
    
    def __init__(self, simulator: ExecutionSimulator):
        self.simulator = simulator
        self.positions: List[OfflinePosition] = []
        self._ticket_counter = 1
        
    def open_position(self, signal: TradeSignal, current_price: float, 
                      current_time: datetime, atr: float) -> Optional[OfflinePosition]:
        """Attempt to open a new position based on a signal."""
        # 1. Simulate entry (applies spread, slippage, fill rate)
        sim_result = self.simulator.simulate_entry(
            direction=signal.direction,
            price=current_price,
            atr=atr
        )
        
        if not sim_result.filled:
            return None  # Order rejected by simulator
            
        # 2. Track position
        pos = OfflinePosition(
            ticket=f"BT_{self._ticket_counter:04d}",
            direction=signal.direction,
            size=signal.position_size,
            entry_price=sim_result.fill_price,  # Actual simulated fill
            sl=signal.sl_price,
            tp=signal.tp_price,
            open_time=current_time,
            entry_result=sim_result
        )
        
        self.positions.append(pos)
        self._ticket_counter += 1
        return pos
        
    def update_positions(self, high: float, low: float, current_time: datetime, atr: float):
        """Check open positions against candle extremes for SL/TP hits."""
        for pos in self.open_positions:
            if pos.direction == "BUY":
                # Check Stop Loss first (pessimistic fill)
                if low <= pos.sl:
                    self._close_position(pos, pos.sl, current_time, "stop_loss", atr)
                # Check Take Profit
                elif high >= pos.tp:
                    self._close_position(pos, pos.tp, current_time, "take_profit", atr)
            else:  # SELL
                # Check Stop Loss first (pessimistic fill)
                if high >= pos.sl:
                    self._close_position(pos, pos.sl, current_time, "stop_loss", atr)
                # Check Take Profit
                elif low <= pos.tp:
                    self._close_position(pos, pos.tp, current_time, "take_profit", atr)

    def _close_position(self, pos: OfflinePosition, trigger_price: float, 
                        current_time: datetime, reason: str, atr: float):
        """Close a target position explicitly."""
        sim_result = self.simulator.simulate_exit(
            direction=pos.direction,
            price=trigger_price,  # Base price is the SL/TP level
            reason=reason,
            atr=atr
        )
        pos.close(sim_result.fill_price, current_time, reason, sim_result)
        
    def close_all(self, current_price: float, current_time: datetime, atr: float, reason: str = "manual"):
        """Force close all open positions (e.g., end of backtest or end of week)."""
        for pos in self.open_positions:
            self._close_position(pos, current_price, current_time, reason, atr)
            
    @property
    def open_positions(self) -> List[OfflinePosition]:
        return [p for p in self.positions if p.is_open]
        
    @property
    def closed_positions(self) -> List[OfflinePosition]:
        return [p for p in self.positions if not p.is_open]
