"""
Pattern Tracker — Tracks success rates of detected chart patterns.

Records pattern detections and their outcomes, building a confidence
multiplier for each pattern/timeframe combination.
"""

import json
import logging
import re
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any

from ..data.storage import Storage
from ..skills.base import SkillContext

logger = logging.getLogger("euroscope.learning.pattern_tracker")

CAUSAL_SCHEMA = {
    "trigger",
    "price_reaction",
    "indicator_response",
    "outcome",
}
CAUSAL_ENUMS = {
    "trigger": {"macro_event", "liquidity_void", "news_shock", "quiet_market", "unknown"},
    "price_reaction": {"strong_break", "weak_break", "rejection", "consolidation"},
    "indicator_response": {"confirmed", "diverged", "neutral"},
    "outcome": {"profitable", "breakeven", "loss"},
}


class PatternTracker:
    """
    Tracks detected chart patterns and their success rates.

    Usage:
        tracker = PatternTracker()
        pid = tracker.record_detection("double_bottom", "H4", "BUY", 1.0850)
        # ... later, when pattern plays out ...
        tracker.resolve(pid, "BUY", 1.0900, True)
        rates = tracker.get_success_rates()
    """

    def __init__(self, storage: Storage = None):
        self.storage = storage or Storage()
        self._last_causal_similarity: Optional[float] = None

    def record_detection(self, pattern_name: str, timeframe: str,
                         predicted_direction: str,
                         price_at_detection: float,
                         causal_chain: Optional[dict] = None) -> int:
        """Record a newly detected pattern."""
        causal_payload = self._normalize_causal_chain(causal_chain)
        pid = self.storage.save_pattern_detection(
            pattern_name=pattern_name,
            timeframe=timeframe,
            predicted_direction=predicted_direction,
            price_at_detection=price_at_detection,
            causal_chain=causal_payload,
        )
        logger.info(f"Pattern #{pid}: {pattern_name} ({timeframe}) → {predicted_direction}")
        return pid

    def save_pattern(self, pattern_name: str, timeframe: str,
                     predicted_direction: str,
                     price_at_detection: float,
                     causal_chain: Optional[dict] = None) -> int:
        return self.record_detection(
            pattern_name=pattern_name,
            timeframe=timeframe,
            predicted_direction=predicted_direction,
            price_at_detection=price_at_detection,
            causal_chain=causal_chain,
        )

    def resolve(self, pattern_id: int, actual_outcome: str,
                price_at_resolution: float, is_success: bool):
        """Resolve a pattern detection with actual outcome."""
        self.storage.resolve_pattern(
            pattern_id, actual_outcome, price_at_resolution, is_success
        )
        icon = "✅" if is_success else "❌"
        logger.info(f"Pattern #{pattern_id} resolved: {icon} {actual_outcome}")

    def resolve_pending(self, current_price: float):
        """
        Check all unresolved patterns against the current price.
        Simple logic: if price moved in predicted direction, it's a success.
        """
        unresolved = self.get_unresolved(limit=100)
        for p in unresolved:
            signal = (p.get("predicted_direction") or "NONE").upper()
            entry = p.get("price_at_detection")
            if not entry:
                continue
            
            # Basic resolution: compare current price to entry
            is_success = False
            outcome = "FAILURE"
            
            if signal == "BULLISH":
                if current_price > entry:
                    is_success = True
                    outcome = "SUCCESS"
                elif current_price < entry:
                    is_success = False
                    outcome = "FAILURE"
                else:
                    continue # No movement yet
            elif signal == "BEARISH":
                if current_price < entry:
                    is_success = True
                    outcome = "SUCCESS"
                elif current_price > entry:
                    is_success = False
                    outcome = "FAILURE"
                else:
                    continue # No movement yet
            else:
                continue

            self.resolve(
                pattern_id=p["id"],
                actual_outcome=outcome,
                price_at_resolution=current_price,
                is_success=is_success
            )

    def get_recent_lessons(self, limit: int = 5) -> str:
        """Summarize recent resolved patterns into a natural language string."""
        resolved = self.storage.get_resolved_patterns(limit=limit)
        if not resolved:
            return "No recent patterns resolved yet. I am continuously monitoring market structure for new opportunities."
        
        parts = []
        for p in resolved:
            icon = "✅" if p.get("is_success") else "❌"
            parts.append(f"{icon} {p.get('pattern_name')} ({p.get('timeframe')}): Anticipated {p.get('predicted_direction')}, result was {p.get('actual_outcome')}.")
        
        return "\n".join(parts)

    def get_success_rates(self) -> dict:
        """Get success rates grouped by pattern + timeframe."""
        return self.storage.get_pattern_success_rates()

    def get_confidence_multiplier(self, pattern_name: str,
                                   timeframe: str) -> float:
        """
        Get a confidence multiplier for a pattern/timeframe combo.

        Returns:
            1.0 if no data, >1.0 for high-success patterns, <1.0 for poor ones
        """
        rates = self.get_success_rates()
        key = f"{pattern_name}_{timeframe}"
        entry = rates.get(key)

        if not entry or entry["total"] < 3:
            return 1.0  # Not enough data

        rate = entry["success_rate"]
        # Map 0-100% to 0.5-1.5 multiplier
        return round(0.5 + rate / 100.0, 2)

    def get_unresolved(self, limit: int = 50) -> list[dict]:
        """Get patterns waiting for resolution."""
        return self.storage.get_unresolved_patterns(limit)

    def match_causal_pattern(self, current_context: dict) -> float:
        self._last_causal_similarity = None
        if not current_context:
            return 1.0
        trigger = current_context.get("trigger")
        price_reaction = current_context.get("price_reaction")
        indicator_response = current_context.get("indicator_response")
        if not trigger or not price_reaction or not indicator_response:
            return 1.0

        pattern_name = current_context.get("pattern_name") or current_context.get("pattern")
        timeframe = current_context.get("timeframe")
        candidates = self.storage.get_similar_patterns(
            pattern_name=pattern_name,
            timeframe=timeframe,
            min_similarity=0.7,
            limit=5,
        )
        if not candidates:
            return 1.0

        weighted = 0.0
        similarity_total = 0.0
        similarity_hits = 0
        for candidate in candidates:
            chain = self._parse_causal_chain(candidate.get("causal_chain"))
            if chain:
                score = (
                    (1.0 if chain["trigger"] == trigger else 0.0) * 0.4
                    + (1.0 if chain["price_reaction"] == price_reaction else 0.0) * 0.3
                    + (1.0 if chain["indicator_response"] == indicator_response else 0.0) * 0.3
                )
                outcome_rate = self._outcome_success_rate(chain, candidate)
            else:
                score = 1.0
                outcome_rate = self._outcome_success_rate_from_candidate(candidate)
            similarity_total += score
            similarity_hits += 1
            weighted += outcome_rate * score

        if similarity_hits == 0:
            return 1.0

        avg_similarity = similarity_total / similarity_hits
        self._last_causal_similarity = round(avg_similarity, 3)
        weighted_avg = weighted / similarity_hits
        multiplier = 0.3 + (weighted_avg * 0.9)
        return round(max(0.3, min(1.2, multiplier)), 3)

    def get_last_causal_similarity(self) -> Optional[float]:
        return self._last_causal_similarity

    def classify_trigger(self, market_context: SkillContext) -> str:
        calendar = market_context.analysis.get("calendar", []) or []
        if self._has_macro_event(calendar):
            return "macro_event"

        volume_spike = self._volume_spike(market_context.market_data.get("candles"))
        news_count = len(market_context.analysis.get("news", []) or [])
        if volume_spike and news_count == 0:
            return "liquidity_void"

        sentiment_change = self._sentiment_change(market_context)
        if sentiment_change is not None and abs(sentiment_change) > 0.5:
            return "news_shock"

        indicators = market_context.analysis.get("indicators", {}) or {}
        ind = indicators.get("indicators", {}) or {}
        adx_val = self._safe_float(ind.get("ADX", {}).get("value"))
        if adx_val is not None and adx_val < 18 and self._volume_low(market_context.market_data.get("candles")):
            return "quiet_market"

        return "unknown"

    def get_current_session(self, timestamp: Optional[datetime] = None) -> str:
        """Determines the trading session based on UTC time."""
        now = timestamp or datetime.now(UTC)
        hour = now.hour
        
        if 8 <= hour < 12:
            return "LONDON"
        elif 12 <= hour < 16:
            return "SYNERGY"  # London + NY overlap
        elif 16 <= hour < 21:
            return "NEWYORK"
        elif 21 <= hour <= 23 or 0 <= hour < 8:
            return "ASIAN"
        return "OTHER"

    def get_confidence_multiplier(self, pattern_name: str,
                                   timeframe: str,
                                   current_regime: Optional[str] = None,
                                   current_session: Optional[str] = None) -> float:
        """
        Get a confidence multiplier for a pattern/timeframe combo,
        weighted by regime and session reliability.
        """
        rates = self.get_success_rates()
        key = f"{pattern_name}_{timeframe}"
        entry = rates.get(key)

        base_multiplier = 1.0
        if entry and entry["total"] >= 3:
            rate = entry["success_rate"]
            base_multiplier = 0.5 + rate / 100.0

        # Regime/Session weightings (Phase 3B enhancement)
        # In a full implementation, we'd query the database for 
        # pattern success rates specific to the regime/session.
        # This is a simplified dynamic adjustment logic.
        
        regime_mod = 1.0
        if current_regime and entry:
            # Boost if regime matches historical success (mock logic for now)
            if current_regime == entry.get("best_regime", "trending"):
                regime_mod = 1.1
            elif current_regime == "volatile":
                regime_mod = 0.9

        session_mod = 1.0
        if current_session == "ASIAN" and pattern_name != "consolidation":
            session_mod = 0.8 # Asian session is less reliable for breakouts
        elif current_session == "SYNERGY":
            session_mod = 1.2 # High liquidity synergy session is more reliable

        return round(base_multiplier * regime_mod * session_mod, 2)

    @staticmethod
    def _normalize_causal_chain(causal_chain: Optional[dict]) -> Optional[dict]:
        if not causal_chain:
            return None
        if set(causal_chain.keys()) != CAUSAL_SCHEMA:
            return None
        for key, values in CAUSAL_ENUMS.items():
            if causal_chain.get(key) not in values:
                return None
        return causal_chain

    @staticmethod
    def _parse_causal_chain(raw: Optional[str]) -> Optional[dict]:
        if not raw:
            return None
        if isinstance(raw, dict):
            return raw if set(raw.keys()) == CAUSAL_SCHEMA else None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if set(payload.keys()) != CAUSAL_SCHEMA:
            return None
        for key, values in CAUSAL_ENUMS.items():
            if payload.get(key) not in values:
                return None
        return payload

    @staticmethod
    def _outcome_success_rate(chain: dict, candidate: dict) -> float:
        outcome = chain.get("outcome")
        if outcome == "profitable":
            return 1.0
        if outcome == "breakeven":
            return 0.5
        if outcome == "loss":
            return 0.0
        is_success = candidate.get("is_success")
        if is_success is None:
            return 0.5
        return 1.0 if is_success else 0.0

    @staticmethod
    def _outcome_success_rate_from_candidate(candidate: dict) -> float:
        is_success = candidate.get("is_success")
        if is_success is None:
            return 0.5
        return 1.0 if is_success else 0.0

    @staticmethod
    def _safe_float(value: Optional[float]) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _has_macro_event(self, events: list) -> bool:
        for event in events:
            minutes = self._extract_minutes_to_event(event)
            if minutes is not None and minutes <= 60:
                return True
        return False

    @staticmethod
    def _extract_minutes_to_event(event) -> Optional[float]:
        if isinstance(event, dict):
            for key in ("minutes_to_event", "time_to_event", "minutes"):
                if key in event:
                    return PatternTracker._safe_float(event.get(key))
            time_val = event.get("time")
        else:
            time_val = getattr(event, "time", None)
        if isinstance(time_val, (int, float)):
            return float(time_val)
        if isinstance(time_val, str):
            digits = re.findall(r"\d+", time_val)
            if digits:
                return float(digits[0])
        return None

    def _sentiment_change(self, market_context: SkillContext) -> Optional[float]:
        summary = market_context.analysis.get("sentiment_summary", {}) or {}
        current = self._safe_float(summary.get("score"))
        previous = self._safe_float(market_context.metadata.get("sentiment_score_prev"))
        if current is None or previous is None:
            return None
        return current - previous

    @staticmethod
    def _volume_spike(candles) -> bool:
        if candles is None or len(candles) < 10:
            return False
        if "Volume" not in candles.columns:
            return False
        df = candles.tail(20)
        current = float(df["Volume"].iloc[-1])
        avg = float(df["Volume"].mean())
        return avg > 0 and current > (3.0 * avg)

    @staticmethod
    def _volume_low(candles) -> bool:
        if candles is None or len(candles) < 10:
            return False
        if "Volume" not in candles.columns:
            return False
        df = candles.tail(20)
        current = float(df["Volume"].iloc[-1])
        avg = float(df["Volume"].mean())
        return avg > 0 and current < (0.8 * avg)
    def format_report(self) -> str:
        """Generate a human-readable pattern performance report."""
        rates = self.get_success_rates()

        if not rates:
            return "📊 *Pattern Tracker*\n\nNo resolved patterns yet."

        lines = ["📊 *Pattern Success Rates*\n"]

        # Sort by success rate descending
        sorted_patterns = sorted(
            rates.values(), key=lambda x: x["success_rate"], reverse=True
        )

        for p in sorted_patterns:
            rate = p["success_rate"]
            icon = "🟢" if rate >= 60 else "🟡" if rate >= 40 else "🔴"
            lines.append(
                f"{icon} `{p['pattern']}` ({p['timeframe']}): "
                f"{rate}% ({p['successes']}/{p['total']})"
            )

        return "\n".join(lines)
