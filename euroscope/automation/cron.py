"""
Cron System — Scheduled task execution for recurring and one-time jobs.

Provides a lightweight scheduler for analysis runs, reports,
and maintenance tasks.
"""

import inspect
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
    is_running: bool = False

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

    def __init__(self, tick_interval: int = 10, config: Optional[object] = None, bot: Optional[object] = None, storage: Optional[object] = None):
        self.tick_interval = tick_interval
        self.config = config
        self.bot = bot
        self.storage = storage
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._history: list[dict] = []
        self._active_tasks = set()
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

        # Always schedule proactive analysis (default 15 min)
        self._schedule_proactive_analysis()
        
        # Schedule periodic 'Market Pulse' (every 2 hours during active sessions)
        self._schedule_periodic_pulse()
        # Schedule self-learning loop
        self._schedule_learning_tasks()
        
        # --- PHASE 4: Autonomous Paper Trader ---
        self._schedule_auto_trader()
        self._schedule_trade_monitor()
        self._schedule_weekly_report()
        
        logger.info(f"Cron: {len(self._tasks)} tasks scheduled: {list(self._tasks.keys())}")

    def _schedule_periodic_pulse(self):
        async def pulse_task():
            logger.info("Market Pulse task starting...")
            if self._is_quiet_time():
                logger.info("Market Pulse skipped: quiet time")
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
            logger.info("Proactive analysis task starting...")
            if self._is_quiet_time():
                logger.info("Proactive analysis skipped: quiet time")
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

                storage = self.storage or getattr(self.bot, "storage", None)
                if not storage:
                    logger.error("Learning tick failed: No storage available")
                    return

                provider = getattr(self.bot, "price_provider", None)
                if not provider:
                    return

                price_data = await provider.get_price()
                current_price = price_data.get("price")
                if not current_price:
                    return

                # 1. Resolve pending patterns
                pt = getattr(self.bot, "pattern_tracker", None)
                if not pt:
                    pt = PatternTracker(storage=storage)
                await pt.resolve_pending(current_price)

                # 2. Resolve open forecasts
                ft = ForecastTracker(storage=storage)
                resolved = await ft.resolve_all(current_price)
                if resolved:
                    logger.info(f"Learning: resolved {len(resolved)} forecasts")
                    
                    # Store the lessons in Vector Memory
                    from ..brain.vector_memory import VectorMemory
                    vm = VectorMemory()
                    for fc in resolved:
                        if hasattr(fc, "_lesson_text") and fc._lesson_text:
                            vm.store_analysis(
                                text=fc._lesson_text,
                                metadata={"skill": fc.skill, "outcome": fc.outcome, "type": "learning_lesson"}
                            )

            except Exception as e:
                logger.error(f"Learning tick failed: {e}")

        async def daily_tuning():
            try:
                from ..learning.adaptive_tuner import AdaptiveTuner

                storage = self.storage or getattr(self.bot, "storage", None)
                if not storage:
                    logger.error("Learning tick failed: No storage available")
                    return

                tuner = getattr(self.bot, "adaptive_tuner", None)
                if not tuner:
                    from ..learning.adaptive_tuner import AdaptiveTuner
                    tuner = AdaptiveTuner(storage=storage)
                await tuner.auto_tune()
                report = await tuner.format_report()

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

    def _schedule_auto_trader(self):
        """Phase 4: Autonomous Paper Trader that scans the market and executes trades."""
        async def auto_trade_task():
            logger.info("Auto Trader task starting...")
            bot_settings = getattr(self.bot, "bot_settings", {})
            if not bot_settings.get("auto_trading_enabled"):
                logger.debug("Auto Trader skipped: auto_trading_enabled is OFF")
                return
                
            if self._is_quiet_time():
                logger.debug("Auto Trader skipped: quiet time")
                return
                
            orchestrator = getattr(self.bot, "orchestrator", None)
            if not orchestrator:
                return
                
            try:
                # 1. Run the full analytical pipeline
                ctx = await orchestrator.run_full_analysis_pipeline(timeframe="H1")
                
                # 2. Re-evaluate strategy with fresh context
                strat_res = await orchestrator.run_skill("trading_strategy", "detect_signal", context=ctx)
                if not strat_res.success:
                    return
                    
                signal_data = strat_res.data
                direction = signal_data.get("direction", "WAIT")
                confidence = signal_data.get("confidence", 0)
                
                # Only execute high-confidence signals autonomously
                if direction in ("BUY", "SELL") and confidence >= 60:
                    logger.info(f"Auto Trader found high-confidence {direction} signal ({confidence}%)!")
                    
                    # 2.5 Run safety guardrails before execution
                    from ..trading.safety_guardrails import SafetyGuardrail
                    guardrail = SafetyGuardrail(config=self.config, storage=self.storage)
                    blocked, reason = await guardrail.should_block_signal(ctx)
                    
                    if blocked:
                        logger.warning(f"Auto Trader BLOCKED by Safety Guardrails: {reason}")
                        chat_ids = getattr(self.config, "admin_chat_ids", [])
                        for chat_id in chat_ids:
                            msg = (
                                f"🛡️ <b>Trade Blocked by Safety Guardrail</b>\n\n"
                                f"Direction: <b>{direction}</b> EUR/USD\n"
                                f"Reason: {reason}\n\n"
                                f"<i>— EuroScope Auto-Trader</i>"
                            )
                            await self._send_proactive_alert_message(chat_id, msg)
                        return
                        
                    # Enhance safety (e.g. widen SL if volatile)
                    ctx = await guardrail.enhance_signal_safety(ctx)
                    
                    # 3. Execute the paper trade
                    exec_res = await orchestrator.run_skill("signal_executor", "open_trade", context=ctx)
                    if exec_res.success:
                        trade = exec_res.data
                        
                        # Extract the final parameters chosen by exactly what signal_executor did
                        entry_price = trade.get("entry_price")
                        sl = trade.get("stop_loss")
                        tp = trade.get("take_profit")
                        
                        # 4. Notify admins
                        chat_ids = getattr(self.config, "admin_chat_ids", [])
                        for chat_id in chat_ids:
                            msg = (
                                f"🤖 <b>Autonomous Trade Opened</b>\n\n"
                                f"Direction: <b>{direction}</b> EUR/USD\n"
                                f"Entry: {entry_price:.5f}\n"
                                f"SL: {sl:.5f} | TP: {tp:.5f}\n"
                                f"Confidence: {confidence}%\n\n"
                                f"<i>— EuroScope Auto-Trader</i>"
                            )
                            await self._send_proactive_alert_message(chat_id, msg)
                    else:
                        logger.warning(f"Auto Trader execution blocked: {exec_res.error}")
                        
            except Exception as e:
                logger.error(f"Auto Trader task failed: {e}", exc_info=True)

        interval_value = getattr(self.config, "proactive_analysis_interval_minutes", 15)
        try:
            interval = int(interval_value)
        except Exception:
            interval = 15
            
        seconds = max(60, interval * 60)
        self.schedule(
            "autonomous_trader",
            TaskFrequency.MINUTELY,
            auto_trade_task,
            interval_seconds=seconds,
            delay=180,  # Offset from proactive_analysis so they don't hit APIs at exact same second
        )
        logger.info(f"Cron: scheduled 'autonomous_trader' ({interval}m)")

    def _schedule_trade_monitor(self):
        """Phase 4: Monitors open trades every minute for TP/SL hits."""
        async def monitor_task():
            if self._is_quiet_time():
                return
                
            orchestrator = getattr(self.bot, "orchestrator", None)
            provider = getattr(self.bot, "price_provider", None)
            if not orchestrator or not provider:
                return
                
            try:
                # 1. Get current price
                price_data = await provider.get_price()
                current_price = price_data.get("price")
                if not current_price:
                    return
                    
                # 2. Get open trades
                trades_res = await orchestrator.run_skill("signal_executor", "list_trades")
                if not trades_res.success or not trades_res.data:
                    return
                    
                open_trades = [t for t in trades_res.data if str(t.get("status", "")).upper() == "OPEN"]
                
                # 3. Check Trailing Stops & TP/SL
                for trade in open_trades:
                    direction = trade.get("direction")
                    sl = trade.get("stop_loss")
                    tp = trade.get("take_profit")
                    entry = trade.get("entry_price")
                    trade_id = trade.get("trade_id")
                    
                    # Context required for signal_executor standard signature
                    from ..skills.base import SkillContext
                    ctx = SkillContext()
                    
                    # --- Trailing Stop Logic ---
                    if direction == "BUY":
                        floating_pips = (current_price - entry) * 10000
                        if floating_pips >= 20.0:
                            # Move SL to Break-Even + 5 pips if SL is still below that
                            new_sl = entry + 0.0005
                            if sl < new_sl:
                                logger.info(f"Trailing Stop Triggered ON {trade_id}: Moving SL {sl:.5f} -> {new_sl:.5f}")
                                await orchestrator.run_skill(
                                    "signal_executor", "update_trade", context=ctx,
                                    trade_id=trade_id, stop_loss=new_sl
                                )
                                sl = new_sl # Update local variable for TP/SL check below
                                
                    elif direction == "SELL":
                        floating_pips = (entry - current_price) * 10000
                        if floating_pips >= 20.0:
                            # Move SL to Break-Even + 5 pips if SL is still above that
                            new_sl = entry - 0.0005
                            if sl > new_sl:
                                logger.info(f"Trailing Stop Triggered ON {trade_id}: Moving SL {sl:.5f} -> {new_sl:.5f}")
                                await orchestrator.run_skill(
                                    "signal_executor", "update_trade", context=ctx,
                                    trade_id=trade_id, stop_loss=new_sl
                                )
                                sl = new_sl

                    # --- TP/SL Hit Logic ---
                    hit_tp = False
                    hit_sl = False
                    
                    if direction == "BUY":
                        if current_price >= tp: hit_tp = True
                        if current_price <= sl: hit_sl = True
                    elif direction == "SELL":
                        if current_price <= tp: hit_tp = True
                        if current_price >= sl: hit_sl = True
                        
                    if hit_tp or hit_sl:
                        logger.info(f"Trade Monitor: {trade_id} hit {'TP' if hit_tp else 'SL'} at {current_price:.5f}")
                        
                        close_res = await orchestrator.run_skill(
                            "signal_executor", 
                            "close_trade", 
                            context=ctx,
                            trade_id=trade_id, 
                            exit_price=current_price
                        )
                        
                        if close_res.success:
                            closed_trade = close_res.data
                            pnl = closed_trade.get("pnl_pips", 0)
                            outcome_emoji = "✅" if pnl > 0 else "❌"
                            
                            chat_ids = getattr(self.config, "admin_chat_ids", [])
                            for chat_id in chat_ids:
                                msg = (
                                    f"🤖 <b>Autonomous Trade Closed</b>\n\n"
                                    f"Status: {outcome_emoji} {'Take Profit' if hit_tp else 'Stop Loss'} Hit\n"
                                    f"Direction: <b>{direction}</b>\n"
                                    f"Exit Price: {current_price:.5f}\n"
                                    f"PnL: <b>{'+' if pnl > 0 else ''}{pnl:.1f} pips</b>\n\n"
                                    f"<i>— EuroScope Auto-Trader</i>"
                                )
                                await self._send_proactive_alert_message(chat_id, msg)
            except Exception as e:
                logger.error(f"Trade Monitor task failed: {e}", exc_info=True)

        self.schedule(
            "trade_monitor",
            TaskFrequency.MINUTELY,
            monitor_task,
            interval_seconds=60,  # Run every minute!
            delay=60,
        )
        logger.info("Cron: scheduled 'trade_monitor' (1m)")

    def _schedule_weekly_report(self):
        """Phase 4: Generates and sends a PDF performance report every Friday at 22:00 UTC."""
        async def generate_and_send_report():
            try:
                storage = self.storage or getattr(self.bot, "storage", None)
                if not storage:
                    logger.error("Weekly report failed: No storage available")
                    return
                    
                from ..analytics.report_generator import PDFReportGenerator
                generator = PDFReportGenerator(storage=storage)
                filepath = await generator.generate_weekly_report()
                
                if not filepath or not __import__('os').path.exists(filepath):
                    logger.warning("Weekly report generation yielded no file.")
                    return
                    
                app = getattr(self.bot, "application", None) or getattr(self.bot, "bot", None)
                telegram_bot = getattr(app, "bot", None) if app else None
                if not telegram_bot:
                    return

                chat_ids = getattr(self.config, "admin_chat_ids", [])
                for chat_id in chat_ids:
                    with open(filepath, "rb") as pdf_file:
                        await telegram_bot.send_document(
                            chat_id=chat_id,
                            document=pdf_file,
                            caption="📊 <b>EuroScope Weekly Performance Report</b>\n\nHere is your institutional tear sheet for the week.",
                            parse_mode="HTML"
                        )
                logger.info("Weekly PDF report generated and dispatched to admins.")
            except Exception as e:
                logger.error(f"Weekly report generation task failed: {e}", exc_info=True)

        now = datetime.now(UTC)
        # Calculate days ahead for next Friday (weekday 4)
        days_ahead = 4 - now.weekday()
        if days_ahead <= 0: # Target day already happened this week
            days_ahead += 7
            
        target = now + timedelta(days=days_ahead)
        target = target.replace(hour=22, minute=0, second=0, microsecond=0)
        
        if target <= now:
            target += timedelta(days=7)
            
        delay_seconds = int((target - now).total_seconds())

        self.schedule(
            "weekly_pdf_report",
            TaskFrequency.WEEKLY,
            generate_and_send_report,
            delay=delay_seconds,
        )
        logger.info("Cron: scheduled 'weekly_pdf_report' (Fridays @ 22:00 UTC)")

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
        """Check and execute due tasks concurrently."""
        async def run_task(task: ScheduledTask):
            try:
                start = time.monotonic()
                if inspect.iscoroutinefunction(task.callback) or inspect.isawaitable(task.callback):
                    await asyncio.wait_for(task.callback(), timeout=120)
                else:
                    res = task.callback()
                    if inspect.isawaitable(res):
                        await asyncio.wait_for(res, timeout=120)
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
            finally:
                task.is_running = False

        for task in list(self._tasks.values()):
            if not task.is_due() or getattr(task, "is_running", False):
                continue

            task.is_running = True
            t = asyncio.create_task(run_task(task))
            self._active_tasks.add(t)
            t.add_done_callback(self._active_tasks.discard)

        # Cap history to prevent unbounded growth
        if len(self._history) > 50:
            self._history = self._history[-50:]

    @property
    def tasks(self) -> dict[str, ScheduledTask]:
        return dict(self._tasks)

    @property
    def history(self) -> list[dict]:
        return list(self._history[-50:])
