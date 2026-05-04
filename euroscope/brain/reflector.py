import logging
from typing import Dict, Any
from .llm_router import LLMRouter

logger = logging.getLogger("euroscope.brain.reflector")


class Reflector:
    """
    Handles reflection on past trading decisions after the outcome is known.
    """

    def __init__(self, llm_router: LLMRouter):
        self.llm = llm_router

    async def reflect(self, decision_text: str, pnl_pips: float, is_win: bool) -> str:
        """
        Generates a concise 2-4 sentence reflection on the decision vs reality.
        """
        outcome_str = "PROFITABLE" if is_win else "LOSS-MAKING"
        
        system_prompt = (
            "You are a trading analyst reviewing your own past decision now that the outcome is known.\n"
            "Write exactly 2-4 sentences of plain prose (no bullets, no headers, no markdown).\n\n"
            "Cover in order:\n"
            "1. Was the directional call correct?\n"
            "2. Which part of the investment thesis (from the debate) held or failed?\n"
            "3. One concrete lesson to apply to the next similar analysis.\n\n"
            "Be specific and terse. Your output will be stored verbatim in a decision log "
            "and re-read by future analysts, so every word must earn its place."
        )
        
        user_prompt = (
            f"Trade Outcome: {outcome_str} ({pnl_pips:+.1f} pips)\n\n"
            f"Original Decision Context:\n{decision_text}\n\n"
            "Write your reflection."
        )
        
        try:
            response = await self.llm.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ])
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate reflection: {e}")
            return "Failed to generate reflection due to LLM error."
