"""
Briefing Engine — Professional Market Intelligence Dashboard

Aggregates real-time data from every AI skill into a structured
briefing optimized for the Mini App dashboard and Telegram broadcasts.
"""

import logging
from datetime import datetime, UTC, timedelta
from typing import Dict, Any, List, Optional

from ..data.storage import Storage

logger = logging.getLogger("euroscope.brain.briefing")


class BriefingEngine:
    """
    Aggregates multi-source intelligence into a professional market briefing.
    
    Data sources (via Orchestrator):
      - market_data      → live price, daily range
      - session_context   → active trading session
      - technical_analysis → RSI, ADX, MACD, EMA, bias, levels, patterns
      - trading_strategy  → active signals
      - fundamental_analysis → macro news headlines
    
    Data sources (via Storage):
      - trade journal     → recent performance stats
      - alerts            → active price alert count
    """

    def __init__(self, config=None, storage: Storage = None, orchestrator=None):
        self.config = config
        self.storage = storage
        self.orchestrator = orchestrator

    # ── Core Generator ──────────────────────────────────────────

    async def generate_briefing(self) -> Dict[str, Any]:
        """
        Generates a rich, structured market briefing from live AI skills.
        Returns a dictionary of raw data — use format_for_api() or
        format_for_telegram() to render it for a specific output.
        """
        logger.info("Generating professional briefing...")

        data: Dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "urgency": "normal",
        }

        # ── 1. Market Pulse (Price + Session) ─────────────────
        data["market_pulse"] = await self._fetch_market_pulse()

        # ── 2. Technical Snapshot ─────────────────────────────
        data["technical"] = await self._fetch_technical()

        # ── 3. Active Signals ─────────────────────────────────
        data["signals"] = await self._fetch_signals()

        # ── 4. Chart Patterns ─────────────────────────────────
        data["patterns"] = await self._fetch_patterns()

        # ── 5. Macro & News ───────────────────────────────────
        data["news"] = await self._fetch_news()

        # ── 6. Performance ────────────────────────────────────
        data["performance"] = await self._fetch_performance()

        # ── 7. Risk / Urgency ─────────────────────────────────
        data["risk_alerts"] = await self._fetch_risk_alert_count()
        data["urgency"] = self._determine_urgency(data)

        # ── 8. Executive Summary (dynamic) ────────────────────
        data["summary"] = self._build_summary(data)

        return data

    # ── Data Fetchers ───────────────────────────────────────────

    async def _fetch_market_pulse(self) -> dict:
        """Fetch live price and session context."""
        pulse = {"price": 0, "change": 0, "change_pct": 0, "session": "UNKNOWN", "status": "Closed"}
        if not self.orchestrator:
            return pulse
        try:
            from ..skills.base import SkillContext
            ctx = SkillContext()
            price_res = await self.orchestrator.run_skill("market_data", "get_price", context=ctx)
            if price_res.success and price_res.data:
                d = price_res.data
                pulse["price"] = d.get("price", 0)
                pulse["change"] = d.get("change", 0)
                pulse["change_pct"] = d.get("change_pct", 0)
                pulse["high"] = d.get("high", 0)
                pulse["low"] = d.get("low", 0)
                pulse["spread_pips"] = d.get("spread_pips", 0)

            session_res = await self.orchestrator.run_skill("session_context", "detect", context=ctx)
            if session_res.success and session_res.data:
                pulse["session"] = session_res.data.get("session_regime", "unknown").upper()
                
            status_res = await self.orchestrator.run_skill("market_data", "check_market_status")
            if status_res.success and status_res.data:
                pulse["status"] = status_res.data.get("status", "Closed")
        except Exception as e:
            logger.warning(f"Briefing: market pulse failed: {e}")
        return pulse

    async def _fetch_technical(self) -> dict:
        """Fetch TA indicators and key levels."""
        tech = {
            "bias": "NEUTRAL", "rsi": 0, "adx": 0,
            "macd_signal": "---", "ema_cross": "---",
            "support": [], "resistance": []
        }
        if not self.orchestrator:
            return tech
        try:
            from ..skills.base import SkillContext
            ctx = SkillContext()
            await self.orchestrator.run_skill("market_data", "get_price", context=ctx)
            ta_res = await self.orchestrator.run_skill("technical_analysis", "analyze", context=ctx, timeframe="H1")
            if ta_res.success and ta_res.data:
                d = ta_res.data
                tech["bias"] = d.get("overall_bias", "NEUTRAL")
                ind = d.get("indicators", {})
                tech["rsi"] = ind.get("RSI", {}).get("value", 0)
                tech["adx"] = ind.get("ADX", {}).get("value", 0)
                tech["macd_signal"] = ind.get("MACD", {}).get("signal_text", "---")
                ema = ind.get("EMA", {})
                ema50 = ema.get("ema50", 0)
                ema200 = ema.get("ema200", 0)
                if ema50 and ema200:
                    tech["ema_cross"] = "ABOVE" if ema50 > ema200 else "BELOW"
                    tech["ema50"] = ema50
                    tech["ema200"] = ema200
                levels = d.get("levels", {})
                tech["support"] = levels.get("support", [])
                tech["resistance"] = levels.get("resistance", [])
                tech["atr_pips"] = ind.get("ATR", {}).get("pips", 0)
        except Exception as e:
            logger.warning(f"Briefing: technical fetch failed: {e}")
        return tech

    async def _fetch_signals(self) -> list:
        """Fetch active trading signals."""
        if not self.orchestrator:
            return []
        try:
            from ..skills.base import SkillContext
            ctx = SkillContext()
            await self.orchestrator.run_skill("market_data", "get_price", context=ctx)
            await self.orchestrator.run_skill("technical_analysis", "analyze", context=ctx, timeframe="H1")
            sig_res = await self.orchestrator.run_skill("trading_strategy", "detect_signal", context=ctx)
            if sig_res.success and sig_res.data and sig_res.data.get("direction") in ("BUY", "SELL"):
                s = sig_res.data
                return [{
                    "direction": s["direction"],
                    "strategy": s.get("strategy", "AI"),
                    "confidence": s.get("confidence", 0),
                }]
        except Exception as e:
            logger.warning(f"Briefing: signal fetch failed: {e}")
        return []

    async def _fetch_patterns(self) -> list:
        """Fetch detected chart patterns."""
        if not self.orchestrator:
            return []
        try:
            from ..skills.base import SkillContext
            ctx = SkillContext()
            await self.orchestrator.run_skill("market_data", "get_price", context=ctx)
            pat_res = await self.orchestrator.run_skill("technical_analysis", "detect_patterns", context=ctx, timeframe="H1")
            if pat_res.success and pat_res.data:
                return [
                    {"name": p.get("name", p.get("pattern", "Unknown")), "status": p.get("status", "active"), "significance": p.get("significance", "medium")}
                    for p in pat_res.data[:4]
                ]
        except Exception as e:
            logger.warning(f"Briefing: pattern fetch failed: {e}")
        return []

    async def _fetch_news(self) -> list:
        """Fetch macro news headlines."""
        if not self.orchestrator:
            return []
        try:
            res = await self.orchestrator.run_skill("fundamental_analysis", "get_news")
            if res.success and res.data:
                items = res.data if isinstance(res.data, list) else res.data.get("headlines", [])
                return [{"title": n.get("title", ""), "source": n.get("source", "")} for n in items[:4]]
        except Exception:
            pass
        # Fallback to storage
        if self.storage:
            try:
                news = await self.storage.get_recent_news(limit=4, min_impact=0.5)
                return [{"title": n.get("title", ""), "source": n.get("source", "")} for n in news]
            except Exception:
                pass
        return []

    async def _fetch_performance(self) -> dict:
        """Fetch trading performance stats."""
        perf = {"total": 0, "win_rate": 0, "total_pnl": 0}
        if not self.storage:
            return perf
        try:
            stats = await self.storage.get_trade_journal_stats()
            if stats:
                perf["total"] = stats.get("total", 0)
                perf["win_rate"] = stats.get("win_rate", 0)
                perf["total_pnl"] = stats.get("total_pnl", 0)
        except Exception:
            pass
        return perf

    async def _fetch_risk_alert_count(self) -> int:
        """Count active risk alerts."""
        if not self.storage:
            return 0
        try:
            alerts = await self.storage.get_active_alerts()
            return len(alerts) if alerts else 0
        except Exception:
            return 0

    # ── Intelligence ────────────────────────────────────────────

    def _determine_urgency(self, data: dict) -> str:
        """Determine briefing urgency from data signals."""
        alerts = data.get("risk_alerts", 0)
        rsi = data.get("technical", {}).get("rsi", 50)
        adx = data.get("technical", {}).get("adx", 0)
        signals = data.get("signals", [])

        if alerts > 3 or rsi < 20 or rsi > 80:
            return "critical"
        if alerts > 1 or signals or adx > 35:
            return "alert"
        return "normal"

    def _build_summary(self, data: dict) -> str:
        """Generate a dynamic executive summary from real data."""
        pulse = data.get("market_pulse", {})
        tech = data.get("technical", {})
        signals = data.get("signals", [])

        price = pulse.get("price", 0)
        change_pct = pulse.get("change_pct", 0)
        session = pulse.get("session", "UNKNOWN")
        bias = tech.get("bias", "NEUTRAL")
        rsi = tech.get("rsi", 0)

        direction_word = "higher" if change_pct > 0 else "lower" if change_pct < 0 else "flat"
        sign = "+" if change_pct > 0 else ""

        parts = [f"EUR/USD at {price:.5f} ({sign}{change_pct:.2f}% {direction_word})"]
        parts.append(f"during the {session.title()} session.")
        parts.append(f"Technical bias is {bias} with RSI at {rsi:.0f}.")

        if signals:
            s = signals[0]
            parts.append(f"Active {s['direction']} signal via {s['strategy']} ({s['confidence']}% confidence).")

        return " ".join(parts)

    # ── Formatters ──────────────────────────────────────────────

    def format_for_api(self, data: Dict[str, Any]) -> dict:
        """Format briefing as rich JSON for the Mini App dashboard."""
        return {
            "timestamp": data.get("timestamp"),
            "urgency": data.get("urgency", "normal"),
            "summary": data.get("summary", ""),
            "market_pulse": data.get("market_pulse", {}),
            "technical": data.get("technical", {}),
            "signals": data.get("signals", []),
            "patterns": data.get("patterns", []),
            "news": data.get("news", []),
            "performance": data.get("performance", {}),
            "risk_alerts": data.get("risk_alerts", 0),
        }

    def format_for_telegram(self, data: Dict[str, Any]) -> str:
        """Format briefing as a rich Telegram message."""
        pulse = data.get("market_pulse", {})
        tech = data.get("technical", {})
        signals = data.get("signals", [])
        patterns = data.get("patterns", [])
        perf = data.get("performance", {})
        dt = datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(UTC)

        price = pulse.get("price", 0)
        change = pulse.get("change", 0)
        change_pct = pulse.get("change_pct", 0)
        sign = "+" if change >= 0 else ""
        direction_emoji = "🟢" if change >= 0 else "🔴"

        lines = [
            f"🎙️ <b>EuroScope Market Briefing</b>",
            f"<i>{dt.strftime('%Y-%m-%d %H:%M')} UTC · {pulse.get('session', 'Unknown')} Session</i>",
            "",
            f"{direction_emoji} <b>EUR/USD {price:.5f}</b>  {sign}{change:.5f} ({sign}{change_pct:.2f}%)",
            "",
            f"📊 <b>Technical Snapshot</b>",
            f"  Bias: <b>{tech.get('bias', '---')}</b> · RSI {tech.get('rsi', 0):.0f} · ADX {tech.get('adx', 0):.0f}",
            f"  MACD: {tech.get('macd_signal', '---')} · EMA Cross: {tech.get('ema_cross', '---')}",
        ]

        sup = tech.get("support", [])
        res = tech.get("resistance", [])
        if sup or res:
            sup_str = ", ".join([f"{l:.4f}" for l in sup[:2]]) if sup else "—"
            res_str = ", ".join([f"{l:.4f}" for l in res[:2]]) if res else "—"
            lines.append(f"  🎯 S: {sup_str} | R: {res_str}")

        if signals:
            lines.append("")
            s = signals[0]
            lines.append(f"📡 <b>Active Signal:</b> {s['direction']} via {s['strategy']} ({s['confidence']}%)")

        if patterns:
            lines.append("")
            lines.append(f"🔎 <b>Patterns:</b> " + " · ".join([p["name"] for p in patterns[:3]]))

        if perf.get("total", 0) > 0:
            lines.append("")
            lines.append(f"📈 <b>Performance:</b> {perf['total']} trades · {perf['win_rate']:.0f}% WR · {perf['total_pnl']:+.1f}p")

        lines.append("")
        lines.append(f"<i>{data.get('summary', '')}</i>")

        return "\n".join(lines)
