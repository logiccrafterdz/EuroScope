"""
Conflict Arbiter — Intelligence Layer for Decision Synthesis.
Resolves conflicts between tools using weights and context.
Phase 3 Part 2: Upgraded with Multi-Agent Deliberation hook.
"""

import logging
from typing import Dict, Any, List
from ..skills.base import SkillContext

logger = logging.getLogger("euroscope.brain.conflict_arbiter")

class ConflictArbiter:
    """
    Resolves conflicts between tools using market context, historical accuracy, and session awareness.
    If conflicts are too strong, it escalates to the Deliberation Committee.
    """
    def __init__(self, llm_router=None):
        self.llm_router = llm_router
        
    async def resolve(self, context: SkillContext) -> Dict[str, Any]:
        """
        Analyzes all tool outputs and produces a coherent decision.
        """
        signals = self._collect_signals(context)
        weighted_signals = self._apply_weights(signals, context)
        decision = await self._synthesize_decision(signals, weighted_signals, context)
        return decision
    
    def _collect_signals(self, context: SkillContext) -> Dict[str, str]:
        signals = {}
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
        
        if context.signals.get("direction"):
            signals["trading_strategy"] = context.signals["direction"].upper()
            
        return signals

    def _apply_weights(self, signals: Dict[str, str], context: SkillContext) -> Dict[str, float]:
        session = context.metadata.get("session_regime", "unknown").lower()
        regime = context.metadata.get("regime", "unknown").lower()
        
        weights = {
            "liquidity_awareness": 0.30,
            "technical_analysis": 0.25,
            "pattern_detection": 0.15,
            "fundamental_analysis": 0.10,
            "trading_strategy": 0.20,
        }
        
        active_weights = {k: v for k, v in weights.items() if k in signals}
        
        if session == "asian":
            if "pattern_detection" in active_weights: active_weights["pattern_detection"] *= 0.6
            if "technical_analysis" in active_weights: active_weights["technical_analysis"] *= 0.8
        elif session == "overlap":
            if "technical_analysis" in active_weights: active_weights["technical_analysis"] *= 1.2
            if "pattern_detection" in active_weights: active_weights["pattern_detection"] *= 1.1
        
        if regime == "ranging":
            if "pattern_detection" in active_weights: active_weights["pattern_detection"] *= 0.5
        elif regime == "trending":
            if "technical_analysis" in active_weights: active_weights["technical_analysis"] *= 1.3
        
        total = sum(active_weights.values())
        if total == 0: return {}
        return {k: v/total for k, v in active_weights.items()}
    
    async def _synthesize_decision(self, signals: Dict[str, str], weighted_signals: Dict[str, float], context: SkillContext) -> Dict[str, Any]:
        if not weighted_signals:
            return {
                "final_direction": "NEUTRAL",
                "confidence": 0.0,
                "primary_evidence": "No actionable signals found.",
                "conflicts_resolved": [],
                "reasoning": "No actionable signals found."
            }

        votes = {"BUY": 0.0, "SELL": 0.0, "NEUTRAL": 0.0}
        for tool, weight in weighted_signals.items():
            raw = signals.get(tool, "NEUTRAL")
            direction = "NEUTRAL"
            if "BUY" in raw or "BULLISH" in raw: direction = "BUY"
            elif "SELL" in raw or "BEARISH" in raw: direction = "SELL"
            votes[direction] += weight
        
        final_direction = max(votes, key=votes.get)
        confidence = votes[final_direction]
        
        # Check if we have strong conflicting forces
        opposite = "SELL" if final_direction == "BUY" else "BUY"
        conflict_ratio = votes.get(opposite, 0)
        
        # Phase 3 Multi-Agent Hook:
        # If there is high conflict (>0.25 opposition) or the winning vote is very weak (<0.45)
        # we trigger the multi-agent deliberation.
        needs_deliberation = False
        if confidence > 0 and confidence < 0.45:
            needs_deliberation = True
        elif conflict_ratio > 0.25 and final_direction != "NEUTRAL":
            needs_deliberation = True
            
        if needs_deliberation:
            # We attempt to use the Deliberation Committee
            from euroscope.brain.multi_agent import DeliberationCommittee
            from euroscope.container import get_container
            container = get_container()
            llm = self.llm_router or (container.llm if container else None)
            
            if llm:
                committee = DeliberationCommittee(llm)
                committee_verdict = await committee.deliberate(context)
                if committee_verdict.get("final_direction") != "NEUTRAL":
                    logger.info("Committee override applied.")
                    committee_verdict["conflicts_resolved"] = self._list_conflicts(committee_verdict["final_direction"], weighted_signals, context)
                    return committee_verdict
            else:
                logger.warning("Could not instantiate Multi-Agent Committee: No LLM router.")

        if confidence < 0.35:
            final_direction = "NEUTRAL"
            
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
        session = context.metadata.get("session_regime", "unknown")
        if direction == "NEUTRAL": return "No strong consensus or trend detected"
        if weights.get("liquidity_awareness", 0) > 0.3: return f"Liquidity flow shows high weight in {session} session"
        elif weights.get("technical_analysis", 0) > 0.25: return f"Technical indicators show strong {direction} bias"
        return f"Consensus for {direction} from multiple tools"

    def _list_conflicts(self, final_dir: str, weights: Dict[str, float], context: SkillContext) -> List[str]:
        conflicts = []
        signals = self._collect_signals(context)
        for tool, direction in signals.items():
            simple_dir = "NEUTRAL"
            if "BUY" in direction or "BULLISH" in direction: simple_dir = "BUY"
            elif "SELL" in direction or "BEARISH" in direction: simple_dir = "SELL"
            
            if simple_dir != final_dir and simple_dir != "NEUTRAL":
                conflicts.append(f"Overrode {tool} {direction} in favor of {final_dir}")
        return conflicts
