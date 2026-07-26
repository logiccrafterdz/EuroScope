# EuroScope v5.0 — Gap Analysis & Enhancement Roadmap

*Generated: 2026-07-22 | Based on codebase audit + 5 research reports*

---

## A. GAP ANALYSIS

### A1. CRITICAL GAPS

| # | Gap | Impact | Difficulty | Category |
|---|-----|--------|------------|----------|
| 1 | **No ML forecasting models** — System is 100% LLM + rule-based TA. No statistical/ML models (GARCH is params-only, no predictive model). Research shows PatchTST, ModernTCN, ensembles achieve MAPE 3.3% and Sharpe 5.9. | CRITICAL | HARD | SIGNAL |
| 2 | **No walk-forward validation** — `WalkForwardEvaluator` exists in `evaluation/harness_core.py` but wraps the backtest engine, not CPCV (Combinatorial Purged Cross-Validation). No purging/embargo to prevent lookahead. Backtest overfitting risk is high. | CRITICAL | MODERATE | VALIDATION |
| 3 | **No real order book / tick data** — `microstructure` skill derives everything from OHLCV candles (spread estimate via `avg_range * 0.2`). No L2 book, no VPIN, no footprint charts. 73% of spot FX is algo-driven; you're blind to the primary driver. | CRITICAL | VERY HARD | DATA |
| 4 | **No news NLP pipeline** — `sentiment.py` has FinBERT ONNX but it's only used as a sentiment scoring utility. No NLP→feature extraction pipeline (FinBERT→XGBoost pattern from research: Sharpe 5.87). `fundamental_analysis` skill scrapes headlines but doesn't extract structured signals. | CRITICAL | HARD | SIGNAL |
| 5 | **Regime detection is simplistic** — `regime_adaptive.py` uses ADX > 25 / BB width / ATR ratio. Research shows HMM-based regime detection + dynamic risk budgets outperform by significant margins. No hidden Markov model, no MS-GARCH. | CRITICAL | HARD | SIGNAL |

### A2. HIGH GAPS

| # | Gap | Impact | Difficulty | Category |
|---|-----|--------|------------|----------|
| 6 | **No distributional risk modeling** — `risk_manager.py` uses fixed % risk per trade. No Kelly criterion, no vol targeting, no full return distribution. Quarter-Kelly + vol targeting + drawdown brake is industry standard. | HIGH | MODERATE | RISK |
| 7 | **No multi-timeframe ML ensemble** — Research shows VAE+Transformer+LSTM ensemble achieves MAPE 3.299%. System has `multi_timeframe_confluence` skill but it's rule-based LLM logic, not statistical. | HIGH | HARD | SIGNAL |
| 8 | **LLM as sole "brain"** — Research explicitly states LLMs are alpha *generators*, not standalone traders. System routes all reasoning through GLM 5.2 / DeepSeek. No Chain-of-Thought alpha mining framework (extract numeric features from LLM reasoning). | HIGH | MODERATE | ARCHITECTURE |
| 9 | **No HMM-RL hybrid** — Research shows HMM-RL hybrid achieves Sharpe 5.9 intraday. System has no reinforcement learning component. `adaptive_tuner.py` is rule-based parameter adjustment, not RL. | HIGH | VERY HARD | ARCHITECTURE |
| 10 | **No Elo-rated agent consensus** — `debate_engine.py` and `multi_agent.py` have Bull/Bear/Risk debate, but no self-correcting feedback loop. Elo rating for agent accuracy doesn't exist. No confidence-weighted voting. | HIGH | MODERATE | ARCHITECTURE |
| 11 | **Backtest engine lacks slippage realism** — `execution_simulator.py` exists but backtest uses simple `OfflineExecutor`. No market-impact modeling, no volume-weighted fill simulation. Research shows realistic slippage modeling changes strategy viability. | HIGH | MODERATE | EXECUTION |
| 12 | **No correlation-based risk overlay** — `_get_correlation_multiplier` in risk skill checks GBP/USD and USD/CHF correlations but uses static thresholds. No rolling correlation monitoring, no portfolio-level VaR. | HIGH | MODERATE | RISK |

