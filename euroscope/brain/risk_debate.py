import json
import logging
from typing import Dict, Any

from .llm_router import LLMRouter
from .schemas import RiskProfile, InvestmentJudgment
from ..skills.base import SkillContext

logger = logging.getLogger("euroscope.brain.risk_debate")


class RiskDebate:
    """
    Risk Debate Panel.
    
    Orchestrates a debate between three risk personalities:
    1. Aggressive Analyst (wants larger size, tighter stops)
    2. Conservative Analyst (wants smaller size, wider stops)
    3. Neutral Analyst (mediates)
    
    The Portfolio Judge synthesizes these into a final RiskProfile.
    """

    def __init__(self, llm_router: LLMRouter):
        self.llm = llm_router

    async def run_risk_debate(self, context: SkillContext, investment_judgment: Dict[str, Any]) -> Dict[str, Any]:
        """Runs the risk debate and returns the Portfolio Judge's final risk profile."""
        direction = investment_judgment.get("final_direction", "HOLD")
        
        if direction not in ["BUY", "SELL"]:
            logger.info(f"Skipping risk debate because direction is {direction}")
            return self._fallback_risk("No trade direction")

        logger.info(f"Starting risk debate for {direction} trade")
        
        context_str = self._format_context(context, investment_judgment)

        # 1. Aggressive
        aggressive = await self._run_analyst(
            context_str, 
            "Aggressive Analyst", 
            "You prefer maximum allowed position sizing, tight stop losses, and aggressive profit targets. You accept higher risk for higher reward."
        )

        # 2. Conservative
        conservative = await self._run_analyst(
            context_str, 
            "Conservative Analyst", 
            "You prefer minimum position sizing, wider stop losses to avoid being stopped out by noise, and conservative profit targets. Capital preservation is your priority."
        )

        # 3. Neutral
        neutral = await self._run_analyst(
            context_str, 
            "Neutral Analyst", 
            "You balance risk and reward. You prefer moderate position sizing and balanced stop/target levels based strictly on technical structure."
        )

        # 4. Portfolio Judge
        profile_dict = await self._run_judge(context_str, aggressive, conservative, neutral)
        
        if not profile_dict or "error" in profile_dict:
            logger.error("Portfolio Judge failed to produce a valid risk profile.")
            return self._fallback_risk("Portfolio Judge failed.")

        return {
            "aggressive_proposal": aggressive,
            "conservative_proposal": conservative,
            "neutral_proposal": neutral,
            "final_profile": profile_dict
        }

    async def _run_analyst(self, context_str: str, role_name: str, persona: str) -> Dict[str, Any]:
        system_prompt = (
            f"You are the {role_name} on a Forex trading desk. {persona}\n\n"
            "Format your response EXACTLY as a JSON object with the following schema:\n"
            "{\n"
            '  "proposed_lots": 0.1 to 5.0,\n'
            '  "proposed_stop_loss_pips": 10.0 to 100.0,\n'
            '  "proposed_take_profit_pips": 10.0 to 300.0,\n'
            '  "reasoning": "Why you chose these parameters"\n'
            "}"
        )
        
        user_prompt = f"Trade Context:\n{context_str}\n\nPropose your risk parameters."
        
        res = await self.llm.chat_json([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])
        
        if "error" in res:
            logger.warning(f"{role_name} failed: {res.get('error')}")
            return {"proposed_lots": 0.1, "proposed_stop_loss_pips": 50.0, "proposed_take_profit_pips": 50.0, "reasoning": "Fallback"}
        return res

    async def _run_judge(self, context_str: str, aggressive: Dict, conservative: Dict, neutral: Dict) -> Dict[str, Any]:
        system_prompt = (
            "You are the Portfolio Manager. You must review the proposals from the three risk analysts "
            "and decide the final execution parameters.\n\n"
            "Format your response EXACTLY as a JSON object with the following schema:\n"
            "{\n"
            '  "position_size_lots": float,\n'
            '  "stop_loss_pips": float,\n'
            '  "take_profit_pips": float,\n'
            '  "risk_reward_ratio": float,\n'
            '  "risk_rating": "low", "medium", or "high",\n'
            '  "reasoning": "Detailed explanation"\n'
            "}"
        )
        
        user_prompt = f"Trade Context:\n{context_str}\n\n"
        user_prompt += f"Aggressive Proposal:\n{json.dumps(aggressive, indent=2)}\n\n"
        user_prompt += f"Conservative Proposal:\n{json.dumps(conservative, indent=2)}\n\n"
        user_prompt += f"Neutral Proposal:\n{json.dumps(neutral, indent=2)}\n\n"
        user_prompt += "Make your final decision on the risk parameters."
        
        return await self.llm.chat_json([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

    def _fallback_risk(self, reason: str) -> Dict[str, Any]:
        return {
            "final_profile": {
                "position_size_lots": 0.0,
                "stop_loss_pips": 0.0,
                "take_profit_pips": 0.0,
                "risk_reward_ratio": 0.0,
                "risk_rating": "low",
                "reasoning": f"Risk debate skipped or failed: {reason}"
            }
        }

    def _format_context(self, context: SkillContext, investment_judgment: Dict) -> str:
        lines = [
            "--- Investment Decision ---",
            f"Direction: {investment_judgment.get('final_direction')}",
            f"Confidence: {investment_judgment.get('confidence')}%",
            f"Reasoning: {investment_judgment.get('reasoning')}",
            "\n--- Market State ---",
            f"Regime: {context.metadata.get('regime', 'unknown')}",
            f"Volatility: {context.metadata.get('volatility', 'unknown')}",
            f"Session: {context.metadata.get('active_session', 'unknown')}"
        ]
        
        atr = context.analysis.get("indicators", {}).get("indicators", {}).get("ATR", {}).get("pips")
        if atr:
            lines.append(f"ATR (Volatility): {atr} pips")
            
        return "\n".join(lines)
