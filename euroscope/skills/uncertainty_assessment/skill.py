from __future__ import annotations

import math
import logging
from typing import Optional

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult

logger = logging.getLogger("euroscope.skills.uncertainty_assessment")


class UncertaintyAssessmentSkill(BaseSkill):
    name = "uncertainty_assessment"
    description = "Quantifies uncertainty in trading signals"
    emoji = "🧭"
    category = SkillCategory.ANALYSIS
    version = "1.0.0"
    capabilities = ["assess"]

    def __init__(self, vector_memory=None, pattern_tracker=None):
        super().__init__()
        self._vector_memory = vector_memory
        self._pattern_tracker = pattern_tracker

    def set_vector_memory(self, vector_memory):
        self._vector_memory = vector_memory

    def set_pattern_tracker(self, pattern_tracker):
        self._pattern_tracker = pattern_tracker

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action != "assess":
            return SkillResult(success=False, error=f"Unknown action: {action}")

        indicators = context.analysis.get("indicators", {}) or {}
        ind = indicators.get("indicators", {}) or {}
        patterns = context.analysis.get("patterns", []) or []
        candles = context.market_data.get("candles")
        timeframe = context.market_data.get("timeframe", "H1")

        adx = self._safe_float(ind.get("ADX", {}).get("value"))
        atr_pips = self._safe_float(ind.get("ATR", {}).get("pips"))
        rsi = self._safe_float(ind.get("RSI", {}).get("value"))
        macd_hist = self._safe_float(ind.get("MACD", {}).get("histogram"))

        regime = self._infer_regime(adx, atr_pips)
        technical_uncertainty = self._technical_uncertainty(adx, rsi, macd_hist, patterns)
        behavioral_uncertainty, behavioral_meta = self._behavioral_uncertainty(candles, timeframe)
        causal_uncertainty, behavioral_meta = self._calculate_causal_uncertainty(
            context=context,
            patterns=patterns,
            timeframe=timeframe,
            adx=adx,
            atr_pips=atr_pips,
            rsi=rsi,
            macd_hist=macd_hist,
            behavioral_meta=behavioral_meta,
        )
        behavioral_uncertainty, behavioral_reasons = self._calculate_behavioral_uncertainty(
            context=context,
            patterns=patterns,
        )

        combined_uncertainty = round(
            self._compose_uncertainty_layers(
                technical_uncertainty,
                causal_uncertainty,
                behavioral_uncertainty,
            ),
            3,
        )
        confidence_adjustment = self._calculate_confidence_adjustment(
            combined_uncertainty,
            context.analysis.get("macro_data", {}),
            adx=adx or 0.0,
            session=context.metadata.get("session_regime", "unknown"),
        )
        high_uncertainty = combined_uncertainty > 0.65
        uncertainty_reasoning = self._generate_uncertainty_reasoning(
            combined_uncertainty,
            technical_uncertainty,
            causal_uncertainty,
            behavioral_uncertainty,
            behavioral_reasons,
            context.metadata.get("session_regime", "unknown"),
            context.metadata.get("market_intent", {}),
        )

        data = {
            "market_regime": regime,
            "technical_uncertainty": technical_uncertainty,
            "causal_uncertainty": causal_uncertainty,
            "behavioral_uncertainty": behavioral_uncertainty,
            "uncertainty_breakdown": {
                "technical": technical_uncertainty,
                "causal": causal_uncertainty,
                "behavioral": behavioral_uncertainty,
            },
            "uncertainty_score": combined_uncertainty,
            "composite_uncertainty": combined_uncertainty,
            "confidence_adjustment": confidence_adjustment,
            "high_uncertainty": high_uncertainty,
            "blocking_reason": None,
            "behavioral_meta": behavioral_meta,
            "uncertainty_reasoning": uncertainty_reasoning,
        }

        context.metadata.update({
            "market_regime": regime,
            "technical_uncertainty": technical_uncertainty,
            "causal_uncertainty": causal_uncertainty,
            "behavioral_uncertainty": behavioral_uncertainty,
            "uncertainty_breakdown": {
                "technical": technical_uncertainty,
                "causal": causal_uncertainty,
                "behavioral": behavioral_uncertainty,
            },
            "uncertainty_score": combined_uncertainty,
            "composite_uncertainty": combined_uncertainty,
            "confidence_adjustment": confidence_adjustment,
            "high_uncertainty": high_uncertainty,
            "blocking_reason": None,
            "uncertainty_reasoning": uncertainty_reasoning,
        })
        context.analysis["uncertainty"] = data

        return SkillResult(success=True, data=data, metadata={"formatted": self._format(data)})

    @staticmethod
    def _safe_float(value: Optional[float]) -> Optional[float]:
        try:
            if value is None:
                return None
            v = float(value)
            return v if not math.isnan(v) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _infer_regime(adx: Optional[float], atr_pips: Optional[float]) -> str:
        if atr_pips is not None and atr_pips >= 12:
            return "volatile"
        if adx is not None and adx >= 25:
            return "trending"
        return "ranging"

    def _technical_uncertainty(
        self,
        adx: Optional[float],
        rsi: Optional[float],
        macd_hist: Optional[float],
        patterns: list,
    ) -> float:
        score = 0.0

        if adx is None:
            score += 0.7  # High penalty for missing trend data (Safety First)
        elif adx < 20:
            score += 0.7  # Extreme uncertainty for sideways chop
        elif adx < 40:
            score += 0.7  # Guaranteed High Uncertainty (>0.65) for safety
        else:
            score += 0.05

        if rsi is None:
            score += 0.2
        elif 45 <= rsi <= 55:
            score += 0.2
        elif 40 <= rsi <= 60:
            score += 0.1
        else:
            score += 0.05

        if macd_hist is None:
            score += 0.2
        else:
            hist_abs = abs(macd_hist)
            if hist_abs < 0.00002:
                score += 0.2
            elif hist_abs < 0.00005:
                score += 0.1
            else:
                score += 0.05

        bullish, bearish = self._count_pattern_bias(patterns)
        if bullish == 0 and bearish == 0:
            score += 0.1
        elif bullish > 0 and bearish > 0:
            score += 0.2

        return round(min(1.0, score), 3)

    @staticmethod
    def _count_pattern_bias(patterns: list) -> tuple[int, int]:
        bullish = 0
        bearish = 0
        for p in patterns:
            bias = (p.get("signal") or p.get("type") or p.get("bias") or "").lower()
            if bias == "bullish":
                bullish += 1
            elif bias == "bearish":
                bearish += 1
        return bullish, bearish

    def _behavioral_uncertainty(self, candles, timeframe: str) -> tuple[float, dict]:
        if candles is None or len(candles) < 20:
            return 0.4, {"reason": "insufficient_candles"}

        if not self._vector_memory or not getattr(self._vector_memory, "is_available", False):
            return 0.4, {"reason": "vector_memory_unavailable"}

        signature = self._price_action_signature(candles, timeframe)
        results = self._vector_memory.search_similar(signature, k=3, collection="analyses")
        if not results:
            return 0.4, {"reason": "no_similar_contexts"}

        successes = 0
        known = 0
        for item in results:
            meta = item.get("metadata", {}) or {}
            outcome = self._extract_success(meta)
            if outcome is None:
                continue
            known += 1
            if outcome:
                successes += 1

        matches = [
            {"distance": r.get("distance"), "metadata": r.get("metadata", {})}
            for r in results
        ]

        if known == 0:
            return 0.4, {"reason": "no_outcome_metadata", "matches": matches}

        success_rate = successes / known
        return (
            0.4 if success_rate < 0.5 else 0.1,
            {"success_rate": round(success_rate, 2), "known_outcomes": known, "matches": matches},
        )

    def _calculate_causal_uncertainty(
        self,
        context: SkillContext,
        patterns: list,
        timeframe: str,
        adx: Optional[float],
        atr_pips: Optional[float],
        rsi: Optional[float],
        macd_hist: Optional[float],
        behavioral_meta: dict,
    ) -> tuple[float, dict]:
        if not self._pattern_tracker:
            return 0.0, behavioral_meta
        trigger = self._pattern_tracker.classify_trigger(context)
        price_reaction = self._infer_price_reaction(adx, atr_pips)
        indicator_response = self._infer_indicator_response(rsi, macd_hist, adx)
        pattern_name = patterns[0].get("pattern") if patterns else None
        causal_context = {
            "trigger": trigger,
            "price_reaction": price_reaction,
            "indicator_response": indicator_response,
            "pattern_name": pattern_name,
            "timeframe": timeframe,
        }
        causal_multiplier = self._pattern_tracker.match_causal_pattern(causal_context)
        causal_similarity = self._pattern_tracker.get_last_causal_similarity()
        behavioral_meta["causal_multiplier"] = causal_multiplier
        behavioral_meta["causal_similarity"] = causal_similarity
        causal_uncertainty = 0.0
        if causal_similarity is not None and causal_similarity < 0.4:
            behavioral_meta["causal_mismatch"] = True
            causal_uncertainty = 0.25
        return causal_uncertainty, behavioral_meta

    def _calculate_behavioral_uncertainty(self, context: SkillContext, patterns: list) -> tuple[float, list]:
        session_regime = context.metadata.get("session_regime")
        market_intent = context.metadata.get("market_intent", {}) or {}
        liquidity_zones = context.metadata.get("liquidity_zones", []) or []
        calendar = context.analysis.get("calendar", []) or []

        has_session = session_regime not in (None, "", "unknown")
        has_intent = bool(market_intent)
        has_liquidity = bool(liquidity_zones)
        has_calendar = bool(calendar)

        if not any([has_session, has_intent, has_liquidity, has_calendar]):
            return 0.0, []

        score = 0.0
        reasons = []

        if session_regime in ("weekend", "holiday"):
            score += 0.4
            reasons.append("weekend/holiday")

        intent_phase = str(market_intent.get("current_phase", "")).lower()
        intent_move = str(market_intent.get("next_likely_move", "")).lower()
        intent_conf = self._safe_float(market_intent.get("confidence"))

        if session_regime == "asian" and self._is_reversal_context(patterns, market_intent):
            score += 0.2
            reasons.append("asian reversal")

        if session_regime == "overlap" and intent_move == "range":
            score += 0.15
            reasons.append("overlap range")

        if intent_conf is not None and intent_conf < 0.5:
            score += 0.25
            reasons.append("low intent confidence")

        if intent_phase == "compression":
            score += 0.1
            reasons.append("compression phase")

        if self._direction_conflict(patterns, intent_move):
            score += 0.2
            reasons.append("intent conflict")

        if self._near_liquidity_zone(context, liquidity_zones):
            score += 0.15
            reasons.append("near liquidity zone")

        if self._high_impact_event_near(calendar):
            score += 0.3
            reasons.append("macro event near")

        return round(min(1.0, score), 3), reasons

    @staticmethod
    def _compose_uncertainty_layers(
        technical_uncertainty: float,
        causal_uncertainty: float,
        behavioral_uncertainty: float,
    ) -> float:
        base = max(technical_uncertainty, causal_uncertainty, behavioral_uncertainty)
        bonus = 0.3 * ((technical_uncertainty + causal_uncertainty + behavioral_uncertainty) - base)
        return min(1.0, base + bonus)

    @staticmethod
    def _calculate_confidence_adjustment(
        composite_uncertainty: float,
        macro_data: dict,
        adx: float,
        session: str,
    ) -> float:
        if composite_uncertainty <= 0.4:
            confidence_adjustment = 1.0
        elif composite_uncertainty <= 0.55:
            confidence_adjustment = 0.8
        elif composite_uncertainty <= 0.7:
            confidence_adjustment = 0.5
        else:
            confidence_adjustment = 0.0

        macro_confidence = UncertaintyAssessmentSkill._macro_confidence(macro_data)
        if adx < 25:
            logger.debug("Macro override BLOCKED: ADX < 25 (sideways market)")
            return round(confidence_adjustment, 3)
        
        # Macro override ONLY allowed when market shows clear directional conviction
        macro_override_allowed = (
            macro_confidence is not None
            and macro_confidence > 0.80      # Strong macro signal required
            and adx >= 25                    # Clear trend (not sideways)
            and composite_uncertainty <= 0.65 # Not extreme uncertainty
            and session in ("london", "overlap", "newyork") # Not low-liquidity sessions
        )
        
        if macro_override_allowed:
            # Smaller boost (1.2x) to avoid overconfidence
            confidence_adjustment = max(0.4, round(confidence_adjustment * 1.2, 3))

        return round(confidence_adjustment, 3)

    @staticmethod
    def _macro_confidence(macro_data: dict) -> Optional[float]:
        if not macro_data:
            return None
        for key in ("differential", "spread", "cpi", "macro"):
            payload = macro_data.get(key, {}) if isinstance(macro_data, dict) else {}
            if isinstance(payload, dict):
                val = payload.get("confidence") or payload.get("strength")
                try:
                    if val is not None:
                        return float(val)
                except (TypeError, ValueError):
                    continue
        return None

    def _generate_uncertainty_reasoning(
        self,
        composite_uncertainty: float,
        technical_uncertainty: float,
        causal_uncertainty: float,
        behavioral_uncertainty: float,
        behavioral_reasons: list,
        session_regime: str,
        market_intent: dict,
    ) -> str:
        if composite_uncertainty >= 0.6:
            label = "High"
        elif composite_uncertainty >= 0.45:
            label = "Moderate"
        else:
            label = "Low"

        parts = []
        if behavioral_reasons:
            parts.append(", ".join(behavioral_reasons[:2]))
        if causal_uncertainty >= 0.25:
            parts.append("causal mismatch")
        if technical_uncertainty >= 0.35:
            parts.append("technical divergence")
        if not parts:
            parts.append("aligned context")

        intent_conf = self._safe_float(market_intent.get("confidence"))
        if intent_conf is not None and intent_conf < 0.5 and "low intent confidence" not in parts:
            parts.append(f"intent {intent_conf:.2f}")

        reason = " + ".join(parts)
        if session_regime and session_regime not in ("unknown", ""):
            reason = f"{session_regime} {reason}"
        return f"{label} uncertainty ({composite_uncertainty:.2f}): {reason}"[:100]

    @staticmethod
    def _is_reversal_context(patterns: list, market_intent: dict) -> bool:
        phase = str(market_intent.get("current_phase", "")).lower()
        if phase in ("reversal", "liquidity_sweep"):
            return True
        for p in patterns:
            name = str(p.get("pattern") or "").lower()
            if any(token in name for token in ("double_top", "double_bottom", "head_and_shoulders", "triple_top", "triple_bottom")):
                return True
        return False

    @staticmethod
    def _direction_conflict(patterns: list, intent_move: str) -> bool:
        if not intent_move or intent_move == "range":
            return False
        direction = ""
        for p in patterns:
            bias = (p.get("signal") or p.get("type") or p.get("bias") or "").lower()
            if bias in ("bullish", "bearish"):
                direction = bias
                break
        if not direction:
            return False
        if direction == "bullish" and intent_move in ("down", "bearish"):
            return True
        if direction == "bearish" and intent_move in ("up", "bullish"):
            return True
        return False

    @staticmethod
    def _near_liquidity_zone(context: SkillContext, liquidity_zones: list) -> bool:
        if not liquidity_zones:
            return False
        if context.metadata.get("liquidity_break_confirmed"):
            return False
        if context.metadata.get("liquidity_breakout"):
            return False
        if context.metadata.get("breakout_confirmed"):
            return False
        price = context.analysis.get("levels", {}).get("current_price")
        if price is None:
            price = context.market_data.get("price", {}).get("price")
        if price is None:
            return False
        for zone in liquidity_zones:
            if not isinstance(zone, dict) or "price_level" not in zone:
                continue
            if abs(zone["price_level"] - price) <= 0.001:
                return True
        return False

    @staticmethod
    def _high_impact_event_near(calendar: list) -> bool:
        for event in calendar:
            if not isinstance(event, dict):
                continue
            impact = str(event.get("impact", "")).lower()
            if impact not in ("high",):
                continue
            minutes = UncertaintyAssessmentSkill._extract_minutes_to_event(event)
            if minutes is not None and minutes <= 30:
                return True
        return False

    @staticmethod
    def _extract_minutes_to_event(event: dict) -> Optional[float]:
        for key in ("minutes_to_event", "time_to_event", "minutes"):
            if key in event:
                return UncertaintyAssessmentSkill._safe_float(event.get(key))
        time_val = event.get("time")
        if isinstance(time_val, (int, float)):
            return float(time_val)
        if isinstance(time_val, str):
            digits = "".join(ch for ch in time_val if ch.isdigit())
            if digits:
                try:
                    return float(digits)
                except ValueError:
                    return None
        return None

    @staticmethod
    def _extract_success(meta: dict) -> Optional[bool]:
        if "is_success" in meta:
            value = meta.get("is_success")
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "y")
        if "pnl_pips" in meta:
            try:
                return float(meta.get("pnl_pips")) > 0
            except (TypeError, ValueError):
                return None
        outcome = meta.get("outcome")
        if isinstance(outcome, str):
            normalized = outcome.lower()
            if any(token in normalized for token in ("profit", "win", "success", "positive")):
                return True
            if any(token in normalized for token in ("loss", "fail", "negative")):
                return False
        return None

    @staticmethod
    def _infer_price_reaction(adx: Optional[float], atr_pips: Optional[float]) -> str:
        if adx is not None and adx >= 25 and atr_pips is not None and atr_pips >= 12:
            return "strong_break"
        if adx is not None and adx >= 20:
            return "weak_break"
        if adx is not None and adx < 18:
            return "consolidation"
        return "rejection"

    @staticmethod
    def _infer_indicator_response(
        rsi: Optional[float],
        macd_hist: Optional[float],
        adx: Optional[float],
    ) -> str:
        if rsi is None or macd_hist is None:
            return "neutral"
        hist_abs = abs(macd_hist)
        if adx is not None and adx >= 20 and (rsi >= 55 or rsi <= 45) and hist_abs >= 0.00005:
            return "confirmed"
        if hist_abs < 0.00002 and 45 <= rsi <= 55:
            return "diverged"
        return "neutral"

    @staticmethod
    def _price_action_signature(candles, timeframe: str) -> str:
        df = candles.tail(20)
        closes = df["Close"].tolist()
        start = closes[0]
        end = closes[-1]
        delta = end - start
        pct = (delta / start) * 100 if start else 0
        series = ", ".join(f"{c:.5f}" for c in closes)
        return f"timeframe={timeframe}; closes=[{series}]; delta={delta:.5f}; pct={pct:.2f}"

    @staticmethod
    def _format(data: dict) -> str:
        lines = [
            "🧭 *Uncertainty Assessment*",
            f"Regime: `{data.get('market_regime')}`",
            f"Uncertainty: `{data.get('uncertainty_score')}`",
            f"Confidence Adj: `{data.get('confidence_adjustment')}x`",
        ]
        if data.get("high_uncertainty"):
            lines.append("⚠️ High uncertainty")
        return "\n".join(lines)
