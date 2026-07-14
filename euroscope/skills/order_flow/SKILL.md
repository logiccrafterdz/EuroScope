---
name: order_flow
description: >
  Order flow proxy analysis using candle-level data. Estimates bid/ask imbalance,
  buying/selling pressure, and volume distribution without requiring Level 2 data.
  Use this skill to detect institutional accumulation/distribution, confirm
  technical signals with volume evidence, and identify absorption before
  breakouts. Run after technical_analysis for signal confirmation.
---

# Order Flow Skill

## What It Does
Estimates order flow dynamics from OHLCV candle data by analyzing:
- **Body-to-range ratio** — how much of the candle range was directional (closing pressure)
- **Delta estimation** — approximate buying vs selling volume using candle direction and body size
- **Cumulative delta divergence** — divergence between price and cumulative delta
- **Volume profile** — value area high/low, point of control estimation
- **Absorption detection** — large wicks with small bodies suggest passive order absorption

Since we don't have tick-level L2 data, this skill uses well-established
candle-based proxies that capture the essence of order flow imbalance.

## When To Use
- **After technical_analysis** — to confirm or contradict indicator signals
- **Before trading_strategy** — to add volume-evidence to signal generation
- **When detecting divergence** — delta divergence from price often precedes reversals
- **During breakouts** — to distinguish genuine breakouts from fakes

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `analyze` | Full order flow analysis | — | `candles` (DataFrame) |
| `delta` | Quick delta estimate | — | `candles` (DataFrame) |
| `absorption` | Check for absorption patterns | — | `candles` (DataFrame) |

## Input / Output Contract

### Reads from SkillContext
- `market_data.candles` — OHLCV DataFrame (auto-fetched if missing)

### Writes to SkillContext
- `analysis.order_flow` — Order flow analysis dict:
  - `buying_pressure` — 0.0–1.0, proportion of buying activity
  - `selling_pressure` — 0.0–1.0, proportion of selling activity
  - `delta_cumulative` — net cumulative delta over lookback
  - `delta_recent` — delta of last 5 candles
  - `absorption_detected` — Boolean
  - `absorption_side` — "buy" / "sell" / None
  - `value_area_high` — estimated VAH
  - `value_area_low` — estimated VAL
  - `poc` — estimated point of control
  - `divergence` — "bullish_divergence" / "bearish_divergence" / "none"
  - `confidence_boost` — -0.2 to +0.2, adjustment for signal confidence

## Delta Estimation Formula
For each candle:
- If close > open: delta = volume × body_ratio (buying dominance)
- If close < open: delta = -volume × body_ratio (selling dominance)
- body_ratio = |close - open| / (high - low + 1e-10)

## Absorption Pattern
- Large wick (> 60% of range) + small body (< 25% of range)
- Indicates passive orders absorbing aggressive flow
- Direction determined by which wick is larger

## Edge Cases
- < 10 candles: returns default neutral values
- Zero volume: delta defaults to 0
- Doji candles (tiny body): neutral delta, potential absorption
