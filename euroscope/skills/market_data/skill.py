"""
Market Data Skill — Wraps PriceProvider for the skills framework.
"""

from datetime import datetime

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class MarketDataSkill(BaseSkill):
    name = "market_data"
    description = "Fetches real-time and historical EUR/USD price data"
    emoji = "📊"
    category = SkillCategory.DATA
    version = "1.0.0"
    capabilities = ["get_price", "get_candles", "check_market_status"]

    def __init__(self, provider=None):
        super().__init__()
        self._provider = provider
        self._buffer: dict = {}

    def set_provider(self, provider):
        """Standard setter for price provider (DI)."""
        self._provider = provider

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "get_price":
            return await self._get_price(context)
        elif action == "get_candles":
            return await self._get_candles(context, **params)
        elif action == "check_market_status":
            return await self._check_status(context)
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
            count = params.get("count", 250)
            df = await self._provider.get_candles(timeframe=timeframe, count=count)
            if df is None or (hasattr(df, 'empty') and df.empty):
                return SkillResult(success=False, error="No candle data returned")
            context.market_data["candles"] = df
            context.market_data["timeframe"] = timeframe
            from datetime import timezone
            self._buffer = {
                "candles": df,
                "timeframe": timeframe,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            return SkillResult(success=True, data=df, next_skill="technical_analysis")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def get_buffer(self) -> dict:
        return dict(self._buffer)

    async def _check_status(self, context: SkillContext) -> SkillResult:
        """Check if the EUR/USD market is currently open (Sun 5PM - Fri 5PM ET)."""
        from datetime import datetime, timezone, timedelta
        
        # ET is UTC-5
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc - timedelta(hours=5)
        
        weekday = now_et.weekday() # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        hour = now_et.hour
        
        is_open = True
        reason = "Trading sessions are active."
        
        # Closed: Friday after 5PM ET
        if weekday == 4 and hour >= 17:
            is_open = False
            reason = "Market closed for the weekend (Friday 5PM ET)."
        # Closed: All Saturday
        elif weekday == 5:
            is_open = False
            reason = "Market closed (Saturday)."
        # Closed: Sunday before 5PM ET
        elif weekday == 6 and hour < 17:
            is_open = False
            reason = "Market opening soon (opens Sunday 5PM ET)."
            
        data = {
            "is_open": is_open,
            "status": "OPEN" if is_open else "CLOSED",
            "reason": reason,
            "current_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S ET")
        }
        
        context.metadata["market_status"] = data
        return SkillResult(success=True, data=data)
