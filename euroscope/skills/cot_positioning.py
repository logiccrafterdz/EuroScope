import logging

from ..data.cot import COTProvider
from .base import BaseSkill, SkillCategory, SkillContext, SkillResult

logger = logging.getLogger("euroscope.skills.cot_positioning")

class COTPositioningSkill(BaseSkill):
    name = "cot_positioning"
    description = "Retrieves CFTC Net Positioning to evaluate long-term institutional bias for the Euro"
    emoji = "🏦"
    category = SkillCategory.FUNDAMENTAL
    version = "1.0.0"
    capabilities = ["get_net_positioning"]

    def __init__(self):
        super().__init__()
        self.provider = COTProvider()

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "get_net_positioning":
            return await self._get_positioning(context)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _get_positioning(self, context: SkillContext) -> SkillResult:
        try:
            positioning = await self.provider.get_latest_positioning()
            if "error" in positioning:
                return SkillResult(success=False, error=positioning["error"])

            net_positions = positioning["non_commercial"]["net"]
            bias = positioning["non_commercial"]["bias"]
            
            # Simple scoring: 100 max, scaled by 50k contracts
            confidence = min(100.0, abs(net_positions) / 50000 * 100)
            
            # Formatted String Let's make it look nice
            icon = "🟢" if bias == "bullish" else "🔴" if bias == "bearish" else "⚪"
            formatted = f"🏦 *CFTC COT Report* (as of {positioning['report_date']})\n"
            formatted += f"{icon} Bias: *{bias.upper()}*\n"
            formatted += f"Net Speculative Positions: `{net_positions:,}` contracts\n"
            formatted += f"Confidence Score: `{min(100, int(confidence))}%`"

            result_data = {
                "report_date": positioning["report_date"],
                "net_positions": net_positions,
                "bias": bias,
                "confidence": confidence,
            }

            # Inject into fundamental context
            if "fundamental" not in context.analysis:
                context.analysis["fundamental"] = {}
            context.analysis["fundamental"]["cot_positioning"] = result_data

            return SkillResult(
                success=True,
                data=result_data,
                metadata={"formatted": formatted}
            )
        except Exception as e:
            logger.error(f"COT positioning execution failed: {e}")
            return SkillResult(success=False, error=str(e))
