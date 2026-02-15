from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import importlib.util
import pandas as pd

from euroscope.automation.alerts import SmartAlerts
from euroscope.automation.events import (
    AlertSuppressionSubscriber,
    EventBus,
    SignalExecutorSubscriber,
)
from euroscope.brain.orchestrator import Orchestrator
from euroscope.data.storage import Storage
from euroscope.skills.base import SkillContext
from euroscope.skills.deviation_monitor import skill as deviation_module
from euroscope.skills.deviation_monitor.skill import DeviationMonitorSkill
from euroscope.skills.risk_management.skill import RiskManagementSkill
from euroscope.skills.session_context import skill as session_module
from euroscope.skills.signal_executor.skill import SignalExecutorSkill


@dataclass
class ExpectedBehavior:
    component: str
    metric: str
    operator: str
    threshold: Any
    tolerance: float = 0.0


@dataclass
class BehavioralScenario:
    name: str
    start_time: datetime
    end_time: datetime
    data: pd.DataFrame
    expected_behaviors: list[ExpectedBehavior]
    interval: str = "1h"
    event_start: datetime | None = None
    event_end: datetime | None = None
    context_overrides: dict = field(default_factory=dict)
    forced_risk_checks: list[dict] = field(default_factory=list)


@dataclass
class BehaviorCheckResult:
    component: str
    metric: str
    expected: Any
    actual: Any
    passed: bool


@dataclass
class ScenarioResult:
    name: str
    checks: list[BehaviorCheckResult]
    metrics: dict
    snapshots: list[dict]
    error: str | None = None


class InMemoryPriceProvider:
    def __init__(self, df: pd.DataFrame, timeframe: str):
        self.df = df
        self.timeframe = timeframe
        self._index = 0

    def set_index(self, idx: int):
        self._index = idx

    async def get_candles(self, timeframe: str = "H1", count: int = 100):
        end = self._index + 1
        start = max(0, end - count)
        return self.df.iloc[start:end].copy()

    async def get_price(self):
        row = self.df.iloc[self._index]
        return {"price": float(row["Close"])}

    def get_buffer(self):
        end = self._index + 1
        return {
            "candles": self.df.iloc[:end].copy(),
            "timeframe": self.timeframe,
        }


class FrozenTime:
    def __init__(self, current_time: datetime):
        self.current_time = current_time
        self._session_datetime = None
        self._deviation_datetime = None

    def __enter__(self):
        class FrozenDateTime:
            @classmethod
            def utcnow(cls):
                return self.current_time

        self._session_datetime = session_module.datetime
        self._deviation_datetime = deviation_module.datetime
        session_module.datetime = FrozenDateTime
        deviation_module.datetime = FrozenDateTime

    def __exit__(self, exc_type, exc, tb):
        if self._session_datetime:
            session_module.datetime = self._session_datetime
        if self._deviation_datetime:
            deviation_module.datetime = self._deviation_datetime


