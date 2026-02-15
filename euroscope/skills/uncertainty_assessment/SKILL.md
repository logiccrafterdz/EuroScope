---
name: uncertainty_assessment
description: Quantifies cognitive uncertainty from technical, causal, and behavioral context
---

# 🧭 Uncertainty Assessment Skill

## What It Does
Computes a composite uncertainty score from technical divergence, causal mismatch, and behavioral context (session + liquidity intent).

## Actions
- `assess` — Calculate uncertainty score, confidence adjustment, and high-uncertainty flag

## Inputs
- Current indicators, patterns, and last 20 candles from context

## Returns
- `uncertainty_score`, `confidence_adjustment`, `high_uncertainty`, `market_regime`
