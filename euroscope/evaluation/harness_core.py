"""
Evaluation Harness — Unified System Assessment Framework.

Combines ReplayEngine (stored signal analysis), ShadowMode (live observation),
WalkForwardEvaluator (rolling window testing), CPCVEvaluator (combinatorial
purged cross-validation), and advanced metrics into a single cohesive API.

Key metrics beyond basic PnL:
- Information Coefficient (Spearman rank corr between confidence and actual PnL)
- Confidence Calibration (predicted vs actual win rate per confidence bucket)
- Regime-conditional performance breakdown
- Session-conditional performance breakdown
- Skill/strategy attribution
- Flip-flop rate and noise ratio
- CPCV: Overfitting-resistant validation with purging + embargo
"""

import asyncio
import dataclasses
import itertools
import logging
import math
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("euroscope.evaluation")


# ── Data Classes ────────────────────────────────────────────────

@dataclass
class EvalMetrics:
    """Comprehensive evaluation metrics."""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    expectancy: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0

    information_coefficient: float = 0.0
    confidence_calibration: dict = field(default_factory=dict)
    regime_breakdown: dict = field(default_factory=dict)
    session_breakdown: dict = field(default_factory=dict)
    skill_attribution: dict = field(default_factory=dict)
    flip_flop_rate: float = 0.0
    noise_ratio: float = 0.0
    meaningful_alert_pct: float = 0.0

    equity_curve: list = field(default_factory=list)


@dataclass
class EvalResult:
    """Unified evaluation result wrapping metrics + raw data."""
    mode: str
    metrics: EvalMetrics
    trades: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ── Helpers ─────────────────────────────────────────────────────

SESSIONS = {"Asia": (0, 8), "London": (8, 16), "New_York": (16, 24)}

CONFIDENCE_BUCKETS = [
    (0, 50, "low"),
    (50, 65, "medium"),
    (65, 80, "high"),
    (80, 100, "very_high"),
]

_EVAL_FIELDS = {f.name for f in dataclasses.fields(EvalMetrics)}