### A3. MEDIUM GAPS

| # | Gap | Impact | Difficulty | Category |
|---|-----|--------|------------|----------|
| 13 | **No COT report deep integration** — `cot.py` exists but COT data is underutilized. Research shows 3-stage filter (extreme → macro confirm → orderflow timing) is profitable. System has the data but not the multi-stage pipeline. | MEDIUM | EASY | SIGNAL |
| 14 | **No satellite/alternative data** — Research shows 80% directional accuracy from satellite data. Not feasible for single-pair system but alternative data (DXY futures, VIX, bond yields) could be incorporated. | MEDIUM | MODERATE | DATA |
| 15 | **No trailing stop optimization** — `trailing_stop.py` exists but research shows dynamic hedging > static hedging (Deutsche Bank TPA). No ATR-trailing, no chandelier exit, no time-based partial exits. | MEDIUM | EASY | EXECUTION |
| 16 | **No circuit breakers for error loops** — Safety guardrails handle drawdown and spread but not connectivity loss, repeated LLM failures, or API error cascades. | MEDIUM | EASY | RISK |
| 17 | **No foundation model integration** — Amazon Chronos-2 and Google TimesFM 2.5 are zero-shot forecasting models. Could provide baseline forecasts to cross-validate LLM reasoning. | MEDIUM | MODERATE | SIGNAL |
| 18 | **No VPIN / toxicity measurement** — `microstructure` skill estimates spread from candle ranges. VPIN > 0.35 indicates stop hunting. Could be computed from tick volume data. | MEDIUM | MODERATE | DATA |
| 19 | **Forecast tracking lacks proper scoring** — `forecast_tracker.py` tracks accuracy but no proper scoring rules (Brier score, log-loss). No probabilistic calibration. | MEDIUM | EASY | VALIDATION |
| 20 | **No diffusion model denoising** — Research shows diffusion models for signal denoising and synthetic data generation. Could clean noisy indicators before strategy input. | MEDIUM | HARD | SIGNAL |

### A4. LOW GAPS

| # | Gap | Impact | Difficulty | Category |
|---|-----|--------|------------|----------|
| 21 | **No LangGraph orchestration** — System uses custom `orchestrator.py`. LangGraph is the production standard (BlackRock, JPMorgan). Migration would add persistence, streaming, human-in-the-loop. | LOW | VERY HARD | ARCHITECTURE |
| 22 | **No HMM-based intraday vol regime** — Options gamma exposure → vol regime is institutional-grade. Requires options data access which is expensive. | LOW | VERY HARD | DATA |
| 23 | **No self-referential meta-learning** — HyperAgents (Meta AI) approach. Extremely research-grade. Not practical for paper trading system. | LOW | VERY HARD | ARCHITECTURE |

---

## B. ENHANCEMENT ROADMAP

### Phase 1: Quick Wins (Week 1-2)

**Highest impact-to-effort ratio items that can be implemented immediately.**

#### 1.1 CPCV Backtest Validation Framework
- **What**: Replace simple walk-forward with Combinatorial Purged Cross-Validation. Add purging window (remove N bars around each test point to prevent lookahead) and embargo (skip bars after test set).
- **Why**: Prevents overfitting — the #1 silent killer of trading systems. Current `WalkForwardEvaluator` has no purging. Research calls CPCV the "gold standard." Without this, every subsequent enhancement is validated on flawed foundations.
- **How**: Extend `euroscope/evaluation/harness_core.py`. Add purging logic to `WalkForwardEvaluator.run()`: for each window boundary, drop `purge_bars` from train set end and `embargo_bars` from test set start. Add combinatorial splitting.
- **Dependencies**: None. Improves all future validation.

