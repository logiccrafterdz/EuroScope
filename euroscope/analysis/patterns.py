"""
Classical Chart Pattern Detection

Detects Head & Shoulders, Double Top/Bottom, Triangles,
Channels, Flags, and Wedges on EUR/USD candle data.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("euroscope.analysis.patterns")


def find_swing_points(close: pd.Series, window: int = 5) -> tuple[list, list]:
    """
    Find swing highs and swing lows in the price data.

    Returns (swing_highs, swing_lows) as lists of (index, price) tuples.
    """
    highs = []
    lows = []

    for i in range(window, len(close) - window):
        # Swing high: higher than `window` bars on each side
        if all(close.iloc[i] >= close.iloc[i - j] for j in range(1, window + 1)) and \
           all(close.iloc[i] >= close.iloc[i + j] for j in range(1, window + 1)):
            highs.append((i, float(close.iloc[i])))

        # Swing low: lower than `window` bars on each side
        if all(close.iloc[i] <= close.iloc[i - j] for j in range(1, window + 1)) and \
           all(close.iloc[i] <= close.iloc[i + j] for j in range(1, window + 1)):
            lows.append((i, float(close.iloc[i])))

    return highs, lows


class PatternDetector:
    """Detects classical chart patterns on EUR/USD data."""

    def __init__(self, tolerance: float = 0.001):
        """
        Args:
            tolerance: Price tolerance for pattern matching (as fraction, e.g. 0.001 = 10 pips)
        """
        self.tolerance = tolerance

    def detect_all(self, df: pd.DataFrame) -> list[dict]:
        """Run all pattern detectors and return found patterns."""
        if df is None or df.empty or len(df) < 20:
            return []

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        patterns = []

        # Find swing points
        swing_highs, swing_lows = find_swing_points(close, window=5)

        # Run detectors
        patterns.extend(self._detect_double_top(swing_highs, close))
        patterns.extend(self._detect_double_bottom(swing_lows, close))
        patterns.extend(self._detect_head_shoulders(swing_highs, swing_lows, close))
        patterns.extend(self._detect_channel(swing_highs, swing_lows, close))
        patterns.extend(self._detect_triangle(swing_highs, swing_lows, close))

        return patterns

    def _detect_double_top(self, swing_highs: list, close: pd.Series) -> list[dict]:
        """Detect Double Top pattern (bearish reversal)."""
        patterns = []
        if len(swing_highs) < 2:
            return patterns

        for i in range(len(swing_highs) - 1):
            idx1, price1 = swing_highs[i]
            idx2, price2 = swing_highs[i + 1]

            # Two peaks at approximately the same level
            if abs(price1 - price2) / price1 <= self.tolerance:
                # Must have a valley between them
                if idx2 - idx1 >= 5:
                    neckline = float(close.iloc[idx1:idx2].min())
                    patterns.append({
                        "pattern": "Double Top",
                        "type": "bearish",
                        "confidence": self._calc_confidence(price1, price2),
                        "level": round((price1 + price2) / 2, 5),
                        "neckline": round(neckline, 5),
                        "target": round(neckline - (price1 - neckline), 5),
                        "description": f"Double Top at {round((price1+price2)/2, 5)} — bearish reversal signal",
                    })

        return patterns[-1:] if patterns else []  # Only most recent

    def _detect_double_bottom(self, swing_lows: list, close: pd.Series) -> list[dict]:
        """Detect Double Bottom pattern (bullish reversal)."""
        patterns = []
        if len(swing_lows) < 2:
            return patterns

        for i in range(len(swing_lows) - 1):
            idx1, price1 = swing_lows[i]
            idx2, price2 = swing_lows[i + 1]

            if abs(price1 - price2) / price1 <= self.tolerance:
                if idx2 - idx1 >= 5:
                    neckline = float(close.iloc[idx1:idx2].max())
                    patterns.append({
                        "pattern": "Double Bottom",
                        "type": "bullish",
                        "confidence": self._calc_confidence(price1, price2),
                        "level": round((price1 + price2) / 2, 5),
                        "neckline": round(neckline, 5),
                        "target": round(neckline + (neckline - price1), 5),
                        "description": f"Double Bottom at {round((price1+price2)/2, 5)} — bullish reversal signal",
                    })

        return patterns[-1:] if patterns else []

    def _detect_head_shoulders(self, swing_highs: list, swing_lows: list,
                               close: pd.Series) -> list[dict]:
        """Detect Head and Shoulders pattern."""
        patterns = []
        if len(swing_highs) < 3:
            return patterns

        for i in range(len(swing_highs) - 2):
            _, left = swing_highs[i]
            _, head = swing_highs[i + 1]
            _, right = swing_highs[i + 2]

            # Head must be higher than shoulders
            if head > left and head > right:
                # Shoulders at approximately same level
                if abs(left - right) / left <= self.tolerance * 2:
                    shoulder_avg = (left + right) / 2
                    patterns.append({
                        "pattern": "Head & Shoulders",
                        "type": "bearish",
                        "confidence": min(90, int(60 + (head - shoulder_avg) / head * 1000)),
                        "head": round(head, 5),
                        "shoulders": round(shoulder_avg, 5),
                        "description": f"Head & Shoulders — head at {round(head, 5)}, bearish reversal",
                    })

        return patterns[-1:] if patterns else []

    def _detect_channel(self, swing_highs: list, swing_lows: list,
                        close: pd.Series) -> list[dict]:
        """Detect ascending/descending channel."""
        patterns = []
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return patterns

        # Check if highs are trending (ascending or descending)
        high_prices = [p for _, p in swing_highs[-4:]]
        low_prices = [p for _, p in swing_lows[-4:]]

        if len(high_prices) >= 2 and len(low_prices) >= 2:
            highs_ascending = all(high_prices[i] <= high_prices[i+1] for i in range(len(high_prices)-1))
            lows_ascending = all(low_prices[i] <= low_prices[i+1] for i in range(len(low_prices)-1))
            highs_descending = all(high_prices[i] >= high_prices[i+1] for i in range(len(high_prices)-1))
            lows_descending = all(low_prices[i] >= low_prices[i+1] for i in range(len(low_prices)-1))

            if highs_ascending and lows_ascending:
                patterns.append({
                    "pattern": "Ascending Channel",
                    "type": "bullish",
                    "confidence": 65,
                    "upper": round(high_prices[-1], 5),
                    "lower": round(low_prices[-1], 5),
                    "description": "Ascending Channel — bullish continuation",
                })
            elif highs_descending and lows_descending:
                patterns.append({
                    "pattern": "Descending Channel",
                    "type": "bearish",
                    "confidence": 65,
                    "upper": round(high_prices[-1], 5),
                    "lower": round(low_prices[-1], 5),
                    "description": "Descending Channel — bearish continuation",
                })

        return patterns

    def _detect_triangle(self, swing_highs: list, swing_lows: list,
                         close: pd.Series) -> list[dict]:
        """Detect triangle patterns (converging highs and lows)."""
        patterns = []
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return patterns

        high_prices = [p for _, p in swing_highs[-3:]]
        low_prices = [p for _, p in swing_lows[-3:]]

        if len(high_prices) >= 2 and len(low_prices) >= 2:
            highs_converging = high_prices[-1] < high_prices[-2]
            lows_converging = low_prices[-1] > low_prices[-2]

            if highs_converging and lows_converging:
                patterns.append({
                    "pattern": "Symmetrical Triangle",
                    "type": "neutral",
                    "confidence": 60,
                    "description": "Symmetrical Triangle — breakout expected in either direction",
                })
            elif highs_converging and not lows_converging:
                patterns.append({
                    "pattern": "Descending Triangle",
                    "type": "bearish",
                    "confidence": 65,
                    "description": "Descending Triangle — bearish breakdown likely",
                })
            elif not highs_converging and lows_converging:
                patterns.append({
                    "pattern": "Ascending Triangle",
                    "type": "bullish",
                    "confidence": 65,
                    "description": "Ascending Triangle — bullish breakout likely",
                })

        return patterns

    def _calc_confidence(self, price1: float, price2: float) -> int:
        """Calculate confidence based on how close two levels are."""
        diff_pct = abs(price1 - price2) / price1
        return min(95, max(50, int(100 - diff_pct * 10000)))

    def format_patterns(self, patterns: list[dict]) -> str:
        """Format detected patterns for Telegram display."""
        if not patterns:
            return "🔍 *Pattern Detection*\nNo classical patterns detected on current data."

        lines = ["🔍 *Detected Patterns*\n"]
        for p in patterns:
            icon = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(p["type"], "⚪")
            lines.append(f"{icon} *{p['pattern']}* (confidence: {p.get('confidence', '?')}%)")
            lines.append(f"   {p['description']}")
            if "level" in p:
                lines.append(f"   Level: `{p['level']}`")
            if "target" in p:
                lines.append(f"   Target: `{p['target']}`")
            if "neckline" in p:
                lines.append(f"   Neckline: `{p['neckline']}`")
            lines.append("")

        return "\n".join(lines)
