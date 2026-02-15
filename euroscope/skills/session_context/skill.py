import logging
import time
from datetime import datetime, date
from enum import Enum

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult

logger = logging.getLogger("euroscope.skills.session_context")


class SessionRegime(str, Enum):
    ASIAN = "asian"
    LONDON = "london"
    OVERLAP = "overlap"
    NEWYORK = "newyork"
    CLOSING = "closing"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"


class SessionContextSkill(BaseSkill):
    name = "session_context"
    description = "Classifies current trading session and provides adaptive rules for other skills"
    emoji = "🕐"
    category = SkillCategory.ANALYSIS
    version = "1.0.0"
    capabilities = ["detect"]

    def __init__(self):
        super().__init__()
        self._cache_timestamp = 0.0
        self._cache_regime = "unknown"
        self._cache_rules = self._neutral_rules()

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action != "detect":
            return SkillResult(success=False, error=f"Unknown action: {action}")
        try:
            regime, rules = self._get_cached_context()
            if not regime:
                now = datetime.utcnow()
                detected = self._detect_session(now)
                regime = detected.value
                rules = self._get_session_rules(regime)
                self._set_cache(regime, rules)
            context.metadata["session_regime"] = regime
            context.metadata["session_rules"] = rules
            return SkillResult(success=True, data={"session_regime": regime, "session_rules": rules})
        except Exception as e:
            logger.warning(f"SessionContextSkill failed: {e}")
            regime = "unknown"
            rules = self._neutral_rules()
            context.metadata["session_regime"] = regime
            context.metadata["session_rules"] = rules
            return SkillResult(success=True, data={"session_regime": regime, "session_rules": rules})

    def _get_cached_context(self) -> tuple[str | None, dict | None]:
        if self._cache_timestamp and (time.time() - self._cache_timestamp) < 300:
            return self._cache_regime, dict(self._cache_rules)
        return None, None

    def _set_cache(self, regime: str, rules: dict):
        self._cache_timestamp = time.time()
        self._cache_regime = regime
        self._cache_rules = dict(rules)

    def _detect_session(self, current: datetime) -> SessionRegime:
        current_date = current.date()
        if current_date.weekday() >= 5:
            return SessionRegime.WEEKEND
        if current_date in self._holiday_dates(current.year):
            return SessionRegime.HOLIDAY
        hour = current.hour
        if 0 <= hour < 7:
            return SessionRegime.ASIAN
        if 7 <= hour < 12:
            return SessionRegime.LONDON
        if 12 <= hour < 16:
            return SessionRegime.OVERLAP
        if 16 <= hour < 21:
            return SessionRegime.NEWYORK
        return SessionRegime.CLOSING

    @staticmethod
    def _holiday_dates(year: int) -> set[date]:
        return {
            date(year, 1, 1),
            date(year, 12, 25),
        }

    def _neutral_rules(self) -> dict:
        return {
            "max_risk_pct": 1.0,
            "min_adx_threshold": 25,
            "deviation_sensitivity": 1.0,
            "trading_allowed": True,
            "pattern_confidence_penalty": 0.0,
        }

    def _get_session_rules(self, session: str) -> dict:
        rules = self._neutral_rules()
        overrides = {
            "asian": {
                "max_risk_pct": 0.5,
                "min_adx_threshold": 20,
                "deviation_sensitivity": 1.0,
                "trading_allowed": True,
                "pattern_confidence_penalty": -0.2,
            },
            "london": {
                "max_risk_pct": 1.0,
                "min_adx_threshold": 25,
                "deviation_sensitivity": 0.9,
                "trading_allowed": True,
                "pattern_confidence_penalty": 0.0,
            },
            "overlap": {
                "max_risk_pct": 1.5,
                "min_adx_threshold": 28,
                "deviation_sensitivity": 0.7,
                "trading_allowed": True,
                "pattern_confidence_penalty": 0.0,
            },
            "newyork": {
                "max_risk_pct": 1.0,
                "min_adx_threshold": 26,
                "deviation_sensitivity": 0.85,
                "trading_allowed": True,
                "pattern_confidence_penalty": 0.0,
            },
            "closing": {
                "max_risk_pct": 0.5,
                "min_adx_threshold": 28,
                "deviation_sensitivity": 1.1,
                "trading_allowed": False,
                "pattern_confidence_penalty": -0.1,
            },
            "weekend": {
                "max_risk_pct": 0.0,
                "min_adx_threshold": 30,
                "deviation_sensitivity": 1.2,
                "trading_allowed": False,
                "pattern_confidence_penalty": -0.2,
            },
            "holiday": {
                "max_risk_pct": 0.0,
                "min_adx_threshold": 30,
                "deviation_sensitivity": 1.2,
                "trading_allowed": False,
                "pattern_confidence_penalty": -0.2,
            },
        }
        if session in overrides:
            rules.update(overrides[session])
        return rules
