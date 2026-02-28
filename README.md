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

## Recent Major Improvements (Last 14 Days)

### 🔴 Core Infrastructure & Data Integrity
- **Capital.com Institutional Integration**: 
  - **REST API**: Full order management with **Secure RSA Encryption** for automated authentication.
  - **WebSocket Streaming**: Migrated from polling to real-time tick-by-tick market data (Bid/Ask) for instantaneous trade evaluation.
  - **Zero-Latency Exits**: Integrated a new `SignalExecutor` that triggers SL/TP levels millisecond-perfect against incoming WS ticks.
- **Real-Time Data (Tiingo/OANDA)**: Replaced `yfinance` as the primary data source to eliminate the 15-minute delay. `MultiSourceProvider` now fetches institutional-grade 0s-delay quotes via **Tiingo** REST API (OANDA practice account supported for broker-grade accuracy).
- **ONNX-Quantized FinBERT Engine**: Upgraded sentiment analysis from `TextBlob` to a quantized `int8` ONNX version of `ProsusAI/finbert`. 
  - **Memory**: Model size reduced from 438MB to 110MB (65MB zipped) to fit 512MB RAM limits.
  - **Performance**: Inference speed increased by ~2x on CPU.
  - **Resilience**: Auto-extracting model support at runtime.
- **V3 Skills-Based Architecture**: Complete migration from monolithic handlers to an auto-discovering, asynchronous Skills Engine.
- **Stable Core**: Achieved **565 passing tests** with zero failures and zero deprecation warnings (asyncio/pandas 3.12 compatibility).

### 🟠 Advanced Analysis & Trading
- **COT (Commitments of Traders)**: Integrated weekly CFTC positioning data for structural sentiment context.
- **Advanced Liquidity Levels**: Automated tracking of PDH/PDL (Previous Day High/Low) and Weekly Liquidity levels.
- **Scenario-Based Reports**: Enhanced the orchestrator to generate multi-path scenarios (Bullish vs. Bearish parameters) instead of single-direction bias.
- **Volume Profile Optimization**: Refactored logic to use ATR-based momentum and Tick Volume for retail-broker accuracy.
- **Emergency Kill Switch**: Integrated a global `emergency_mode` triggered via Zenith Mini App or authenticated API.

### 🟡 UX & Mini-App Overhaul
- **Zenith Dashboard v5.0**: Complete UI overhaul. Consolidated "Backtest/Performance" into a single **Stats** tab.
- **Hidden System Overlays**: Moved debug consoles and API overrides into a logo-long-press overlay for cleaner mobile UX.
- **ReAct Intelligence**: Rebuilt the chat pipeline to use a **Reason-Act-Observe** loop for complex queries (`/comprehensive_analysis`).
- **Live Trades & History**: Direct backend integration for paper-trading journals in the Mini App.
- **Proactive Alerts**: Autonomous monitoring with deduplication and priority-based notifications.

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

## 🤖 Proactive Intelligence
EuroScope can autonomously monitor EUR/USD and send intelligent alerts without waiting for commands.

### How It Works
- Runs a ReAct loop every configured interval
- Decides if conditions warrant an alert
- Deduplicates alerts within a 60-minute window
- Prioritizes alerts as 🚨 urgent, ⚠️ medium, or ℹ️ low

### Example Alerts
- 🚨 URGENT: "Price sweeping liquidity below 1.0800 — reversal likely. Avoid shorts."
- ⚠️ MEDIUM: "Bullish breakout above 1.0850 with volume confirmation. Watch for pullback entry."
- ℹ️ LOW: "Market consolidating ahead of NY session. Wait for London close direction."

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
- `EUROSCOPE_TIINGO_KEY` — Tiingo API (Primary source for 0s delayed real-time data)
- `EUROSCOPE_RATE_LIMIT_REQUESTS` — Max commands per window (default: 5)
- `EUROSCOPE_RATE_LIMIT_WINDOW_MINUTES` — Rate limit window minutes (default: 1)
- `EUROSCOPE_VECTOR_MEMORY_TTL_DAYS` — Vector Memory retention in days (default: 30)
- `EUROSCOPE_PROACTIVE_CHAT_IDS` — Chat IDs for proactive alerts (comma-separated)
- `EUROSCOPE_PROACTIVE_INTERVAL_MINUTES` — Proactive analysis interval (default: 30)
- `EUROSCOPE_PROACTIVE_CACHE_MINUTES` — Deduplication window (default: 60)
- `EUROSCOPE_PROACTIVE_QUIET_HOURS` — Quiet hours in UTC, format `22-6`
- `EUROSCOPE_PROACTIVE_DISABLE_WEEKENDS` — Disable on weekends (1/0)
- `EUROSCOPE_PROACTIVE_HOLIDAYS` — Comma-separated holiday dates (YYYY-MM-DD)

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
**558+ tests** covering all modules:
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
- **ONNX Runtime & Optimum** (Quantized AI Inference)
- **Transformers (PyTorch)** (FinBERT Sentiment)
- **python-telegram-bot** (Async V21+)
- **DeepSeek & OpenAI** (Multi-LLM Agents)
- **ChromaDB** (Vector Memory)
- **Tiingo & OANDA** (Real-time Market Data)
- **Capital.com** (Institutional REST & WebSocket API)
- **SQLite** (Persistence & DB)
- **psutil** (Runtime monitoring)
- **websockets** (High-performance streaming)
- **pycryptodome** (RSA/AES Security)

## License
Private project.