#### 1.2 Proper Kelly Criterion + Vol Targeting Position Sizing
- **What**: Replace fixed `risk_per_trade: 1.0%` with fractional Kelly sizing based on historical win rate and average win/loss ratio, combined with volatility targeting (scale position inversely with realized vol).
- **Why**: Research shows Quarter-Kelly + vol targeting is the institutional standard. Current sizing ignores the actual edge size. A system with 55% win rate and 2:1 R:R should bet fundamentally differently than one with 50% win rate and 1:1 R:R.
- **How**: Modify `euroscope/trading/risk_manager.py` `calculate_position_size()`. Add `kelly_fraction()` method: `f = (p * b - q) / b` where p=win_rate, b=avg_win/avg_loss, q=1-p. Use `min(kelly/4, 0.02)` as fraction. Multiply by `target_vol / realized_vol` for vol targeting.
- **Dependencies**: Needs 20+ closed trades from paper trading for calibration. Falls back to current system until then.

#### 1.3 Circuit Breakers for Error Loops
- **What**: Add connectivity check, LLM failure counter, and API error rate tracking. Auto-pause trading after 3 consecutive LLM failures or 5-minute connectivity loss.
- **Why**: Current safety guardrails only handle market risk. A stuck LLM or API outage could cause the agent to make decisions with stale data.
- **How**: Add `CircuitBreaker` class to `euroscope/trading/safety_guardrails.py`. Track: `llm_failures_consecutive`, `api_errors_last_5min`, `last_successful_data_fetch`. Block signals when any breaker trips.
- **Dependencies**: None.

#### 1.4 COT 3-Stage Filter Pipeline
- **What**: Implement the 3-stage COT filter: (1) detect extreme positioning, (2) confirm with macro divergence, (3) time entry with orderflow/microstructure.
- **Why**: COT data is already collected (`cot.py`) but only surface-level. Research shows the 3-stage filter is the profitable version. Current usage is informational only.
- **How**: Create `euroscope/skills/cot_filter/skill.py`. Stage 1: classify net speculative position as extreme (>90th or <10th percentile). Stage 2: check if macro data supports the contrarian view. Stage 3: only trigger when microstructure confirms (liquidity sweep, volume expansion).
- **Dependencies**: Enhances existing `cot_positioning` skill.

#### 1.5 Adaptive Trailing Stops
- **What**: Replace fixed R:R exit with ATR-based trailing stops (Chandelier Exit variant), plus time-based partial exits (50% at 1:1 R:R, trail remainder).
- **Why**: Research shows dynamic hedging > static hedging. Current system uses fixed `default_rr_ratio: 2.0` TP. This leaves money on the table in trending moves and doesn't protect profits.
- **How**: Extend `euroscope/trading/trailing_stop.py`. Add `ChandelierExit`: stop = highest_high - ATR * 3 (for longs). Add `PartialExit`: close 50% at entry + risk_distance, trail rest with chandelier.
- **Dependencies**: None. Works with current signal flow.

---

### Phase 2: Significant Upgrades (Week 3-4)

**Architecture-level improvements that compound.**

#### 2.1 HMM Regime Detection
- **What**: Replace rule-based regime detection (ADX > 25) with a 3-4 state Hidden Markov Model fit on returns + volatility. States: low-vol trending, high-vol trending, mean-reverting, crisis.
- **Why**: Research shows HMM regime detection enables dynamic risk budgets. Current detection has 4 hardcoded states with simple thresholds. HMM learns transition probabilities and adapts to regime persistence.
- **How**: Replace `euroscope/trading/regime_adaptive.py` `detect_regime()` with HMM. Use `hmmlearn.hmm.GaussianHMM(n_components=4)`. Fit on rolling 60-day window of returns + realized vol. Extract Viterbi path for current state. Scale risk per trade by regime: crisis = 0.25x, trending = 1.2x, ranging = 0.8x.
- **Dependencies**: Needs 60+ days of historical data (already available via yfinance).

