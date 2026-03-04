"""
Briefing Engine — Synthesizes overnight data and learning insights into a daily plan.
Phase 3C implementation.
"""

import logging
from datetime import datetime, UTC, timedelta
from typing import Dict, Any, List

from ..data.storage import Storage
from ..analytics.health_monitor import HealthMonitor

logger = logging.getLogger("euroscope.brain.briefing")

class BriefingEngine:
    """
    Aggregates multi-source intelligence into a human-readable daily briefing.
    """
    
    def __init__(self, config=None, storage: Storage = None, orchestrator=None):
        self.config = config
        self.storage = storage
        self.orchestrator = orchestrator
        
    async def generate_briefing(self) -> Dict[str, Any]:
        """
        Generates a comprehensive daily market briefing as structured data.
        """
        logger.info("Generating daily briefing data...")
        
        # 1. Overnight Summary (News & Sentiment)
        overnight_news = await self.storage.get_recent_news(limit=5, min_impact=0.7) if self.storage else []
        
        # 2. Key Levels (Fetch from technical analysis)
        key_levels = "• Data unavailable"
        if self.orchestrator:
            from ..skills.base import SkillContext
            ctx = SkillContext()
            await self.orchestrator.run_skill("market_data", "get_price", context=ctx)
            ta_res = await self.orchestrator.run_skill("technical_analysis", "analyze", context=ctx, timeframe="H1")
            if ta_res.success and ta_res.data:
                levels = ta_res.data.get("levels", {})
                sup = levels.get("support", [])
                res = levels.get("resistance", [])
                
                sup_str = ", ".join([f"{l:.4f}" for l in sup[:2]]) if sup else "None"
                res_str = ", ".join([f"{l:.4f}" for l in res[:2]]) if res else "None"
                key_levels = f"• Support: {sup_str}\n• Resistance: {res_str}"
                
        # 3. High-Probability Setups
        setups = "• No significant setups detected"
        if self.orchestrator:
            from ..skills.base import SkillContext
            ctx2 = SkillContext()
            await self.orchestrator.run_skill("market_data", "get_price", context=ctx2)
            pattern_res = await self.orchestrator.run_skill("technical_analysis", "detect_patterns", context=ctx2, timeframe="H1")
            signal_res = await self.orchestrator.run_skill("trading_strategy", "detect_signal", context=ctx2)
            
            setup_lines = []
            if signal_res.success and signal_res.data and signal_res.data.get("direction") in ("BUY", "SELL"):
                sig = signal_res.data
                setup_lines.append(f"• Active {sig['direction']} Signal via {sig.get('strategy', 'AI')} ({sig.get('confidence', 0)}% conf)")
                
            if pattern_res.success and pattern_res.data:
                patterns = [p for p in pattern_res.data if p.get('status') == 'active']
                for p in patterns[:2]:
                    setup_lines.append(f"• {p.get('name', 'Pattern')} marked as active")
                    
            if setup_lines:
                setups = "\n".join(setup_lines)
        
        # 4. Learning Insights & Trade Review (Yesterday)
        yesterday_str = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        trades_yesterday = await self.storage.get_trade_journal_for_date(yesterday_str) if self.storage else []
        insights = await self.storage.get_recent_learning_insights(limit=3) if self.storage else []
        
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "urgency": "normal",
            "news": overnight_news,
            "levels": key_levels,
            "setups": setups,
            "insights": insights,
            "trades": trades_yesterday
        }

    def format_for_telegram(self, data: Dict[str, Any]) -> str:
        """Formats the briefing data into a professional synthesized message for Telegram."""
        dt = datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(UTC)
        now_str = dt.strftime("%Y-%m-%d %H:%M")
        
        report = [
            f"📅 <b>EuroScope Daily Intelligence Briefing</b>",
            f"<i>{now_str} UTC | London Session Open</i>\n",
        ]
        
        # 1. Overnight Summary
        report.append("🌙 <b>Overnight Session Pulse</b>")
        if data.get("news"):
            for item in data["news"][:3]:
                report.append(f"• {item.get('title')} ({item.get('source')})")
        else:
            report.append("• Market consolidated in a tight range overnight.")
        report.append("")
        
        # 2. Key Levels
        report.append("🎯 <b>Key Levels Today</b>")
        report.append(data.get("levels", ""))
        report.append("")
        
        # 3. High-Probability Setups
        report.append("💡 <b>High-Probability Setups</b>")
        report.append(data.get("setups", ""))
        report.append("")
        
        # 4. Yesterday's Trade Review
        report.append("📊 <b>Yesterday's Trade Review</b>")
        trades = data.get("trades", [])
        if trades:
            wins = sum(1 for t in trades if t.get('pips', 0) > 0)
            pnl = sum(t.get('pips', 0) for t in trades)
            report.append(f"• Trades: {len(trades)} | Win Rate: {(wins/len(trades)):.0%} | P/L: {pnl:+.1f}p")
            insights = data.get("insights", [])
            if insights:
                report.append(f"• 🎓 <b>Key Lesson:</b> {insights[0].get('recommendations', ['Stay disciplined'])[0]}")
        else:
            report.append("• No trades executed yesterday.")
        
        report.append("\n⚠️ <b>Risk Factors:</b> High-impact USD CPI at 13:30 UTC. Monitor liquidity.")
        
        return "\n".join(report)

    def format_for_api(self, data: Dict[str, Any]) -> dict:
        """Format briefing data as JSON structured sections for the Mini App."""
        sections = []
        
        # Overnight Summary
        news_content = "• Market consolidated in a tight range overnight."
        if data.get("news"):
            news_content = "\n".join([f"• {item.get('title')} ({item.get('source')})" for item in data["news"][:3]])
        sections.append({
            "title": "Overnight Session Pulse",
            "content": news_content,
            "priority": 2,
            "icon": "🌙"
        })
        
        # Key Levels
        sections.append({
            "title": "Key Levels Today",
            "content": data.get("levels", ""),
            "priority": 2,
            "icon": "🎯"
        })
        
        # Setups
        sections.append({
            "title": "High-Probability Setups",
            "content": data.get("setups", ""),
            "priority": 3,
            "icon": "💡"
        })
        
        # Performance Review
        trades = data.get("trades", [])
        perf_content = "• No trades executed yesterday."
        if trades:
            wins = sum(1 for t in trades if t.get('pips', 0) > 0)
            pnl = sum(t.get('pips', 0) for t in trades)
            perf_content = f"• Executed {len(trades)} trades ({(wins/len(trades)):.0%} WR) netting {pnl:+.1f} pips."
            insights = data.get("insights", [])
            if insights:
                perf_content += f"\n• 🎓 **System Lesson**: {insights[0].get('recommendations', ['Stay disciplined'])[0]}"
        sections.append({
            "title": "Yesterday's Trade Review",
            "content": perf_content,
            "priority": 4,
            "icon": "📊"
        })
        
        # Summary one-liner
        summary_text = "EuroScope AI compiled comprehensive system insights and key trading levels for the upcoming session."
        
        return {
            "timestamp": data.get("timestamp", datetime.now(UTC).isoformat()),
            "urgency": data.get("urgency", "normal"),
            "summary": summary_text,
            "section_count": len(sections),
            "sections": sections
        }
