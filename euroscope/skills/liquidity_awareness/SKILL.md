---
name: liquidity_awareness
description: >
  Detects institutional liquidity zones (session highs/lows, previous day
  levels, equal highs/lows, order blocks, psychological levels) and infers
  market intent (sweep, compression, momentum, accumulation). Use this skill
  whenever the agent needs to understand WHERE smart money is positioned,
  WHAT the market is likely to do next, and WHERE to place stop losses safely.
  Invoke after session_context and before technical_analysis or risk_management.
  Critical for avoiding stop hunts and timing entries with institutional flow.
---

# 💧 Liquidity Awareness Skill

## What It Does
Maps the invisible architecture of the market — the liquidity zones where
institutional orders cluster and where stop losses accumulate. By detecting
these zones and analyzing price behavior around them, the skill infers the
market's likely next move: sweep, breakout, compression, or range.

This is the skill that bridges raw price data with institutional trading
logic. Traditional technical analysis sees patterns; liquidity awareness
sees the WHY behind the patterns — where money is trapped, where stops
will be hunted, and where the real moves begin.

## When To Use
- After `session_context.detect` and `market_data.get_candles`
- Before `technical_analysis` — liquidity zones enhance pattern confidence scoring
- Before `risk_management` — stop loss placement needs liquidity zone awareness
- When the agent detects a pattern but needs to validate it against institutional flow
- When the user asks "where are the key levels?" or "is this a stop hunt?"
- During the OODA Orient phase for complete market structure analysis

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `analyze` | Full liquidity zone detection + market intent inference | — | `df` (DataFrame) |

## Input/Output Contract

### Reads From Context
- `context.market_data["candles"]` — OHLCV DataFrame (minimum 20 candles)
- `context.metadata["session_regime"]` — Current trading session

### Writes To Context
- `context.metadata["liquidity_zones"]` — List of detected zones (max 12, sorted by strength)
- `context.metadata["market_intent"]` — Inferred market intent object
- `context.metadata["liquidity_aware"]` — `True` once analysis is complete
- `context.metadata["liquidity_signal"]` — "BUY" / "SELL" / "NEUTRAL"

## Liquidity Zone Taxonomy

The skill detects 10 types of liquidity zones, each representing a different
kind of institutional order accumulation:

| Zone Type | Strength | Description |
|-----------|----------|-------------|
| `session_high` | 0.75 | Current London/NY session high — stops above |
| `session_low` | 0.75 | Current London/NY session low — stops below |
| `previous_day_high` | 0.85 | Yesterday's high — strong institutional reference |
| `previous_day_low` | 0.85 | Yesterday's low — strong institutional reference |
| `weekly_high` | 0.90 | Last 7 days' high — major liquidity pool |
| `weekly_low` | 0.90 | Last 7 days' low — major liquidity pool |
| `psychological` | 0.50-0.90 | Round numbers (x.x050, x.x100) with ≥2 touches |
| `equal_highs` | 0.60-0.90 | 3+ highs at same binned level — retail stops above |
| `equal_lows` | 0.60-0.90 | 3+ lows at same binned level — retail stops below |
| `order_block` | 0.0-0.80 | Breakout origin candles — decaying strength over 24h |

### Zone Strength Scoring
- **Psychological levels**: `strength = 0.5 + (touches - 1) × 0.1`, capped at 0.9
- **Equal highs/lows**: `strength = 0.6 + count × 0.1`, capped at 0.9
- **Order blocks**: `strength = 0.8 × (1 - hours_since / 24)` — time-decay model

## Market Intent Inference

After detecting zones, the skill analyzes price behavior around the nearest
zone to infer WHAT the market is doing:

### Liquidity Sweep Detection (4-Condition Scoring)
A sweep occurs when price pierces a liquidity zone and reverses sharply:

| Condition | Threshold | What It Confirms |
|-----------|-----------|------------------|
| Wick extension | > 18 pipettes beyond zone | Price reached into the liquidity pool |
| Wick-to-body ratio | > 3.0 | Strong rejection (small body, long wick) |
| Reversal close % | > 70% of prior range | Decisive reversal, not just a probe |
| Time in zone | < 90 seconds | Fast rejection = institutional, not retail |

- **3-4 conditions met** → `liquidity_sweep`, confidence 0.85
- **2 conditions met** → `possible_sweep`, confidence 0.55
- **0-1 conditions met** → falls through to structural analysis

### Structural Intent Phases

| Phase | Detection Logic | Next Likely Move |
|-------|----------------|------------------|
| `compression` | Range < 10 pips + ≥2 zone touches | `breakout_pending` |
| `momentum` | Break above/below zone + 2× volume | Direction of break |
| `accumulation` | Asian session + no dominant signal | `range` |
| `unknown` | No pattern matches | `range` (low confidence) |

## Examples

### Example 1: Confirmed Liquidity Sweep (Bearish)
```json
{
  "liquidity_zones": [
    {"price_level": 1.09050, "zone_type": "session_high", "strength": 0.75, "session": "london"},
    {"price_level": 1.08500, "zone_type": "previous_day_low", "strength": 0.85, "session": "daily"}
  ],
  "market_intent": {
    "current_phase": "liquidity_sweep",
    "next_likely_move": "down",
    "confidence": 0.85,
    "reasoning": "Confirmed sweep (3/4) above liquidity zone with strong rejection"
  }
}
```

### Example 2: Compression Before Breakout
```json
{
  "market_intent": {
    "current_phase": "compression",
    "next_likely_move": "breakout_pending",
    "confidence": 0.52,
    "reasoning": "Tight range with repeated liquidity touches"
  }
}
```

## Edge Cases & Degraded Modes
- **Fewer than 20 candles**: Returns empty zones + neutral intent. Does NOT fail — downstream skills proceed with reduced context.
- **Invalid/non-DataFrame input**: Attempts conversion, returns empty on failure.
- **Weekend/Holiday session**: Returns `neutral_intent` immediately — no sweep analysis during closed markets.
- **No zones detected**: Returns empty zones list — this can happen in very low-volatility environments.
- **Exception in analysis**: Caught internally, returns empty zones + neutral intent with `liquidity_aware=True` so downstream skills know analysis was attempted.

## Integration Chain
```
session_context → market_data → liquidity_awareness
                                      ↓
                               technical_analysis (pattern confidence adjustment)
                                      ↓
                               risk_management (adaptive stop placement)
                                      ↓
                               signal_executor (guards check liquidity context)
```

### How Downstream Skills Use Liquidity Data
- **technical_analysis**: Adjusts pattern confidence based on proximity to zones and sweep state
- **risk_management**: Places stops beyond liquidity zones with session-specific buffers
- **uncertainty_assessment**: Incorporates market intent confidence into overall uncertainty score
- **signal_executor**: Uses liquidity signal for trade direction confirmation
