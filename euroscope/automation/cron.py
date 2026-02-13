"""
Cron System — Scheduled task execution for recurring and one-time jobs.

Provides a lightweight scheduler for analysis runs, reports,
and maintenance tasks.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional
from enum import Enum

logger = logging.getLogger("euroscope.automation.cron")


class TaskFrequency(Enum):
    ONCE = "once"
    MINUTELY = "minutely"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


@dataclass
class ScheduledTask:
    """A scheduled task definition."""
    name: str
    frequency: TaskFrequency
    callback: Callable
    interval_seconds: int = 0
    last_run: Optional[float] = None
    next_run: float = 0.0
    run_count: int = 0
    enabled: bool = True
    max_runs: int = 0  # 0 = unlimited

    def is_due(self) -> bool:
        return self.enabled and time.time() >= self.next_run

    def schedule_next(self):
        if self.frequency == TaskFrequency.ONCE:
            self.enabled = False
        else:
            self.next_run = time.time() + self.interval_seconds


_FREQ_SECONDS = {
    TaskFrequency.MINUTELY: 60,
    TaskFrequency.HOURLY: 3600,
    TaskFrequency.DAILY: 86400,
    TaskFrequency.WEEKLY: 604800,
}


class CronScheduler:
    """
    Lightweight task scheduler.

    Usage:
        cron = CronScheduler()
        cron.schedule("daily_report", TaskFrequency.DAILY, generate_report)
        cron.schedule_once("startup_check", check_config)
        await cron.start()
    """

    def __init__(self, tick_interval: int = 10):
        self.tick_interval = tick_interval
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._history: list[dict] = []

    def schedule(self, name: str, frequency: TaskFrequency,
                 callback: Callable, delay: int = 0) -> ScheduledTask:
        """
        Schedule a recurring task.

        Args:
            name: Unique task name
            frequency: How often to run
            callback: Function to execute (sync or async)
            delay: Initial delay in seconds before first run
        """
        interval = _FREQ_SECONDS.get(frequency, 60)
        task = ScheduledTask(
            name=name,
            frequency=frequency,
            callback=callback,
            interval_seconds=interval,
            next_run=time.time() + delay,
        )
        self._tasks[name] = task
        logger.info(f"Cron: scheduled '{name}' ({frequency.value})")
        return task

    def schedule_once(self, name: str, callback: Callable,
                      delay: int = 0) -> ScheduledTask:
        """Schedule a one-time task."""
        task = ScheduledTask(
            name=name,
            frequency=TaskFrequency.ONCE,
            callback=callback,
            interval_seconds=0,
            next_run=time.time() + delay,
            max_runs=1,
        )
        self._tasks[name] = task
        logger.info(f"Cron: scheduled one-time '{name}'")
        return task

    def cancel(self, name: str) -> bool:
        """Cancel a scheduled task."""
        if name in self._tasks:
            self._tasks[name].enabled = False
            logger.info(f"Cron: cancelled '{name}'")
            return True
        return False

    async def start(self):
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Cron scheduler started")

    async def stop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Cron scheduler stopped")

    async def _loop(self):
        while self._running:
            await self._tick()
            await asyncio.sleep(self.tick_interval)

    async def _tick(self):
        """Check and execute due tasks."""
        for task in list(self._tasks.values()):
            if not task.is_due():
                continue

            try:
                start = time.monotonic()
                if asyncio.iscoroutinefunction(task.callback):
                    await task.callback()
                else:
                    task.callback()
                elapsed = round((time.monotonic() - start) * 1000, 1)

                task.last_run = time.time()
                task.run_count += 1
                task.schedule_next()

                self._history.append({
                    "task": task.name,
                    "status": "success",
                    "elapsed_ms": elapsed,
                    "timestamp": datetime.utcnow().isoformat(),
                })

                if task.max_runs and task.run_count >= task.max_runs:
                    task.enabled = False

            except Exception as e:
                logger.error(f"Cron task '{task.name}' failed: {e}")
                task.schedule_next()
                self._history.append({
                    "task": task.name,
                    "status": "error",
                    "error": str(e)[:200],
                    "timestamp": datetime.utcnow().isoformat(),
                })

    @property
    def tasks(self) -> dict[str, ScheduledTask]:
        return dict(self._tasks)

    @property
    def history(self) -> list[dict]:
        return list(self._history[-50:])
