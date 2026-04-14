"""
Technical Analysis Skill — Wraps TechnicalAnalyzer, PatternDetector, LevelAnalyzer.
"""

from datetime import datetime, UTC

from ...analysis.technical import TechnicalAnalyzer
from ...analysis.patterns import PatternDetector
from ...analysis.levels import LevelAnalyzer
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class TechnicalAnalysisSkill(BaseSkill):
    name = "technical_analysis"
    description = "Computes indicators, detects patterns, and finds key price levels"
    emoji = "📈"
    category = SkillCategory.ANALYSIS
    version = "1.0.0"
    capabilities = ["analyze", "detect_patterns", "find_levels", "full"]

    def __init__(self):
        super().__init__()
        self.technical = TechnicalAnalyzer()
        self.patterns = PatternDetector()
        self.levels = LevelAnalyzer()
        self._provider = None
        self._tracker = None

    def set_provider(self, provider):
        """Inject the PriceProvider instance."""
        self._provider = provider

    def set_price_provider(self, provider):
        self._provider = provider

    def set_pattern_tracker(self, tracker):
        """Inject the PatternTracker instance."""
        self._tracker = tracker

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        df = params.get("df", context.market_data.get("candles"))
        
        # Auto-fetch if missing and provider available
        if (df is None or (hasattr(df, 'empty') and df.empty)) and self._provider:
            tf = params.get("timeframe", context.market_data.get("timeframe", "H1"))
            # Fetch 300 candles to ensure indicators like EMA 200 and RSI have enough warm-up
            df = await self._provider.get_candles(timeframe=tf, count=300)
            if df is not None:
                context.market_data["candles"] = df
                context.market_data["timeframe"] = tf

        if df is None or (hasattr(df, 'empty') and df.empty):
            return SkillResult(success=False, error="No candle data available")

        # Validate data sufficiency BEFORE analysis
        if not self._has_sufficient_data(df):
            return SkillResult(
                status="rejected",
                data={},
                metadata={
                    "rejection_reason": "insufficient_candle_data",
                    "required_candles": 50,
                    "available_candles": len(df)
                }
            )

        if action == "analyze":
            return await self._analyze(context, df)
        elif action == "detect_patterns":
            return await self._detect_patterns(context, df)
        elif action == "find_levels":
            return await self._find_levels(context, df)
        elif action == "full":
            return await self._full(context, df)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _analyze(self, context: SkillContext, df) -> SkillResult:
        ta = self.technical.analyze(df)
        if "error" in ta:
            return SkillResult(success=False, error=ta["error"])
        context.analysis["indicators"] = ta
        bias = str(ta.get("overall_bias", "neutral")).upper()
        context.metadata["technical_bias"] = bias
        
        formatted = self._format_analysis(ta)
        return SkillResult(success=True, data=ta, metadata={"formatted": formatted})

    def _format_analysis(self, data: dict) -> str:
        lines = ["📊 *Technical Analysis*"]
        bias = data.get("overall_bias", "N/A")
        icon = {"Bullish": "🟢", "Bearish": "🔴"}.get(bias, "⚪")
        lines.append(f"Bias: {icon} {bias}\n")

        ind = data.get("indicators", {})
        
        # RSI
        rsi = ind.get("RSI", {})
        lines.append(f"*RSI*: `{rsi.get('value', 0):.1f}` ({rsi.get('signal', 'N/A')})")
        
        # MACD
        macd = ind.get("MACD", {})
        lines.append(f"*MACD*: `{macd.get('macd', 0):.5f}` ({macd.get('signal_text', 'N/A')})")
        
        # Bands
        bb = ind.get("Bollinger", {})
        lines.append(f"*BB*: {bb.get('position', 'N/A')}")
        
        # ATR
        atr = ind.get("ATR", {})
        lines.append(f"*ATR*: `{atr.get('pips', 0):.1f} pips`")

        return "\n".join(lines)

    async def _detect_patterns(self, context: SkillContext, df) -> SkillResult:
        patterns = self.patterns.detect_all(df)
        adjusted = self._apply_pattern_context(patterns, context, df)
        context.analysis["patterns"] = adjusted
        context.metadata["patterns"] = adjusted
        context.metadata["pattern_context_applied"] = True
        context.metadata["pattern_signal"] = self._infer_pattern_signal(adjusted)
        
        # Record patterns if tracker available
        multipliers = {}
        if self._tracker:
            tf = context.market_data.get("timeframe", "H1")
            price = float(df['Close'].iloc[-1])
            for p in adjusted:
                name, signal = self._normalize_pattern(p)
                await self._tracker.record_detection(name, tf, signal, price)
                multipliers[name] = await self._tracker.get_confidence_multiplier(name, tf)

        formatted = self._format_patterns(adjusted)
        return SkillResult(success=True, data=adjusted, metadata={
            "formatted": formatted,
            "pattern_multipliers": multipliers
        })

    def _format_patterns(self, patterns: list) -> str:
        if not patterns:
            return "📉 No patterns detected."
        
        lines = ["🧩 *Detected Patterns*"]
        for p in patterns:
            name, signal = self._normalize_pattern(p)
            icon = "🟢" if signal == "BULLISH" else "🔴" if signal == "BEARISH" else "⚪"
            lines.append(f"{icon} {name} ({signal.capitalize()})")
        return "\n".join(lines)

    async def _find_levels(self, context: SkillContext, df) -> SkillResult:
        levels = self.levels.find_support_resistance(df)
        context.analysis["levels"] = levels
        formatted = self._format_levels(levels)
        return SkillResult(success=True, data=levels, metadata={"formatted": formatted})

    def _format_levels(self, levels: dict) -> str:
        lines = ["📏 *Key Levels*"]
        sup = levels.get("support", [])
        res = levels.get("resistance", [])
        
        lines.append(f"Supports: " + ", ".join([f"`{p:.5f}`" for p in sup[:3]]))
        lines.append(f"Resistances: " + ", ".join([f"`{p:.5f}`" for p in res[:3]]))
        return "\n".join(lines)

    async def _full(self, context: SkillContext, df) -> SkillResult:
        ta = self.technical.analyze(df)
        patterns = self.patterns.detect_all(df)
        adjusted = self._apply_pattern_context(patterns, context, df)
        levels = self.levels.find_support_resistance(df)

        # Record patterns if tracker available
        multipliers = {}
        if self._tracker:
            tf = context.market_data.get("timeframe", "H1")
            price = float(df['Close'].iloc[-1])
            for p in adjusted:
                name, signal = self._normalize_pattern(p)
                await self._tracker.record_detection(name, tf, signal, price)
                multipliers[name] = await self._tracker.get_confidence_multiplier(name, tf)

        data = {"indicators": ta, "patterns": adjusted, "levels": levels}
        context.analysis.update(data)
        bias = str(ta.get("overall_bias", "neutral")).upper()
        context.metadata["technical_bias"] = bias
        context.metadata["patterns"] = adjusted
        context.metadata["pattern_context_applied"] = True
        context.metadata["pattern_signal"] = self._infer_pattern_signal(adjusted)
        if multipliers:
            context.metadata["pattern_multipliers"] = multipliers
            
        formatted_ta = self._format_analysis(ta)
        formatted_patterns = self._format_patterns(adjusted)
        formatted_levels = self._format_levels(levels)
        formatted = f"{formatted_ta}\n\n{formatted_patterns}\n\n{formatted_levels}"
        
        context.metadata["formatted"] = formatted

        return SkillResult(
            success=True, data=data, next_skill="risk_management",
            metadata={"pattern_multipliers": multipliers, "formatted": formatted}
        )

    @staticmethod
    def _normalize_pattern(pattern: dict) -> tuple[str, str]:
        name = pattern.get("name") or pattern.get("pattern") or "Unknown"
        raw_signal = pattern.get("signal") or pattern.get("type") or "neutral"
        signal = str(raw_signal).strip().lower()
        if signal == "bullish":
            return name, "BULLISH"
        if signal == "bearish":
            return name, "BEARISH"
        return name, "NEUTRAL"

    @staticmethod
    def _infer_pattern_signal(patterns: list) -> str:
        bullish = 0
        bearish = 0
        for p in patterns:
            signal = str(p.get("signal") or p.get("type") or p.get("bias") or "neutral").strip().lower()
            if signal == "bullish":
                bullish += 1
            elif signal == "bearish":
                bearish += 1
        if bullish > bearish:
            return "BULLISH"
        if bearish > bullish:
            return "BEARISH"
        return "NEUTRAL"

    def _apply_pattern_context(self, patterns: list, context: SkillContext, df) -> list:
        session_regime = context.metadata.get("session_regime", "unknown")
        market_intent = context.metadata.get("market_intent", {}) or {}
        liquidity_zones = context.metadata.get("liquidity_zones", []) or []
        return [
            self._adjust_pattern_confidence(p, session_regime, market_intent, liquidity_zones, context, df)
            for p in patterns
        ]

    def _adjust_pattern_confidence(self, pattern: dict, session_regime: str,
                                   market_intent: dict, liquidity_zones: list,
                                   context: SkillContext, df) -> dict:
        base_raw = pattern.get("confidence", 0.5)
        try:
            base_raw = float(base_raw)
        except (TypeError, ValueError):
            base_raw = 0.5
        base_confidence = base_raw / 100.0 if base_raw > 1 else base_raw
        base_confidence = max(0.0, min(1.0, base_confidence))

        notes = []
        session_penalty = 0.0
        liquidity_penalty = 0.0
        liquidity_bonus = 0.0
        pattern_bonus = 0.0
        pattern_penalty = 0.0

        name = (pattern.get("pattern") or pattern.get("name") or "").strip().lower()
        pattern_type = (pattern.get("type") or pattern.get("signal") or "neutral").strip().lower()
        reversal_names = {"head & shoulders", "head and shoulders", "double top", "double bottom"}
        is_reversal = name in reversal_names

        if session_regime in ("weekend", "holiday"):
            session_penalty -= 0.30
            notes.append(f"session_penalty: {session_regime}")
        elif session_regime == "asian" and is_reversal:
            session_penalty -= 0.20
            notes.append("session_penalty: asian")

        next_move = (market_intent.get("next_likely_move") or "").lower()
        if is_reversal and next_move in ("up", "down"):
            if pattern_type == "bearish" and next_move == "up":
                liquidity_penalty -= 0.25
                notes.append("liquidity_conflict: reversal_vs_up")
            if pattern_type == "bullish" and next_move == "down":
                liquidity_penalty -= 0.25
                notes.append("liquidity_conflict: reversal_vs_down")

        pattern_price = self._pattern_reference_price(pattern)
        if market_intent.get("current_phase") == "liquidity_sweep" and pattern_price is not None:
            if self._near_zone(pattern_price, liquidity_zones, 10, None):
                liquidity_penalty -= 0.20
                notes.append("liquidity_penalty: near_sweep_zone")

        last_close = None
        if df is not None and hasattr(df, "iloc") and len(df) > 0:
            try:
                last_close = float(df["Close"].iloc[-1])
            except Exception as e:
                logger.debug(f"Failed to get last close price: {e}")
                last_close = None
        if last_close is not None:
            if self._breaks_strong_zone(last_close, liquidity_zones, pattern_type):
                liquidity_bonus += 0.15
                notes.append("liquidity_bonus: strong_break")

        if name in {"head & shoulders", "head and shoulders"}:
            bias = (context.analysis.get("indicators", {}) or {}).get("overall_bias")
            bias = (bias or "").lower()
            if pattern_type == "bearish" and bias == "bullish":
                pattern_penalty -= 0.20
                notes.append("pattern_penalty: against_trend")
            if pattern_type == "bullish" and bias == "bearish":
                pattern_penalty -= 0.20
                notes.append("pattern_penalty: against_trend")
            if self._high_impact_news_within(context, 60):
                pattern_penalty -= 0.25
                notes.append("pattern_penalty: high_impact_news")
            if self._in_range_midpoint(pattern_price, df):
                pattern_penalty -= 0.15
                notes.append("pattern_penalty: mid_range")

        if name in {"double top", "double bottom"}:
            if name == "double top" and self._near_zone(pattern_price, liquidity_zones, 10, "session_high"):
                pattern_bonus += 0.10
                notes.append("pattern_bonus: session_high")
            if name == "double bottom" and self._near_zone(pattern_price, liquidity_zones, 10, "session_low"):
                pattern_bonus += 0.10
                notes.append("pattern_bonus: session_low")
            if self._volume_spike(df):
                pattern_bonus += 0.15
                notes.append("pattern_bonus: volume_spike")

        final_confidence = base_confidence + session_penalty + liquidity_penalty + liquidity_bonus + pattern_bonus + pattern_penalty
        final_confidence = max(0.0, min(1.0, final_confidence))

        updated = dict(pattern)
        updated["confidence"] = round(final_confidence, 2)
        updated["context_notes"] = notes
        updated["confidence_breakdown"] = {
            "base_confidence": round(base_confidence, 2),
            "session_penalty": round(session_penalty, 2),
            "liquidity_penalty": round(liquidity_penalty, 2),
            "liquidity_bonus": round(liquidity_bonus, 2),
            "pattern_penalty": round(pattern_penalty, 2),
            "pattern_bonus": round(pattern_bonus, 2),
            "final_confidence": round(final_confidence, 2),
        }
        return updated

    @staticmethod
    def _pattern_reference_price(pattern: dict) -> float | None:
        for key in ("level", "neckline", "head", "shoulders", "upper", "lower"):
            if key in pattern:
                try:
                    return float(pattern[key])
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _near_zone(price: float, zones: list, pips: int, zone_type: str | None) -> bool:
        if price is None:
            return False
        threshold = pips / 10000.0
        for z in zones:
            if zone_type and z.get("zone_type") != zone_type:
                continue
            try:
                level = float(z.get("price_level"))
            except (TypeError, ValueError):
                continue
            if abs(price - level) <= threshold:
                return True
        return False

    @staticmethod
    def _volume_spike(df) -> bool:
        if df is None or not hasattr(df, "tail") or len(df) < 5:
            return False
        if "Volume" not in df.columns:
            return False
        recent = df.tail(20)
        avg = float(recent["Volume"].mean())
        last = float(recent["Volume"].iloc[-1])
        return avg > 0 and last > 2 * avg

    @staticmethod
    def _breaks_strong_zone(last_close: float, zones: list, pattern_type: str) -> bool:
        for z in zones:
            try:
                level = float(z.get("price_level"))
                strength = float(z.get("strength", 0.0))
            except (TypeError, ValueError):
                continue
            if strength < 0.7:
                continue
            if pattern_type == "bullish" and last_close > level + 0.0015:
                return True
            if pattern_type == "bearish" and last_close < level - 0.0015:
                return True
        return False

    @staticmethod
    def _high_impact_news_within(context: SkillContext, minutes: int) -> bool:
        events = context.analysis.get("calendar", []) or []
        if not events:
            return False
        now = datetime.now(UTC)
        for e in events:
            impact = (e.get("impact") if isinstance(e, dict) else getattr(e, "impact", "")) or ""
            if str(impact).lower() != "high":
                continue
            time_val = e.get("time") if isinstance(e, dict) else getattr(e, "time", None)
            if not time_val:
                continue
            event_time = TechnicalAnalysisSkill._parse_event_time(time_val, now)
            if event_time and 0 <= (event_time - now).total_seconds() <= minutes * 60:
                return True
        return False

    @staticmethod
    def _parse_event_time(time_val, now: datetime) -> datetime | None:
        if isinstance(time_val, datetime):
            return time_val
        try:
            return datetime.fromisoformat(str(time_val))
        except ValueError:
            pass
        try:
            parsed = datetime.strptime(str(time_val), "%H:%M")
            return now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
        except ValueError:
            return None

    @staticmethod
    def _in_range_midpoint(pattern_price: float | None, df) -> bool:
        if pattern_price is None or df is None or not hasattr(df, "tail") or len(df) < 20:
            return False
        recent = df.tail(50)
        high = float(recent["High"].max())
        low = float(recent["Low"].min())
        if high <= low:
            return False
        position = (pattern_price - low) / (high - low)
        return 0.4 <= position <= 0.6
    async def _analyze_one(self, df, timeframe, context):
        # Implementation of single timeframe analysis
        pass

    def _has_sufficient_data(self, df) -> bool:
        """Check if we have enough candles for reliable technical analysis."""
        return df is not None and len(df) >= 50
