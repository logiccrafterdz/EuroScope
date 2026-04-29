"""
Performance Analytics Skill — Wraps PerformanceAnalytics for skills framework.
"""

from ...analytics.performance_analytics import PerformanceAnalytics
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class PerformanceAnalyticsSkill(BaseSkill):
    name = "performance_analytics"
    description = "Real-time PnL tracking, Sharpe/Sortino ratios, equity curves"
    emoji = "📊"
    category = SkillCategory.ANALYTICS
    version = "1.0.0"
    capabilities = ["compute_metrics", "get_snapshot", "breakdown", "format_report"]

    def __init__(self, storage=None):
        super().__init__()
        self.storage = storage
        self._analytics = PerformanceAnalytics(storage) if storage else None

    def set_storage(self, storage):
        """Standard setter for auto-injection."""
        self.storage = storage
        self._analytics = PerformanceAnalytics(storage)

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "compute_metrics":
            return await self._compute(context, **params)
        elif action == "get_snapshot":
            return await self._snapshot(**params)
        elif action == "breakdown":
            return await self._breakdown(**params)
        elif action == "format_report":
            return await self._format(**params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _compute(self, context: SkillContext, **params) -> SkillResult:
        trades = params.get("trades", [])
        try:
            snap = self._analytics.compute_from_trades(trades)
            data = {
                "total_trades": snap.total_trades,
                "win_rate": snap.win_rate,
                "total_pnl": snap.total_pnl,
                "sharpe_ratio": snap.sharpe_ratio,
                "sortino_ratio": snap.sortino_ratio,
                "max_drawdown_pips": snap.max_drawdown,
                "profit_factor": snap.profit_factor,
                "expectancy": snap.expectancy,
            }
            return SkillResult(success=True, data=data)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _snapshot(self, **params) -> SkillResult:
        if not self._analytics:
            return SkillResult(success=False, error="Performance analytics engine not initialized")
        try:
            snap = self._analytics.calculate(period=params.get("period", "all"))
            formatted = self._analytics.format_full_report(snap)
            return SkillResult(success=True, data=snap.__dict__, metadata={"formatted": formatted})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _breakdown(self, **params) -> SkillResult:
        trades = params.get("trades", [])
        by = params.get("by", "strategy")
        try:
            if by == "strategy":
                data = self._analytics.breakdown_by_strategy(trades)
            elif by == "session":
                data = self._analytics.breakdown_by_session(trades)
            elif by == "day":
                data = self._analytics.breakdown_by_day(trades)
            else:
                data = {}
            return SkillResult(success=True, data=data)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _format(self, **params) -> SkillResult:
        trades = params.get("trades", [])
        try:
            snap = self._analytics.compute_from_trades(trades)
            text = self._analytics.format_full_report(snap)
            return SkillResult(success=True, data=text)
        except Exception as e:
            return SkillResult(success=False, error=str(e))