#### 2.2 Chain-of-Thought Alpha Mining
- **What**: Extract structured numeric features from LLM reasoning text. Instead of using LLM output as the final signal, parse it into quantifiable alpha factors.
- **Why**: Research explicitly shows LLMs are alpha *generators* not traders. Current system feeds LLM text directly as signal. Mining numeric features enables ML models to learn from LLM insights without the noise of natural language.
- **How**: Create `euroscope/brain/alpha_miner.py`. After each LLM analysis, extract: sentiment_score (from word embeddings), mentioned_levels (parse price levels from text), directional_bias (BULLISH/BEARISH/NEUTRAL mapped to +1/-1/0), urgency_words (count of time-sensitive terms). Store as features in a feature store. These feed into Phase 3 ML models.
- **Dependencies**: Works with existing LLM pipeline. No changes to `llm_interface.py`.

#### 2.3 Elo-Rated Agent Consensus
- **What**: Assign Elo ratings to each debate agent (Bull, Bear, Risk Manager). Weight their votes by historical accuracy. Add self-correction: agents that are consistently wrong get lower weight.
- **Why**: Research shows debate amplifies correctness (NeurIPS 2025). Current `DeliberationCommittee` treats all agents equally. The Risk Manager uses a different LLM (`force_provider="fallback"`) but accuracy isn't tracked.
- **How**: Extend `euroscope/brain/multi_agent.py`. Add `EloTracker` class: initialize all agents at 1500. After each debate outcome, update ratings using standard Elo formula (K=32). Weight final vote: `score = sum(elo_weight * vote)`. Store ratings in `storage.save_json("elo_ratings", ...)`.
- **Dependencies**: Needs `prediction_tracker` to grade debate outcomes.

#### 2.4 Enhanced News NLP Pipeline
- **What**: Build a pipeline that goes from raw news → FinBERT sentiment → structured signal features. Add event classification (rate decision, geopolitical, data release) and impact scoring.
- **Why**: Research shows NLP on GDELT → FinBERT → XGBoost achieves Sharpe 5.87 on EUR/USD. Current `fundamental_analysis` skill scrapes news but treats it as undifferentiated text for LLM consumption.
- **How**: Extend `euroscope/data/sentiment.py` and `euroscope/skills/fundamental_analysis/skill.py`. Pipeline: (1) scrape headlines (existing), (2) classify event type (new: rate_decision, geopolitical, data_release, etc.), (3) FinBERT sentiment score (existing), (4) time-decay weighting (recent = higher weight), (5) aggregate into `sentiment_signal` feature. Store as structured data, not just text.
- **Dependencies**: FinBERT ONNX model already exists at `euroscope/data/models/finbert_onnx_quantized/`.

#### 2.5 Multi-Source Data Fusion for Feature Store
- **What**: Create a unified feature store that aggregates signals from all data sources into a single time-aligned DataFrame. Features: DXY correlation, VIX level, bond yield spread, COT positioning, sentiment score, technical indicators — all at the same timestamp.
- **Why**: Research shows the best ML models need clean, aligned feature matrices. Currently each skill produces isolated data that the LLM loosely combines. A feature store enables proper ML training.
- **How**: Create `euroscope/data/feature_store.py`. On each analysis cycle: (1) compute all features, (2) align to current timestamp, (3) store in SQLite/Postgres with proper schema. Add `get_feature_vector(timestamp)` for ML model consumption. Use `pandas.DataFrame` with datetime index.
- **Dependencies**: Needs data from all existing skills. No changes to individual skills.

---

### Phase 3: Advanced Capabilities (Month 2)

**ML-powered signal generation and ensemble forecasting.**

#### 3.1 PatchTST / ModernTCN Forecasting Model
- **What**: Train a PatchTST (Patch Time Series Transformer) or ModernTCN model on the feature store data to produce directional probability forecasts. Use as a "quantitative signal" alongside LLM reasoning.
- **Why**: Research shows PatchTST and ModernTCN are state-of-the-art for time series forecasting. ModernTCN won across 918 experiments. A trained model on your feature store can produce consistent, fast forecasts without LLM API costs.
- **How**: Create `euroscope/ml/forecaster.py`. Train on 2+ years of EUR/USD hourly data with the feature store features. Input: 168-hour lookback window (1 week) of features. Output: probability of up/down/flat over next 24 hours. Use `torch` + `tsai` library (designed for this). Validate with CPCV (Phase 1). Deploy as ONNX for inference speed.
- **Dependencies**: Phase 2.5 (feature store), Phase 1.1 (CPCV validation).

