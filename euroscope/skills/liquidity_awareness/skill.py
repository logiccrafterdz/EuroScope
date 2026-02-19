import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import numpy as np
import pandas as pd

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult

logger = logging.getLogger("euroscope.skills.liquidity_awareness")


class LiquidityZoneType(str, Enum):
    SESSION_HIGH = "session_high"
    SESSION_LOW = "session_low"
    PSYCHOLOGICAL = "psychological"
    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"
    ORDER_BLOCK = "order_block"


@dataclass
class LiquidityZone:
    price_level: float
    zone_type: str
    strength: float
    session: str


class LiquidityAwarenessSkill(BaseSkill):
    name = "liquidity_awareness"
    description = "Detects liquidity zones and infers market intent for downstream skills"
    emoji = "💧"
    category = SkillCategory.ANALYSIS
    version = "1.0.0"
    capabilities = ["analyze"]

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action != "analyze":
            return SkillResult(success=False, error=f"Unknown action: {action}")
        try:
            df = params.get("df", context.market_data.get("candles"))
            session_regime = context.metadata.get("session_regime", "unknown")
            zones, intent = self._run(df, session_regime)
            context.metadata["liquidity_zones"] = zones
            context.metadata["market_intent"] = intent
            context.metadata["liquidity_aware"] = True
            context.metadata["liquidity_signal"] = self._intent_to_signal(intent)
            return SkillResult(success=True, data={"liquidity_zones": zones, "market_intent": intent})
        except Exception as e:
            logger.warning(f"LiquidityAwarenessSkill failed: {e}")
            context.metadata["liquidity_zones"] = []
            context.metadata["market_intent"] = self._neutral_intent()
            context.metadata["liquidity_aware"] = True
            context.metadata["liquidity_signal"] = "NEUTRAL"
            return SkillResult(success=True, data={"liquidity_zones": [], "market_intent": self._neutral_intent()})

    def _run(self, df, session_regime: str) -> tuple[list[dict], dict]:
        if df is None or (hasattr(df, "empty") and df.empty) or len(df) < 20:
            return [], self._neutral_intent()
        df = self._normalize_df(df).tail(50)
        if len(df) < 20:
            return [], self._neutral_intent()
        zones = self._detect_liquidity_zones(df, session_regime)
        intent = self._assess_market_intent(df, zones, session_regime)
        return zones, intent

    def _intent_to_signal(self, intent: dict) -> str:
        move = (intent.get("next_likely_move") or intent.get("direction") or intent.get("bias") or "")
        move = str(move).strip().lower()
        if "up" in move or "bull" in move or "buy" in move or "long" in move:
            return "BUY"
        if "down" in move or "bear" in move or "sell" in move or "short" in move:
            return "SELL"
        return "NEUTRAL"

    def _normalize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)
        rename_map = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
        df = df.rename(columns=rename_map)
        if "datetime" in df.columns:
            df = df.set_index(pd.to_datetime(df["datetime"]))
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)
        return df

    def _detect_liquidity_zones(self, df: pd.DataFrame, session_regime: str) -> list[dict]:
        zones: list[LiquidityZone] = []
        last_dt = df.index[-1]
        last_date = last_dt.date()
        for name, start, end in (("london", 7, 12), ("newyork", 16, 21)):
            session_df = df[(df.index.date == last_date) & (df.index.hour >= start) & (df.index.hour < end)]
            if not session_df.empty:
                zones.append(LiquidityZone(
                    price_level=float(session_df["High"].max()),
                    zone_type=LiquidityZoneType.SESSION_HIGH.value,
                    strength=0.75,
                    session=name,
                ))
                zones.append(LiquidityZone(
                    price_level=float(session_df["Low"].min()),
                    zone_type=LiquidityZoneType.SESSION_LOW.value,
                    strength=0.75,
                    session=name,
                ))

        low = float(df["Low"].min())
        high = float(df["High"].max())
        step = 0.005
        start = np.floor(low / step) * step
        end = np.ceil(high / step) * step
        levels = np.arange(start, end + step, step)
        for level in levels:
            touches = ((df["High"] >= level - 0.0002) & (df["Low"] <= level + 0.0002)).sum()
            if touches >= 2:
                strength = min(0.9, 0.5 + (touches - 1) * 0.1)
                zones.append(LiquidityZone(
                    price_level=float(level),
                    zone_type=LiquidityZoneType.PSYCHOLOGICAL.value,
                    strength=float(strength),
                    session=session_regime,
                ))

        bin_size = 0.0005
        highs_bin = (df["High"] / bin_size).round() * bin_size
        lows_bin = (df["Low"] / bin_size).round() * bin_size
        for level, count in highs_bin.value_counts().items():
            if count >= 3:
                strength = min(0.9, 0.6 + count * 0.1)
                zones.append(LiquidityZone(
                    price_level=float(level),
                    zone_type=LiquidityZoneType.EQUAL_HIGHS.value,
                    strength=float(strength),
                    session=session_regime,
                ))
        for level, count in lows_bin.value_counts().items():
            if count >= 3:
                strength = min(0.9, 0.6 + count * 0.1)
                zones.append(LiquidityZone(
                    price_level=float(level),
                    zone_type=LiquidityZoneType.EQUAL_LOWS.value,
                    strength=float(strength),
                    session=session_regime,
                ))

        roll_high = df["High"].rolling(window=5, min_periods=5).max().shift(1)
        roll_low = df["Low"].rolling(window=5, min_periods=5).min().shift(1)
        breakout_high = df["Close"] > (roll_high + 0.0002)
        breakout_low = df["Close"] < (roll_low - 0.0002)
        last_time = df.index[-1]
        for idx in df.index[breakout_high.fillna(False)]:
            hours_since = (last_time - idx).total_seconds() / 3600 if isinstance(last_time, datetime) else 0
            strength = max(0.0, 0.8 * (1 - hours_since / 24))
            zones.append(LiquidityZone(
                price_level=float(df.loc[idx, "Low"]),
                zone_type=LiquidityZoneType.ORDER_BLOCK.value,
                strength=float(strength),
                session=session_regime,
            ))
        for idx in df.index[breakout_low.fillna(False)]:
            hours_since = (last_time - idx).total_seconds() / 3600 if isinstance(last_time, datetime) else 0
            strength = max(0.0, 0.8 * (1 - hours_since / 24))
            zones.append(LiquidityZone(
                price_level=float(df.loc[idx, "High"]),
                zone_type=LiquidityZoneType.ORDER_BLOCK.value,
                strength=float(strength),
                session=session_regime,
            ))

        zones_sorted = sorted(zones, key=lambda z: z.strength, reverse=True)[:8]
        return [
            {
                "price_level": round(z.price_level, 5),
                "zone_type": z.zone_type,
                "strength": round(z.strength, 2),
                "session": z.session,
            }
            for z in zones_sorted
        ]

    def _assess_market_intent(self, df: pd.DataFrame, zones: list[dict], session_regime: str) -> dict:
        if session_regime in ("weekend", "holiday"):
            return self._neutral_intent()

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        last_close = float(last["Close"])
        last_open = float(last["Open"]) if "Open" in last else last_close
        last_high = float(last["High"])
        last_low = float(last["Low"])
        prev_close = float(prev["Close"])
        prev_high = float(prev["High"])
        prev_low = float(prev["Low"])
        avg_volume = float(df["Volume"].tail(20).mean()) if "Volume" in df.columns else 0.0
        last_volume = float(last.get("Volume", 0.0)) if "Volume" in df.columns else 0.0
        last_time = df.index[-1]

        if zones:
            nearest_zone = min(zones, key=lambda z: abs(z["price_level"] - last_close))
            level = nearest_zone["price_level"]
            candle_body = abs(last_close - last_open)
            candle_body = candle_body if candle_body > 0 else 1e-6
            upper_wick = last_high - max(last_open, last_close)
            lower_wick = min(last_open, last_close) - last_low
            prior_range = max(prev_high - prev_low, 0.0)
            time_in_zone = 0.0
            if isinstance(last_time, datetime) and isinstance(prev.name, datetime):
                time_in_zone = (last_time - prev.name).total_seconds()

            if last_high > level and last_close <= level:
                wick_extension = last_high - level
                wick_to_body_ratio = upper_wick / candle_body
                reversal_close_pct = (prev_high - last_close) / prior_range if prior_range > 0 else 0.0
                wick_extension_pipettes = wick_extension * 100000
                sweep_conditions = [
                    wick_extension_pipettes > 18,
                    wick_to_body_ratio > 3.0,
                    reversal_close_pct > 0.70,
                    time_in_zone < 90,
                ]
                confirmed = sum(1 for c in sweep_conditions if c)
                if confirmed >= 3:
                    return {
                        "current_phase": "liquidity_sweep",
                        "next_likely_move": "down",
                        "confidence": 0.85,
                        "reasoning": f"Confirmed sweep ({confirmed}/4) above liquidity zone with strong rejection",
                    }
                if confirmed == 2:
                    return {
                        "current_phase": "possible_sweep",
                        "next_likely_move": "down",
                        "confidence": 0.55,
                        "reasoning": "Partial sweep conditions (2/4) above liquidity zone",
                    }
                return self._fallback_to_structure_intent(df, zones, session_regime, last, prev, avg_volume, last_volume)

            if last_low < level and last_close >= level:
                wick_extension = level - last_low
                wick_to_body_ratio = lower_wick / candle_body
                reversal_close_pct = (last_close - prev_low) / prior_range if prior_range > 0 else 0.0
                wick_extension_pipettes = wick_extension * 100000
                sweep_conditions = [
                    wick_extension_pipettes > 18,
                    wick_to_body_ratio > 3.0,
                    reversal_close_pct > 0.70,
                    time_in_zone < 90,
                ]
                confirmed = sum(1 for c in sweep_conditions if c)
                if confirmed >= 3:
                    return {
                        "current_phase": "liquidity_sweep",
                        "next_likely_move": "up",
                        "confidence": 0.85,
                        "reasoning": f"Confirmed sweep ({confirmed}/4) below liquidity zone with strong rejection",
                    }
                if confirmed == 2:
                    return {
                        "current_phase": "possible_sweep",
                        "next_likely_move": "up",
                        "confidence": 0.55,
                        "reasoning": "Partial sweep conditions (2/4) below liquidity zone",
                    }
                return self._fallback_to_structure_intent(df, zones, session_regime, last, prev, avg_volume, last_volume)

        return self._fallback_to_structure_intent(df, zones, session_regime, last, prev, avg_volume, last_volume)

    def _fallback_to_structure_intent(
        self,
        df: pd.DataFrame,
        zones: list[dict],
        session_regime: str,
        last,
        prev,
        avg_volume: float,
        last_volume: float,
    ) -> dict:
        last_close = float(last["Close"])
        prev_close = float(prev["Close"])
        recent = df.tail(15)
        range_pips = (recent["High"].max() - recent["Low"].min()) * 10000
        touches = 0
        for zone in zones:
            level = zone["price_level"]
            touches += ((recent["High"] >= level - 0.0002) & (recent["Low"] <= level + 0.0002)).sum()
        if range_pips < 10 and touches >= 2:
            confidence = min(0.7, 0.4 + (len(recent) * 0.01))
            return {
                "current_phase": "compression",
                "next_likely_move": "breakout_pending",
                "confidence": round(confidence, 2),
                "reasoning": "Tight range with repeated liquidity touches",
            }

        for zone in zones:
            level = zone["price_level"]
            if prev_close <= level + 0.001 and last_close > level + 0.001 and last_close > prev_close:
                if avg_volume > 0 and last_volume > 2 * avg_volume:
                    confidence = 0.7
                    if session_regime == "asian":
                        confidence = max(0.3, confidence - 0.2)
                    if session_regime == "overlap":
                        confidence = min(0.9, confidence + 0.1)
                    return {
                        "current_phase": "momentum",
                        "next_likely_move": "up",
                        "confidence": round(confidence, 2),
                        "reasoning": "Break above liquidity zone with volume follow-through",
                    }
            if prev_close >= level - 0.001 and last_close < level - 0.001 and last_close < prev_close:
                if avg_volume > 0 and last_volume > 2 * avg_volume:
                    confidence = 0.7
                    if session_regime == "asian":
                        confidence = max(0.3, confidence - 0.2)
                    if session_regime == "overlap":
                        confidence = min(0.9, confidence + 0.1)
                    return {
                        "current_phase": "momentum",
                        "next_likely_move": "down",
                        "confidence": round(confidence, 2),
                        "reasoning": "Break below liquidity zone with volume follow-through",
                    }

        if session_regime == "asian":
            return {
                "current_phase": "accumulation",
                "next_likely_move": "range",
                "confidence": 0.4,
                "reasoning": "Asian session favors range unless strong signals appear",
            }

        return {
            "current_phase": "unknown",
            "next_likely_move": "range",
            "confidence": 0.3,
            "reasoning": "No dominant liquidity behavior detected",
        }

    def _neutral_intent(self) -> dict:
        return {
            "current_phase": "unknown",
            "next_likely_move": "range",
            "confidence": 0.0,
            "reasoning": "No liquidity context available",
        }
