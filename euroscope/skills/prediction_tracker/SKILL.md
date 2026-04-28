---
name: prediction_tracker
description: >
  Records the agent's directional predictions, evaluates them against actual
  outcomes, computes accuracy statistics, and generates learning context that
  is injected into the LLM system prompt. Use this skill when the agent makes
  a price prediction (BUY/SELL direction with confidence), when evaluating
  whether a past prediction was correct, when generating accuracy reports for
  briefings, or when the agent needs its own historical accuracy data to
  calibrate future confidence levels. This is the self-improvement feedback loop.
---

# 🎯 Prediction Tracker Skill

## What It Does
Enables the agent to learn from its own predictions. Every time the agent
makes a directional call (BUY/SELL/NEUTRAL with a confidence level), this
skill records it. Later, when the actual outcome is known, the prediction
is evaluated and accuracy statistics are updated.

The most powerful feature is `get_learning_context` — it generates a
structured summary of the agent's prediction accuracy that gets injected
into the LLM system prompt. This means the agent literally knows its own
track record and can adjust confidence accordingly.

## When To Use
- After `trading_strategy.detect_signal` produces a direction — record the prediction
- When a trade closes or a prediction window expires — evaluate against actual
- For daily briefings — include accuracy stats
- At system startup — inject learning context into the LLM prompt

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `record` | Record a new prediction | `direction`, `confidence` | `reasoning`, `target_price`, `timeframe` |
| `evaluate` | Evaluate a prediction against outcome | `pred_id`, `actual_direction` | `actual_price` |
| `accuracy_report` | Get accuracy statistics | — | `days` (int, default 30) |
| `get_learning_context` | Get learning summary for LLM prompt | — | — |

## Prediction Lifecycle
```
record ──→ [prediction stored with timestamp]
              ↓ (time passes, outcome known)
evaluate ──→ [accuracy updated, insight stored]
              ↓
accuracy_report ──→ [stats computed over N days]
              ↓
get_learning_context ──→ [injected into LLM system prompt]
```

## Learning Context Format
The `get_learning_context` output is designed for LLM consumption:
```
Your prediction accuracy (last 30 days):
- Overall: 62% (31/50 correct)
- BUY predictions: 68% accuracy
- SELL predictions: 55% accuracy
- High-confidence (>75%) accuracy: 71%
- Low-confidence (<50%) accuracy: 44%

Key insight: Your SELL predictions underperform. Consider requiring
stronger confirmation before SELL signals.
```

## Edge Cases & Degraded Modes
- **No memory/storage configured**: Returns `success=False`. Cannot track without persistence.
- **No predictions yet**: Returns empty report. Not an error.
- **Evaluation of non-existent prediction**: Returns error with pred_id.

## Integration Chain
```
trading_strategy ──→ prediction_tracker.record
                           ↓ (later)
signal_executor.close ──→ prediction_tracker.evaluate
                           ↓
                    prediction_tracker.get_learning_context
                           ↓
                    LLM system prompt (self-aware accuracy)
```

## Runtime Dependencies
- `Memory` — for prediction storage and retrieval
- `Storage` — for accuracy statistics queries