#### 3.2 Ensemble Forecasting with Foundation Models
- **What**: Combine the PatchTST model with Amazon Chronos-2 / Google TimesFM 2.5 zero-shot forecasts and the LLM ensemble. Weight all three by historical accuracy (IC metric from evaluation harness).
- **Why**: Research shows ensembles beat any single model. VAE+Transformer+LSTM achieves MAPE 3.299%. Your existing LLM ensemble (`forecast_ensemble`) is a start, but adding quantitative models creates true diversity.
- **How**: Extend `euroscope/forecast/engine.py`. Add `QuantitativeForecaster` class that runs PatchTST inference. Add `FoundationForecaster` for Chronos-2 (API call or local). Combine all three: `final_signal = w1 * llm_signal + w2 * patchtst_signal + w3 * chronos_signal`. Weights from rolling IC: `w_i = IC_i / sum(IC_all)`.
- **Dependencies**: Phase 3.1 (PatchTST model).

#### 3.3 Two-Layer Risk Architecture
- **What**: Split risk management into sub-strategy level (existing `RiskManager`) and portfolio overlay level (new). Portfolio overlay enforces correlation-based VaR, max portfolio heat, and regime-scaled risk budgets.
- **Why**: Research shows two-layer risk (sub-strategy + portfolio overlay) is the institutional standard. Current system has single-layer risk. For a single-pair system, "portfolio" means managing multiple concurrent signals (trend + mean-reversion + breakout strategies running simultaneously).
- **How**: Create `euroscope/trading/portfolio_risk.py`. Track all open positions. Compute: portfolio VaR (95%, 1-day, from historical simulation), correlation between open positions (even same-pair, different-timeframe positions have different risk profiles), regime-scaled risk budget (HMM regime → total risk budget). Override sub-strategy sizing when portfolio heat > threshold.
- **Dependencies**: Phase 2.1 (HMM regime detection).

#### 3.4 Distributional RL for Exit Management
- **What**: Use distributional reinforcement learning (C51 or QR-DQN) to learn optimal exit policies. Instead of fixed SL/TP, the RL agent learns a policy: hold / partial_close / full_close / move_stop based on the full return distribution.
- **Why**: Research shows distributional RL models the full return distribution, not just expected value. This produces more nuanced exit decisions — especially important for managing drawdowns and letting winners run.
- **How**: Create `euroscope/ml/exit_rl.py`. State: current PnL, time_in_trade, vol_regime, momentum_score, distance_to_tp, distance_to_sl. Action space: {hold, close_25%, close_50%, close_75%, close_all, move_sl_to_breakeven}. Train on historical paper trades using C51 algorithm. Deploy as ONNX for fast inference.
- **Dependencies**: Phase 3.3 (portfolio risk for state features), Phase 1.1 (CPCV for validation).

#### 3.5 Behavioral Validation Suite
- **What**: Create tests that validate the system behaves correctly under edge cases: extreme volatility, data gaps, LLM timeouts, conflicting signals, rapid regime shifts. Not correctness tests, but *behavioral* tests.
- **Why**: 690 pytest tests exist but they test individual components. The system can fail at integration points. Research shows most algo disasters happen during regime transitions and connectivity issues.
- **How**: Extend `euroscope/testing/behavioral_validator.py` (already exists). Add scenarios: (1) flash crash simulation (100-pip drop in 1 minute), (2) LLM returns garbage output, (3) data feed goes silent for 5 minutes, (4) conflicting signals from Bull vs Bear debate, (5) regime shifts every 30 minutes. Each scenario has expected behavior.
- **Dependencies**: None, but benefits from all other phases.

