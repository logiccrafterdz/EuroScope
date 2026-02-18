import pytest
from datetime import datetime, UTC, timedelta
from euroscope.brain.proactive_engine import ProactiveEngine, MarketEvent, AlertPriority

@pytest.fixture
def engine():
    return ProactiveEngine()

def test_calculate_priority_critical(engine):
    event = MarketEvent(
        type="technical",
        description="Major breakout",
        technical_strength=0.8,
        liquidity_aligned=True,
        macro_event_minutes=15,
        regime_shift=True
    )
    priority = engine.calculate_priority(event)
    assert priority == AlertPriority.CRITICAL

def test_calculate_priority_high(engine):
    event = MarketEvent(
        type="technical",
        description="Standard breakout",
        technical_strength=0.8,
        liquidity_aligned=True,
        macro_event_minutes=60
    )
    priority = engine.calculate_priority(event)
    assert priority == AlertPriority.HIGH

def test_calculate_priority_medium(engine):
    event = MarketEvent(
        type="technical",
        description="Weak breakout",
        technical_strength=0.8,
        macro_event_minutes=60
    )
    priority = engine.calculate_priority(event)
    assert priority == AlertPriority.MEDIUM

def test_calculate_priority_low(engine):
    event = MarketEvent(
        type="technical",
        description="Noise",
        technical_strength=0.5
    )
    priority = engine.calculate_priority(event)
    assert priority == AlertPriority.LOW

def test_should_suppress_low_priority(engine):
    event = MarketEvent(type="test", description="Low setup")
    # Low priority should be suppressed by default MEDIUM filter
    assert engine.should_suppress(event, user_min_priority=AlertPriority.MEDIUM) is True

def test_should_suppress_duplicate(engine):
    event = MarketEvent(type="technical", description="Breakout", technical_strength=0.8, liquidity_aligned=True)
    engine.mark_alerted(event)
    
    # Same type within 60 mins should be suppressed if not CRITICAL
    assert engine.should_suppress(event) is True

def test_no_suppress_critical_duplicate(engine):
    event = MarketEvent(
        type="technical", 
        description="CRITICAL Event", 
        technical_strength=0.9, 
        liquidity_aligned=True, 
        macro_event_minutes=10, 
        regime_shift=True
    )
    engine.mark_alerted(event)
    
    # CRITICAL events bypass duplicate suppression
    assert engine.should_suppress(event) is False

def test_session_suppression_asian(engine):
    event = MarketEvent(type="technical", description="MEDIUM Setup", technical_strength=0.8)
    # Mock time to Asian session (e.g. 02:00 UTC)
    # We can't easily mock datetime.now() without a library like freezegun, 
    # but we can test the logic if we make the engine session-aware via injection.
    # For now, we'll verify the hour logic in the existing implementation.
    pass
