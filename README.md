<div align="center">
  <img src="assets/robot_logo.png" alt="EuroScope Logo" width="450">
</div>

# EuroScope

**Autonomous AI Agent specialized exclusively in the EUR/USD forex pair.**

EuroScope is an always-on trading intelligence agent that continuously monitors EUR/USD, forms market theses, and makes autonomous decisions. It combines a skills-based multi-agent architecture with an OODA-loop cognitive framework, institutional-grade analysis, adaptive learning, and real-time Telegram control.

**System Status:** Fully operational as an autonomous agent. The system runs a 30-second heartbeat loop, maintains a structured world model, tracks trading convictions with evidence-based confidence decay, and generates session-aware game plans.

---

## Architecture Overview

EuroScope operates as an **autonomous agent**, transcending the traditional chatbot paradigm.

| Aspect | Traditional Chatbot | EuroScope Autonomous Agent |
|:---|:---|:---|
| **Behavior** | Waits for user commands | Continuously monitors and acts |
| **Decision Making** | One-off analysis per request | Conviction-based with evidence tracking |
| **Market Awareness** | Fetches data on demand | Maintains a persistent World Model |
| **Planning** | None | Session-aware game plans with If-Then scenarios |
| **Identity** | Helpful assistant | Senior EUR/USD analyst briefing a portfolio manager |

### Cognitive Loop (OODA)

The Agent Core runs a state machine that follows the **Observe -> Orient -> Decide -> Act** cycle every 30 seconds:

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

## Intelligence & Core Components

### 1. Multi-Agent Deliberation Committee (`brain/multi_agent.py`)
Resolves high-ambiguity market conditions using an adversarial committee framework.
- Consists of three specialized LLM agents: Bull Advocate, Bear Advocate, and Risk Manager.
- A Chief Judge (Conflict Arbiter) synthesizes the arguments and establishes a consensus direction and confidence score.
- Implements strict LLM fallback routing, parallel asynchronous execution, and time-bound deliberation to guarantee system stability during volatile events.

### 2. Sentiment Network Graph (`data/sentiment_graph.py`)
Utilizes a directed acyclic graph (via NetworkX) to track macroeconomic narrative linkages from real-time news.
- Extracts causal relationships using LLMs (e.g., FED -> strengthens -> USD).
- Persists data with automated temporal decay on edge weights to prioritize recent narratives while gracefully forgetting stale hypotheses.

### 3. Market Regime Memory Bank (`brain/vector_memory.py`)
Records the state of the market (ADX, RSI, MACD, Trend, Volatility, Macro Bias) alongside trading outcomes.
- Before executing a trade, the system queries SQLite FTS5 vector memory to locate historically similar market regimes.
- Dynamically adjusts signal confidence based on the historic win rate of analogous past environments.

### 4. Counterfactual Engine (`learning/counterfactual.py`)
An asynchronous background task that analyzes closed trades to simulate alternative 'what-if' scenarios.
- Evaluates if wider stop losses would have prevented stop hunts or if tighter taking profits would have optimized yield.
- Results are embedded directly into the vector memory insights collection to dynamically tune future risk parameters.

### 5. World Model (`brain/world_model.py`)
A structured, always-current representation of the EUR/USD market state tracking Price, Technicals, Fundamentals, Sentiment, Regimes, Risk, Liquidity, and Session states. Implements strict delta detection to restrict agent reasoning to state transitions.

### 6. Conviction System (`brain/conviction.py`)
Maintains logical trading theses with decay vectors. If reinforcing evidence ceases or hard invalidation levels are breached, convictions auto-terminate gracefully.

### 7. Orchestrator & Containerization (`container.py`, `brain/orchestrator.py`)
Implements a strict Dependency Injection (DI) framework with a global service registry to eliminate circular dependencies. Exposes pipelines for complete market analysis or lightweight tick scans.

---

## Key Features Matrix

| Domain | Capabilities |
|:---|:---|
| **Agent Intelligence** | OODA Loop, Multi-Agent Deliberation, Regime Memory, Sentiment Graphs |
| **Skills Engine** | Auto-discovered discrete capabilities, Dynamic Prompting |
| **Trading & Execution** | Signal Executor, Risk Manager, Strategy Engine, Paper Trading |
| **Quantitative Analytics**| Equity Curves, Walk-Forward Backtesting, Sharpe/Sortino calculations |
| **Technical Analysis** | Adaptive RSI, MACD, Automated support/resistance, Pattern Detection |
| **Macro Intelligence** | FRED/ECB integration, Causal Impact Attribution, Calendar Events |
| **Adaptive Learning** | Counterfactual Analysis, Parameter Tuning, Knowledge Vectorization |
| **Interoperability** | Telegram Command API, Smart Protocol Alerts, Containerized DI |

---

## Command Interface Reference

