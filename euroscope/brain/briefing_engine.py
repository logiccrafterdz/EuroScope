"""
Briefing Engine — AI-Synthesized Market Intelligence Report

Uses the LLM (Agent) to generate an institutional-grade narrative briefing
that synthesizes ALL data into a coherent analyst report.

Unlike other tabs that show raw data, the Briefing provides:
  1. AI-written narrative analysis (what's happening and WHY)
  2. Session Playbook (what to watch in THIS session)
  3. Scenario Planning (bull/bear/base cases)
  4. Conviction Score (how confident is the overall AI system)
  5. Key Watchlist (the 3 most critical things right now)
"""

import logging
from datetime import datetime, UTC
from typing import Dict, Any

from ..data.storage import Storage

logger = logging.getLogger("euroscope.brain.briefing")


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

        Flow:
        1. Run the full analysis pipeline (TA, News, Macro, Liquidity, etc.)
        2. Feed the raw data to the LLM with a specialized briefing prompt
        3. Parse the LLM output into structured sections
        """
        logger.info("Generating AI-synthesized briefing...")

        data: Dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "urgency": "normal",
        }

        # ── 1. Gather raw intelligence from all skills ──────────
        raw_intel = await self._gather_raw_intelligence()

        # ── 2. Ask the LLM to synthesize a narrative report ─────
        narrative = await self._generate_ai_narrative(raw_intel)

        # ── 3. Structure the response ───────────────────────────
        data["narrative"] = narrative
        data["raw_price"] = raw_intel.get("price", 0)
        data["raw_change"] = raw_intel.get("change", 0)
        data["raw_change_pct"] = raw_intel.get("change_pct", 0)
        data["session"] = raw_intel.get("session", "UNKNOWN")
        data["conviction"] = raw_intel.get("conviction", 50)
        data["urgency"] = self._assess_urgency(raw_intel)

        return data

    async def _gather_raw_intelligence(self) -> dict:
        """Gather all raw data from the full analysis pipeline."""
        intel = {
            "price": 0, "change": 0, "change_pct": 0,
            "session": "UNKNOWN",
            "advanced_analysis": "No data available.",
            "news": "No recent news.",
            "macro": "No macro data.",
            "conviction": 50,
        }

        if not self.orchestrator:
            return intel

        try:
            from ..skills.base import SkillContext

            # Get live price
            ctx = SkillContext()
            price_res = await self.orchestrator.run_skill("market_data", "get_price", context=ctx)
            if price_res.success and price_res.data:
                intel["price"] = price_res.data.get("price", 0)
                intel["change"] = price_res.data.get("change", 0)
                intel["change_pct"] = price_res.data.get("change_pct", 0)

            # Get session
            session_res = await self.orchestrator.run_skill("session_context", "detect", context=ctx)
            if session_res.success and session_res.data:
                intel["session"] = session_res.data.get("session_regime", "unknown").upper()

            # Run full analysis pipeline (TA + Liquidity + Macro + etc.)
            full_ctx = await self.orchestrator.run_full_analysis_pipeline(timeframe="H1")
            formatted = full_ctx.metadata.get("formatted", "")
            if formatted:
                intel["advanced_analysis"] = formatted

            # Fetch news explicitly (pipeline doesn't always include it)
            news_res = await self.orchestrator.run_skill("fundamental_analysis", "get_news")
            if news_res.success and news_res.metadata and news_res.metadata.get("formatted"):
                intel["news"] = news_res.metadata["formatted"]

            # Fetch macro data
            macro_res = await self.orchestrator.run_skill("fundamental_analysis", "get_macro")
            if macro_res.success and macro_res.metadata and macro_res.metadata.get("formatted"):
                intel["macro"] = macro_res.metadata["formatted"]

            # Calculate conviction from TA data
            ta_result = full_ctx.get_result("technical_analysis")
            if ta_result and ta_result.get("data"):
                ta = ta_result["data"]
                adx = ta.get("indicators", {}).get("ADX", {}).get("value", 0)
                rsi = ta.get("indicators", {}).get("RSI", {}).get("value", 50)
                bias = ta.get("overall_bias", "neutral").upper()

                # Higher conviction when trend is strong and clear
                conviction = 40
                if adx > 25:
                    conviction += 20
                if adx > 40:
                    conviction += 10
                if bias in ("BULLISH", "BEARISH"):
                    conviction += 15
                if 30 < rsi < 70:
                    conviction += 5  # Not at extremes = clearer trend
                intel["conviction"] = min(95, conviction)

        except Exception as e:
            logger.error(f"Briefing: raw intelligence gathering failed: {e}")

        return intel

    async def _generate_ai_narrative(self, intel: dict) -> str:
        """Use the LLM to generate a professional narrative briefing."""
        if not self.agent:
            return self._generate_fallback_narrative(intel)

        price = intel.get("price", 0)
        session = intel.get("session", "UNKNOWN")
        change_pct = intel.get("change_pct", 0)

        briefing_prompt = (
            "You are EuroScope, an elite market strategist delivering a concise intelligence briefing.\n\n"
            "## YOUR TASK\n"
            "Write a professional market briefing that a trader reads first thing to understand:\n"
            "1. WHAT happened (narrative of recent price action and WHY)\n"
            "2. WHAT TO WATCH (the 2-3 critical things in this session)\n"
            "3. SCENARIOS (if price goes up → X, if price goes down → Y)\n\n"
            "## RULES\n"
            "- Write in flowing narrative paragraphs, NOT bullet points or data dumps.\n"
            "- Be specific: mention exact prices, levels, and events.\n"
            "- Give your professional OPINION and conviction, not just facts.\n"
            "- Keep it under 250 words. Quality over quantity.\n"
            "- Do NOT use markdown headers, bold, or formatting. Plain text only.\n"
            "- Do NOT list indicators (RSI, ADX, MACD) separately — weave them into your narrative.\n"
            "- Write like a Goldman Sachs morning note, not a data readout.\n\n"
            f"## LIVE CONTEXT\n"
            f"- EUR/USD: {price:.5f} ({'+' if change_pct >= 0 else ''}{change_pct:.2f}%)\n"
            f"- Session: {session}\n\n"
            f"## FULL ANALYSIS DATA\n{intel.get('advanced_analysis', 'None')}\n\n"
            f"## NEWS & GEOPOLITICS\n{intel.get('news', 'None')}\n\n"
            f"## MACRO CONTEXT\n{intel.get('macro', 'None')}\n\n"
            "Now write the briefing. Start directly with the narrative — no greetings or headers."
        )

        try:
            response = await self.agent.stateless_chat(
                user_message="Generate the Market Intelligence Briefing now based on the full data provided.",
                system_override=briefing_prompt,
            )
            if response and response.strip():
                return response.strip()
        except Exception as e:
            logger.error(f"Briefing: LLM narrative generation failed: {e}")

        return self._generate_fallback_narrative(intel)

    def _generate_fallback_narrative(self, intel: dict) -> str:
        """Generate a basic narrative when the LLM is unavailable."""
        price = intel.get("price", 0)
        change_pct = intel.get("change_pct", 0)
        session = intel.get("session", "Unknown")
        direction = "higher" if change_pct > 0 else "lower" if change_pct < 0 else "flat"

        return (
            f"EUR/USD is trading at {price:.5f}, moving {direction} by {abs(change_pct):.2f}% "
            f"during the {session.title()} session. The AI analysis pipeline is gathering data — "
            f"a full narrative briefing will be available once the LLM engine processes the complete "
            f"market context including technical structure, macro events, and liquidity dynamics."
        )

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
