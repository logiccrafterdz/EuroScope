"""
Conviction System — The Agent's Thesis Tracker

Professional traders build and maintain market theses (convictions) that
evolve with evidence. This module gives the agent that discipline —
no flip-flopping between BUY and SELL every 15 minutes.

A Conviction represents a directional thesis backed by evidence,
with automatic invalidation and confidence decay.

Part of the EuroScope Agent Transformation (Phase 2).
"""

import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional, Any

logger = logging.getLogger("euroscope.brain.conviction")


# ── Evidence ──────────────────────────────────────────────────

@dataclass
class Evidence:
    """A single piece of evidence supporting or challenging a conviction."""
    text: str                     # Human-readable description
    source: str                   # "technical", "fundamental", "sentiment", "liquidity", "pattern"
    weight: float = 1.0           # Importance multiplier (0.5 = minor, 2.0 = major)
    direction: str = "for"        # "for" or "against"
    timestamp: float = field(default_factory=time.time)
    decayed: bool = False         # True if age > 4 hours and weight has been halved

    def age_minutes(self) -> float:
        return (time.time() - self.timestamp) / 60


# ── Conviction ────────────────────────────────────────────────

@dataclass
class Conviction:
    """
    A directional thesis on EUR/USD.

    Represents the agent's current belief about market direction,
    backed by accumulated evidence. Evolves over time.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    thesis: str = ""                    # "EUR weakness driven by ECB dovish pivot"
    direction: str = "neutral"          # "bullish", "bearish", "neutral"
    confidence: float = 0.5             # 0.0 - 1.0
    evidence_for: list = field(default_factory=list)
    evidence_against: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    invalidation_level: float = 0.0     # Price level that kills the thesis
    invalidation_reason: str = ""       # "If price breaks above 1.0950"
    target_level: float = 0.0           # Price target for the thesis
    status: str = "forming"             # "forming", "active", "invalidated", "realized", "expired"
    timeframe: str = "H1"              # Primary timeframe for this conviction
    regime_at_creation: str = ""        # Market regime when conviction was formed
    peak_confidence: float = 0.0        # Highest confidence ever reached

    def age_hours(self) -> float:
        return (time.time() - self.created_at) / 3600

    def is_active(self) -> bool:
        return self.status in ("forming", "active")

    def total_evidence_count(self) -> int:
        return len(self.evidence_for) + len(self.evidence_against)


# ── Conviction Tracker ────────────────────────────────────────

class ConvictionTracker:
    """
    Manages the agent's active convictions.

    Rules (like a professional trader):
    - Maximum 3 active convictions at any time
    - New conviction needs minimum evidence before becoming 'active'
    - Confidence decays over time if no new evidence
    - Auto-invalidated if price crosses invalidation level
    - Realized when price reaches target
    """

    # Thresholds
    MAX_ACTIVE_CONVICTIONS = 3
    MIN_EVIDENCE_TO_ACTIVATE = 3
    CONFIDENCE_DECAY_RATE = 0.02     # Per hour
    MIN_CONFIDENCE_TO_ACT = 0.55     # Below this, conviction is too weak to trade
    ACTIVATION_CONFIDENCE = 0.60     # Minimum confidence to move from forming → active
    MAX_AGE_HOURS = 48               # Convictions expire after 48h without reinforcement

    def __init__(self):
        self._convictions: list[Conviction] = []
        self._history: list[Conviction] = []  # Closed convictions for learning
        self._last_decay_time: float = time.time()

    # ── Core Operations ───────────────────────────────────────

    def create_conviction(
        self,
        thesis: str,
        direction: str,
        initial_evidence: list[Evidence],
        invalidation_level: float = 0.0,
        invalidation_reason: str = "",
        target_level: float = 0.0,
        timeframe: str = "H1",
        regime: str = "",
    ) -> Optional[Conviction]:
        """
        Form a new conviction from initial analysis.

        Returns None if max convictions reached or conflicting conviction exists.
        """
        # Check capacity
        active = [c for c in self._convictions if c.is_active()]
        if len(active) >= self.MAX_ACTIVE_CONVICTIONS:
            logger.warning(
                f"Cannot create conviction: max {self.MAX_ACTIVE_CONVICTIONS} reached. "
                f"Active: {[c.thesis[:30] for c in active]}"
            )
            return None

        # Check for conflicting conviction in same direction
        for existing in active:
            if existing.direction == direction and existing.thesis != thesis:
                # Similar direction — strengthen existing instead of duplicating
                logger.info(f"Strengthening existing {direction} conviction instead of creating new")
                for ev in initial_evidence:
                    self.add_evidence(existing.id, ev)
                return existing

        # Check for opposing conviction
        opposing = self._get_opposing(direction)
        if opposing and opposing.confidence > 0.7:
            logger.info(
                f"Strong opposing conviction exists ({opposing.direction} @ {opposing.confidence:.0%}). "
                f"New {direction} conviction will start with reduced confidence."
            )

        # Create the conviction
        initial_confidence = self._calculate_initial_confidence(initial_evidence)

        conviction = Conviction(
            thesis=thesis,
            direction=direction,
            confidence=initial_confidence,
            evidence_for=[e for e in initial_evidence if e.direction == "for"],
            evidence_against=[e for e in initial_evidence if e.direction == "against"],
            invalidation_level=invalidation_level,
            invalidation_reason=invalidation_reason,
            target_level=target_level,
            timeframe=timeframe,
            regime_at_creation=regime,
            peak_confidence=initial_confidence,
            status="forming" if initial_confidence < self.ACTIVATION_CONFIDENCE else "active",
        )

        self._convictions.append(conviction)
        logger.info(
            f"🧠 New conviction [{conviction.id}]: {direction.upper()} — "
            f"'{thesis}' (confidence: {initial_confidence:.0%}, status: {conviction.status})"
        )
        return conviction

    def add_evidence(self, conviction_id: str, evidence: Evidence) -> bool:
        """
        Add new evidence to an existing conviction.

        Adjusts confidence up (for) or down (against).
        """
        conv = self._get_by_id(conviction_id)
        if not conv or not conv.is_active():
            return False

        if evidence.direction == "for":
            conv.evidence_for.append(evidence)
            # Boost confidence (diminishing returns)
            boost = evidence.weight * 0.05 * (1 - conv.confidence)
            conv.confidence = min(0.95, conv.confidence + boost)
        else:
            conv.evidence_against.append(evidence)
            # Reduce confidence
            penalty = evidence.weight * 0.08
            conv.confidence = max(0.05, conv.confidence - penalty)

        conv.updated_at = time.time()
        conv.peak_confidence = max(conv.peak_confidence, conv.confidence)

        # Check if forming conviction should become active
        if conv.status == "forming":
            total_for = len(conv.evidence_for)
            if total_for >= self.MIN_EVIDENCE_TO_ACTIVATE and conv.confidence >= self.ACTIVATION_CONFIDENCE:
                conv.status = "active"
                logger.info(
                    f"🟢 Conviction [{conv.id}] activated: {conv.direction.upper()} "
                    f"with {total_for} evidence points ({conv.confidence:.0%})"
                )

        logger.debug(
            f"Evidence added to [{conv.id}]: {evidence.direction} "
            f"'{evidence.text[:50]}' → confidence: {conv.confidence:.0%}"
        )
        return True

    def invalidate(self, conviction_id: str, reason: str = "manual") -> bool:
        """Manually invalidate a conviction."""
        conv = self._get_by_id(conviction_id)
        if not conv or not conv.is_active():
            return False

        conv.status = "invalidated"
        conv.updated_at = time.time()
        self._archive(conv)

        logger.info(f"❌ Conviction [{conv.id}] invalidated: {reason}")
        return True

    def realize(self, conviction_id: str, exit_price: float = 0) -> bool:
        """Mark a conviction as realized (target hit or thesis played out)."""
        conv = self._get_by_id(conviction_id)
        if not conv or not conv.is_active():
            return False

        conv.status = "realized"
        conv.updated_at = time.time()
        self._archive(conv)

        logger.info(
            f"✅ Conviction [{conv.id}] realized: {conv.direction.upper()} "
            f"thesis '{conv.thesis[:40]}' played out"
        )
        return True

    # ── Automatic Updates ─────────────────────────────────────

    def tick(self, current_price: float) -> list[dict]:
        """
        Run periodic checks on all convictions.

        Call this every agent cycle. Returns list of events that occurred.

        Events: invalidation, expiration, activation, confidence_warning
        """
        events = []

        # 1. Apply time-based confidence decay
        self._apply_decay()

        for conv in list(self._convictions):
            if not conv.is_active():
                continue

            # 2. Price-based invalidation
            if conv.invalidation_level and current_price:
                invalidated = False
                if conv.direction == "bullish" and current_price < conv.invalidation_level:
                    invalidated = True
                elif conv.direction == "bearish" and current_price > conv.invalidation_level:
                    invalidated = True

                if invalidated:
                    conv.status = "invalidated"
                    conv.updated_at = time.time()
                    self._archive(conv)
                    events.append({
                        "type": "invalidated",
                        "conviction_id": conv.id,
                        "thesis": conv.thesis,
                        "direction": conv.direction,
                        "reason": f"Price {current_price:.5f} crossed invalidation {conv.invalidation_level:.5f}",
                    })
                    logger.warning(
                        f"⚡ Conviction [{conv.id}] AUTO-INVALIDATED: "
                        f"price {current_price:.5f} broke {conv.invalidation_level:.5f}"
                    )
                    continue

            # 3. Target realization
            if conv.target_level and current_price:
                realized = False
                if conv.direction == "bullish" and current_price >= conv.target_level:
                    realized = True
                elif conv.direction == "bearish" and current_price <= conv.target_level:
                    realized = True

                if realized:
                    conv.status = "realized"
                    conv.updated_at = time.time()
                    self._archive(conv)
                    events.append({
                        "type": "realized",
                        "conviction_id": conv.id,
                        "thesis": conv.thesis,
                        "direction": conv.direction,
                        "target": conv.target_level,
                    })
                    logger.info(f"🎯 Conviction [{conv.id}] TARGET HIT at {current_price:.5f}")
                    continue

            # 4. Age-based expiration
            if conv.age_hours() > self.MAX_AGE_HOURS:
                conv.status = "expired"
                conv.updated_at = time.time()
                self._archive(conv)
                events.append({
                    "type": "expired",
                    "conviction_id": conv.id,
                    "thesis": conv.thesis,
                    "age_hours": conv.age_hours(),
                })
                logger.info(f"⏰ Conviction [{conv.id}] expired after {conv.age_hours():.1f}h")
                continue

            # 5. Low confidence warning
            if conv.status == "active" and conv.confidence < self.MIN_CONFIDENCE_TO_ACT:
                events.append({
                    "type": "confidence_warning",
                    "conviction_id": conv.id,
                    "thesis": conv.thesis,
                    "confidence": conv.confidence,
                })

        # Clean up non-active from main list
        self._convictions = [c for c in self._convictions if c.is_active()]

        return events

    def _apply_decay(self) -> None:
        """Apply time-based confidence decay to all convictions and expire old evidence."""
        now = time.time()
        hours_since_decay = (now - self._last_decay_time) / 3600

        if hours_since_decay < 0.25:  # Only decay every 15 minutes
            return

        for conv in self._convictions:
            if not conv.is_active():
                continue

            # 1. Decay stale evidence weight (TTL = 4 hours)
            for ev in conv.evidence_for + conv.evidence_against:
                if getattr(ev, "decayed", False):
                    continue
                    
                if ev.age_minutes() > 240:
                    ev.decayed = True
                    ev.weight *= 0.5  # Halve weight of stale evidence
                    
                    # Revert a portion of the evidence's initial impact based on new weight
                    if ev.direction == "for":
                        penalty = ev.weight * 0.05
                        conv.confidence = max(0.05, conv.confidence - penalty)
                    else:
                        boost = ev.weight * 0.05
                        conv.confidence = min(0.95, conv.confidence + boost)
                        
                    logger.debug(f"Evidence weight decayed (4h) in [{conv.id}]: '{ev.text[:30]}...' ({ev.direction})")

            # 1b. Prune evidence older than 12 hours entirely
            before_for = len(conv.evidence_for)
            before_against = len(conv.evidence_against)
            conv.evidence_for = [e for e in conv.evidence_for if e.age_minutes() <= 720]
            conv.evidence_against = [e for e in conv.evidence_against if e.age_minutes() <= 720]
            pruned = (before_for - len(conv.evidence_for)) + (before_against - len(conv.evidence_against))
            if pruned:
                logger.info(f"Pruned {pruned} stale evidence (>12h) from conviction [{conv.id}]")

            # 2. General conviction decay rate scales with age (older convictions decay faster)
            age_factor = min(2.0, 1.0 + conv.age_hours() / 24)
            decay = self.CONFIDENCE_DECAY_RATE * hours_since_decay * age_factor
            conv.confidence = max(0.05, conv.confidence - decay)

        self._last_decay_time = now

    # ── Query Methods ─────────────────────────────────────────

    def get_active_convictions(self) -> list[Conviction]:
        """Get all currently active convictions."""
        return [c for c in self._convictions if c.is_active()]

    def get_strongest(self) -> Optional[Conviction]:
        """Get the conviction with highest confidence."""
        active = self.get_active_convictions()
        if not active:
            return None
        return max(active, key=lambda c: c.confidence)

    def get_dominant_direction(self) -> tuple[str, float]:
        """
        Get the net directional bias from all convictions.

        Returns (direction, net_confidence).
        """
        active = self.get_active_convictions()
        if not active:
            return "neutral", 0.0

        bullish_score = sum(c.confidence for c in active if c.direction == "bullish")
        bearish_score = sum(c.confidence for c in active if c.direction == "bearish")

        if bullish_score > bearish_score:
            return "bullish", bullish_score - bearish_score
        elif bearish_score > bullish_score:
            return "bearish", bearish_score - bullish_score
        else:
            return "neutral", 0.0

    def should_act(self, direction: str) -> bool:
        """
        Can the agent take action in this direction?

        True only if there's an active conviction with sufficient confidence
        in the specified direction.
        """
        for conv in self.get_active_convictions():
            if conv.status == "active" and conv.direction == direction:
                if conv.confidence >= self.MIN_CONFIDENCE_TO_ACT:
                    return True
        return False

    def has_opposing_conviction(self, direction: str) -> bool:
        """Check if there's an active conviction opposing the given direction."""
        opposite = "bearish" if direction == "bullish" else "bullish"
        return any(
            c.direction == opposite and c.confidence > 0.5
            for c in self.get_active_convictions()
        )

    # ── Summary for LLM ──────────────────────────────────────

    def get_summary(self) -> str:
        """LLM-ready summary of current convictions."""
        active = self.get_active_convictions()
        if not active:
            return "No active convictions. The agent has no directional thesis."

        lines = [f"=== ACTIVE CONVICTIONS ({len(active)}) ==="]
        for conv in sorted(active, key=lambda c: -c.confidence):
            icon = "🟢" if conv.direction == "bullish" else "🔴" if conv.direction == "bearish" else "⚪"
            lines.append(
                f"\n{icon} [{conv.id}] {conv.direction.upper()} — {conv.thesis}"
            )
            lines.append(f"  Status: {conv.status} | Confidence: {conv.confidence:.0%} (peak: {conv.peak_confidence:.0%})")
            lines.append(f"  Age: {conv.age_hours():.1f}h | Evidence: {len(conv.evidence_for)} active for, {len(conv.evidence_against)} active against")
            if conv.invalidation_level:
                lines.append(f"  Invalidation: {conv.invalidation_reason} @ {conv.invalidation_level:.5f}")
            if conv.target_level:
                lines.append(f"  Target: {conv.target_level:.5f}")

        dom_dir, dom_conf = self.get_dominant_direction()
        lines.append(f"\n📊 Net Bias: {dom_dir.upper()} (net confidence: {dom_conf:.0%})")

        return "\n".join(lines)

    # ── Persistence ───────────────────────────────────────────

    def serialize(self) -> dict:
        """Serialize for storage."""
        return {
            "convictions": [asdict(c) for c in self._convictions],
            "history": [asdict(c) for c in self._history[-20:]],  # Keep last 20
            "last_decay_time": self._last_decay_time,
        }

    def deserialize(self, data: dict) -> None:
        """Restore from storage."""
        if not data:
            return

        self._convictions = []
        for c_data in data.get("convictions", []):
            conv = Conviction()
            for key, val in c_data.items():
                if key == "evidence_for":
                    conv.evidence_for = [Evidence(**e) if isinstance(e, dict) else e for e in val]
                elif key == "evidence_against":
                    conv.evidence_against = [Evidence(**e) if isinstance(e, dict) else e for e in val]
                elif hasattr(conv, key):
                    setattr(conv, key, val)
            self._convictions.append(conv)

        self._history = []
        for c_data in data.get("history", []):
            conv = Conviction()
            for key, val in c_data.items():
                if hasattr(conv, key) and key not in ("evidence_for", "evidence_against"):
                    setattr(conv, key, val)
            self._history.append(conv)

        self._last_decay_time = data.get("last_decay_time", time.time())
        logger.info(f"ConvictionTracker restored: {len(self._convictions)} active, {len(self._history)} historical")

    # ── Learning from History ─────────────────────────────────

    def get_accuracy_stats(self) -> dict:
        """Calculate historical accuracy of convictions."""
        if not self._history:
            return {"total": 0, "realized": 0, "invalidated": 0, "expired": 0, "accuracy": 0.0}

        total = len(self._history)
        realized = sum(1 for c in self._history if c.status == "realized")
        invalidated = sum(1 for c in self._history if c.status == "invalidated")
        expired = sum(1 for c in self._history if c.status == "expired")

        accuracy = realized / total * 100 if total > 0 else 0.0

        return {
            "total": total,
            "realized": realized,
            "invalidated": invalidated,
            "expired": expired,
            "accuracy": round(accuracy, 1),
            "avg_confidence_at_creation": round(
                sum(c.peak_confidence for c in self._history) / total, 2
            ) if total > 0 else 0,
        }

    # ── Internal Helpers ──────────────────────────────────────

    def _get_by_id(self, conviction_id: str) -> Optional[Conviction]:
        for conv in self._convictions:
            if conv.id == conviction_id:
                return conv
        return None

    def _get_opposing(self, direction: str) -> Optional[Conviction]:
        opposite = "bearish" if direction == "bullish" else "bullish"
        for conv in self.get_active_convictions():
            if conv.direction == opposite:
                return conv
        return None

    def _archive(self, conv: Conviction) -> None:
        """Move a closed conviction to history."""
        self._history.append(conv)
        # Keep max 50 historical convictions
        if len(self._history) > 50:
            self._history = self._history[-50:]

    @staticmethod
    def _calculate_initial_confidence(evidence: list[Evidence]) -> float:
        """Calculate starting confidence from initial evidence."""
        if not evidence:
            return 0.3

        for_weight = sum(e.weight for e in evidence if e.direction == "for")
        against_weight = sum(e.weight for e in evidence if e.direction == "against")
        total_weight = for_weight + against_weight

        if total_weight == 0:
            return 0.3

        # Base confidence from evidence ratio
        ratio = for_weight / total_weight
        confidence = 0.3 + ratio * 0.4  # Range: 0.3 - 0.7

        # Bonus for diverse sources
        sources = set(e.source for e in evidence if e.direction == "for")
        if len(sources) >= 3:
            confidence += 0.1  # Multi-source confirmation bonus

        return min(0.80, confidence)  # Cap initial confidence

    def __repr__(self) -> str:
        active = self.get_active_convictions()
        return f"<ConvictionTracker active={len(active)} history={len(self._history)}>"
