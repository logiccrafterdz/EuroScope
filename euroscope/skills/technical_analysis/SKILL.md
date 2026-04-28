---
name: technical_analysis
description: >
  Computes indicators (RSI, MACD, EMA, Bollinger, ATR, ADX, Stochastic),
  detects chart patterns with context-aware confidence scoring, and finds
  key support/resistance levels. Use this skill whenever the agent needs to
  assess market direction, identify entry/exit zones, or build a technical
  picture before signal generation. This is the core analysis engine — invoke
  it after market_data and before risk_management in every trading pipeline.
  Also use when the user asks about indicators, patterns, or price levels.
---

# 📈 Technical Analysis Skill

## What It Does
Runs a complete multi-layered technical analysis on EUR/USD candle data.
This is the analytical brain of EuroScope — it takes raw OHLCV data and
transforms it into actionable intelligence: indicator readings, detected
chart patterns with context-adjusted confidence, and key price levels.

What makes this skill powerful is its **context-aware confidence scoring**.
Chart patterns don't exist in a vacuum — a Head & Shoulders during Asian
session is less reliable than during London, and a Double Top near a
liquidity sweep zone needs extra caution. This skill applies session,
liquidity, trend, and news penalties/bonuses automatically.

## When To Use
- After `market_data.get_candles` in every analysis pipeline
- When the agent needs to determine bullish/bearish/neutral bias
- Before `risk_management.assess_trade` — it needs indicator data for stop/TP calculation
- When the user asks "what does the chart look like?" or "any patterns forming?"
- When `trading_strategy` needs confluence data for signal generation
- Automatically in the OODA Orient phase

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `analyze` | Full indicator suite | — | `df` (DataFrame), `timeframe` (str) |
| `detect_patterns` | Chart pattern detection with context scoring | — | `df` (DataFrame) |
| `find_levels` | Support/resistance, Fibonacci, pivots | — | `df` (DataFrame) |
| `full` | All of the above in one call (recommended) | — | `df` (DataFrame), `timeframe` (str) |

> If `df` is not passed, the skill auto-fetches 300 candles via PriceProvider
> to ensure warm-up for indicators like EMA 200.

## Input/Output Contract

### Reads From Context
- `context.market_data["candles"]` — OHLCV DataFrame (auto-fetched if missing)
- `context.market_data["timeframe"]` — Current timeframe (default "H1")
- `context.metadata["session_regime"]` — For pattern confidence adjustment
- `context.metadata["liquidity_zones"]` — For pattern confidence adjustment
- `context.metadata["market_intent"]` — For pattern confidence adjustment
- `context.analysis["calendar"]` — For high-impact news proximity check

### Writes To Context
- `context.analysis["indicators"]` — Full indicator suite with values and signals
- `context.analysis["patterns"]` — List of detected patterns with adjusted confidence
- `context.analysis["levels"]` — Support/resistance arrays, Fibonacci, pivots
- `context.metadata["technical_bias"]` — "BULLISH" / "BEARISH" / "NEUTRAL"
- `context.metadata["patterns"]` — Same as analysis.patterns for easy access
- `context.metadata["pattern_signal"]` — Aggregate pattern direction
- `context.metadata["pattern_context_applied"]` — True after adjustment

## Indicator Suite

| Indicator | Parameters | Signal Logic |
|-----------|-----------|--------------|
| **RSI** | period=14 | <30 oversold (bullish), >70 overbought (bearish) |
| **MACD** | fast=12, slow=26, signal=9 | Crossover direction + histogram |
| **EMA** | 20, 50, 200 | Price position relative to EMAs determines trend |
| **Bollinger Bands** | period=20, std=2 | Upper/lower band touch + squeeze detection |
| **ATR** | period=14 | Volatility measure in pips (used for stop sizing) |
| **ADX** | period=14 | <20 no trend, 20-40 trending, >40 strong trend |
| **Stochastic** | K=14, D=3, smooth=3 | <20 oversold, >80 overbought |

## Pattern Detection & Context-Aware Confidence

### Detected Patterns
- Head & Shoulders / Inverse H&S
- Double Top / Double Bottom
- Ascending/Descending/Symmetric Triangles
- Rising/Falling Channels
- Flag/Pennant formations

### Confidence Adjustment Rules
Every pattern starts with a base confidence (0.0-1.0) and is then adjusted:

| Factor | Adjustment | Condition |
|--------|-----------|-----------|
| **Weekend/Holiday session** | -30% | `session_regime` is weekend or holiday |
| **Asian session + reversal** | -20% | Reversal pattern during low-volume Asian hours |
| **Liquidity conflict** | -25% | Pattern direction conflicts with market intent |
| **Near sweep zone** | -20% | Pattern forms during active liquidity sweep |
| **Against trend** | -20% | H&S signal vs overall technical bias |
| **High-impact news** | -25% | High-impact event within 60 minutes |
| **Mid-range position** | -15% | Pattern at 40-60% of recent price range |
| **Session high/low** | +10% | Double Top/Bottom at session extremes |
| **Volume spike** | +15% | Last volume > 2× average (20-period) |
| **Strong zone break** | +15% | Price breaks level with strength ≥ 0.7 |

### Pattern Tracker Integration
When a `PatternTracker` is injected, the skill records each detection and
retrieves historical accuracy multipliers per pattern × timeframe, providing
a data-driven reliability score.

## Examples

### Example 1: Full Technical Scan (H1, London Session)
```
Action: full
Input: H1 candles (300 bars), session_regime="london"

Output:
📊 Technical Analysis
Bias: 🔴 Bearish

RSI: 42.3 (neutral)
MACD: -0.00023 (Bearish crossover)
BB: Lower band approach
ATR: 8.2 pips

🧩 Detected Patterns
🔴 Head & Shoulders (Bearish) — confidence: 0.62

📏 Key Levels
Supports: 1.08500, 1.08320, 1.08100
Resistances: 1.08900, 1.09050, 1.09200
```

### Example 2: Pattern Rejected Due to Insufficient Data
```
Action: full
Input: Only 30 candles available

Output: status=rejected, rejection_reason=insufficient_candle_data
  Required: 50 candles, Available: 30
```

## Edge Cases & Degraded Modes
- **Fewer than 50 candles**: Returns `status=rejected` with `insufficient_candle_data` reason. Downstream skills should not generate signals.
- **Provider unavailable + no cached data**: Returns `success=False`. The pipeline halts at this stage.
- **No patterns detected**: Returns empty patterns list — this is normal, not an error.
- **Missing session/liquidity context**: Patterns are returned with base confidence only (no adjustment). This is safe but less precise.

## Integration Chain
```
session_context ─┐
market_data ─────┤→ technical_analysis → risk_management → signal_executor
liquidity_awareness ─┘        ↓
                    trading_strategy (reads indicators + patterns)
                              ↓
                    uncertainty_assessment (reads divergence signals)
```

## Data Sufficiency
The skill requires a minimum of **50 candles** for reliable analysis.
For optimal results (especially EMA 200), **300 candles** are fetched
when auto-fetching from the provider. The `_has_sufficient_data()` gate
prevents unreliable analysis from propagating downstream.
