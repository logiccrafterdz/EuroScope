import logging
from typing import Optional

from ...data.cot import COTProvider
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult

logger = logging.getLogger("euroscope.skills.cot_positioning")


class COTPositioningSkill(BaseSkill):
    name = "cot_positioning"
    description = "Retrieves CFTC Net Positioning and provides 3-stage institutional filter for EUR/USD"
    emoji = "🏦"
    category = SkillCategory.ANALYSIS
    version = "2.0.0"
    capabilities = ["get_net_positioning", "filter_signal"]

    def __init__(self):
        super().__init__()
        self.provider = COTProvider()
        self._positioning_cache: Optional[dict] = None

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "get_net_positioning":
            return await self._get_positioning(context)
        elif action == "filter_signal":
            return await self._filter_signal(context, **params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _get_positioning(self, context: SkillContext) -> SkillResult:
        try:
            positioning = await self.provider.get_latest_positioning()
            if "error" in positioning:
                return SkillResult(success=False, error=positioning["error"])

            net_positions = positioning["non_commercial"]["net"]
            bias = positioning["non_commercial"]["bias"]
            
            confidence = min(100.0, abs(net_positions) / 50000 * 100)
            
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

            self._positioning_cache = {
                "report_date": positioning["report_date"],
                "non_commercial": {
                    "long": positioning["non_commercial"].get("long", 0),
                    "short": positioning["non_commercial"].get("short", 0),
                    "net": net_positions,
                    "bias": bias,
                },
                "commercial": positioning.get("commercial", {}),
                "raw_timestamp": positioning.get("raw_timestamp", ""),
            }

            if "fundamental" not in context.analysis:
                context.analysis["fundamental"] = {}
            context.analysis["fundamental"]["cot_positioning"] = {
                "report_date": positioning["report_date"],
                "net_positions": net_positions,
                "bias": bias,
                "confidence": confidence,
            }

            return SkillResult(
                success=True,
                data=result_data,
                metadata={"formatted": formatted}
            )
        except Exception as e:
            logger.error(f"COT positioning execution failed: {e}")
            return SkillResult(success=False, error=str(e))

    async def _filter_signal(self, context: SkillContext, **params) -> SkillResult:
        """
        3-Stage COT Filter Pipeline:

        Stage 1: Extreme Positioning Detection
            Classify net speculative position as extreme (>90th or <10th percentile)
            based on historical distribution.

        Stage 2: Macro Confirmation
            Check if macro data supports the contrarian view.
            Extreme bullish positioning + weak macro = potential reversal.

        Stage 3: Orderflow Timing
            Only trigger when microstructure confirms (liquidity sweep, volume expansion).
        """
        try:
            positioning = self._positioning_cache
            if not positioning:
                positioning = await self.provider.get_latest_positioning()
                if "error" in positioning:
                    return SkillResult(success=False, error=positioning["error"])
                self._positioning_cache = positioning

            net_positions = positioning.get("non_commercial", {}).get("net", 0)
            signal_direction = params.get("direction", "").upper()

            stage1 = self._stage1_extreme_detection(net_positions)
            stage2 = self._stage2_macro_confirmation(context, stage1)
            stage3 = self._stage3_orderflow_timing(context, stage1)

            combined_confidence = (
                stage1["confidence"] * 0.4 +
                stage2["confidence"] * 0.35 +
                stage3["confidence"] * 0.25
            )

            if stage1["is_extreme"] and stage2["confirmed"]:
                if stage3["timing_ok"]:
                    action = "contrarian_signal"
                    adjusted_confidence = min(95, combined_confidence + 15)
                else:
                    action = "wait_for_timing"
                    adjusted_confidence = combined_confidence * 0.7
            elif stage1["is_extreme"] and not stage2["confirmed"]:
                action = "no_filter"
                adjusted_confidence = combined_confidence
            else:
                action = "no_filter"
                adjusted_confidence = combined_confidence

            formatted = self._format_filter_report(
                stage1, stage2, stage3, action, adjusted_confidence
            )

            result_data = {
                "stage1": stage1,
                "stage2": stage2,
                "stage3": stage3,
                "action": action,
                "combined_confidence": round(adjusted_confidence, 1),
                "net_positions": net_positions,
            }

            return SkillResult(
                success=True,
                data=result_data,
                metadata={"formatted": formatted}
            )
        except Exception as e:
            logger.error(f"COT filter failed: {e}")
            return SkillResult(success=False, error=str(e))

    @staticmethod
    def _stage1_extreme_detection(net_positions: int) -> dict:
        """
        Stage 1: Detect extreme positioning.

        Historical ranges for EUR/USD Euro FX:
        - Bullish extreme: net > +100,000 contracts
        - Bearish extreme: net < -100,000 contracts
        - Normal: between -100k and +100k
        """
        bullish_threshold = 100000
        bearish_threshold = -100000

        if net_positions > bullish_threshold:
            is_extreme = True
            direction = "bullish_extreme"
            confidence = min(100, (net_positions - bullish_threshold) / 50000 * 100 + 60)
        elif net_positions < bearish_threshold:
            is_extreme = True
            direction = "bearish_extreme"
            confidence = min(100, (bearish_threshold - net_positions) / 50000 * 100 + 60)
        else:
            is_extreme = False
            direction = "normal"
            distance_from_nearest = min(
                abs(net_positions - bullish_threshold),
                abs(net_positions - bearish_threshold)
            )
            confidence = max(20, 60 - distance_from_nearest / 5000)

        return {
            "is_extreme": is_extreme,
            "direction": direction,
            "confidence": round(confidence, 1),
            "net_positions": net_positions,
        }

    @staticmethod
    def _stage2_macro_confirmation(context: SkillContext, stage1: dict) -> dict:
        """
        Stage 2: Check if macro context supports contrarian view.

        If COT shows extreme bullish positioning, we expect:
        - Weak macro data OR overbought technicals → supports reversal (contrarian)

        If COT shows extreme bearish positioning, we expect:
        - Strong macro data OR oversold technicals → supports reversal (contrarian)
        """
        if not stage1["is_extreme"]:
            return {"confirmed": False, "confidence": 50, "reason": "no_extreme_positioning"}

        fundamental = context.analysis.get("fundamental", {})
        macro_quality = context.metadata.get("macro_quality", "unknown")

        indicators = []
        has_macro = macro_quality in ("complete", "good")

        volatility = context.metadata.get("volatility", context.metadata.get("volatility_regime", "normal"))
        if volatility in ("high", "extreme"):
            indicators.append("high_volatility")

        uncertainty = context.metadata.get("composite_uncertainty", 0)
        if uncertainty and float(uncertainty) > 0.6:
            indicators.append("high_uncertainty")

        confirmed = len(indicators) >= 1 and has_macro
        confidence = 50
        if confirmed:
            confidence = min(90, 50 + len(indicators) * 20)
        elif has_macro:
            confidence = 40

        return {
            "confirmed": confirmed,
            "confidence": round(confidence, 1),
            "indicators": indicators,
            "has_macro": has_macro,
        }

    @staticmethod
    def _stage3_orderflow_timing(context: SkillContext, stage1: dict) -> dict:
        """
        Stage 3: Check microstructure timing.

        Look for:
        - Liquidity sweep detected
        - Volume expansion
        - Regime transition
        """
        if not stage1["is_extreme"]:
            return {"timing_ok": False, "confidence": 50, "reason": "no_extreme_positioning"}

        microstructure = context.analysis.get("microstructure", {})
        liquidity_sweep = microstructure.get("liquidity_sweep_detected", False)
        volume_expansion = microstructure.get("volume_expansion", False)

        regime = context.metadata.get("session_regime", "unknown")
        regime_transition = regime in ("london_open", "ny_open", "overlap")

        indicators = []
        if liquidity_sweep:
            indicators.append("liquidity_sweep")
        if volume_expansion:
            indicators.append("volume_expansion")
        if regime_transition:
            indicators.append("session_transition")

        timing_ok = len(indicators) >= 1
        confidence = 50 + len(indicators) * 15

        return {
            "timing_ok": timing_ok,
            "confidence": min(95, round(confidence, 1)),
            "indicators": indicators,
        }

    @staticmethod
    def _format_filter_report(stage1: dict, stage2: dict, stage3: dict,
                              action: str, confidence: float) -> str:
        lines = ["🏦 *COT 3-Stage Filter*"]

        e1 = "🔴" if "bearish" in stage1["direction"] else "🟢" if "bullish" in stage1["direction"] else "⚪"
        lines.append(f"  Stage 1: {e1} {stage1['direction'].replace('_', ' ').upper()} ({stage1['confidence']:.0f}%)")

        e2 = "✅" if stage2["confirmed"] else "❌"
        lines.append(f"  Stage 2: {e2} Macro {'CONFIRMED' if stage2['confirmed'] else 'NOT CONFIRMED'} ({stage2['confidence']:.0f}%)")

        e3 = "✅" if stage3["timing_ok"] else "⏳"
        lines.append(f"  Stage 3: {e3} Timing {'OK' if stage3['timing_ok'] else 'WAITING'} ({stage3['confidence']:.0f}%)")

        action_map = {
            "contrarian_signal": "🎯 CONTRARIAN SIGNAL READY",
            "wait_for_timing": "⏳ WAITING FOR TIMING",
            "no_filter": "➡️ NO FILTER (proceed normally)",
        }
        lines.append(f"\n  {action_map.get(action, action)}")
        lines.append(f"  Combined Confidence: `{confidence:.0f}%`")

        return "\n".join(lines)