---

### Phase 4: Cutting Edge (Month 3+)

**Research-grade capabilities for competitive edge.**

#### 4.1 Diffusion Model Signal Denoising
- **What**: Use a denoising diffusion probabilistic model to clean noisy technical indicators before they reach the strategy engine. Trained to separate signal from noise in indicator time series.
- **Why**: Research shows diffusion models outperform traditional denoising (wavelet, Kalman). Noisy RSI/MACD signals cause false entries. Clean signals improve Sharpe by 15-25% in backtests.
- **How**: Create `euroscope/ml/diffusion_denoiser.py`. Train a small diffusion model on historical indicator values + forward returns. Input: noisy indicators. Output: denoised indicators. Use `diffusers` library with 1D UNet architecture. Validate: compare strategy performance with/without denoising using CPCV.
- **Dependencies**: Phase 2.5 (feature store), Phase 3.1 (ML infrastructure).

#### 4.2 PPO with Auxiliary Tasks
- **What**: Use Proximal Policy Optimization (PPO) with auxiliary tasks (volatility prediction, regime classification, next-return prediction) to improve the main trading policy.
- **Why**: Research shows PPO with auxiliary tasks gives +42% improvement on EUR/USD. The auxiliary tasks act as regularizers and force the policy to learn market structure.
- **How**: Extend `euroscope/ml/exit_rl.py` into full PPO agent. State space expanded to include full feature vector. Action space: continuous (position size: -1 to +1). Auxiliary losses: MSE for vol prediction, cross-entropy for regime, MSE for next-return. Use `stable-baselines3` PPO with custom `AuxiliaryPolicy`.
- **Dependencies**: Phase 3.4 (RL infrastructure), Phase 3.1 (ML models).

#### 4.3 Self-Correcting Feedback Loops
- **What**: Implement a meta-learning loop where the system evaluates its own prediction accuracy over time and automatically adjusts: confidence thresholds, indicator weights, regime detection parameters, risk multipliers.
- **Why**: Research shows self-referential meta-learning (HyperAgents) adapts faster to market changes. Current `adaptive_tuner.py` does this manually with static rules.
- **How**: Create `euroscope/learning/meta_learner.py`. Every 100 trades: compute IC, calibration error, regime accuracy, session performance. If IC drops below 0.1: widen confidence thresholds. If calibration is off: adjust confidence scaling. If regime accuracy < 60%: switch to simpler regime model. Store adjustments in `meta_state.json`.
- **Dependencies**: Phase 1.1 (CPCV), Phase 2.5 (feature store).

#### 4.4 Real-Time Feature Importance Dashboard
- **What**: Live dashboard showing which features (indicators, sentiment, COT, liquidity) are currently driving the system's decisions. SHAP values for each prediction.
- **Why**: Black-box LLM decisions are unexplainable. For live trading, you need to understand *why* the system is making each decision. Research shows explainability improves manual override decisions.
- **How**: Add SHAP analysis to the ML models (Phase 3.1). For LLM decisions, extract attention patterns. Create `euroscope/analytics/explainer.py`. Expose via existing Telegram bot or web dashboard (`euroscope/bot/api_server.py`).
- **Dependencies**: Phase 3.1 (ML models need SHAP integration).

---

## C. WHAT NOT TO DO

These sound impressive but are **NOT worth implementing** for a single-pair EUR/USD paper trading system:

