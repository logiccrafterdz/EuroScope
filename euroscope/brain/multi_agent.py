"""
Multi-Agent Deliberation (The Committee)

Instantiates specialized AI agents (Bull, Bear, Risk Manager) to deliberate on
conflicting market data and produce a final unified and highly-scrutinized decision.
"""

import logging
import asyncio
from typing import Dict, Any

from euroscope.skills.base import SkillContext

logger = logging.getLogger("euroscope.brain.committee")

class DeliberationCommittee:
    def __init__(self, llm_router=None):
        self.llm = llm_router
        
    def _build_context_prompt(self, context: SkillContext) -> str:
        tech = context.signals.get("technical_bias", "Unknown")
        fund = context.metadata.get("fundamental_bias", "Unknown")
        liq = context.metadata.get("liquidity_signal", "Unknown")
        regime = context.metadata.get("regime", "Unknown")
        
        return (
            f"Current Context:\n"
            f"- Technical Bias: {tech}\n"
            f"- Fundamental Bias: {fund}\n"
            f"- Liquidity Bias: {liq}\n"
            f"- Market Regime: {regime}\n"
            f"- Recent Signals: {context.signals}\n"
        )

    async def _ask_bull_advocate(self, context_str: str) -> str:
        prompt = (
            "You are the BULL ADVOCATE. Your job is to find reasons why EUR/USD will go UP.\n"
            "Analyze the following context and argue the bullish case. What data supports a long position?\n"
            "If the data is hopelessly bearish, acknowledge the risk but still point out the bullish counter-narrative.\n\n"
            f"{context_str}\n"
            "Argue your case in 2-3 sentences."
        )
        # Assuming deepseek is primary
        return await self.llm.chat([{"role": "user", "content": prompt}])

    async def _ask_bear_advocate(self, context_str: str) -> str:
        prompt = (
            "You are the BEAR ADVOCATE. Your job is to find reasons why EUR/USD will go DOWN.\n"
            "Analyze the following context and argue the bearish case. What data supports a short position?\n"
            "If the data is hopelessly bullish, acknowledge the trend but point out the bearish risks.\n\n"
            f"{context_str}\n"
            "Argue your case in 2-3 sentences."
        )
        # Use default router (model diversity is handled by LLMRouter fallback chain)
        return await self.llm.chat([{"role": "user", "content": prompt}])

    async def _ask_risk_manager(self, context_str: str) -> str:
        prompt = (
            "You are the STRICT RISK MANAGER. You hate losing money.\n"
            "Analyze the context and point out ONLY the risks, contradictions, and reasons why we should NOT trade right now.\n"
            f"{context_str}\n"
            "State your concerns in 2-3 sentences."
        )
        return await self.llm.chat([{"role": "user", "content": prompt}])

    async def deliberate(self, context: SkillContext) -> Dict[str, Any]:
        """
        Runs the full deliberation process.
        """
        if not self.llm:
            return {"final_direction": "NEUTRAL", "confidence": 0, "reasoning": "Committee offline - No LLM."}
            
        logger.info("Conflict detected. Convening the AI Deliberation Committee...")
        
        context_str = self._build_context_prompt(context)
        
        # Parallel execution of three distinct agents with timeout protection
        try:
            bull_resp, bear_resp, risk_resp = await asyncio.wait_for(
                asyncio.gather(
                    self._ask_bull_advocate(context_str),
                    self._ask_bear_advocate(context_str),
                    self._ask_risk_manager(context_str),
                    return_exceptions=True
                ),
                timeout=15.0  # Hard ceiling: 15 seconds for all 3 agents
            )
        except asyncio.TimeoutError:
            logger.error("Committee timed out after 15s. Defaulting to NEUTRAL.")
            return {"final_direction": "NEUTRAL", "confidence": 0, "reasoning": "Committee timed out."}
        except Exception as e:
            logger.error(f"Committee crashed: {e}")
            return {"final_direction": "NEUTRAL", "confidence": 0, "reasoning": "Committee failed to reach consensus."}
            
        # Clean exceptions if any
        bull_resp = str(bull_resp) if not isinstance(bull_resp, Exception) else "Bull offline."
        bear_resp = str(bear_resp) if not isinstance(bear_resp, Exception) else "Bear offline."
        risk_resp = str(risk_resp) if not isinstance(risk_resp, Exception) else "Risk manager offline."

        # Final Judge (Orbeus) interprets the committee
        judge_prompt = (
            "You are the CHIEF JUDGE of an AI Trading Committee for EUR/USD.\n"
            "You have heard arguments from 3 agents:\n\n"
            f"🐂 BULL ADVOCATE:\n{bull_resp}\n\n"
            f"🐻 BEAR ADVOCATE:\n{bear_resp}\n\n"
            f"🛡️ RISK MANAGER:\n{risk_resp}\n\n"
            "Based strictly on who presented the strongest, data-backed argument, make a final decision.\n"
            "Return a JSON object with: \n"
            "- 'decision' (must be 'BUY', 'SELL', or 'NEUTRAL')\n"
            "- 'confidence' (float 0.0 - 1.0)\n"
            "- 'reasoning' (1 sentence summary)\n"
            "If the Risk Manager's concerns are overwhelming, rule NEUTRAL."
        )
        
        try:
            final_verdict = await self.llm.chat([{"role": "user", "content": judge_prompt}])
            import re, json
            match = re.search(r'\{.*\}', final_verdict, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                logger.info(f"Committee Verdict: {data.get('decision')} @ {data.get('confidence')}")
                return {
                    "final_direction": data.get("decision", "NEUTRAL"),
                    "confidence": float(data.get("confidence", 0.0)),
                    "primary_evidence": "Committee Deliberation Consensus",
                    "reasoning": data.get("reasoning", ""),
                    "committee_notes": {
                        "bull": bull_resp, "bear": bear_resp, "risk": risk_resp
                    }
                }
        except Exception as e:
            logger.error(f"Judge failed: {e}")
            
        return {"final_direction": "NEUTRAL", "confidence": 0.0, "reasoning": "Judge could not parse verdict."}
