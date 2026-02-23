"""
Cron System — Scheduled task execution for recurring and one-time jobs.

Provides a lightweight scheduler for analysis runs, reports,
and maintenance tasks.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Callable, Optional
from enum import Enum

from ..brain.vector_memory import VectorMemory
from ..brain.proactive_engine import ProactiveEngine, AlertPriority

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
        now = datetime.now(UTC)
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
        self.alerts.add((chat_id, message_hash, datetime.now(UTC)))
        self.user_alerts.setdefault(chat_id, []).append(datetime.now(UTC))

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
        self.proactive_engine = ProactiveEngine()
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
        
        # Schedule periodic 'Market Pulse' (every 2 hours during active sessions)
        self._schedule_periodic_pulse()
        # Schedule self-learning loop
        self._schedule_learning_tasks()

    def _schedule_periodic_pulse(self):
        async def pulse_task():
            if self._is_quiet_time():
                return
            try:
                agent = getattr(self.bot, "agent", None)
                if not agent:
                    return
                
                pulse_text = await agent.run_periodic_observation()
                chat_ids = getattr(self.config, "proactive_alert_chat_ids", [])
                
                for chat_id in chat_ids:
                    message = (
                        f"🌐 <b>EuroScope Market Pulse</b>\n\n"
                        f"{pulse_text}\n\n"
                        f"<i>— Continuous Thinking & Learning</i>"
                    )
                    await self._send_proactive_alert_message(chat_id, message)
            except Exception as e:
                logger.error(f"Periodic pulse task failed: {e}")

        # Run every 2 hours (7200 seconds) during active sessions
        interval_secs = 2 * 3600
        self.schedule(
            "market_pulse",
            TaskFrequency.MINUTELY,
            pulse_task,
            interval_seconds=interval_secs,
            delay=120,  # First pulse 2 min after startup
        )

    async def _send_proactive_alert_message(self, chat_id: int, text: str) -> bool:
        if not self.bot:
            return False
        app = getattr(self.bot, "application", None) or getattr(self.bot, "bot", None)
        telegram_bot = getattr(app, "bot", None) if app else None
        if not telegram_bot:
            return False
            
        try:
            await telegram_bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send proactive message to {chat_id}: {e}")
            return False

    def _seconds_until(self, hour: int, minute: int) -> int:
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)
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

        # Weekend Insights mode: allow MEDIUM+ analysis on weekends
        # instead of full blackout — the bot stays engaged
        if getattr(self.config, "proactive_disable_weekends", False):
            if now.weekday() >= 5:
                # Don't block completely — let proactive analysis run
                # but _schedule_proactive_analysis will handle reduced frequency
                pass

        holiday_dates = set(getattr(self.config, "proactive_holiday_dates", []))
        if holiday_dates and now.strftime("%Y-%m-%d") in holiday_dates:
            return True
        return False

    def _schedule_proactive_analysis(self):
        async def analysis_task():
            if self._is_quiet_time():
                return
            try:

                # Reuse the bot's agent (has router, orchestrator, vector_memory)
                agent = getattr(self.bot, "agent", None)
                if agent is None:
                    logger.warning("Proactive analysis skipped: no agent available on bot")
                    return
                decision = await asyncio.wait_for(
                    agent.run_proactive_analysis(),
                    timeout=90,
                )
                if not decision.get("should_alert"):
                    logger.debug("Proactive analysis: No alert warranted")
                    return

                # Phase 3A: Context-Aware Suppression
                from ..brain.proactive_engine import MarketEvent, AlertPriority as EnginePriority
                
                # Convert string priority from LLM to EnginePriority enum
                p_str = decision.get("priority", "low").upper()
                try:
                    priority = EnginePriority[p_str]
                except KeyError:
                    priority = EnginePriority.LOW

                event = MarketEvent(
                    type="proactive_scan",
                    description=decision.get("message", ""),
                    metadata=decision
                )

                if self.proactive_engine.should_suppress(event, user_min_priority=EnginePriority.LOW):
                    logger.info(f"Proactive alert suppressed by engine logic ({p_str})")
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
                        self.proactive_engine.mark_alerted(event)
                        self._alert_cache.record_alert(chat_id, message)
                        logger.info(
                            f"Proactive alert sent [{decision.get('priority')}]: "
                            f"{message[:50]} | Reason: {decision.get('reason')}"
                        )

                # Auto-notify for new signals via NotificationManager
                try:
                    notifier = getattr(self.bot, "notification_manager", None)
                    if notifier and decision.get("signal"):
                        signal_data = decision.get("signal", {})
                        for chat_id in chat_ids:
                            await notifier.notify_new_signal(chat_id, signal_data)
                except Exception as notify_err:
                    logger.warning(f"Signal notification failed: {notify_err}")

            except Exception as e:
                logger.error(f"Proactive analysis failed: {e}", exc_info=True)

        interval_value = getattr(self.config, "proactive_analysis_interval_minutes", 15)
        if isinstance(interval_value, int):
            interval = interval_value
        elif isinstance(interval_value, str) and interval_value.strip().isdigit():
            interval = int(interval_value)
        else:
            interval = 15
        seconds = max(60, interval * 60)
        task = ScheduledTask(
            name="proactive_market_analysis",
            frequency=TaskFrequency.MINUTELY,
            callback=analysis_task,
            interval_seconds=seconds,
            next_run=time.time() + 90,  # First run 90s after startup
        )
        self._tasks[task.name] = task
        logger.info(f"Cron: scheduled '{task.name}' ({interval}m)")

    def _schedule_learning_tasks(self):
        """Schedule self-learning loop: resolve patterns, forecasts, and daily tuning."""

        async def learning_tick():
            if self._is_quiet_time():
                return
            try:
                from ..learning.pattern_tracker import PatternTracker
                from ..learning.forecast_tracker import ForecastTracker

                storage = getattr(self.bot, "storage", None)
                if not storage:
                    from ..data.storage import Storage
                    storage = Storage()

                provider = getattr(self.bot, "price_provider", None)
                if not provider:
                    return

                price_data = await provider.get_price()
                current_price = price_data.get("price")
                if not current_price:
                    return

                # 1. Resolve pending patterns
                pt = PatternTracker(storage=storage)
                pt.resolve_pending(current_price)

                # 2. Resolve open forecasts
                ft = ForecastTracker(storage=storage)
                resolved = ft.resolve_all(current_price)
                if resolved:
                    logger.info(f"Learning: resolved {len(resolved)} forecasts")

            except Exception as e:
                logger.error(f"Learning tick failed: {e}")

        async def daily_tuning():
            try:
                from ..learning.adaptive_tuner import AdaptiveTuner

                storage = getattr(self.bot, "storage", None)
                if not storage:
                    from ..data.storage import Storage
                    storage = Storage()

                tuner = AdaptiveTuner(storage=storage)
                report = tuner.format_report()

                chat_ids = getattr(self.config, "proactive_alert_chat_ids", [])
                for chat_id in chat_ids:
                    await self._send_proactive_alert_message(
                        chat_id,
                        f"📊 <b>Daily Self-Learning Report</b>\n\n{report}\n\n"
                        f"<i>— EuroScope Adaptive Tuner</i>"
                    )
            except Exception as e:
                logger.error(f"Daily tuning report failed: {e}")

        # Learning tick every 15 minutes
        self.schedule(
            "learning_tick",
            TaskFrequency.MINUTELY,
            learning_tick,
            interval_seconds=900,
            delay=120,
        )
        logger.info("Cron: scheduled 'learning_tick' (15m)")

        # Daily tuning report at ~18:00 UTC
        self.schedule(
            "daily_tuning_report",
            TaskFrequency.DAILY,
            daily_tuning,
            delay=self._seconds_until(18, 0),
        )
        logger.info("Cron: scheduled 'daily_tuning_report' (daily 18:00 UTC)")

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

        emoji = {
            "critical": "🚨",
            "high": "🔥",
            "medium": "⚠️",
            "low": "ℹ️"
        }.get(decision.get("priority"), "ℹ️")
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
                 callback: Callable, delay: int = 0, interval_seconds: int = 0) -> ScheduledTask:
        """
        Schedule a recurring task.

        Args:
            name: Unique task name
            frequency: How often to run
            callback: Function to execute (sync or async)
            delay: Initial delay in seconds before first run
            interval_seconds: Custom interval (overrides frequency default if > 0)
        """
        interval = interval_seconds if interval_seconds > 0 else _FREQ_SECONDS.get(frequency, 60)
        task = ScheduledTask(
            name=name,
            frequency=frequency,
            callback=callback,
            interval_seconds=interval,
            next_run=time.time() + delay,
        )
        self._tasks[name] = task
        logger.info(f"Cron: scheduled '{name}' ({frequency.value}, interval={interval}s)")
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
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Cron loop tick failed (recovering): {e}", exc_info=True)
            await asyncio.sleep(self.tick_interval)

    async def _tick(self):
        """Check and execute due tasks."""
        for task in list(self._tasks.values()):
            if not task.is_due():
                continue

            try:
                start = time.monotonic()
                if asyncio.iscoroutinefunction(task.callback):
                    await asyncio.wait_for(task.callback(), timeout=120)
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
                    "timestamp": datetime.now(UTC).isoformat(),
                })

                if task.max_runs and task.run_count >= task.max_runs:
                    task.enabled = False

            except asyncio.TimeoutError:
                logger.warning(f"Cron task '{task.name}' timed out after 120s — skipping")
                task.schedule_next()
                self._history.append({
                    "task": task.name,
                    "status": "timeout",
                    "timestamp": datetime.now(UTC).isoformat(),
                })
            except Exception as e:
                logger.error(f"Cron task '{task.name}' failed: {e}")
                task.schedule_next()
                self._history.append({
                    "task": task.name,
                    "status": "error",
                    "error": str(e)[:200],
                    "timestamp": datetime.now(UTC).isoformat(),
                })

        # Cap history to prevent unbounded growth
        if len(self._history) > 50:
            self._history = self._history[-50:]

    @property
    def tasks(self) -> dict[str, ScheduledTask]:
        return dict(self._tasks)

    @property
    def history(self) -> list[dict]:
        return list(self._history[-50:])
