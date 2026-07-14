---
name: volatility_forecast
description: >
  GARCH-based volatility forecasting that predicts near-term volatility regimes
  and provides confidence adjustments based on volatility clustering. Use this
  skill to anticipate volatility expansions/contractions, size positions
  appropriately, and adjust confidence before signal generation. Especially
  valuable before high-impact news events and during regime transitions.
---

# Volatility Forecast Skill

## What It Does
Forecasts near-term volatility using an exponentially weighted GARCH(1,1) model
applied to log returns. Identifies the current volatility regime (low / normal /
elevated / high / extreme), predicts whether volatility is expanding or
contracting, and provides a confidence multiplier that downstream skills use
to adjust position sizing and signal confidence.

Unlike simple ATR-based volatility measures, GARCH captures volatility
clustering — the tendency for high-volatility periods to be followed by
more high volatility. This gives the system a forward-looking edge.

## When To Use
- **Before trading_strategy** — to adjust confidence based on volatility regime
- **Before risk_management** — to anticipate ATR changes for stop/take-profit sizing
- **During news events** — to detect volatility expansion in real time
- **In briefings** — to report the current volatility regime and forecast

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `forecast` | Full volatility analysis with GARCH forecast | — | `candles` (DataFrame) |
| `regime` | Quick regime classification only | — | `candles` (DataFrame) |

## Input / Output Contract

### Reads from SkillContext
- `market_data.candles` — OHLCV DataFrame (auto-fetched if missing)

### Writes to SkillContext
- `analysis.volatility` — Full volatility analysis dict:
  - `current_vol` — Annualized current volatility
  - `forecast_vol` — GARCH(1,1) forecasted volatility
  - `regime` — "low" / "normal" / "elevated" / "high" / "extreme"
  - `expanding` — Boolean, is vol expanding?
  - `confidence_multiplier` — 0.0–1.0, applied to signal confidence
  - `annualized_range` — ATR-based annualized range estimate
  - `percentile_rank` — Where current vol sits in historical distribution

## GARCH(1,1) Model
- Uses log returns: r_t = ln(close_t / close_{t-1})
- Exponentially weighted with halflife=20 for recent data emphasis
- Parameters: omega=0, alpha=0.09, beta=0.90 (standard equity/FX defaults)
- σ²_t = ω + α·r²_{t-1} + β·σ²_{t-1}

## Volatility Regimes

| Regime | Annualized Vol | Confidence Mult | Behavior |
|--------|---------------|-----------------|----------|
| low | < 5% | 0.85 | Low opportunity, mean-reversion favored |
| normal | 5–10% | 1.00 | Standard conditions |
| elevated | 10–15% | 0.80 | Caution, wider stops needed |
| high | 15–25% | 0.50 | Reduce size, trend following only |
| extreme | > 25% | 0.20 | Risk-off, minimal trading |

## Edge Cases
- < 30 candles: returns default "normal" regime with warning
- All-zero prices: returns error
- Single-price series: returns vol=0, regime="low"
