"""
Tests for UserSettings — preference persistence, toggle logic, defaults.
"""

import pytest
from unittest.mock import MagicMock

from euroscope.data.storage import Storage
from euroscope.bot.user_settings import (
    UserSettings, TOGGLE_SIGNAL_ALERTS, TOGGLE_NEWS_ALERTS,
    TOGGLE_DAILY_REPORT, SET_TIMEFRAME, SET_RISK, SET_REPORT_HOUR,
)


@pytest.fixture
def settings(tmp_path):
    db_path = str(tmp_path / "test_settings.db")
    storage = Storage(db_path)
    return UserSettings(storage)


class TestDefaults:

    def test_creates_defaults_on_first_access(self, settings):
        prefs = settings.get_prefs(12345)
        assert prefs["risk_tolerance"] == "medium"
        assert prefs["preferred_timeframe"] == "H1"
        assert prefs["alert_on_signals"] == 1
        assert prefs["alert_on_news"] == 1
        assert prefs["daily_report_enabled"] == 1
        assert prefs["daily_report_hour"] == 8
        assert prefs["compact_mode"] == 0

    def test_idempotent(self, settings):
        prefs1 = settings.get_prefs(12345)
        prefs2 = settings.get_prefs(12345)
        assert prefs1["risk_tolerance"] == prefs2["risk_tolerance"]


class TestKeyboardBuilder:

    def test_returns_text_and_markup(self, settings):
        text, keyboard = settings.build_settings_keyboard(12345)
        assert "Settings" in text
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) >= 3

    def test_shows_current_values(self, settings):
        settings.storage.save_user_preferences(12345, preferred_timeframe="H4")
        text, _ = settings.build_settings_keyboard(12345)
        assert "H4" in text

    def test_alert_icons_reflect_state(self, settings):
        settings.storage.save_user_preferences(12345, alert_on_signals=0)
        text, _ = settings.build_settings_keyboard(12345)
        assert "❌" in text  # Signals off


class TestToggleLogic:

    def test_toggle_signals_off(self, settings):
        # Default is ON (1)
        settings.get_prefs(12345)  # Initialize
        prefs = settings.get_prefs(12345)
        assert prefs["alert_on_signals"] == 1

        # Simulate toggle
        settings.storage.save_user_preferences(12345, alert_on_signals=0)
        prefs = settings.get_prefs(12345)
        assert prefs["alert_on_signals"] == 0

    def test_toggle_signals_back_on(self, settings):
        settings.storage.save_user_preferences(12345, alert_on_signals=0)
        settings.storage.save_user_preferences(12345, alert_on_signals=1)
        prefs = settings.get_prefs(12345)
        assert prefs["alert_on_signals"] == 1

    def test_toggle_news(self, settings):
        settings.get_prefs(12345)
        settings.storage.save_user_preferences(12345, alert_on_news=0)
        prefs = settings.get_prefs(12345)
        assert prefs["alert_on_news"] == 0

    def test_toggle_daily_report(self, settings):
        settings.get_prefs(12345)
        settings.storage.save_user_preferences(12345, daily_report_enabled=0)
        prefs = settings.get_prefs(12345)
        assert prefs["daily_report_enabled"] == 0


class TestCycleSettings:

    def test_timeframe_cycle(self, settings):
        settings.get_prefs(12345)
        # H1 → H4
        settings.storage.save_user_preferences(12345, preferred_timeframe="H4")
        assert settings.get_prefs(12345)["preferred_timeframe"] == "H4"
        # H4 → D1
        settings.storage.save_user_preferences(12345, preferred_timeframe="D1")
        assert settings.get_prefs(12345)["preferred_timeframe"] == "D1"

    def test_risk_cycle(self, settings):
        settings.get_prefs(12345)
        settings.storage.save_user_preferences(12345, risk_tolerance="high")
        assert settings.get_prefs(12345)["risk_tolerance"] == "high"
        settings.storage.save_user_preferences(12345, risk_tolerance="low")
        assert settings.get_prefs(12345)["risk_tolerance"] == "low"

    def test_report_hour_cycle(self, settings):
        settings.get_prefs(12345)
        settings.storage.save_user_preferences(12345, daily_report_hour=10)
        assert settings.get_prefs(12345)["daily_report_hour"] == 10

    def test_different_users_independent(self, settings):
        settings.storage.save_user_preferences(111, risk_tolerance="high")
        settings.storage.save_user_preferences(222, risk_tolerance="low")
        assert settings.get_prefs(111)["risk_tolerance"] == "high"
        assert settings.get_prefs(222)["risk_tolerance"] == "low"
