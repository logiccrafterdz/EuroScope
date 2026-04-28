---
name: session_context
description: >
  Classifies the current EUR/USD trading session (Asian, London, Overlap,
  New York, Closing, Weekend, Holiday) and provides session-specific adaptive
  rules that control risk limits, pattern confidence, and trading eligibility.
  Invoke at the START of every analysis pipeline — before any other analysis
  skill — because session regime propagates to technical_analysis (pattern
  confidence), risk_management (position sizing), liquidity_awareness (intent
  inference), and signal_executor (trade blocking). This is the environmental
  context that makes all other skills session-aware.
---

# 🕐 Session Context Skill

## What It Does
Detects the current forex trading session using UTC time and applies
session-specific rules that cascade through the entire analysis pipeline.
The forex market isn't a single entity — it's a sequence of overlapping
regional sessions, each with distinct characteristics in volatility,
liquidity, and directional tendency.

This skill ensures that every downstream decision is session-aware:
patterns detected during Asian hours are penalized, risk during London
open is elevated, and weekend trading is blocked entirely.

Results are cached for 5 minutes to avoid redundant session detection
during rapid OODA cycles.

## When To Use
- **FIRST** in every analysis pipeline — before technical_analysis, liquidity_awareness, and risk_management
- At the start of each OODA loop cycle
- When the agent needs to know if trading is currently allowed
- When risk_management needs session-appropriate position sizing multipliers
- When the user asks "what session are we in?" or "should I trade now?"

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `detect` | Classify current session and attach rules to context | — | — |

## Session Schedule (UTC)

| Session | UTC Hours | Characteristics |
|---------|-----------|-----------------|
| **Asian** | 00:00 — 07:00 | Low volatility, range-bound, EUR/USD often consolidates |
| **London** | 07:00 — 12:00 | High volatility, breakout-prone, most EUR/USD volume |
| **Overlap** | 12:00 — 16:00 | Peak volatility, London + NY both active, strongest moves |
| **New York** | 16:00 — 21:00 | Moderate volatility, continuation or reversal of London moves |
| **Closing** | 21:00 — 00:00 | Low liquidity, wide spreads, avoid new positions |
| **Weekend** | Sat/Sun | Market closed — NO trading |
| **Holiday** | Jan 1, Dec 25 | Market closed — NO trading |

## Input/Output Contract

### Reads From Context
- Nothing — uses system clock (UTC)

### Writes To Context
- `context.metadata["session_regime"]` — Session identifier string
- `context.metadata["session_rules"]` — Adaptive rules object

## Session Rules Matrix

Each session produces a specific set of adaptive rules that downstream
skills consume:

| Rule | Asian | London | Overlap | New York | Closing | Weekend/Holiday |
|------|-------|--------|---------|----------|---------|-----------------|
| `max_risk_pct` | 0.5% | 1.0% | 1.5% | 1.0% | 0.5% | 0.0% |
| `min_adx_threshold` | 20 | 25 | 28 | 26 | 28 | 30 |
| `deviation_sensitivity` | 1.0 | 0.9 | 0.7 | 0.85 | 1.1 | 1.2 |
| `trading_allowed` | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| `pattern_confidence_penalty` | -0.20 | 0.00 | 0.00 | 0.00 | -0.10 | -0.20 |

### How Rules Propagate

- **`max_risk_pct`** → `risk_management` uses it to cap position sizing
- **`min_adx_threshold`** → `trading_strategy` requires ADX above this to confirm trend
- **`deviation_sensitivity`** → `deviation_monitor` adjusts alert thresholds
- **`trading_allowed`** → `signal_executor` blocks new trades when `False`
- **`pattern_confidence_penalty`** → `technical_analysis` applies to all detected patterns

## Examples

### Example 1: London Session (Prime Trading Time)
```json
{
  "session_regime": "london",
  "session_rules": {
    "max_risk_pct": 1.0,
    "min_adx_threshold": 25,
    "deviation_sensitivity": 0.9,
    "trading_allowed": true,
    "pattern_confidence_penalty": 0.0
  }
}
```

### Example 2: Weekend (No Trading)
```json
{
  "session_regime": "weekend",
  "session_rules": {
    "max_risk_pct": 0.0,
    "min_adx_threshold": 30,
    "deviation_sensitivity": 1.2,
    "trading_allowed": false,
    "pattern_confidence_penalty": -0.2
  }
}
```

## Edge Cases & Degraded Modes
- **Clock skew**: Uses `datetime.now(UTC)` — system clock must be NTP-synced. No fallback if clock is wrong.
- **Exception in detection**: Returns `session_regime="unknown"` with neutral rules. Trading is allowed but at default risk levels.
- **Cache behavior**: Results cached for 300 seconds (5 min). During rapid OODA cycles, the session won't be re-detected until cache expires. This is intentional — sessions don't change every few seconds.
- **Holiday detection**: Currently only covers Jan 1 and Dec 25. Other market holidays (Good Friday, etc.) are not yet handled — they fall through to normal session detection.

## Integration Chain
```
session_context (FIRST) ──→ market_data
         ↓                       ↓
  technical_analysis ←───── liquidity_awareness
         ↓
  risk_management ──→ trading_strategy ──→ signal_executor
```

Every skill in the chain reads `context.metadata["session_regime"]` and
`context.metadata["session_rules"]` to make session-aware decisions.
This is why session_context must run FIRST.
