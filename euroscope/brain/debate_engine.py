import json
import logging
from typing import Dict, Any

from .llm_router import LLMRouter
from .schemas import InvestmentJudgment
from ..skills.base import SkillContext

logger = logging.getLogger("euroscope.brain.debate_engine")


class DebateEngine:
    """
    Multi-Agent Debate Engine for Investment Decisions.
    
    Orchestrates a debate between a Bull agent (arguing for a trade)
    and a Bear agent (arguing against it), followed by a Research Manager
    who synthesizes the arguments into a final decision.
    """

    def __init__(self, llm_router: LLMRouter):
        self.llm = llm_router

    async def run_investment_debate(self, context: SkillContext, proposed_direction: str) -> Dict[str, Any]:
        """
        Runs a full Bull vs Bear debate round and returns the Research Manager's judgment.
        """
        logger.info(f"Starting investment debate for proposed direction: {proposed_direction}")
        
        # Format the context into a string for the LLMs
        context_str = self._format_context(context)
        past_reflections = context.metadata.get("past_reflections", "")

        # 1. Bull Agent
        bull_case = await self._run_bull(context_str, past_reflections, proposed_direction)
        if not bull_case:
            logger.error("Bull agent failed to produce a valid case.")
            return self._fallback_judgment(proposed_direction, "Bull agent failed.")

        # 2. Bear Agent
        bear_case = await self._run_bear(context_str, past_reflections, proposed_direction, bull_case)
        if not bear_case:
            logger.error("Bear agent failed to produce a valid case.")
            return self._fallback_judgment(proposed_direction, "Bear agent failed.")

        # 3. Research Manager
        judgment = await self._run_judge(context_str, past_reflections, proposed_direction, bull_case, bear_case)
        if not judgment:
            logger.error("Research Manager failed to produce a valid judgment.")
            return self._fallback_judgment(proposed_direction, "Research Manager failed.")

        # Return as dict for easy serialization
        return {
            "bull_case": bull_case,
            "bear_case": bear_case,
            "judgment": judgment
        }

    async def _run_bull(self, context_str: str, past_reflections: str, proposed_direction: str) -> Dict[str, Any]:
        system_prompt = (
            "You are a 'Bullish' Trading Researcher. Your job is to build the strongest possible "
            f"case FOR trading in the {proposed_direction} direction based on the provided analysis.\n\n"
            "Format your response EXACTLY as a JSON object with the following schema:\n"
            "{\n"
            '  "direction": "BUY or SELL",\n'
            '  "conviction": 0.0 to 100.0,\n'
            '  "key_arguments": ["arg1", "arg2"],\n'
            '  "supporting_indicators": ["ind1", "ind2"]\n'
            "}"
        )
        
        user_prompt = f"Market Context:\n{context_str}\n\n"
        if past_reflections:
            user_prompt += f"Past Reflections to consider:\n{past_reflections}\n\n"
        
        user_prompt += f"Build the strongest case for a {proposed_direction} trade."
        
        return await self.llm.chat_json([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

    async def _run_bear(self, context_str: str, past_reflections: str, proposed_direction: str, bull_case: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = (
            "You are a 'Bearish' Trading Researcher. Your job is to critically attack and "
            f"find flaws in the {proposed_direction} case presented by the Bull Researcher.\n\n"
            "Format your response EXACTLY as a JSON object with the following schema:\n"
            "{\n"
            '  "counter_arguments": ["flaw1", "flaw2"],\n'
            '  "risk_factors": ["risk1", "risk2"],\n'
            '  "invalidation_levels": [1.1050, 1.0980]\n'
            "}"
        )
        
        user_prompt = f"Market Context:\n{context_str}\n\n"
        if past_reflections:
            user_prompt += f"Past Reflections to consider:\n{past_reflections}\n\n"
            
        user_prompt += f"Bull Case to attack:\n{json.dumps(bull_case, indent=2)}\n\n"
        user_prompt += "Critique this case and build the strongest counter-argument."
        
        return await self.llm.chat_json([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

    async def _run_judge(self, context_str: str, past_reflections: str, proposed_direction: str, bull_case: Dict, bear_case: Dict) -> Dict[str, Any]:
        system_prompt = (
            "You are the Research Manager for a trading desk. You must weigh the "
            "Bull case against the Bear case and make a final investment decision.\n\n"
            "Format your response EXACTLY as a JSON object with the following schema:\n"
            "{\n"
            '  "final_direction": "BUY", "SELL", or "HOLD",\n'
            '  "confidence": 0.0 to 100.0,\n'
            '  "reasoning": "Detailed explanation of why you sided with bull/bear",\n'
            '  "bull_weight": 0.0 to 1.0 (how much weight given to the bull case),\n'
            '  "bear_weight": 0.0 to 1.0 (how much weight given to the bear case)\n'
            "}"
        )
        
        user_prompt = f"Market Context:\n{context_str}\n\n"
        if past_reflections:
            user_prompt += f"Past Reflections to consider:\n{past_reflections}\n\n"
            
        user_prompt += f"Bull Case:\n{json.dumps(bull_case, indent=2)}\n\n"
        user_prompt += f"Bear Case:\n{json.dumps(bear_case, indent=2)}\n\n"
        user_prompt += f"Original Proposed Direction: {proposed_direction}\n\n"
        user_prompt += "Make your final decision."
        
        return await self.llm.chat_json([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

    def _fallback_judgment(self, direction: str, error_msg: str) -> Dict[str, Any]:
        """Provides a safe fallback judgment if the LLM fails."""
        return {
            "bull_case": {"error": error_msg},
            "bear_case": {"error": error_msg},
            "judgment": {
                "final_direction": "HOLD",
                "confidence": 0.0,
                "reasoning": f"Debate engine failed: {error_msg}. Defaulting to HOLD for safety.",
                "bull_weight": 0.0,
                "bear_weight": 0.0
            }
        }

    async def run_conflict_deliberation(self, context: SkillContext) -> Dict[str, Any]:
        """
        Conflict escalation: Bull vs Bear vs Risk Manager debate.
        Used when the ConflictArbiter detects high signal conflict.
        Returns: {final_direction, confidence, primary_evidence, reasoning, committee_notes}
        """
        logger.info("Conflict escalation: convening debate committee...")

        context_str = self._format_context(context)

        # 1. Bull Advocate — argues why price goes UP
        bull_prompt = (
            "You are the BULL ADVOCATE for EUR/USD.\n"
            f"Market Context:\n{context_str}\n\n"
            "Argue the bullish case in 2-3 sentences. What data supports a long position?"
        )
        # 2. Bear Advocate — argues why price goes DOWN
        bear_prompt = (
            "You are the BEAR ADVOCATE for EUR/USD.\n"
            f"Market Context:\n{context_str}\n\n"
            "Argue the bearish case in 2-3 sentences. What data supports a short position?"
        )
        # 3. Risk Manager — points out risks and contradictions
        risk_prompt = (
            "You are the STRICT RISK MANAGER. You hate losing money.\n"
            f"Market Context:\n{context_str}\n\n"
            "Point out ONLY the risks, contradictions, and reasons NOT to trade. 2-3 sentences."
        )

        try:
            import asyncio
            bull_resp, bear_resp, risk_resp = await asyncio.wait_for(
                asyncio.gather(
                    self.llm.chat([{"role": "user", "content": bull_prompt}], temperature=0.7),
                    self.llm.chat([{"role": "user", "content": bear_prompt}], temperature=0.7),
                    self.llm.chat([{"role": "user", "content": risk_prompt}], temperature=0.1),
                    return_exceptions=True,
                ),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.error("Conflict committee timed out after 15s")
            return {"final_direction": "NEUTRAL", "confidence": 0, "reasoning": "Committee timed out."}
        except Exception as e:
            logger.error(f"Conflict committee crashed: {e}")
            return {"final_direction": "NEUTRAL", "confidence": 0, "reasoning": "Committee failed."}

        bull_resp = str(bull_resp) if not isinstance(bull_resp, Exception) else "Bull offline."
        bear_resp = str(bear_resp) if not isinstance(bear_resp, Exception) else "Bear offline."
        risk_resp = str(risk_resp) if not isinstance(risk_resp, Exception) else "Risk manager offline."

        # Judge synthesizes all three
        judge_prompt = (
            "You are the CHIEF JUDGE of an AI Trading Committee for EUR/USD.\n"
            f"BULL ADVOCATE:\n{bull_resp}\n\n"
            f"BEAR ADVOCATE:\n{bear_resp}\n\n"
            f"RISK MANAGER:\n{risk_resp}\n\n"
            "Based on who presented the strongest, data-backed argument, decide: BUY, SELL, or NEUTRAL.\n"
            'Return JSON: {"decision": "BUY|SELL|NEUTRAL", "confidence": 0.0-1.0, "reasoning": "..."}'
            "\nIf the Risk Manager's concerns are overwhelming, rule NEUTRAL."
        )

        try:
            import re, json
            verdict = await self.llm.chat([{"role": "user", "content": judge_prompt}], temperature=0.3)
            match = re.search(r'\{.*\}', verdict, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return {
                    "final_direction": data.get("decision", "NEUTRAL"),
                    "confidence": float(data.get("confidence", 0.0)),
                    "primary_evidence": "Committee Deliberation Consensus",
                    "reasoning": data.get("reasoning", ""),
                    "committee_notes": {"bull": bull_resp, "bear": bear_resp, "risk": risk_resp},
                }
        except Exception as e:
            logger.error(f"Conflict judge failed: {e}")

        return {"final_direction": "NEUTRAL", "confidence": 0.0, "reasoning": "Judge could not parse verdict."}

    def _format_context(self, context: SkillContext) -> str:
        """Formats the SkillContext into a readable string for the LLM."""
        lines = []
        
        # Technicals
        indicators = context.analysis.get("indicators", {})
        if indicators:
            lines.append("--- Technical Analysis ---")
            lines.append(f"Overall Bias: {indicators.get('overall_bias', 'NEUTRAL')}")
            for k, v in indicators.get("indicators", {}).items():
                if isinstance(v, dict) and "value" in v:
                    lines.append(f"{k}: {v['value']}")
                elif isinstance(v, dict) and "signal" in v:
                    lines.append(f"{k}: {v['signal']}")
                
        # Liquidity
        liquidity = context.analysis.get("liquidity", {})
        if liquidity:
            lines.append("\n--- Liquidity Zones ---")
            for zone in liquidity.get("zones", []):
                lines.append(f"{zone.get('type')} at {zone.get('price_level')} (Strength: {zone.get('strength')})")
                
        # Macro & News
        macro = context.analysis.get("macro", {})
        if macro:
            lines.append("\n--- Macro Events ---")
            for ev in macro.get("events", []):
                lines.append(f"{ev.get('title')} ({ev.get('impact')} impact)")
                
        return "\n".join(lines)
