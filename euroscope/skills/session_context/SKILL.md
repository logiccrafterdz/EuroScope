---
name: session_context
description: Classifies current EUR/USD trading session and provides adaptive rules. Invoke at the start of analysis pipelines or before risk/strategy adjustments.
---

# 🕐 Session Context Skill

## What It Does
Detects the current EUR/USD trading session using UTC time and provides session-specific guidance for other skills.

## Actions
- `detect` — Classify the session and attach session rules to context metadata

## Outputs
- `context.metadata["session_regime"]`
- `context.metadata["session_rules"]`
