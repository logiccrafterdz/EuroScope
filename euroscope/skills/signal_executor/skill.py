"""
Signal Executor Skill — Paper trading order management.
"""

import time
from dataclasses import dataclass, field
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


@dataclass
class PaperTrade:
    """A virtual paper trade."""
    trade_id: str = ""
    direction: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    strategy: str = ""
    timestamp: float = 0.0
    status: str = "open"  # open, closed
    exit_price: float = 0.0
    pnl_pips: float = 0.0


class SignalExecutorSkill(BaseSkill):
    name = "signal_executor"
    description = "Converts signals to paper trade orders with tracking"
    emoji = "⚡"
    category = SkillCategory.TRADING
    version = "1.0.0"
    capabilities = ["open_trade", "close_trade", "list_trades", "trade_history"]

    def __init__(self):
        super().__init__()
        self._open: list[PaperTrade] = []
        self._closed: list[PaperTrade] = []
        self._counter = 0

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "open_trade":
            return await self._open_trade(context, **params)
        elif action == "close_trade":
            return await self._close_trade(context, **params)
        elif action == "list_trades":
            return await self._list_trades()
        elif action == "trade_history":
            return await self._trade_history()
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _open_trade(self, context: SkillContext, **params) -> SkillResult:
        self._counter += 1
        signal = context.signals or params
        risk = context.risk or {}

        trade = PaperTrade(
            trade_id=f"PT-{self._counter:04d}",
            direction=signal.get("direction", "BUY"),
            entry_price=signal.get("entry_price", risk.get("entry_price", 0)),
            stop_loss=risk.get("stop_loss", 0),
            take_profit=risk.get("take_profit", 0),
            strategy=signal.get("strategy", "manual"),
            timestamp=time.time(),
        )
        self._open.append(trade)
        context.open_positions.append(trade.__dict__)
        return SkillResult(success=True, data=trade.__dict__,
                          metadata={"trade_id": trade.trade_id})

    async def _close_trade(self, context: SkillContext, **params) -> SkillResult:
        trade_id = params.get("trade_id", "")
        exit_price = params.get("exit_price", 0)

        for i, trade in enumerate(self._open):
            if trade.trade_id == trade_id:
                trade.exit_price = exit_price
                trade.status = "closed"
                if trade.direction == "BUY":
                    trade.pnl_pips = round((exit_price - trade.entry_price) * 10000, 1)
                else:
                    trade.pnl_pips = round((trade.entry_price - exit_price) * 10000, 1)
                self._closed.append(trade)
                self._open.pop(i)
                return SkillResult(success=True, data=trade.__dict__)

        return SkillResult(success=False, error=f"Trade {trade_id} not found")

    async def _list_trades(self) -> SkillResult:
        return SkillResult(success=True, data=[t.__dict__ for t in self._open])

    async def _trade_history(self) -> SkillResult:
        return SkillResult(success=True, data=[t.__dict__ for t in self._closed])
