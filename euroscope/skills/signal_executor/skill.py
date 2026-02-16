"""
Signal Executor Skill — Paper trading order management.
"""

import time
from dataclasses import dataclass, field
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult
from ...automation.events import Event
from ...data.storage import Storage


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
    execution_mode: str = "paper"


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
        self._storage: Storage | None = None
        self._bus = None
        self._emergency_halt = False
        self._emergency_halt_until = 0.0
        self._paper_trading_only = True

    def set_storage(self, storage):
        self._storage = storage

    def set_event_bus(self, event_bus):
        self._bus = event_bus

    def set_config(self, config):
        value = getattr(config, "paper_trading_only", None)
        if value is None:
            value = getattr(config, "EUROSCOPE_PAPER_TRADING_ONLY", None)
        if value is None:
            value = True
        self._paper_trading_only = bool(value)

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

    async def execute_trade(self, context: SkillContext, **params) -> SkillResult:
        return await self._open_trade(context, **params)

    async def _open_trade(self, context: SkillContext, **params) -> SkillResult:
        abort_reason = self._guard_trade(context)
        if abort_reason:
            await self._record_abort(context, params, abort_reason)
            return SkillResult(success=False, error=abort_reason, data={
                "aborted": True,
                "reason": abort_reason,
            })
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
        if self._storage:
            timeframe = context.market_data.get("timeframe", "H1")
            regime = context.metadata.get("regime", "")
            confidence = signal.get("confidence", 0.0)
            indicators = self._build_indicators(context)
            patterns = self._build_patterns(context)
            self._storage.save_trade_journal(
                direction=signal.get("direction", "BUY"),
                entry_price=trade.entry_price,
                stop_loss=trade.stop_loss,
                take_profit=trade.take_profit,
                strategy=trade.strategy,
                timeframe=timeframe,
                regime=regime,
                confidence=confidence,
                indicators=indicators,
                patterns=patterns,
                reasoning="paper trade opened",
                status="open",
            )
        return SkillResult(success=True, data=trade.__dict__,
                          metadata={"trade_id": trade.trade_id})

    def _guard_trade(self, context: SkillContext) -> str | None:
        now = time.time()
        if self._emergency_halt and now < self._emergency_halt_until:
            return "EMERGENCY: market regime shift"
        if self._emergency_halt and now >= self._emergency_halt_until:
            self._emergency_halt = False
        if context.metadata.get("emergency_mode") is True:
            return "EMERGENCY: market regime shift"
        if self._paper_trading_only:
            mode = context.metadata.get("execution_mode")
            if mode and str(mode).lower() not in {"paper", "sim", "simulation"}:
                return "PAPER_ONLY: live execution disabled"
        if context.metadata.get("uncertainty_score", 0) > 0.65:
            return "UNCERTAINTY: confidence too low"
        if context.metadata.get("confidence_adjustment", 1.0) < 0.5:
            return "CONFIDENCE: signal degraded"
        return None

    def set_emergency_halt(self, duration_seconds: int = 300):
        self._emergency_halt = True
        self._emergency_halt_until = time.time() + duration_seconds

    async def _record_abort(self, context: SkillContext, params: dict, reason: str):
        signal = context.signals or params
        risk = context.risk or {}
        entry_price = signal.get("entry_price", risk.get("entry_price", 0))
        stop_loss = risk.get("stop_loss", 0)
        take_profit = risk.get("take_profit", 0)
        strategy = signal.get("strategy", "manual")
        timeframe = context.market_data.get("timeframe", "H1")
        regime = context.metadata.get("regime", "")
        confidence = signal.get("confidence", 0.0)
        indicators = self._build_indicators(context)
        patterns = self._build_patterns(context)
        if self._storage:
            self._storage.save_trade_journal(
                direction=signal.get("direction", "BUY"),
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy=strategy,
                timeframe=timeframe,
                regime=regime,
                confidence=confidence,
                indicators=indicators,
                patterns=patterns,
                reasoning=f"paper rejection: {reason}",
                status="rejected",
            )
        if self._bus:
            await self._bus.emit(Event("trade.aborted", "signal_executor", {
                "reason": reason,
                "direction": signal.get("direction", "BUY"),
                "strategy": strategy,
                "timeframe": timeframe,
            }))

    @staticmethod
    def _build_patterns(context: SkillContext) -> list:
        patterns = context.analysis.get("patterns", [])
        if isinstance(patterns, list):
            return patterns
        return []

    @staticmethod
    def _build_indicators(context: SkillContext) -> dict:
        indicators = context.analysis.get("indicators", {})
        if not isinstance(indicators, dict):
            indicators = {}
        indicators = dict(indicators)
        if "uncertainty_score" in context.metadata:
            indicators["uncertainty_score"] = context.metadata.get("uncertainty_score")
        if "uncertainty_reasoning" in context.metadata:
            indicators["uncertainty_reasoning"] = context.metadata.get("uncertainty_reasoning")
        return indicators

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
        trades = [t.__dict__ for t in self._open]
        formatted = self._format_trades(trades, "📋 *Open Trades*")
        return SkillResult(success=True, data=trades, metadata={"formatted": formatted})

    async def _trade_history(self) -> SkillResult:
        trades = [t.__dict__ for t in self._closed]
        formatted = self._format_trades(trades, "📘 *Trade History*")
        return SkillResult(success=True, data=trades, metadata={"formatted": formatted})

    def _format_trades(self, trades: list[dict], title: str) -> str:
        if not trades:
            return "📋 No open trades."
        lines = [f"{title} ({len(trades)})\n"]
        for t in trades:
            direction = str(t.get("direction", "")).upper()
            icon = "📈" if direction == "BUY" else "📉"
            trade_id = t.get("trade_id", "")
            entry = self._format_price(t.get("entry_price"))
            stop = self._format_price(t.get("stop_loss"))
            target = self._format_price(t.get("take_profit"))
            lines.append(f"{icon} {trade_id} {direction} @ `{entry}` SL=`{stop}` TP=`{target}`")
        return "\n".join(lines)

    @staticmethod
    def _format_price(value) -> str:
        try:
            return f"{float(value):.5f}"
        except (TypeError, ValueError):
            return str(value)
