"""
Order Flow Skill — Candle-Based Order Flow Proxy Analysis.

Estimates bid/ask imbalance, buying/selling pressure, delta divergence,
and absorption patterns from OHLCV data without requiring Level 2 quotes.
"""

import logging
from typing import Optional

import pandas as pd

from ..base import BaseSkill, SkillCategory, SkillResult, SkillContext

logger = logging.getLogger("euroscope.skills.order_flow")


def _body_ratio(row) -> float:
    """How much of the candle range was directional body."""
    h, l, c, o = row["high"], row["low"], row["close"], row["open"]
    rng = h - l
    if rng < 1e-10:
        return 0.0
    return abs(c - o) / rng


def _wick_ratio(row) -> float:
    """Upper + lower wick as ratio of range."""
    h, l, c, o = row["high"], row["low"], row["close"], row["open"]
    rng = h - l
    if rng < 1e-10:
        return 0.0
    body_top = max(c, o)
    body_bot = min(c, o)
    upper_wick = h - body_top
    lower_wick = body_bot - l
    return (upper_wick + lower_wick) / rng


def _estimate_delta(row) -> float:
    """Estimate single-candle delta from direction and body ratio."""
    volume = row.get("volume", 0)
    br = _body_ratio(row)
    if row["close"] >= row["open"]:
        return volume * br
    else:
        return -volume * br


