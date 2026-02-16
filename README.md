# <img src="assets/robot_logo.png" width="40" height="40" align="center"> EuroScope

**AI-powered expert bot specialized exclusively in the EUR/USD forex pair.**

EuroScope is a skills-based multi-agent system that provides institutional-grade analysis, pattern detection, macro data, AI forecasting, adaptive learning, and interactive Telegram control — all focused 100% on EUR/USD.

## Key Features

| Category | Features |
|:---|:---|
| **AI Brain** | Multi-Agent Specialists (Tech, Fund, Sentiment, Risk), Vector Memory (ChromaDB), LLM Router with fallback |
| **Skills Engine** | 9+ auto-discovered skills, Orchestrator, SkillsRegistry, dynamic prompt generation |
| **Trading** | Risk Management, Strategy Engine (Trend/MR/Breakout), Signal Executor, Paper Trading |
| **Analytics** | Performance Metrics (Sharpe/Sortino), Walk-Forward Backtesting, Equity Curves |
| **Analysis** | RSI, MACD, Patterns (H&S, Double Top), Fibonacci & Pivot levels, Sentiment |
| **Macro** | FRED & ECB integration (Rate differentials, CPI, GDP), Economic Calendar |
| **Learning** | Trade Journal, Prediction Tracker, Pattern Success Rates, Adaptive Parameter Tuner |
| **Telegram V3** | **Fully English Interface**, Inline keyboards, Smart Alerts, Cron Scheduler, Heartbeat Service |
| **Validation** | Behavioral Testing Suite (5 Scenarios), Historical Scenario Replay, Component Analysis |

## Bot Commands

| Command | Description |
|:---|:---|
| `/menu` | Main interactive dashboard |
| `/price` | Real-time EUR/USD quotes |
| `/analysis` | Full technical analysis report |
| `/chart` | Dark-themed candlestick chart |
| `/forecast` | AI directional outlook |
| `/news` | Live sentiment & headlines |
| `/signals` | Active trading signals |
| `/strategy` | Current strategy recommendation |
| `/risk` | Risk assessment for next trade |
| `/trades` | Paper trade history |
| `/performance` | ROI & Sharpe stats |
| `/report` | Full skills-based analysis pipeline |
| `/health` | System health & runtime stats |
| `/settings` | Personal alert preferences |

## 🤖 Smart Analysis Commands

### /comprehensive_analysis [query]
Full ReAct loop analysis with multi-step reasoning. Shows:
- Confidence score
- Reasoning process
- Tools used
- Final actionable recommendation

**Example:** `/comprehensive_analysis Should I trade EUR/USD now?`

### /quick_analysis
Faster analysis using simplified 2-step reasoning loop. Good for quick checks.

**Example:** `/quick_analysis`

### How It Works
The bot uses a **ReAct (Reason-Act-Observe)** framework:
1. **Reasons** about what information is needed
2. **Acts** by calling relevant tools (price, technicals, news, etc.)
3. **Observes** the results
4. **Repeats** until enough information is gathered
5. **Answers** with comprehensive, actionable analysis

## Quick Start