| Item | Why Not |
|------|---------|
| **Multi-agent system with 7+ specialized LLMs (TradingAgents-style)** | Overkill. You already have Bull/Bear/Risk debate. Adding 7 agents increases API costs 7x with diminishing returns. TradingAgents' Sharpe 8.21 is on multi-asset portfolios, not single-pair. |
| **Satellite data / alternative data ingestion** | Not accessible for retail. Requires institutional data feeds ($10K+/year). The 80% accuracy claim is for agricultural commodities, not FX. |
| **20-agent ensemble (AI NeuroSignal-style)** | 20 agents for single-pair EUR/USD is absurd complexity. Your 3-agent debate is sufficient. Focus on making 3 agents *better* (Elo ratings) rather than adding more. |
| **Full LangGraph migration** | Your custom orchestrator works. LangGraph adds persistence/checkpointing but you don't need it for 15-minute analysis cycles. Migration cost is high, benefit is marginal for paper trading. |
| **Real-time order book heatmap visualization** | Requires L2 tick data ($500+/month). Your OHLCV-based microstructure analysis is a reasonable proxy. Visual dashboards don't improve decision quality. |
| **Options gamma exposure analysis** | Requires options chain data (expensive) and is most relevant for market makers, not directional traders. |
| **Full GARCH(1,1) parameter estimation** | Your exponentially-weighted GARCH approximation in `volatility_forecast` is sufficient. Full MLE GARCH estimation requires significant compute and is overkill for volatility regime classification. |
| **HFT-level execution optimization** | You're running on 15-minute cycles. Sub-millisecond execution optimization is irrelevant. Focus on signal quality, not execution speed. |
| **Building your own LLM from scratch / fine-tuning** | Free APIs (GLM 5.2, DeepSeek) are sufficient. Fine-tuning on trading data sounds good but you don't have enough labeled data (<1000 trades). Use LLMs as reasoning engines, not predictors. |
| **Multi-asset correlation trading** | You're a single-pair system. Correlation analysis with DXY/GBP/CHF is useful as an input but don't expand to trading multiple pairs. Focus beats diversification at your scale. |
| **Complex walk-forward optimization (grid search over 50+ params)** | Overfitting trap. With 50 parameters and limited data, you'll fit noise. Use CPCV + simple random search over <10 key parameters. |
| **Intraday scalping (1-min / 5-min timeframes)** | Your data infrastructure is H1/H4 candles. Scalping requires tick data and sub-second execution. Stay on H1-H4-D1 timeframes where your data quality is good. |

---

## Summary: Priority Matrix

```
                        HIGH IMPACT
                            │
    ┌───────────────────────┼───────────────────────┐
    │                       │                       │
    │  Phase 1: CPCV        │  Phase 3: ML Models   │
    │  Phase 1: Kelly Sizing │  Phase 3: Ensemble    │
    │  Phase 1: Circuit Bkrs │  Phase 3: Dist RL     │
    │  Phase 2: HMM Regime  │  Phase 4: Diffusion   │
    │  Phase 2: Alpha Mining│  Phase 4: PPO+Aux     │
    │  Phase 2: Elo Agents  │  Phase 4: Meta-Learn  │
    │                       │                       │
LOW ────────────────────────┼─────────────────────── HIGH
DIFFICULTY                  │                   DIFFICULTY
    │                       │                       │
    │  Phase 1: COT Filter  │  Phase 4: SHAP Board  │
    │  Phase 1: Trail Stops │                       │
    │  Phase 2: NLP Pipeline│                       │
    │  Phase 2: FeatureStore│                       │
    │  Phase 3: Behave Tests│                       │
    │                       │                       │
    └───────────────────────┼───────────────────────┘
                            │
                        LOW IMPACT
```

**Expected outcome if Phase 1-2 are implemented well:**
- Win rate: 50% → 55-58% (better regime detection + COT filter)
- Sharpe ratio: ~1.0 → 2.0+ (Kelly sizing + trailing stops + circuit breakers)
- Max drawdown: Uncontrolled → Capped at 8% (two-layer risk)
- Signal quality: LLM-only → LLM + quantitative cross-validation

**Expected outcome if Phase 3-4 are implemented:**
- Sharpe ratio: 2.0 → 3.5-5.0 (ML ensemble + RL exits + meta-learning)
- Adaptability: Manual tuning → Self-correcting (meta-learning loop)
- Robustness: Fragile at regime edges → Resilient (diffusion denoising + behavioral tests)

---

*End of Report*
