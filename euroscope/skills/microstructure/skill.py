"""
Microstructure Skill — Market Microstructure Analysis.

Analyzes spread dynamics, price efficiency, tick patterns, and liquidity
quality from OHLCV data to assess execution conditions and market quality.
"""

import math
import logging
from typing import Optional

import pandas as pd

from ..base import BaseSkill, SkillCategory, SkillResult, SkillContext

logger = logging.getLogger("euroscope.skills.microstructure")


def _efficiency_ratio(closes: list[float]) -> float:
    """
    Price efficiency ratio = net directional move / total path.
    ER > 0.7 = trending, < 0.3 = choppy.
    """
    if len(closes) < 2:
        return 0.0

    net_move = abs(closes[-1] - closes[0])
    total_path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))

    if total_path < 1e-10:
        return 0.0
    return net_move / total_path


def _consecutive_direction(closes: list[float]) -> int:
    """Longest recent streak of consecutive same-direction bars."""
    if len(closes) < 2:
        return 0

    max_streak = 1
    current_streak = 1
    last_dir = 0  # 0=flat, 1=up, -1=down

    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            d = 1
        elif closes[i] < closes[i - 1]:
            d = -1
        else:
            d = 0

        if d == last_dir and d != 0:
            current_streak += 1
        elif d != 0:
            current_streak = 1
        else:
            current_streak = 0

        last_dir = d
        max_streak = max(max_streak, current_streak)

    return max_streak


def _momentum_autocorrelation(returns: list[float], lag: int = 1) -> float:
    """Autocorrelation of returns at given lag."""
    n = len(returns)
    if n < lag + 3:
        return 0.0

    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / n

    if var < 1e-15:
        return 0.0

    cov = sum((returns[i] - mean) * (returns[i - lag] - mean) for i in range(lag, n)) / n
    return cov / var


def _amihud_illiquidity(closes: list[float], volumes: list[float]) -> float:
    """
    Amihud illiquidity = mean(|return| / volume).
    Higher = more illiquid.
    """
    if len(closes) < 2:
        return 0.0

    ratios = []
    for i in range(1, len(closes)):
        ret = abs(closes[i] - closes[i - 1]) / max(abs(closes[i - 1]), 1e-10)
        vol = volumes[i] if i < len(volumes) else 0
        if vol > 0:
            ratios.append(ret / vol)

    return sum(ratios) / len(ratios) if ratios else 0.0


def _spread_estimate(highs: list[float], lows: list[float], closes: list[float]) -> float:
    """Estimate effective spread from candle ranges (in pips)."""
    if not highs or not lows:
        return 0.0

    ranges = [(h - l) * 10000 for h, l in zip(highs, lows)]
    avg_range = sum(ranges) / len(ranges)

    # Spread is roughly 15-30% of average range for FX
    return round(avg_range * 0.2, 1)


def _tick_pattern(efficiency: float, autocorr: float, avg_range_pips: float) -> str:
    """Classify tick pattern from microstructure features."""
    if efficiency > 0.65 and autocorr > 0.1:
        return "trending"
    if efficiency < 0.30 and avg_range_pips < 8:
        return "mean_reverting"
    if avg_range_pips > 20:
        return "volatile"
    return "random"


