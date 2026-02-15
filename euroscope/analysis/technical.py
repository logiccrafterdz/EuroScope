"""
Technical Analysis Module

Computes indicators (RSI, MACD, EMA, Bollinger, ATR, ADX, Stochastic)
on EUR/USD candle data and generates human-readable summaries.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("euroscope.analysis.technical")


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD indicator."""
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def bollinger_bands(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> dict:
    """Bollinger Bands."""
    middle = sma(close, period)
    std = close.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return {"upper": upper, "middle": middle, "lower": lower}


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index (simplified)."""
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    atr_val = atr(high, low, close, period)
    plus_di = 100 * ema(plus_dm, period) / atr_val
    minus_di = 100 * ema(minus_dm, period) / atr_val

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return ema(dx, period)


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
               k_period: int = 14, d_period: int = 3) -> dict:
    """Stochastic Oscillator (%K and %D)."""
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    k_line = 100 * (close - lowest_low) / (highest_high - lowest_low)
    d_line = sma(k_line, d_period)
    return {"k": k_line, "d": d_line}


class TechnicalAnalyzer:
    """Runs full technical analysis on EUR/USD candle data."""

    def analyze(self, df: pd.DataFrame) -> dict:
        """
        Run all indicators on a DataFrame with OHLCV columns.

        Returns a dict with indicator values and interpretations.
        """
        if df is None or df.empty or len(df) < 26:
            return {"error": "Insufficient data for analysis (need at least 26 candles)"}

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        current_price = float(close.iloc[-1])

        # Compute all indicators
        rsi_val = float(rsi(close).iloc[-1])
        macd_data = macd(close)
        macd_val = float(macd_data["macd"].iloc[-1])
        macd_signal = float(macd_data["signal"].iloc[-1])
        macd_hist = float(macd_data["histogram"].iloc[-1])

        bb = bollinger_bands(close)
        bb_upper = float(bb["upper"].iloc[-1])
        bb_lower = float(bb["lower"].iloc[-1])
        bb_middle = float(bb["middle"].iloc[-1])

        ema20 = float(ema(close, 20).iloc[-1])
        ema50 = float(ema(close, 50).iloc[-1])
        ema200_val = float(ema(close, 200).iloc[-1]) if len(close) >= 200 else None

        atr_val = float(atr(high, low, close).iloc[-1])
        adx_val = float(adx(high, low, close).iloc[-1]) if len(close) >= 28 else None

        stoch = stochastic(high, low, close)
        stoch_k = float(stoch["k"].iloc[-1])
        stoch_d = float(stoch["d"].iloc[-1])

        # Interpretations
        result = {
            "price": round(current_price, 5),
            "indicators": {
                "RSI": {"value": round(rsi_val, 1), "signal": self._rsi_signal(rsi_val)},
                "MACD": {
                    "macd": round(macd_val, 6),
                    "signal": round(macd_signal, 6),
                    "histogram": round(macd_hist, 6),
                    "signal_text": "Bullish" if macd_val > macd_signal else "Bearish",
                },
                "Bollinger": {
                    "upper": round(bb_upper, 5),
                    "middle": round(bb_middle, 5),
                    "lower": round(bb_lower, 5),
                    "position": self._bb_position(current_price, bb_upper, bb_lower, bb_middle),
                },
                "EMA": {
                    "ema20": round(ema20, 5),
                    "ema50": round(ema50, 5),
                    "ema200": round(ema200_val, 5) if ema200_val else None,
                    "trend": self._ema_trend(current_price, ema20, ema50, ema200_val),
                },
                "ATR": {"value": round(atr_val, 5), "pips": round(atr_val * 10000, 1)},
                "ADX": {
                    "value": round(adx_val, 1) if adx_val else None,
                    "strength": self._adx_strength(adx_val) if adx_val else "Weak / no trend",
                },
                "Stochastic": {
                    "k": round(stoch_k, 1),
                    "d": round(stoch_d, 1),
                    "signal": self._stoch_signal(stoch_k, stoch_d),
                },
            },
            "overall_bias": self._overall_bias(rsi_val, macd_val, macd_signal, current_price, ema20, ema50),
        }

        return result

    def format_analysis(self, result: dict, timeframe: str = "H1") -> str:
        """Format technical analysis for Telegram display."""
        if "error" in result:
            return f"⚠️ {result['error']}"

        ind = result["indicators"]
        bias = result["overall_bias"]
        bias_icon = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "⚪"}.get(bias, "⚪")

        lines = [
            f"📊 *EUR/USD Technical Analysis ({timeframe})*",
            f"💰 Price: `{result['price']}`",
            f"🎯 Bias: {bias_icon} *{bias}*\n",

            f"📈 *Indicators:*",
            f"  RSI(14): `{ind['RSI']['value']}` — {ind['RSI']['signal']}",
            f"  MACD: `{ind['MACD']['macd']}` — {ind['MACD']['signal_text']}",
            f"  Stoch: `%K={ind['Stochastic']['k']}` — {ind['Stochastic']['signal']}",
            f"  ADX: `{ind['ADX']['value']}` — {ind['ADX']['strength']}",
            f"  ATR: `{ind['ATR']['pips']} pips`\n",

            f"📏 *Moving Averages:*",
            f"  EMA 20: `{ind['EMA']['ema20']}`",
            f"  EMA 50: `{ind['EMA']['ema50']}`",
            f"  EMA 200: `{ind['EMA']['ema200']}`",
            f"  Trend: {ind['EMA']['trend']}\n",

            f"📐 *Bollinger Bands:*",
            f"  Upper: `{ind['Bollinger']['upper']}`",
            f"  Middle: `{ind['Bollinger']['middle']}`",
            f"  Lower: `{ind['Bollinger']['lower']}`",
            f"  Position: {ind['Bollinger']['position']}",
        ]
        return "\n".join(lines)

    # --- Signal Interpretation Helpers ---

    @staticmethod
    def _rsi_signal(val: float) -> str:
        if val >= 70:
            return "🔴 Overbought"
        elif val <= 30:
            return "🟢 Oversold"
        elif val >= 60:
            return "🟡 Approaching overbought"
        elif val <= 40:
            return "🟡 Approaching oversold"
        return "⚪ Neutral"

    @staticmethod
    def _bb_position(price, upper, lower, middle) -> str:
        if price >= upper:
            return "🔴 At/above upper band (overbought)"
        elif price <= lower:
            return "🟢 At/below lower band (oversold)"
        elif price > middle:
            return "🟡 Above middle band (bullish bias)"
        else:
            return "🟡 Below middle band (bearish bias)"

    @staticmethod
    def _ema_trend(price, ema20, ema50, ema200) -> str:
        if ema200 and price > ema20 > ema50 > ema200:
            return "🟢 Strong uptrend (price > EMA20 > EMA50 > EMA200)"
        elif ema200 and price < ema20 < ema50 < ema200:
            return "🔴 Strong downtrend (price < EMA20 < EMA50 < EMA200)"
        elif price > ema20 > ema50:
            return "🟢 Uptrend"
        elif price < ema20 < ema50:
            return "🔴 Downtrend"
        return "⚪ Mixed / consolidation"

    @staticmethod
    def _adx_strength(val: float) -> str:
        if val >= 50:
            return "Very strong trend"
        elif val >= 25:
            return "Strong trend"
        elif val >= 20:
            return "Developing trend"
        return "Weak / no trend"

    @staticmethod
    def _stoch_signal(k, d) -> str:
        if k > 80 and d > 80:
            return "🔴 Overbought"
        elif k < 20 and d < 20:
            return "🟢 Oversold"
        elif k > d:
            return "🟡 Bullish crossover"
        elif k < d:
            return "🟡 Bearish crossover"
        return "⚪ Neutral"

    @staticmethod
    def _overall_bias(rsi_val, macd_val, macd_signal, price, ema20, ema50) -> str:
        score = 0
        # RSI
        if rsi_val > 55:
            score += 1
        elif rsi_val < 45:
            score -= 1
        # MACD
        if macd_val > macd_signal:
            score += 1
        else:
            score -= 1
        # EMA
        if price > ema20 > ema50:
            score += 1
        elif price < ema20 < ema50:
            score -= 1

        if score >= 2:
            return "Bullish"
        elif score <= -2:
            return "Bearish"
        return "Neutral"
