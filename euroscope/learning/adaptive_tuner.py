"""
Adaptive Parameter Tuner — Auto-adjusts strategy parameters
based on trade journal performance data.
"""

import logging
from typing import Any

from ..data.storage import Storage

logger = logging.getLogger("euroscope.learning.adaptive_tuner")


# Default parameter bounds (guardrails)
PARAM_BOUNDS = {
    "rsi_oversold": (20, 40),
    "rsi_overbought": (60, 80),
    "adx_threshold": (15, 35),
    "confidence_threshold": (40, 80),
    "stop_loss_pips": (10, 50),
    "take_profit_pips": (15, 100),
    "risk_per_trade_pct": (0.5, 3.0),
}


class AdaptiveTuner:
    """
    Analyzes trade journal performance and recommends parameter adjustments.

    - Reads closed trades from Storage
    - Groups by strategy
    - Calculates optimal thresholds based on historical win rates
    - Respects guardrail bounds on all parameters
    """

    def __init__(self, storage: Storage = None):
        self.storage = storage or Storage()

    def analyze(self, strategy: str = None) -> dict:
        """
        Analyze trade performance and generate tuning recommendations.

        Returns dict with current stats and adjustment suggestions.
        """
        stats = self.storage.get_trade_journal_stats(strategy)

        if stats["total"] < 5:
            return {
                "ready": False,
                "message": f"Need at least 5 trades to tune (have {stats['total']})",
                "stats": stats,
                "recommendations": [],
            }

        recommendations = []
        
        # 1. Qualitative Learning Analysis (Phase 3B)
        insights = self.storage.get_recent_learning_insights(limit=10)
        factors_count = {}
        for insight in insights:
            for factor in insight.get("factors", []):
                factors_count[factor] = factors_count.get(factor, 0) + 1
        
        if factors_count.get("regime_misidentification", 0) >= 2:
            recommendations.append({
                "param": "regime_sensitivity",
                "action": "increase",
                "reason": "Frequent regime misidentification detected in recent trades",
                "suggested_change": "+10%",
            })
            
        if factors_count.get("incomplete_fundamental_data", 0) >= 2:
            recommendations.append({
                "param": "data_quality_threshold",
                "action": "increase",
                "reason": "Trades failing due to incomplete macro data",
                "suggested_change": "Require 'complete' quality",
            })

        if factors_count.get("liquidity_analysis_error", 0) >= 2:
            recommendations.append({
                "param": "liquidity_volume_threshold",
                "action": "increase",
                "reason": "Liquidity analysis error detected — require stronger volume confirmation",
                "suggested_change": "+5%",
            })

        # 2. Win rate analysis
        if stats["win_rate"] < 40:
            recommendations.append({
                "param": "confidence_threshold",
                "action": "increase",
                "reason": f"Low win rate ({stats['win_rate']}%) — raise entry bar",
                "suggested_change": "+5",
            })
        elif stats.get("win_rate", 0) > 70:
            recommendations.append({
                "param": "confidence_threshold",
                "action": "decrease",
                "reason": f"High win rate ({stats['win_rate']}%) — capture more opportunities",
                "suggested_change": "-5",
            })

        # 2. P/L analysis
        if stats.get("avg_pnl", 0) < -5:
            recommendations.append({
                "param": "stop_loss_pips",
                "action": "tighten",
                "reason": f"Negative avg P/L ({stats['avg_pnl']:+.1f}p) — tighten stops",
                "suggested_change": "-5",
            })

        if stats["avg_pnl"] > 15:
            recommendations.append({
                "param": "take_profit_pips",
                "action": "widen",
                "reason": f"Strong avg P/L ({stats['avg_pnl']:+.1f}p) — allow more upside",
                "suggested_change": "+10",
            })

        # 3. Strategy-specific analysis
        by_strat = stats.get("by_strategy", {})
        for strat_name, strat_data in by_strat.items():
            if strat_data["total"] >= 3:
                if strat_data["win_rate"] < 30:
                    recommendations.append({
                        "param": f"{strat_name}_weight",
                        "action": "reduce",
                        "reason": f"Strategy '{strat_name}' underperforming ({strat_data['win_rate']}% WR)",
                        "suggested_change": "-0.1",
                    })
                elif strat_data["win_rate"] > 70:
                    recommendations.append({
                        "param": f"{strat_name}_weight",
                        "action": "increase",
                        "reason": f"Strategy '{strat_name}' outperforming ({strat_data['win_rate']}% WR)",
                        "suggested_change": "+0.1",
                    })

        return {
            "ready": True,
            "stats": stats,
            "recommendations": recommendations,
            "message": f"{len(recommendations)} tuning suggestions based on {stats['total']} trades",
        }

    def apply_adjustment(self, param: str, current_value: float,
                          delta: float) -> float:
        """
        Apply an adjustment respecting guardrail bounds.

        Returns the new clamped value.
        """
        new_value = current_value + delta
        bounds = PARAM_BOUNDS.get(param)
        if bounds:
            new_value = max(bounds[0], min(bounds[1], new_value))
        return round(new_value, 2)

    def format_report(self, strategy: str = None) -> str:
        """Generate a human-readable tuning report."""
        result = self.analyze(strategy)

        if not result["ready"]:
            return f"⚙️ *Adaptive Tuner*\n\n{result['message']}"

        lines = [
            "⚙️ *Adaptive Tuner Report*\n",
            f"Based on {result['stats']['total']} trades "
            f"({result['stats']['win_rate']}% WR, "
            f"{result['stats']['total_pnl']:+.1f}p total)\n",
        ]

        if result["recommendations"]:
            lines.append("*Recommendations:*")
            for rec in result["recommendations"]:
                lines.append(
                    f"  {'📈' if rec['action'] in ('increase', 'widen') else '📉'} "
                    f"`{rec['param']}` → {rec['action']} ({rec['suggested_change']})\n"
                    f"    _{rec['reason']}_"
                )
        else:
            lines.append("✅ All parameters look optimal — no changes recommended.")

        return "\n".join(lines)
