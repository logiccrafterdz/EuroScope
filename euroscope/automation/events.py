"""
Event Bus — Pub/sub event system for cross-skill communication.

Skills can emit events and subscribe to events from other skills,
enabling reactive, event-driven workflows.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger("euroscope.automation.events")


@dataclass
class Event:
    """An event emitted by a skill or system component."""
    topic: str
    source: str
    data: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


class EventBus:
    """
    Publish/subscribe event bus for decoupled skill communication.

    Usage:
        bus = EventBus()
        bus.subscribe("signal.new", on_new_signal)
        bus.subscribe("price.alert", on_price_alert)
        await bus.emit(Event("signal.new", "trading_strategy", {"direction": "BUY"}))
    """

    def __init__(self, max_history: int = 100):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._wildcard_subscribers: list[Callable] = []
        self._history: list[Event] = []
        self._max_history = max_history

    def subscribe(self, topic: str, callback: Callable):
        """
        Subscribe to events on a topic.

        Args:
            topic: Event topic (e.g. "signal.new", "price.*")
                   Use "*" to subscribe to all events.
            callback: Function(Event) — can be sync or async.
        """
        if topic == "*":
            self._wildcard_subscribers.append(callback)
        else:
            self._subscribers[topic].append(callback)
        logger.debug(f"EventBus: subscribed to '{topic}'")

    def unsubscribe(self, topic: str, callback: Callable):
        """Remove a subscription."""
        if topic == "*":
            if callback in self._wildcard_subscribers:
                self._wildcard_subscribers.remove(callback)
        elif topic in self._subscribers:
            if callback in self._subscribers[topic]:
                self._subscribers[topic].remove(callback)

    async def emit(self, event: Event):
        """
        Emit an event to all matching subscribers.

        Matches exact topic and wildcard subscribers.
        """
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Exact match subscribers
        callbacks = list(self._subscribers.get(event.topic, []))

        # Prefix match (e.g. "signal.*" matches "signal.new")
        for pattern, subs in self._subscribers.items():
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if event.topic.startswith(prefix) and pattern != event.topic:
                    callbacks.extend(subs)

        # Wildcard subscribers
        callbacks.extend(self._wildcard_subscribers)

        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event)
                else:
                    cb(event)
            except Exception as e:
                logger.error(f"EventBus subscriber error on '{event.topic}': {e}")

    def emit_sync(self, event: Event):
        """Synchronous emit — only calls sync subscribers."""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        callbacks = list(self._subscribers.get(event.topic, []))
        callbacks.extend(self._wildcard_subscribers)

        for cb in callbacks:
            if not asyncio.iscoroutinefunction(cb):
                try:
                    cb(event)
                except Exception as e:
                    logger.error(f"EventBus sync subscriber error: {e}")

    @property
    def history(self) -> list[Event]:
        return list(self._history)

    @property
    def topics(self) -> list[str]:
        return sorted(self._subscribers.keys())


class SignalExecutorSubscriber:
    def __init__(self, executor, cooldown_seconds: int = 600, halt_seconds: int = 300):
        self.executor = executor
        self.cooldown_seconds = cooldown_seconds
        self.halt_seconds = halt_seconds
        self._last_triggered = 0.0

    async def handle(self, event: Event):
        now = time.time()
        if now - self._last_triggered < self.cooldown_seconds:
            return
        self._last_triggered = now
        if self.executor:
            self.executor.set_emergency_halt(self.halt_seconds)


class AlertSuppressionSubscriber:
    def __init__(self, alerts, cooldown_seconds: int = 600, suppress_seconds: int = 300):
        self.alerts = alerts
        self.cooldown_seconds = cooldown_seconds
        self.suppress_seconds = suppress_seconds
        self._last_triggered = 0.0

    async def handle(self, event: Event):
        now = time.time()
        if now - self._last_triggered < self.cooldown_seconds:
            return
        self._last_triggered = now
        if self.alerts:
            self.alerts.suppress(self.suppress_seconds)


class TelegramEmergencySubscriber:
    def __init__(self, send_fn, chat_ids: list[int], cooldown_seconds: int = 600):
        self.send_fn = send_fn
        self.chat_ids = chat_ids
        self.cooldown_seconds = cooldown_seconds
        self._last_triggered = 0.0

    async def handle(self, event: Event):
        now = time.time()
        if now - self._last_triggered < self.cooldown_seconds:
            return
        self._last_triggered = now
        if not self.send_fn or not self.chat_ids:
            return
        await self.send_fn(self.chat_ids, "⚠️ EMERGENCY: Market regime shift detected — trading paused")
