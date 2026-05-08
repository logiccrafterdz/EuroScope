<div align="center">
  <img src="assets/robot_logo.png" alt="EuroScope Logo" width="450">
</div>

# EuroScope

[![CI](https://github.com/logiccrafterdz/EuroScope/actions/workflows/tests.yml/badge.svg)](https://github.com/logiccrafterdz/EuroScope/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

**Autonomous AI trading agent specialized exclusively in the EUR/USD forex pair.**

EuroScope is an always-on trading intelligence system that continuously monitors EUR/USD, forms market theses, and makes autonomous decisions. It combines a skills-based architecture with an OODA-loop cognitive framework, institutional-grade analysis, adaptive learning, and real-time Telegram control.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Core Components](#core-components)
- [Project Structure](#project-structure)
- [Features](#features)
- [Command Reference](#command-reference)
- [Getting Started](#getting-started)
- [Docker Deployment](#docker-deployment)
- [Technical Stack](#technical-stack)
- [Testing](#testing)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

---

## Architecture Overview

EuroScope operates as an **autonomous agent** rather than a traditional chatbot. It runs continuously, reasoning over structured market context without waiting for user commands.

| Aspect | Traditional Chatbot | EuroScope Agent |
|:---|:---|:---|
| **Behavior** | Waits for user commands | Continuously monitors and acts |
| **Decision Making** | One-off analysis per request | Conviction-based with evidence tracking |
| **Market Awareness** | Fetches data on demand | Maintains a persistent World Model |
| **Planning** | None | Session-aware game plans with If-Then scenarios |
| **Identity** | General-purpose assistant | Senior EUR/USD analyst briefing a portfolio manager |

### Cognitive Loop (OODA)

The agent runs a state machine that follows the **Observe -> Orient -> Decide -> Act** cycle every 30 seconds:

```text
+---------------------------------------------------------+
|                    CRON HEARTBEAT (30s)                 |
|                         |                               |
|                    +----v----+                          |
|                    |  IDLE   |<------------------+      |
|                    +----+----+                   |      |
|                         | tick()                 |      |
|                    +----v----+                   |      |
|                    |OBSERVING| <- run_scan()     |      |
|                    +----+----+                   |      |
|                         | deltas?                |      |
|                    +----v----+                   |      |
|                    |ORIENTING| <- World Model    |      |
|                    |         |   update          |      |
|                    +----+----+                   |      |
|                         |                        |      |
|                    +----v----+                   |      |
|                    |DECIDING | <- LLM reasoning  |      |
|                    +----+----+                   |      |
|                    +----v----+                   |      |
|                    | ACTING  | <- Execute/Alert  |      |
|                    +----+----+                   |      |
|                         |                        |      |
|                    +----v----+                   |      |
|                    |REVIEWING| <- Track outcomes -+      |
|                    +---------+                          |
+---------------------------------------------------------+
```

---

## Core Components

### 1. Debate Engine

**Files:** `brain/multi_agent.py`, `brain/conflict_arbiter.py`

Resolves high-ambiguity market conditions using an adversarial committee framework:

- Three specialized LLM agents: Bull Advocate, Bear Advocate, and Risk Manager.
- A Conflict Arbiter synthesizes their arguments into a consensus direction, confidence score, and unified game plan.
- Uses LLM fallback routing via `brain/llm_router.py`, parallel async execution, and a 20-second timeout to guarantee stability during volatile events.

### 2. Self-Reflection and Decision Logging

**Files:** `brain/reflector.py`, `brain/decision_log.py`

A continuous learning loop that evaluates past trade outcomes:

- **Decision Log** persists every debate, thesis, and trading decision to the database.
- **Reflector** autonomously reviews closed trades against their initial thesis, generating feedback to improve future performance.

### 3. Sentiment Network Graph

**File:** `data/sentiment_graph.py`

A directed graph (NetworkX) that tracks macroeconomic narrative linkages from real-time news:

- Extracts causal relationships using LLMs (e.g., "strong NFP -> forces rate hike -> hawkish FED").
- Applies exponential temporal decay (0.95x) on edge weights so stale narratives naturally fade.

### 4. Market Regime Memory

**File:** `brain/vector_memory.py`

Records the market state (ADX, RSI, MACD, trend, ATR volatility, macro bias) alongside realized trade outcomes:

- Before opening a new trade, the system queries the SQLite FTS5 memory to find historically similar market regimes.
- Dynamically scales signal confidence based on the historic win rate of matched regimes.

### 5. Counterfactual Engine

**File:** `learning/counterfactual.py`

A background analysis pipeline that reviews closed trades to identify alternative scenarios:

- Tests whether wider stops would have avoided stop hunts, or if trailing stops prematurely cut profitable trades.
- Insights feed into the `adaptive_tuner.py` for automatic parameter optimization.

### 6. Conviction System and World Model

**Files:** `brain/conviction.py`, `brain/world_model.py`

A structured representation of the current EUR/USD market state covering price, technicals, fundamentals, sentiment, regimes, risk, liquidity levels (PDH/PDL), and session context:

- The agent only reasons when meaningful state changes (deltas) are detected.
- Convictions maintain decay gradients and invalidation thresholds tied to specific price levels.

### 7. Event Architecture and Scheduling

**Files:** `automation/events.py`, `automation/heartbeat.py`

- Pub/sub event bus for inter-component communication.
- Async periodic task scheduler that separates data fetching from execution logic.

---

## Project Structure

```text
euroscope/
|-- analysis/            # Analytical abstractions
|-- analytics/           # Metrics, PDF report generation
|-- automation/          # Scheduling, heartbeat, events, alerts
|-- backtest/            # Backtesting engine
|-- bot/                 # Telegram bot, REST API server
|-- brain/               # Agent core: OODA, World Model, Memory, LLM routing
|-- data/                # Data ingestion: news, prices, macroeconomic feeds
|-- forecast/            # Directional forecasting
|-- learning/            # Adaptive tuning, counterfactual analysis
|-- testing/             # Behavioral test scenarios
|-- trading/             # Execution, risk management, safety guardrails
|-- skills/              # Modular skill plugins (20 skills)
|   |-- backtesting/
|   |-- briefing_generator/
|   |-- correlation_monitor/
|   |-- cot_positioning/
|   |-- deviation_monitor/
|   |-- fundamental_analysis/
|   |-- liquidity_awareness/
|   |-- macro_calendar/
|   |-- market_data/
|   |-- monitoring/
|   |-- multi_timeframe_confluence/
|   |-- performance_analytics/
|   |-- portfolio_context/
|   |-- prediction_tracker/
|   |-- risk_management/
|   |-- session_context/
|   |-- signal_executor/
|   |-- technical_analysis/
|   |-- trade_journal/
|   |-- trading_strategy/
|   +-- uncertainty_assessment/
|-- utils/               # Chart rendering, formatting utilities
+-- workspace/           # Identity configuration, operational settings
```

---

## Features

| Domain | Capabilities |
|:---|:---|
| **Agent Intelligence** | OODA loop, multi-agent debate, regime memory, sentiment graphs, briefing generation |
| **Skills Engine** | 20 independently executing skills with dynamic prompt interfacing and dependency injection |
| **Trading and Execution** | Signal executor, trailing stops, Capital.com WebSocket, execution simulation |
| **Analytics** | Post-trade diagnostics, convexity profiling, forecast tracking |
| **Technical Analysis** | Multi-timeframe confluence, regime recognition, correlation tracking |
| **Macro Intelligence** | FRED data parsing, causal impact attribution, economic calendar |
| **Adaptive Learning** | Counterfactual simulations, pattern detection, unsupervised parameter tuning |
| **Integration** | Telegram bot, REST API, event bus alerting, Docker deployment |

---

## Command Reference

The following commands are registered in the Telegram bot:

### Standard Commands

| Command | Description |
|:---|:---|
| `/start` | Launch the EuroScope dashboard |
| `/help` | List all available commands |
| `/id` | Display your Telegram chat ID |
| `/health` | Show system health and component status |
| `/data_health` | Check the status of all data sources (APIs, feeds) |

### Agent Introspection

| Command | Description |
|:---|:---|
| `/agent_status` | Show the agent's current state and world model summary |
| `/conviction` | Display active trading theses with confidence levels |
| `/session_plan` | Show today's trading game plan with If-Then scenarios |

### Alerts

| Command | Description |
|:---|:---|
| `/alerts` | List all active price alerts |
| `/delete_alert <id>` | Delete a specific price alert by its ID |

> **Note:** Additional analysis features (price, charts, signals, news, forecasts, reports) are accessible through the integrated Web Dashboard launched via the `/start` command.

---

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- An LLM API key (e.g., NVIDIA NIM, OpenAI)

### 1. Clone and Install

```bash
git clone https://github.com/logiccrafterdz/EuroScope.git
cd EuroScope
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Required
EUROSCOPE_LLM_API_KEY=your-llm-api-key
EUROSCOPE_TELEGRAM_TOKEN=your-telegram-bot-token
EUROSCOPE_ADMIN_CHAT_IDS=123456789

# Optional - Fallback LLM
EUROSCOPE_LLM_FALLBACK_API_KEY=your-fallback-key

# Recommended - Data Providers
EUROSCOPE_FRED_API_KEY=your-fred-api-key
EUROSCOPE_TIINGO_KEY=your-tiingo-api-key
```

**Environment Variable Reference:**

| Variable | Purpose | Required |
|:---|:---|:---:|
| `EUROSCOPE_LLM_API_KEY` | API key for the primary LLM provider | Yes |
| `EUROSCOPE_TELEGRAM_TOKEN` | Telegram Bot API token from BotFather | Yes |
| `EUROSCOPE_ADMIN_CHAT_IDS` | Comma-separated Telegram chat IDs for admin users | Yes |
| `EUROSCOPE_LLM_FALLBACK_API_KEY` | API key for the fallback LLM provider | No |
| `EUROSCOPE_FRED_API_KEY` | St. Louis FRED API key for macroeconomic data | No |
| `EUROSCOPE_TIINGO_KEY` | Tiingo API key for market data | No |
| `EUROSCOPE_VECTOR_MEMORY_TTL_DAYS` | Number of days to retain vector memory entries | No |

### 3. Run

```bash
python -m euroscope.main
```

This initializes the dependency injection container, connects to the database, starts the event bus and heartbeat service, and begins the autonomous OODA monitoring loop.

---

## Docker Deployment

Build and run using Docker:

```bash
# Build the image
docker build -t euroscope .

# Run with environment variables
docker run -d \
  --name euroscope \
  -p 8080:8080 \
  --env-file .env \
  -v euroscope-data:/app/data \
  euroscope
```

The Dockerfile uses a multi-stage build with Python 3.11-slim, runs as an unprivileged user, and exposes port 8080 for the API/Web Dashboard.

---

## Technical Stack

| Domain | Technologies |
|:---|:---|
| **Runtime** | Python 3.11+ with strict typing |
| **LLM Providers** | NVIDIA NIM (DeepSeek), OpenAI (fallback), ONNX Runtime (sentiment) |
| **Database** | PostgreSQL via SQLAlchemy 2.0, SQLite with FTS5 for vector search |
| **Market Data** | Tiingo, OANDA, Capital.com (REST + WebSocket), AlphaVantage |
| **Macro Data** | St. Louis FRED, DuckDuckGo News |
| **Telegram** | python-telegram-bot v21 (async) |
| **Security** | PyCryptodome (AES-256, RSA) |
| **Graph Analysis** | NetworkX for sentiment causal graphs |
| **CI/CD** | GitHub Actions (lint + test on every push) |

---

## Testing

Run the full test suite:

```bash
python -m pytest tests/
```

### Behavioral Replay Tests

The project includes scenario-based replay tests that validate the system against specific historical market conditions (e.g., ECB rate decisions, extreme volatility periods):

```bash
python -m euroscope.testing.report_generator --output behavioral_report.md
```

---

## Contributing

We welcome contributions. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to submit issues, propose changes, and set up your development environment.

---

## Security

For information about reporting vulnerabilities and our security practices, see [SECURITY.md](SECURITY.md).

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