class OrderFlowSkill(BaseSkill):
    name = "order_flow"
    description = "Order flow proxy analysis using candle data"
    emoji = "📊"
    category = SkillCategory.ANALYSIS
    version = "1.0.0"
    capabilities = ["analyze", "delta", "absorption"]
    dependencies = ["market_data"]
    execution_timeout = 15

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action not in self.capabilities:
            return SkillResult(success=False, error=f"Unknown action '{action}'. Available: {self.capabilities}")

        candles = params.get("candles")
        if candles is None:
            candles = context.market_data.get("candles")
        if candles is None:
            return SkillResult(success=False, error="No candle data available. Run market_data first.")

        if isinstance(candles, list):
            candles = pd.DataFrame(candles)

        required = {"Open", "High", "Low", "Close"}
        cols = set(candles.columns)
        if not required.issubset(cols):
            lower = {c.lower() for c in cols}
            if {"open", "high", "low", "close"}.issubset(lower):
                candles.columns = [c.capitalize() for c in candles.columns]
            else:
                return SkillResult(success=False, error=f"Missing OHLC columns. Found: {list(candles.columns)}")

        if len(candles) < 5:
            return SkillResult(success=False, error=f"Insufficient data: {len(candles)} candles (minimum 5)")

        # Normalize column names
        df = candles.copy()
        rename_map = {}
        for c in df.columns:
            cl = c.lower()
            if cl == "open": rename_map[c] = "open"
            elif cl == "high": rename_map[c] = "high"
            elif cl == "low": rename_map[c] = "low"
            elif cl == "close": rename_map[c] = "close"
            elif cl == "volume": rename_map[c] = "volume"
        df = df.rename(columns=rename_map)

        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)
        if "volume" in df.columns:
            df["volume"] = df["volume"].astype(float)
        else:
            df["volume"] = 0.0

        if action == "delta":
            result = self._quick_delta(df)
        elif action == "absorption":
            result = self._check_absorption(df)
        else:
            result = self._full_analysis(df)

        context.analysis["order_flow"] = result
        return SkillResult(
            success=True,
            data=result,
            metadata={"skill": "order_flow", "action": action},
            next_skill="trading_strategy",
        )

    def _full_analysis(self, df: pd.DataFrame) -> dict:
        n = len(df)
        lookback = min(n, 50)
        recent = df.tail(lookback).copy()

        has_volume = "volume" in recent.columns and recent["volume"].sum() > 0

        # Delta per candle
        if has_volume:
            deltas = recent.apply(_estimate_delta, axis=1).tolist()
        else:
            # Price-based delta estimation when volume is unavailable
            deltas = []
            for _, row in recent.iterrows():
                body = row["close"] - row["open"]
                rng = row["high"] - row["low"]
                if rng < 1e-10:
                    deltas.append(0.0)
                    continue
                body_ratio = abs(body) / rng
                deltas.append(body * body_ratio * 100000)

        # Buying/selling pressure
        total_delta = sum(deltas)
        abs_delta = sum(abs(d) for d in deltas)
        buying_pressure = round(sum(d for d in deltas if d > 0) / max(abs_delta, 1e-10), 4)
        selling_pressure = round(sum(-d for d in deltas if d < 0) / max(abs_delta, 1e-10), 4)

        # Recent delta (last 5)
        recent_5 = deltas[-5:] if len(deltas) >= 5 else deltas
        delta_recent = round(sum(recent_5), 2)

        # Cumulative delta divergence
        divergence = self._check_divergence(recent, deltas)

        # Absorption
        absorption = self._detect_absorption(recent)

        # Volume-weighted price levels (simplified VA)
        vwah, vwal, poc = self._volume_profile(recent)

        # Confidence boost
        boost = self._confidence_boost(buying_pressure, selling_pressure, divergence, absorption)

        return {
            "buying_pressure": round(buying_pressure, 3),
            "selling_pressure": round(selling_pressure, 3),
            "delta_cumulative": round(total_delta, 2),
            "delta_recent": round(delta_recent, 2),
            "absorption_detected": absorption["detected"],
            "absorption_side": absorption.get("side"),
            "value_area_high": round(vwah, 5),
            "value_area_low": round(vwal, 5),
            "poc": round(poc, 5),
            "divergence": divergence,
            "confidence_boost": round(boost, 3),
            "lookback": lookback,
        }

    def _quick_delta(self, df: pd.DataFrame) -> dict:
        deltas = df.tail(10).apply(_estimate_delta, axis=1).tolist()
        total = sum(deltas)
        abs_total = sum(abs(d) for d in deltas)
        bp = round(sum(d for d in deltas if d > 0) / max(abs_total, 1e-10), 3)
        sp = round(sum(-d for d in deltas if d < 0) / max(abs_total, 1e-10), 3)

        return {
            "buying_pressure": bp,
            "selling_pressure": sp,
            "delta_cumulative": round(total, 2),
            "delta_recent": round(sum(deltas[-5:]), 2) if len(deltas) >= 5 else round(total, 2),
            "bars": len(deltas),
        }

    def _check_absorption(self, df: pd.DataFrame) -> dict:
        """Detect absorption: large wick + small body = passive orders absorbing."""
        if len(df) < 3:
            return {"detected": False, "side": None}

        last = df.iloc[-1]
        br = _body_ratio(last)
        wr = _wick_ratio(last)
        rng = last["high"] - last["low"]

        if wr > 0.60 and br < 0.25 and rng > 0:
            upper_wick = last["high"] - max(last["close"], last["open"])
            lower_wick = min(last["close"], last["open"]) - last["low"]
            if upper_wick > lower_wick * 1.5:
                return {"detected": True, "side": "sell", "wick_ratio": round(wr, 3)}
            elif lower_wick > upper_wick * 1.5:
                return {"detected": True, "side": "buy", "wick_ratio": round(wr, 3)}
            return {"detected": True, "side": None, "wick_ratio": round(wr, 3)}

        return {"detected": False, "side": None}

    def _detect_absorption(self, df: pd.DataFrame) -> dict:
        return self._check_absorption(df)

    def _check_divergence(self, df: pd.DataFrame, deltas: list[float]) -> str:
        """Check for bullish/bearish divergence between price and cumulative delta."""
        if len(deltas) < 10:
            return "none"

        closes = df["close"].tolist()
        half = len(deltas) // 2

        first_half_price = sum(closes[:half]) / half if half > 0 else 0
        second_half_price = sum(closes[half:]) / (len(closes) - half) if half < len(closes) else 0
        first_half_delta = sum(deltas[:half])
        second_half_delta = sum(deltas[half:])

        price_up = second_half_price > first_half_price
        delta_up = second_half_delta > first_half_delta

        if price_up and not delta_up:
            return "bearish_divergence"
        if not price_up and delta_up:
            return "bullish_divergence"
        return "none"

    def _volume_profile(self, df: pd.DataFrame) -> tuple[float, float, float]:
        """Simplified volume-weighted price levels."""
        if "volume" not in df.columns or df["volume"].sum() == 0:
            closes = df["close"].tolist()
            return (max(closes), min(closes), closes[-1])

        total_vol = df["volume"].sum()
        if total_vol == 0:
            closes = df["close"].tolist()
            return (max(closes), min(closes), closes[-1])

        vwah = (df["high"] * df["volume"]).sum() / total_vol
        vwal = (df["low"] * df["volume"]).sum() / total_vol
        poc = (df["close"] * df["volume"]).sum() / total_vol
        return (float(vwah), float(vwal), float(poc))

    def _confidence_boost(self, bp: float, sp: float, divergence: str,
                          absorption: dict) -> float:
        boost = 0.0
        # Strong imbalance adds confidence
        if bp > 0.65:
            boost += 0.10
        elif sp > 0.65:
            boost += 0.10

        # Divergence reduces confidence
        if divergence != "none":
            boost -= 0.15

        # Absorption reduces confidence (uncertainty)
        if absorption["detected"]:
            boost -= 0.05

        return max(-0.20, min(0.20, boost))