### 1. Clone & Install
```bash
git clone https://github.com/logiccrafterdz/EuroScope.git
cd EuroScope
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 2. Configure
```bash
copy .env.example .env
```
Edit `.env` with your API keys:
- `EUROSCOPE_LLM_API_KEY` — LLM provider (DeepSeek/OpenAI)
- `EUROSCOPE_LLM_FALLBACK_API_KEY` — Backup LLM API key for true failover redundancy (optional)
  Recommended: Use different provider (primary=DeepSeek, fallback=OpenAI)
- `EUROSCOPE_TELEGRAM_TOKEN` — From [@BotFather](https://t.me/BotFather)
- `EUROSCOPE_ADMIN_CHAT_IDS` — Admins bypass limits (comma-separated chat IDs)
- `EUROSCOPE_BRAVE_API_KEY` — News sentiment (optional)
- `EUROSCOPE_ALPHAVANTAGE_KEY` — AlphaVantage data (optional)
- `EUROSCOPE_FRED_API_KEY` — FRED macro data (optional)
- `EUROSCOPE_TIINGO_KEY` — Tiingo API (Recommended for Behavioral Validation)
- `EUROSCOPE_RATE_LIMIT_REQUESTS` — Max commands per window (default: 5)
- `EUROSCOPE_RATE_LIMIT_WINDOW_MINUTES` — Rate limit window minutes (default: 1)
- `EUROSCOPE_VECTOR_MEMORY_TTL_DAYS` — Vector Memory retention in days (default: 30)

### 3. Run
```bash
python -m euroscope.main
```

## Architecture (Skills-Based V3)

```
euroscope/
├── skills/              # 9+ auto-discovered skills
│   ├── base.py          # BaseSkill, SkillResult, SkillContext
│   ├── registry.py      # Auto-discovery & LLM prompt generation
│   ├── market_data/     # Price & OHLCV data
│   ├── technical_analysis/
│   ├── pattern_detection/
│   ├── fundamental/
│   ├── signals/
│   ├── backtesting/     # Walk-forward + slippage
│   ├── monitoring/      # Health + runtime stats
│   ├── trade_journal/   # Full-context trade logging
│   └── prediction_tracker/
├── brain/               # AI Agent, Memory (ChromaDB), Orchestrator
├── learning/            # Pattern Tracker, Adaptive Tuner
├── automation/          # HeartbeatService, CronScheduler, EventBus, SmartAlerts
├── bot/                 # Telegram V3 (Skills-Based)
├── trading/             # Risk, Strategy Engine, Signal Executor
├── analytics/           # Performance, Backtesting, Health Monitor
├── data/                # Providers, News, Calendar, Storage (SQLite)
├── forecast/            # AI Forecasting
├── workspace/           # IDENTITY.md, SOUL.md, TOOLS.md, MEMORY.md
└── utils/               # Charts, Logging, Formatting, Resilience
```

### How Skills Work
Each skill lives in its own folder under `skills/` with:
- `SKILL.md` — Description and capabilities
- `skill.py` — Implementation extending `BaseSkill`
- `__init__.py` — Exports

The `SkillsRegistry` auto-discovers skills at startup. The `Orchestrator` routes requests and assembles multi-skill analysis pipelines.

## Testing
**406+ tests** covering all modules:
```bash
python -m pytest tests/
python -m pytest tests/
```

### Behavioral Validation
Run comprehensive behavioral tests against historical market scenarios:
```bash
python -m euroscope.testing.report_generator --output behavioral_report.md
```
This validates the bot's logic against:
1.  **Sideways Market Trap** (Avoiding false signals in chop)
2.  **Lagarde Shock** (Emergency response to news events)
3.  **Liquidity Sweep** (Detecting stop hunts)
4.  **Session Transition** (Handling market open volatility)
5.  **Macro Override** (Fundamental data impact)

## Vector Memory Maintenance
EuroScope cleans up old vector memory documents to keep semantic search fast.

Retention window:
```env
EUROSCOPE_VECTOR_MEMORY_TTL_DAYS=60
```

Manual cleanup:
```python
from euroscope.brain.vector_memory import VectorMemory
memory = VectorMemory()
await memory.cleanup_old_documents(ttl_days=30)
```

## Tech Stack
- **Python 3.12+**
- **python-telegram-bot** (Async)
- **DeepSeek & OpenAI** (Multi-LLM)
- **ChromaDB** (Vector Memory)
- **DeepSeek & OpenAI** (Multi-LLM)
- **ChromaDB** (Vector Memory)
- **Tiingo** & **yfinance** & **pandas**
- **SQLite** (Persistence)
- **psutil** (Runtime monitoring)

## License
Private project.
