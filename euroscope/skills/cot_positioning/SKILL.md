---
name: cot_positioning
description: >
  Retrieves CFTC Net Positioning to evaluate long-term institutional bias for the Euro.
  Use this to understand macro positioning by non-commercial (speculative) traders.
---

# 🏦 COT Positioning Skill

## What It Does
Fetches the latest Commitment of Traders (COT) report from the CFTC and extracts the net positioning of non-commercial traders for the Euro. This provides a macro-level institutional bias that can supplement fundamental analysis.

## When To Use
- When analyzing long-term institutional sentiment.
- During fundamental analysis workflows.
- As a macroeconomic confirmation tool.

## Actions
| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_net_positioning` | Retrieve the latest COT data and compute bias | — | — |

## Integration Chain
```
cot_positioning ──→ fundamental_analysis
```
