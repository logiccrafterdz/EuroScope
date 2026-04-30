# Automation & Events Architecture

EuroScope relies on a robust set of decoupled event-driven systems to manage state, trigger alarms, and schedule background tasks without blocking the main OODA loop.

## 1. EventBus Architecture

The `EventBus` (`euroscope.automation.events`) provides a publish/subscribe pattern for cross-skill communication.

### 1.1 Emitting and Subscribing
Skills can emit `Event` or `MarketEvent` objects:
```python
await bus.emit(Event("signal.new", "trading_strategy", {"direction": "BUY"}))
```

Other components subscribe to exact topics or wildcards:
```python
bus.subscribe("signal.*", on_new_signal)
bus.subscribe("*", log_all_events)
```

### 1.2 Core Event Subscriptions
Several system-critical subscribers are hardwired into the bus:
- **`SignalExecutorSubscriber`**: Listens for critical errors and sets a temporary emergency halt on trading.
- **`AlertSuppressionSubscriber`**: Can temporarily silence non-critical Telegram alerts during volatile periods.
- **`TelegramEmergencySubscriber`**: Dispatches immediate push notifications on severe market regime shifts.

## 2. SmartAlerts System

The `SmartAlerts` module (`euroscope.automation.alerts`) evaluates system data against predefined rules to notify the user via Telegram or logging.

### 2.1 Priorities and Throttling
Alerts are ranked by `AlertPriority` (CRITICAL, HIGH, MEDIUM, LOW). The system employs advanced throttling to prevent alert fatigue:
1. **Per-Rule Cooldowns:** Minimum seconds between consecutive triggers of the same rule (e.g., 30 mins for RSI oversold).
2. **Session-Aware Suppression:** During the low-volatility Asian session, MEDIUM/LOW priority alerts are silently suppressed.
3. **Global Hourly Cap:** Limits total alerts per hour; CRITICAL alerts bypass this cap.
4. **Content Deduplication:** Prevents sending identically titled alerts within a 15-minute window.

### 2.2 Default Rules
`setup_default_alerts()` initializes the standard rule set:
- **`rsi_oversold` / `rsi_overbought`**: Triggers on RSI < 30 or > 70 (MEDIUM).
- **`high_impact_event`**: Triggers before major macroeconomic news (HIGH).
- **`drawdown_warning`**: Triggers if unrealized drawdown exceeds 50 pips (CRITICAL).

## 3. HeartbeatService

The `HeartbeatService` (`euroscope.automation.heartbeat`) is a background task runner that tracks the health of various components.

### 3.1 Loop Mechanics
- **Interval Tick:** Every 30 seconds, it runs all registered health checks (e.g., API connectivity, database latency).
- **Event Emission:** It emits a `tick.30s` event to the `EventBus`, which the Agent Core uses to drive the OODA loop.
- **Status Change:** If a component's health status flips (e.g., `healthy` → `error`), it triggers registered listeners, often resulting in an administrative Telegram alert.

## 4. CronScheduler

The `CronSystem` (`euroscope.automation.cron`) manages both recurring (`TaskFrequency`) and one-time deferred tasks.

### 4.1 Key Scheduled Tasks
- **Proactive Intelligence (`ProactiveEngine`)**: Wakes up autonomously (e.g., every 30 mins) to scan the market and provide unsolicited insights to the user, provided it's outside defined "Quiet Hours".
- **Daily Tracker (`DailyTracker`)**: Aggregates the day's PnL, win rates, and executed signals, dispatching an end-of-day summary report.
- **Memory Cleanup**: Periodically purges stale entries from the Vector Memory database.
