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
    
    def __init__(self, storage: Storage = None):
        self.storage = storage or Storage()
        
    async def generate_briefing(self) -> str:
        """
        Generates a comprehensive daily briefing report.
        """
        logger.info("Generating daily briefing...")
        
        # 1. Fetch overnight market sentiment and data
        overnight_news = self.storage.get_recent_news(limit=5, min_impact=0.7)
        overnight_notes = self.storage.get_recent_notes(limit=3)
        
        # 2. Fetch learning insights from yesterday
        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        learning_insights = self.storage.get_recent_learning_insights(limit=5)
        
        # 3. Fetch performance metrics
        stats = self.storage.get_trade_journal_stats()
        
        # 4. Fetch system health
        monitor = HealthMonitor(storage=self.storage)
        health = await monitor.full_check_async()
        
        return self._format_markdown_report(
            news=overnight_news,
            notes=overnight_notes,
            insights=learning_insights,
            stats=stats,
            health=health
        )

    def _format_markdown_report(self, news: List, notes: List, insights: List, stats: Dict, health: Any) -> str:
        """Formats the collected data into a clean Markdown string."""
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        
        report = [
            f"📅 <b>EuroScope Daily Proactive Plan</b>",
            f"<i>Report generated at {now_str} UTC</i>\n",
        ]
        
        # --- Section: Overnight pulse ---
        report.append("🌐 <b>Overnight Market Pulse</b>")
        if news:
            for item in news:
                sentiment_emoji = "🟢" if item.get('sentiment') == 'bullish' else "🔴" if item.get('sentiment') == 'bearish' else "⚪"
                report.append(f"• {sentiment_emoji} {item.get('title')} ({item.get('source')})")
        else:
            report.append("• No high-impact overnight news detected.")
        report.append("")
        
        # --- Section: Active Learning ---
        report.append("🎓 <b>Active Learning & Evolution</b>")
        if insights:
            for insight in insights[:3]:
                rec = insight.get('recommendations', [])
                if rec:
                    report.append(f"• 💡 <i>Lesson from trade #{insight.get('trade_id')}:</i> {rec[0]}")
        else:
            report.append("• Continuous learning loop active. No new insights today.")
        report.append("")
        
        # --- Section: Performance & Health ---
        report.append("📊 <b>Performance & Health</b>")
        report.append(f"• Win Rate: {stats.get('win_rate', 0)}% ({stats.get('total', 0)} trades)")
        report.append(f"• P/L: {stats.get('total_pnl', 0):+.1f} pips")
        status_emoji = "✅" if all(c.healthy for c in health.components) else "⚠️"
        report.append(f"• System Status: {status_emoji} Operational")
        report.append("")
        
        report.append("🎯 <b>Today's Focus:</b> EUR/USD liquidity sweeps and H4 trend alignment.")
        
        return "\n".join(report)
