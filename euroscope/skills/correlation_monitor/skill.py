"""
Correlation Monitor Skill

Tracks EUR/USD correlations with DXY, US10Y, and Gold (XAU/USD)
to detect divergences and confirm directional signals.
"""

import logging
from datetime import datetime, UTC

import numpy as np

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult

logger = logging.getLogger("euroscope.skills.correlation_monitor")

# Expected correlations with EUR/USD
CORRELATION_MAP = {
    "DX-Y.NYB": {
        "label": "DXY (Dollar Index)",
        "expected": -0.85,  # Strong inverse correlation
        "emoji": "💵",
    },
    "^TNX": {
        "label": "US 10Y Yield",
        "expected": -0.40,  # Moderate inverse (higher yields → stronger USD)
        "emoji": "📊",
    },
    "GC=F": {
        "label": "Gold (XAU/USD)",
        "expected": 0.50,  # Moderate positive (both anti-USD)
        "emoji": "🥇",
    },
}


class CorrelationMonitorSkill(BaseSkill):
    name = "correlation_monitor"
    description = "Tracks EUR/USD correlations with DXY, yields, and Gold for divergence detection"
    emoji = "🔗"
    category = SkillCategory.ANALYSIS
    version = "1.0.0"
    capabilities = ["check_correlations", "detect_divergence"]

    def __init__(self):
        super().__init__()
        self._provider = None

    def set_price_provider(self, provider):
        self._provider = provider

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "check_correlations":
            return await self._check_correlations(context, **params)
        elif action == "detect_divergence":
            return await self._detect_divergence(context, **params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _check_correlations(self, context: SkillContext, **params) -> SkillResult:
        """Compute correlations between EUR/USD and related instruments."""
        period = params.get("period", "1mo")
        interval = params.get("interval", "1d")

        try:
            import yfinance as yf
        except ImportError:
            return SkillResult(
                success=False,
                error="yfinance not available for correlation data"
            )

        # Fetch EUR/USD
        try:
            eurusd = yf.download("EURUSD=X", period=period, interval=interval, progress=False)
            if eurusd is None or eurusd.empty:
                return SkillResult(success=False, error="Could not fetch EUR/USD data")
            eurusd_close = eurusd["Close"].dropna()
            # Handle MultiIndex columns from yfinance
            if hasattr(eurusd_close, 'columns'):
                eurusd_close = eurusd_close.iloc[:, 0]
        except Exception as e:
            return SkillResult(success=False, error=f"EUR/USD fetch failed: {e}")

        results = {}
        divergences = []

        for ticker, info in CORRELATION_MAP.items():
            try:
                data = yf.download(ticker, period=period, interval=interval, progress=False)
                if data is None or data.empty:
                    logger.warning(f"No data for {ticker}")
                    continue

                close = data["Close"].dropna()
                if hasattr(close, 'columns'):
                    close = close.iloc[:, 0]

                # Align dates
                aligned = eurusd_close.align(close, join="inner")
                if len(aligned[0]) < 10:
                    logger.warning(f"Insufficient aligned data for {ticker}: {len(aligned[0])}")
                    continue

                eu_returns = aligned[0].pct_change().dropna()
                tk_returns = aligned[1].pct_change().dropna()

                # Compute correlations
                corr_20 = self._rolling_corr(eu_returns, tk_returns, 20)
                corr_full = float(np.corrcoef(eu_returns.values, tk_returns.values)[0, 1])

                # Check for divergence
                expected = info["expected"]
                deviation = abs(corr_full - expected)
                is_diverging = deviation > 0.40

                # Price direction comparison
                eu_direction = "UP" if float(eurusd_close.iloc[-1]) > float(eurusd_close.iloc[0]) else "DOWN"
                tk_direction = "UP" if float(close.iloc[-1]) > float(close.iloc[0]) else "DOWN"

                result_entry = {
                    "label": info["label"],
                    "ticker": ticker,
                    "correlation_20d": round(corr_20, 3) if corr_20 is not None else None,
                    "correlation_full": round(corr_full, 3),
                    "expected": expected,
                    "deviation": round(deviation, 3),
                    "is_diverging": is_diverging,
                    "eur_direction": eu_direction,
                    "instrument_direction": tk_direction,
                    "emoji": info["emoji"],
                }
                results[ticker] = result_entry

                if is_diverging:
                    divergences.append({
                        "instrument": info["label"],
                        "expected_corr": expected,
                        "actual_corr": round(corr_full, 3),
                        "eur_direction": eu_direction,
                        "instrument_direction": tk_direction,
                    })

            except Exception as e:
                logger.warning(f"Correlation check failed for {ticker}: {e}")

        if not results:
            return SkillResult(success=False, error="No correlation data available")

        analysis = {
            "instruments": results,
            "divergences": divergences,
            "divergence_count": len(divergences),
            "analyzed_at": datetime.now(UTC).isoformat(),
            "period": period,
        }

        # Store in context
        context.analysis["correlations"] = analysis

        # Set risk flag if divergences detected
        if divergences:
            context.metadata["correlation_warning"] = True
            context.metadata["divergence_count"] = len(divergences)

        formatted = self._format_correlations(analysis)
        return SkillResult(
            success=True,
            data=analysis,
            metadata={"formatted": formatted},
        )

    async def _detect_divergence(self, context: SkillContext, **params) -> SkillResult:
        """Convenience action that focuses on divergence detection."""
        result = await self._check_correlations(context, **params)
        if not result.success:
            return result

        divergences = result.data.get("divergences", [])
        if divergences:
            summary = "; ".join(
                f"{d['instrument']}: expected {d['expected_corr']}, actual {d['actual_corr']}"
                for d in divergences
            )
            return SkillResult(
                success=True,
                data={"has_divergence": True, "divergences": divergences, "summary": summary},
                metadata=result.metadata,
            )
        return SkillResult(
            success=True,
            data={"has_divergence": False, "divergences": []},
            metadata={"formatted": "✅ No correlation divergences detected."},
        )

    @staticmethod
    def _rolling_corr(series_a, series_b, window: int):
        """Compute the last value of rolling correlation."""
        if len(series_a) < window:
            return None
        try:
            rolling = series_a.rolling(window).corr(series_b)
            last_valid = rolling.dropna()
            return float(last_valid.iloc[-1]) if len(last_valid) > 0 else None
        except Exception:
            return None

    def _format_correlations(self, data: dict) -> str:
        """Format correlation analysis for Telegram display."""
        lines = ["🔗 *Correlation Monitor*", ""]

        for _, info in data["instruments"].items():
            emoji = info["emoji"]
            label = info["label"]
            corr = info["correlation_full"]
            expected = info["expected"]

            # Color-code correlation health
            if info["is_diverging"]:
                status = "⚠️ DIVERGING"
            elif abs(corr - expected) < 0.15:
                status = "✅ Normal"
            else:
                status = "🔶 Shifting"

            lines.append(f"{emoji} *{label}*")
            lines.append(f"  Correlation: `{corr:+.3f}` (expected: `{expected:+.2f}`) — {status}")
            lines.append(f"  EUR: {info['eur_direction']} | {label}: {info['instrument_direction']}")
            lines.append("")

        if data["divergences"]:
            lines.append(f"⚠️ *{data['divergence_count']} divergence(s) detected!*")
            lines.append("This may signal an unusual market regime or pending reversal.")

        return "\n".join(lines)
