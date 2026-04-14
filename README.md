<div align="center">
  <img src="assets/robot_logo.png" alt="EuroScope Logo" width="450">
</div>

# EuroScope

**Autonomous AI Agent specialized exclusively in the EUR/USD forex pair.**

EuroScope is an always-on trading intelligence agent that continuously monitors EUR/USD, forms market theses, and makes autonomous decisions. It combines a skills-based multi-agent architecture with an OODA-loop cognitive framework, institutional-grade analysis, adaptive learning, and real-time Telegram control.

**System Status:** Fully operational as an autonomous agent. The system runs a 30-second heartbeat loop, maintains a structured world model, tracks trading convictions with evidence-based confidence decay, and generates session-aware game plans.

---

## Architecture Overview

EuroScope operates as an **autonomous agent**, transcending the traditional chatbot paradigm. It runs continuously, reasoning over localized context structures.

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
- Consists of specialized LLM agents: Bull Advocate, Bear Advocate, and Risk Manager.
- A Chief Judge (Conflict Arbiter) synthesizes the arguments and establishes a consensus direction and confidence score.
- Implements strict LLM fallback routing via `brain/llm_router.py`, parallel asynchronous execution, and time-bound deliberation (20-second timeout) to guarantee system stability during volatile macro events.
- Employs a cooldown mechanism to prevent token saturation.

### 2. Sentiment Network Graph (`data/sentiment_graph.py`)
Utilizes a directed acyclic graph (implemented as a Singleton via NetworkX) to track macroeconomic narrative linkages from real-time news engines.
- Extracts causal relationships using LLMs (e.g., NFP -> forces_hike -> FED).
- Persists data with automated exponential temporal decay (0.95x modifier) on edge weights, naturally obsoleting stale structural hypotheses over time.

### 3. Market Regime Memory Bank (`brain/vector_memory.py`)
Records the state of the market (ADX, RSI, MACD, Trend, ATR Volatility, Macro Bias) alongside realized post-trade outcomes mapping to profit constraints.
- Prior to discrete trade initialization, the system performs an internal nearest-neighbor query to the SQLite FTS5 vector memory framework to index historically similar market regimes.
- Dynamically scales signal confidence thresholds proportional to the historic win rate of the matched regime matrices.

### 4. Counterfactual Engine (`learning/counterfactual.py`)
An asynchronous background analysis pipeline that digests closed trading iterations to isolate mathematical counter-scenarios.
- Computes trajectory variances: tests whether expanding standard deviation on stop losses mitigates slippage/stop hunts, or if trailing constraints prematurely truncate PnL duration.
- Extracted theorems are embedded into the central insight registry, enabling dynamic, unsupervised parameter retuning per the `adaptive_tuner.py`.

### 5. Conviction System & World Model (`brain/conviction.py`, `brain/world_model.py`)
A rigorously structured, sub-millisecond representation of the active EUR/USD market state mapping Price, Technicals, Fundamentals, Sentiment, Regimes, Risk matrices, Liquidity levels (PDH/PDL), and Session demarcations.
- Implements strict delta threshold detection logic restricting agent reasoning cycles purely to explicit state transitions.
- Logical convictions maintain decay gradients and absolute invalidation thresholds mapped to physical price boundaries.

### 6. Event Architecture & Scheduling (`automation/events.py`, `automation/heartbeat.py`)
- Event Bus architecture for pub-sub inter-process communication bounding all execution parameters.
- Asynchronous periodic task scheduler mapping data fetches independently, segregating discrete I/O boundaries from execution logic.

---

## System Architecture Structure

The project encompasses a heavily expanded micro-module architecture:

```text
euroscope/
+-- analysis/            # Analytical abstractions
+-- analytics/           # Deep-dive metrics and PDF generation logic
+-- automation/          # Scheduling and Heartbeat algorithms (cron, events, alerts)
+-- backtest/            # Backtesting runtimes
+-- bot/                 # Telegram interfacing and REST server deployment handlers
+-- brain/               # Agent LLM Framework (OODA, World Model, Memory, Agents)
+-- data/                # Ingestion layers (Brave News, Tiingo, OANDA, FRED, Graphs)
+-- forecast/            # Directional neural abstractions
+-- learning/            # Unsupervised optimization (Adaptive Tuner, Counterfactuals)
+-- testing/             # CI and behavioral integration test suites
+-- trading/             # Direct Market Access routines (Executors, Guardrails)
+-- skills/              # Unidirectional bounded context algorithms
    +-- backtesting/
    +-- correlation_monitor/
    +-- deviation_monitor/
    +-- fundamental_analysis/
    +-- liquidity_awareness/
    +-- market_data/
    +-- monitoring/
    +-- multi_timeframe_confluence/
    +-- performance_analytics/
    +-- prediction_tracker/
    +-- risk_management/
    +-- session_context/
    +-- signal_executor/
    +-- technical_analysis/
    +-- trade_journal/
    +-- trading_strategy/
    +-- uncertainty_assessment/
+-- utils/               # Chart rendering and mathematical abstractions
+-- workspace/           # Identity configurations and operational logic matrices
```

