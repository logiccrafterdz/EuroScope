"""
Voice Briefing Engine — Generates concise audio-friendly market briefings.

Compiles key data (price, bias, regime, forecasts, risk) into a
structured text briefing that can be:
  1. Sent as a Telegram text message (formatted)
  2. Converted to audio via TTS (Google/OpenAI)

Usage:
    engine = VoiceBriefingEngine(orchestrator, storage)
    briefing = await engine.generate_briefing()
    text = engine.format_for_telegram(briefing)
    audio = await engine.generate_audio(briefing)  # optional TTS
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional

logger = logging.getLogger("euroscope.analytics.voice_briefing")


@dataclass
class BriefingSection:
    """A single section of the voice briefing."""
    title: str
    content: str
    priority: int = 5
    icon: str = "📋"  # 1=highest, 10=lowest


@dataclass
class MarketBriefing:
    """Complete market briefing compiled from multiple data sources."""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    sections: list[BriefingSection] = field(default_factory=list)
    summary: str = ""
    urgency: str = "normal"  # "normal", "alert", "critical"

    def to_text(self) -> str:
        """Convert briefing to plain text for TTS."""
        lines = [self.summary, ""]
        for s in sorted(self.sections, key=lambda x: x.priority):
            lines.append(f"{s.title}. {s.content}")
        return ". ".join(lines)


class VoiceBriefingEngine:
    """
    Compiles data from orchestrator and storage into
    a structured voice briefing.
    """

    def __init__(self, orchestrator=None, storage=None):
        self.orchestrator = orchestrator
        self.storage = storage

    async def generate_briefing(self) -> MarketBriefing:
        """
        Generate a complete market briefing.

        Gathers data from multiple sources and compiles into sections.
        """
        briefing = MarketBriefing()
        sections = []

        # 1. Price & Session
        price_section = await self._get_price_section()
        if price_section:
            sections.append(price_section)

        # 2. Technical Bias
        ta_section = await self._get_technical_section()
        if ta_section:
            sections.append(ta_section)

        # 2b. News & Geopolitics
        news_section = await self._get_news_section()
        if news_section:
            sections.append(news_section)

        # 3. Recent Signals  
        signal_section = await self._get_signal_section()
        if signal_section:
            sections.append(signal_section)

        # 4. Scenario Analysis & Targets
        scenario_section = await self._get_scenario_section()
        if scenario_section:
            sections.append(scenario_section)

        # 5. Performance Summary
        perf_section = await self._get_performance_section()
        if perf_section:
            sections.append(perf_section)

        # 6. Risk Alerts
        risk_section = await self._get_risk_section()
        if risk_section:
            sections.append(risk_section)

        briefing.sections = sections
        briefing.summary = self._build_summary(sections)
        briefing.urgency = self._assess_urgency(sections)

        return briefing

    async def _get_price_section(self) -> Optional[BriefingSection]:
        """Get current price and session info."""
        if not self.orchestrator:
            return None
        try:
            from ..skills.base import SkillContext
            ctx = SkillContext()
            result = await self.orchestrator.run_skill(
                "market_data", "get_summary", context=ctx
            )
            if result.success and result.data:
                d = result.data
                price = d.get("price", 0)
                change = d.get("change", 0)
                change_pct = d.get("change_pct", 0)
                sign = "+" if change >= 0 else ""
                return BriefingSection(
                    title="Current Price",
                    content=(
                        f"EUR/USD is trading at {price:.5f}, "
                        f"{sign}{change:.5f} ({sign}{change_pct:.2f}%) on the day"
                    ),
                    priority=1,
                    icon="💹",
                )
        except Exception as e:
            logger.debug(f"Price section failed: {e}")
        return None

    async def _get_technical_section(self) -> Optional[BriefingSection]:
        """Get technical analysis bias."""
        if not self.orchestrator:
            return None
        try:
            from ..skills.base import SkillContext
            ctx = SkillContext()
            result = await self.orchestrator.run_skill(
                "technical_analysis", "analyze", context=ctx, timeframe="H1"
            )
            if result.success and result.data:
                bias = result.data.get("overall_bias", "NEUTRAL")
                indicators = result.data.get("indicators", {})
                rsi = indicators.get("RSI", {}).get("value", 0)
                adx = indicators.get("ADX", {}).get("value", 0)
                return BriefingSection(
                    title="Technical Outlook",
                    content=(
                        f"The overall bias is {bias}. "
                        f"RSI is at {rsi:.1f}, ADX is at {adx:.1f}"
                    ),
                    priority=2,
                    icon="📊",
                )
        except Exception as e:
            logger.debug(f"Technical section failed: {e}")
        return None

    async def _get_news_section(self) -> Optional[BriefingSection]:
        """Get latest macroeconomic events and geopolitical news."""
        if not self.orchestrator:
            return None
        try:
            # We call the 'fundamental_analysis' skill which parses raw news and FRED
            result = await self.orchestrator.run_skill("fundamental_analysis", "get_news")
            if result.success and result.data:
                # The 'formatted' field contains the raw aggregated newsletter style bullet points
                formatted_news = result.metadata.get("formatted") or str(result.data)
                
                # Truncate only for extreme length — 3000 chars keeps full newsletter context
                content = formatted_news[:3000] + "..." if len(formatted_news) > 3000 else formatted_news
                
                return BriefingSection(
                    title="Macro & Geopolitics",
                    content=content,
                    priority=2,
                    icon="🌍",
                )
        except Exception as e:
            logger.debug(f"News section failed: {e}")
        return None

    async def _get_scenario_section(self) -> Optional[BriefingSection]:
        """Get structured strategic scenarios from the forecaster."""
        if not self.orchestrator or not hasattr(self.orchestrator, 'global_context'):
            return None
        try:
            # We can retrieve the forecast from memory if it ran recently, 
            # but for a fresh briefing, we should trigger a forecast scan
            # However, invoking the full LLM forecaster here might be slow.
            # Fast path: check if we have a recent forecast stored in memory.
            mem = await self.storage.get_memory('active_forecast', {})
            if mem and mem.get('text'):
                text = mem.get('text', '')
                # 2000 chars keeps the full forecast reasoning intact
                snippet = text[:2000] + "..." if len(text) > 2000 else text
                return BriefingSection(
                    title="Strategic Scenarios",
                    content=snippet,
                    priority=3,
                    icon="🎯",
                )
            return None
        except Exception as e:
            logger.debug(f"Scenario section failed: {e}")
        return None

    async def _get_signal_section(self) -> Optional[BriefingSection]:
        """Get recent trading signals."""
        if not self.storage:
            return None
        try:
            signals = await self.storage.get_signals(limit=3)
            if signals:
                count = len(signals)
                latest = signals[0]
                direction = latest.get("direction", "unknown")
                return BriefingSection(
                    title="Trading Signals",
                    content=f"{count} recent signals. Latest is a {direction} signal",
                    priority=3,
                    icon="📡",
                )
        except Exception as e:
            logger.debug(f"Signal section failed: {e}")
        return None

    async def _get_performance_section(self) -> Optional[BriefingSection]:
        """Get trading performance stats."""
        if not self.storage:
            return None
        try:
            stats = await self.storage.get_trade_journal_stats()
            if stats and stats.get("total", 0) > 0:
                return BriefingSection(
                    title="Performance",
                    content=(
                        f"{stats['total']} trades with "
                        f"{stats.get('win_rate', 0):.0f}% win rate "
                        f"and {stats.get('total_pnl', 0):+.1f} pips total"
                    ),
                    priority=4,
                    icon="📈",
                )
        except Exception as e:
            logger.debug(f"Performance section failed: {e}")
        return None

    async def _get_risk_section(self) -> Optional[BriefingSection]:
        """Check for any elevated risk conditions."""
        # Compile risk warnings
        warnings = []
        if self.storage:
            try:
                alerts = await self.storage.get_active_alerts()
                if alerts and len(alerts) > 2:
                    warnings.append(f"{len(alerts)} active price alerts")
            except Exception:
                pass

        if warnings:
            return BriefingSection(
                title="Risk Alerts",
                content=". ".join(warnings),
                priority=1,
                icon="⚠️",
            )
        return None

    def _build_summary(self, sections: list[BriefingSection]) -> str:
        """Build a concise executive summary — NOT a copy of section content."""
        if not sections:
            return "No market data available for briefing."

        # Extract key facts for a proper one-liner
        price_part = ""
        bias_part = ""
        for s in sections:
            if s.title == "Current Price" and "trading at" in s.content:
                # Extract just the price and change
                price_part = s.content.split(",")[0].replace("EUR/USD is trading at ", "")
            if s.title == "Technical Outlook" and "bias is" in s.content:
                bias_part = s.content.split(".")[0].replace("The overall bias is ", "").strip()

        if price_part and bias_part:
            return f"EUR/USD at {price_part} — Technical bias: {bias_part}. {len(sections)} sections analyzed."
        elif price_part:
            return f"EUR/USD at {price_part}. {len(sections)} sections analyzed."
        else:
            return f"Market briefing compiled with {len(sections)} sections."

    def _assess_urgency(self, sections: list[BriefingSection]) -> str:
        """Assess overall briefing urgency."""
        has_risk = any(s.title == "Risk Alerts" for s in sections)
        if has_risk:
            return "alert"
        return "normal"

    # ── Formatting ─────────────────────────────────────────────

    def format_for_telegram(self, briefing: MarketBriefing) -> str:
        """Format briefing for Telegram message display."""
        icons = {
            "Current Price": "💱",
            "Technical Outlook": "📊",
            "Trading Signals": "📡",
            "Performance": "📈",
            "Risk Alerts": "⚠️",
        }
        urgency_header = {
            "normal": "🎙️ *Market Briefing*",
            "alert": "🔔 *Market Briefing — Alert*",
            "critical": "🚨 *CRITICAL Market Briefing*",
        }

        lines = [
            urgency_header.get(briefing.urgency, "🎙️ *Market Briefing*"),
            f"_{briefing.timestamp.strftime('%Y-%m-%d %H:%M UTC')}_",
            "",
        ]

        for s in sorted(briefing.sections, key=lambda x: x.priority):
            icon = icons.get(s.title, "📌")
            lines.append(f"{icon} *{s.title}*")
            lines.append(f"  {s.content}")
            lines.append("")

        return "\n".join(lines)

    def format_for_api(self, briefing: MarketBriefing) -> dict:
        """Format briefing as JSON for Mini App API."""
        return {
            "timestamp": briefing.timestamp.isoformat(),
            "urgency": briefing.urgency,
            "summary": briefing.summary,
            "section_count": len(briefing.sections),
            "sections": [
                {
                    "title": s.title,
                    "content": s.content,
                    "priority": s.priority,
                    "icon": s.icon,
                }
                for s in sorted(briefing.sections, key=lambda x: x.priority)
            ],
            "text_for_tts": briefing.to_text(),
        }

    async def generate_audio(self, briefing: MarketBriefing) -> Optional[bytes]:
        """
        Generate audio from briefing text using TTS.

        Currently a placeholder — can be wired to:
        - Google Cloud TTS
        - OpenAI TTS (tts-1 model)
        - Edge-TTS (free, local)

        Returns audio bytes (MP3) or None.
        """
        # TODO: Wire to actual TTS provider
        logger.info("Audio TTS generation not yet configured — returning text only")
        return None
