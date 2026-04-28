---
name: trading_strategy
description: >
  Multi-strategy signal generation with confluence scoring. Detects trading
  signals using Trend Following (EMA cross + MACD + ADX), Mean Reversion
  (Bollinger + RSI), and Breakout (channel break + volatility expansion)
  strategies. Use this skill after technical_analysis provides indicator data
  and before risk_management sizes the trade. Also applies MTF confirmation,
  regime memory penalties/boosts, pattern multipliers, and emergency fallback
  mode. Invoke when the agent needs to decide BUY/SELL/WAIT with reasoning.
---

# 🎯 Trading Strategy Skill

## What It Does
The decision engine of EuroScope. Takes the full indicator suite, detected
patterns, and price levels from technical_analysis, then runs three
independent strategy algorithms to find the best trading opportunity.
Each strategy votes with a confidence score, and the engine selects
the highest-conviction signal.

What makes this skill sophisticated is its multi-layer filtering:
1. **Strategy engine** produces a raw signal
2. **MTF confirmation** checks if higher timeframes agree (50% penalty if not)
3. **Regime memory** compares current conditions to historical outcomes
4. **Pattern multipliers** adjust confidence based on pattern reliability data
5. **Uncertainty gate** blocks signals during high uncertainty

## When To Use
- After `technical_analysis.full` provides indicators, patterns, and levels
- After `uncertainty_assessment.assess` provides confidence adjustment
- Before `risk_management.assess_trade` — it needs direction and confidence
- When the agent is in the OODA Decide phase
- When the user asks "should I trade?" or "any signals?"

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `detect_signal` | Run strategy detection on current market conditions | — | `indicators`, `levels`, `patterns` |
| `list_strategies` | List available strategy names | — | — |

## Strategy Algorithms

### 1. Trend Following
**Logic**: EMA crossover direction + MACD confirmation + ADX trend strength

| Condition | Threshold | Signal |
|-----------|----------|--------|
| EMA 20 > EMA 50 + MACD bullish + ADX > 25 | — | BUY |
| EMA 20 < EMA 50 + MACD bearish + ADX > 25 | — | SELL |
| ADX < 20 | — | WAIT (no trend) |

### 2. Mean Reversion
**Logic**: Bollinger Band touch + RSI extreme + Stochastic confirmation

| Condition | Threshold | Signal |
|-----------|----------|--------|
| Price at lower BB + RSI < 30 + Stoch oversold | — | BUY |
| Price at upper BB + RSI > 70 + Stoch overbought | — | SELL |

### 3. Breakout
**Logic**: Channel/range break + volatility expansion (ATR spike) + volume

| Condition | Threshold | Signal |
|-----------|----------|--------|
| Break above resistance + ATR expanding + volume surge | — | BUY |
| Break below support + ATR expanding + volume surge | — | SELL |

## Multi-Layer Filtering

### MTF Confirmation Check
When `multi_timeframe_confluence` has run and provided `mtf_bias`:
- Signal BUY + MTF bearish → **50% confidence penalty** + warning
- Signal SELL + MTF bullish → **50% confidence penalty** + warning
- Signal aligns with MTF → no adjustment

### Regime Memory Bank
Queries `VectorMemory` for similar past market conditions (ADX, RSI, MACD, volatility, macro):
- Similar regimes won < 33% of time → **40% confidence penalty**
- Similar regimes won > 66% of time → **20% confidence boost** (capped at 95%)

### Pattern Multipliers
When `PatternTracker` provides historical accuracy data per pattern × timeframe:
```
adjusted_confidence = base_confidence × average_pattern_multiplier
```

### Emergency Fallback Mode
When `emergency_mode` is active in context, the skill bypasses the full
strategy engine and falls back to pure technical signals:
- ADX > 25 + RSI/MACD aligned → STRONG_SIGNAL (80% confidence)
- ADX < 20 → NEUTRAL (0% confidence, WAIT)
- Otherwise → WEAK_SIGNAL (50% confidence)

## Input/Output Contract

### Reads From Context
- `context.analysis["indicators"]` — Full indicator suite (required)
- `context.analysis["levels"]` — Support/resistance (required)
- `context.analysis["patterns"]` — Detected patterns
- `context.analysis["macro_data"]` — For macro-aware strategy selection
- `context.metadata["confidence_adjustment"]` — From uncertainty_assessment
- `context.metadata["high_uncertainty"]` — Blocks signal if true
- `context.metadata["mtf_bias"]` — Multi-timeframe verdict
- `context.metadata["emergency_mode"]` — Triggers fallback mode
- `context.metadata["pattern_multipliers"]` — Pattern reliability data
- `context.user_prefs` — Strategy preferences

### Writes To Context
- `context.signals` — `{direction, strategy, confidence, entry_price, reasoning, regime}`
- `context.metadata["regime"]` — "trending" / "ranging" / "transitional"

## Examples

### Example 1: Trend Following Signal
```
🎯 Trading Signal
🟢 BUY
Strategy: trend_following
Confidence: 72.5%
Regime: trending
Entry: 1.08750

📝 Reasoning:
• EMA bullish crossover confirmed
• MACD histogram positive and expanding
• ADX at 32 confirms strong trend
```

### Example 2: Blocked by Uncertainty
```
🎯 Trading Signal
⚪ WAIT
Strategy: uncertain
Confidence: 0%
Regime: ranging

📝 Reasoning:
• High uncertainty without macro confirmation
• ADX below threshold
```

## Edge Cases & Degraded Modes
- **Missing ADX or RSI**: Returns `success=False` with specific error ("ADX is missing" / "RSI is missing"). Cannot generate signals without core indicators.
- **Emergency mode**: Falls back to technical-only analysis. Reduced confidence but functional.
- **Vector memory unavailable**: Skips regime memory check. Signal proceeds with base confidence.
- **No patterns detected**: Pattern multipliers = 1.0 (no adjustment). Normal operation.
- **All strategies return WAIT**: Returns WAIT with 0% confidence. This is correct — sometimes the best trade is no trade.

## Integration Chain
```
technical_analysis ──→ trading_strategy ──→ risk_management ──→ signal_executor
uncertainty_assessment ─┘        ↓
multi_timeframe_confluence ─────→│
```
