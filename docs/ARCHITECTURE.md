# EuroScope Architecture Reference (Part 1)

This document provides a comprehensive overview of the EuroScope v5.0.0 architecture, detailing the system flow, component dependencies, and cognitive structure.

## 1. System Overview

EuroScope is built on a highly modular, decoupled architecture. At its core, the system acts as an autonomous agent operating within an OODA loop (Observe, Orient, Decide, Act), supported by discrete, unidirectional components.

### 1.1 High-Level Component Interactions

The following diagram illustrates the interaction between the primary domains of the system:

```mermaid
graph TD
    classDef core fill:#2d3748,stroke:#4a5568,color:#fff
    classDef intelligence fill:#2b6cb0,stroke:#2c5282,color:#fff
    classDef domain fill:#276749,stroke:#22543d,color:#fff
    classDef data fill:#744210,stroke:#7b341e,color:#fff

    A[Agent Core / Orchestrator]:::core
    B[Brain / LLM Agents]:::intelligence
    C[Skills System]:::intelligence
    D[Trading Engine]:::domain
    E[Data Providers]:::data
    F[Storage / Persistence]:::data
    G[Automation / Events]:::core
    H[Learning / Analytics]:::domain

    E -->|Market/News Data| A
    A <-->|Prompts & Logic| B
    A -->|Context Routing| C
    C -->|Analysis| A
    A -->|Decisions| D
    D -->|Execution Logs| F
    C -->|Metrics| F
    A <-->|Event Pub/Sub| G
    H -->|Feedback Loop| A
    F -->|Historical Insights| H
```

### 1.2 Dependency Injection Container (`container.py`)

To eliminate circular dependencies and ensure a deterministic startup sequence, EuroScope implements a central `ServiceContainer`. Dependencies are instantiated in six strict topological layers:

1. **Base Infrastructure:** Database engine (SQLAlchemy/SQLite), EventBus, SmartAlerts, SkillsRegistry, RateLimiter.
2. **Core Brain Components:** Memory, VectorMemory, Orchestrator, LLMRouter.
3. **Intelligence Layers:** LLMInterface (Agent), Forecaster.
4. **Domain & Data Services:** MultiSourceProvider, CapitalProvider (Broker), NewsEngine, EconomicCalendar, FundamentalDataProvider, RiskManager.
5. **Tracking & Analytics:** PatternTracker, AdaptiveTuner, EvolutionTracker, DailyTracker, BriefingEngine.
6. **User Management & Notifications:** UserSettings, NotificationManager, WorkspaceManager.

### 1.3 The Cognitive Loop (OODA)

The system operates autonomously via a 30-second `HeartbeatService` that triggers the Agent Core's OODA loop state machine:

```mermaid
stateDiagram-v2
    [*] --> IDLE
    
    IDLE --> OBSERVING : Heartbeat Tick (30s)
    OBSERVING --> ORIENTING : Deltas Detected
    OBSERVING --> IDLE : No Changes
    
    ORIENTING --> DECIDING : World Model Updated
    
    DECIDING --> ACTING : Signal Generated
    DECIDING --> REVIEWING : No Actionable Signal
    
    ACTING --> REVIEWING : Trade Executed / Alert Sent
    
    REVIEWING --> IDLE : State Persisted
```

## 2. Skills Architecture

The EuroScope "Skills" framework allows the agent to interact with internal engines and external data sources using self-documenting, independent modules.

### 2.1 Topological Dependency Graph (DAG)

Skills often require data from other skills. The `SkillsRegistry` enforces a strict topological execution order.

```mermaid
graph LR
    classDef data fill:#744210,stroke:#7b341e,color:#fff
    classDef analysis fill:#2b6cb0,stroke:#2c5282,color:#fff
    classDef trading fill:#276749,stroke:#22543d,color:#fff

    M[market_data]:::data --> T[technical_analysis]:::analysis
    M --> L[liquidity_awareness]:::analysis
    
    T --> S[trading_strategy]:::trading
    
    S --> R[risk_management]:::trading
    R --> E[signal_executor]:::trading
```

### 2.2 Skill Lifecycle and Data Flow

1. **`BaseSkill` Definition:** Every skill extends `BaseSkill` and defines its metadata (`name`, `capabilities`, `category`).
2. **Discovery:** `SkillsRegistry.discover()` scans the `euroscope/skills/` directory, loading any module that contains a valid `SKILL.md` and `skill.py`.
3. **Context Passing:** The `SkillContext` object acts as a localized data bus. As skills execute, they mutate specific namespaces within the context (e.g., `ctx.market_data`, `ctx.analysis`, `ctx.signals`).
4. **Execution Safety:** The orchestrator invokes skills via `safe_execute()`. This wrapper intercepts all exceptions, applies an execution timeout (default 30s), and guarantees a standardized `SkillResult` is returned, preventing any single skill failure from crashing the pipeline.
