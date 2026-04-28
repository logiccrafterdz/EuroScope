# EuroScope Skills Catalog

> Auto-discoverable skill inventory for the EuroScope trading agent.
> Each skill is a self-contained module with a `SKILL.md` providing
> rich documentation following the Anthropic Agent Skills standard.

## Execution Chains

### Full Analysis Pipeline (OODA Loop)
```
session_context ─────────────────────────────────────────────────────┐
market_data ──→ liquidity_awareness ──→ technical_analysis ──→       │
correlation_monitor ──→                                              │
fundamental_analysis ──→ multi_timeframe_confluence ──→              │
uncertainty_assessment ──→ trading_strategy ──→ risk_management ──→  │
signal_executor                                                      │
       ↓                                                             │
trade_journal (auto-log) ──→ prediction_tracker                     │
       ↓                                                             │
performance_analytics                                                │
```

### Quick Price Check
```
market_data.get_price
```

### Health Check
```
monitoring.check_health → monitoring.format_dashboard
```

### Strategy Backtest
```
market_data.get_candles → backtesting.run → performance_analytics.format_report
```

### Emergency Response
```
deviation_monitor (auto) → emergency_mode → signal_executor (blocked)
```

---

## Skills by Category

### 📊 Data (2 skills)

| Skill | Actions | Dependencies | Description |
|:------|:--------|:-------------|:------------|
| [market_data](market_data/SKILL.md) | `get_price`, `get_candles`, `check_market_status`, `get_correlation` | PriceProvider | Real-time and historical EUR/USD data gateway |
| [correlation_monitor](correlation_monitor/SKILL.md) | `check_correlations`, `detect_divergence` | yfinance | DXY, US10Y, Gold correlation tracking |

### 📈 Analysis (7 skills)

| Skill | Actions | Dependencies | Description |
|:------|:--------|:-------------|:------------|
| [session_context](session_context/SKILL.md) | `detect` | System clock | Session classification + adaptive rules |
| [technical_analysis](technical_analysis/SKILL.md) | `analyze`, `detect_patterns`, `find_levels`, `full` | PriceProvider, TechnicalAnalyzer | Indicators, patterns, key levels |
| [liquidity_awareness](liquidity_awareness/SKILL.md) | `analyze` | — | Institutional zone detection + intent inference |
| [multi_timeframe_confluence](multi_timeframe_confluence/SKILL.md) | `confluence`, `check_alignment` | PriceProvider | M15/H1/H4/D1 alignment scoring |
| [fundamental_analysis](fundamental_analysis/SKILL.md) | `get_news`, `get_calendar`, `get_sentiment`, `get_macro`, `get_narratives`, `full` | NewsEngine, Calendar, MacroProvider | News, macro, sentiment analysis |
| [cot_positioning](cot_positioning/SKILL.md) | `get_net_positioning` | COTProvider | CFTC Net Positioning for institutional bias |
| [uncertainty_assessment](uncertainty_assessment/SKILL.md) | `assess` | VectorMemory, PatternTracker | 3-layer uncertainty quantification |

### 🎯 Trading (3 skills)

| Skill | Actions | Dependencies | Description |
|:------|:--------|:-------------|:------------|
| [trading_strategy](trading_strategy/SKILL.md) | `detect_signal`, `list_strategies` | StrategyEngine | Multi-strategy signal generation |
| [risk_management](risk_management/SKILL.md) | `assess_trade`, `position_size`, `stop_loss`, `take_profit` | Config | Adaptive stops + dynamic sizing |
| [signal_executor](signal_executor/SKILL.md) | `open_trade`, `close_trade`, `list_trades`, `trade_history`, `update_trade` | Storage, Config, SafetyGuardrail | Trade execution with 6 guardrails |

### 📊 Analytics (4 skills)

| Skill | Actions | Dependencies | Description |
|:------|:--------|:-------------|:------------|
| [performance_analytics](performance_analytics/SKILL.md) | `compute_metrics`, `get_snapshot`, `breakdown`, `format_report` | Storage | Sharpe, Sortino, drawdown, win rate |
| [prediction_tracker](prediction_tracker/SKILL.md) | `record`, `evaluate`, `accuracy_report`, `get_learning_context` | Memory, Storage | Self-improving accuracy tracking |
| [trade_journal](trade_journal/SKILL.md) | `log_trade`, `close_trade`, `get_journal`, `get_stats` | Storage | Full-context trade logging + learning |
| [backtesting](backtesting/SKILL.md) | `run`, `compare`, `walk_forward`, `format_result` | BacktestEngine, PriceProvider | Historical strategy validation |

### 🏥 System (2 skills)

| Skill | Actions | Dependencies | Description |
|:------|:--------|:-------------|:------------|
| [monitoring](monitoring/SKILL.md) | `check_health`, `track_error`, `get_status`, `format_dashboard`, `runtime_stats` | HealthMonitor, psutil | System health + resource monitoring |
| [deviation_monitor](deviation_monitor/SKILL.md) | `start` | EventBus, MarketDataSkill | Anomaly detection + emergency halt |

---

## Skill Architecture

### SKILL.md Standard (Anthropic-aligned)
Every skill directory contains:
```
skill_name/
├── SKILL.md        # Rich documentation with YAML frontmatter
├── skill.py        # BaseSkill implementation
├── __init__.py     # Module init
└── [references/]   # Optional domain docs
```

### YAML Frontmatter
```yaml
---
name: skill_name
description: >
  Rich, trigger-oriented description. Explains WHEN and WHY
  to use this skill, not just what it does.
---
```

### Discovery
The `SkillsRegistry` scans `euroscope/skills/*/` for directories containing
`skill.py`. Each skill's `SKILL.md` frontmatter description is injected
into the LLM system prompt via `get_tools_prompt()`, enabling the agent
to autonomously select the right skill for each situation.

### Dependency Resolution
Skills declare their dependencies via:
```python
dependencies: list[str] = ["session_context", "market_data"]
```
The registry's `get_execution_order(target_skill)` resolves the DAG
using topological sort, ensuring prerequisites run first.

---

## Total: 18 Skills | 50+ Actions | 5 Categories
