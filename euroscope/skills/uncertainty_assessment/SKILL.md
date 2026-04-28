---
name: uncertainty_assessment
description: >
  Quantifies cognitive uncertainty from technical divergence, causal pattern
  mismatch, and behavioral context (session regime, liquidity intent, macro
  events). Use this skill as the FINAL gate before signal generation — it
  determines whether the market context is clear enough to trade. When
  uncertainty exceeds 0.65, the signal_executor will block trades. Invoke
  after technical_analysis, liquidity_awareness, and fundamental_analysis
  so all context layers are available for assessment. Also use when the agent
  needs to explain WHY a trade was blocked or confidence was reduced.
---

# 🧭 Uncertainty Assessment Skill

## What It Does
Acts as the system's cognitive confidence filter. It synthesizes three
independent uncertainty dimensions — technical, causal, and behavioral —
into a single composite score that gates the entire trading pipeline.

This isn't just a simple threshold check. The skill understands that
uncertainty comes from different sources: conflicting indicators (technical),
mismatched causal patterns from historical data (causal), and adverse
environmental conditions like weekend trading or approaching macro events
(behavioral). By composing these layers, it provides a nuanced confidence
assessment that prevents overtrading in ambiguous conditions.

## When To Use
- **After all analysis skills** and **before signal generation/execution**
- When `signal_executor` needs to check if conditions are safe to trade
- When the agent needs to explain a confidence reduction or trade block
- When building briefings that include market clarity assessment
- Automatically in every OODA Orient → Decide transition

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `assess` | Full multi-layer uncertainty assessment | — | — |

## Three Uncertainty Layers

### 1. Technical Uncertainty (Weight: Primary)
Measures how clear the indicator picture is:

| Condition | Uncertainty Added | Rationale |
|-----------|------------------|-----------|
| ADX missing | +0.70 | No trend data = maximum uncertainty |
| ADX < 20 | +0.70 | Sideways chop — no reliable direction |
| ADX 20-40 | +0.70 | Safety-first: ensures high uncertainty |
| ADX > 40 | +0.05 | Strong trend = clear direction |
| RSI 45-55 | +0.20 | Dead center — no momentum signal |
| RSI 40-60 | +0.10 | Mild zone — weak signal |
| RSI extreme | +0.05 | Clear overbought/oversold |
| MACD histogram near zero | +0.20 | No momentum confirmation |
| Conflicting patterns (bull + bear) | +0.20 | Market giving mixed signals |
| No patterns detected | +0.10 | Lack of structural confirmation |

### 2. Causal Uncertainty
Measures whether current market conditions match historical patterns:

- Uses `PatternTracker` to classify the current trigger and match it
  against the causal pattern database
- When causal similarity < 0.4 → +0.25 uncertainty ("causal mismatch")
- When no pattern tracker available → 0.0 (neutral, doesn't penalize)

### 3. Behavioral Uncertainty
Measures environmental/contextual risk:

| Condition | Uncertainty Added | Rationale |
|-----------|------------------|-----------|
| Weekend/Holiday | +0.40 | Market closed — no valid signals |
| Asian session + reversal pattern | +0.20 | Low-volume reversals are unreliable |
| Overlap session + range intent | +0.15 | Expected volatility but seeing compression |
| Low intent confidence (<0.5) | +0.25 | Market intent is unclear |
| Compression phase | +0.10 | Pre-breakout = unpredictable direction |
| Pattern vs intent conflict | +0.20 | Technical and structural disagree |
| Near liquidity zone | +0.15 | Stop hunt risk — unless breakout confirmed |
| High-impact macro event within 30 min | +0.30 | Upcoming volatility spike |

## Composition Formula

The three layers are composed using a max-plus-bonus formula:
```
base = max(technical, causal, behavioral)
bonus = 0.3 × (sum_of_all_three - base)
composite = min(1.0, base + bonus)
```

This ensures the worst dimension dominates, but secondary dimensions
still contribute meaningfully.

## Confidence Adjustment

The composite uncertainty maps to a confidence multiplier:

| Uncertainty Range | Confidence Adjustment | Effect |
|:-----------------|:---------------------|:-------|
| ≤ 0.40 | 1.0× | Full confidence — proceed normally |
| 0.41 — 0.55 | 0.8× | Slightly reduced — smaller position size |
| 0.56 — 0.70 | 0.5× | Significant reduction — trade with caution |
| > 0.70 | 0.0× | **BLOCKED** — do not trade |

### Macro Override (Strict Conditions)
In rare cases, strong macro data can partially restore confidence:
- Requires: macro_confidence > 0.80 AND ADX ≥ 25 AND uncertainty ≤ 0.65
  AND session is London/Overlap/NY
- Effect: 1.2× boost to confidence adjustment (max recovery to 0.4)

## Input/Output Contract

### Reads From Context
- `context.analysis["indicators"]` — Technical indicator suite
- `context.analysis["patterns"]` — Detected patterns
- `context.analysis["calendar"]` — Economic events
- `context.analysis["macro_data"]` — Macro analysis
- `context.market_data["candles"]` — Price data for behavioral analysis
- `context.metadata["session_regime"]` — Current session
- `context.metadata["market_intent"]` — Liquidity intent
- `context.metadata["liquidity_zones"]` — Active liquidity zones

### Writes To Context
- `context.metadata["uncertainty_score"]` — Composite uncertainty (0.0-1.0)
- `context.metadata["confidence_adjustment"]` — Multiplier (0.0-1.0)
- `context.metadata["high_uncertainty"]` — Boolean flag (>0.65)
- `context.metadata["market_regime"]` — "trending" / "ranging" / "volatile"
- `context.metadata["uncertainty_reasoning"]` — Human-readable explanation
- `context.analysis["uncertainty"]` — Full breakdown object

## Examples

### Example 1: Clear Market (Trade Allowed)
```
🧭 Uncertainty Assessment
Regime: trending
Uncertainty: 0.35
Confidence Adj: 1.0×
```

### Example 2: Blocked Trade
```
🧭 Uncertainty Assessment
Regime: ranging
Uncertainty: 0.72
Confidence Adj: 0.0×
⚠️ High uncertainty
Reasoning: "High uncertainty (0.72): london technical divergence + low intent confidence"
```

## Edge Cases & Degraded Modes
- **Missing indicators**: Technical uncertainty defaults to high values (0.7 for missing ADX). This is intentional — missing data = high uncertainty.
- **No candle data**: Behavioral analysis returns 0.4 uncertainty with "insufficient_candles" reason.
- **Vector memory unavailable**: Falls back to 0.4 behavioral uncertainty. Does NOT block — just less confident.
- **No pattern tracker**: Causal uncertainty = 0.0 (neutral). Only technical and behavioral layers are active.
- **All context missing**: Returns high uncertainty — the system correctly identifies that it doesn't know enough to trade.

## Integration Chain
```
technical_analysis ─┐
liquidity_awareness ─┤→ uncertainty_assessment → signal_executor (gate)
fundamental_analysis ┘        ↓                        ↓
session_context ─────────────→│               confidence_adjustment
                              ↓               used by risk_management
                    context.metadata["uncertainty_score"]
                    context.metadata["confidence_adjustment"]
```

## Runtime Dependencies
- `VectorMemory` — optional, for historical pattern matching
- `PatternTracker` — optional, for causal pattern analysis
