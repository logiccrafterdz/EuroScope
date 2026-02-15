---
name: technical_analysis
description: Computes indicators, detects patterns with context-aware confidence, and finds key price levels
---

# 📈 Technical Analysis Skill

## What It Does
Runs a complete technical analysis on EUR/USD candle data — indicators, chart patterns with context-aware confidence, and support/resistance levels.

## Actions
- `analyze` — Full indicator suite (RSI, MACD, EMA, BB, ATR, ADX, Stochastic)
- `detect_patterns` — Classical chart patterns (H&S, Double Top/Bottom, Triangles, Channels)
- `find_levels` — Support/Resistance, Fibonacci retracements, Pivot points
- `full` — All of the above in one call

## Parameters
| Action | Param | Type | Default | Description |
|--------|-------|------|---------|-------------|
| all | df | DataFrame | from context | OHLCV DataFrame (auto-reads from context.market_data) |

## Returns
- `indicators`: dict of RSI, MACD, EMA, BB, ATR, ADX, Stochastic with values + signals
- `patterns`: list of detected chart patterns
- `levels`: dict with support[], resistance[], fibonacci, pivots
- `overall_bias`: bullish / bearish / neutral
