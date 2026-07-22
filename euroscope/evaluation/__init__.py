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
]