### Standard Operations
- `/menu` - Main interactive dashboard
- `/price` - Real-time EUR/USD quotes
- `/analysis` - Full technical analysis report
- `/chart` - Rendered candlestick chart graphics
- `/forecast` - AI-driven directional outlook
- `/news` - Live sentiment and fundamental headlines
- `/signals` - Active trading signals and entries
- `/strategy` - Current algorithmic strategy recommendation
- `/risk` - Risk allocation assessment for the next sequential trade
- `/trades` - Paper trading ledger execution history
- `/performance` - Deep-dive ROI and Sharpe statistics
- `/report` - Pipeline compilation of all skills into a singular report
- `/health` - System diagnostic and runtime metrics
- `/settings` - Configuration management

### Agent Introspection Commands
- `/agent_status` - Dump of the Agent Core state, execution tick count, and active World Model components.
- `/conviction` - Active trading theses sorted by confidence and direction.
- `/session_plan` - Active algorithmic game plans organized into contingent If-Then scenarios.

### Smart Analysis Executions
- `/comprehensive_analysis [query]` - Instigates a full ReAct loop with multi-step logical deduction.
- `/quick_analysis` - Restricted-depth analysis prioritized for latency.

---

## Proactive Intelligence Protocol

EuroScope autonomously monitors EUR/USD data streams and generates event-driven notifications.
- Executes distributed ReAct analysis loops at configurable intervals.
- Manages stateful alert suppression within 60-minute rolling windows.
- Prioritizes distributions into Critical, High, Medium, and Low severity classifications.
- Utilizes context-aware throttling (e.g., weekend suppression, major holiday silences).

**Example Notifications:**
- [CRITICAL] Price sweeping liquidity below 1.0800 - reversal dynamic likely. Short allocations restricted.
- [HIGH] Bullish structural breakout above 1.0850. Volume validation present. Watch for mean-reversion pullback for optimal entry.
- [LOW] Market exhibiting tight consolidation preceding the New York session open. Awaiting liquidity injection.

---

## Quick Start Configuration

### 1. Environment & Dependencies
```bash
git clone https://github.com/logiccrafterdz/EuroScope.git
cd EuroScope
python -m venv .venv
# Activate virtual environment (.venv\Scripts\activate on Windows or source .venv/bin/activate on Linux/Mac)
pip install -r requirements.txt
```

### 2. Environment Variables
Create a `.env` file referencing `.env.example`:

| Key | Purpose | Status |
|:---|:---|:---|
| `EUROSCOPE_LLM_API_KEY` | Primary LLM Provider API Key (OpenRouter/DeepSeek/OpenAI) | Required |
| `EUROSCOPE_TELEGRAM_TOKEN` | Telegram Bot Framework Token | Required |
| `EUROSCOPE_ADMIN_CHAT_IDS` | Comma-separated strict admin authorization IDs | Required |
| `EUROSCOPE_LLM_FALLBACK_API_KEY`| Secondary LLM key for failover redundancy | Optional |
| `EUROSCOPE_FRED_API_KEY` | St. Louis Fed macro data access | Recommended |
| `EUROSCOPE_TIINGO_KEY` | Real-time WebSocket market data | Recommended |
| `EUROSCOPE_BRAVE_API_KEY` | News and sentiment aggregation | Optional |
| `EUROSCOPE_VECTOR_MEMORY_TTL_DAYS`| Memory retention window (default: 30) | Optional |

### 3. Execution Standard
```bash
python -m euroscope.main
```
The initialization sequence performs Dependency Injection bindings, loads SQLite/ChromaDB state files, initializes the Telegram listeners, and boots the Agent Core OODA loop.

---

## Technical Stack

| Domain | Applied Technologies |
|:---|:---|
| **Runtime & Language** | Python 3.12+ |
| **Logic & AI** | DeepSeek, OpenAI APIs, FinBERT (INT8 Quantized), ONNX Runtime |
| **State Persistence** | SQLite (with FTS5 for vector text), NetworkX (Graphs) |
| **Data Pipelines** | Tiingo API, OANDA API, Capital.com (REST and WebSocket integrations) |
| **Client Interface** | python-telegram-bot (Async V21+) |
| **Cryptographic Security** | PyCryptodome (AES/RSA handling for institutional endpoints) |

---

## Testing & Validation Framework

The repository is covered by continuous integration tests guaranteeing robustness across discrete analytical skills.
```bash
python -m pytest tests/
```

### End-to-End Behavioral Validation
A deterministic scenario replay engine evaluates the agent against historical market anomalies:
```bash
python -m euroscope.testing.report_generator --output behavioral_report.md
```
Validates resilience against constraints such as the Sideways Market Trap, Central Bank Rate Shocks, Institutional Liquidity Sweeps, and Conflicting Multi-Timeframe signals.

---

## License
Proprietary software. All rights reserved.
