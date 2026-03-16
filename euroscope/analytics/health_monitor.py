"""
Health Monitor — System Component Health Checks

Checks connectivity and status of all EuroScope components:
database, price API, news API, LLM, and tracks errors.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Optional

from ..data.storage import Storage

logger = logging.getLogger("euroscope.analytics.health")


@dataclass
class ComponentStatus:
    """Status of a single component."""
    name: str
    healthy: bool = True
    response_time_ms: float = 0.0
    last_check: str = ""
    error: str = ""


@dataclass
class SystemHealth:
    """Overall system health report."""
    overall: str = "healthy"  # healthy, degraded, critical
    components: list[ComponentStatus] = field(default_factory=list)
    uptime_seconds: float = 0.0
    total_errors: int = 0
    error_rate_per_hour: float = 0.0
    recent_errors: list[dict] = field(default_factory=list)


class HealthMonitor:
    """
    Monitors health of all EuroScope system components.

    Tracks error rates, component connectivity, and provides
    formatted health dashboards.
    """

    def __init__(self, storage: Storage = None):
        self.storage = storage
        self._start_time = time.time()
        self._errors: list[dict] = []
        self._max_errors = 100  # Rolling buffer

    # ── Error Tracking ───────────────────────────────────────

    def record_error(self, component: str, error: str, severity: str = "error"):
        """
        Record an error event.

        Args:
            component: Which component errored (e.g. "price_api", "llm")
            error: Error message
            severity: "warning", "error", or "critical"
        """
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "component": component,
            "error": error,
            "severity": severity,
        }
        self._errors.append(entry)

        # Rolling buffer
        if len(self._errors) > self._max_errors:
            self._errors = self._errors[-self._max_errors:]

        logger.log(
            logging.CRITICAL if severity == "critical" else
            logging.ERROR if severity == "error" else logging.WARNING,
            f"[{component}] {error}"
        )

    def get_error_rate(self, hours: float = 1.0) -> float:
        """Get error rate per the given time window."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        recent = [
            e for e in self._errors
            if datetime.fromisoformat(e["timestamp"]) > cutoff
        ]
        return round(len(recent) / hours, 2) if hours > 0 else 0

    def get_recent_errors(self, limit: int = 10) -> list[dict]:
        """Get the N most recent errors."""
        return self._errors[-limit:]

    # ── Component Checks ─────────────────────────────────────

    async def check_database(self) -> ComponentStatus:
        """Check database connectivity."""
        status = ComponentStatus(name="Database")
        start = time.time()
        try:
            # Simple query to verify DB is accessible
            await self.storage.get_accuracy_stats(days=1)
            status.healthy = True
            status.response_time_ms = round((time.time() - start) * 1000, 1)
        except Exception as e:
            status.healthy = False
            status.error = str(e)
            self.record_error("database", str(e))
        status.last_check = datetime.now(UTC).isoformat()
        return status

    def check_price_api(self, provider=None) -> ComponentStatus:
        """Check price data API connectivity."""
        status = ComponentStatus(name="Price API")
        if provider is None:
            status.healthy = True
            status.response_time_ms = 0
            status.last_check = datetime.now(UTC).isoformat()
            return status

        start = time.time()
        try:
            data = provider.get_price()
            status.healthy = "error" not in data
            status.response_time_ms = round((time.time() - start) * 1000, 1)
            if not status.healthy:
                status.error = data.get("error", "Unknown error")
                self.record_error("price_api", status.error)
        except Exception as e:
            status.healthy = False
            status.error = str(e)
            self.record_error("price_api", str(e))
        status.last_check = datetime.now(UTC).isoformat()
        return status

    async def check_price_api_async(self, provider=None) -> ComponentStatus:
        """Async check for price data API connectivity."""
        status = ComponentStatus(name="Price API")
        if provider is None:
            status.healthy = True
            status.response_time_ms = 0
            status.last_check = datetime.now(UTC).isoformat()
            return status

        start = time.time()
        try:
            data = await provider.get_price()
            if isinstance(data, dict):
                status.healthy = "error" not in data
                if not status.healthy:
                    status.error = data.get("error", "Unknown error")
                    self.record_error("price_api", status.error)
            else:
                status.healthy = False
                status.error = "Invalid price response"
                self.record_error("price_api", status.error)
            status.response_time_ms = round((time.time() - start) * 1000, 1)
        except Exception as e:
            status.healthy = False
            status.error = str(e)
            self.record_error("price_api", str(e))
        status.last_check = datetime.now(UTC).isoformat()
        return status

    def check_llm(self, agent=None) -> ComponentStatus:
        """Check LLM API connectivity."""
        status = ComponentStatus(name="LLM API")
        if agent is None:
            status.healthy = True
            status.response_time_ms = 0
            status.last_check = datetime.now(UTC).isoformat()
            return status

        start = time.time()
        try:
            router = getattr(agent, "router", None)
            api_key = getattr(getattr(agent, "config", None), "api_key", "")
            status.healthy = bool(router or api_key)
            status.response_time_ms = round((time.time() - start) * 1000, 1)
            if not status.healthy:
                status.error = "LLM not configured"
        except Exception as e:
            status.healthy = False
            status.error = str(e)
            self.record_error("llm", str(e))
        status.last_check = datetime.now(UTC).isoformat()
        return status

    async def check_cron(self, cron=None) -> ComponentStatus:
        """Check the health of scheduled tasks."""
        status = ComponentStatus(name="Cron Tasks")
        if cron is None:
            status.healthy = True
            status.last_check = datetime.now(UTC).isoformat()
            return status

        try:
            tasks = cron.tasks
            failing = [t for t in tasks.values() if t.consecutive_failures >= 3]
            
            if failing:
                status.healthy = False
                status.error = f"{len(failing)} tasks failing: " + ", ".join([t.name for t in failing])
            else:
                status.healthy = True
            
            status.last_check = datetime.now(UTC).isoformat()
        except Exception as e:
            status.healthy = False
            status.error = str(e)
            self.record_error("cron", str(e))
        
        return status

    # ── Full Health Check ────────────────────────────────────

    async def full_check(self, provider=None, agent=None, cron=None) -> SystemHealth:
        """
        Run all component health checks.

        Returns:
            SystemHealth with overall status and component details
        """
        components = [
            await self.check_database(),
            self.check_price_api(provider),
            self.check_llm(agent),
            await self.check_cron(cron),
        ]

        uptime = time.time() - self._start_time
        error_rate = self.get_error_rate(1.0)

        # Determine overall status
        unhealthy = [c for c in components if not c.healthy]
        if any(c.name == "Database" and not c.healthy for c in components):
            overall = "critical"
        elif len(unhealthy) >= 2:
            overall = "critical"
        elif len(unhealthy) == 1:
            overall = "degraded"
        else:
            overall = "healthy"

        return SystemHealth(
            overall=overall,
            components=components,
            uptime_seconds=round(uptime, 0),
            total_errors=len(self._errors),
            error_rate_per_hour=error_rate,
            recent_errors=self.get_recent_errors(5),
        )

    async def full_check_async(self, provider=None, agent=None, cron=None) -> SystemHealth:
        """
        Run all component health checks asynchronously.
        """
        components = [
            await self.check_database(),
            await self.check_price_api_async(provider),
            self.check_llm(agent),
            await self.check_cron(cron),
        ]

        uptime = time.time() - self._start_time
        error_rate = self.get_error_rate(1.0)

        unhealthy = [c for c in components if not c.healthy]
        if any(c.name == "Database" and not c.healthy for c in components):
            overall = "critical"
        elif len(unhealthy) >= 2:
            overall = "critical"
        elif len(unhealthy) == 1:
            overall = "degraded"
        else:
            overall = "healthy"

        return SystemHealth(
            overall=overall,
            components=components,
            uptime_seconds=round(uptime, 0),
            total_errors=len(self._errors),
            error_rate_per_hour=error_rate,
            recent_errors=self.get_recent_errors(5),
        )

    # ── Formatting ───────────────────────────────────────────

    @staticmethod
    def format_health(health: SystemHealth) -> str:
        """Format health report for Telegram."""
        status_icon = {
            "healthy": "🟢",
            "degraded": "🟡",
            "critical": "🔴",
        }

        # Uptime formatting
        uptime_h = health.uptime_seconds / 3600
        if uptime_h >= 24:
            uptime_str = f"{uptime_h / 24:.1f} days"
        elif uptime_h >= 1:
            uptime_str = f"{uptime_h:.1f} hours"
        else:
            uptime_str = f"{health.uptime_seconds / 60:.0f} min"

        lines = [
            f"🏥 *System Health*\n",
            f"Status: {status_icon.get(health.overall, '⚪')} {health.overall.upper()}",
            f"⏱ Uptime: {uptime_str}",
            f"⚠️ Errors (1h): {health.error_rate_per_hour}/h",
            f"📊 Total Errors: {health.total_errors}",
            "\n*Components:*",
        ]

        for c in health.components:
            icon = "✅" if c.healthy else "❌"
            latency = f" ({c.response_time_ms}ms)" if c.response_time_ms > 0 else ""
            error_info = f" — {c.error}" if c.error else ""
            lines.append(f"  {icon} {c.name}{latency}{error_info}")

        if health.recent_errors:
            lines.append("\n*Recent Errors:*")
            for err in health.recent_errors[-3:]:
                lines.append(
                    f"  ⚠️ [{err['component']}] {err['error'][:60]}"
                )

        return "\n".join(lines)