---

## Key Features Matrix

| Domain | Capabilities |
|:---|:---|
| **Agent Intelligence** | OODA Loop, Multi-Agent Deliberation, Regime Memory, Sentiment Graphs, Briefing Generation |
| **Discrete Skills Engine** | 17 independently executing capabilities, Dynamic Prompt Interfacing, Dependency Registration |
| **Trading & Execution** | Signal Executor, Trailing Stops, Capital.com WS, Execution Simulators, Slippage Matrices |
| **Quantitative Analytics** | Post-Trade Diagnostics, Convexity Profiling, Forecast Tracking |
| **Technical Analysis** | MTF Confluence, Regime Recognition, Correlation tracking, Predictive Interpolation |
| **Macro Intelligence** | St. Louis FRED parsing, Causal Impact Attribution, Asymmetric Event Parsing |
| **Adaptive Learning** | Counterfactual Simulations, Metric-based Pattern Detection, Unsupervised Error Correction |
| **Interoperability** | Telegram Asynchronous Interface, Smart Event Bus Alerting, Containerized Service Scopes |

---

## Command Interface Reference

### Standard Operations
- `/menu` - Instantiates the master execution dashboard
- `/price` - Bids explicit sub-10ms EUR/USD quotes
- `/analysis` - Dumps the standard multi-timeframe algorithm report
- `/chart` - Generates raw heuristic graphical overlays
- `/forecast` - Prompts the neural net for forward projection variances
- `/news` - Fetches sentiment polarity matrices
- `/signals` - Polls the deterministic signal output framework
- `/strategy` - Verifies current active algorithmic profiles
- `/risk` - Dumps volumetric exposure ratios
- `/trades` - Outputs structured transaction histories
- `/performance` - Returns the aggregate strategy indices (Sharpe/Sortino)
- `/report` - Merges full skills-based analyses
- `/health` - Returns memory mapping buffers
- `/settings` - Modifies persistent parameters

### Agent Introspection Commands
- `/agent_status` - Re-evaluates Agent Core memory state vectors
- `/conviction` - Dumps current evidence-backed logic theses
- `/session_plan` - Proscribes contingency constraints prior to NY/London market intersections

### Smart Analysis Executions
- `/comprehensive_analysis [query]` - Invokes an infinite-depth ReAct topological query loop
- `/quick_analysis` - Bounds analysis to Tier 1 latency considerations

---

## Quick Start Configuration

### 1. Environment & Dependencies
```bash
git clone https://github.com/logiccrafterdz/EuroScope.git
cd EuroScope
python -m venv .venv
# Source .venv/bin/activate OR .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Variables
Mandatory `.env` declarations:

| Key | Purpose | Status |
|:---|:---|:---|
| `EUROSCOPE_LLM_API_KEY` | Authorization token for LLM API schemas | Required |
| `EUROSCOPE_TELEGRAM_TOKEN` | Telemetry mapping via Telegram servers | Required |
| `EUROSCOPE_ADMIN_CHAT_IDS` | Absolute strict integers bounding authorization overrides | Required |
| `EUROSCOPE_LLM_FALLBACK_API_KEY`| High availability API swap target | Optional |
| `EUROSCOPE_FRED_API_KEY` | Key for quantitative macroeconomic interpolation | Recommended |
| `EUROSCOPE_TIINGO_KEY` | Socket endpoint mapping for latency reduction | Recommended |
| `EUROSCOPE_VECTOR_MEMORY_TTL_DAYS`| FTS5/Chroma vector saturation limits | Optional |

### 3. Execution Standard
```bash
python -m euroscope.main
```
Initialization mounts DI scopes (`container.py`), resolves internal schema cyclic logic, mounts SQLite state files, establishes event bus sockets, and runs the baseline memory mapping algorithms.

---

## Technical Stack

| Domain | Applied Technologies |
|:---|:---|
| **Runtime Architecture** | Python 3.12 (Strict Typing Guidelines) |
| **Logic Orchestration** | FinBERT (INT8), Generalized LLM Parsing API models, ONNX inference |
| **Persistence Layers** | SQLite + FTS5 indexing, NetworkX Acyclic Models, JSON Flat-files |
| **Telemetry Access** | Tiingo API, OANDA API, Capital.com direct REST + WSS implementations |
| **Client Protocols** | Async Python-Telegram-Bot (V21 API Layer) |
| **Security Specifications** | PyCryptodome AES-256 / RSA cryptographic exchange |

---

## Validation & Testing Diagnostics

The repository implements strict integration tests running algorithmic sweeps against internal logic.
```bash
python -m pytest tests/
```

### Deterministic Behavioral Replays
To guarantee non-deterministic AI parameters maintain consistency across structural breaks, system architectures must successfully endure replay diagnostics:
```bash
python -m euroscope.testing.report_generator --output behavioral_report.md
```
Guarantees systemic operation during specific constraints such as the ECB quantitative structural shocks and extreme deviation scenarios.

---

## Deployment Scope
Private intelligence engine build. All licensing protocols restricted.
