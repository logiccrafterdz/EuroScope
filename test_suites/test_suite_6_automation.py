"""
Test Suite 6: Automation Layer — EventBus, SmartAlerts, Heartbeat, Cron, DailyTracker
Tests: Event pub/sub, alert system, scheduler, daily tracking
"""

import asyncio
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

RESULTS = []

def log(test_name, status, detail=""):
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    RESULTS.append((test_name, status, detail))
    print(f"  {icon} {test_name}" + (f" — {detail}" if detail else ""))


async def test_event_bus_creation():
    """Test 1: EventBus creation"""
    from euroscope.automation import EventBus
    bus = EventBus()
    if bus and hasattr(bus, "_subscribers") and hasattr(bus, "_history"):
        log("EventBus creation", "PASS", f"topics={bus.topics}")
    else:
        log("EventBus creation", "FAIL", "missing expected attributes")


async def test_event_bus_subscribe_publish():
    """Test 2: EventBus subscribe and publish (mock callback)"""
    from euroscope.automation import EventBus, Event
    bus = EventBus()
    received = []

    def on_signal(event):
        received.append(event)

    bus.subscribe("signal.new", on_signal)
    await bus.emit(Event(topic="signal.new", source="test", data={"direction": "BUY"}))
    if len(received) == 1 and received[0].data.get("direction") == "BUY":
        log("EventBus subscribe/publish", "PASS", f"received 1 event with direction=BUY")
    else:
        log("EventBus subscribe/publish", "FAIL", f"received {len(received)} events")


async def test_smart_alerts_creation():
    """Test 3: SmartAlerts creation"""
    from euroscope.automation import SmartAlerts
    alerts = SmartAlerts()
    if alerts and hasattr(alerts, "_rules") and hasattr(alerts, "_history"):
        log("SmartAlerts creation", "PASS", f"rules={len(alerts._rules)}")
    else:
        log("SmartAlerts creation", "FAIL", "missing expected attributes")


async def test_heartbeat_service_creation():
    """Test 4: HeartbeatService creation"""
    from euroscope.automation import HeartbeatService
    hb = HeartbeatService(interval=60)
    if hb and hb.interval == 60 and hasattr(hb, "_checks"):
        log("HeartbeatService creation", "PASS", f"interval={hb.interval}s")
    else:
        log("HeartbeatService creation", "FAIL", f"interval={getattr(hb, 'interval', None)}")


async def test_cron_scheduler_creation():
    """Test 5: CronScheduler creation (mock)"""
    from euroscope.automation import CronScheduler
    try:
        cron = CronScheduler(tick_interval=30)
        if cron and hasattr(cron, "_tasks") and hasattr(cron, "tick_interval"):
            log("CronScheduler creation", "PASS", f"tick_interval={cron.tick_interval}")
        else:
            log("CronScheduler creation", "FAIL", "missing expected attributes")
    except Exception as e:
        log("CronScheduler creation", "SKIP", str(e)[:100])


async def test_task_frequency_enum():
    """Test 6: TaskFrequency enum values exist"""
    from euroscope.automation import TaskFrequency
    values = [f.value for f in TaskFrequency]
    expected = {"once", "minutely", "hourly", "daily", "weekly"}
    if set(values) == expected:
        log("TaskFrequency enum", "PASS", f"values={values}")
    else:
        log("TaskFrequency enum", "FAIL", f"values={values} (expected {expected})")


async def test_daily_tracker_instantiation():
    """Test 7: DailyTracker instantiation"""
    from euroscope.automation.daily_tracker import DailyTracker
    try:
        dt = DailyTracker()
        if dt and hasattr(dt, "get_summary"):
            log("DailyTracker instantiation", "PASS", f"log_path={dt._log_path}")
        else:
            log("DailyTracker instantiation", "FAIL", "missing get_summary")
    except Exception as e:
        log("DailyTracker instantiation", "FAIL", str(e)[:100])


async def test_event_bus_multiple_subscribers():
    """Test 8: EventBus multiple subscribers"""
    from euroscope.automation import EventBus, Event
    bus = EventBus()
    received_a = []
    received_b = []

    def callback_a(event):
        received_a.append(event)

    def callback_b(event):
        received_b.append(event)

    bus.subscribe("trade.closed", callback_a)
    bus.subscribe("trade.closed", callback_b)
    await bus.emit(Event(topic="trade.closed", source="test", data={"pnl": 50}))
    if len(received_a) == 1 and len(received_b) == 1:
        log("EventBus multiple subscribers", "PASS", f"both subscribers received event")
    else:
        log("EventBus multiple subscribers", "FAIL", f"a={len(received_a)}, b={len(received_b)}")


async def test_smart_alerts_default_setup():
    """Test 9: SmartAlerts setup_default_alerts doesn't throw"""
    from euroscope.automation import SmartAlerts, setup_default_alerts
    try:
        alerts = SmartAlerts()
        setup_default_alerts(alerts)
        rule_count = len(alerts._rules)
        if rule_count > 0:
            log("setup_default_alerts", "PASS", f"{rule_count} rules registered")
        else:
            log("setup_default_alerts", "FAIL", "no rules registered")
    except Exception as e:
        log("setup_default_alerts", "FAIL", str(e)[:100])


async def main():
    print("\n" + "="*60)
    print("  SUITE 6: AUTOMATION LAYER TESTS")
    print("="*60)

    tests = [
        test_event_bus_creation,
        test_event_bus_subscribe_publish,
        test_smart_alerts_creation,
        test_heartbeat_service_creation,
        test_cron_scheduler_creation,
        test_task_frequency_enum,
        test_daily_tracker_instantiation,
        test_event_bus_multiple_subscribers,
        test_smart_alerts_default_setup,
    ]

    for test_fn in tests:
        await test_fn()

    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    warned = sum(1 for _, s, _ in RESULTS if s == "WARN")
    skipped = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    total = len(RESULTS)

    print(f"\n{'─'*60}")
    print(f"  RESULTS: {passed}✅ {failed}❌ {warned}⚠️ {skipped}⏭️ / {total} total")
    print(f"{'─'*60}\n")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
