import json
import logging
import uuid
from datetime import datetime, UTC
from typing import Dict, Any, List

logger = logging.getLogger("euroscope.brain.decision_log")


class DecisionLog:
    """
    Persistent log of trading decisions and reflections.
    
    Creates a feedback loop: 
    Decision -> Market Outcome -> LLM Reflection -> Next Decision Context
    """

    def __init__(self, storage=None, reflector=None):
        self.storage = storage
        self.reflector = reflector
        self._log_key = "decision_log"

    async def store_decision(self, context: Any, decision: Dict[str, Any], debate_transcript: Dict[str, Any] = None) -> str:
        """
        Stores a new decision as 'pending' outcome.
        Returns the unique decision ID.
        """
        decision_id = str(uuid.uuid4())
        
        entry = {
            "id": decision_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "pending",
            "direction": decision.get("final_direction", "UNKNOWN"),
            "confidence": decision.get("confidence", 0.0),
            "reasoning": decision.get("reasoning", ""),
            "market_regime": context.metadata.get("regime", "unknown") if hasattr(context, "metadata") else "unknown",
            "debate_summary": self._summarize_debate(debate_transcript) if debate_transcript else ""
        }
        
        if self.storage:
            logs = await self.storage.load_json(self._log_key) or []
            logs.append(entry)
            # Keep only the last 100 entries to prevent bloat
            if len(logs) > 100:
                logs = logs[-100:]
            await self.storage.save_json(self._log_key, logs)
            
        logger.info(f"Stored pending decision {decision_id} ({entry['direction']})")
        return decision_id

    async def resolve_with_outcome(self, decision_id: str, pnl_pips: float, is_win: bool) -> str:
        """
        Updates a pending decision with its actual outcome and generates a reflection.
        """
        if not self.storage or not self.reflector:
            return ""
            
        logs = await self.storage.load_json(self._log_key) or []
        target_entry = None
        
        for entry in logs:
            if entry.get("id") == decision_id:
                target_entry = entry
                break
                
        if not target_entry:
            logger.warning(f"Decision ID {decision_id} not found in log.")
            return ""
            
        if target_entry.get("status") == "resolved":
            logger.info(f"Decision {decision_id} is already resolved.")
            return target_entry.get("reflection", "")
            
        # Generate Reflection
        decision_text = f"Direction: {target_entry['direction']}\nReasoning: {target_entry['reasoning']}\nDebate: {target_entry['debate_summary']}"
        reflection = await self.reflector.reflect(decision_text, pnl_pips, is_win)
        
        # Update entry
        target_entry["status"] = "resolved"
        target_entry["pnl_pips"] = pnl_pips
        target_entry["is_win"] = is_win
        target_entry["reflection"] = reflection
        target_entry["resolved_at"] = datetime.now(UTC).isoformat()
        
        await self.storage.save_json(self._log_key, logs)
        logger.info(f"Resolved decision {decision_id} with reflection.")
        
        return reflection

    async def get_past_context(self, n_recent: int = 5) -> str:
        """
        Retrieves the most recent reflections to inject into the next debate.
        """
        if not self.storage:
            return ""
            
        logs = await self.storage.load_json(self._log_key) or []
        resolved_logs = [log for log in logs if log.get("status") == "resolved"]
        
        if not resolved_logs:
            return ""
            
        recent = resolved_logs[-n_recent:]
        
        lines = ["--- Lessons from Recent Trades ---"]
        for log in recent:
            win_str = "WIN" if log.get("is_win") else "LOSS"
            pnl = log.get("pnl_pips", 0.0)
            lines.append(f"Trade ({log['direction']}) -> {win_str} ({pnl:.1f} pips):")
            lines.append(f"Reflection: {log.get('reflection', '')}")
            lines.append("")
            
        return "\n".join(lines)

    def _summarize_debate(self, debate_transcript: Dict[str, Any]) -> str:
        """Creates a compact summary of the debate for the log."""
        try:
            bull = debate_transcript.get("bull_case", {}).get("key_arguments", [])
            bear = debate_transcript.get("bear_case", {}).get("counter_arguments", [])
            return f"Bull argued: {', '.join(bull[:2])}. Bear argued: {', '.join(bear[:2])}."
        except Exception:
            return "Debate summary unavailable."
