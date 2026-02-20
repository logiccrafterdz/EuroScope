"""
Multi-Timeframe Confluence Skill

Analyzes EUR/USD across M15, H1, H4, D1 timeframes simultaneously
to find alignment signals for higher-confidence trading decisions.
"""

import logging
from datetime import datetime, UTC

from ...analysis.technical import TechnicalAnalyzer
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult

logger = logging.getLogger("euroscope.skills.multi_timeframe_confluence")

TIMEFRAMES = ["M15", "H1", "H4", "D1"]

# Weight higher timeframes more heavily
TF_WEIGHTS = {
    "M15": 0.15,
    "H1": 0.25,
    "H4": 0.30,
    "D1": 0.30,
}


class MultiTimeframeConfluenceSkill(BaseSkill):
    name = "multi_timeframe_confluence"
    description = "Analyzes EUR/USD across M15/H1/H4/D1 for confluence signals"
    emoji = "🔀"
    category = SkillCategory.ANALYSIS
    version = "1.0.0"
    capabilities = ["confluence", "check_alignment"]

    def __init__(self):
        super().__init__()
        self.technical = TechnicalAnalyzer()
        self._provider = None

    def set_price_provider(self, provider):
        self._provider = provider

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "confluence":
            return await self._full_confluence(context, **params)
        elif action == "check_alignment":
            return await self._check_alignment(context, **params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _full_confluence(self, context: SkillContext, **params) -> SkillResult:
        """Run full multi-timeframe confluence analysis."""
        if not self._provider:
            return SkillResult(success=False, error="No price provider configured")

        timeframes = params.get("timeframes", TIMEFRAMES)
        tf_results = {}
        errors = []

        for tf in timeframes:
            try:
                df = await self._provider.get_candles(timeframe=tf, count=200)
                if df is None or (hasattr(df, 'empty') and df.empty) or len(df) < 50:
                    errors.append(f"{tf}: insufficient data ({len(df) if df is not None else 0} candles)")
                    continue

                ta = self.technical.analyze(df)
                if "error" in ta:
                    errors.append(f"{tf}: {ta['error']}")
                    continue

                tf_results[tf] = self._extract_signals(ta, tf)
            except Exception as e:
                errors.append(f"{tf}: {e}")
                logger.warning(f"MTF: {tf} analysis failed: {e}")

        if not tf_results:
            return SkillResult(
                success=False,
                error=f"No timeframes analyzed successfully. Errors: {'; '.join(errors)}"
            )

        # Compute confluence
        confluence = self._compute_confluence(tf_results)
        confluence["errors"] = errors
        confluence["analyzed_at"] = datetime.now(UTC).isoformat()

        # Store in context
        context.analysis["confluence"] = confluence
        context.metadata["mtf_bias"] = confluence["verdict"]
        context.metadata["mtf_confidence"] = confluence["confidence"]

        formatted = self._format_confluence(confluence)
        return SkillResult(
            success=True,
            data=confluence,
            metadata={"formatted": formatted},
            next_skill="trading_strategy",
        )

    async def _check_alignment(self, context: SkillContext, **params) -> SkillResult:
        """Quick alignment check — lighter than full confluence."""
        result = await self._full_confluence(context, **params)
        if not result.success:
            return result

        alignment = result.data["verdict"]
        return SkillResult(
            success=True,
            data={"aligned": alignment != "MIXED", "direction": alignment},
            metadata=result.metadata,
        )

    def _extract_signals(self, ta: dict, timeframe: str) -> dict:
        """Extract directional signals from technical analysis output."""
        indicators = ta.get("indicators", {})

        # RSI signal
        rsi_data = indicators.get("RSI", {})
        rsi_value = rsi_data.get("value", 50)
        if rsi_value > 60:
            rsi_signal = "BULLISH"
        elif rsi_value < 40:
            rsi_signal = "BEARISH"
        else:
            rsi_signal = "NEUTRAL"

        # MACD signal
        macd_data = indicators.get("MACD", {})
        macd_text = str(macd_data.get("signal_text", "")).lower()
        if "bullish" in macd_text:
            macd_signal = "BULLISH"
        elif "bearish" in macd_text:
            macd_signal = "BEARISH"
        else:
            macd_signal = "NEUTRAL"

        # EMA trend
        ema_data = indicators.get("EMA", {})
        ema_trend = str(ema_data.get("trend", "")).lower()
        if "bull" in ema_trend or "up" in ema_trend:
            ema_signal = "BULLISH"
        elif "bear" in ema_trend or "down" in ema_trend:
            ema_signal = "BEARISH"
        else:
            ema_signal = "NEUTRAL"

        # ADX strength
        adx_data = indicators.get("ADX", {})
        adx_value = adx_data.get("value", 0)
        trending = adx_value > 25 if isinstance(adx_value, (int, float)) else False

        # Overall bias
        overall = str(ta.get("overall_bias", "Neutral")).upper()

        return {
            "timeframe": timeframe,
            "rsi": {"value": rsi_value, "signal": rsi_signal},
            "macd": {"signal": macd_signal},
            "ema": {"signal": ema_signal, "trend": ema_trend},
            "adx": {"value": adx_value, "trending": trending},
            "overall_bias": overall,
        }

    def _compute_confluence(self, tf_results: dict) -> dict:
        """Compute weighted confluence score from all timeframe results."""
        bullish_score = 0.0
        bearish_score = 0.0
        total_weight = 0.0
        details = {}

        for tf, signals in tf_results.items():
            weight = TF_WEIGHTS.get(tf, 0.2)
            total_weight += weight
            bias = signals["overall_bias"]

            # Score each indicator
            tf_bullish = 0
            tf_bearish = 0
            for indicator in ["rsi", "macd", "ema"]:
                sig = signals.get(indicator, {}).get("signal", "NEUTRAL")
                if sig == "BULLISH":
                    tf_bullish += 1
                elif sig == "BEARISH":
                    tf_bearish += 1

            # Weight by trend strength (ADX)
            strength_multiplier = 1.2 if signals["adx"]["trending"] else 0.8

            if tf_bullish > tf_bearish:
                tf_direction = "BULLISH"
                bullish_score += weight * strength_multiplier
            elif tf_bearish > tf_bullish:
                tf_direction = "BEARISH"
                bearish_score += weight * strength_multiplier
            else:
                tf_direction = "NEUTRAL"

            details[tf] = {
                "direction": tf_direction,
                "bullish_indicators": tf_bullish,
                "bearish_indicators": tf_bearish,
                "trending": signals["adx"]["trending"],
                "adx": signals["adx"]["value"],
                "weight": weight,
                "signals": signals,
            }

        # Normalize
        if total_weight > 0:
            bullish_score /= total_weight
            bearish_score /= total_weight

        # Determine verdict
        if bullish_score > bearish_score and bullish_score > 0.5:
            verdict = "BULLISH"
        elif bearish_score > bullish_score and bearish_score > 0.5:
            verdict = "BEARISH"
        else:
            verdict = "MIXED"

        # Confidence = how strongly aligned
        alignment = abs(bullish_score - bearish_score)
        num_aligned = sum(
            1 for d in details.values()
            if d["direction"] == verdict and verdict != "MIXED"
        )
        confidence = min(95, round(alignment * 100 + num_aligned * 5))

        return {
            "verdict": verdict,
            "confidence": confidence,
            "bullish_score": round(bullish_score, 3),
            "bearish_score": round(bearish_score, 3),
            "alignment": round(alignment, 3),
            "timeframes_analyzed": len(tf_results),
            "timeframes_aligned": num_aligned,
            "details": details,
        }

    def _format_confluence(self, data: dict) -> str:
        """Format confluence analysis for Telegram display."""
        verdict = data["verdict"]
        icon = {"BULLISH": "🟢", "BEARISH": "🔴"}.get(verdict, "⚪")

        lines = [
            f"🔀 *Multi-Timeframe Confluence*",
            f"Verdict: {icon} *{verdict}* ({data['confidence']}% confidence)",
            f"Alignment: {data['timeframes_aligned']}/{data['timeframes_analyzed']} timeframes",
            "",
        ]

        for tf, detail in data["details"].items():
            dir_icon = {"BULLISH": "🟢", "BEARISH": "🔴"}.get(detail["direction"], "⚪")
            trend = "📈" if detail["trending"] else "➡️"
            lines.append(
                f"  {trend} *{tf}*: {dir_icon} {detail['direction']} "
                f"(B:{detail['bullish_indicators']} vs R:{detail['bearish_indicators']})"
            )

        if data.get("errors"):
            lines.append(f"\n⚠️ Skipped: {', '.join(data['errors'][:2])}")

        return "\n".join(lines)
