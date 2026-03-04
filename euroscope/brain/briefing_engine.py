"""
Briefing Engine — AI-Synthesized Market Intelligence Report

Uses the LLM (Agent) to generate an institutional-grade narrative briefing
that synthesizes ALL data into a coherent analyst report.

Unlike other tabs that show raw data, the Briefing provides:
  1. AI-written narrative analysis (what's happening and WHY)
  2. Session Playbook (what to watch in THIS session)
  3. Scenario Planning (bull/bear/base cases)
  4. Conviction Score (how confident is the overall AI system)
"""

import asyncio
import logging
from datetime import datetime, UTC
from typing import Dict, Any

from ..data.storage import Storage

logger = logging.getLogger("euroscope.brain.briefing")

# Timeout for the entire briefing generation (seconds)
BRIEFING_TIMEOUT = 45
# Timeout for individual skill calls (seconds)
SKILL_TIMEOUT = 10
# Timeout for LLM narrative generation (seconds)
LLM_TIMEOUT = 25


class BriefingEngine:
    """
    Generates an AI-synthesized market briefing using the LLM.

    This is NOT a data dashboard — it's an analyst report.
    Raw data lives in other tabs; this tab provides SYNTHESIS and JUDGMENT.
    """

    def __init__(self, config=None, storage: Storage = None, orchestrator=None):
        self.config = config
        self.storage = storage
        self.orchestrator = orchestrator
        self.agent = None  # Set by telegram_bot after init

    async def generate_briefing(self) -> Dict[str, Any]:
        """
        Generate a rich AI-synthesized market briefing.
        Wrapped in a global timeout to prevent HTTP deadline exceeded errors.
        """
        logger.info("Generating AI-synthesized briefing...")

        try:
            return await asyncio.wait_for(
                self._generate_briefing_inner(),
                timeout=BRIEFING_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("Briefing: global timeout exceeded — returning fallback")
            return self._make_timeout_response()

    async def _generate_briefing_inner(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "urgency": "normal",
        }

        # ── 1. Gather raw intelligence (lightweight calls) ─────
        raw_intel = await self._gather_raw_intelligence()

        # ── 2. Ask the LLM to synthesize a narrative report ────
        narrative = await self._generate_ai_narrative(raw_intel)

        # ── 3. Structure the response ──────────────────────────
        data["narrative"] = narrative
        data["raw_price"] = raw_intel.get("price", 0)
        data["raw_change"] = raw_intel.get("change", 0)
        data["raw_change_pct"] = raw_intel.get("change_pct", 0)
        data["session"] = raw_intel.get("session", "UNKNOWN")
        data["conviction"] = raw_intel.get("conviction", 50)
        data["urgency"] = self._assess_urgency(raw_intel)

        return data

    def _make_timeout_response(self) -> dict:
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "urgency": "normal",
            "narrative": "The AI analysis is taking longer than expected. The system is processing a large amount of market data. Please try again in a moment.",
            "raw_price": 0, "raw_change": 0, "raw_change_pct": 0,
            "session": "UNKNOWN", "conviction": 0,
        }

    async def _gather_raw_intelligence(self) -> dict:
        """Gather data using lightweight individual skill calls with timeouts."""
        intel = {
            "price": 0, "change": 0, "change_pct": 0,
            "session": "UNKNOWN",
            "ta_summary": "",
            "news": "No recent news.",
            "macro": "No macro data.",
            "conviction": 50,
        }

        if not self.orchestrator:
            return intel

        from ..skills.base import SkillContext

        # ── Price (fast, critical) ─────────────────────────────
        try:
            ctx = SkillContext()
            price_res = await asyncio.wait_for(
                self.orchestrator.run_skill("market_data", "get_price", context=ctx),
                timeout=SKILL_TIMEOUT,
            )
            if price_res.success and price_res.data:
                intel["price"] = price_res.data.get("price", 0)
                intel["change"] = price_res.data.get("change", 0)
                intel["change_pct"] = price_res.data.get("change_pct", 0)
        except Exception as e:
            logger.warning(f"Briefing: price fetch failed: {e}")

        # ── Session (fast) ─────────────────────────────────────
        try:
            session_res = await asyncio.wait_for(
                self.orchestrator.run_skill("session_context", "detect"),
                timeout=SKILL_TIMEOUT,
            )
            if session_res.success and session_res.data:
                intel["session"] = session_res.data.get("session_regime", "unknown").upper()
        except Exception as e:
            logger.warning(f"Briefing: session fetch failed: {e}")

        # ── TA (moderate — needs candles first) ────────────────
        try:
            ctx2 = SkillContext()
            await asyncio.wait_for(
                self.orchestrator.run_skill("market_data", "get_price", context=ctx2),
                timeout=SKILL_TIMEOUT,
            )
            ta_res = await asyncio.wait_for(
                self.orchestrator.run_skill("technical_analysis", "analyze", context=ctx2, timeframe="H1"),
                timeout=SKILL_TIMEOUT,
            )
            if ta_res.success and ta_res.data:
                ta = ta_res.data
                bias = ta.get("overall_bias", "neutral").upper()
                ind = ta.get("indicators", {})
                rsi = ind.get("RSI", {}).get("value", 0)
                adx = ind.get("ADX", {}).get("value", 0)
                levels = ta.get("levels", {})
                sup = levels.get("support", [])
                res_l = levels.get("resistance", [])
                
                sup_str = ", ".join([f"{l:.4f}" for l in sup[:2]]) if sup else "none"
                res_str = ", ".join([f"{l:.4f}" for l in res_l[:2]]) if res_l else "none"
                
                intel["ta_summary"] = (
                    f"Bias: {bias} | RSI: {rsi:.0f} | ADX: {adx:.0f} | "
                    f"Support: {sup_str} | Resistance: {res_str}"
                )
                
                # Conviction
                conviction = 40
                if adx > 25: conviction += 20
                if adx > 40: conviction += 10
                if bias in ("BULLISH", "BEARISH"): conviction += 15
                if 30 < rsi < 70: conviction += 5
                intel["conviction"] = min(95, conviction)
            
            # Also get formatted summary from metadata
            if ta_res.metadata and ta_res.metadata.get("formatted"):
                intel["ta_summary"] = ta_res.metadata["formatted"]
        except Exception as e:
            logger.warning(f"Briefing: TA fetch failed: {e}")

        # ── News + Macro (concurrent, with timeouts) ──────────
        async def fetch_news():
            try:
                res = await asyncio.wait_for(
                    self.orchestrator.run_skill("fundamental_analysis", "get_news"),
                    timeout=SKILL_TIMEOUT,
                )
                if res.success and res.metadata and res.metadata.get("formatted"):
                    return res.metadata["formatted"]
            except Exception:
                pass
            return "No recent news."

        async def fetch_macro():
            try:
                res = await asyncio.wait_for(
                    self.orchestrator.run_skill("fundamental_analysis", "get_macro"),
                    timeout=SKILL_TIMEOUT,
                )
                if res.success and res.metadata and res.metadata.get("formatted"):
                    return res.metadata["formatted"]
            except Exception:
                pass
            return "No macro data."

        news_result, macro_result = await asyncio.gather(
            fetch_news(), fetch_macro(), return_exceptions=True
        )
        intel["news"] = news_result if isinstance(news_result, str) else "No recent news."
        intel["macro"] = macro_result if isinstance(macro_result, str) else "No macro data."

        return intel

    async def _generate_ai_narrative(self, intel: dict) -> str:
        """Use the LLM to generate a professional narrative briefing (with timeout)."""
        if not self.agent:
            return self._generate_fallback_narrative(intel)

        price = intel.get("price", 0)
        session = intel.get("session", "UNKNOWN")
        change_pct = intel.get("change_pct", 0)

        briefing_prompt = (
            "You are EuroScope, an elite market strategist delivering a concise intelligence briefing.\n\n"
            "## YOUR TASK\n"
            "Write a professional market briefing that a trader reads to understand:\n"
            "1. WHAT happened (narrative of recent price action and WHY)\n"
            "2. WHAT TO WATCH (the 2-3 critical things in this session)\n"
            "3. SCENARIOS (if price goes up → X, if price goes down → Y)\n\n"
            "## RULES\n"
            "- Write in flowing narrative paragraphs, NOT bullet points or data dumps.\n"
            "- Be specific: mention exact prices, levels, and events.\n"
            "- Give your professional OPINION and conviction, not just facts.\n"
            "- Keep it under 200 words. Quality over quantity.\n"
            "- Do NOT use markdown headers, bold, or formatting. Plain text only.\n"
            "- Do NOT list indicators separately — weave them into your narrative.\n"
            "- Write like a Goldman Sachs morning note, not a data readout.\n\n"
            f"## LIVE DATA\n"
            f"- EUR/USD: {price:.5f} ({'+' if change_pct >= 0 else ''}{change_pct:.2f}%)\n"
            f"- Session: {session}\n"
            f"- Technical: {intel.get('ta_summary', 'N/A')}\n\n"
            f"## NEWS\n{intel.get('news', 'None')}\n\n"
            f"## MACRO\n{intel.get('macro', 'None')}\n\n"
            "Now write the briefing. Start directly — no greetings or headers."
        )

        try:
            response = await asyncio.wait_for(
                self.agent.stateless_chat(
                    user_message="Generate the Market Intelligence Briefing based on the data provided.",
                    system_override=briefing_prompt,
                ),
                timeout=LLM_TIMEOUT,
            )
            if response and response.strip():
                return response.strip()
        except asyncio.TimeoutError:
            logger.warning("Briefing: LLM timed out — using fallback")
        except Exception as e:
            logger.error(f"Briefing: LLM narrative generation failed: {e}")

        return self._generate_fallback_narrative(intel)

    def _generate_fallback_narrative(self, intel: dict) -> str:
        """Generate a basic narrative when the LLM is unavailable."""
        price = intel.get("price", 0)
        change_pct = intel.get("change_pct", 0)
        session = intel.get("session", "Unknown")
        ta = intel.get("ta_summary", "")
        direction = "higher" if change_pct > 0 else "lower" if change_pct < 0 else "flat"

        parts = [
            f"EUR/USD is trading at {price:.5f}, moving {direction} by {abs(change_pct):.2f}% "
            f"during the {session.title()} session."
        ]
        if ta:
            parts.append(f"Technical snapshot: {ta}.")
        parts.append("Full AI narrative will be available once the LLM engine responds.")
        return " ".join(parts)

    def _assess_urgency(self, intel: dict) -> str:
        """Assess briefing urgency from market conditions."""
        conviction = intel.get("conviction", 50)
        change_pct = abs(intel.get("change_pct", 0))

        if change_pct > 0.5 or conviction > 80:
            return "critical"
        if change_pct > 0.2 or conviction > 65:
            return "alert"
        return "normal"

    # ── Formatters ──────────────────────────────────────────────

    def format_for_api(self, data: Dict[str, Any]) -> dict:
        """Format briefing for the Mini App dashboard."""
        return {
            "timestamp": data.get("timestamp"),
            "urgency": data.get("urgency", "normal"),
            "narrative": data.get("narrative", ""),
            "price": data.get("raw_price", 0),
            "change": data.get("raw_change", 0),
            "change_pct": data.get("raw_change_pct", 0),
            "session": data.get("session", "UNKNOWN"),
            "conviction": data.get("conviction", 50),
        }

    def format_for_telegram(self, data: Dict[str, Any]) -> str:
        """Format briefing as a Telegram message."""
        price = data.get("raw_price", 0)
        change = data.get("raw_change", 0)
        change_pct = data.get("raw_change_pct", 0)
        session = data.get("session", "Unknown")
        conviction = data.get("conviction", 50)
        narrative = data.get("narrative", "")
        sign = "+" if change >= 0 else ""
        emoji = "🟢" if change >= 0 else "🔴"

        dt = datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(UTC)

        lines = [
            f"🎙️ <b>Market Intelligence Briefing</b>",
            f"<i>{dt.strftime('%H:%M UTC')} · {session} Session</i>",
            "",
            f"{emoji} <b>EUR/USD {price:.5f}</b>  {sign}{change_pct:.2f}%",
            f"🎯 AI Conviction: {conviction}%",
            "",
            narrative,
        ]

        return "\n".join(lines)
