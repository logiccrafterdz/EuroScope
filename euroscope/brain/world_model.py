"""
World Model — The Agent's Situational Awareness

A structured, always-current representation of everything the agent
knows about EUR/USD. Replaces scattered SkillContext.metadata with
a formal, queryable model that supports delta detection.

Part of the EuroScope Agent Transformation (Phase 1).
"""

import logging
import time
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional, Any

logger = logging.getLogger("euroscope.brain.world_model")


# ── Sub-Models ────────────────────────────────────────────────

@dataclass
class PriceState:
    """Current price action snapshot."""
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread_pips: float = 0.0
    high_today: float = 0.0
    low_today: float = 0.0
    change_pips: float = 0.0
    tick_velocity: float = 0.0       # pips/min — how fast price is moving
    spread_blowout: bool = False
    last_updated: float = 0.0


@dataclass
class TechnicalState:
    """Technical indicator snapshot."""
    rsi: float = 50.0
    macd_histogram: float = 0.0
    macd_signal: float = 0.0
    adx: float = 20.0
    atr: float = 0.0
    atr_avg: float = 0.0
    ema_20: float = 0.0
    ema_50: float = 0.0
    ema_200: float = 0.0
    bb_upper: float = 0.0
    bb_lower: float = 0.0
    bb_bandwidth: float = 0.0
    overall_bias: str = "neutral"    # "bullish", "bearish", "neutral"
    patterns: list = field(default_factory=list)
    support_levels: list = field(default_factory=list)
    resistance_levels: list = field(default_factory=list)
    last_updated: float = 0.0


@dataclass
class FundamentalState:
    """Macro and fundamental landscape."""
    active_theme: str = ""           # e.g. "ECB dovish pivot", "USD strength"
    ecb_rate: float = 0.0
    fed_rate: float = 0.0
    rate_differential: float = 0.0
    rate_bias: str = ""              # "EUR stronger", "USD stronger"
    upcoming_events: list = field(default_factory=list)  # [{name, time, impact}]
    next_high_impact_event: str = ""
    minutes_to_next_event: int = 999
    news_headlines: list = field(default_factory=list)
    last_updated: float = 0.0


@dataclass
class SentimentState:
    """Market sentiment and positioning."""
    news_sentiment: str = "neutral"  # "bullish", "bearish", "neutral"
    news_score: float = 0.0
    cot_net_position: float = 0.0    # COT EUR net speculative
    cot_bias: str = "neutral"
    market_mood: str = "neutral"     # Overall aggregated mood
    last_updated: float = 0.0


@dataclass
class RegimeState:
    """Market regime classification."""
    regime: str = "ranging"          # "trending", "ranging", "breakout"
    regime_strength: float = 0.5     # 0.0 - 1.0
    direction: str = "neutral"       # "bullish", "bearish", "neutral"
    volatility: str = "normal"       # "low", "normal", "high"
    mtf_bias: str = "neutral"        # Higher timeframe bias
    mtf_timeframe: str = "D1"
    regime_history: list = field(default_factory=list)  # last N regime changes
    last_updated: float = 0.0


@dataclass
class SessionState:
    """Trading session context."""
    active_session: str = "off"      # "london", "new_york", "overlap", "asian", "off"
    session_phase: str = "idle"      # "pre_market", "opening", "active", "closing"
    is_high_liquidity: bool = False
    overlap_active: bool = False
    hours_until_close: float = 0.0
    last_updated: float = 0.0


@dataclass
class RiskState:
    """Current risk and portfolio state."""
    open_trades: list = field(default_factory=list)   # [{direction, entry, sl, tp, pnl_pips}]
    open_trade_count: int = 0
    daily_pnl_pips: float = 0.0
    daily_drawdown_pct: float = 0.0
    consecutive_losses: int = 0
    risk_budget_remaining: float = 100.0  # % of daily risk left
    is_trading_allowed: bool = True       # False if drawdown limit hit
    last_updated: float = 0.0


