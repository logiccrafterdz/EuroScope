"""
Strategy Engine — Market Regime Detection

Identifies the current market regime and recommends the best
trading strategy: Trend Following, Mean Reversion, or Breakout.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("euroscope.trading.strategy_engine")


@dataclass
class RegimeInfo:
    """Market regime classification with strength and evidence."""
    regime: str          # "trending", "ranging", "breakout"
    strength: float      # 0.0 - 1.0 (confidence in the classification)
    direction: str       # "bullish", "bearish", "neutral"
    details: dict = field(default_factory=dict)  # supporting evidence


@dataclass
class StrategySignal:
    """Strategy recommendation with entry/exit rules."""
    strategy: str                    # "trend_following", "mean_reversion", "breakout"
    direction: str                   # "BUY", "SELL", "WAIT"
    confidence: float                # 0-100
    entry_rules: list[str] = field(default_factory=list)
    exit_rules: list[str] = field(default_factory=list)
    reasoning: str = ""
    regime: str = ""                 # "trending", "ranging", "breakout"
    regime_strength: float = 0.0     # 0.0 - 1.0


class StrategyEngine:
    """
    Detects market regime and recommends the optimal strategy.

    Strategies:
    - Trend Following: ride established trends with EMAs + ADX
    - Mean Reversion: fade extremes at key levels
    - Breakout: trade level breaks with momentum
    """

    def __init__(self):
        self._tuning_params = self._load_params()
        
    def _load_params(self) -> dict:
        import json
        import os
        defaults = {
            "rsi_oversold": 30.0,
            "rsi_overbought": 70.0,
            "adx_threshold": 25.0,
            "confidence_threshold": 60.0,
        }
        tuning_file = "data/tuning.json"
        if os.path.exists(tuning_file):
            try:
                with open(tuning_file, "r") as f:
                    defaults.update(json.load(f))
            except Exception as e:
                logger.error(f"StrategyEngine failed to load {tuning_file}: {e}")
        return defaults

    def detect_strategy(self, indicators: dict, levels: dict,
                        patterns: list = None, uncertainty: Optional[dict] = None,
                        macro_data: Optional[dict] = None,
                        user_prefs: Optional[dict] = None,
                        session: Optional[str] = None) -> StrategySignal:
        """
        Analyze market conditions and recommend a strategy.

        Args:
            indicators: Technical indicator data (RSI, MACD, EMA, ADX, BB, ATR, zscore)
            levels: {"current_price", "support", "resistance"}
            patterns: Detected chart patterns
            uncertainty: Uncertainty data
            macro_data: Macroeconomic data
            user_prefs: Dynamically tuned parameters from tuning.json
            session: Trading session ("asian", "london", "overlap", "newyork",
                     "closing", "weekend", "holiday", "unknown")

        Returns:
            StrategySignal with recommended action
        """
        if user_prefs:
            self._tuning_params.update(user_prefs)
        regime_info = self._detect_regime(indicators)
        patterns = patterns or []
        if regime_info.regime not in ("breakout", "volatile") and self._has_breakout_trigger(indicators, levels):
            regime_info = RegimeInfo(
                regime="breakout",
                strength=max(regime_info.strength, 0.6),
                direction=regime_info.direction,
                details=regime_info.details,
            )

        if regime_info.regime == "trending":
            sig = self._trend_following(indicators, levels, patterns)
        elif regime_info.regime == "breakout":
            sig = self._breakout_strategy(indicators, levels, patterns)
        elif regime_info.regime == "volatile":
            sig = self._volatile_defensive(indicators, levels)
        else:
            sig = self._mean_reversion(indicators, levels, patterns)

        # Attach regime metadata to signal
        sig.regime_strength = regime_info.strength
        if regime_info.strength < 0.4:
            sig.confidence *= 0.85  # Lower confidence in ambiguous regimes

        # Session-aware gating (institutional: trade the right hours)
        sig = self._apply_session_gating(sig, session)

        if uncertainty:
            sig = self._apply_uncertainty(sig, uncertainty, macro_data or {})

        return sig

    _NO_TRADE_SESSIONS = {"closing", "weekend", "holiday"}
    _SESSION_MULTIPLIERS = {
        "asian": 0.90,
        "london": 1.00,
        "overlap": 1.05,
        "newyork": 1.00,
    }

    def _apply_session_gating(self, sig: StrategySignal, session: Optional[str]) -> StrategySignal:
        """Gate signals by session: no-trade sessions block, quiet sessions penalize."""
        if not session:
            return sig

        if session in self._NO_TRADE_SESSIONS:
            return StrategySignal(
                strategy=sig.strategy,
                direction="WAIT",
                confidence=0,
                entry_rules=[],
                exit_rules=sig.exit_rules,
                reasoning=f"{sig.reasoning} | Session '{session}' closed for trading",
                regime=sig.regime,
                regime_strength=sig.regime_strength,
            )

        multiplier = self._SESSION_MULTIPLIERS.get(session, 1.0)
        if sig.direction in ("BUY", "SELL"):
            # Breakout needs a live session; fade trades (MR) thrive in overlap/London
            if sig.strategy == "breakout" and session == "asian":
                sig.confidence = min(95, sig.confidence * 0.7)
                sig.reasoning += f" | Breakout penalized in {session} session"
            sig.confidence = min(95, sig.confidence * multiplier)

        return sig

    def _apply_uncertainty(self, sig: StrategySignal, uncertainty: dict, macro_data: dict) -> StrategySignal:
        confidence_adjustment = uncertainty.get("confidence_adjustment", 1.0)
        try:
            confidence_adjustment = float(confidence_adjustment)
        except (TypeError, ValueError):
            confidence_adjustment = 1.0

        sig.confidence = min(95, max(0, sig.confidence * confidence_adjustment))

        if uncertainty.get("high_uncertainty"):
            if not self._macro_confirmation(sig.direction, macro_data):
                return StrategySignal(
                    strategy="uncertain",
                    direction="WAIT",
                    confidence=0,
                    entry_rules=[],
                    exit_rules=[],
                    reasoning="High uncertainty without macro confirmation",
                    regime=sig.regime or "ranging",
                )

        return sig

    @staticmethod
    def _macro_confirmation(direction: str, macro_data: dict) -> bool:
        if direction not in ("BUY", "SELL"):
            return True
        differential = macro_data.get("differential", {}) if macro_data else {}
        bias = differential.get("bias") or differential.get("interpretation")
        if not bias:
            return False
        bias_text = str(bias).lower()
        if direction == "BUY" and ("eur stronger" in bias_text or "usd weaker" in bias_text):
            return True
        if direction == "SELL" and ("usd stronger" in bias_text or "eur weaker" in bias_text):
            return True
        return False

    def _has_breakout_trigger(self, indicators: dict, levels: dict) -> bool:
        current_price = levels.get("current_price")
        support = levels.get("support", [])
        resistance = levels.get("resistance", [])
        if not current_price:
            return False
        hist = self._macd_histogram(indicators.get("macd"))
        above_resistance = bool(resistance) and current_price > resistance[0]
        below_support = bool(support) and current_price < support[0]
        if above_resistance and (hist is None or hist > 0):
            return True
        if below_support and (hist is None or hist < 0):
            return True
        return False

    @staticmethod
    def _macd_histogram(macd) -> Optional[float]:
        """Extract the MACD histogram value, tolerant of both key conventions."""
        if not isinstance(macd, dict):
            return None
        hist = macd.get("histogram_latest")
        if hist is None:
            hist = macd.get("histogram")
        return hist

    def _detect_regime(self, indicators: dict) -> RegimeInfo:
        """
        Determine market regime using RegimeAdaptiveEngine as the single source of truth.
        """
        if not hasattr(self, '_regime_engine'):
            from .regime_adaptive import RegimeAdaptiveEngine
            self._regime_engine = RegimeAdaptiveEngine()
            
        # Map StrategyEngine indicators to the format expected by RegimeAdaptiveEngine
        bb = indicators.get("bollinger", {})
        raw_atr = indicators.get("atr", 0)
        atr_val = raw_atr.get("value") if isinstance(raw_atr, dict) else raw_atr
        atr_avg = raw_atr.get("sma") if isinstance(raw_atr, dict) else indicators.get("atr_avg")
        mapped_inds = {
            "ADX": {"value": indicators.get("adx", 20)},
            "ATR": {"value": atr_val or 0, "average": atr_avg or 0},
            "BB": {
                "upper": bb.get("upper", 0),
                "lower": bb.get("lower", 0),
                "current_price": bb.get("current_price") or indicators.get("price", 0),
            }
        }
        
        # Calculate bandwidth if possible
        if mapped_inds["BB"]["upper"] and mapped_inds["BB"]["lower"] and mapped_inds["BB"]["current_price"]:
            width = (mapped_inds["BB"]["upper"] - mapped_inds["BB"]["lower"]) / mapped_inds["BB"]["current_price"] * 100
            mapped_inds["BB"]["bandwidth"] = width
            
        regime_name = self._regime_engine.detect_regime(mapped_inds)
        rsi = indicators.get("rsi", 50)
        bb_bandwidth = mapped_inds.get("BB", {}).get("bandwidth", 0)
        bb_upper = bb.get("upper", 0)
        bb_lower = bb.get("lower", 0)
        bb_price = bb.get("current_price", 0)
        rsi_extreme = rsi >= 75 or rsi <= 25
        outside_band = (bb_upper and bb_price and bb_price > bb_upper) or (bb_lower and bb_price and bb_price < bb_lower)
        if regime_name == "ranging" and rsi_extreme and (outside_band or (bb_bandwidth and bb_bandwidth <= 0.08)):
            regime_name = "breakout"
        if regime_name == "volatile" and rsi_extreme and outside_band:
            regime_name = "breakout"
        
        # Determine direction
        overall_bias = str(indicators.get("overall_bias", "neutral")).lower()
        ema_data = indicators.get("ema")
        ema_20 = indicators.get("ema_20")
        ema_50 = indicators.get("ema_50")
        if ema_20 is None and isinstance(ema_data, dict):
            ema_20 = ema_data.get("ema20")
        if ema_50 is None and isinstance(ema_data, dict):
            ema_50 = ema_data.get("ema50")
        
        if overall_bias == "bullish" or (ema_20 and ema_50 and ema_20 > ema_50):
            direction = "bullish"
        elif overall_bias == "bearish" or (ema_20 and ema_50 and ema_20 < ema_50):
            direction = "bearish"
        else:
            direction = "neutral"
            
        # Strength: confidence in the regime classification, strategy-appropriate
        adx = indicators.get("adx", 20)
        if regime_name == "trending":
            strength = min(1.0, max(0.4, adx / 50.0))
        elif regime_name == "breakout":
            strength = max(0.6, min(1.0, 0.5 + adx / 100.0))
        elif regime_name == "volatile":
            strength = 0.5
        else:
            # Ranging strength reflects how stretched price is (reversion potential)
            zscore = indicators.get("zscore")
            z_abs = abs(zscore) if isinstance(zscore, (int, float)) else 0.0
            stretch = max(abs(rsi - 50) / 50.0, min(1.0, z_abs / 2.0))
            strength = min(0.8, 0.35 + stretch * 0.9)
        
        logger.debug(f"Regime detection via RegimeAdaptiveEngine: {regime_name} (strength={strength:.2f})")
        
        return RegimeInfo(
            regime=regime_name,
            strength=strength,
            direction=direction,
            details={"source": "RegimeAdaptiveEngine"}
        )

    # ─── Volatile (Defensive) ────────────────────────────────

    def _volatile_defensive(self, indicators: dict, levels: dict) -> StrategySignal:
        """
        Defensive posture during volatility spikes.

        Fading extremes in a volatile market is dangerous. We stand aside
        unless a strong trend (ADX >= 30) is present — then we ride it with
        reduced confidence.
        """
        adx = indicators.get("adx", 0)
        reasoning = "Elevated volatility — standing aside (defensive)"
        if adx and adx >= 30:
            sig = self._trend_following(indicators, levels, [])
            sig.confidence = min(60.0, sig.confidence * 0.7)
            sig.reasoning += " | Volatile regime: reduced confidence"
            sig.regime = "volatile"
            return sig

        return StrategySignal(
            strategy="volatile_defensive",
            direction="WAIT",
            confidence=15.0,
            entry_rules=[],
            exit_rules=["Stand aside until volatility normalizes (ATR ratio < 1.5)"],
            reasoning=reasoning,
            regime="volatile",
        )

    # ─── Trend Following ─────────────────────────────────────

    def _trend_following(self, indicators: dict, levels: dict,
                         patterns: list) -> StrategySignal:
        """
        Trend Following strategy — ride the trend with Market Structure & Momentum.

        Entry: Break of Structure (BOS) / Moving Average alignment + pullback
               (not chasing extended price) + ADX confirmation.
        Exit: CHoCH (Change of Character) or trailing stop.
        """
        bias = str(indicators.get("overall_bias", "neutral")).lower()
        adx = indicators.get("adx", 0)
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", {})
        zscore = indicators.get("zscore")

        confidence = 40.0
        entry_rules = []
        exit_rules = []
        direction = "WAIT"

        # Determine direction using Market Structure / EMAs
        if bias == "bullish":
            direction = "BUY"
            entry_rules.append("Market Structure: Bullish (BOS detected / Price > EMA 50)")
            confidence += 15
        elif bias == "bearish":
            direction = "SELL"
            entry_rules.append("Market Structure: Bearish (BOS detected / Price < EMA 50)")
            confidence += 15

        # Volume/Volatility Expansion Confirmation (ATR proxy instead of pseudo-volume)
        atr_data = indicators.get("atr", {})
        current_atr = atr_data.get("current") or atr_data.get("value", 0) if isinstance(atr_data, dict) else 0
        avg_atr = atr_data.get("avg_14") or atr_data.get("sma", 1) if isinstance(atr_data, dict) else 1

        if current_atr and avg_atr and avg_atr > 0:
            if current_atr / avg_atr > 1.25:
                entry_rules.append("ATR Expansion: High momentum supports trend")
                confidence += 10
            elif current_atr / avg_atr < 0.75:
                entry_rules.append("ATR Compression: Low volatility, risk of fake-out")
                confidence -= 5

        # ADX confirmation
        adx_thresh = self._tuning_params.get("adx_threshold", 25.0)
        if adx > adx_thresh + 5:
            entry_rules.append(f"ADX strong ({adx:.0f} > {adx_thresh+5})")
            confidence += 15
        elif adx > adx_thresh:
            entry_rules.append(f"ADX moderate ({adx:.0f} > {adx_thresh})")
            confidence += 8

        # MACD alignment
        hist = self._macd_histogram(macd)
        if hist is not None:
            if (direction == "BUY" and hist > 0) or (direction == "SELL" and hist < 0):
                entry_rules.append("MACD histogram confirms direction")
                confidence += 10

        # RSI not extreme (trend has room)
        if 35 < rsi < 65:
            entry_rules.append(f"RSI has room to move ({rsi:.0f})")
            confidence += 5

        # Pullback / no-chase filter (institutional: buy strength on the dip)
        if direction in ("BUY", "SELL") and isinstance(zscore, (int, float)):
            overextended = (direction == "BUY" and zscore > 2.0) or (direction == "SELL" and zscore < -2.0)
            pullback_zone = (direction == "BUY" and -0.5 <= zscore <= 1.5) or (direction == "SELL" and -1.5 <= zscore <= 0.5)
            if overextended:
                entry_rules.append(f"Z-score {zscore:+.2f}: overextended — avoid chasing")
                confidence -= 20
            elif pullback_zone:
                entry_rules.append(f"Z-score {zscore:+.2f}: healthy pullback zone")
                confidence += 10

        # Bullish patterns in uptrend
        for p in patterns:
            if p.get("bias") == bias:
                entry_rules.append(f"Pattern confirms: {p.get('name', 'unknown')}")
                confidence += 8

        exit_rules = [
            "Trailing stop: 1.5× ATR below/above entry",
            "Change of Character (CHoCH): Price breaks swing point against direction",
            "ADX drops below 20 (trend weakening)",
        ]

        return StrategySignal(
            strategy="trend_following",
            direction=direction,
            confidence=min(confidence, 95),
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            reasoning=f"Market in strong trend (ADX: {adx:.0f}), bias: {bias}",
            regime="trending",
        )

    # ─── Mean Reversion ──────────────────────────────────────

    def _mean_reversion(self, indicators: dict, levels: dict,
                        patterns: list) -> StrategySignal:
        """
        Mean Reversion — fade statistical extremes at key levels.

        Institutional entry rules:
          - Statistical stretch: RSI extreme AND/OR z-score >= 1.25 (std devs)
          - Price at/through a Bollinger band (deviation from mean)
          - No strong trend (ADX < 25) — never fade an established trend
          - Preferably at support (long) / resistance (short)

        Exit: price returns to the mean (mid-band / RSI 45-55), time-stop
              (3× reversion half-life), or stop beyond the extreme.
        """
        rsi = indicators.get("rsi", 50)
        bb = indicators.get("bollinger", {})
        zscore = indicators.get("zscore")
        adx = indicators.get("adx", 20)
        current_price = levels.get("current_price", 0)
        support = levels.get("support", [])
        resistance = levels.get("resistance", [])

        confidence = 35.0
        entry_rules = []
        direction = "WAIT"

        rsi_os = self._tuning_params.get("rsi_oversold", 30.0)
        rsi_ob = self._tuning_params.get("rsi_overbought", 70.0)

        # ── Trend filter: never fade a strong trend ──
        if adx and adx >= 25:
            return StrategySignal(
                strategy="mean_reversion",
                direction="WAIT",
                confidence=20.0,
                entry_rules=["Trend filter: ADX >= 25 — do not fade the trend"],
                exit_rules=[
                    "Price returns to middle Bollinger Band (mean)",
                    "RSI returns to 45-55 range",
                    "Stop loss: below nearest support / above nearest resistance",
                ],
                reasoning=f"Ranging regime but ADX {adx:.0f} >= 25 — mean reversion suppressed (no trend fading)",
                regime="ranging",
            )

        z_abs = abs(zscore) if isinstance(zscore, (int, float)) else 0.0
        rsi_buy = rsi < rsi_os
        rsi_sell = rsi > rsi_ob
        z_buy = isinstance(zscore, (int, float)) and zscore <= -1.25
        z_sell = isinstance(zscore, (int, float)) and zscore >= 1.25

        # ── Oversold → BUY ──
        if rsi_buy or z_buy:
            direction = "BUY"
            entry_rules.append(f"Stretch: RSI {rsi:.0f} < {rsi_os}" if rsi_buy else f"Stretch: z-score {zscore:+.2f} <= -1.25")
            confidence += 15

            if rsi_buy and z_buy:
                entry_rules.append("Double confirmation: RSI + z-score")
                confidence += 8
            if z_abs >= 2.0:
                entry_rules.append(f"Deep z-score {zscore:+.2f}: strong reversion potential")
                confidence += 10
            elif z_abs >= 1.5:
                entry_rules.append(f"z-score {zscore:+.2f} beyond 1.5σ")
                confidence += 5

            if support and current_price:
                nearest_s = support[0]
                dist_pips = (current_price - nearest_s) * 10000
                if dist_pips < 20:
                    entry_rules.append(f"Near support {nearest_s} ({dist_pips:.0f} pips)")
                    confidence += 15

            bb_lower = bb.get("lower")
            if bb_lower and current_price and current_price <= bb_lower * 1.001:
                entry_rules.append("Price at/below lower Bollinger Band")
                confidence += 10

        # ── Overbought → SELL ──
        elif rsi_sell or z_sell:
            direction = "SELL"
            entry_rules.append(f"Stretch: RSI {rsi:.0f} > {rsi_ob}" if rsi_sell else f"Stretch: z-score {zscore:+.2f} >= 1.25")
            confidence += 15

            if rsi_sell and z_sell:
                entry_rules.append("Double confirmation: RSI + z-score")
                confidence += 8
            if z_abs >= 2.0:
                entry_rules.append(f"Deep z-score {zscore:+.2f}: strong reversion potential")
                confidence += 10
            elif z_abs >= 1.5:
                entry_rules.append(f"z-score {zscore:+.2f} beyond 1.5σ")
                confidence += 5

            if resistance and current_price:
                nearest_r = resistance[0]
                dist_pips = (nearest_r - current_price) * 10000
                if dist_pips < 20:
                    entry_rules.append(f"Near resistance {nearest_r} ({dist_pips:.0f} pips)")
                    confidence += 15

            bb_upper = bb.get("upper")
            if bb_upper and current_price and current_price >= bb_upper * 0.999:
                entry_rules.append("Price at/above upper Bollinger Band")
                confidence += 10

        # ── Volatility sanity: don't fade in a dead market ──
        bb_upper = bb.get("upper")
        bb_lower = bb.get("lower")
        bb_mid = bb.get("middle")
        if bb_upper and bb_lower and bb_mid and bb_mid > 0:
            bandwidth = (bb_upper - bb_lower) / bb_mid
            if 0 < bandwidth < 0.0012:
                entry_rules.append("Narrow bands: low reversion energy")
                confidence -= 8

        # Reversal patterns
        for p in patterns:
            p_bias = p.get("bias", "")
            if direction == "BUY" and p_bias == "bullish":
                entry_rules.append(f"Reversal pattern: {p.get('name', 'unknown')}")
                confidence += 10
            elif direction == "SELL" and p_bias == "bearish":
                entry_rules.append(f"Reversal pattern: {p.get('name', 'unknown')}")
                confidence += 10

        exit_rules = [
            "Price returns to middle Bollinger Band (the mean)",
            "RSI returns to 45-55 range",
            "Time stop: exit if no reversion within ~3× half-life (≈ 18-24 bars)",
            "Stop loss: below nearest support / above nearest resistance",
        ]

        z_str = f"{zscore:+.2f}" if isinstance(zscore, (int, float)) else "n/a"
        return StrategySignal(
            strategy="mean_reversion",
            direction=direction,
            confidence=min(confidence, 90),
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            reasoning=f"Ranging market, RSI at {rsi:.0f}, z-score {z_str} — fading the extreme",
            regime="ranging",
        )

    # ─── Breakout ────────────────────────────────────────────

    def _breakout_strategy(self, indicators: dict, levels: dict,
                           patterns: list) -> StrategySignal:
        """
        Breakout — trade level breaks with momentum.

        Entry: Price breaks S/R with RSI/MACD confirmation
        Exit: Opposite level hit or momentum fades
        """
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", {})
        current_price = levels.get("current_price", 0)
        support = levels.get("support", [])
        resistance = levels.get("resistance", [])

        confidence = 35.0
        entry_rules = []
        direction = "WAIT"

        # Breakout above resistance
        if resistance and current_price:
            nearest_r = resistance[0]
            if current_price > nearest_r:
                direction = "BUY"
                entry_rules.append(f"Price broke above resistance {nearest_r}")
                confidence += 20

                # Momentum & Volatility confirmation
                hist = self._macd_histogram(macd)
                atr_data = indicators.get("atr", {})
                current_atr = atr_data.get("current") or atr_data.get("value", 0) if isinstance(atr_data, dict) else 0
                avg_atr = atr_data.get("avg_14") or atr_data.get("sma", 1) if isinstance(atr_data, dict) else 1

                if hist and hist > 0:
                    entry_rules.append("MACD momentum confirms breakout")
                    confidence += 10

                if current_atr and avg_atr and avg_atr > 0 and current_atr / avg_atr > 1.25:
                    entry_rules.append("ATR Expansion validates breakout momentum")
                    confidence += 15

                if rsi > 50:
                    entry_rules.append(f"RSI bullish ({rsi:.0f})")
                    confidence += 5

                tick_vol = indicators.get("tick_volume_5m", 0)
                if tick_vol > 60:
                    entry_rules.append(f"Strong tick momentum validates breakout ({tick_vol} ticks/5m)")
                    confidence += 15

        # Breakdown below support
        if direction == "WAIT" and support and current_price:
            nearest_s = support[0]
            if current_price < nearest_s:
                direction = "SELL"
                entry_rules.append(f"Price broke below support {nearest_s}")
                confidence += 20

                hist = self._macd_histogram(macd)
                atr_data = indicators.get("atr", {})
                current_atr = atr_data.get("current") or atr_data.get("value", 0) if isinstance(atr_data, dict) else 0
                avg_atr = atr_data.get("avg_14") or atr_data.get("sma", 1) if isinstance(atr_data, dict) else 1

                if hist and hist < 0:
                    entry_rules.append("MACD momentum confirms breakdown")
                    confidence += 10

                if current_atr and avg_atr and avg_atr > 0 and current_atr / avg_atr > 1.25:
                    entry_rules.append("ATR Expansion validates breakdown momentum")
                    confidence += 15

                if rsi < 50:
                    entry_rules.append(f"RSI bearish ({rsi:.0f})")
                    confidence += 5
                    
                tick_vol = indicators.get("tick_volume_5m", 0)
                if tick_vol > 60:
                    entry_rules.append(f"Strong tick momentum validates breakdown ({tick_vol} ticks/5m)")
                    confidence += 15

        # Breakout patterns
        for p in patterns:
            if "breakout" in p.get("name", "").lower():
                entry_rules.append(f"Pattern: {p.get('name')}")
                confidence += 10

        exit_rules = [
            "Next major S/R level as target",
            "Stop loss: back below/above broken level + 5 pip buffer",
            "Trail stop after 20+ pip move in favor",
        ]

        return StrategySignal(
            strategy="breakout",
            direction=direction,
            confidence=min(confidence, 90),
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            reasoning="Potential breakout detected at key level",
            regime="breakout",
        )

    # ─── Formatting ──────────────────────────────────────────

    def format_strategy(self, sig: StrategySignal) -> str:
        """Format strategy signal for Telegram display."""
        strategy_names = {
            "trend_following": "📈 Trend Following",
            "mean_reversion": "🔄 Mean Reversion",
            "breakout": "💥 Breakout",
        }

        dir_icon = "🟢" if sig.direction == "BUY" else "🔴" if sig.direction == "SELL" else "⚪"
        strat_name = strategy_names.get(sig.strategy, sig.strategy)

        lines = [
            "🧠 *Strategy Recommendation*\n",
            f"📊 Regime: *{sig.regime.title()}*",
            f"🎯 Strategy: *{strat_name}*",
            f"{dir_icon} Direction: *{sig.direction}* ({sig.confidence:.0f}% confidence)\n",
        ]

        if sig.entry_rules:
            lines.append("✅ *Entry Rules:*")
            for rule in sig.entry_rules:
                lines.append(f"  • {rule}")

        if sig.exit_rules:
            lines.append("\n🚪 *Exit Rules:*")
            for rule in sig.exit_rules:
                lines.append(f"  • {rule}")

        return "\n".join(lines)
