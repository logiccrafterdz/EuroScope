"""
Evaluation Harness — Unified System Assessment Framework.

Provides ReplayEngine (stored signal analysis), ShadowMode (live observation),
WalkForwardEvaluator (rolling window testing), CPCVEvaluator (combinatorial
purged cross-validation), and advanced metrics (confidence calibration,
regime breakdown, Information Coefficient).
"""

from .harness_core import (
    EvalMetrics,
    EvalResult,
    ReplayEngine,
    ShadowMode,
    WalkForwardEvaluator,
    CPCVEvaluator,
    CPCVConfig,
    CPCVFoldResult,
    EvalHarness,
)
from .llm_judge import (
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
)

__all__ = [
    "EvalMetrics",
    "EvalResult",
    "ReplayEngine",
    "ShadowMode",
    "WalkForwardEvaluator",
    "CPCVEvaluator",
    "CPCVConfig",
    "CPCVFoldResult",
    "EvalHarness",
    "GradeResult",
    "EvalSuiteResult",
    "grade_direction",
    "grade_confidence",
    "grade_forecast",
    "compute_pass_at_k",
    "compute_pass_pow_k",
    "run_evaluation_suite",
    "format_grade_report",
    "load_golden_dataset",
]
