---
name: correlation_monitor
description: >
  Tracks EUR/USD correlations with DXY, US 10Y yields, and Gold to detect
  divergences that signal unusual market regimes. Use this skill when the agent
  needs to confirm directional bias with cross-market evidence, when preparing
  risk assessments that consider macro alignment, or when a divergence warning
  could prevent a false signal. Invoke during the analysis phase alongside
  technical_analysis for a multi-dimensional market view.
---

# 🔗 Correlation Monitor Skill

## What It Does
Monitors the relationship between EUR/USD and three key macro instruments
to detect when correlations break down — a powerful signal for regime changes,
pending reversals, or increased uncertainty.

The forex market doesn't move in isolation. EUR/USD has well-documented
correlations with macro instruments, and when those correlations break, it
often signals something important is happening. This skill quantifies those
relationships and raises flags when things diverge from historical norms.

### Tracked Instruments
| Instrument | Ticker | Expected Correlation | Rationale |
|:-----------|:-------|:---------------------|:----------|
| **DXY** (Dollar Index) | DX-Y.NYB | **-0.85** (strong inverse) | EUR is ~57% of DXY basket |
| **US 10Y Yield** | ^TNX | **-0.40** (moderate inverse) | Higher yields → stronger USD → weaker EUR |
| **Gold (XAU/USD)** | GC=F | **+0.50** (moderate positive) | Both are anti-USD assets |

## When To Use
- During the **analysis phase** of the OODA loop, alongside technical_analysis
- Before generating signals — divergence = increased uncertainty
- When the agent detects conflicting technical signals and needs macro confirmation
- When risk_management needs to adjust position sizing based on correlation risk
- When a sudden move in EUR/USD lacks technical explanation — check if DXY/Gold confirm it

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `check_correlations` | Compute correlations for all tracked instruments | — | `period` (str, default "1mo"), `interval` (str, default "1d") |
| `detect_divergence` | Focus specifically on divergence detection | — | `period`, `interval` |

## Input/Output Contract

### Reads From Context
- Nothing directly — fetches its own data via yfinance

### Writes To Context
- `context.analysis["correlations"]` — Full correlation analysis object
- `context.metadata["correlation_warning"]` — `True` when divergences detected
- `context.metadata["divergence_count"]` — Number of diverging instruments

### Output Structure
```json
{
  "instruments": {
    "DX-Y.NYB": {
      "label": "DXY (Dollar Index)",
      "correlation_20d": -0.812,
      "correlation_full": -0.756,
      "expected": -0.85,
      "deviation": 0.094,
      "is_diverging": false,
      "eur_direction": "UP",
      "instrument_direction": "DOWN"
    }
  },
  "divergences": [],
  "divergence_count": 0,
  "analyzed_at": "2026-04-28T12:00:00+00:00",
  "period": "1mo"
}
```

## Divergence Detection Logic
A divergence is flagged when the actual correlation deviates from the expected
correlation by more than **0.40**:

```
deviation = |actual_correlation - expected_correlation|
is_diverging = deviation > 0.40
```

**Example**: DXY expected correlation = -0.85, actual = -0.30 → deviation = 0.55 → **DIVERGING**

This threshold (0.40) balances sensitivity with noise. Correlations naturally
fluctuate, but a 0.40+ deviation represents a statistically significant
structural change in the market relationship.

### What Divergences Mean
- **DXY divergence**: EUR/USD and Dollar Index moving in the same direction — possible structural shift or intervention risk
- **Yield divergence**: Interest rate expectations disconnecting from currency — look for central bank surprises
- **Gold divergence**: Risk sentiment misalignment — possible risk-on/risk-off regime change

## Edge Cases & Degraded Modes
- **yfinance unavailable**: Returns `success=False`. The system continues without correlation data.
- **Insufficient data alignment** (<10 common data points): Skips that instrument with a warning.
- **Weekend/Holiday**: yfinance returns stale data — correlations are valid but based on last available trading data.
- **All instruments fail**: Returns `success=False`. Risk management should use conservative sizing.

## Integration Chain
```
market_data ──→ correlation_monitor ──→ risk_management (sizing adjustment)
                       ↓
              uncertainty_assessment (divergence increases uncertainty)
```

The `risk_management` skill reads `context.market_data["correlation"]` to apply
correlation-based position sizing multipliers (GBP/USD > 0.75 → +15% size,
USD/CHF < -0.75 → +15% size, confirming EUR/USD bias).

## Runtime Dependencies
- `yfinance` — for DXY, US10Y, Gold data fetching
- `PriceProvider` — optional, for EUR/USD data (fallback to yfinance)
