"""
Evolution Tracker — Measures how system performance improves as it learns.
Phase 3D implementation.
"""

import logging
from datetime import datetime, UTC, timedelta
from typing import Dict, Any, List

from ..data.storage import Storage

logger = logging.getLogger("euroscope.analytics.evolution")

class EvolutionTracker:
    """
    Monitors the 'Learning Curve' of the system by comparing performance 
    before and after key learning milestones.
    """
    
    def __init__(self, storage: Storage = None):
        self.storage = storage or Storage()
        
    def get_evolution_report(self) -> str:
        """
        Generates a summary of how the system has improved over time.
        """
        # 1. Prediction Accuracy Trend (Last 30 days vs 7 days)
        acc_30d = self.storage.get_accuracy_stats(days=30)
        acc_7d = self.storage.get_accuracy_stats(days=7)
        
        # 2. Insights adoption rate
        insights = self.storage.get_recent_learning_insights(limit=100)
        total_insights = len(insights)
        applied_insights = sum(1 for i in insights if i.get('accuracy', 0) > 0.8) # Simple proxy for 'successful' learning
        
        # 3. Parameter Stability (proxy for convergence)
        # In a full implementation, we'd track how often parameters changed
        
        return self._format_evolution_report(
            acc_30d=acc_30d,
            acc_7d=acc_7d,
            total_insights=total_insights,
            applied_insights=applied_insights
        )

    def _format_evolution_report(self, acc_30d: Dict, acc_7d: Dict, total_insights: int, applied_insights: int) -> str:
        """Formats the evolution metrics into a Markdown report."""
        acc_long = acc_30d.get('accuracy', 0)
        acc_short = acc_7d.get('accuracy', 0)
        diff = acc_short - acc_long
        trend_emoji = "📈" if diff > 0 else "📉" if diff < 0 else "⏺️"
        
        lines = [
            "🧬 <b>EuroScope Evolution Tracker</b>\n",
            f"<b>Intelligence Growth:</b>",
            f"• 30d Accuracy: {acc_long:.1f}%",
            f"• 7d Accuracy: {acc_short:.1f}% ({trend_emoji} {diff:+.1f}%)",
            "",
            f"<b>Learning Intensity:</b>",
            f"• Extracted Insights: {total_insights}",
            f"• High-Conf Lessons: {applied_insights}",
            "",
            f"<b>Milestones:</b>"
        ]
        
        if total_insights > 50:
            lines.append("• 🏆 <i>Veteran:</i> System has processed 50+ learning cycles.")
        elif total_insights > 10:
            lines.append("• 🎓 <i>Adapting:</i> Qualitative feedback loop is active.")
        else:
            lines.append("• 🥚 <i>Initial:</i> Learning loop warming up.")
            
        lines.append("\n<i>— Continuous self-improvement active.</i>")
        
        return "\n".join(lines)