class BehavioralValidator:
    def __init__(
        self,
        cache_dir: str | Path = "tests/data/behavioral_scenarios",
        lookahead_bars: int = 6,
        profit_pips: float = 6.0,
        loss_pips: float = 6.0,
    ):
        self.cache_dir = Path(cache_dir)
        self.lookahead_bars = lookahead_bars
        self.profit_pips = profit_pips
        self.loss_pips = loss_pips

    def load_yfinance_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
        cache_key: str,
    ) -> pd.DataFrame:
        if importlib.util.find_spec("yfinance") is None:
            raise RuntimeError("yfinance is required for behavioral validation")
        import yfinance as yf

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / f"{cache_key}_{interval}.csv"
        
        # Only load from cache if file is not empty/corrupted
        if cache_path.exists() and cache_path.stat().st_size > 100:
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            if not df.empty:
                return self._normalize_df(df)
            else:
                # Remove empty/invalid cache file
                cache_path.unlink()

        try:
            df = yf.download(
                symbol,
                start=start,
                end=end,
                interval=interval,
                progress=False,
                auto_adjust=False,
            )
            df = self._normalize_df(df)
        except Exception:
            df = pd.DataFrame()

        if df.empty:
            df = self._generate_synthetic_data(start, end, interval, cache_key)
        else:
            # Only cache if we actually got data from yfinance
            df.to_csv(cache_path)
            
        return df

    async def run_scenario(self, scenario: BehavioralScenario) -> ScenarioResult:
        df = self._normalize_df(scenario.data)
        df = df[(df.index >= scenario.start_time) & (df.index <= scenario.end_time)]
        if df.empty:
            metrics = {
                "signal_rejection_rate": 0.0,
                "false_positive_rate": 0.0,
                "false_negative_rate": 0.0,
                "emergency_response_time": None,
                "emergency_mode_triggered": False,
                "composite_uncertainty_ratio": 0.0,
                "neutral_signal_ratio": 0.0,
                "behavioral_rejection_ratio": 0.0,
                "liquidity_sweep_detected": False,
                "behavioral_uncertainty_peak": 0.0,
                "session_transition_detected": False,
                "stop_buffer_asian": None,
                "stop_buffer_london": None,
                "macro_confidence_adjustment": 0.0,
                "position_size_multiplier": None,
                "alerts_suppressed_until": 0.0,
                "data_source": "empty",
            }
            checks = self._evaluate_checks(scenario, metrics)
            return ScenarioResult(
                name=scenario.name,
                checks=checks,
                metrics=metrics,
                snapshots=[],
                error="No data available for scenario window",
            )
        provider = InMemoryPriceProvider(df, scenario.interval)

        orchestrator = Orchestrator()
        market_skill = orchestrator.registry.get("market_data")
        if market_skill:
            market_skill.set_price_provider(provider)

        session_skill = orchestrator.registry.get("session_context")
        risk_skill = RiskManagementSkill()
        signal_executor = SignalExecutorSkill()
        storage = Storage(":memory:")
        alerts = SmartAlerts()
        orchestrator.alerts = alerts

        bus = EventBus()
        bus.subscribe("market.regime_shift", SignalExecutorSubscriber(signal_executor).handle)
        bus.subscribe("market.regime_shift", AlertSuppressionSubscriber(alerts).handle)

        deviation_monitor = DeviationMonitorSkill(
            event_bus=bus,
            market_data_skill=provider,
            storage=storage,
            global_context=orchestrator.global_context,
        )

        context = orchestrator.global_context
        context.analysis.update(scenario.context_overrides.get("analysis", {}))
        context.metadata.update(scenario.context_overrides.get("metadata", {}))

        snapshots = []
        signal_records = []

        for idx, (timestamp, row) in enumerate(df.iterrows()):
            provider.set_index(idx)
            if session_skill:
                session_skill._cache_timestamp = 0.0
            with FrozenTime(timestamp):
                await deviation_monitor._check_once()
                await orchestrator.run_full_analysis_pipeline(context=context)

                signal = context.signals or {}
                direction = signal.get("direction")
                if direction in ("BUY", "SELL"):
                    await risk_skill.execute(
                        context,
                        "assess_trade",
                        direction=direction,
                        entry_price=float(row["Close"]),
                    )

                execution = None
                if direction in ("BUY", "SELL"):
                    execution = await signal_executor.safe_execute(context, "open_trade")
                    if execution.success:
                        trade_id = execution.data.get("trade_id")
                        await signal_executor.execute(context, "close_trade", trade_id=trade_id, exit_price=float(row["Close"]))

                snapshots.append(
                    {
                        "timestamp": timestamp,
                        "metadata": dict(context.metadata),
                        "signals": dict(signal) if signal else {},
                        "risk": dict(context.risk) if context.risk else {},
                        "execution": {
                            "success": execution.success,
                            "error": execution.error,
                        } if execution else None,
                    }
                )

                if direction in ("BUY", "SELL"):
                    future = df.iloc[idx + 1 : idx + 1 + self.lookahead_bars]
                    profitable = self._is_profitable(direction, float(row["Close"]), future)
                    signal_records.append(
                        {
                            "timestamp": timestamp,
                            "direction": direction,
                            "blocked": execution is not None and not execution.success,
                            "blocked_reason": execution.error if execution else None,
                            "profitable": profitable,
                            "price": float(row["Close"]),
                        }
                    )

        self._inject_forced_risk_checks(scenario, snapshots, risk_skill, context, df)

        metrics = self._compute_metrics(
            scenario=scenario,
            snapshots=snapshots,
            signal_records=signal_records,
            alerts=alerts,
        )
        checks = self._evaluate_checks(scenario, metrics)
        return ScenarioResult(name=scenario.name, checks=checks, metrics=metrics, snapshots=snapshots)

    async def run_suite(self, scenarios: list[BehavioralScenario]) -> list[ScenarioResult]:
        results = []
        for scenario in scenarios:
            results.append(await self.run_scenario(scenario))
        return results

    def load_default_scenarios(self) -> list[BehavioralScenario]:
        from euroscope.testing import scenarios as scenario_module

        builders = [
            scenario_module.sideways_july2023,
            scenario_module.lagarde_shock_june2023,
            scenario_module.liquidity_sweep_march2024,
            scenario_module.session_transition_april2024,
            scenario_module.macro_override_sept2023,
        ]
        return [builder(self) for builder in builders]

    def render_report(
        self,
        results: list[ScenarioResult],
        template_path: str | Path | None = None,
    ) -> str:
        summary = self._build_summary(results)
        scenario_table = self._build_scenario_table(results)
        component_analysis = self._build_component_analysis(results)
        overrides = self._build_overrides(results)
        recommendations = self._build_recommendations(results)

        template = self._load_template(template_path)
        return (
            template.replace("{{SUMMARY}}", summary)
            .replace("{{SCENARIO_TABLE}}", scenario_table)
            .replace("{{COMPONENT_ANALYSIS}}", component_analysis)
            .replace("{{BEHAVIORAL_OVERRIDES}}", overrides)
            .replace("{{IMPROVEMENT_RECOMMENDATIONS}}", recommendations)
        )

    def _compute_metrics(self, scenario, snapshots, signal_records, alerts):
        total_signals = len(signal_records)
        blocked_signals = [s for s in signal_records if s["blocked"]]
        allowed_signals = [s for s in signal_records if not s["blocked"]]
        blocked_profitable = [s for s in blocked_signals if s["profitable"]]
        allowed_unprofitable = [s for s in allowed_signals if not s["profitable"]]

        rejection_rate = (len(blocked_signals) / total_signals) if total_signals else 0.0
        false_positive = (len(blocked_profitable) / len(blocked_signals)) if blocked_signals else 0.0
        false_negative = (len(allowed_unprofitable) / len(allowed_signals)) if allowed_signals else 0.0

        uncertainty_scores = [s["metadata"].get("uncertainty_score") for s in snapshots]
        uncertainty_scores = [u for u in uncertainty_scores if isinstance(u, (int, float))]
        composite_uncertainty_ratio = (
            sum(1 for u in uncertainty_scores if u > 0.65) / len(uncertainty_scores)
            if uncertainty_scores else 0.0
        )

        neutral_ratio = (
            sum(1 for s in snapshots if (s["signals"].get("direction") in (None, "WAIT"))) / len(snapshots)
            if snapshots else 0.0
        )

        behavioral_rejections = [
            s for s in signal_records if s["blocked_reason"] == "UNCERTAINTY: confidence too low"
        ]
        behavioral_rejection_ratio = (
            len(behavioral_rejections) / total_signals if total_signals else 0.0
        )

        emergency_times = [
            s["timestamp"] for s in snapshots if s["metadata"].get("emergency_mode") is True
        ]
        response_time = None
        emergency_mode_triggered = bool(emergency_times)
        if scenario.event_start and emergency_times:
            response_time = (min(emergency_times) - scenario.event_start).total_seconds()

        liquidity_sweep_detected = any(
            (s["metadata"].get("market_intent") or {}).get("current_phase") == "liquidity_sweep"
            for s in snapshots
        )
        behavioral_peak = max(
            [s["metadata"].get("behavioral_uncertainty", 0.0) for s in snapshots] or [0.0]
        )

        session_transition_detected = any(
            s["timestamp"].hour == 7 and s["timestamp"].minute == 0
            and s["metadata"].get("session_regime") == "london"
            for s in snapshots
        )

        stop_buffer_asian = None
        stop_buffer_london = None
        for check in scenario.forced_risk_checks:
            ts = check.get("timestamp")
            if ts is None:
                continue
            entry = check.get("entry_price", 0.0)
            session = check.get("session")
            if session == "asian":
                stop_buffer_asian = check.get("stop_buffer_pips")
            if session == "london":
                stop_buffer_london = check.get("stop_buffer_pips")

        macro_confidence_adjustment = max(
            [s["metadata"].get("confidence_adjustment", 0.0) for s in snapshots] or [0.0]
        )
        position_size_multiplier = None
        for s in snapshots:
            risk = s.get("risk", {})
            if risk:
                adjusted_pct = s["metadata"].get("risk_assessment", {}).get("adjusted_position_size_pct")
                if adjusted_pct is not None:
                    position_size_multiplier = adjusted_pct
                    break

        return {
            "signal_rejection_rate": rejection_rate,
            "false_positive_rate": false_positive,
            "false_negative_rate": false_negative,
            "emergency_response_time": response_time,
            "emergency_mode_triggered": emergency_mode_triggered,
            "composite_uncertainty_ratio": composite_uncertainty_ratio,
            "neutral_signal_ratio": neutral_ratio,
            "behavioral_rejection_ratio": behavioral_rejection_ratio,
            "liquidity_sweep_detected": liquidity_sweep_detected,
            "behavioral_uncertainty_peak": behavioral_peak,
            "session_transition_detected": session_transition_detected,
            "stop_buffer_asian": stop_buffer_asian,
            "stop_buffer_london": stop_buffer_london,
            "macro_confidence_adjustment": macro_confidence_adjustment,
            "position_size_multiplier": position_size_multiplier,
            "alerts_suppressed_until": alerts._suppress_until,
        }

    def _evaluate_checks(self, scenario: BehavioralScenario, metrics: dict) -> list[BehaviorCheckResult]:
        checks = []
        for expected in scenario.expected_behaviors:
            actual = metrics.get(expected.metric)
            passed = self._compare(actual, expected.operator, expected.threshold, expected.tolerance)
            checks.append(
                BehaviorCheckResult(
                    component=expected.component,
                    metric=expected.metric,
                    expected=expected.threshold,
                    actual=actual,
                    passed=passed,
                )
            )
        return checks

    def _compare(self, actual, operator: str, threshold, tolerance: float):
        if operator == "==":
            return actual == threshold
        if operator == ">":
            return actual is not None and actual > threshold - tolerance
        if operator == "<":
            return actual is not None and actual < threshold + tolerance
        if operator == ">=":
            return actual is not None and actual >= threshold - tolerance
        if operator == "<=":
            return actual is not None and actual <= threshold + tolerance
        if operator == "contains":
            return threshold in (actual or [])
        if operator == "truthy":
            return bool(actual)
        return False

    def _is_profitable(self, direction: str, entry_price: float, future: pd.DataFrame) -> bool:
        if future is None or future.empty:
            return False
        high = float(future["High"].max())
        low = float(future["Low"].min())
        profit = self.profit_pips * 0.0001
        loss = self.loss_pips * 0.0001
        if direction == "BUY":
            if high - entry_price >= profit:
                return True
            if entry_price - low >= loss:
                return False
        if direction == "SELL":
            if entry_price - low >= profit:
                return True
            if high - entry_price >= loss:
                return False
        return False

    def _inject_forced_risk_checks(
        self,
        scenario: BehavioralScenario,
        snapshots: list[dict],
        risk_skill: RiskManagementSkill,
        context: SkillContext,
        df: pd.DataFrame,
    ):
        if scenario.forced_risk_checks:
            return
        if "Session Transition" not in scenario.name:
            return
        if df.empty:
            return
        checkpoints = [
            {"timestamp": datetime(scenario.start_time.year, scenario.start_time.month, scenario.start_time.day, 6, 50), "session": "asian"},
            {"timestamp": datetime(scenario.start_time.year, scenario.start_time.month, scenario.start_time.day, 7, 5), "session": "london"},
        ]
        for checkpoint in checkpoints:
            ts = checkpoint["timestamp"]
            if ts not in df.index:
                idx = df.index.get_indexer([ts], method="nearest")
                if len(idx) == 0 or idx[0] == -1:
                    continue
                ts = df.index[idx[0]]
            row = df.loc[ts]
            matching = next((s for s in snapshots if s["timestamp"] == ts), None)
            if matching:
                context.metadata.update(matching["metadata"])
            context.metadata["session_regime"] = checkpoint["session"]
            stop_buffer = risk_skill._calculate_adaptive_stop(
                direction="BUY",
                entry_price=float(row["Close"]),
                atr=None,
                liquidity_zones=[],
                session_regime=checkpoint["session"],
            )
            scenario.forced_risk_checks.append(
                {
                    "timestamp": ts,
                    "session": checkpoint["session"],
                    "stop_buffer_pips": stop_buffer["buffer_pips"],
                }
            )

    def _build_summary(self, results: list[ScenarioResult]) -> str:
        total = len(results)
        all_checks = [check for r in results for check in r.checks]
        passed = [c for c in all_checks if c.passed]
        failed = [c for c in all_checks if not c.passed]
        pass_rate = (len(passed) / len(all_checks) * 100) if all_checks else 0.0
        lines = [
            f"Scenarios: {total}",
            f"Checks: {len(all_checks)}",
            f"Passed: {len(passed)}",
            f"Failed: {len(failed)}",
            f"Pass rate: {pass_rate:.1f}%",
        ]
        if failed:
            failed_labels = ", ".join({f"{c.component}:{c.metric}" for c in failed})
            lines.append(f"Failed checks: {failed_labels}")
        errors = [r for r in results if r.error]
        if errors:
            lines.append(f"Scenario errors: {len(errors)}")
        return "\n".join(lines)

    def _build_scenario_table(self, results: list[ScenarioResult]) -> str:
        lines = ["| Scenario | Pass Rate | Failed Checks |", "| --- | --- | --- |"]
        for result in results:
            total = len(result.checks)
            failed = [c for c in result.checks if not c.passed]
            pass_rate = (total - len(failed)) / total * 100 if total else 0.0
            failed_labels = ", ".join({f"{c.component}:{c.metric}" for c in failed}) or "None"
            if result.error:
                failed_labels = f"{failed_labels} (error: {result.error})"
            lines.append(f"| {result.name} | {pass_rate:.1f}% | {failed_labels} |")
        return "\n".join(lines)

    def _build_component_analysis(self, results: list[ScenarioResult]) -> str:
        failures = {}
        for result in results:
            for check in result.checks:
                if check.passed:
                    continue
                failures.setdefault(check.component, []).append(check.metric)
        if not failures:
            return "All components met expectations."
        lines = []
        for component, metrics in failures.items():
            uniq = ", ".join(sorted(set(metrics)))
            lines.append(f"- {component}: {uniq}")
        return "\n".join(lines)

    def _build_overrides(self, results: list[ScenarioResult]) -> str:
        lines = []
        for result in results:
            metrics = result.metrics
            if metrics.get("emergency_mode_triggered"):
                lines.append(f"- {result.name}: emergency mode triggered")
            if metrics.get("behavioral_rejection_ratio", 0) > 0:
                lines.append(f"- {result.name}: behavioral rejections {metrics.get('behavioral_rejection_ratio'):.2f}")
            if metrics.get("macro_confidence_adjustment", 0) > 0:
                lines.append(f"- {result.name}: macro confidence adjustment {metrics.get('macro_confidence_adjustment'):.2f}")
            if metrics.get("session_transition_detected"):
                lines.append(f"- {result.name}: session transition detected")
        return "\n".join(lines) if lines else "No overrides observed."

    def _build_recommendations(self, results: list[ScenarioResult]) -> str:
        failed = [c for r in results for c in r.checks if not c.passed]
        if not failed:
            return "No improvements required."
        suggestions = []
        for check in failed:
            suggestions.append(f"- Review {check.component} for {check.metric} threshold mismatches.")
        for result in results:
            if result.error:
                suggestions.append(f"- Resolve data availability for {result.name}.")
        return "\n".join(sorted(set(suggestions)))

    def _generate_synthetic_data(
        self,
        start: datetime,
        end: datetime,
        interval: str,
        cache_key: str,
    ) -> pd.DataFrame:
        freq = "1min" if interval.endswith("m") else "1h" if interval.endswith("h") else "1d"
        index = pd.date_range(start=start, end=end, freq=freq)
        if len(index) == 0:
            return pd.DataFrame()
        seed = abs(hash(cache_key)) % (2**32)
        rng = pd.Series(range(len(index)), index=index)
        base = 1.08 + (seed % 1000) * 0.000001
        drift = (rng * 0.000001).astype(float)
        close = base + drift + (seed % 7) * 0.00001
        open_prices = close.shift(1).fillna(close)
        high = close + 0.0003
        low = close - 0.0003
        volume = pd.Series(10000.0, index=index)
        df = pd.DataFrame(
            {
                "Open": open_prices.values,
                "High": high.values,
                "Low": low.values,
                "Close": close.values,
                "Volume": volume.values,
            },
            index=index,
        )
        return self._normalize_df(df)

    def _load_template(self, template_path: str | Path | None) -> str:
        if template_path is None:
            template_path = Path(__file__).parent / "report_templates" / "behavioral_report.md.j2"
        path = Path(template_path)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return (
            "# Behavioral Validation Report\n\n"
            "## Summary\n{{SUMMARY}}\n\n"
            "## Scenario Analysis\n{{SCENARIO_TABLE}}\n\n"
            "## Component Contribution Analysis\n{{COMPONENT_ANALYSIS}}\n\n"
            "## Behavioral Corrections & Overrides Observed\n{{BEHAVIORAL_OVERRIDES}}\n\n"
            "## Improvement Recommendations\n{{IMPROVEMENT_RECOMMENDATIONS}}\n"
        )

    @staticmethod
    def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        cols = {c: c.title() for c in df.columns}
        df = df.rename(columns=cols)
        needed = {"Open", "High", "Low", "Close", "Volume"}
        for col in needed:
            if col not in df.columns:
                df[col] = 0.0
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)
        return df
