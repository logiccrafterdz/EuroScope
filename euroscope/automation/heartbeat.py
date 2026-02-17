"""
Heartbeat Service — Background task runner with periodic health checks.

Runs scheduled health checks, updates workspace HEARTBEAT.md,
and triggers alerts on status changes.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from .events import Event

logger = logging.getLogger("euroscope.automation.heartbeat")


class HeartbeatService:
    """
    Background service that periodically runs health checks
    and updates the workspace heartbeat status.

    Usage:
        hb = HeartbeatService(interval=60)
        hb.register_check("price_api", check_price_connectivity)
        await hb.start()
    """

    def __init__(self, interval: int = 60, event_bus=None):
        self.interval = interval
        self._checks: dict[str, Callable] = {}
        self._results: dict[str, dict] = {}
        self._listeners: list[Callable] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._tick_task: Optional[asyncio.Task] = None
        self._event_bus = event_bus
        self._tick_count = 0
        self._tick_interval = 30

    def register_check(self, name: str, check_fn: Callable):
        """
        Register a health check function.

        Args:
            name: Component name (e.g. "price_api", "database")
            check_fn: Callable that returns {"status": str, "detail": str}
                      Can be sync or async.
        """
        self._checks[name] = check_fn
        logger.info(f"Heartbeat: registered check '{name}'")

    def on_status_change(self, callback: Callable):
        """Register a listener for status changes."""
        self._listeners.append(callback)

    async def start(self):
        """Start the heartbeat loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self._tick_task = asyncio.create_task(self._tick_loop())
        logger.info(f"Heartbeat started (interval={self.interval}s)")

    async def stop(self):
        """Stop the heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        logger.info("Heartbeat stopped")

    async def _loop(self):
        """Main heartbeat loop."""
        while self._running:
            try:
                await self.tick()
            except Exception as e:
                logger.error(f"Heartbeat tick error: {e}")
            await asyncio.sleep(self.interval)

    async def _tick_loop(self):
        while self._running:
            if self._event_bus:
                try:
                    await self._event_bus.emit(Event("tick.30s", "heartbeat", {"tick": self._tick_count}))
                except Exception as e:
                    logger.error(f"Heartbeat tick event error: {e}")
            await asyncio.sleep(self._tick_interval)

    async def tick(self) -> dict[str, dict]:
        """Run all checks once and return results."""
        self._tick_count += 1
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

        for name, check_fn in self._checks.items():
            try:
                start = time.monotonic()
                if asyncio.iscoroutinefunction(check_fn):
                    result = await check_fn()
                else:
                    result = check_fn()
                elapsed = round((time.monotonic() - start) * 1000, 1)

                status = result.get("status", "unknown")
                detail = result.get("detail", "")

                old = self._results.get(name, {}).get("status")
                self._results[name] = {
                    "status": status,
                    "detail": detail,
                    "response_ms": elapsed,
                    "last_check": timestamp,
                }

                # Notify on status change
                if old and old != status:
                    await self._notify_change(name, old, status)

            except Exception as e:
                old = self._results.get(name, {}).get("status")
                self._results[name] = {
                    "status": "error",
                    "detail": str(e)[:200],
                    "response_ms": 0,
                    "last_check": timestamp,
                }
                if old != "error":
                    await self._notify_change(name, old or "unknown", "error")

        return dict(self._results)

    async def _notify_change(self, component: str, old: str, new: str):
        """Notify listeners of a status change."""
        event = {
            "component": component,
            "old_status": old,
            "new_status": new,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.warning(f"Status change: {component} {old} → {new}")
        for listener in self._listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event)
                else:
                    listener(event)
            except Exception as e:
                logger.error(f"Heartbeat listener error: {e}")

    @property
    def status(self) -> dict[str, dict]:
        return dict(self._results)

    @property
    def is_healthy(self) -> bool:
        if not self._results:
            return True
        return all(r.get("status") == "healthy" for r in self._results.values())

    @property
    def tick_count(self) -> int:
        return self._tick_count
