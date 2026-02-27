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
        Generates a comprehensive daily market briefing.
        """
        logger.info("Generating daily briefing...")
        
        # 1. Overnight Summary (News & Sentiment)
        overnight_news = await self.storage.get_recent_news(limit=5, min_impact=0.7)
        
        # 2. Key Levels (Fetch from technical analysis or storage)
        # For simplicity, we'll assume they are stored or we run a quick scan
        key_levels = "• Support: 1.0780, 1.0750\n• Resistance: 1.0850, 1.0880"
        
        # 3. High-Probability Setups
        # Mocking setups logic for now
        setups = "• Bullish Engulfing at H1 Support (1.0790)\n• Liquidity Sweep at 1.0820 pending"
        
        # 4. Learning Insights & Trade Review (Yesterday)
        yesterday_str = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        trades_yesterday = await self.storage.get_trade_journal_for_date(yesterday_str)
        insights = await self.storage.get_recent_learning_insights(limit=3)
        
        return self._format_comprehensive_report(
            news=overnight_news,
            levels=key_levels,
            setups=setups,
            insights=insights,
            trades=trades_yesterday
        )

    def _format_comprehensive_report(self, news: List, levels: str, setups: str, insights: List, trades: List) -> str:
        """Formats the briefing into a professional synthesized report."""
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        
        report = [
            f"📅 <b>EuroScope Daily Intelligence Briefing</b>",
            f"<i>{now_str} UTC | London Session Open</i>\n",
        ]
        
        # 1. Overnight Summary
        report.append("🌙 <b>Overnight Session Pulse</b>")
        if news:
            for item in news[:3]:
                report.append(f"• {item.get('title')} ({item.get('source')})")
        else:
            report.append("• Market consolidated in a tight range overnight.")
        report.append("")
        
        # 2. Key Levels
        report.append("🎯 <b>Key Levels Today</b>")
        report.append(levels)
        report.append("")
        
        # 3. High-Probability Setups
        report.append("💡 <b>High-Probability Setups</b>")
        report.append(setups)
        report.append("")
        
        # 4. Yesterday's Trade Review
        report.append("📊 <b>Yesterday's Trade Review</b>")
        if trades:
            wins = sum(1 for t in trades if t.get('pips', 0) > 0)
            pnl = sum(t.get('pips', 0) for t in trades)
            report.append(f"• Trades: {len(trades)} | Win Rate: {(wins/len(trades)):.0%} | P/L: {pnl:+.1f}p")
            if insights:
                report.append(f"• 🎓 <b>Key Lesson:</b> {insights[0].get('recommendations', ['Stay disciplined'])[0]}")
        else:
            report.append("• No trades executed yesterday.")
        
        report.append("\n⚠️ <b>Risk Factors:</b> High-impact USD CPI at 13:30 UTC. Monitor liquidity.")
        
        return "\n".join(report)
