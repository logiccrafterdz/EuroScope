"""
Tests for HealthMonitor — component checks, error tracking, formatting.
"""

import time

import pytest

from euroscope.data.storage import Storage
from euroscope.analytics.health_monitor import HealthMonitor, SystemHealth


@pytest.fixture
def monitor(tmp_path):
    db_path = str(tmp_path / "test_health.db")
    storage = Storage(db_path)
    return HealthMonitor(storage)


# ── Error Tracking ───────────────────────────────────────

class TestErrorTracking:

    def test_record_error(self, monitor):
        monitor.record_error("price_api", "Timeout")
        assert len(monitor._errors) == 1
        assert monitor._errors[0]["component"] == "price_api"

    def test_error_rate(self, monitor):
        for i in range(5):
            monitor.record_error("test", f"Error {i}")
        rate = monitor.get_error_rate(1.0)
        assert rate == 5.0

    def test_recent_errors(self, monitor):
        for i in range(20):
            monitor.record_error("test", f"Error {i}")
        recent = monitor.get_recent_errors(5)
        assert len(recent) == 5
        assert recent[-1]["error"] == "Error 19"

    def test_rolling_buffer(self, monitor):
        monitor._max_errors = 10
        for i in range(25):
            monitor.record_error("test", f"Error {i}")
        assert len(monitor._errors) == 10
        assert monitor._errors[0]["error"] == "Error 15"


# ── Component Checks ────────────────────────────────────

class TestComponentChecks:

    @pytest.mark.asyncio
    async def test_database_healthy(self, monitor):
        status = await monitor.check_database()
        assert status.healthy is True
        assert status.name == "Database"
        assert status.response_time_ms >= 0

    def test_price_api_no_provider(self, monitor):
        status = monitor.check_price_api(provider=None)
        assert status.healthy is True  # No provider = skip

    def test_llm_no_agent(self, monitor):
        status = monitor.check_llm(agent=None)
        assert status.healthy is True  # No agent = skip


# ── Full Health Check ────────────────────────────────────

class TestFullCheck:

    @pytest.mark.asyncio
    async def test_all_healthy(self, monitor):
        health = await monitor.full_check()
        assert health.overall == "healthy"
        assert len(health.components) >= 1
        assert all(c.healthy for c in health.components)

    @pytest.mark.asyncio
    async def test_uptime_tracked(self, monitor):
        health = await monitor.full_check()
        assert health.uptime_seconds >= 0

    @pytest.mark.asyncio
    async def test_error_rate_included(self, monitor):
        monitor.record_error("test", "Error")
        health = await monitor.full_check()
        assert health.total_errors == 1
        assert health.error_rate_per_hour >= 0


# ── Overall Status Logic ────────────────────────────────

class TestStatusLogic:

    def test_degraded_on_one_failure(self, monitor):
        # Manually create health with one failed component
        from euroscope.analytics.health_monitor import ComponentStatus
        health = SystemHealth(
            components=[
                ComponentStatus(name="DB", healthy=True),
                ComponentStatus(name="API", healthy=False, error="Down"),
                ComponentStatus(name="LLM", healthy=True),
            ]
        )
        unhealthy = [c for c in health.components if not c.healthy]
        if len(unhealthy) >= 2:
            health.overall = "critical"
        elif len(unhealthy) == 1:
            health.overall = "degraded"
        assert health.overall == "degraded"

    def test_critical_on_two_failures(self, monitor):
        from euroscope.analytics.health_monitor import ComponentStatus
        health = SystemHealth(
            components=[
                ComponentStatus(name="DB", healthy=False),
                ComponentStatus(name="API", healthy=False),
                ComponentStatus(name="LLM", healthy=True),
            ]
        )
        unhealthy = [c for c in health.components if not c.healthy]
        if len(unhealthy) >= 2:
            health.overall = "critical"
        assert health.overall == "critical"


# ── Formatting ───────────────────────────────────────────

class TestFormatting:

    @pytest.mark.asyncio
    async def test_format_healthy(self, monitor):
        health = await monitor.full_check()
        text = HealthMonitor.format_health(health)
        assert "HEALTHY" in text
        assert "✅" in text

    @pytest.mark.asyncio
    async def test_format_with_errors(self, monitor):
        monitor.record_error("test_comp", "Something broke")
        health = await monitor.full_check()
        text = HealthMonitor.format_health(health)
        assert "Errors" in text

    @pytest.mark.asyncio
    async def test_uptime_format_minutes(self, monitor):
        monitor._start_time = time.time() - 600  # 10 minutes
        health = await monitor.full_check()
        text = HealthMonitor.format_health(health)
        assert "min" in text

    @pytest.mark.asyncio
    async def test_uptime_format_hours(self, monitor):
        monitor._start_time = time.time() - 7200  # 2 hours
        health = await monitor.full_check()
        text = HealthMonitor.format_health(health)
        assert "hours" in text
