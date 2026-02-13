"""
Chart Generation

Generates candlestick charts with indicators for EUR/USD.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import mplfinance as mpf

logger = logging.getLogger("euroscope.utils.charts")


def generate_chart(df: pd.DataFrame, timeframe: str = "H1",
                   output_dir: str = "data/charts",
                   ema_periods: list[int] = None,
                   show_volume: bool = True) -> Optional[str]:
    """
    Generate a candlestick chart with indicators.

    Args:
        df: OHLCV DataFrame
        timeframe: Label for the chart title
        output_dir: Directory to save the chart
        ema_periods: EMA periods to overlay (default: [20, 50])
        show_volume: Whether to show volume subplot

    Returns:
        Path to the saved chart image, or None on failure.
    """
    if df is None or df.empty:
        return None

    if ema_periods is None:
        ema_periods = [20, 50]

    try:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        filename = out_path / f"eurusd_{timeframe.lower()}.png"

        # Build EMA overlays
        added_plots = []
        colors = ["#2196F3", "#FF9800", "#4CAF50", "#E91E63"]
        for i, period in enumerate(ema_periods):
            if len(df) >= period:
                ema_data = df["Close"].ewm(span=period, adjust=False).mean()
                color = colors[i % len(colors)]
                added_plots.append(mpf.make_addplot(ema_data, color=color, width=1.2,
                                                     label=f"EMA {period}"))

        # Chart style
        style = mpf.make_mpf_style(
            base_mpf_style="nightclouds",
            marketcolors=mpf.make_marketcolors(
                up="#26A69A", down="#EF5350",
                edge={"up": "#26A69A", "down": "#EF5350"},
                wick={"up": "#26A69A", "down": "#EF5350"},
                volume={"up": "#26A69A80", "down": "#EF535080"},
            ),
            figcolor="#1A1A2E",
            facecolor="#1A1A2E",
            gridstyle="--",
            gridcolor="#333355",
        )

        # Render chart
        mpf.plot(
            df,
            type="candle",
            style=style,
            title=f"\n EUR/USD — {timeframe}",
            ylabel="Price",
            volume=show_volume and "Volume" in df.columns,
            addplot=added_plots if added_plots else None,
            savefig=dict(fname=str(filename), dpi=150, bbox_inches="tight"),
            figscale=1.3,
            tight_layout=True,
        )

        logger.info(f"Chart saved to {filename}")
        return str(filename)

    except Exception as e:
        logger.error(f"Chart generation error: {e}")
        return None
