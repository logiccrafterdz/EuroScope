---
name: microstructure
description: >
  Market microstructure analysis examining spread dynamics, price efficiency,
  tick patterns, and liquidity quality from candle data. Use this skill to
  assess execution quality expectations, detect regime changes through
  microstructure shifts, and identify optimal entry timing based on
  price action efficiency. Run alongside technical_analysis for deeper
  market structure insights.
---

# Microstructure Skill

## What It Does
Analyzes market microstructure properties from OHLCV data:
- **Spread proxy** — estimated effective spread from candle high-low range
- **Price efficiency** — ratio of directional move to total path (efficiency ratio)
- **Tick patterns** — consecutive directional moves, momentum persistence
- **Amihud illiquidity** — price impact per unit of volume
- **Intraday volatility pattern** — session-based volatility clustering
- **Liquidity quality score** — composite score of spread, depth, and efficiency

These microstructure features help the system understand *how* the market
is moving, not just *where* it's moving. Low efficiency with wide spreads
means choppy, expensive-to-trade conditions.

## When To Use
- **Before signal execution** — to estimate execution quality and slippage
- **During regime detection** — microstructure shifts often precede regime changes
- **In briefings** — to report market quality and liquidity conditions
- **For session comparison** — different sessions have different microstructure

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `analyze` | Full microstructure analysis | — | `candles` (DataFrame) |
| `efficiency` | Price efficiency ratio only | — | `candles` (DataFrame) |
| `liquidity` | Liquidity quality assessment | — | `candles` (DataFrame) |

## Input / Output Contract

### Reads from SkillContext
- `market_data.candles` — OHLCV DataFrame (auto-fetched if missing)

### Writes to SkillContext
- `analysis.microstructure` — Microstructure analysis dict:
  - `spread_estimate` — estimated spread in pips
  - `efficiency_ratio` — 0.0–1.0, directional/total move ratio
  - `consecutive_direction` — longest recent consecutive bar direction
  - `momentum_persistence` — autocorrelation of returns
  - `amihud_illiquidity` — price impact measure
  - `liquidity_score` — 0.0–1.0 composite quality score
  - `tick_pattern` — "trending" / "mean_reverting" / "random" / "volatile"
  - `session_quality` — "good" / "moderate" / "poor"
  - `confidence_adjustment` — -0.15 to +0.15

## Efficiency Ratio
ER = |close_t - close_{t-n}| / Σ|close_i - close_{i-1}|
- ER > 0.7: trending (directional, low friction)
- ER 0.3–0.7: normal
- ER < 0.3: choppy/random (high friction, avoid)

## Amihud Illiquidity
ILLIQ = mean(|return| / volume) over lookback window
Higher values = more illiquid = wider expected spreads

## Liquidity Quality Score
Composite of: spread (30%), efficiency (30%), volume consistency (20%), tick pattern (20%)

## Edge Cases
- < 10 candles: returns defaults with "insufficient_data" warning
- Zero volume: Amihud returns inf, handled gracefully
- Flat price: efficiency = 0, spread_estimate = minimum
