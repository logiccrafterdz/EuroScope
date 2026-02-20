# Correlation Monitor Skill

## Overview
Tracks correlations between EUR/USD and key related instruments:
- **DXY** (US Dollar Index) — strong inverse correlation
- **US10Y** (10-Year Treasury Yield) — interest rate differential driver
- **Gold (XAU/USD)** — risk sentiment proxy

## Actions
- `check_correlations`: Compute current correlations and detect divergences
- `detect_divergence`: Flag when EUR/USD diverges from its historical correlation

## How It Works
1. Fetches price data for EUR/USD and correlated instruments
2. Computes rolling correlations over 20/50 periods
3. Detects divergences (e.g., EUR/USD rising while DXY also rising)
4. Flags unusual correlation breakdowns

## Integration
- Uses `PriceProvider` for EUR/USD data
- Uses `yfinance` for DXY, US10Y, Gold data
- Stores results in `SkillContext.analysis["correlations"]`