@dataclass
class LiquidityState:
    """Smart money / liquidity concepts."""
    nearest_order_block: Optional[dict] = None
    session_high: float = 0.0
    session_low: float = 0.0
    sweep_detected: bool = False
    liquidity_bias: str = "neutral"
    last_updated: float = 0.0


# ── World Model ──────────────────────────────────────────────

class WorldModel:
    """
    The Agent's complete situational awareness.

    Aggregates all sub-states into a single queryable model.
    Supports delta detection (what changed?) and LLM-ready summaries.
    """

    def __init__(self):
        self.price = PriceState()
        self.technical = TechnicalState()
        self.fundamental = FundamentalState()
        self.sentiment = SentimentState()
        self.regime = RegimeState()
        self.session = SessionState()
        self.risk = RiskState()
        self.liquidity = LiquidityState()

        # Meta
        self._last_snapshot: Optional[dict] = None
        self._update_count: int = 0
        self._created_at: float = time.time()
        self._last_full_update: float = 0.0
        self._cached_summary: Optional[str] = None

    # ── Update Methods ────────────────────────────────────────

    def update_from_pipeline(self, ctx) -> None:
        """
        Sync the world model from a SkillContext produced by
        Orchestrator.run_full_analysis_pipeline().
        """
        self._save_snapshot()
        now = time.time()

        # --- Price ---
        market_data = ctx.market_data or {}
        candles = market_data.get("candles")
        if candles is not None and hasattr(candles, "iloc") and len(candles) > 0:
            last = candles.iloc[-1]
            self.price.price = float(last.get("close", 0))
            self.price.high_today = float(candles["high"].max())
            self.price.low_today = float(candles["low"].min())
            self.price.last_updated = now

        price_data = market_data.get("price_data", {})
        if price_data:
            self.price.price = price_data.get("price", self.price.price)
            self.price.bid = price_data.get("bid", self.price.bid)
            self.price.ask = price_data.get("ask", self.price.ask)
            self.price.spread_pips = price_data.get("spread_pips", self.price.spread_pips)
            self.price.change_pips = price_data.get("change_pips", self.price.change_pips)
            self.price.last_updated = now
            # Hardcoded limit check or from config (though WorldModel doesn't inject config directly here, assume 8.0 normally)
            if self.price.spread_pips > 8.0:
                self.price.spread_blowout = True
            else:
                self.price.spread_blowout = False

        # --- Technical ---
        analysis = ctx.analysis or {}
        indicators_raw = analysis.get("indicators", {})
        indicators = indicators_raw.get("indicators", indicators_raw)

        if indicators:
            rsi_data = indicators.get("RSI", {})
            self.technical.rsi = rsi_data.get("value", self.technical.rsi) if isinstance(rsi_data, dict) else rsi_data

            macd_data = indicators.get("MACD", {})
            if isinstance(macd_data, dict):
                self.technical.macd_histogram = macd_data.get("histogram", self.technical.macd_histogram)
                self.technical.macd_signal = macd_data.get("signal", self.technical.macd_signal)

            adx_data = indicators.get("ADX", {})
            self.technical.adx = adx_data.get("value", self.technical.adx) if isinstance(adx_data, dict) else adx_data

            atr_data = indicators.get("ATR", {})
            if isinstance(atr_data, dict):
                self.technical.atr = atr_data.get("value", self.technical.atr)
                self.technical.atr_avg = atr_data.get("average", self.technical.atr_avg)

            ema_data = indicators.get("EMA", {})
            if isinstance(ema_data, dict):
                self.technical.ema_20 = ema_data.get("EMA_20", self.technical.ema_20)
                self.technical.ema_50 = ema_data.get("EMA_50", self.technical.ema_50)
                self.technical.ema_200 = ema_data.get("EMA_200", self.technical.ema_200)

            bb_data = indicators.get("BB", {})
            if isinstance(bb_data, dict):
                self.technical.bb_upper = bb_data.get("upper", self.technical.bb_upper)
                self.technical.bb_lower = bb_data.get("lower", self.technical.bb_lower)
                self.technical.bb_bandwidth = bb_data.get("bandwidth", self.technical.bb_bandwidth)

            self.technical.overall_bias = indicators_raw.get("overall_bias", self.technical.overall_bias)
            self.technical.last_updated = now

        # Patterns
        patterns = analysis.get("patterns", [])
        if patterns:
            self.technical.patterns = patterns

        # Levels
        levels = analysis.get("levels", {})
        if levels:
            self.technical.support_levels = levels.get("support", self.technical.support_levels)
            self.technical.resistance_levels = levels.get("resistance", self.technical.resistance_levels)

        # --- Fundamental ---
        macro = ctx.metadata.get("macro_data", {})
        if macro:
            differential = macro.get("differential", {})
            self.fundamental.rate_bias = differential.get("bias", self.fundamental.rate_bias)
            self.fundamental.rate_differential = differential.get("value", self.fundamental.rate_differential)

            eu_data = macro.get("eu", {})
            us_data = macro.get("us", {})
            if eu_data.get("interest_rate"):
                self.fundamental.ecb_rate = eu_data["interest_rate"]
            if us_data.get("interest_rate"):
                self.fundamental.fed_rate = us_data["interest_rate"]
            self.fundamental.last_updated = now

        calendar = ctx.metadata.get("calendar_events", [])
        if calendar:
            self.fundamental.upcoming_events = calendar[:5]
            high_impact = [e for e in calendar if e.get("impact") == "high"]
            if high_impact:
                self.fundamental.next_high_impact_event = high_impact[0].get("name", "")
                self.fundamental.minutes_to_next_event = high_impact[0].get("minutes_to_event", 999)

        # --- Regime ---
        self.regime.regime = ctx.metadata.get("regime", self.regime.regime)
        self.regime.volatility = ctx.metadata.get("volatility", self.regime.volatility)
        self.regime.mtf_bias = ctx.metadata.get("mtf_bias", self.regime.mtf_bias)
        self.regime.mtf_timeframe = ctx.metadata.get("mtf_timeframe", self.regime.mtf_timeframe)

        # Direction from signals
        direction = ctx.signals.get("direction", "").lower()
        if direction in ("buy", "bullish"):
            self.regime.direction = "bullish"
        elif direction in ("sell", "bearish"):
            self.regime.direction = "bearish"
        else:
            self.regime.direction = "neutral"

        if ctx.signals.get("regime"):
            self.regime.regime = ctx.signals["regime"]
        self.regime.last_updated = now

        # --- Session ---
        session_regime = ctx.metadata.get("session_regime")
        if session_regime:
            self.session.active_session = session_regime
            self.session.is_high_liquidity = session_regime in ("london", "new_york", "overlap")
            self.session.overlap_active = session_regime == "overlap"
            self.session.last_updated = now

        # --- Liquidity ---
        liquidity_data = ctx.metadata.get("liquidity", {}) or analysis.get("liquidity", {})
        if liquidity_data:
            self.liquidity.sweep_detected = bool(liquidity_data.get("sweep"))
            self.liquidity.nearest_order_block = liquidity_data.get("order_block")
            self.liquidity.session_high = liquidity_data.get("session_high", self.liquidity.session_high)
            self.liquidity.session_low = liquidity_data.get("session_low", self.liquidity.session_low)
            self.liquidity.liquidity_bias = ctx.metadata.get("liquidity_signal", self.liquidity.liquidity_bias)
            self.liquidity.last_updated = now

        # --- Sentiment ---
        sentiment_data = ctx.metadata.get("sentiment_data", {})
        if sentiment_data:
            self.sentiment.news_sentiment = sentiment_data.get("label", self.sentiment.news_sentiment)
            self.sentiment.news_score = sentiment_data.get("score", self.sentiment.news_score)
            self.sentiment.cot_net_position = sentiment_data.get("cot_net", self.sentiment.cot_net_position)
            self.sentiment.market_mood = sentiment_data.get("mood", self.sentiment.market_mood)
            self.sentiment.last_updated = now

        # --- Risk ---
        risk = ctx.risk or {}
        if risk:
            self.risk.is_trading_allowed = risk.get("approved", True)
            self.risk.last_updated = now

        # --- Conflict resolution metadata ---
        final_direction = ctx.metadata.get("final_direction")
        if final_direction:
            self.regime.direction = final_direction.lower()
            confidence = ctx.metadata.get("final_confidence", 0.5)
            self.regime.regime_strength = confidence

        self._update_count += 1
        self._last_full_update = now
        logger.info(
            f"WorldModel updated (#{self._update_count}): "
            f"price={self.price.price:.5f} regime={self.regime.regime} "
            f"bias={self.technical.overall_bias} session={self.session.active_session}"
        )

    def update_price_tick(self, price: float, bid: float = 0, ask: float = 0) -> None:
        """Fast update from a live tick — no pipeline needed."""
        old_price = self.price.price
        now = time.time()

        self.price.price = price
        if bid:
            self.price.bid = bid
        if ask:
            self.price.ask = ask
        if bid and ask:
            self.price.spread_pips = round((ask - bid) * 10000, 1)

        # Calculate tick velocity (pips per minute)
        if old_price and self.price.last_updated:
            dt = now - self.price.last_updated
            if dt > 0:
                dp_pips = abs(price - old_price) * 10000
                self.price.tick_velocity = round(dp_pips / (dt / 60), 2)

        self.price.last_updated = now

    def update_risk_state(self, open_trades: list, daily_pnl: float = 0,
                          consecutive_losses: int = 0) -> None:
        """Update risk state from trade data."""
        self.risk.open_trades = open_trades
        self.risk.open_trade_count = len(open_trades)
        self.risk.daily_pnl_pips = daily_pnl
        self.risk.consecutive_losses = consecutive_losses

        # Calculate floating P&L
        if self.price.price and open_trades:
            for trade in self.risk.open_trades:
                entry = trade.get("entry_price", 0)
                direction = trade.get("direction", "")
                if direction == "BUY":
                    trade["floating_pnl"] = round((self.price.price - entry) * 10000, 1)
                elif direction == "SELL":
                    trade["floating_pnl"] = round((entry - self.price.price) * 10000, 1)

        self.risk.last_updated = time.time()

    # ── Delta Detection ───────────────────────────────────────

    def _save_snapshot(self) -> None:
        """Save current state as snapshot for delta comparison."""
        self._last_snapshot = {
            "price": self.price.price,
            "regime": self.regime.regime,
            "direction": self.regime.direction,
            "bias": self.technical.overall_bias,
            "rsi": self.technical.rsi,
            "adx": self.technical.adx,
            "session": self.session.active_session,
            "open_trades": self.risk.open_trade_count,
            "sweep": self.liquidity.sweep_detected,
        }

    def get_delta(self) -> dict:
        """
        Return what changed since the last update.

        Returns a dict of changed fields with old→new values.
        Critical for the Agent Core to decide if action is needed.
        """
        if not self._last_snapshot:
            return {"initial": True}

        current = {
            "price": self.price.price,
            "regime": self.regime.regime,
            "direction": self.regime.direction,
            "bias": self.technical.overall_bias,
            "rsi": self.technical.rsi,
            "adx": self.technical.adx,
            "session": self.session.active_session,
            "open_trades": self.risk.open_trade_count,
            "sweep": self.liquidity.sweep_detected,
        }

        changes = {}
        for key, new_val in current.items():
            old_val = self._last_snapshot.get(key)
            if old_val != new_val:
                # For floats, only flag if meaningful change
                if isinstance(new_val, float) and isinstance(old_val, float):
                    if key == "price" and abs(new_val - old_val) < 0.00005:
                        continue
                    if key in ("rsi", "adx") and abs(new_val - old_val) < 1.0:
                        continue
                changes[key] = {"old": old_val, "new": new_val}

        return changes

    def has_significant_change(self) -> bool:
        """Check if any actionable change occurred since last snapshot."""
        delta = self.get_delta()
        if not delta or delta.get("initial"):
            return True

        # These are always significant
        significant_keys = {"regime", "direction", "session", "sweep"}
        if significant_keys & delta.keys():
            return True

        # Price move > 10 pips
        if "price" in delta:
            old_p = delta["price"]["old"] or 0
            new_p = delta["price"]["new"] or 0
            if abs(new_p - old_p) * 10000 > 10:
                return True

        # RSI crossing extremes
        if "rsi" in delta:
            old_rsi = delta["rsi"]["old"] or 50
            new_rsi = delta["rsi"]["new"] or 50
            if (old_rsi < 30 <= new_rsi) or (old_rsi > 70 >= new_rsi):
                return True
            if (new_rsi < 30 and old_rsi >= 30) or (new_rsi > 70 and old_rsi <= 70):
                return True

        return False

    # ── LLM-Ready Summary ─────────────────────────────────────

    def get_summary(self) -> str:
        """
        Generate a concise, structured text summary for LLM consumption.

        This is what the Agent Core feeds to the LLM when reasoning.
        """
        delta = self.get_delta()
        # Return cached summary only when delta is truly empty (no changes)
        if self._cached_summary and isinstance(delta, dict) and len(delta) == 0:
            return self._cached_summary

        age = time.time() - self._last_full_update if self._last_full_update else 999

        lines = [
            "=== WORLD MODEL STATE ===",
            f"Last updated: {age:.0f}s ago | Updates: {self._update_count}",
            "",
            "📊 PRICE",
            f"  EUR/USD: {self.price.price:.5f} | Spread: {self.price.spread_pips:.1f} pips",
            f"  Today Range: {self.price.low_today:.5f} — {self.price.high_today:.5f}",
            f"  Change: {self.price.change_pips:+.1f} pips | Velocity: {self.price.tick_velocity:.1f} pips/min",
            "",
            "📈 TECHNICAL",
            f"  Bias: {self.technical.overall_bias.upper()} | RSI: {self.technical.rsi:.1f} | ADX: {self.technical.adx:.1f}",
            f"  MACD Hist: {self.technical.macd_histogram:.5f}",
            f"  EMA20: {self.technical.ema_20:.5f} | EMA50: {self.technical.ema_50:.5f}",
            f"  BB: [{self.technical.bb_lower:.5f} — {self.technical.bb_upper:.5f}] Width: {self.technical.bb_bandwidth:.4f}",
            f"  S/R: Support {self.technical.support_levels[:3]} | Resistance {self.technical.resistance_levels[:3]}",
            f"  Patterns: {[p.get('name', '?') for p in self.technical.patterns[:3]]}",
            "",
            "🌍 FUNDAMENTAL",
            f"  Theme: {self.fundamental.active_theme or 'None active'}",
            f"  Rates: ECB {self.fundamental.ecb_rate}% | Fed {self.fundamental.fed_rate}% | Diff: {self.fundamental.rate_differential}",
            f"  Next Event: {self.fundamental.next_high_impact_event} ({self.fundamental.minutes_to_next_event}min)",
            "",
            "🧭 REGIME",
            f"  Market: {self.regime.regime.upper()} (strength: {self.regime.regime_strength:.0%})",
            f"  Direction: {self.regime.direction.upper()} | Volatility: {self.regime.volatility}",
            f"  MTF Bias ({self.regime.mtf_timeframe}): {self.regime.mtf_bias}",
            "",
            "🏦 SESSION",
            f"  Active: {self.session.active_session} | Liquidity: {'HIGH' if self.session.is_high_liquidity else 'LOW'}",
            f"  Overlap: {'YES' if self.session.overlap_active else 'NO'}",
            "",
            "💧 LIQUIDITY",
            f"  Sweep: {'⚡ DETECTED' if self.liquidity.sweep_detected else 'None'}",
            f"  Bias: {self.liquidity.liquidity_bias}",
            "",
            "💬 SENTIMENT",
            f"  News: {self.sentiment.news_sentiment.upper()} (score: {self.sentiment.news_score:.2f})",
            f"  Market Mood: {self.sentiment.market_mood.upper()}",
            f"  COT Net: {self.sentiment.cot_net_position:.0f} | Bias: {self.sentiment.cot_bias}",
            "",
            "🛡️ RISK",
            f"  Open Trades: {self.risk.open_trade_count} | Daily P&L: {self.risk.daily_pnl_pips:+.1f} pips",
            f"  Consecutive Losses: {self.risk.consecutive_losses}",
            f"  Trading Allowed: {'YES' if self.risk.is_trading_allowed else '🛑 NO'}",
        ]

        summary = "\n".join(lines)
        self._cached_summary = summary
        return summary

    def get_compact_summary(self) -> str:
        """Ultra-short summary for quick agent decisions."""
        return (
            f"EUR/USD {self.price.price:.5f} | {self.regime.regime}/{self.regime.direction} "
            f"| RSI:{self.technical.rsi:.0f} ADX:{self.technical.adx:.0f} "
            f"| {self.session.active_session} | Trades:{self.risk.open_trade_count} "
            f"| PnL:{self.risk.daily_pnl_pips:+.1f}"
        )

    # ── Persistence ───────────────────────────────────────────

    def serialize(self) -> dict:
        """Serialize the world model for storage."""
        return {
            "price": asdict(self.price),
            "technical": {
                k: v for k, v in asdict(self.technical).items()
                if k not in ("patterns",)  # patterns can be large
            },
            "fundamental": asdict(self.fundamental),
            "sentiment": asdict(self.sentiment),
            "regime": asdict(self.regime),
            "session": asdict(self.session),
            "risk": asdict(self.risk),
            "liquidity": asdict(self.liquidity),
            "_meta": {
                "update_count": self._update_count,
                "last_full_update": self._last_full_update,
                "serialized_at": datetime.now(UTC).isoformat(),
            }
        }

    def deserialize(self, data: dict) -> None:
        """Restore the world model from stored data with type validation."""
        if not data:
            return

        def _update_dataclass(dc, values: dict):
            for key, val in values.items():
                if hasattr(dc, key):
                    # Basic type coercion based on dataclass hints
                    expected_type = dc.__annotations__.get(key)
                    if expected_type and val is not None:
                        try:
                            # Handle simple types
                            if expected_type == float:
                                val = float(val)
                            elif expected_type == int:
                                val = int(val)
                            elif expected_type == str:
                                val = str(val)
                            elif expected_type == bool:
                                val = bool(val)
                        except (ValueError, TypeError):
                            logger.warning(f"Type mismatch restoring {key} in {dc.__class__.__name__}: expected {expected_type}, got {type(val)}")
                            continue  # Skip corrupted field
                    setattr(dc, key, val)

        for section, obj in [
            ("price", self.price),
            ("technical", self.technical),
            ("fundamental", self.fundamental),
            ("sentiment", self.sentiment),
            ("regime", self.regime),
            ("session", self.session),
            ("risk", self.risk),
            ("liquidity", self.liquidity),
        ]:
            section_data = data.get(section, {})
            if section_data:
                _update_dataclass(obj, section_data)

        meta = data.get("_meta", {})
        self._update_count = meta.get("update_count", 0)
        self._last_full_update = meta.get("last_full_update", 0)

        logger.info(f"WorldModel restored: {self._update_count} prior updates")

    # ── Query Methods ─────────────────────────────────────────

    def is_stale(self, max_age_seconds: int = 300) -> bool:
        """Check if the world model needs a fresh update."""
        if not self._last_full_update:
            return True
        return (time.time() - self._last_full_update) > max_age_seconds

    def is_high_volatility(self) -> bool:
        """Quick check: is the market volatile right now?"""
        return self.regime.volatility == "high"

    def is_trending(self) -> bool:
        """Quick check: is the market trending?"""
        return self.regime.regime == "trending" and self.technical.adx > 25

    def has_open_trades(self) -> bool:
        """Quick check: any open positions?"""
        return self.risk.open_trade_count > 0

    def is_near_event(self, minutes_threshold: int = 30) -> bool:
        """Quick check: is a high-impact event imminent?"""
        return self.fundamental.minutes_to_next_event < minutes_threshold

    def __repr__(self) -> str:
        return (
            f"<WorldModel price={self.price.price:.5f} "
            f"regime={self.regime.regime} bias={self.technical.overall_bias} "
            f"session={self.session.active_session} "
            f"updates={self._update_count}>"
        )
