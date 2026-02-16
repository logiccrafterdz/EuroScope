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

from ..brain.vector_memory import VectorMemory

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


class ProactiveAlertCache:
    def __init__(self, cache_duration_minutes: int = 60, per_user_limit: int = 3):
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self.per_user_limit = per_user_limit
        self.alerts: set[tuple[int, int, datetime]] = set()
        self.user_alerts: dict[int, list[datetime]] = {}

    def _prune(self) -> None:
        now = datetime.utcnow()
        self.alerts = {
            (uid, h, ts) for uid, h, ts in self.alerts
            if now - ts < self.cache_duration
        }
        for chat_id, timestamps in list(self.user_alerts.items()):
            self.user_alerts[chat_id] = [ts for ts in timestamps if now - ts < timedelta(hours=1)]
            if not self.user_alerts[chat_id]:
                self.user_alerts.pop(chat_id, None)

    def is_duplicate(self, chat_id: int, message: str) -> bool:
        self._prune()
        message_hash = hash(message.lower().strip()[:50])
        for cached_chat, cached_hash, _ in self.alerts:
            if cached_chat == chat_id and cached_hash == message_hash:
                return True
        return False

    def record_alert(self, chat_id: int, message: str) -> None:
        self._prune()
        message_hash = hash(message.lower().strip()[:50])
        self.alerts.add((chat_id, message_hash, datetime.utcnow()))
        self.user_alerts.setdefault(chat_id, []).append(datetime.utcnow())

    def within_user_limit(self, chat_id: int) -> bool:
        self._prune()
        return len(self.user_alerts.get(chat_id, [])) < self.per_user_limit


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

    def __init__(self, tick_interval: int = 10, config: Optional[object] = None, bot: Optional[object] = None):
        self.tick_interval = tick_interval
        self.config = config
        self.bot = bot
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._history: list[dict] = []
        self._proactive_warned = False
        cache_minutes = getattr(self.config, "proactive_alert_cache_minutes", 60)
        try:
            cache_minutes = int(cache_minutes)
        except Exception:
            cache_minutes = 60
        self._alert_cache = ProactiveAlertCache(
            cache_duration_minutes=cache_minutes,
            per_user_limit=3,
        )
        if self.config and getattr(self.config, "vector_memory_ttl_days", None):
            self._schedule_vector_memory_cleanup()
        interval_value = getattr(self.config, "proactive_analysis_interval_minutes", None)
        interval = None
        if isinstance(interval_value, int):
            interval = interval_value
        elif isinstance(interval_value, str) and interval_value.strip().isdigit():
            interval = int(interval_value)
        if self.config and interval and interval > 0:
            self._schedule_proactive_analysis()

    def _seconds_until(self, hour: int, minute: int) -> int:
        now = datetime.utcnow()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return max(0, int((target - now).total_seconds()))

    def _schedule_vector_memory_cleanup(self):
        async def cleanup_task():
            try:
                memory = VectorMemory()
                deleted = await memory.cleanup_old_documents(
                    ttl_days=self.config.vector_memory_ttl_days
                )
                if deleted > 0:
                    logger.info(f"Vector Memory: {deleted} old documents purged")
            except Exception as e:
                logger.error(f"Vector Memory cleanup task failed: {e}")

        delay = self._seconds_until(3, 0)
        self.schedule("vector_memory_cleanup", TaskFrequency.DAILY, cleanup_task, delay=delay)

    def set_bot(self, bot: object) -> None:
        self.bot = bot

    def _is_quiet_time(self) -> bool:
        now = datetime.utcnow()
        quiet_hours = getattr(self.config, "proactive_quiet_hours", None)
        if quiet_hours:
            start, end = quiet_hours
            if start == end:
                return True
            if start < end:
                if start <= now.hour < end:
                    return True
            else:
                if now.hour >= start or now.hour < end:
                    return True

        if getattr(self.config, "proactive_disable_weekends", False):
            if now.weekday() >= 5:
                return True

        holiday_dates = set(getattr(self.config, "proactive_holiday_dates", []))
        if holiday_dates and now.strftime("%Y-%m-%d") in holiday_dates:
            return True
        return False

    def _schedule_proactive_analysis(self):
        async def analysis_task():
            if self._is_quiet_time():
                return
            try:
                from ..brain.agent import Agent
                from ..analytics.health_monitor import HealthMonitor
                from ..data.storage import Storage

                storage = Storage()
                monitor = HealthMonitor(storage=storage)
                health = await monitor.full_check_async()
                healthy_components = [c for c in health.components if c.healthy]
                health_score = (len(healthy_components) / max(len(health.components), 1)) * 100
                if health_score < 90:
                    logger.warning("Proactive analysis skipped due to health score")
                    return

                agent = Agent(config=self.config.llm)
                decision = await agent.run_proactive_analysis()
                if not decision.get("should_alert"):
                    logger.debug("Proactive analysis: No alert warranted")
                    return

                message = decision.get("message") or ""
                if not message:
                    logger.debug("Proactive analysis: Missing alert message")
                    return

                chat_ids = getattr(self.config, "proactive_alert_chat_ids", [])
                if not chat_ids:
                    if not self._proactive_warned:
                        logger.warning("Proactive alerts enabled but no chat IDs configured")
                        self._proactive_warned = True
                    return

                for chat_id in chat_ids:
                    if self._alert_cache.is_duplicate(chat_id, message):
                        logger.debug("Proactive analysis: Duplicate alert suppressed")
                        continue
                    if not self._alert_cache.within_user_limit(chat_id):
                        logger.debug("Proactive analysis: Rate limit suppressed")
                        continue
                    sent = await self._send_proactive_alert(chat_id, decision)
                    if sent:
                        self._alert_cache.record_alert(chat_id, message)
                        logger.info(
                            f"Proactive alert sent [{decision.get('priority')}]: "
                            f"{message[:50]} | Reason: {decision.get('reason')}"
                        )
            except Exception as e:
                logger.error(f"Proactive analysis failed: {e}", exc_info=True)

        interval_value = getattr(self.config, "proactive_analysis_interval_minutes", 30)
        if isinstance(interval_value, int):
            interval = interval_value
        elif isinstance(interval_value, str) and interval_value.strip().isdigit():
            interval = int(interval_value)
        else:
            interval = 30
        seconds = max(60, interval * 60)
        task = ScheduledTask(
            name="proactive_market_analysis",
            frequency=TaskFrequency.MINUTELY,
            callback=analysis_task,
            interval_seconds=seconds,
            next_run=time.time() + seconds,
        )
        self._tasks[task.name] = task
        logger.info(f"Cron: scheduled '{task.name}' ({interval}m)")

    async def _send_proactive_alert(self, chat_id: int, decision: dict) -> bool:
        if not self.bot:
            return False
        app = getattr(self.bot, "application", None) or getattr(self.bot, "bot", None)
        telegram_bot = getattr(app, "bot", None) if app else None
        if not telegram_bot:
            return False

        if str(chat_id) not in getattr(self.config, "admin_chat_ids", []):
            limiter = getattr(self.bot, "rate_limiter", None)
            if limiter:
                allowed, _ = await limiter.is_allowed(chat_id)
                if not allowed:
                    return False

        emoji = {"urgent": "🚨", "medium": "⚠️", "low": "ℹ️"}.get(decision.get("priority"), "ℹ️")
        message = (
            f"{emoji} <b>Proactive Alert ({decision.get('priority', 'low').upper()})</b>\n\n"
            f"{decision.get('message')}\n\n"
            f"<i>— EuroScope Autonomous Analysis</i>"
        )
        await telegram_bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="HTML",
        )
        return True

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
