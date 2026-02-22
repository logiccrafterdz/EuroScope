from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ..data.calendar import EconomicCalendar
from ..skills.base import SkillContext


@dataclass
class SafetyGuardrail:
    config: object
    calendar: Optional[EconomicCalendar] = None

    def __post_init__(self):
        if self.calendar is None:
            self.calendar = EconomicCalendar()

    async def should_block_signal(self, context: SkillContext) -> Tuple[bool, str]:
        try:
            if context is None:
                return True, "Missing safety context"

            if context.metadata.get("emergency_mode"):
                return True, "EMERGENCY: market regime shift"

            direction = (context.signals or {}).get("direction")
            if direction not in ("BUY", "SELL"):
                return True, "Signal direction missing for safety validation"

            # Soft checks: warn instead of blocking for missing context data
            warnings = []
            session = context.metadata.get("session_regime")
            if not session:
                warnings.append("Session regime data unavailable")
                session = "unknown"  # Allow signal through with warning

            quality = context.metadata.get("macro_quality")
            if not quality:
                details = context.metadata.get("data_quality_details", {})
                quality = details.get("quality")
            if not quality:
                warnings.append("Macro data quality unavailable")
                quality = "unknown"  # Allow signal through with warning

            block_minutes = int(getattr(self.config, "safety_news_block_minutes", 30))
            calendar = context.analysis.get("calendar") if context.analysis else None
            upcoming = calendar if calendar else self.calendar.get_upcoming_events()
            for event in upcoming or []:
                impact = str(event.get("impact", "")).lower()
                if impact != "high":
                    continue
                minutes = self._extract_minutes_to_event(event)
                if minutes is not None and minutes <= block_minutes:
                    name = event.get("event") or event.get("name") or "High-impact event"
                    return True, f"High-impact news in {int(minutes)} min: {name}"

            confidence = self._normalize_confidence((context.signals or {}).get("confidence"))
            strategy = str((context.signals or {}).get("strategy", "")).lower()
            min_conf = float(getattr(self.config, "safety_asian_min_confidence", 0.75))
            if session == "asian" and confidence < min_conf:
                if strategy in ("reversal", "mean_reversion"):
                    return True, f"Weak reversal signal ({confidence:.0%} confidence) in low-liquidity Asian session"

            # Only block for known-bad quality, not for unknown/missing
            if quality in ("partial_eu", "partial_us", "minimal"):
                return True, f"Incomplete macro data ({quality}) — cannot assess full risk context"

            # Attach warnings to metadata so the user sees them
            if warnings:
                existing = context.metadata.get("safety_warnings", [])
                context.metadata["safety_warnings"] = existing + warnings

            return False, ""
        except Exception as e:
            return True, f"Safety guardrail error: {e}"

    async def enhance_signal_safety(self, context: SkillContext) -> SkillContext:
        if context is None:
            return context

        enhanced = False
        volatility = context.metadata.get("volatility") or context.metadata.get("volatility_regime") or "normal"
        min_stop = int(getattr(self.config, "safety_volatility_stop_min", 25))
        if volatility in ("high", "extreme"):
            risk = context.risk or {}
            entry = risk.get("entry_price") or (context.signals or {}).get("entry_price")
            stop = risk.get("stop_loss")
            direction = (context.signals or {}).get("direction")
            if entry and stop and direction in ("BUY", "SELL"):
                current_pips = abs((entry - stop) * 10000)
                target_pips = max(current_pips, float(min_stop))
                if target_pips > current_pips:
                    if direction == "BUY":
                        risk["stop_loss"] = round(entry - (target_pips * 0.0001), 5)
                    else:
                        risk["stop_loss"] = round(entry + (target_pips * 0.0001), 5)
                    context.risk = risk
                    context.metadata["stop_loss_pips"] = round(target_pips, 1)
                    enhanced = True

        uncertainty = context.metadata.get("composite_uncertainty", context.metadata.get("uncertainty_score", 0.0))
        if uncertainty and float(uncertainty) > 0.6:
            risk = context.risk or {}
            size = risk.get("position_size") or context.metadata.get("position_size")
            if size:
                adjusted = float(size) * 0.7
                risk["position_size"] = adjusted
                context.risk = risk
                context.metadata["position_size"] = adjusted
                enhanced = True

        if enhanced:
            context.metadata["safety_guardrail_triggered"] = True
            context.metadata["safety_enhanced"] = True
        return context

    @staticmethod
    def _extract_minutes_to_event(event: dict) -> Optional[float]:
        for key in ("minutes_to_event", "time_to_event", "minutes"):
            if key in event:
                return SafetyGuardrail._safe_float(event.get(key))
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
    def _safe_float(value: object) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_confidence(value: object) -> float:
        val = SafetyGuardrail._safe_float(value)
        if val is None:
            return 0.0
        if val > 1.0:
            return max(0.0, min(1.0, val / 100.0))
        return max(0.0, min(1.0, val))
