import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("euroscope.automation.daily_tracker")


class DailyTracker:
    def __init__(
        self,
        storage: Optional[object] = None,
        log_path: Optional[str] = None,
        now_fn: Optional[Callable[[], datetime]] = None,
    ):
        self._storage = storage
        if log_path:
            self._log_path = Path(log_path)
        else:
            base = Path(__file__).resolve().parents[1]
            self._log_path = base / "workspace" / "paper_trading_log.csv"
        self._now_fn = now_fn or datetime.utcnow

    def set_storage(self, storage):
        self._storage = storage

    async def run(self) -> dict:
        summary = self.get_summary()
        self._append_to_csv(summary)
        return summary

    def get_summary(self, date: Optional[str] = None) -> dict:
        date_value = date or self._now_fn().strftime("%Y-%m-%d")
        if not self._storage:
            return self._empty_summary(date_value)

        entries = self._storage.get_trade_journal_for_date(date_value)
        signals_generated = len(entries)
        signals_rejected = 0
        signals_executed = 0
        rejection_reasons: dict[str, int] = {}
        confidences: list[float] = []
        uncertainty_scores: list[float] = []
        max_uncertainty = 0.0
        max_uncertainty_time = ""
        max_uncertainty_reason = ""

        for entry in entries:
            status = str(entry.get("status", "open"))
            reasoning = entry.get("reasoning", "") or ""
            if status == "rejected":
                signals_rejected += 1
                reason_key = self._normalize_rejection_reason(reasoning)
                if reason_key:
                    rejection_reasons[reason_key] = rejection_reasons.get(reason_key, 0) + 1
            else:
                signals_executed += 1

            confidence = entry.get("confidence", 0.0)
            try:
                confidences.append(float(confidence))
            except (TypeError, ValueError):
                pass

            indicators = self._parse_indicators(entry.get("indicators_snapshot"))
            uncertainty = indicators.get("uncertainty_score")
            if uncertainty is not None:
                try:
                    uncertainty_val = float(uncertainty)
                    uncertainty_scores.append(uncertainty_val)
                    if uncertainty_val > max_uncertainty:
                        max_uncertainty = uncertainty_val
                        max_uncertainty_time = entry.get("timestamp", "")
                        max_uncertainty_reason = self._format_uncertainty_reason(indicators, reasoning)
                except (TypeError, ValueError):
                    pass

        avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
        uncertainty_distribution = self._uncertainty_distribution(uncertainty_scores)
        emergency_mode_activations = rejection_reasons.get("emergency_mode", 0)

        return {
            "date": date_value,
            "signals_generated": signals_generated,
            "signals_executed": signals_executed,
            "signals_rejected": signals_rejected,
            "rejection_reasons": rejection_reasons,
            "avg_confidence": avg_confidence,
            "max_uncertainty": round(max_uncertainty, 2),
            "max_uncertainty_time": max_uncertainty_time,
            "max_uncertainty_reason": max_uncertainty_reason,
            "uncertainty_distribution": uncertainty_distribution,
            "emergency_mode_activations": emergency_mode_activations,
        }

    def _append_to_csv(self, summary: dict) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self._log_path.exists()
        fieldnames = [
            "date",
            "signals_generated",
            "signals_executed",
            "signals_rejected",
            "avg_confidence",
            "max_uncertainty",
            "emergency_mode_activations",
            "top_rejection_reason",
        ]
        with self._log_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            # Find the most common rejection reason
            reasons = summary.get("rejection_reasons", {})
            top_reason = max(reasons, key=reasons.get) if reasons else ""
            writer.writerow({
                "date": summary.get("date"),
                "signals_generated": summary.get("signals_generated", 0),
                "signals_executed": summary.get("signals_executed", 0),
                "signals_rejected": summary.get("signals_rejected", 0),
                "avg_confidence": summary.get("avg_confidence", 0.0),
                "max_uncertainty": summary.get("max_uncertainty", 0.0),
                "emergency_mode_activations": summary.get("emergency_mode_activations", 0),
                "top_rejection_reason": top_reason,
            })

    def _parse_indicators(self, raw: Any) -> dict:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
        return {}

    def _normalize_rejection_reason(self, reason: str) -> str:
        text = reason.lower()
        if "emergency" in text:
            return "emergency_mode"
        if "uncertainty" in text:
            return "high_uncertainty"
        if "confidence" in text:
            return "low_confidence"
        if "paper_only" in text or "paper only" in text:
            return "paper_only"
        return "other"

    def _format_uncertainty_reason(self, indicators: dict, fallback: str) -> str:
        reason = indicators.get("uncertainty_reasoning")
        if isinstance(reason, list):
            reason_text = ", ".join(str(r) for r in reason if r)
        else:
            reason_text = str(reason) if reason else ""
        if reason_text:
            return reason_text
        return fallback

    def _uncertainty_distribution(self, scores: list[float]) -> dict:
        buckets = {"0-0.3": 0, "0.3-0.6": 0, "0.6-1.0": 0}
        for score in scores:
            if score < 0.3:
                buckets["0-0.3"] += 1
            elif score < 0.6:
                buckets["0.3-0.6"] += 1
            else:
                buckets["0.6-1.0"] += 1
        return buckets

    def _empty_summary(self, date_value: str) -> dict:
        return {
            "date": date_value,
            "signals_generated": 0,
            "signals_executed": 0,
            "signals_rejected": 0,
            "rejection_reasons": {},
            "avg_confidence": 0.0,
            "max_uncertainty": 0.0,
            "max_uncertainty_time": "",
            "max_uncertainty_reason": "",
            "uncertainty_distribution": {"0-0.3": 0, "0.3-0.6": 0, "0.6-1.0": 0},
            "emergency_mode_activations": 0,
        }
