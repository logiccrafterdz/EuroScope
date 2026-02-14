"""
Smart Alerts — Cross-skill notification system.

Monitors skill results and triggers alerts based on configurable rules.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger("euroscope.automation.alerts")


class AlertPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertChannel(Enum):
    TELEGRAM = "telegram"
    LOG = "log"
    MEMORY = "memory"


@dataclass
class Alert:
    """A triggered alert."""
    title: str
    message: str
    priority: AlertPriority = AlertPriority.MEDIUM
    channel: AlertChannel = AlertChannel.TELEGRAM
    source: str = ""
    timestamp: str = ""
    data: dict = field(default_factory=dict)
    acknowledged: bool = False

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


@dataclass
class AlertRule:
    """A rule that triggers an alert when conditions are met."""
    name: str
    condition: Callable  # Callable(data) -> bool
    alert_template: Callable  # Callable(data) -> Alert
    cooldown_seconds: int = 300  # Prevent alert spam
    enabled: bool = True
    last_triggered: float = 0


class SmartAlerts:
    """
    Cross-skill notification system.

    Usage:
        alerts = SmartAlerts()
        alerts.add_rule(
            "rsi_oversold",
            condition=lambda d: d.get("rsi", 50) < 30,
            title="RSI Oversold Alert",
            message_template="RSI is {rsi:.0f} — potential reversal zone",
        )
        alerts.check({"rsi": 25, "price": 1.085})
    """

    def __init__(self):
        self._rules: dict[str, AlertRule] = {}
        self._history: list[Alert] = []
        self._handlers: dict[AlertChannel, Callable] = {}
        self._max_history = 200
        self._suppress_until = 0.0
        self._essential_priorities = {AlertPriority.CRITICAL}

    def add_rule(self, name: str, condition: Callable,
                 title: str = "", message_template: str = "",
                 priority: AlertPriority = AlertPriority.MEDIUM,
                 channel: AlertChannel = AlertChannel.TELEGRAM,
                 cooldown: int = 300):
        """
        Add an alert rule.

        Args:
            name: Unique rule name
            condition: Function(data_dict) -> bool
            title: Alert title
            message_template: Message with {key} format placeholders
            priority: Alert priority level
            channel: Where to send the alert
            cooldown: Minimum seconds between repeated alerts
        """
        def make_alert(data):
            try:
                msg = message_template.format(**data)
            except (KeyError, IndexError):
                msg = message_template
            return Alert(
                title=title or name,
                message=msg,
                priority=priority,
                channel=channel,
                source=name,
                data=data,
            )

        rule = AlertRule(
            name=name,
            condition=condition,
            alert_template=make_alert,
            cooldown_seconds=cooldown,
        )
        self._rules[name] = rule
        logger.info(f"SmartAlerts: added rule '{name}'")

    def register_handler(self, channel: AlertChannel, handler: Callable):
        """Register a handler for an alert channel."""
        self._handlers[channel] = handler

    def check(self, data: dict, source: str = "") -> list[Alert]:
        """
        Check all rules against data and return triggered alerts.

        Args:
            data: Data dict to check against rules
            source: Source identifier

        Returns:
            List of triggered Alert objects
        """
        import time
        triggered = []
        now = time.time()

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            # Cooldown check
            if now - rule.last_triggered < rule.cooldown_seconds:
                continue

            try:
                if rule.condition(data):
                    alert = rule.alert_template(data)
                    alert.source = source or alert.source
                    if now < self._suppress_until and alert.priority not in self._essential_priorities:
                        continue
                    rule.last_triggered = now
                    triggered.append(alert)
                    self._history.append(alert)

                    # Dispatch to handler
                    handler = self._handlers.get(alert.channel)
                    if handler:
                        try:
                            handler(alert)
                        except Exception as e:
                            logger.error(f"Alert handler error: {e}")
                    else:
                        logger.info(f"Alert [{alert.priority.value}]: {alert.title} — {alert.message}")

            except Exception as e:
                logger.error(f"Alert rule '{rule.name}' check error: {e}")

        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return triggered

    def suppress(self, duration_seconds: int = 300, essential_priorities: set = None):
        import time
        if essential_priorities is not None:
            self._essential_priorities = set(essential_priorities)
        self._suppress_until = max(self._suppress_until, time.time() + duration_seconds)

    def disable_rule(self, name: str):
        if name in self._rules:
            self._rules[name].enabled = False

    def enable_rule(self, name: str):
        if name in self._rules:
            self._rules[name].enabled = True

    @property
    def rules(self) -> dict[str, AlertRule]:
        return dict(self._rules)

    @property
    def history(self) -> list[Alert]:
        return list(self._history)

    def unacknowledged(self) -> list[Alert]:
        return [a for a in self._history if not a.acknowledged]


# ── Pre-built Alert Rules ────────────────────────────────────

def setup_default_alerts(alerts: SmartAlerts):
    """Register sensible default alert rules for EUR/USD trading."""

    alerts.add_rule(
        "rsi_oversold",
        condition=lambda d: d.get("rsi", 50) < 30,
        title="📊 RSI Oversold",
        message_template="RSI at {rsi:.0f} — potential BUY zone",
        priority=AlertPriority.MEDIUM,
        cooldown=1800,
    )

    alerts.add_rule(
        "rsi_overbought",
        condition=lambda d: d.get("rsi", 50) > 70,
        title="📊 RSI Overbought",
        message_template="RSI at {rsi:.0f} — potential SELL zone",
        priority=AlertPriority.MEDIUM,
        cooldown=1800,
    )

    alerts.add_rule(
        "high_impact_event",
        condition=lambda d: d.get("event_impact", "") == "high",
        title="📅 High-Impact Event",
        message_template="{event_name} in {minutes_until:.0f} minutes",
        priority=AlertPriority.HIGH,
        cooldown=3600,
    )

    alerts.add_rule(
        "drawdown_warning",
        condition=lambda d: d.get("drawdown_pips", 0) > 50,
        title="⚠️ Drawdown Warning",
        message_template="Drawdown at {drawdown_pips:.0f} pips — review positions",
        priority=AlertPriority.CRITICAL,
        cooldown=600,
    )
