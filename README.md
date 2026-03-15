<div align="center">
  <img src="assets/robot_logo.png" alt="EuroScope Logo" width="200">
</div>

# EuroScope

**Autonomous AI Agent specialized exclusively in the EUR/USD forex pair.**

EuroScope is an always-on trading intelligence agent that continuously monitors EUR/USD, forms market theses, and makes autonomous decisions. It combines a skills-based multi-agent architecture with an OODA-loop cognitive framework, institutional-grade analysis, adaptive learning, and real-time Telegram control.

> **System Status:** Fully operational as an autonomous agent. The system runs a 30-second heartbeat loop, maintains a structured world model, tracks trading convictions with evidence-based confidence decay, and generates session-aware game plans.

---

## Architecture Overview

EuroScope operates as an **autonomous agent**, not a chatbot. The core difference:

| Aspect | Old (Chatbot) | New (Agent) |
|:---|:---|:---|
| **Behavior** | Waits for user commands | Continuously monitors and acts |
| **Decision Making** | One-off analysis per request | Conviction-based with evidence tracking |
| **Market Awareness** | Fetches data on demand | Maintains a persistent World Model |
| **Planning** | None | Session-aware game plans with If-Then scenarios |
| **Identity** | Helpful assistant | Senior EUR/USD analyst briefing a portfolio manager |

### Cognitive Loop (OODA)

The Agent Core runs a state machine that follows the **Observe → Orient → Decide → Act** cycle every 30 seconds:

```
┌─────────────────────────────────────────────────────────┐
│                    CRON HEARTBEAT (30s)                  │
│                         │                               │
│                    ┌────▼────┐                           │
│                    │  IDLE   │◄──────────────────┐       │
│                    └────┬────┘                   │       │
│                         │ tick()                 │       │
│                    ┌────▼────┐                   │       │
│                    │OBSERVING│ ← run_scan()      │       │
│                    └────┬────┘                   │       │
│                         │ deltas?                │       │
│                    ┌────▼────┐                   │       │
│                    │ORIENTING│ ← World Model     │       │
│                    │         │   update           │       │
│                    └────┬────┘                   │       │
│                         │                        │       │
│                    ┌────▼────┐                   │       │
│                    │DECIDING │ ← LLM reasoning   │       │
│                    └────┬────┘                   │       │
│                    ┌────▼────┐                   │       │
│                    │ ACTING  │ ← Execute/Alert   │       │
│                    └────┬────┘                   │       │
│                         │                        │       │
│                    ┌────▼────┐                   │       │
│                    │REVIEWING│ ← Track outcomes  ─┘       │
│                    └─────────┘                           │
└─────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. World Model (`brain/world_model.py`)
A structured, always-current representation of the EUR/USD market state. Contains 8 sub-models:

| Sub-Model | What It Tracks |
|:---|:---|
| **PriceState** | Current price, daily range, pip change, spread |
| **TechnicalState** | RSI, MACD, ADX, trend direction, support/resistance |
| **FundamentalState** | ECB/Fed rate differential, CPI, GDP, NFP |
| **SentimentState** | FinBERT score, COT positioning, retail sentiment |
| **RegimeState** | Trending/Ranging/Breakout/Volatile classification |
| **RiskState** | Open exposure, drawdown, daily P&L |
| **LiquidityState** | PDH/PDL levels, weekly highs/lows, spread |
| **SessionState** | Active session (London/NY/Asia/Overlap), time-of-day |

Each sub-model includes **delta detection** — the agent only reasons about what has *changed* since the last tick.

### 2. Conviction System (`brain/conviction.py`)
The agent forms, maintains, and invalidates trading theses:

- **Evidence-based**: Every conviction is backed by specific data points
- **Confidence decay**: Convictions lose strength over time without reinforcing evidence
- **Auto-invalidation**: If price hits an invalidation level, the conviction is killed immediately
- **Multi-conviction**: The agent can hold multiple theses simultaneously (e.g., short-term bearish + long-term bullish)

### 3. Agent Core (`brain/agent_core.py`)
The main state machine with 8 states: `IDLE → OBSERVING → ORIENTING → DECIDING → ACTING → MONITORING → PLANNING → REVIEWING`. Drives the autonomous loop and coordinates all other components.

### 4. Session Planner (`brain/session_planner.py`)
Generates daily trading game plans before each major session opens:

- **London Session Plan**: Generated before 07:00 UTC
- **New York Session Plan**: Generated before 12:00 UTC
- Each plan includes 1-3 **If-Then scenarios** with entry zones, invalidation levels, and targets
- Plans are enriched by LLM using the current World Model and active convictions

### 5. LLM Interface (`brain/llm_interface.py`)
Handles all LLM interactions (formerly `agent.py`):

- `chat()` — Conversational responses for Telegram
- `run_react_loop()` — Multi-step reasoning with tool calling
- `reason_about()` — Internal deliberation for the Agent Core (no direct action)
- `call_stateless()` — One-shot LLM calls for specific tasks

### 6. Orchestrator (`brain/orchestrator.py`)
Coordinates skills to produce analysis. Includes two new Agent Core APIs:

- `run_scan()` — Lightweight price + session check (<2s)
- `get_quick_state()` — Instant market snapshot without full pipeline
- `run_full_analysis_pipeline()` — Complete multi-skill analysis

---

## Key Features

| Category | Features |
|:---|:---|
| **Agent Brain** | OODA Loop, World Model, Conviction Tracker, Session Planner, LLM Interface |
| **Skills Engine** | 9+ auto-discovered skills, Orchestrator, SkillsRegistry, dynamic prompt generation |
| **Trading** | Risk Management, Strategy Engine (Trend/MR/Breakout), Signal Executor, Paper Trading |
| **Analytics** | Performance Metrics (Sharpe/Sortino), Walk-Forward Backtesting, Equity Curves |
| **Analysis** | RSI, MACD, Patterns (H&S, Double Top), Fibonacci & Pivot levels, Sentiment |
| **Macro** | FRED & ECB integration (Rate differentials, CPI, GDP), Economic Calendar |
| **Learning** | Trade Journal, Prediction Tracker, Pattern Success Rates, Adaptive Parameter Tuner |
| **Telegram** | Agent commands, Smart Alerts, Cron Scheduler, Proactive Intelligence |
| **Validation** | Behavioral Testing Suite (5 Scenarios), Historical Scenario Replay |

---

## Bot Commands

### Standard Commands

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

### 🤖 Agent Commands

| Command | Description |
|:---|:---|
| `/agent_status` | Agent Core state, tick count, world model snapshot |
| `/conviction` | Active trading theses with direction, confidence, and thesis text |
| `/session_plan` | Today's game plan with If-Then scenarios and entry zones |

### Smart Analysis Commands

| Command | Description |
|:---|:---|
| `/comprehensive_analysis [query]` | Full ReAct loop with multi-step reasoning |
| `/quick_analysis` | Faster 2-step analysis for quick checks |

---

## Proactive Intelligence

EuroScope autonomously monitors EUR/USD and sends intelligent alerts:

- Runs a ReAct analysis loop at configurable intervals
- Deduplicates alerts within a 60-minute window
- Prioritizes as 🚨 Critical, 🔥 High, ⚠️ Medium, or ℹ️ Low
- Context-aware suppression (quiet hours, weekends, holidays)

**Example Alerts:**
- 🚨 `Price sweeping liquidity below 1.0800 — reversal likely. Avoid shorts.`
- ⚠️ `Bullish breakout above 1.0850 with volume confirmation. Watch for pullback entry.`
- ℹ️ `Market consolidating ahead of NY session. Wait for London close direction.`

---

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

| Variable | Purpose | Required |
|:---|:---|:---|
| `EUROSCOPE_LLM_API_KEY` | LLM provider (DeepSeek/OpenAI) | ✅ |
| `EUROSCOPE_TELEGRAM_TOKEN` | From [@BotFather](https://t.me/BotFather) | ✅ |
| `EUROSCOPE_ADMIN_CHAT_IDS` | Admin chat IDs (comma-separated) | ✅ |
| `EUROSCOPE_LLM_FALLBACK_API_KEY` | Backup LLM for failover | Optional |
| `EUROSCOPE_TIINGO_KEY` | Real-time market data (0s delay) | Recommended |
| `EUROSCOPE_FRED_API_KEY` | FRED macro data | Recommended |
| `EUROSCOPE_BRAVE_API_KEY` | News sentiment | Optional |
| `EUROSCOPE_ALPHAVANTAGE_KEY` | AlphaVantage data | Optional |
| `EUROSCOPE_PROACTIVE_CHAT_IDS` | Chat IDs for proactive alerts | Optional |
| `EUROSCOPE_PROACTIVE_INTERVAL_MINUTES` | Analysis interval (default: 30) | Optional |
| `EUROSCOPE_VECTOR_MEMORY_TTL_DAYS` | Vector Memory retention (default: 30) | Optional |

### 3. Run
```bash
python -m euroscope.main
```

The agent will:
1. Initialize all skills and data providers
2. Start the Telegram bot
3. Begin the 30-second heartbeat loop
4. Generate session plans before London/NY opens
5. Form convictions as evidence accumulates
6. Send proactive alerts when significant events occur

---

## Project Structure

```
euroscope/
├── brain/                  # Agent Intelligence
│   ├── agent_core.py       # State machine (OODA loop)
│   ├── world_model.py      # 8 structured market sub-models
│   ├── conviction.py       # Thesis tracking with evidence & decay
│   ├── session_planner.py  # Daily game plan generation
│   ├── llm_interface.py    # LLM chat, ReAct, reason_about()
│   ├── orchestrator.py     # Skills coordinator + scan/quick_state
│   ├── prompts.py          # Agent identity & reasoning prompts
│   ├── llm_router.py       # Multi-LLM routing with fallback
│   ├── memory.py           # Conversation memory
│   └── vector_memory.py    # ChromaDB semantic search
├── skills/                 # 9+ auto-discovered skills
│   ├── base.py             # BaseSkill, SkillResult, SkillContext
│   ├── registry.py         # Auto-discovery & LLM prompt generation
│   ├── market_data/        # Price & OHLCV data
│   ├── technical_analysis/ # RSI, MACD, ADX, patterns
│   ├── pattern_detection/  # H&S, Double Top/Bottom, Fibonacci
│   ├── fundamental/        # FRED, ECB, macro data
│   ├── signals/            # Signal generation
│   ├── backtesting/        # Walk-forward + slippage
│   ├── monitoring/         # Health + runtime stats
│   ├── trade_journal/      # Full-context trade logging
│   └── prediction_tracker/ # Forecast accuracy tracking
├── trading/                # Execution Layer
│   ├── risk_manager.py     # Position sizing, exposure limits
│   ├── strategy_engine.py  # Trend/MR/Breakout strategies
│   ├── signal_executor.py  # Paper & live trade execution
│   ├── capital_provider.py # Capital.com REST API
│   └── capital_ws.py       # Capital.com WebSocket streaming
├── automation/             # Scheduling
│   ├── cron.py             # Task scheduler + agent heartbeat
│   └── daily_tracker.py    # Daily stats
├── learning/               # Self-Improvement
│   ├── pattern_tracker.py  # Pattern success rates
│   ├── forecast_tracker.py # Prediction accuracy
│   └── adaptive_tuner.py   # Auto-tune parameters
├── bot/                    # Telegram Interface
│   ├── telegram_bot.py     # Main bot class
│   ├── handlers/           # Command & task handlers
│   ├── api_server.py       # REST API for Mini App
│   └── rate_limiter.py     # Per-user rate limiting
├── data/                   # Data Providers
│   ├── multi_provider.py   # Tiingo, OANDA, fallback
│   ├── news.py             # News aggregation
│   ├── calendar.py         # Economic calendar
│   ├── fundamental.py      # FRED, ECB macro data
│   └── storage.py          # SQLite persistence
├── forecast/               # AI Forecasting
│   └── engine.py           # Neural directional outlook
├── analytics/              # Performance
│   └── report_generator.py # PDF reports
├── workspace/              # Agent Identity
│   └── IDENTITY.md         # Agent personality & rules
└── utils/                  # Utilities
    ├── charts.py           # Candlestick chart generation
    └── formatting.py       # Telegram message formatting
```

---

## Tech Stack

| Layer | Technologies |
|:---|:---|
| **Runtime** | Python 3.12+ |
| **AI/ML** | ONNX Runtime, FinBERT (quantized int8), DeepSeek & OpenAI |
| **Memory** | ChromaDB (vector), SQLite (relational) |
| **Market Data** | Tiingo, OANDA, Capital.com (REST + WebSocket) |
| **Telegram** | python-telegram-bot (Async V21+) |
| **Security** | pycryptodome (RSA/AES for Capital.com) |
| **Monitoring** | psutil, custom health checks |

---

## Testing

**558+ tests** covering all modules:
```bash
python -m pytest tests/
```

### Behavioral Validation
Run comprehensive behavioral tests against historical market scenarios:
```bash
python -m euroscope.testing.report_generator --output behavioral_report.md
```
Validates against: Sideways Market Trap, Lagarde Shock, Liquidity Sweep, Session Transition, Macro Override.

---

## License
Private project.
