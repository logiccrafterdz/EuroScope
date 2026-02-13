# Prediction Tracker Skill

> Wraps the Memory system to provide prediction accuracy tracking and learning feedback

## Actions

| Action | Description | Parameters |
|--------|-------------|------------|
| `record` | Record a new prediction | `direction`, `confidence`, `reasoning`, `target_price?`, `timeframe?` |
| `evaluate` | Evaluate a past prediction | `pred_id`, `actual_direction`, `actual_price` |
| `accuracy_report` | Get accuracy stats | `days?` (default 30) |
| `get_learning_context` | Get LLM-ready learning insights | — |
