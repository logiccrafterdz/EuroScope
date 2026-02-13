"""
Tests for euroscope.data.models module.
"""

import pytest

from euroscope.data.models import (
    TradingSignal,
    NewsEvent,
    PerformanceMetric,
    UserPreference,
)


class TestTradingSignal:
    """Test TradingSignal dataclass."""

    def test_basic_creation(self):
        signal = TradingSignal(
            direction="BUY",
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0910,
            confidence=75.0,
            timeframe="H1",
        )
        assert signal.direction == "BUY"
        assert signal.status == "pending"
        assert signal.created_at != ""

    def test_risk_reward_auto_calc(self):
        signal = TradingSignal(
            direction="BUY",
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0910,
            confidence=75.0,
            timeframe="H1",
        )
        # Risk = 30 pips, Reward = 60 pips → RR = 2.0
        assert signal.risk_reward_ratio == 2.0

    def test_sell_signal(self):
        signal = TradingSignal(
            direction="SELL",
            entry_price=1.0900,
            stop_loss=1.0930,
            take_profit=1.0840,
            confidence=65.0,
            timeframe="H4",
        )
        assert signal.direction == "SELL"
        assert signal.risk_reward_ratio == 2.0

    def test_custom_source(self):
        signal = TradingSignal(
            direction="BUY",
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0910,
            confidence=80.0,
            timeframe="D1",
            source="ai_agent",
        )
        assert signal.source == "ai_agent"


class TestNewsEvent:
    """Test NewsEvent dataclass."""

    def test_basic_creation(self):
        event = NewsEvent(
            title="ECB raises rates by 25bps",
            source="reuters",
        )
        assert event.title == "ECB raises rates by 25bps"
        assert event.sentiment == "neutral"
        assert event.fetched_at != ""

    def test_with_sentiment(self):
        event = NewsEvent(
            title="Strong NFP report",
            source="brave",
            sentiment="bearish",
            sentiment_score=-0.7,
            currency_impact="USD",
            impact_score=8.5,
        )
        assert event.sentiment == "bearish"
        assert event.sentiment_score == -0.7
        assert event.impact_score == 8.5


class TestPerformanceMetric:
    """Test PerformanceMetric dataclass."""

    def test_basic_creation(self):
        metric = PerformanceMetric(period="daily")
        assert metric.period == "daily"
        assert metric.calculated_at != ""

    def test_win_rate_auto_calc(self):
        metric = PerformanceMetric(
            period="weekly",
            total_signals=10,
            winning_signals=7,
        )
        assert metric.win_rate == 70.0

    def test_zero_signals(self):
        metric = PerformanceMetric(period="monthly", total_signals=0)
        assert metric.win_rate == 0.0


class TestUserPreference:
    """Test UserPreference dataclass."""

    def test_basic_creation(self):
        pref = UserPreference(chat_id=12345)
        assert pref.chat_id == 12345
        assert pref.risk_tolerance == "medium"
        assert pref.preferred_timeframe == "H1"
        assert pref.created_at != ""
        assert pref.updated_at != ""

    def test_custom_values(self):
        pref = UserPreference(
            chat_id=67890,
            risk_tolerance="high",
            preferred_timeframe="H4",
            language="ar",
            alert_min_confidence=80.0,
        )
        assert pref.risk_tolerance == "high"
        assert pref.language == "ar"
        assert pref.alert_min_confidence == 80.0
