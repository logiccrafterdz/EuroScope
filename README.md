# <img src="assets/robot_logo.png" width="40" height="40" align="center"> EuroScope

**AI-powered expert bot specialized exclusively in the EUR/USD forex pair.**

EuroScope is a skills-based multi-agent system that provides institutional-grade analysis, pattern detection, macro data, AI forecasting, adaptive learning, and interactive Telegram control — all focused 100% on EUR/USD.

## 🚀 Key Features

| Category | Features |
|:---|:---|
| 🧠 **AI Brain** | Multi-Agent Specialists (Tech, Fund, Sentiment, Risk), Vector Memory (ChromaDB), LLM Router with fallback |
| 🔧 **Skills Engine** | 9+ auto-discovered skills, Orchestrator, SkillsRegistry, dynamic prompt generation |
| 🛡️ **Trading** | Risk Management, Strategy Engine (Trend/MR/Breakout), Signal Executor, Paper Trading |
| 📊 **Analytics** | Performance Metrics (Sharpe/Sortino), Walk-Forward Backtesting, Equity Curves |
| 🔍 **Analysis** | RSI, MACD, Patterns (H&S, Double Top), Fibonacci & Pivot levels, Sentiment |
| 📰 **Macro** | FRED & ECB integration (Rate differentials, CPI, GDP), Economic Calendar |
| 📓 **Learning** | Trade Journal, Prediction Tracker, Pattern Success Rates, Adaptive Parameter Tuner |
| 🤖 **Telegram V3** | Inline keyboards, Smart Alerts, Cron Scheduler, Heartbeat Service |

## 🤖 Bot Commands

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

## 🛠️ Quick Start

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
- `EUROSCOPE_TELEGRAM_TOKEN` — From [@BotFather](https://t.me/BotFather)
- `EUROSCOPE_BRAVE_API_KEY` — News sentiment (optional)
- `EUROSCOPE_ALPHAVANTAGE_KEY` — AlphaVantage data (optional)
- `EUROSCOPE_FRED_API_KEY` — FRED macro data (optional)

### 3. Run
```bash
python -m euroscope.main
```

## 🏗️ Architecture (Skills-Based V3)

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

## 🧪 Testing
**406+ tests** covering all modules:
```bash
python -m pytest tests/
```

## 🧰 Tech Stack
- **Python 3.12+**
- **python-telegram-bot** (Async)
- **DeepSeek & OpenAI** (Multi-LLM)
- **ChromaDB** (Vector Memory)
- **yfinance** & **pandas**
- **SQLite** (Persistence)
- **psutil** (Runtime monitoring)

## ⚖️ License
Private project.
