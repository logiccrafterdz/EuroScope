"""
Proactive Intelligence Engine — Multi-Layer Event Detection & Prioritization.
Phase 3A implementation.
"""

import logging
from enum import IntEnum
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional

logger = logging.getLogger("euroscope.brain.proactive")

class AlertPriority(IntEnum):
    CRITICAL = 4  # Immediate action required (e.g., liquidity sweep + breakout)
    HIGH = 3      # Strong opportunity/risk
    MEDIUM = 2    # Notable setup forming
    LOW = 1       # Informational only

@dataclass
class MarketEvent:
    """Represents a detected market event to be prioritized."""
    type: str  # technical, liquidity, macro, regime
    description: str
    technical_strength: float = 0.0
    liquidity_aligned: bool = False
    macro_event_minutes: int = 999
    regime_shift: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

class ProactiveEngine:
    """
    Analyzes market data across multiple layers to detect and prioritize events.
    """
    
    def __init__(self):
        self.last_alerts = {}  # type -> timestamp for suppression

    def calculate_priority(self, event: MarketEvent) -> AlertPriority:
        """
        Determines the priority of an event based on multi-factor alignment.
        """
        base_score = 0
        
        # Layer 1: Technical strength
        if event.technical_strength > 0.7:
            base_score += 1
        
        # Layer 2: Liquidity confirmation
        if event.liquidity_aligned:
            base_score += 1
        
        # Layer 3: Macro catalyst proximity
        if event.macro_event_minutes < 30:
            base_score += 1
        
        # Layer 4: Regime shift detected
        if event.regime_shift:
            base_score += 1
            
        # Prioritization mapping
        if base_score >= 3:
            return AlertPriority.CRITICAL
        elif base_score == 2:
            return AlertPriority.HIGH
        elif base_score == 1:
            return AlertPriority.MEDIUM
        else:
            return AlertPriority.LOW

    def should_suppress(self, event: MarketEvent, user_min_priority: AlertPriority = AlertPriority.LOW) -> bool:
        """
        Context-aware alert suppression.
        """
        priority = self.calculate_priority(event)
        
        # 1. Respect user minimum priority
        if priority < user_min_priority:
            return True
            
        # 2. De-duplication: Suppress similar events within 60 minutes
        last_time = self.last_alerts.get(event.type)
        if last_time:
            delta = (datetime.now(UTC) - last_time).total_seconds() / 60
            if delta < 60 and priority < AlertPriority.CRITICAL:
                return True
                
        # 3. Session awareness: Suppress LOW priority during low liquidity (Asian session)
        now_hour = datetime.now(UTC).hour
        is_asian = 22 <= now_hour or now_hour <= 7
        if is_asian and priority <= AlertPriority.LOW:
            return True
            
        return False

    def mark_alerted(self, event: MarketEvent):
        """Record alert time for suppression."""
        self.last_alerts[event.type] = datetime.now(UTC)

    def analyze_context(self, context: Any) -> List[MarketEvent]:
        """
        Scans SkillContext for events across all layers.
        """
        events = []
        analysis = getattr(context, "analysis", {})
        metadata = getattr(context, "metadata", {})
        
        # Layer 1: Technical Breakouts
        technical = analysis.get("technical", {})
        if technical.get("breakout"):
            events.append(MarketEvent(
                type="technical",
                description=f"Technical breakout detected: {technical.get('breakout_type', 'Price')}",
                technical_strength=technical.get("strength", 0.5),
                metadata=technical
            ))

        # Layer 2: Liquidity Events
        liquidity = analysis.get("liquidity", {})
        if liquidity.get("sweep") or liquidity.get("order_block"):
            events.append(MarketEvent(
                type="liquidity",
                description=f"Liquidity event: {liquidity.get('event_name', 'Sweep')}",
                liquidity_aligned=True,
                metadata=liquidity
            ))

        # Layer 3: Macro Catalysts
        calendar = analysis.get("calendar", [])
        for item in calendar:
            minutes = item.get("minutes_to_event", 999)
            if minutes < 60:
                events.append(MarketEvent(
                    type="macro",
                    description=f"Upcoming Macro Catalyst: {item.get('event_name')}",
                    macro_event_minutes=int(minutes),
                    metadata=item
                ))

        # Layer 4: Regime Shifts
        regime = analysis.get("regime", {})
        if regime.get("shift_detected"):
            events.append(MarketEvent(
                type="regime",
                description=f"Market Regime Shift: {regime.get('previous_regime')} -> {regime.get('current_regime')}",
                regime_shift=True,
                metadata=regime
            ))
            
        return events
