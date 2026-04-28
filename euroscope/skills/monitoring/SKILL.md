---
name: monitoring
description: >
  System health monitoring: checks DB connectivity, API key validity, price
  provider status, agent state, cron scheduler health, and process-level
  resource usage (uptime, memory, CPU). Use this skill when the user asks
  "/health" or "/status", when the system needs a self-diagnostic, when
  generating operational dashboards, or when other skills need to verify
  that their runtime dependencies are healthy. Also use for error tracking
  and runtime statistics. This is the operational backbone of EuroScope.
---

# 🏥 Monitoring Skill

## What It Does
The operations center of EuroScope. Performs comprehensive health checks
across all system components, tracks errors, monitors resource usage,
and generates formatted dashboards for Telegram display.

Unlike analysis skills that look at markets, this skill looks inward —
ensuring that the system itself is healthy enough to make reliable
trading decisions.

## When To Use
- When the user sends `/health` or `/status` via Telegram
- At system startup to verify all components initialized correctly
- Periodically (via cron) for automated health monitoring
- When the agent detects errors and needs to report system state
- When debugging — to quickly see what's working and what's not

## Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `check_health` | Full system health check | — | — |
| `track_error` | Record an error for a component | `component` (str), `error` (str) | — |
| `get_status` | Quick overall status | — | — |
| `format_dashboard` | Generate formatted health dashboard for Telegram | — | — |
| `runtime_stats` | Process-level stats (uptime, memory, CPU) | — | — |

## Health Check Components

The `check_health` action runs the `HealthMonitor` which checks:

| Component | What's Checked | Healthy When |
|-----------|---------------|-------------|
| **Database** | SQLite connectivity, table existence | Connection OK, tables present |
| **API Keys** | OANDA, FRED, Telegram tokens configured | Non-empty values in config |
| **Price Provider** | Can fetch a live quote | Returns valid price data |
| **Agent** | LLM router responsive | Agent instance exists and responds |
| **Cron Scheduler** | Scheduled jobs running | Scheduler active with jobs queued |
| **Error History** | Recent error count | Below threshold (configurable) |

### Health Report Structure
```json
{
  "overall": "healthy",
  "components": {
    "database": {"status": "ok", "details": "..."},
    "api_keys": {"status": "ok", "details": "..."},
    "provider": {"status": "ok", "details": "..."},
    "agent": {"status": "ok", "details": "..."},
    "cron": {"status": "ok", "details": "..."}
  },
  "error_count_24h": 3,
  "uptime": "12h 30m 45s"
}
```

## Runtime Statistics

The `runtime_stats` action provides process-level metrics:

```
🏥 Runtime Stats

⏱ Uptime: 12h 30m 45s
💾 Memory: 245.3 MB
🖥 CPU: 2.3%
🔧 PID: 12345
```

Uses `psutil` for accurate cross-platform resource measurement.

## Dashboard Format (Telegram)
```
🏥 EuroScope Health Dashboard

✅ Database: Connected
✅ API Keys: All configured
✅ Provider: OANDA responding (1.08750)
✅ Agent: LLM router active
⚠️ Cron: 2 jobs delayed

Overall: 🟢 Healthy
Uptime: 12h 30m | Memory: 245 MB | Errors (24h): 3
```

## Error Tracking
The `track_error` action records errors per component:
```python
monitor.record_error("price_provider", "Connection timeout after 30s")
```
Errors are timestamped and count toward health degradation thresholds.

## Edge Cases & Degraded Modes
- **Storage unavailable**: Health check itself still runs but database check reports failure. Error tracking is disabled.
- **Provider unavailable**: Reports `provider: down` but other components checked normally.
- **psutil unavailable**: `runtime_stats` returns `success=False`. Other actions unaffected.
- **Agent not injected**: Reports `agent: unknown` status.

## Integration Chain
```
cron (periodic) ──→ monitoring.check_health ──→ Telegram dashboard
user command ──────→ monitoring.format_dashboard ──→ formatted response
any skill error ──→ monitoring.track_error ──→ error history
```

## Runtime Dependencies
- `HealthMonitor` — internal health check engine
- `Storage` — for error history persistence
- `PriceProvider` — for provider health check
- `Agent` — for agent status check
- `CronScheduler` — for scheduler health check
- `psutil` — for runtime statistics
