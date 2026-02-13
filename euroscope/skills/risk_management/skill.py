"""
Risk Management Skill — Wraps RiskManager for the skills framework.
"""

from ...trading.risk_manager import RiskManager, RiskConfig
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class RiskManagementSkill(BaseSkill):
    name = "risk_management"
    description = "Position sizing, stop loss, take profit, and drawdown control"
    emoji = "🛡️"
    category = SkillCategory.TRADING
    version = "1.0.0"
    capabilities = ["assess_trade", "position_size", "stop_loss", "take_profit"]

    def __init__(self, config: RiskConfig = None):
        super().__init__()
        self.manager = RiskManager(config or RiskConfig())

    def set_risk_manager(self, manager):
        """Inject the RiskManager instance."""
        self.manager = manager

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "assess_trade":
            return await self._assess(context, **params)
        elif action == "position_size":
            return await self._position_size(**params)
        elif action == "stop_loss":
            return await self._stop_loss(**params)
        elif action == "take_profit":
            return await self._take_profit(**params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _assess(self, context: SkillContext, **params) -> SkillResult:
        direction = params.get("direction", "BUY")
        entry = params.get("entry_price", 0)
        atr = params.get("atr")
        support = params.get("support", context.analysis.get("levels", {}).get("support", []))
        resistance = params.get("resistance", context.analysis.get("levels", {}).get("resistance", []))

        if not entry:
            price_data = context.market_data.get("price", {})
            entry = price_data.get("price", 0)

        if not atr:
            ind = context.analysis.get("indicators", {})
            atr_data = ind.get("indicators", {}).get("ATR", {})
            atr = atr_data.get("value")

        try:
            result = self.manager.assess_trade(
                direction, entry, atr=atr, support=support, resistance=resistance,
            )
            data = {
                "approved": result.approved,
                "direction": result.direction,
                "entry_price": result.entry_price,
                "stop_loss": result.stop_loss,
                "take_profit": result.take_profit,
                "position_size": result.position_size,
                "risk_pips": result.risk_pips,
                "reward_pips": result.reward_pips,
                "risk_reward_ratio": result.risk_reward_ratio,
                "reason": result.reason,
            }
            context.risk = data
            return SkillResult(success=True, data=data, next_skill="trading_strategy")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _position_size(self, **params) -> SkillResult:
        balance = params.get("balance", 10000)
        risk_pct = params.get("risk_pct", 0.01)
        stop_pips = params.get("stop_pips", 30)
        try:
            size = self.manager.calculate_position_size(balance, risk_pct, stop_pips)
            return SkillResult(success=True, data={"position_size": size})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _stop_loss(self, **params) -> SkillResult:
        direction = params.get("direction", "BUY")
        entry = params.get("entry_price", 0)
        atr = params.get("atr", 0.001)
        try:
            sl = self.manager.calculate_stop_loss(direction, entry, atr)
            return SkillResult(success=True, data={"stop_loss": sl})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _take_profit(self, **params) -> SkillResult:
        direction = params.get("direction", "BUY")
        entry = params.get("entry_price", 0)
        sl = params.get("stop_loss", 0)
        try:
            tp = self.manager.calculate_take_profit(direction, entry, sl)
            return SkillResult(success=True, data={"take_profit": tp})
        except Exception as e:
            return SkillResult(success=False, error=str(e))
