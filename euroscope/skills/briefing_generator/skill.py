import logging
from datetime import datetime, timezone

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult

logger = logging.getLogger("euroscope.skills.briefing_generator")


class BriefingGeneratorSkill(BaseSkill):
    name = "briefing_generator"
    description = "Synthesizes market data into cohesive morning and weekly briefing reports"
    emoji = "📰"
    category = SkillCategory.ANALYTICS
    version = "1.0.0"
    capabilities = ["generate_morning_briefing", "generate_weekly_review"]
    dependencies = ["technical_analysis", "fundamental_analysis", "macro_calendar", "performance_analytics"]

    def __init__(self, agent=None):
        super().__init__()
        # If we have an LLM agent instance, we can use it to generate natural language briefings.
        # Otherwise, we fallback to a structured template.
        self.agent = agent

    def set_agent(self, agent):
        self.agent = agent

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "generate_morning_briefing":
            return await self._generate_morning_briefing(context, **params)
        elif action == "generate_weekly_review":
            return await self._generate_weekly_review(context, **params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _generate_morning_briefing(self, context: SkillContext, **params) -> SkillResult:
        try:
            # Extract data populated by prerequisites
            tech = context.analysis.get("technical", {})
            fund = context.analysis.get("fundamental", {})
            cal = context.analysis.get("upcoming_events", [])
            perf = context.analysis.get("performance", {})
            
            # Simple template generation
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            
            lines = [
                f"🌅 *EuroScope Morning Briefing* ({now})\n",
                "📈 *Technical Overview*",
            ]
            
            if tech:
                trend = tech.get("indicators", {}).get("ema_trend", "Neutral")
                rsi = tech.get("indicators", {}).get("rsi", "N/A")
                lines.append(f"  • Trend: {trend}")
                lines.append(f"  • RSI(14): {rsi}")
            else:
                lines.append("  • No technical data available.")
                
            lines.append("\n🌍 *Macro & Fundamentals*")
            if fund:
                sentiment = fund.get("sentiment", {}).get("overall_score", "Neutral")
                lines.append(f"  • News Sentiment: {sentiment}")
            else:
                lines.append("  • No fundamental data available.")
                
            lines.append("\n📆 *Today's Key Events*")
            high_impact = [e for e in cal if e.get("impact", "").lower() == "high"]
            if high_impact:
                for e in high_impact:
                    lines.append(f"  • 🔴 {e['name']} ({e['currency']})")
            else:
                lines.append("  • No high-impact events scheduled.")
                
            formatted = "\n".join(lines)
            
            data = {
                "report_type": "morning_briefing",
                "date": now,
                "sections": {
                    "technical": tech,
                    "fundamental": fund,
                    "calendar": cal,
                    "performance": perf
                }
            }
            
            # Store in context
            context.metadata["latest_briefing"] = data
            
            return SkillResult(success=True, data=data, metadata={"formatted": formatted})
        except Exception as e:
            logger.error(f"Failed to generate morning briefing: {e}")
            return SkillResult(success=False, error=str(e))

    async def _generate_weekly_review(self, context: SkillContext, **params) -> SkillResult:
        try:
            perf = context.analysis.get("performance", {})
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            
            lines = [
                f"🗓️ *EuroScope Weekly Review* (Week ending {now})\n",
                "📊 *Performance Summary*",
            ]
            
            if perf:
                win_rate = perf.get("win_rate", 0.0)
                pnl = perf.get("total_pnl", 0.0)
                lines.append(f"  • Net PnL: {pnl:.1f} pips")
                lines.append(f"  • Win Rate: {win_rate:.1f}%")
            else:
                lines.append("  • No performance data available for this week.")
                
            formatted = "\n".join(lines)
            
            data = {
                "report_type": "weekly_review",
                "date": now,
                "performance": perf
            }
            
            return SkillResult(success=True, data=data, metadata={"formatted": formatted})
        except Exception as e:
            logger.error(f"Failed to generate weekly review: {e}")
            return SkillResult(success=False, error=str(e))