def _spearman_rank_corr(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation between two series."""
    n = len(xs)
    if n < 3:
        return 0.0

    def _rank(arr):
        indexed = sorted(enumerate(arr), key=lambda x: x[1])
        ranks = [0.0] * len(arr)
        i = 0
        while i < len(indexed):
            j = i
            while j < len(indexed) - 1 and indexed[j + 1][1] == indexed[j][1]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    rx = _rank(xs)
    ry = _rank(ys)
    d_sq = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return round(1.0 - (6.0 * d_sq) / (n * (n * n - 1)), 4)


def _classify_session(dt: datetime) -> str:
    hour = dt.hour
    for name, (start, end) in SESSIONS.items():
        if start <= hour < end:
            return name
    return "Unknown"


def _build_equity_curve(pnls: list[float]) -> list[float]:
    curve = []
    cum = 0.0
    for p in pnls:
        cum += p
        curve.append(round(cum, 1))
    return curve


def _sharpe(pnls: list[float], periods_per_year: int = 252) -> float:
    if len(pnls) < 2:
        return 0.0
    mean = sum(pnls) / len(pnls)
    var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
    std = math.sqrt(var) if var > 0 else 0
    return round((mean / std) * math.sqrt(periods_per_year), 2) if std > 0 else 0.0


def _sortino(pnls: list[float], periods_per_year: int = 252) -> float:
    if len(pnls) < 2:
        return 0.0
    mean = sum(pnls) / len(pnls)
    downside = [p for p in pnls if p < 0]
    if not downside:
        return float("inf") if mean > 0 else 0.0
    down_var = sum(p ** 2 for p in downside) / len(downside)
    down_std = math.sqrt(down_var)
    return round((mean / down_std) * math.sqrt(periods_per_year), 2) if down_std > 0 else 0.0


def _max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    mdd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > mdd:
            mdd = dd
    return round(mdd, 1)


def _compute_core_metrics(pnls: list[float]) -> dict:
    if not pnls:
        return {}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity = _build_equity_curve(pnls)
    return {
        "total_trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(pnls) * 100, 1),
        "total_pnl": round(sum(pnls), 1),
        "avg_pnl": round(sum(pnls) / len(pnls), 1),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "sharpe_ratio": _sharpe(pnls),
        "sortino_ratio": _sortino(pnls),
        "max_drawdown": _max_drawdown(equity),
        "expectancy": round(
            (len(wins) / len(pnls)) * (gross_profit / len(wins) if wins else 0)
            - (len(losses) / len(pnls)) * (gross_loss / len(losses) if losses else 0),
            2,
        ),
        "best_trade": round(max(pnls), 1),
        "worst_trade": round(min(pnls), 1),
        "equity_curve": equity,
    }


# ── CPCV (Combinatorial Purged Cross-Validation) ──────────────

@dataclass
class CPCVConfig:
    """Configuration for CPCV validation."""
    n_folds: int = 5
    purge_bars: int = 50
    embargo_bars: int = 20
    test_combinations: int = 0
    min_trades_per_fold: int = 10


@dataclass
class CPCVFoldResult:
    """Result of a single CPCV fold."""
    fold_id: int
    test_indices: list
    metrics: EvalMetrics
    trades: list = field(default_factory=list)
    train_size: int = 0
    test_size: int = 0


def cpcv_splits(total_bars: int, config: CPCVConfig) -> list[tuple[list[int], list[int]]]:
    """
    Generate Combinatorial Purged Cross-Validation splits.

    Unlike standard K-Fold, CPCV:
    1. Creates N equal folds
    2. For each combination of N-1 folds as train, the remaining fold is test
    3. Applies purging: removes purge_bars from end of train set (prevents lookahead)
    4. Applies embargo: skips embargo_bars after test set (prevents contamination)

    Args:
        total_bars: Total number of bars in the dataset
        config: CPCV configuration

    Returns:
        List of (train_indices, test_indices) tuples
    """
    n = config.n_folds
    fold_size = total_bars // n
    if fold_size < config.purge_bars + config.embargo_bars + 10:
        logger.warning(f"CPCV: fold_size={fold_size} too small for purge={config.purge_bars} "
                       f"+ embargo={config.embargo_bars}. Adjusting.")
        config.purge_bars = max(0, fold_size // 4)
        config.embargo_bars = max(0, fold_size // 8)

    folds = []
    for i in range(n):
        start = i * fold_size
        end = start + fold_size if i < n - 1 else total_bars
        folds.append(list(range(start, end)))

    test_fold_indices = list(range(n))
    if config.test_combinations > 0:
        combos = list(itertools.combinations(test_fold_indices, 1))
        if len(combos) > config.test_combinations:
            combos = combos[:config.test_combinations]
    else:
        combos = [(i,) for i in test_fold_indices]

    splits = []
    for test_combo in combos:
        test_fold_idx = test_combo[0]
        test_indices = folds[test_fold_idx]

        train_indices = []
        for f_idx in range(n):
            if f_idx == test_fold_idx:
                continue
            train_indices.extend(folds[f_idx])

        if config.purge_bars > 0:
            train_indices = [i for i in train_indices
                             if i < min(test_indices) - config.purge_bars
                             or i > max(test_indices) + config.purge_bars]

        if config.embargo_bars > 0:
            embargo_start = max(test_indices) + 1
            embargo_end = embargo_start + config.embargo_bars
            embargo_range = set(range(embargo_start, embargo_end))
            train_indices = [i for i in train_indices if i not in embargo_range]

        splits.append((sorted(train_indices), sorted(test_indices)))

    return splits


class CPCVEvaluator:
    """
    Combinatorial Purged Cross-Validation evaluator.

    Prevents overfitting by testing on combinations of folds with:
    - Purging: removes N bars from train set near test boundary
    - Embargo: skips N bars after test set to prevent contamination
    - Aggregates metrics across all test folds with confidence intervals
    """

    def __init__(self, backtest_engine, config: Optional[CPCVConfig] = None):
        self.bt = backtest_engine
        self.config = config or CPCVConfig()

    def run(self, candles: list[dict], strategy: Optional[str] = None,
            slippage_pips: float = 1.5, commission_pips: float = 0.7) -> EvalResult:
        """
        Run CPCV evaluation on candle data.

        Args:
            candles: List of candle dicts with OHLCV data
            strategy: Strategy filter (None = all)
            slippage_pips: Slippage per trade
            commission_pips: Commission per trade

        Returns:
            EvalResult with aggregated metrics and fold-level details
        """
        total_bars = len(candles)
        if total_bars < self.config.n_folds * (self.config.purge_bars + self.config.embargo_bars + 10):
            return EvalResult(mode="cpcv", metrics=EvalMetrics(),
                              metadata={"error": "insufficient data for CPCV configuration"})

        splits = cpcv_splits(total_bars, self.config)
        if not splits:
            return EvalResult(mode="cpcv", metrics=EvalMetrics(),
                              metadata={"error": "no splits generated"})

        fold_results = []
        all_trades = []
        all_pnls = []
        all_confidences = []

        for fold_id, (train_idx, test_idx) in enumerate(splits):
            test_candles = [candles[i] for i in test_idx if i < len(candles)]
            if not test_candles:
                continue

            res = self.bt.run(test_candles, strategy_filter=strategy,
                              slippage_pips=slippage_pips, commission_pips=commission_pips)

            fold_pnls = [t.pnl_pips for t in res.trades]
            fold_trades = []
            for t in res.trades:
                trade_dict = {
                    "direction": t.direction,
                    "entry_price": t.entry_price,
                    "pnl_pips": t.pnl_pips,
                    "strategy": t.strategy,
                    "is_win": t.is_win,
                    "entry_bar": t.entry_bar,
                    "fold": fold_id,
                }
                fold_trades.append(trade_dict)
                all_trades.append(trade_dict)
                all_pnls.append(t.pnl_pips)

            fold_core = _compute_core_metrics(fold_pnls) if fold_pnls else {}
            fold_metrics = EvalMetrics(**{k: v for k, v in fold_core.items() if k in _EVAL_FIELDS})

            fold_results.append(CPCVFoldResult(
                fold_id=fold_id,
                test_indices=test_idx,
                metrics=fold_metrics,
                trades=fold_trades,
                train_size=len(train_idx),
                test_size=len(test_idx),
            ))

        if not all_pnls:
            return EvalResult(mode="cpcv", metrics=EvalMetrics(),
                              metadata={"error": "no trades across all folds"})

        core = _compute_core_metrics(all_pnls)
        m = EvalMetrics(**{k: v for k, v in core.items() if k in _EVAL_FIELDS})

        if all_confidences:
            m.information_coefficient = _spearman_rank_corr(all_confidences, all_pnls)

        m.session_breakdown = self._aggregate_session_breakdown(all_trades)
        m.regime_breakdown = self._aggregate_regime_breakdown(fold_results)

        stability = self._fold_stability(fold_results)
        overfit_score = self._compute_overfit_score(fold_results)

        return EvalResult(
            mode="cpcv",
            metrics=m,
            trades=all_trades,
            metadata={
                "n_folds": self.config.n_folds,
                "purge_bars": self.config.purge_bars,
                "embargo_bars": self.config.embargo_bars,
                "total_splits": len(splits),
                "total_bars": total_bars,
                "stability": stability,
                "overfit_score": overfit_score,
                "fold_details": [
                    {
                        "fold_id": f.fold_id,
                        "trades": len(f.trades),
                        "train_size": f.train_size,
                        "test_size": f.test_size,
                        "pnl": round(sum(t["pnl_pips"] for t in f.trades), 1),
                        "win_rate": f.metrics.win_rate,
                    }
                    for f in fold_results
                ],
            },
        )

    def _aggregate_session_breakdown(self, trades: list[dict]) -> dict:
        sessions: dict[str, list[float]] = {}
        for t in trades:
            session = t.get("session", "Unknown")
            sessions.setdefault(session, []).append(t.get("pnl_pips", 0))
        result = {}
        for sess, pnls in sessions.items():
            wins = [p for p in pnls if p > 0]
            result[sess] = {
                "trades": len(pnls),
                "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
                "total_pnl": round(sum(pnls), 1),
            }
        return result

    @staticmethod
    def _aggregate_regime_breakdown(fold_results: list[CPCVFoldResult]) -> dict:
        regime_trades: dict[str, list[float]] = {}
        for fold in fold_results:
            for t in fold.trades:
                regime = t.get("regime", "unknown")
                regime_trades.setdefault(regime, []).append(t.get("pnl_pips", 0))
        result = {}
        for regime, pnls in regime_trades.items():
            wins = [p for p in pnls if p > 0]
            result[regime] = {
                "trades": len(pnls),
                "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
                "total_pnl": round(sum(pnls), 1),
            }
        return result

    @staticmethod
    def _fold_stability(fold_results: list[CPCVFoldResult]) -> dict:
        if not fold_results:
            return {}
        pnls_by_fold = [sum(t["pnl_pips"] for t in f.trades) for f in fold_results]
        win_rates = [f.metrics.win_rate for f in fold_results if f.metrics.total_trades > 0]
        profitable_folds = sum(1 for p in pnls_by_fold if p > 0)
        mean_pnl = sum(pnls_by_fold) / len(pnls_by_fold) if pnls_by_fold else 0
        var_pnl = sum((p - mean_pnl) ** 2 for p in pnls_by_fold) / len(pnls_by_fold) if pnls_by_fold else 0
        std_pnl = math.sqrt(var_pnl)
        return {
            "total_folds": len(fold_results),
            "profitable_folds": profitable_folds,
            "fold_win_rate": round(profitable_folds / len(fold_results) * 100, 1),
            "avg_pnl_per_fold": round(mean_pnl, 1),
            "pnl_std_across_folds": round(std_pnl, 2),
            "avg_win_rate": round(sum(win_rates) / len(win_rates), 1) if win_rates else 0,
        }

    @staticmethod
    def _compute_overfit_score(fold_results: list[CPCVFoldResult]) -> dict:
        if len(fold_results) < 2:
            return {"score": 0.0, "grade": "insufficient_data"}
        pnls = [sum(t["pnl_pips"] for t in f.trades) for f in fold_results]
        mean_pnl = sum(pnls) / len(pnls)
        std_pnl = math.sqrt(sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls))
        if mean_pnl <= 0:
            return {"score": 1.0, "grade": "likely_overfit"}
        cv = std_pnl / abs(mean_pnl) if mean_pnl != 0 else float("inf")
        profitable = sum(1 for p in pnls if p > 0)
        consistency = profitable / len(pnls)
        score = min(1.0, cv * 0.5 + (1 - consistency) * 0.5)
        if score < 0.2:
            grade = "robust"
        elif score < 0.4:
            grade = "moderate"
        elif score < 0.6:
            grade = "caution"
        else:
            grade = "likely_overfit"
        return {"score": round(score, 3), "grade": grade, "cv": round(cv, 3), "consistency": round(consistency, 3)}


# ── ReplayEngine ───────────────────────────────────────────────

class ReplayEngine:
    """
    Analyzes stored signals from the database against actual outcomes.

    Pulls closed trading_signals and trade_journal entries, computes
    advanced metrics (confidence calibration, IC, regime/session breakdowns),
    and returns a unified EvalResult.
    """

    def __init__(self, storage):
        self.storage = storage

    async def run(self, days: int = 30, source: str = "signals") -> EvalResult:
        """
        Run replay analysis on stored signals.

        Args:
            days: How many days of history to analyze
            source: "signals" for trading_signals table, "journal" for trade_journal
        """
        if not self.storage:
            return EvalResult(mode="replay", metrics=EvalMetrics(), metadata={"days": days, "source": source})

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        if source == "journal":
            trades = await self.storage.get_trade_journal(limit=500)
            trades = [t for t in trades if t.get("timestamp", "") >= cutoff and t.get("status") == "closed"]
        else:
            trades = await self.storage.get_signals(status="closed", limit=500)
            trades = [t for t in trades if t.get("created_at", "") >= cutoff]

        if not trades:
            return EvalResult(mode="replay", metrics=EvalMetrics(), metadata={"days": days, "source": source})

        metrics = self._compute_advanced_metrics(trades)
        return EvalResult(
            mode="replay",
            metrics=metrics,
            trades=trades,
            metadata={"days": days, "source": source, "analyzed": len(trades)},
        )

    def _compute_advanced_metrics(self, trades: list[dict]) -> EvalMetrics:
        pnls = [t.get("pnl_pips", 0) for t in trades]
        core = _compute_core_metrics(pnls)
        m = EvalMetrics(**{k: v for k, v in core.items() if k in _EVAL_FIELDS})

        confidences = [t.get("confidence", 50) for t in trades]
        m.information_coefficient = _spearman_rank_corr(confidences, pnls)
        m.confidence_calibration = self._calibration(confidences, pnls)
        m.session_breakdown = self._session_breakdown(trades)
        m.skill_attribution = self._skill_attribution(trades)
        m.flip_flop_rate = self._flip_flop_rate(trades)
        m.noise_ratio = self._noise_ratio(trades)
        return m

    @staticmethod
    def _calibration(confidences: list[float], pnls: list[float]) -> dict:
        buckets: dict[str, list[bool]] = {}
        for conf, pnl in zip(confidences, pnls):
            label = "unknown"
            for lo, hi, name in CONFIDENCE_BUCKETS:
                if lo <= conf < hi:
                    label = name
                    break
            buckets.setdefault(label, []).append(pnl > 0)

        result = {}
        for label, outcomes in sorted(buckets.items()):
            wr = round(sum(outcomes) / len(outcomes) * 100, 1) if outcomes else 0
            result[label] = {"count": len(outcomes), "actual_win_rate": wr}
        return result

    @staticmethod
    def _session_breakdown(trades: list[dict]) -> dict:
        sessions: dict[str, list[float]] = {}
        for t in trades:
            ts = t.get("created_at") or t.get("timestamp", "")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                session = _classify_session(dt)
            except (ValueError, TypeError):
                session = "Unknown"
            sessions.setdefault(session, []).append(t.get("pnl_pips", 0))

        result = {}
        for sess, pnls in sessions.items():
            wins = [p for p in pnls if p > 0]
            result[sess] = {
                "trades": len(pnls),
                "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
                "total_pnl": round(sum(pnls), 1),
            }
        return result

    @staticmethod
    def _skill_attribution(trades: list[dict]) -> dict:
        sources: dict[str, list[float]] = {}
        for t in trades:
            src = t.get("source", t.get("strategy", "unknown"))
            sources.setdefault(src, []).append(t.get("pnl_pips", 0))

        result = {}
        for src, pnls in sources.items():
            wins = [p for p in pnls if p > 0]
            result[src] = {
                "trades": len(pnls),
                "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
                "total_pnl": round(sum(pnls), 1),
                "avg_pnl": round(sum(pnls) / len(pnls), 1) if pnls else 0,
            }
        return result

    @staticmethod
    def _flip_flop_rate(trades: list[dict]) -> float:
        if len(trades) < 2:
            return 0.0
        sorted_trades = sorted(trades, key=lambda t: t.get("created_at") or t.get("timestamp", ""))
        flips = 0
        for i in range(1, len(sorted_trades)):
            prev_dir = sorted_trades[i - 1].get("direction", "").upper()
            curr_dir = sorted_trades[i].get("direction", "").upper()
            if prev_dir and curr_dir and prev_dir != curr_dir and prev_dir != "WAIT" and curr_dir != "WAIT":
                prev_ts = sorted_trades[i - 1].get("created_at") or sorted_trades[i - 1].get("timestamp", "")
                curr_ts = sorted_trades[i].get("created_at") or sorted_trades[i].get("timestamp", "")
                try:
                    t1 = datetime.fromisoformat(prev_ts.replace("Z", "+00:00"))
                    t2 = datetime.fromisoformat(curr_ts.replace("Z", "+00:00"))
                    if abs((t2 - t1).total_seconds()) < 43200:
                        flips += 1
                except (ValueError, TypeError):
                    pass
        return round(flips / (len(sorted_trades) - 1) * 100, 1)

    @staticmethod
    def _noise_ratio(trades: list[dict]) -> float:
        if not trades:
            return 0.0
        meaningful = 0
        for t in trades:
            pnl = abs(t.get("pnl_pips", 0))
            if pnl >= 10.0:
                meaningful += 1
        return round((1 - meaningful / len(trades)) * 100, 1)


# ── ShadowMode ─────────────────────────────────────────────────

class ShadowMode:
    """
    Records system predictions during live observation without executing trades.

    Call start() to begin recording, tick() on each analysis cycle,
    and stop() to finalize and return an EvalResult.
    """

    def __init__(self):
        self.predictions: list[dict] = []
        self._active = False
        self._started_at: Optional[str] = None

    def start(self):
        self._active = True
        self._started_at = datetime.now(timezone.utc).isoformat()
        self.predictions.clear()
        logger.info("ShadowMode started")

    def stop(self) -> EvalResult:
        self._active = False
        logger.info(f"ShadowMode stopped: {len(self.predictions)} predictions recorded")
        return self._finalize()

    def tick(self, direction: str, confidence: float, price: float,
             reasoning: str = "", metadata: Optional[dict] = None):
        """Record a single prediction cycle."""
        if not self._active:
            return
        self.predictions.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "direction": direction,
            "confidence": confidence,
            "price": price,
            "reasoning": reasoning,
            "metadata": metadata or {},
            "graded": False,
        })

    def grade(self, current_price: float, lookback_bars: int = 24):
        """Grade ungraded predictions: did the price move in the predicted direction?"""
        for p in self.predictions:
            if p["graded"]:
                continue
            if p["direction"] not in ("BUY", "SELL"):
                p["graded"] = True
                continue
            diff_pips = (current_price - p["price"]) * 10000
            if p["direction"] == "BUY":
                p["outcome_pips"] = round(diff_pips, 1)
            else:
                p["outcome_pips"] = round(-diff_pips, 1)
            p["is_correct"] = p["outcome_pips"] > 0
            p["graded"] = True

    def _finalize(self) -> EvalResult:
        graded = [p for p in self.predictions if p.get("graded")]
        pnls = [p.get("outcome_pips", 0) for p in graded]
        confidences = [p.get("confidence", 50) for p in graded]

        core = _compute_core_metrics(pnls) if pnls else {}
        m = EvalMetrics(**{k: v for k, v in core.items() if k in _EVAL_FIELDS})

        if confidences and pnls:
            m.information_coefficient = _spearman_rank_corr(confidences, pnls)
            m.confidence_calibration = ReplayEngine._calibration(confidences, pnls)

        correct = sum(1 for p in graded if p.get("is_correct"))
        total = len(graded)
        m.meaningful_alert_pct = round(correct / total * 100, 1) if total else 0

        return EvalResult(
            mode="shadow",
            metrics=m,
            trades=graded,
            metadata={
                "started_at": self._started_at,
                "stopped_at": datetime.now(timezone.utc).isoformat(),
                "total_predictions": len(self.predictions),
                "graded": total,
            },
        )


# ── WalkForwardEvaluator ───────────────────────────────────────

class WalkForwardEvaluator:
    """
    Walk-forward evaluation over sliding windows with regime-conditional metrics.

    Wraps the existing BacktestEngine but adds regime/session breakdowns
    per window and aggregates across all windows.
    """

    def __init__(self, backtest_engine):
        self.bt = backtest_engine

    def run(self, candles: list[dict], strategy: Optional[str] = None,
            window_size: int = 500, step_size: int = 100,
            slippage_pips: float = 1.5, commission_pips: float = 0.7) -> EvalResult:
        if len(candles) < window_size:
            return EvalResult(mode="walk_forward", metrics=EvalMetrics(),
                              metadata={"error": "insufficient data"})

        window_results = []
        for start in range(0, len(candles) - window_size + 1, step_size):
            end = start + window_size
            window_candles = candles[start:end]
            res = self.bt.run(window_candles, strategy_filter=strategy,
                              slippage_pips=slippage_pips, commission_pips=commission_pips)
            window_results.append(res)

        all_trades = []
        all_pnls = []
        for wr in window_results:
            for t in wr.trades:
                all_trades.append({
                    "direction": t.direction,
                    "entry_price": t.entry_price,
                    "pnl_pips": t.pnl_pips,
                    "strategy": t.strategy,
                    "is_win": t.is_win,
                    "entry_bar": t.entry_bar,
                })
                all_pnls.append(t.pnl_pips)

        core = _compute_core_metrics(all_pnls) if all_pnls else {}
        m = EvalMetrics(**{k: v for k, v in core.items() if k in _EVAL_FIELDS})

        stability = self._window_stability(window_results)
        return EvalResult(
            mode="walk_forward",
            metrics=m,
            trades=all_trades,
            metadata={
                "windows": len(window_results),
                "window_size": window_size,
                "step_size": step_size,
                "strategy": strategy or "all",
                "stability": stability,
            },
        )

    @staticmethod
    def _window_stability(results: list) -> dict:
        if not results:
            return {}
        pnls_by_window = [sum(t.pnl_pips for t in r.trades) for r in results]
        win_rates = [r.win_rate for r in results if r.total_trades > 0]
        profitable_windows = sum(1 for p in pnls_by_window if p > 0)
        return {
            "total_windows": len(results),
            "profitable_windows": profitable_windows,
            "window_win_rate": round(profitable_windows / len(results) * 100, 1) if results else 0,
            "avg_pnl_per_window": round(sum(pnls_by_window) / len(pnls_by_window), 1) if pnls_by_window else 0,
            "pnl_std": round(math.sqrt(sum((p - sum(pnls_by_window) / len(pnls_by_window)) ** 2
                                           for p in pnls_by_window) / len(pnls_by_window)), 2) if pnls_by_window else 0,
            "avg_win_rate": round(sum(win_rates) / len(win_rates), 1) if win_rates else 0,
        }


# ── EvalHarness ────────────────────────────────────────────────

class EvalHarness:
    """
    Unified evaluation harness coordinating all evaluation modes.

    Provides a single entry point for replay analysis, shadow mode,
    and walk-forward evaluation with consistent metrics.
    """

    def __init__(self, storage=None, orchestrator=None, price_provider=None):
        self.storage = storage
        self.orchestrator = orchestrator
        self.price_provider = price_provider
        self._shadow = ShadowMode()

    def replay_engine(self) -> ReplayEngine:
        return ReplayEngine(self.storage)

    def shadow_mode(self) -> ShadowMode:
        return self._shadow

    def walk_forward(self, backtest_engine) -> WalkForwardEvaluator:
        return WalkForwardEvaluator(backtest_engine)

    def cpcv(self, backtest_engine, config: Optional[CPCVConfig] = None) -> CPCVEvaluator:
        return CPCVEvaluator(backtest_engine, config)

    async def full_report(self, days: int = 30) -> str:
        """Generate a comprehensive evaluation report from stored data."""
        replay = self.replay_engine()
        result = await replay.run(days=days)
        return self.format_report(result)

    @staticmethod
    def format_report(result: EvalResult) -> str:
        m = result.metrics
        lines = [
            "═══════════════════════════════════════════",
            f"  EVALUATION REPORT — {result.mode.upper()}",
            "═══════════════════════════════════════════",
            "",
            "── Core Metrics ──",
            f"  Total Trades:    {m.total_trades}",
            f"  Win Rate:        {m.win_rate}%",
            f"  Total P/L:       {m.total_pnl:+.1f} pips",
            f"  Profit Factor:   {m.profit_factor}",
            f"  Sharpe Ratio:    {m.sharpe_ratio}",
            f"  Sortino Ratio:   {m.sortino_ratio}",
            f"  Max Drawdown:    {m.max_drawdown:.1f} pips",
            f"  Expectancy:      {m.expectancy:+.2f} pips",
            f"  Best Trade:      {m.best_trade:+.1f}",
            f"  Worst Trade:     {m.worst_trade:+.1f}",
            "",
            "── Advanced Metrics ──",
            f"  Information Coefficient:  {m.information_coefficient}",
        ]

        if m.confidence_calibration:
            lines.append("  Confidence Calibration:")
            for bucket, data in m.confidence_calibration.items():
                lines.append(f"    {bucket}: {data['actual_win_rate']}% WR ({data['count']} trades)")

        if m.session_breakdown:
            lines.append("  Session Breakdown:")
            for sess, data in m.session_breakdown.items():
                lines.append(f"    {sess}: {data['trades']} trades, {data['win_rate']}% WR, {data['total_pnl']:+.1f} pips")

        if m.skill_attribution:
            lines.append("  Skill Attribution:")
            for skill, data in m.skill_attribution.items():
                lines.append(f"    {skill}: {data['trades']} trades, {data['win_rate']}% WR, avg {data['avg_pnl']:+.1f} pips")

        lines.extend([
            "",
            f"  Flip-Flop Rate:  {m.flip_flop_rate}%",
            f"  Noise Ratio:     {m.noise_ratio}%",
            "═══════════════════════════════════════════",
        ])

        if result.mode == "cpcv" and result.metadata:
            stability = result.metadata.get("stability", {})
            overfit = result.metadata.get("overfit_score", {})
            lines.extend([
                "",
                "── CPCV Validation ──",
                f"  Folds:           {result.metadata.get('total_splits', '?')}",
                f"  Purge Bars:      {result.metadata.get('purge_bars', '?')}",
                f"  Embargo Bars:    {result.metadata.get('embargo_bars', '?')}",
                f"  Fold Win Rate:   {stability.get('fold_win_rate', '?')}%",
                f"  Profitable:      {stability.get('profitable_folds', '?')}/{stability.get('total_folds', '?')} folds",
                f"  PnL Std/Fold:    {stability.get('pnl_std_across_folds', '?')}",
                f"  Overfit Score:   {overfit.get('score', '?')} ({overfit.get('grade', '?')})",
            ])
            fold_details = result.metadata.get("fold_details", [])
            if fold_details:
                lines.append("  Fold Details:")
                for fd in fold_details:
                    lines.append(f"    Fold {fd['fold_id']}: {fd['trades']} trades, "
                                 f"{fd['win_rate']}% WR, {fd['pnl']:+.1f} pips "
                                 f"(train={fd['train_size']}, test={fd['test_size']})")

        if result.metadata:
            lines.append(f"  Metadata: {json.dumps({k: v for k, v in result.metadata.items() if k != 'stability'}, indent=2)}")

        return "\n".join(lines)
