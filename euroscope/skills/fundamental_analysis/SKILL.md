---
name: fundamental_analysis
description: >
  Aggregates news sentiment, economic calendar events, FRED macro data (ECB/Fed
  rates, CPI, NFP), and narrative graph analysis for EUR/USD fundamental context.
  Use this skill whenever the agent needs to understand WHY the market is moving,
  not just HOW. Invoke when building complete market briefings, when a sudden
  price spike needs causal explanation, when macro data quality affects signal
  confidence, or when the user asks about news, economic events, or central
  bank policy. Essential for the OODA Orient phase alongside technical_analysis.
---

# 📰 Fundamental Analysis Skill

## What It Does
Provides the macro-economic and news context layer that technical analysis
alone cannot deliver. This skill answers the "why" behind price movements
by aggregating four data streams:

1. **News sentiment** — Real-time EUR/USD-relevant headlines with sentiment scores
2. **Economic calendar** — Upcoming high/medium/low impact events with forecasts
3. **Macro data** — FRED-sourced ECB/Fed rates, CPI, employment data with quality assessment
4. **Narrative graphs** — AI-extracted causal relationships between macro entities

The skill also performs **adaptive confidence scoring** — when macro data
is incomplete (partial EU or US data), it automatically reduces the confidence
of its output so downstream skills don't over-rely on degraded information.

## When To Use
- During the OODA Orient phase alongside `technical_analysis`
- When the agent needs to explain a sudden price movement (causal attribution)
- Before signal generation when macro context could override technical signals
- When the user asks "any news?", "what's the ECB doing?", or "why is EUR moving?"
- When `uncertainty_assessment` needs macro data to calibrate confidence adjustment
- For morning/daily briefings that combine technical and fundamental views

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_news` | Fetch latest EUR/USD-relevant news articles | — | — |
| `get_calendar` | Upcoming economic calendar events | — | — |
| `get_sentiment` | Aggregate news sentiment score | — | — |
| `get_macro` | Comprehensive FRED macro data with quality assessment | — | — |
| `get_narratives` | AI-extracted causal narrative graph | — | — |
| `full` | All of the above in one call | — | — |

## Input/Output Contract

### Reads From Context
- `context.metadata["causal_trigger"]` — If set by market_data, prioritizes explaining the spike

### Writes To Context
- `context.analysis["news"]` — List of news articles with sentiment scores
- `context.analysis["calendar"]` — Upcoming economic events
- `context.analysis["sentiment_summary"]` — `{sentiment, score, article_count}`
- `context.analysis["macro_data"]` — Full macro package with quality metadata
- `context.analysis["narratives"]` — Causal narrative graph entities
- `context.metadata["sentiment_data"]` — `{label, score, mood, cot_net}`
- `context.metadata["macro_quality"]` — "complete" / "partial_eu" / "partial_us" / "minimal"
- `context.metadata["fundamental_confidence"]` — 0.0-0.85 based on data quality
- `context.metadata["fundamental_bias"]` — "BULLISH" / "BEARISH" / "NEUTRAL"

## Sentiment Scoring

News articles are scored individually, then averaged:
```
avg_score = sum(article.sentiment_score) / count
sentiment = "bullish" if avg > 0.15 else "bearish" if avg < -0.15 else "neutral"
```

## Macro Data Quality & Adaptive Confidence

The macro provider fetches data from FRED for both EU and US economies.
When data sources are unavailable, the skill degrades gracefully:

| Data Quality | Available Data | Base Confidence | Adjustment |
|:------------|:--------------|:----------------|:-----------|
| `complete` | EU + US data | 0.85 | Full confidence |
| `partial_eu` | US only | 0.85 × 0.6 = 0.51 | 40% reduction |
| `partial_us` | EU only | 0.85 × 0.6 = 0.51 | 40% reduction |
| `minimal` | Neither | 0.85 × 0.3 = 0.26 | 70% reduction |

### Macro Impact Calculation
```
rate_differential = Fed_rate - ECB_rate
impact = "bearish" if differential > 1.0 else "bullish" if differential < 0 else "neutral"
```

## Narrative Graph Integration
When news is fetched, the skill asynchronously extracts causal relationships
using the LLM and stores them in a `NarrativeGraph`. This enables queries
like "what are the dominant macro narratives driving EUR/USD right now?"

The graph tracks entities (ECB, Fed, CPI, NFP, etc.) and their causal
relationships with weighted edges.

## Examples

### Example 1: Calendar Output
```
📅 Economic Calendar
🔴 14:30 USD: Non-Farm Payrolls
   Act: 263K  Fcst: 250K
🟠 10:00 EUR: CPI Flash Estimate
   Act:        Fcst: 2.4%
⚪ 15:45 USD: PMI Services
```

### Example 2: Degraded Macro Data
```
Macro analysis: Bearish bias (US data only — EU data missing)
Data quality: partial_eu
Confidence: 0.51
```

## Edge Cases & Degraded Modes
- **News engine unavailable**: `get_news` and `get_sentiment` return `success=False`. Calendar and macro proceed independently.
- **Calendar unavailable**: Returns `success=False` for that action only. Other actions unaffected.
- **FRED API down**: Macro data returns with `quality=minimal` and confidence=0.26. Downstream skills should not rely heavily on fundamental bias.
- **No articles found**: Sentiment returns `neutral` with score=0. This is safe, not an error.
- **Narrative extraction fails**: Silently logged. The main analysis pipeline is unaffected.

## Integration Chain
```
market_data ──→ fundamental_analysis ──→ uncertainty_assessment
                       ↓                         ↓
              context.metadata["fundamental_bias"]
              context.metadata["fundamental_confidence"]
                       ↓
              risk_management (macro override check)
              trading_strategy (bias confirmation)
```

## Runtime Dependencies
- `NewsEngine` — injected via `set_news_engine()`
- `EconomicCalendar` — injected via `set_calendar()`
- `MacroProvider` — injected via `set_macro_provider()`
- `LLM Router` — used internally for narrative extraction (via container)
