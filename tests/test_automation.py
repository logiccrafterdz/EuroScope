"""
Tests for Phase 5 — Heartbeat, Cron, EventBus, SmartAlerts.
"""

import asyncio
import time
from datetime import datetime, UTC
from unittest.mock import MagicMock, AsyncMock

import pandas as pd
import pytest
import euroscope.skills.deviation_monitor.skill as deviation_module
from euroscope.automation.heartbeat import HeartbeatService
from euroscope.automation.cron import CronScheduler, TaskFrequency, ScheduledTask, ProactiveAlertCache
from euroscope.automation.daily_tracker import DailyTracker
from euroscope.automation.events import EventBus, Event
from euroscope.automation.alerts import (
    SmartAlerts, AlertPriority, AlertChannel, Alert, setup_default_alerts,
)
from euroscope.skills.base import SkillContext
from euroscope.skills.deviation_monitor import DeviationMonitorSkill
from euroscope.brain.agent import Agent
from euroscope.config import LLMConfig
from euroscope.data.storage import Storage


# ── HeartbeatService Tests ───────────────────────────────────

class TestHeartbeatService:
    @pytest.mark.asyncio
    async def test_tick_runs_checks(self):
        hb = HeartbeatService(interval=60)
        hb.register_check("test", lambda: {"status": "healthy", "detail": "ok"})
        results = await hb.tick()
        assert "test" in results
        assert results["test"]["status"] == "healthy"
        assert hb.tick_count == 1

    @pytest.mark.asyncio
    async def test_tick_async_check(self):
        async def async_check():
            return {"status": "healthy", "detail": "async ok"}

        hb = HeartbeatService()
        hb.register_check("async_test", async_check)
        results = await hb.tick()
        assert results["async_test"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_tick_error_handling(self):
        def bad_check():
            raise ConnectionError("timeout")

        hb = HeartbeatService()
        hb.register_check("bad", bad_check)
        results = await hb.tick()
        assert results["bad"]["status"] == "error"
        assert "timeout" in results["bad"]["detail"]

    @pytest.mark.asyncio
    async def test_status_change_notification(self):
        events = []

        hb = HeartbeatService()
        hb.on_status_change(lambda e: events.append(e))

        # First tick — no change (no previous status)
        hb.register_check("comp", lambda: {"status": "healthy"})
        await hb.tick()
        assert len(events) == 0

        # Change to error
        hb._checks["comp"] = lambda: {"status": "error"}
        await hb.tick()
        assert len(events) == 1
        assert events[0]["new_status"] == "error"

    def test_is_healthy(self):
        hb = HeartbeatService()
        assert hb.is_healthy  # No checks = healthy


# ── CronScheduler Tests ─────────────────────────────────────

class TestCronScheduler:
    @pytest.mark.asyncio
    async def test_schedule_once(self):
        counter = {"n": 0}
        def inc():
            counter["n"] += 1

        cron = CronScheduler(tick_interval=1)
        cron.schedule_once("test", inc, delay=0)
        await cron._tick()
        await asyncio.sleep(0.01) # Yield to allow the created task to complete
        assert counter["n"] == 1
        # Should not run again
        await cron._tick()
        await asyncio.sleep(0.01)
        assert counter["n"] == 1

    @pytest.mark.asyncio
    async def test_schedule_recurring(self):
        counter = {"n": 0}
        def inc():
            counter["n"] += 1

        cron = CronScheduler()
        task = cron.schedule("test", TaskFrequency.MINUTELY, inc, delay=0)
        await cron._tick()
        await asyncio.sleep(0.01)
        assert counter["n"] == 1
        assert task.run_count == 1

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        counter = {"n": 0}
        cron = CronScheduler()
        cron.schedule_once("test", lambda: counter.__setitem__("n", 1), delay=0)
        cron.cancel("test")
        await cron._tick()
        assert counter["n"] == 0

    @pytest.mark.asyncio
    async def test_error_handling(self):
        def bad():
            raise ValueError("oops")

        cron = CronScheduler()
        cron.schedule_once("bad", bad, delay=0)
        await cron._tick()
        await asyncio.sleep(0.01)
        assert len(cron.history) == 1
        assert cron.history[0]["status"] == "error"


class TestProactiveAlerts:
    def test_proactive_alert_cache_deduplication(self):
        cache = ProactiveAlertCache(cache_duration_minutes=10, per_user_limit=3)
        message = "Price approaching 1.0850 resistance"
        assert cache.is_duplicate(1, message) is False
        cache.record_alert(1, message)
        assert cache.is_duplicate(1, message) is True
        assert cache.is_duplicate(2, message) is False
        assert cache.within_user_limit(1) is True

    @pytest.mark.asyncio
    async def test_proactive_analysis_decision(self):
        router = MagicMock()
        router.chat_with_functions = AsyncMock(return_value={
            "content": "Decision made",
            "function_calls": [
                {
                    "name": "proactive_alert_decision",
                    "arguments": {
                        "should_alert": True,
                        "message": "Test alert",
                        "priority": "medium",
                        "reason": "Setup detected",
                    },
                }
            ],
        })

        agent = Agent(LLMConfig(), router=router)
        decision = await agent.run_proactive_analysis()

        assert decision["should_alert"] is True
        assert decision["message"] == "Test alert"
        assert decision["priority"] == "medium"
        assert "analysis_summary" in decision


class TestDailyTracker:
    def test_daily_summary_counts(self):
        storage = Storage(":memory:")
        tracker = DailyTracker(storage=storage)
        date_value = datetime.now(UTC).strftime("%Y-%m-%d")

        storage.save_trade_journal(
            direction="BUY",
            entry_price=1.1,
            stop_loss=1.09,
            take_profit=1.12,
            strategy="paper",
            confidence=0.7,
            indicators={"uncertainty_score": 0.2},
            reasoning="paper trade opened",
            status="open",
        )
        storage.save_trade_journal(
            direction="SELL",
            entry_price=1.09,
            stop_loss=1.095,
            take_profit=1.08,
            strategy="paper",
            confidence=0.6,
            indicators={"uncertainty_score": 0.82, "uncertainty_reasoning": "Lagarde speech"},
            reasoning="paper trade opened",
            status="open",
        )
        storage.save_trade_journal(
            direction="BUY",
            entry_price=1.12,
            stop_loss=1.11,
            take_profit=1.13,
            strategy="paper",
            confidence=0.4,
            indicators={"uncertainty_score": 0.7},
            reasoning="paper rejection: EMERGENCY: market regime shift",
            status="rejected",
        )

        summary = tracker.get_summary(date_value)

        assert summary["signals_generated"] == 3
        assert summary["signals_executed"] == 2
        assert summary["signals_rejected"] == 1
        assert summary["rejection_reasons"]["emergency_mode"] == 1
        assert summary["avg_confidence"] == 0.57
        assert summary["max_uncertainty"] == 0.82
        assert "Lagarde" in summary["max_uncertainty_reason"]


# ── EventBus Tests ───────────────────────────────────────────

class TestEventBus:
    @pytest.mark.asyncio
    async def test_emit_and_subscribe(self):
        received = []
        bus = EventBus()
        bus.subscribe("test.topic", lambda e: received.append(e))

        await bus.emit(Event("test.topic", "unit_test", {"key": "val"}))
        assert len(received) == 1
        assert received[0].data["key"] == "val"

    @pytest.mark.asyncio
    async def test_wildcard_subscriber(self):
        received = []
        bus = EventBus()
        bus.subscribe("*", lambda e: received.append(e))
        await bus.emit(Event("any.topic", "test"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_prefix_match(self):
        received = []
        bus = EventBus()
        bus.subscribe("signal.*", lambda e: received.append(e))
        await bus.emit(Event("signal.new", "test"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        received = []
        cb = lambda e: received.append(e)
        bus = EventBus()
        bus.subscribe("test", cb)
        bus.unsubscribe("test", cb)
        await bus.emit(Event("test", "src"))
        assert len(received) == 0

    def test_emit_sync(self):
        received = []
        bus = EventBus()
        bus.subscribe("test", lambda e: received.append(e))
        bus.emit_sync(Event("test", "src"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_history(self):
        bus = EventBus(max_history=5)
        for i in range(10):
            await bus.emit(Event(f"topic.{i}", "src"))
        assert len(bus.history) == 5

    def test_topics(self):
        bus = EventBus()
        bus.subscribe("b", lambda e: None)
        bus.subscribe("a", lambda e: None)
        assert bus.topics == ["a", "b"]


# ── SmartAlerts Tests ────────────────────────────────────────

class TestSmartAlerts:
    def test_add_and_check_rule(self):
        alerts = SmartAlerts()
        alerts.add_rule(
            "test_rule",
            condition=lambda d: d.get("value", 0) > 10,
            title="Test Alert",
            message_template="Value is {value}",
            cooldown=0,
        )
        triggered = alerts.check({"value": 15})
        assert len(triggered) == 1
        assert triggered[0].title == "Test Alert"
        assert "15" in triggered[0].message

    def test_no_trigger(self):
        alerts = SmartAlerts()
        alerts.add_rule("test", condition=lambda d: False, cooldown=0)
        assert len(alerts.check({})) == 0

    def test_cooldown(self):
        alerts = SmartAlerts()
        alerts.add_rule("cd", condition=lambda d: True, cooldown=9999)
        assert len(alerts.check({})) == 1
        assert len(alerts.check({})) == 0  # Cooldown active

    def test_disable_enable(self):
        alerts = SmartAlerts()
        alerts.add_rule("toggle", condition=lambda d: True, cooldown=0)
        alerts.disable_rule("toggle")
        assert len(alerts.check({})) == 0
        alerts.enable_rule("toggle")
        assert len(alerts.check({})) == 1

    def test_handler_dispatch(self):
        handled = []
        alerts = SmartAlerts()
        alerts.register_handler(AlertChannel.TELEGRAM, lambda a: handled.append(a))
        alerts.add_rule("h", condition=lambda d: True, cooldown=0,
                       channel=AlertChannel.TELEGRAM)
        alerts.check({})
        assert len(handled) == 1

    def test_unacknowledged(self):
        alerts = SmartAlerts()
        alerts.add_rule("ack", condition=lambda d: True, cooldown=0)
        alerts.check({})
        assert len(alerts.unacknowledged()) == 1
        alerts.history[0].acknowledged = True
        assert len(alerts.unacknowledged()) == 0

    def test_default_rules(self):
        alerts = SmartAlerts()
        setup_default_alerts(alerts)
        assert "rsi_oversold" in alerts.rules
        assert "rsi_overbought" in alerts.rules
        assert "high_impact_event" in alerts.rules
        assert "drawdown_warning" in alerts.rules

    def test_rsi_oversold_trigger(self):
        alerts = SmartAlerts()
        setup_default_alerts(alerts)
        # Reset cooldowns
        for r in alerts.rules.values():
            r.cooldown_seconds = 0
        triggered = alerts.check({"rsi": 25})
        names = [a.source for a in triggered]
        assert "rsi_oversold" in names


class TestDeviationMonitor:
    @pytest.mark.asyncio
    async def test_price_velocity_triggers_emergency_mode(self, monkeypatch):
        candles = pd.DataFrame(
            [
                {"Close": 1.0000},
                {"Close": 1.0000},
                {"Close": 1.0020},
            ]
        )

        class MarketDataStub:
            def get_buffer(self):
                return {"candles": candles, "timeframe": "M1"}

        bus = EventBus()
        context = SkillContext()
        skill = DeviationMonitorSkill(
            event_bus=bus,
            market_data_skill=MarketDataStub(),
            global_context=context,
        )
        skill.set_event_bus(bus)
        monkeypatch.setattr(skill, "_detect_trading_session", lambda _: "asian")

        await bus.emit(Event("tick.30s", "test"))
        assert context.metadata.get("emergency_mode") is True

    def test_overlap_velocity_below_threshold_no_trigger(self, monkeypatch):
        candles = pd.DataFrame(
            [
                {"Close": 1.0000},
                {"Close": 1.0000},
                {"Close": 1.0020},
            ]
        )

        target_dt = datetime(2023, 6, 15, 14, 0, 0)

        class FixedDateTime:
            @classmethod
            def utcnow(cls):
                return target_dt
            @classmethod
            def now(cls, tz=None):
                return target_dt
            @classmethod
            def now(cls, tz=None):
                return target_dt

        monkeypatch.setattr(deviation_module, "datetime", FixedDateTime)
        skill = DeviationMonitorSkill()
        result = skill._detect_deviation(candles)
        assert result is None

    def test_asian_velocity_above_threshold_triggers(self, monkeypatch):
        candles = pd.DataFrame(
            [
                {"Close": 1.0000},
                {"Close": 1.0000},
                {"Close": 1.0020},
            ]
        )

        target_dt = datetime(2023, 6, 15, 3, 0, 0)

        class FixedDateTime:
            @classmethod
            def utcnow(cls):
                return target_dt
            @classmethod
            def now(cls, tz=None):
                return target_dt

        monkeypatch.setattr(deviation_module, "datetime", FixedDateTime)
        skill = DeviationMonitorSkill()
        result = skill._detect_deviation(candles)
        assert result is not None
        assert result.get("trigger") == "price_velocity"

    @pytest.mark.asyncio
    async def test_overlap_lagarde_speech_triggers(self, monkeypatch):
        candles = pd.DataFrame(
            [
                {"Close": 1.0000},
                {"Close": 1.0000},
                {"Close": 1.0050},
            ]
        )

        target_dt = datetime(2023, 6, 15, 14, 0, 0)

        class FixedDateTime:
            @classmethod
            def utcnow(cls):
                return target_dt
            @classmethod
            def now(cls, tz=None):
                return target_dt

        monkeypatch.setattr(deviation_module, "datetime", FixedDateTime)

        class MarketDataStub:
            def get_buffer(self):
                return {"candles": candles, "timeframe": "M1"}

        context = SkillContext()
        skill = DeviationMonitorSkill(
            market_data_skill=MarketDataStub(),
            global_context=context,
        )

        await skill._check_once()
        assert context.metadata.get("emergency_mode") is True
        assert context.metadata.get("deviation_monitor_last_trigger", {}).get("session") == "overlap"
