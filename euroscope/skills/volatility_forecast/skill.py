"""
Volatility Forecast Skill — GARCH(1,1) Volatility Prediction.

Forecasts near-term volatility using exponentially weighted GARCH,
classifies volatility regimes, and provides confidence adjustments.
"""

import math
import logging
from typing import Optional

import pandas as pd

from ..base import BaseSkill, SkillCategory, SkillResult, SkillContext

logger = logging.getLogger("euroscope.skills.volatility_forecast")

# Volatility regime thresholds (annualized)
REGIMES = {
    "low": (0.0, 0.05),
    "normal": (0.05, 0.10),
    "elevated": (0.10, 0.15),
    "high": (0.15, 0.25),
    "extreme": (0.25, float("inf")),
}

REGIME_CONFIDENCE = {
    "low": 0.85,
    "normal": 1.00,
    "elevated": 0.80,
    "high": 0.50,
    "extreme": 0.20,
}


def _log_returns(close: pd.Series) -> pd.Series:
    """Compute log returns from close prices."""
    import numpy as np
    return np.log(close / close.shift(1)).dropna()


def _garch_forecast(returns: pd.Series, halflife: int = 20) -> dict:
    """
    Exponentially weighted GARCH(1,1) volatility forecast.

    σ²_t = ω + α·r²_{t-1} + β·σ²_{t-1}
    """
    import numpy as np

    if len(returns) < 30:
        return {"current_vol": 0.0, "forecast_vol": 0.0, "expanding": False}

    r2 = returns ** 2

    # Exponentially weighted variance
    ewm_var = r2.ewm(halflife=halflife, min_periods=10).var()
    current_var = float(ewm_var.iloc[-1]) if not pd.isna(ewm_var.iloc[-1]) else 0.0

    # GARCH parameters
    omega = 0.0
    alpha = 0.09
    beta = 0.90

    # GARCH forecast: one-step ahead variance
    last_r2 = float(r2.iloc[-1]) if not pd.isna(r2.iloc[-1]) else 0.0
    last_var = float(ewm_var.iloc[-2]) if len(ewm_var) > 1 and not pd.isna(ewm_var.iloc[-2]) else current_var

    forecast_var = omega + alpha * last_r2 + beta * last_var

    # Annualize (252 trading days)
    current_vol = math.sqrt(max(current_var * 252, 0.0))
    forecast_vol = math.sqrt(max(forecast_var * 252, 0.0))

    expanding = forecast_vol > current_vol * 1.05

    return {
        "current_vol": round(current_vol, 4),
        "forecast_vol": round(forecast_vol, 4),
        "expanding": expanding,
    }


def _classify_regime(annualized_vol: float) -> str:
    for regime, (lo, hi) in REGIMES.items():
        if lo <= annualized_vol < hi:
            return regime
    return "extreme"


def _percentile_rank(values: list[float], target: float) -> float:
    if not values:
        return 50.0
    count_below = sum(1 for v in values if v <= target)
    return round(count_below / len(values) * 100, 1)


class VolatilityForecastSkill(BaseSkill):
    name = "volatility_forecast"
    description = "GARCH-based volatility forecasting and regime classification"
    emoji = "📊"
    category = SkillCategory.ANALYSIS
    version = "1.0.0"
    capabilities = ["forecast", "regime"]
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

        if len(candles) < 10:
            return SkillResult(
                success=False,
                error=f"Insufficient data: {len(candles)} candles (minimum 10)",
            )

        close = candles["Close"] if "Close" in candles.columns else candles.get("close")
        if close is None:
            return SkillResult(success=False, error="No 'Close' column in candle data")

        close = close.astype(float)

        if action == "regime":
            result = self._quick_regime(close)
        else:
            result = self._full_forecast(close, candles)

        context.analysis["volatility"] = result
        return SkillResult(
            success=True,
            data=result,
            metadata={"skill": "volatility_forecast", "action": action},
            next_skill="trading_strategy",
        )

    def _quick_regime(self, close: pd.Series) -> dict:
        returns = _log_returns(close)
        if len(returns) < 10:
            return self._default_result("insufficient_data")

        import numpy as np
        recent_var = float(returns.tail(20).var()) if len(returns) >= 20 else float(returns.var())
        current_vol = math.sqrt(max(recent_var * 252, 0.0))
        regime = _classify_regime(current_vol)

        return {
            "current_vol": round(current_vol, 4),
            "forecast_vol": round(current_vol, 4),
            "regime": regime,
            "expanding": False,
            "confidence_multiplier": REGIME_CONFIDENCE[regime],
            "percentile_rank": 50.0,
        }

    def _full_forecast(self, close: pd.Series, candles: pd.DataFrame) -> dict:
        returns = _log_returns(close)
        if len(returns) < 30:
            return self._default_result("insufficient_data")

        garch = _garch_forecast(returns)

        # Percentile rank of current vol against rolling 20-day windows
        import numpy as np
        rolling_vols = []
        window = min(20, len(returns) - 1)
        for i in range(window, len(returns)):
            chunk = returns.iloc[i - window:i + 1]
            v = math.sqrt(max(float(chunk.var()) * 252, 0.0))
            rolling_vols.append(v)

        pctile = _percentile_rank(rolling_vols, garch["current_vol"])

        # ATR-based annualized range
        if "High" in candles.columns and "Low" in candles.columns:
            high = candles["High"].astype(float)
            low = candles["Low"].astype(float)
            tr = (high - low).tail(14)
            atr_pips = float(tr.mean()) * 10000
            annualized_range = round(atr_pips * math.sqrt(252), 1)
        else:
            annualized_range = 0.0

        regime = _classify_regime(garch["current_vol"])
        forecast_regime = _classify_regime(garch["forecast_vol"])

        return {
            "current_vol": garch["current_vol"],
            "forecast_vol": garch["forecast_vol"],
            "regime": regime,
            "forecast_regime": forecast_regime,
            "expanding": garch["expanding"],
            "confidence_multiplier": REGIME_CONFIDENCE[regime],
            "annualized_range": annualized_range,
            "percentile_rank": pctile,
            "data_points": len(returns),
        }

    @staticmethod
    def _default_result(warning: str) -> dict:
        return {
            "current_vol": 0.0,
            "forecast_vol": 0.0,
            "regime": "normal",
            "expanding": False,
            "confidence_multiplier": 1.0,
            "percentile_rank": 50.0,
            "warning": warning,
        }
