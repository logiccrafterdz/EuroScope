---
name: multi_timeframe_confluence
description: >
  Analyzes EUR/USD across M15, H1, H4, and D1 timeframes simultaneously to
  find confluence — where multiple timeframes agree on direction. Use this skill
  when the agent needs high-confidence directional bias before generating signals.
  Invoke after technical_analysis for single-timeframe data, and before
  trading_strategy for signal generation. Essential for filtering out noise and
  avoiding trades where timeframes conflict. Also use when the user asks
  "are the timeframes aligned?" or needs a multi-timeframe view.
---

# 🔀 Multi-Timeframe Confluence Skill

## What It Does
Analyzes EUR/USD across four timeframes simultaneously (M15, H1, H4, D1),
extracting directional signals from RSI, MACD, and EMA on each, then computing
a weighted confluence score that tells the agent how strongly the market
agrees on a direction.

Single-timeframe analysis can be misleading — a bullish H1 chart means little
if H4 and D1 are bearish. This skill solves that by quantifying multi-timeframe
alignment and providing a confidence-weighted verdict that downstream skills
can trust for signal generation and risk sizing.

## When To Use
- After `market_data` and alongside `technical_analysis` in the analysis phase
- Before `trading_strategy` — confluence verdict gates signal generation
- When the agent needs to decide whether to trade or wait for alignment
- When the user asks "what's the bigger picture?" or "should I trade this timeframe?"
- As a filter: MIXED verdict → reduce position size or skip trading

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `confluence` | Full multi-timeframe analysis with weighted scoring | — | `timeframes` (list, default ["M15","H1","H4","D1"]) |
| `check_alignment` | Quick boolean alignment check | — | `timeframes` (list) |

## Timeframe Hierarchy & Weights

Higher timeframes carry more weight because they represent larger market forces:

| Timeframe | Weight | Role |
|-----------|--------|------|
| **M15** | 0.15 | Noise filter — entry timing only |
| **H1** | 0.25 | Primary trading timeframe — swing detection |
| **H4** | 0.30 | Trend confirmation — institutional positioning |
| **D1** | 0.30 | Macro direction — dominant trend |

## Input/Output Contract

### Reads From Context
- Nothing directly — fetches its own candle data via PriceProvider for each timeframe

### Writes To Context
- `context.analysis["confluence"]` — Full confluence analysis object
- `context.metadata["mtf_bias"]` — "BULLISH" / "BEARISH" / "MIXED"
- `context.metadata["mtf_confidence"]` — 0-95 confidence score

### Confluence Scoring Algorithm

For each timeframe, three indicators are evaluated:
1. **RSI**: >60 = BULLISH, <40 = BEARISH, else NEUTRAL
2. **MACD**: Signal text parsed for direction
3. **EMA**: Trend direction parsed

The majority direction becomes that timeframe's vote. A trending market
(ADX > 25) amplifies the vote by 1.2×; non-trending reduces it to 0.8×.

```
weighted_score = Σ(tf_weight × direction_score × strength_multiplier) / total_weight
verdict = BULLISH if bullish_score > 0.5, BEARISH if bearish_score > 0.5, else MIXED
confidence = |bullish_score - bearish_score| × 100 + aligned_count × 5
```

## Examples

### Example 1: Strong Bullish Confluence
```
🔀 Multi-Timeframe Confluence
Verdict: 🟢 BULLISH (78% confidence)
Alignment: 4/4 timeframes

  📈 M15: 🟢 BULLISH (B:3 vs R:0)
  📈 H1:  🟢 BULLISH (B:2 vs R:0)
  📈 H4:  🟢 BULLISH (B:3 vs R:0)
  📈 D1:  🟢 BULLISH (B:2 vs R:1)
```

### Example 2: Mixed / No Trade
```
🔀 Multi-Timeframe Confluence
Verdict: ⚪ MIXED (23% confidence)
Alignment: 1/4 timeframes

  📈 M15: 🟢 BULLISH (B:2 vs R:1)
  ➡️ H1:  ⚪ NEUTRAL (B:1 vs R:1)
  📈 H4:  🔴 BEARISH (B:0 vs R:2)
  📈 D1:  🔴 BEARISH (B:1 vs R:2)
```

## Edge Cases & Degraded Modes
- **Provider unavailable**: Returns `success=False`. Trading should not proceed without MTF context.
- **Insufficient data for a timeframe** (<50 candles): That timeframe is skipped with a warning. Analysis continues with remaining timeframes.
- **All timeframes fail**: Returns `success=False` with combined error messages.
- **Only 1-2 timeframes succeed**: Analysis proceeds but confidence is naturally lower due to reduced weight coverage.

## Integration Chain
```
market_data → multi_timeframe_confluence → trading_strategy → signal_executor
                     ↓
              context.metadata["mtf_bias"] + ["mtf_confidence"]
                     ↓
              risk_management (uses confidence for sizing)
```

## Runtime Dependencies
- `PriceProvider` — injected via `set_price_provider()`
- `TechnicalAnalyzer` — internal (no injection needed)
