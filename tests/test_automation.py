"""
Tests for Phase 5 — Heartbeat, Cron, EventBus, SmartAlerts.
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock

from euroscope.automation.heartbeat import HeartbeatService
from euroscope.automation.cron import CronScheduler, TaskFrequency, ScheduledTask
from euroscope.automation.events import EventBus, Event
from euroscope.automation.alerts import (
    SmartAlerts, AlertPriority, AlertChannel, Alert, setup_default_alerts,
)


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
        assert counter["n"] == 1
        # Should not run again
        await cron._tick()
        assert counter["n"] == 1

    @pytest.mark.asyncio
    async def test_schedule_recurring(self):
        counter = {"n": 0}
        def inc():
            counter["n"] += 1

        cron = CronScheduler()
        task = cron.schedule("test", TaskFrequency.MINUTELY, inc, delay=0)
        await cron._tick()
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
        assert len(cron.history) == 1
        assert cron.history[0]["status"] == "error"


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
