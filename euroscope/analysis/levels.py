"""
Support/Resistance & Fibonacci Levels

Identifies key price levels for EUR/USD.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("euroscope.analysis.levels")

FIBONACCI_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]


class LevelAnalyzer:
    """Detects support/resistance levels and Fibonacci retracements."""

    def find_support_resistance(self, df: pd.DataFrame, num_levels: int = 5) -> dict:
        """
        Find key support and resistance levels using price clustering.

        Groups price touches within a tolerance and ranks by frequency.
        """
        if df is None or df.empty or len(df) < 20:
            return {"support": [], "resistance": []}

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        current_price = float(close.iloc[-1])

        # Collect all swing highs/lows as candidate levels
        from .patterns import find_swing_points
        swing_highs, swing_lows = find_swing_points(close, window=3)

        all_levels = []
        for _, price in swing_highs:
            all_levels.append(price)
        for _, price in swing_lows:
            all_levels.append(price)

        if not all_levels:
            return {"support": [], "resistance": []}

        # Cluster nearby levels (within 15 pips)
        tolerance = 0.0015
        clusters = self._cluster_levels(sorted(all_levels), tolerance)

        # Separate into support and resistance
        support = [lvl for lvl in clusters if lvl < current_price]
        resistance = [lvl for lvl in clusters if lvl > current_price]

        # Sort: support descending (nearest first), resistance ascending
        support.sort(reverse=True)
        resistance.sort()

        return {
            "current_price": round(current_price, 5),
            "support": [round(s, 5) for s in support[:num_levels]],
            "resistance": [round(r, 5) for r in resistance[:num_levels]],
        }

    def fibonacci_retracement(self, df: pd.DataFrame, lookback: int = 50) -> dict:
        """
        Calculate Fibonacci retracement levels based on recent swing high/low.
        """
        if df is None or df.empty or len(df) < lookback:
            return {"error": "Insufficient data"}

        recent = df.tail(lookback)
        swing_high = float(recent["High"].max())
        swing_low = float(recent["Low"].min())

        high_idx = recent["High"].idxmax()
        low_idx = recent["Low"].idxmin()

        # Determine trend direction
        if high_idx > low_idx:
            # Uptrend: measure retracement from low to high
            direction = "uptrend"
            levels = {
                f"{int(r*100)}%": round(swing_high - (swing_high - swing_low) * r, 5)
                for r in FIBONACCI_RATIOS
            }
        else:
            # Downtrend: measure retracement from high to low
            direction = "downtrend"
            levels = {
                f"{int(r*100)}%": round(swing_low + (swing_high - swing_low) * r, 5)
                for r in FIBONACCI_RATIOS
            }

        return {
            "direction": direction,
            "swing_high": round(swing_high, 5),
            "swing_low": round(swing_low, 5),
            "range_pips": round((swing_high - swing_low) * 10000, 1),
            "levels": levels,
        }

    def pivot_points(self, df: pd.DataFrame) -> dict:
        """Calculate classic pivot points from the previous period."""
        if df is None or df.empty or len(df) < 2:
            return {"error": "Insufficient data"}

        # Use previous candle
        prev = df.iloc[-2]
        h = float(prev["High"])
        l = float(prev["Low"])
        c = float(prev["Close"])

        pivot = (h + l + c) / 3
        r1 = 2 * pivot - l
        s1 = 2 * pivot - h
        r2 = pivot + (h - l)
        s2 = pivot - (h - l)
        r3 = h + 2 * (pivot - l)
        s3 = l - 2 * (h - pivot)

        return {
            "R3": round(r3, 5),
            "R2": round(r2, 5),
            "R1": round(r1, 5),
            "Pivot": round(pivot, 5),
            "S1": round(s1, 5),
            "S2": round(s2, 5),
            "S3": round(s3, 5),
        }

    def format_levels(self, sr_data: dict, fib_data: dict = None, pivot_data: dict = None) -> str:
        """Format levels for Telegram display."""
        lines = ["📐 *Key Levels (EUR/USD)*\n"]

        # Support & Resistance
        if sr_data.get("resistance"):
            lines.append("🔴 *Resistance:*")
            for i, r in enumerate(sr_data["resistance"], 1):
                lines.append(f"  R{i}: `{r}`")
            lines.append("")

        lines.append(f"💰 Current: `{sr_data.get('current_price', 'N/A')}`\n")

        if sr_data.get("support"):
            lines.append("🟢 *Support:*")
            for i, s in enumerate(sr_data["support"], 1):
                lines.append(f"  S{i}: `{s}`")
            lines.append("")

        # Fibonacci
        if fib_data and "levels" in fib_data:
            lines.append(f"📊 *Fibonacci ({fib_data['direction']})*")
            lines.append(f"  Range: {fib_data['range_pips']} pips")
            for label, level in fib_data["levels"].items():
                lines.append(f"  {label}: `{level}`")
            lines.append("")

        # Pivots
        if pivot_data and "Pivot" in pivot_data:
            lines.append("🔄 *Pivot Points:*")
            for label in ["R3", "R2", "R1", "Pivot", "S1", "S2", "S3"]:
                icon = "🔴" if label.startswith("R") else "🟢" if label.startswith("S") else "⚪"
                lines.append(f"  {icon} {label}: `{pivot_data[label]}`")

        return "\n".join(lines)

    @staticmethod
    def _cluster_levels(levels: list[float], tolerance: float) -> list[float]:
        """Group nearby price levels into clusters, return cluster centers."""
        if not levels:
            return []

        clusters = []
        current_cluster = [levels[0]]

        for price in levels[1:]:
            if price - current_cluster[-1] <= tolerance:
                current_cluster.append(price)
            else:
                clusters.append(sum(current_cluster) / len(current_cluster))
                current_cluster = [price]

        clusters.append(sum(current_cluster) / len(current_cluster))
        return clusters
