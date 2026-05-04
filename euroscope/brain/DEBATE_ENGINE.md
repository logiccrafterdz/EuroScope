# Multi-Agent Debate Engine Architecture

EuroScope v3 implements a sophisticated multi-agent debate architecture (inspired by TradingAgents) to reduce LLM hallucination and enforce rigorous risk management.

## 1. Core Components

### 1.1 Investment Debate (`euroscope/brain/debate_engine.py`)
When a trading signal reaches the minimum confidence threshold, the Debate Engine triggers a 3-agent debate:
*   **Bull Analyst:** Argues strongly for the trade direction, citing supportive indicators.
*   **Bear Analyst:** Critiques the Bull Case, looking for flaws, contrary indicators, and invalidation levels.
*   **Research Manager (Judge):** Weighs both arguments and makes a final decision (`BUY`, `SELL`, or `HOLD`) with an updated confidence score.

### 1.2 Risk Panel (`euroscope/brain/risk_debate.py`)
Once an investment decision is finalized, a specialized risk panel determines the execution parameters:
*   **Aggressive Risk Manager:** Proposes maximum position size and tight stops.
*   **Conservative Risk Manager:** Proposes minimum position size and wide stops for safety.
*   **Neutral Risk Manager:** Balances risk and reward based on ATR and liquidity levels.
*   **Portfolio Judge:** Reviews all proposals and outputs the final `RiskProfile` (Lots, Stop Loss, Take Profit).

### 1.3 Decision Log & Reflector (`euroscope/brain/decision_log.py`, `euroscope/brain/reflector.py`)
*   Every finalized debate decision is stored as `pending` with a unique `decision_id`.
*   When the trade is closed by the `signal_executor`, an event (`trade.closed`) is emitted.
*   The `DecisionLog` captures this event and triggers the `Reflector`.
*   The `Reflector` generates a concise 2-4 sentence review of what went right or wrong.
*   These reflections are injected into future debates, creating a continuous self-learning loop.

## 2. Configuration (`euroscope/config.py`)

*   `debate_enabled` (bool): Master switch for the debate engine.
*   `debate_min_confidence` (float): Minimum signal confidence (e.g., 55.0) required to trigger a debate (saves tokens on weak signals).
*   `max_debate_rounds` (int): Number of Bull/Bear back-and-forth rounds (Default: 1).
*   `max_risk_debate_rounds` (int): Number of Risk Panel rounds (Default: 1).

## 3. Data Flow Integration
The debate engine hooks directly into `Orchestrator._execute_pipeline`:
1. `trading_strategy` detects initial signal.
2. If signal is strong enough, `DebateEngine` evaluates it.
3. If approved, `RiskDebate` generates the risk profile.
4. Standard `risk_management` applies hard safety guardrails over the debated profile.
5. `signal_executor` opens the trade with the injected `decision_id`.
6. Trade closes -> `Reflector` runs.