class MicrostructureSkill(BaseSkill):
    name = "microstructure"
    description = "Market microstructure analysis: efficiency, spread, liquidity quality"
    emoji = "🔬"
    category = SkillCategory.ANALYSIS
    version = "1.0.0"
    capabilities = ["analyze", "efficiency", "liquidity"]
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

        if len(candles) < 5:
            return SkillResult(success=False, error=f"Insufficient data: {len(candles)} candles (minimum 5)")

        # Normalize columns
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
            if col in df.columns:
                df[col] = df[col].astype(float)
        if "volume" not in df.columns:
            df["volume"] = 0.0
        else:
            df["volume"] = df["volume"].astype(float)

        if action == "efficiency":
            result = self._quick_efficiency(df)
        elif action == "liquidity":
            result = self._liquidity_assessment(df)
        else:
            result = self._full_analysis(df)

        context.analysis["microstructure"] = result
        return SkillResult(
            success=True,
            data=result,
            metadata={"skill": "microstructure", "action": action},
            next_skill="trading_strategy",
        )

    def _full_analysis(self, df: pd.DataFrame) -> dict:
        closes = df["close"].tolist()
        highs = df["high"].tolist()
        lows = df["low"].tolist()
        volumes = df["volume"].tolist()

        # Efficiency
        er = _efficiency_ratio(closes)

        # Returns for autocorrelation
        returns = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        autocorr = _momentum_autocorrelation(returns)

        # Consecutive direction
        consec = _consecutive_direction(closes)

        # Spread estimate
        spread_pips = _spread_estimate(highs[-20:], lows[-20:], closes[-20:])

        # Amihud
        amihud = _amihud_illiquidity(closes, volumes)

        # Avg range in pips
        avg_range_pips = sum((h - l) * 10000 for h, l in zip(highs[-20:], lows[-20:])) / min(20, len(highs))

        # Tick pattern
        pattern = _tick_pattern(er, autocorr, avg_range_pips)

        # Liquidity quality score (composite)
        liq_score = self._liquidity_score(er, spread_pips, autocorr, pattern)

        # Session quality
        session_quality = self._session_quality(spread_pips, er, liq_score)

        # Confidence adjustment
        conf_adj = self._confidence_adjustment(er, pattern, session_quality)

        return {
            "spread_estimate": round(spread_pips, 1),
            "efficiency_ratio": round(er, 4),
            "consecutive_direction": consec,
            "momentum_persistence": round(autocorr, 4),
            "amihud_illiquidity": round(amihud, 8),
            "liquidity_score": round(liq_score, 3),
            "tick_pattern": pattern,
            "session_quality": session_quality,
            "confidence_adjustment": round(conf_adj, 3),
            "data_points": len(closes),
        }

    def _quick_efficiency(self, df: pd.DataFrame) -> dict:
        closes = df["close"].tolist()
        er = _efficiency_ratio(closes[-20:] if len(closes) > 20 else closes)
        consec = _consecutive_direction(closes[-20:] if len(closes) > 20 else closes)
        return {
            "efficiency_ratio": round(er, 4),
            "consecutive_direction": consec,
            "regime": "trending" if er > 0.65 else "choppy" if er < 0.30 else "normal",
        }

    def _liquidity_assessment(self, df: pd.DataFrame) -> dict:
        closes = df["close"].tolist()
        highs = df["high"].tolist()
        lows = df["low"].tolist()
        volumes = df["volume"].tolist()

        spread = _spread_estimate(highs[-20:], lows[-20:], closes[-20:])
        amihud = _amihud_illiquidity(closes, volumes)
        er = _efficiency_ratio(closes)
        returns = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        autocorr = _momentum_autocorrelation(returns)
        pattern = _tick_pattern(er, autocorr, sum((h - l) * 10000 for h, l in zip(highs[-20:], lows[-20:])) / min(20, len(highs)))
        liq_score = self._liquidity_score(er, spread, autocorr, pattern)

        return {
            "spread_estimate": round(spread, 1),
            "amihud_illiquidity": round(amihud, 8),
            "liquidity_score": round(liq_score, 3),
            "session_quality": self._session_quality(spread, er, liq_score),
        }

    @staticmethod
    def _liquidity_score(er: float, spread_pips: float, autocorr: float, pattern: str) -> float:
        score = 0.5  # base

        # Efficiency component (30%)
        if er > 0.6:
            score += 0.15
        elif er < 0.3:
            score -= 0.15

        # Spread component (30%)
        if spread_pips < 1.5:
            score += 0.15
        elif spread_pips > 5:
            score -= 0.15

        # Pattern component (20%)
        if pattern == "trending":
            score += 0.10
        elif pattern == "volatile":
            score -= 0.10

        # Momentum consistency (20%)
        if 0.05 < autocorr < 0.3:
            score += 0.10
        elif autocorr < -0.1:
            score -= 0.05

        return max(0.0, min(1.0, score))

    @staticmethod
    def _session_quality(spread_pips: float, er: float, liq_score: float) -> str:
        if spread_pips < 2.0 and er > 0.5 and liq_score > 0.6:
            return "good"
        if spread_pips > 5.0 or er < 0.2:
            return "poor"
        return "moderate"

    @staticmethod
    def _confidence_adjustment(er: float, pattern: str, session_quality: str) -> float:
        adj = 0.0
        if pattern == "trending":
            adj += 0.10
        elif pattern == "volatile":
            adj -= 0.10
        elif pattern == "mean_reverting":
            adj += 0.05

        if session_quality == "good":
            adj += 0.05
        elif session_quality == "poor":
            adj -= 0.10

        return max(-0.15, min(0.15, adj))
