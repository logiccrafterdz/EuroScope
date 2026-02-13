"""
Orchestrator — Multi-Agent Coordinator

Runs all specialist agents and produces a weighted consensus analysis.
"""

import logging
from typing import Optional

from .specialists import (
    TechnicalSpecialist,
    FundamentalSpecialist,
    SentimentSpecialist,
    RiskSpecialist,
)

logger = logging.getLogger("euroscope.brain.orchestrator")


class Orchestrator:
    """
    Coordinates specialist agents and synthesizes their verdicts
    into a final consensus recommendation.
    """

    def __init__(self):
        self.technical = TechnicalSpecialist()
        self.fundamental = FundamentalSpecialist()
        self.sentiment = SentimentSpecialist()
        self.risk = RiskSpecialist()

    def run_analysis(self, market_context: dict) -> dict:
        """
        Run all specialists and produce a consensus.

        Args:
            market_context: dict with keys:
                - indicators: technical indicator data
                - patterns: detected chart patterns
                - levels: support/resistance levels
                - macro: fundamental data (rate diff, yield spread, cpi)
                - calendar: list of EconomicEvent objects
                - sentiment_summary: aggregated news sentiment
                - news_articles: list of recent articles

        Returns:
            {
                "consensus": {"verdict", "confidence", "reasoning"},
                "specialists": [verdict_dict, ...],
                "risk_assessment": verdict_dict,
                "formatted": str (Telegram-ready),
            }
        """
        # Run directional specialists
        tech_result = self._safe_run(self.technical, market_context)
        fund_result = self._safe_run(self.fundamental, market_context)
        sent_result = self._safe_run(self.sentiment, market_context)

        # Risk specialist gets other verdicts for conflict detection
        risk_context = dict(market_context)
        risk_context["other_verdicts"] = [tech_result, fund_result, sent_result]
        risk_result = self._safe_run(self.risk, risk_context)

        # Build weighted consensus from directional specialists
        specialists = [tech_result, fund_result, sent_result]
        consensus = self._calculate_consensus(specialists)

        # Adjust confidence based on risk assessment
        risk_confidence = risk_result.get("confidence", 50)
        if risk_confidence < 50:  # High risk
            consensus["confidence"] = max(consensus["confidence"] * 0.7, 20)
            consensus["risk_note"] = "⚠️ Elevated risk — confidence adjusted downward"

        result = {
            "consensus": consensus,
            "specialists": specialists,
            "risk_assessment": risk_result,
            "formatted": self._format_analysis(consensus, specialists, risk_result),
        }

        logger.info(
            f"Orchestrator consensus: {consensus['verdict']} "
            f"({consensus['confidence']:.0f}% confidence)"
        )

        return result

    def _safe_run(self, specialist, context: dict) -> dict:
        """Run a specialist with error handling."""
        try:
            return specialist.analyze(context)
        except Exception as e:
            logger.error(f"{specialist.name} specialist failed: {e}")
            return {
                "specialist": specialist.name,
                "verdict": "neutral",
                "confidence": 0,
                "reasoning": f"Error: {str(e)[:100]}",
                "key_points": [f"⚠️ {specialist.name} analysis failed"],
            }

    def _calculate_consensus(self, verdicts: list[dict]) -> dict:
        """
        Calculate weighted consensus from specialist verdicts.

        Weights: Technical 35%, Fundamental 30%, Sentiment 20%
        (Risk is handled separately)
        """
        weights = {
            "technical": 0.35,
            "fundamental": 0.30,
            "sentiment": 0.20,
        }

        # Convert verdicts to numeric scores
        verdict_scores = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}

        weighted_score = 0.0
        weighted_confidence = 0.0
        total_weight = 0.0
        reasoning_parts = []

        for v in verdicts:
            name = v.get("specialist", "unknown")
            weight = weights.get(name, 0.15)
            score = verdict_scores.get(v.get("verdict", "neutral"), 0.0)
            conf = v.get("confidence", 0)

            weighted_score += score * weight * (conf / 100)
            weighted_confidence += conf * weight
            total_weight += weight

            icon = "🟢" if v["verdict"] == "bullish" else "🔴" if v["verdict"] == "bearish" else "⚪"
            reasoning_parts.append(f"{icon} {name.title()}: {v['verdict']} ({conf:.0f}%)")

        if total_weight > 0:
            weighted_score /= total_weight
            weighted_confidence /= total_weight

        # Determine final verdict
        if weighted_score > 0.15:
            verdict = "bullish"
        elif weighted_score < -0.15:
            verdict = "bearish"
        else:
            verdict = "neutral"

        return {
            "verdict": verdict,
            "confidence": round(weighted_confidence, 1),
            "score": round(weighted_score, 3),
            "reasoning": " | ".join(reasoning_parts),
        }

    def _format_analysis(self, consensus: dict, specialists: list[dict],
                         risk: dict) -> str:
        """Format the full analysis for Telegram display."""
        verdict = consensus["verdict"]
        confidence = consensus["confidence"]

        if verdict == "bullish":
            icon = "🟢"
            direction = "BULLISH"
        elif verdict == "bearish":
            icon = "🔴"
            direction = "BEARISH"
        else:
            icon = "⚪"
            direction = "NEUTRAL"

        lines = [
            f"🤖 *Multi-Agent Analysis*\n",
            f"{icon} **Consensus: {direction}** ({confidence:.0f}% confidence)\n",
        ]

        # Per-specialist breakdown
        lines.append("📊 *Specialist Breakdown:*")
        for s in specialists:
            s_icon = "🟢" if s["verdict"] == "bullish" else "🔴" if s["verdict"] == "bearish" else "⚪"
            lines.append(f"  {s_icon} *{s['specialist'].title()}* — {s['verdict']} ({s['confidence']:.0f}%)")
            for point in s.get("key_points", [])[:3]:
                lines.append(f"      • {point}")

        # Risk assessment
        lines.append(f"\n🛡️ *Risk Assessment:* ({risk['confidence']:.0f}% safe)")
        for point in risk.get("key_points", [])[:4]:
            lines.append(f"  {point}")

        # Risk note if present
        risk_note = consensus.get("risk_note")
        if risk_note:
            lines.append(f"\n{risk_note}")

        return "\n".join(lines)
