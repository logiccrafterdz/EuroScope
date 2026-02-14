from __future__ import annotations

from typing import Optional

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


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

        behavioral_uncertainty, behavioral_meta = self._apply_causal_adjustment(
            context=context,
            patterns=patterns,
            timeframe=timeframe,
            adx=adx,
            atr_pips=atr_pips,
            rsi=rsi,
            macd_hist=macd_hist,
            behavioral_uncertainty=behavioral_uncertainty,
            behavioral_meta=behavioral_meta,
        )

        combined_uncertainty = round(
            min(1.0, (technical_uncertainty * 0.7) + (behavioral_uncertainty * 0.3)),
            3,
        )
        confidence_adjustment = round(max(0.4, 1 - combined_uncertainty), 3)
        high_uncertainty = combined_uncertainty > 0.65

        data = {
            "market_regime": regime,
            "technical_uncertainty": technical_uncertainty,
            "behavioral_uncertainty": behavioral_uncertainty,
            "uncertainty_breakdown": {
                "technical": technical_uncertainty,
                "behavioral": behavioral_uncertainty,
            },
            "uncertainty_score": combined_uncertainty,
            "confidence_adjustment": confidence_adjustment,
            "high_uncertainty": high_uncertainty,
            "blocking_reason": None,
            "behavioral_meta": behavioral_meta,
        }

        context.metadata.update({
            "market_regime": regime,
            "technical_uncertainty": technical_uncertainty,
            "behavioral_uncertainty": behavioral_uncertainty,
            "uncertainty_breakdown": {
                "technical": technical_uncertainty,
                "behavioral": behavioral_uncertainty,
            },
            "uncertainty_score": combined_uncertainty,
            "confidence_adjustment": confidence_adjustment,
            "high_uncertainty": high_uncertainty,
            "blocking_reason": None,
        })
        context.analysis["uncertainty"] = data

        return SkillResult(success=True, data=data, metadata={"formatted": self._format(data)})

    @staticmethod
    def _safe_float(value: Optional[float]) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
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
            score += 0.3
        elif adx < 20:
            score += 0.35
        elif adx < 25:
            score += 0.2
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

    def _apply_causal_adjustment(
        self,
        context: SkillContext,
        patterns: list,
        timeframe: str,
        adx: Optional[float],
        atr_pips: Optional[float],
        rsi: Optional[float],
        macd_hist: Optional[float],
        behavioral_uncertainty: float,
        behavioral_meta: dict,
    ) -> tuple[float, dict]:
        if not self._pattern_tracker:
            return behavioral_uncertainty, behavioral_meta
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
        if causal_similarity is not None and causal_similarity < 0.4:
            behavioral_meta["causal_mismatch"] = True
            behavioral_uncertainty = round(min(1.0, behavioral_uncertainty + 0.25), 3)
        return behavioral_uncertainty, behavioral_meta

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
