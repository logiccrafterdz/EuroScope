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

    def should_suppress(self, event: MarketEvent, user_min_priority: AlertPriority = AlertPriority.MEDIUM) -> bool:
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
                
        # 3. Session awareness: Suppress non-critical during low liquidity (Asian session)
        # Note: In a full implementation, this uses a SessionManager
        now_hour = datetime.now(UTC).hour
        is_asian = 22 <= now_hour or now_hour <= 7
        if is_asian and priority < AlertPriority.HIGH:
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
        
        # This is a stub for the actual detection logic which will 
        # pull from context.analysis and context.metadata
        
        # Example Technical Breakout Detection
        # if context.analysis.get("technical", {}).get("breakout"):
        #    events.append(MarketEvent(type="technical", ...))
            
        return events
