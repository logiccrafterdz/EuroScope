"""
LLM-as-Judge Evaluation Module

Grades system forecasts against a golden dataset of known-good scenarios.
Computes pass@k (did at least 1 of k attempts get it right?)
and pass^k (did ALL k attempts get it right?) metrics.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("euroscope.evaluation.llm_judge")

GOLDEN_DATASET_PATH = Path(__file__).parent / "golden_dataset.json"


@dataclass
class GradeResult:
    """Result of grading a single forecast against a golden scenario."""
    scenario_id: str
    scenario_name: str
    direction_correct: bool
    confidence_in_range: bool
    direction_score: float  # 0.0 or 1.0
    confidence_score: float  # 0.0 to 1.0 (closeness to expected range)
    reasoning_score: float  # 0.0 to 1.0 (LLM-graded quality)
    overall_score: float  # weighted average
    notes: str = ""


@dataclass
class EvalSuiteResult:
    """Aggregated results from running the full evaluation suite."""
    grades: list[GradeResult] = field(default_factory=list)
    pass_at_k: dict[int, float] = field(default_factory=dict)
    pass_pow_k: dict[int, float] = field(default_factory=dict)
    mean_direction_accuracy: float = 0.0
    mean_confidence_score: float = 0.0
    mean_reasoning_score: float = 0.0
    mean_overall_score: float = 0.0
    total_scenarios: int = 0
    summary: str = ""


def load_golden_dataset(path: Optional[Path] = None) -> list[dict]:
    """Load the golden dataset from JSON."""
    p = path or GOLDEN_DATASET_PATH
    if not p.exists():
        logger.warning(f"Golden dataset not found at {p}")
        return []
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def grade_direction(predicted: str, expected: str) -> tuple[bool, float]:
    """Grade direction prediction. Returns (correct, score)."""
    pred = predicted.strip().upper()
    exp = expected.strip().upper()
    if pred == exp:
        return True, 1.0
    # Partial credit: HOLD vs BUY/SELL is 0, wrong direction is 0
    return False, 0.0


def grade_confidence(predicted_conf: float, expected_range: tuple[float, float]) -> tuple[bool, float]:
    """Grade confidence prediction. Returns (in_range, score)."""
    low, high = expected_range
    in_range = low <= predicted_conf <= high
    if in_range:
        return True, 1.0
    # Partial credit: how close to range?
    mid = (low + high) / 2
    span = max(high - low, 0.01)
    distance = max(low - predicted_conf, predicted_conf - high, 0)
    score = max(0.0, 1.0 - distance / span)
    return False, score


def grade_forecast(
    predicted_direction: str,
    predicted_confidence: float,
    scenario: dict,
    llm_router=None,
) -> GradeResult:
    """
    Grade a single forecast against a golden scenario.
    
    If llm_router is provided, uses LLM-as-Judge for reasoning quality.
    Otherwise, uses keyword matching as fallback.
    """
    expected = scenario["expected"]
    exp_dir = expected["direction"]
    exp_range = tuple(expected["confidence_range"])

    dir_correct, dir_score = grade_direction(predicted_direction, exp_dir)
    conf_in_range, conf_score = grade_confidence(predicted_confidence, exp_range)

    # Reasoning quality: keyword matching (fast, no LLM needed)
    reasoning_score = 0.5  # default neutral
    reasoning_keywords = expected.get("reasoning_keywords", [])
    if reasoning_keywords and llm_router:
        reasoning_score = _grade_reasoning_llm(
            predicted_direction, predicted_confidence, scenario, llm_router
        )
    elif reasoning_keywords:
        reasoning_score = _grade_reasoning_keywords(
            predicted_direction, scenario, reasoning_keywords
        )

    # Weighted overall score
    overall = 0.4 * dir_score + 0.3 * conf_score + 0.3 * reasoning_score

    notes = ""
    if not dir_correct:
        notes += f"Wrong direction (expected {exp_dir}). "
    if not conf_in_range:
        notes += f"Confidence {predicted_confidence:.2f} outside range [{exp_range[0]:.2f}, {exp_range[1]:.2f}]. "

    return GradeResult(
        scenario_id=scenario["id"],
        scenario_name=scenario["name"],
        direction_correct=dir_correct,
        confidence_in_range=conf_in_range,
        direction_score=dir_score,
        confidence_score=conf_score,
        reasoning_score=reasoning_score,
        overall_score=overall,
        notes=notes.strip(),
    )


def _grade_reasoning_keywords(
    predicted_direction: str, scenario: dict, keywords: list[str]
) -> float:
    """Grade reasoning quality using keyword matching against expected keywords."""
    if not keywords:
        return 0.5
        
    expected_direction = scenario.get("expected", {}).get("direction", "")
    if predicted_direction.upper() != expected_direction.upper():
        return 0.1

    context = scenario.get("context", {})
    indicators = context.get("indicators", {})
    regime = context.get("regime", "")
    session = context.get("session", "")

    # Build a text representation of the context
    context_text = f"{regime} {session} {json.dumps(indicators)}".lower()

    # Count how many expected keywords appear in the context
    matched = sum(1 for kw in keywords if kw.lower() in context_text)
    return min(1.0, matched / max(len(keywords), 1) * 1.5)  # slight boost


def _grade_reasoning_llm(
    predicted_direction: str,
    predicted_confidence: float,
    scenario: dict,
    llm_router,
) -> float:
    """Grade reasoning quality using LLM-as-Judge."""
    import asyncio

    expected = scenario["expected"]
    context_str = json.dumps(scenario["context"], indent=2, default=str)

    prompt = (
        "You are a trading expert grading an AI system's forecast.\n\n"
        f"Scenario: {scenario['name']}\n"
        f"Description: {scenario['description']}\n\n"
        f"Market Context:\n{context_str}\n\n"
        f"System's Forecast:\n"
        f"- Direction: {predicted_direction}\n"
        f"- Confidence: {predicted_confidence:.2f}\n\n"
        f"Expected Direction: {expected['direction']}\n"
        f"Expected Confidence Range: {expected['confidence_range']}\n"
        f"Key Reasoning Keywords: {expected.get('reasoning_keywords', [])}\n\n"
        "Grade the system's reasoning quality from 0.0 to 1.0:\n"
        "- 1.0: Perfect reasoning — direction correct, confidence well-calibrated, "
        "would make correct decisions based on this analysis\n"
        "- 0.7: Good — direction correct, minor calibration issues\n"
        "- 0.5: Acceptable — direction wrong but reasoning is sound\n"
        "- 0.3: Poor — direction wrong and reasoning is weak\n"
        "- 0.1: Very poor — clearly wrong with bad reasoning\n\n"
        'Return ONLY a number between 0.0 and 1.0 (e.g., "0.75")'
    )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return 0.5  # Can't call async from sync in running loop
        result = loop.run_until_complete(
            llm_router.chat([{"role": "user", "content": prompt}], temperature=0.1)
        )
        import re
        match = re.search(r'(\d+\.?\d*)', str(result))
        if match:
            return max(0.0, min(1.0, float(match.group(1))))
    except Exception as e:
        logger.warning(f"LLM judge failed: {e}")

    return _grade_reasoning_keywords(predicted_direction, scenario, expected.get("reasoning_keywords", []))


def compute_pass_at_k(grades: list[GradeResult], k: int) -> float:
    """
    pass@k: What fraction of scenario groups have at least 1 correct
    forecast out of k attempts?
    
    For single-attempt evaluation (k=1), this is just directional accuracy.
    For multi-attempt, we need multiple forecasts per scenario.
    
    Here we implement a simplified version:
    - Group grades by scenario_id
    - For each scenario, check if at least one grade has direction_correct=True
    - Return the fraction of scenarios where at least one got it right
    """
    if not grades:
        return 0.0

    # Group by scenario
    scenario_groups: dict[str, list[GradeResult]] = {}
    for g in grades:
        scenario_groups.setdefault(g.scenario_id, []).append(g)

    # For k=1 (single attempt), just check each scenario once
    correct_count = 0
    for scenario_id, group in scenario_groups.items():
        # Take first k grades for this scenario
        top_k = group[:k]
        if any(g.direction_correct for g in top_k):
            correct_count += 1

    return correct_count / max(len(scenario_groups), 1)


def compute_pass_pow_k(grades: list[GradeResult], k: int) -> float:
    """
    pass^k: What fraction of scenario groups have ALL k forecasts correct?
    
    Stricter than pass@k — requires every attempt to be correct.
    """
    if not grades:
        return 0.0

    scenario_groups: dict[str, list[GradeResult]] = {}
    for g in grades:
        scenario_groups.setdefault(g.scenario_id, []).append(g)

    all_correct_count = 0
    for scenario_id, group in scenario_groups.items():
        top_k = group[:k]
        if len(top_k) >= k and all(g.direction_correct for g in top_k):
            all_correct_count += 1

    return all_correct_count / max(len(scenario_groups), 1)


def run_evaluation_suite(
    forecasts: list[dict],
    llm_router=None,
    dataset_path: Optional[Path] = None,
) -> EvalSuiteResult:
    """
    Run the full evaluation suite.
    
    Args:
        forecasts: List of dicts with keys:
            - scenario_id: str
            - direction: str ("BUY", "SELL", "HOLD")
            - confidence: float (0.0 to 1.0)
        llm_router: Optional LLM router for LLM-as-Judge reasoning grading
        dataset_path: Optional path to custom golden dataset
    
    Returns:
        EvalSuiteResult with all metrics
    """
    dataset = load_golden_dataset(dataset_path)
    if not dataset:
        return EvalSuiteResult(summary="No golden dataset found.")

    # Index dataset by ID
    scenario_map = {s["id"]: s for s in dataset}

    grades = []
    for forecast in forecasts:
        scenario_id = forecast.get("scenario_id", "")
        scenario = scenario_map.get(scenario_id)
        if not scenario:
            logger.warning(f"Forecast for unknown scenario: {scenario_id}")
            continue

        grade = grade_forecast(
            predicted_direction=forecast.get("direction", "HOLD"),
            predicted_confidence=forecast.get("confidence", 0.0),
            scenario=scenario,
            llm_router=llm_router,
        )
        grades.append(grade)

    # Compute metrics
    result = EvalSuiteResult(grades=grades, total_scenarios=len(dataset))

    if grades:
        result.mean_direction_accuracy = sum(g.direction_score for g in grades) / len(grades)
        result.mean_confidence_score = sum(g.confidence_score for g in grades) / len(grades)
        result.mean_reasoning_score = sum(g.reasoning_score for g in grades) / len(grades)
        result.mean_overall_score = sum(g.overall_score for g in grades) / len(grades)

    # pass@k and pass^k for k=1 (removed k>1 as we only generate 1 forecast per scenario)
    for k in [1]:
        if len(grades) >= k:
            result.pass_at_k[k] = compute_pass_at_k(grades, k)
            result.pass_pow_k[k] = compute_pass_pow_k(grades, k)

    # Summary
    n_correct = sum(1 for g in grades if g.direction_correct)
    n_total = len(grades)
    result.summary = (
        f"Evaluation Suite: {n_total}/{len(dataset)} scenarios graded\n"
        f"Direction Accuracy: {result.mean_direction_accuracy:.1%} ({n_correct}/{n_total})\n"
        f"Confidence Score:   {result.mean_confidence_score:.1%}\n"
        f"Reasoning Score:    {result.mean_reasoning_score:.1%}\n"
        f"Overall Score:      {result.mean_overall_score:.1%}\n"
    )
    if result.pass_at_k:
        for k, v in sorted(result.pass_at_k.items()):
            result.summary += f"pass@{k}: {v:.1%}  pass^{k}: {result.pass_pow_k.get(k, 0):.1%}\n"

    return result


def format_grade_report(result: EvalSuiteResult) -> str:
    """Format evaluation results as a readable report."""
    lines = ["=" * 60, "  GOLDEN DATASET EVALUATION REPORT", "=" * 60, ""]

    for g in result.grades:
        status = "PASS" if g.direction_correct else "FAIL"
        conf_status = "OK" if g.confidence_in_range else "MISS"
        lines.append(
            f"  [{status}] {g.scenario_id}: {g.scenario_name}"
        )
        lines.append(
            f"    Direction: {'correct' if g.direction_correct else 'wrong'} | "
            f"Confidence: {conf_status} | "
            f"Overall: {g.overall_score:.2f}"
        )
        if g.notes:
            lines.append(f"    Notes: {g.notes}")
        lines.append("")

    lines.append("-" * 60)
    lines.append(result.summary)
    lines.append("=" * 60)

    return "\n".join(lines)
