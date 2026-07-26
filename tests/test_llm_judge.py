"""Tests for LLM-as-Judge evaluation module."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from euroscope.evaluation.llm_judge import (
    GradeResult,
    EvalSuiteResult,
    grade_direction,
    grade_confidence,
    grade_forecast,
    compute_pass_at_k,
    compute_pass_pow_k,
    run_evaluation_suite,
    format_grade_report,
    load_golden_dataset,
    GOLDEN_DATASET_PATH,
)


@pytest.fixture
def golden_dataset():
    return load_golden_dataset()


@pytest.fixture
def sample_scenario():
    return {
        "id": "trend_01",
        "name": "Strong Uptrend",
        "description": "EUR/USD in strong uptrend with bullish indicators",
        "category": "trend",
        "context": {
            "current_price": 1.0950,
            "regime": "TRENDING",
            "session": "london",
            "indicators": {
                "RSI": {"value": 68, "zone": "upper"},
                "MACD": {"histogram": "positive_expanding"},
                "SMA_50": 1.0900,
                "SMA_200": 1.0850,
            },
            "recent_events": [],
            "candles": [],
        },
        "expected": {
            "direction": "BUY",
            "confidence_range": [0.6, 0.85],
            "reasoning_keywords": ["trend", "momentum", "moving average", "bullish"],
        },
    }


class TestGradeDirection:
    def test_correct_direction(self):
        assert grade_direction("BUY", "BUY") == (True, 1.0)
        assert grade_direction("SELL", "SELL") == (True, 1.0)
        assert grade_direction("HOLD", "HOLD") == (True, 1.0)

    def test_wrong_direction(self):
        assert grade_direction("BUY", "SELL") == (False, 0.0)
        assert grade_direction("SELL", "BUY") == (False, 0.0)

    def test_case_insensitive(self):
        assert grade_direction("buy", "BUY") == (True, 1.0)
        assert grade_direction("Sell", "SELL") == (True, 1.0)

    def test_whitespace_tolerance(self):
        assert grade_direction("  BUY  ", "BUY") == (True, 1.0)


class TestGradeConfidence:
    def test_within_range(self):
        assert grade_confidence(0.7, (0.6, 0.85)) == (True, 1.0)
        assert grade_confidence(0.6, (0.6, 0.85)) == (True, 1.0)
        assert grade_confidence(0.85, (0.6, 0.85)) == (True, 1.0)

    def test_outside_range(self):
        in_range, score = grade_confidence(0.5, (0.6, 0.85))
        assert in_range is False
        assert 0.0 <= score <= 1.0

    def test_far_outside(self):
        in_range, score = grade_confidence(0.2, (0.6, 0.85))
        assert in_range is False
        assert score == 0.0

    def test_boundary(self):
        in_range, score = grade_confidence(0.59, (0.6, 0.85))
        assert in_range is False
        assert 0.0 < score < 1.0  # very close to range, partial credit


class TestGradeForecast:
    def test_perfect_forecast(self, sample_scenario):
        grade = grade_forecast("BUY", 0.7, sample_scenario)
        assert grade.direction_correct is True
        assert grade.confidence_in_range is True
        assert grade.overall_score >= 0.8

    def test_wrong_direction(self, sample_scenario):
        grade = grade_forecast("SELL", 0.7, sample_scenario)
        assert grade.direction_correct is False
        assert grade.overall_score < 0.5

    def test_correct_direction_bad_confidence(self, sample_scenario):
        grade = grade_forecast("BUY", 0.3, sample_scenario)
        assert grade.direction_correct is True
        assert grade.confidence_in_range is False

    def test_grade_result_fields(self, sample_scenario):
        grade = grade_forecast("BUY", 0.7, sample_scenario)
        assert grade.scenario_id == "trend_01"
        assert grade.scenario_name == "Strong Uptrend"
        assert isinstance(grade.notes, str)


class TestPassAtK:
    def test_single_correct(self):
        grades = [GradeResult("s1", "Test", True, True, 1.0, 1.0, 1.0, 1.0)]
        assert compute_pass_at_k(grades, 1) == 1.0

    def test_single_wrong(self):
        grades = [GradeResult("s1", "Test", False, False, 0.0, 0.0, 0.0, 0.0)]
        assert compute_pass_at_k(grades, 1) == 0.0

    def test_multiple_scenarios_mixed(self):
        grades = [
            GradeResult("s1", "A", True, True, 1.0, 1.0, 1.0, 1.0),
            GradeResult("s2", "B", False, False, 0.0, 0.0, 0.0, 0.0),
        ]
        assert compute_pass_at_k(grades, 1) == 0.5

    def test_pass_at_k_3(self):
        grades = [
            GradeResult("s1", "A", False, False, 0.0, 0.0, 0.0, 0.0),
            GradeResult("s1", "A", False, False, 0.0, 0.0, 0.0, 0.0),
            GradeResult("s1", "A", True, True, 1.0, 1.0, 1.0, 1.0),
        ]
        assert compute_pass_at_k(grades, 3) == 1.0

    def test_empty(self):
        assert compute_pass_at_k([], 1) == 0.0


class TestPassPowK:
    def test_all_correct(self):
        grades = [
            GradeResult("s1", "A", True, True, 1.0, 1.0, 1.0, 1.0),
            GradeResult("s1", "A", True, True, 1.0, 1.0, 1.0, 1.0),
        ]
        assert compute_pass_pow_k(grades, 2) == 1.0

    def test_one_wrong(self):
        grades = [
            GradeResult("s1", "A", True, True, 1.0, 1.0, 1.0, 1.0),
            GradeResult("s1", "A", False, False, 0.0, 0.0, 0.0, 0.0),
        ]
        assert compute_pass_pow_k(grades, 2) == 0.0


class TestRunEvaluationSuite:
    def test_full_run(self, golden_dataset):
        if not golden_dataset:
            pytest.skip("No golden dataset available")

        forecasts = []
        for scenario in golden_dataset[:5]:
            forecasts.append({
                "scenario_id": scenario["id"],
                "direction": scenario["expected"]["direction"],
                "confidence": sum(scenario["expected"]["confidence_range"]) / 2,
            })

        result = run_evaluation_suite(forecasts)
        assert isinstance(result, EvalSuiteResult)
        assert result.total_scenarios == len(golden_dataset)
        assert len(result.grades) == len(forecasts)
        assert result.mean_direction_accuracy == 1.0  # all correct by design

    def test_empty_forecasts(self):
        result = run_evaluation_suite([])
        assert len(result.grades) == 0

    def test_unknown_scenario(self):
        forecasts = [{"scenario_id": "nonexistent", "direction": "BUY", "confidence": 0.7}]
        result = run_evaluation_suite(forecasts)
        assert len(result.grades) == 0


class TestFormatReport:
    def test_format(self, golden_dataset):
        if not golden_dataset:
            pytest.skip("No golden dataset")

        forecasts = [{
            "scenario_id": golden_dataset[0]["id"],
            "direction": golden_dataset[0]["expected"]["direction"],
            "confidence": 0.7,
        }]
        result = run_evaluation_suite(forecasts)
        report = format_grade_report(result)
        assert "EVALUATION REPORT" in report
        assert golden_dataset[0]["id"] in report


class TestGoldenDataset:
    def test_load(self, golden_dataset):
        assert len(golden_dataset) == 25

    def test_schema(self, golden_dataset):
        for scenario in golden_dataset:
            assert "id" in scenario
            assert "name" in scenario
            assert "description" in scenario
            assert "context" in scenario
            assert "expected" in scenario
            assert "direction" in scenario["expected"]
            assert "confidence_range" in scenario["expected"]
            assert len(scenario["expected"]["confidence_range"]) == 2

    def test_regimes(self, golden_dataset):
        regimes = {s["context"]["regime"] for s in golden_dataset}
        assert "trending" in regimes
        assert "ranging" in regimes
