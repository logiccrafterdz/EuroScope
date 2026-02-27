"""
Conflict Arbiter — Intelligence Layer for Decision Synthesis.
Resolves conflicts between tools using weights and context.
"""

import logging
from typing import Dict, Any, List
from ..skills.base import SkillContext

logger = logging.getLogger("euroscope.brain.conflict_arbiter")

class ConflictArbiter:
    """
    Resolves conflicts between tools using market context, historical accuracy, and session awareness.
    Returns a unified, justified decision — not a list of contradictions.
    """
    
    def resolve(self, context: SkillContext) -> Dict[str, Any]:
        """
        Analyzes all tool outputs and produces a coherent decision.
        """
        # Step 1: Extract all signals from metadata (once)
        signals = self._collect_signals(context)
        
        # Step 2: Weight signals by reliability (session-aware)
        weighted_signals = self._apply_weights(signals, context)
        
        # Step 3: Resolve conflicts using hierarchy
        decision = self._synthesize_decision(signals, weighted_signals, context)
        
        return decision
    
    def _collect_signals(self, context: SkillContext) -> Dict[str, str]:
        """Collects all signals from context metadata."""
        signals = {}
        # Map tool names to their signal metadata keys
        tool_mapping = {
            "liquidity_awareness": "liquidity_signal",
            "technical_analysis": "technical_bias",
            "pattern_detection": "pattern_signal",
            "fundamental_analysis": "fundamental_bias"
        }
        
        for tool, key in tool_mapping.items():
            val = context.metadata.get(key)
            if val:
                signals[tool] = val.upper()
        
        # Also check context.signals directly
        if context.signals.get("direction"):
            signals["trading_strategy"] = context.signals["direction"].upper()
            
        return signals

    def _apply_weights(self, signals: Dict[str, str], context: SkillContext) -> Dict[str, float]:
        """
        Weight signals based on:
        1. Market session (Asian vs Overlap)
        2. Historical accuracy of each tool
        3. Market regime (Trending vs Ranging)
        """
        session = context.metadata.get("session_regime", "unknown").lower()
        regime = context.metadata.get("regime", "unknown").lower()
        
        # Base weights (normalized to sum ≈ 1.0)
        weights = {
            "liquidity_awareness": 0.30,   # Market intent > indicators
            "technical_analysis": 0.25,
            "pattern_detection": 0.15,
            "fundamental_analysis": 0.10,
            "trading_strategy": 0.20,
        }
        
        # Filter weights based on available signals
        active_weights = {k: v for k, v in weights.items() if k in signals}
        
        # Session adjustments
        if session == "asian":
            if "pattern_detection" in active_weights:
                active_weights["pattern_detection"] *= 0.6
            if "technical_analysis" in active_weights:
                active_weights["technical_analysis"] *= 0.8
        
        elif session == "overlap":
            if "technical_analysis" in active_weights:
                active_weights["technical_analysis"] *= 1.2
            if "pattern_detection" in active_weights:
                active_weights["pattern_detection"] *= 1.1
        
        # Market regime adjustments
        if regime == "ranging":
            if "pattern_detection" in active_weights:
                active_weights["pattern_detection"] *= 0.5
        
        elif regime == "trending":
            if "technical_analysis" in active_weights:
                active_weights["technical_analysis"] *= 1.3
        
        # Normalize to sum to 1.0
        total = sum(active_weights.values())
        if total == 0:
            return {}
            
        return {k: v/total for k, v in active_weights.items()}
    
    def _synthesize_decision(self, signals: Dict[str, str], weighted_signals: Dict[str, float], context: SkillContext) -> Dict[str, Any]:
        """
        Synthesize weighted signals into final decision using voting logic.
        """
        if not weighted_signals:
            return {
                "final_direction": "NEUTRAL",
                "confidence": 0.0,
                "primary_evidence": "No tools provided a signal",
                "conflicts_resolved": [],
                "reasoning": "No actionable signals found."
            }

        # Count weighted votes for each direction
        votes = {"BUY": 0.0, "SELL": 0.0, "NEUTRAL": 0.0}
        
        # Use the signals passed as parameter (not re-collected)
        for tool, weight in weighted_signals.items():
            raw_signal = signals.get(tool, "NEUTRAL")
            
            direction = "NEUTRAL"
            if "BUY" in raw_signal or "BULLISH" in raw_signal:
                direction = "BUY"
            elif "SELL" in raw_signal or "BEARISH" in raw_signal:
                direction = "SELL"
                
            votes[direction] += weight
        
        # Determine winner
        final_direction = max(votes, key=votes.get)
        confidence = votes[final_direction]

        # Minimum confidence threshold — prevent acting on weak consensus
        if confidence < 0.35:
            final_direction = "NEUTRAL"
            logger.info(f"Confidence too low ({confidence:.0%}), returning NEUTRAL")
        
        # Build reasoning
        primary_evidence = self._explain_decision(final_direction, weighted_signals, context)
        conflicts_resolved = self._list_conflicts(final_direction, weighted_signals, context)
        
        return {
            "final_direction": final_direction,
            "confidence": confidence,
            "primary_evidence": primary_evidence,
            "conflicts_resolved": conflicts_resolved,
            "reasoning": f"{primary_evidence} (Confidence: {confidence:.0%})"
        }
    
    def _explain_decision(self, direction: str, weights: Dict[str, float], context: SkillContext) -> str:
        """Generate human-readable explanation for decision"""
        session = context.metadata.get("session_regime", "unknown")
        
        if direction == "NEUTRAL":
            return "No strong consensus or trend detected"

        if weights.get("liquidity_awareness", 0) > 0.3:
            return f"Liquidity flow shows high weight in {session} session"
        
        elif weights.get("technical_analysis", 0) > 0.25:
            return f"Technical indicators show strong {direction} bias"
        
        return f"Consensus for {direction} from multiple analysis tools"

    def _list_conflicts(self, final_direction: str, weights: Dict[str, float], context: SkillContext) -> List[str]:
        """Lists what was overridden and why."""
        conflicts = []
        signals = self._collect_signals(context)
        
        for tool, direction in signals.items():
            # Simplify direction for comparison
            simple_dir = "NEUTRAL"
            if "BUY" in direction or "BULLISH" in direction: simple_dir = "BUY"
            elif "SELL" in direction or "BEARISH" in direction: simple_dir = "SELL"
            
            if simple_dir != final_direction and simple_dir != "NEUTRAL":
                conflicts.append(f"Overrode {tool} {direction} in favor of {final_direction}")
        
        return conflicts
