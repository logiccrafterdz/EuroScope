"""
Market Data Skill — Wraps PriceProvider for the skills framework.
"""

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class MarketDataSkill(BaseSkill):
    name = "market_data"
    description = "Fetches real-time and historical EUR/USD price data"
    emoji = "📊"
    category = SkillCategory.DATA
    version = "1.0.0"
    capabilities = ["get_price", "get_candles"]

    def __init__(self, provider=None):
        super().__init__()
        self._provider = provider

    def set_provider(self, provider):
        """Inject the PriceProvider instance."""
        self._provider = provider

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "get_price":
            return await self._get_price(context)
        elif action == "get_candles":
            return await self._get_candles(context, **params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _get_price(self, context: SkillContext) -> SkillResult:
        if not self._provider:
            return SkillResult(success=False, error="No price provider configured")
        try:
            data = await self._provider.get_price()
            if "error" in data:
                return SkillResult(success=False, error=data["error"])
            context.market_data["price"] = data
            return SkillResult(success=True, data=data, next_skill="technical_analysis")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_candles(self, context: SkillContext, **params) -> SkillResult:
        if not self._provider:
            return SkillResult(success=False, error="No price provider configured")
        try:
            timeframe = params.get("timeframe", "H1")
            count = params.get("count", 100)
            df = await self._provider.get_candles(timeframe=timeframe, count=count)
            if df is None or (hasattr(df, 'empty') and df.empty):
                return SkillResult(success=False, error="No candle data returned")
            context.market_data["candles"] = df
            context.market_data["timeframe"] = timeframe
            return SkillResult(success=True, data=df, next_skill="technical_analysis")
        except Exception as e:
            return SkillResult(success=False, error=str(e))
