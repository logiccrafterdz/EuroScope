import pytest
from datetime import datetime

from euroscope.skills.base import SkillContext
from euroscope.skills.session_context import SessionContextSkill, SessionRegime


class TestSessionDetection:
    def test_session_boundaries(self):
        skill = SessionContextSkill()
        assert skill._detect_session(datetime(2026, 1, 5, 6, 59)) == SessionRegime.ASIAN
        assert skill._detect_session(datetime(2026, 1, 5, 7, 0)) == SessionRegime.LONDON
        assert skill._detect_session(datetime(2026, 1, 5, 11, 59)) == SessionRegime.LONDON
        assert skill._detect_session(datetime(2026, 1, 5, 12, 0)) == SessionRegime.OVERLAP
        assert skill._detect_session(datetime(2026, 1, 5, 15, 59)) == SessionRegime.OVERLAP
        assert skill._detect_session(datetime(2026, 1, 5, 16, 0)) == SessionRegime.NEWYORK
        assert skill._detect_session(datetime(2026, 1, 5, 20, 59)) == SessionRegime.NEWYORK
        assert skill._detect_session(datetime(2026, 1, 5, 21, 0)) == SessionRegime.CLOSING

    def test_weekend_detection(self):
        skill = SessionContextSkill()
        assert skill._detect_session(datetime(2026, 1, 3, 14, 0)) == SessionRegime.WEEKEND

    def test_holiday_detection(self):
        skill = SessionContextSkill()
        assert skill._detect_session(datetime(2026, 12, 25, 10, 0)) == SessionRegime.HOLIDAY


class TestFailureHandling:
    @pytest.mark.asyncio
    async def test_failure_returns_neutral_defaults(self, monkeypatch):
        skill = SessionContextSkill()
        context = SkillContext()
        def blow_up(_dt):
            raise ValueError("boom")
        monkeypatch.setattr(skill, "_detect_session", blow_up)
        result = await skill.execute(context, "detect")
        assert result.success
        assert context.metadata["session_regime"] == "unknown"
        assert context.metadata["session_rules"]["max_risk_pct"] == 1.0
