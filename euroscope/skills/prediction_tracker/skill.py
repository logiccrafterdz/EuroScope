"""Prediction Tracker Skill — Wraps Memory for skill-level prediction tracking."""

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult
from ...brain.memory import Memory
from ...data.storage import Storage


class PredictionTrackerSkill(BaseSkill):
    """
    Prediction accuracy tracking as a skill.
    Records predictions, evaluates them, and generates learning insights
    that feed back into the LLM system prompt.
    """

    name = "prediction_tracker"
    description = "Prediction accuracy tracking and learning feedback"
    emoji = "🎯"
    category = SkillCategory.ANALYTICS
    version = "1.0.0"
    capabilities = ["record", "evaluate", "accuracy_report", "get_learning_context"]

    def __init__(self):
        super().__init__()
        self.storage = None
        self.memory = None

    def set_storage(self, storage):
        """Inject shared storage."""
        self.storage = storage

    def set_memory(self, memory):
        """Inject shared memory."""
        self.memory = memory

    def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "record":
            return self._record(**params)
        elif action == "evaluate":
            return self._evaluate(**params)
        elif action == "accuracy_report":
            return self._accuracy_report(**params)
        elif action == "get_learning_context":
            return self._get_learning_context()
        return SkillResult(success=False, error=f"Unknown action: {action}")

    def _record(self, **params) -> SkillResult:
        """Record a new prediction."""
        try:
            pred_id = self.memory.record_prediction(
                direction=params.get("direction", "NEUTRAL"),
                confidence=params.get("confidence", 50.0),
                reasoning=params.get("reasoning", ""),
                target_price=params.get("target_price"),
                timeframe=params.get("timeframe", "D1"),
            )
            return SkillResult(
                success=True,
                data={"prediction_id": pred_id},
                metadata={"formatted": f"🎯 Prediction #{pred_id} recorded."},
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _evaluate(self, **params) -> SkillResult:
        """Evaluate a prediction against actual outcome."""
        try:
            pred_id = params["pred_id"]
            actual_direction = params["actual_direction"]
            actual_price = params.get("actual_price", 0.0)

            self.memory.evaluate_prediction(pred_id, actual_direction, actual_price)

            return SkillResult(
                success=True,
                data={"pred_id": pred_id, "outcome": actual_direction},
                metadata={"formatted": f"✅ Prediction #{pred_id} evaluated: {actual_direction}"},
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _accuracy_report(self, **params) -> SkillResult:
        """Get accuracy stats."""
        try:
            days = params.get("days", 30)
            report = self.memory.get_accuracy_report(days)
            stats = self.storage.get_accuracy_stats(days)

            return SkillResult(
                success=True,
                data=stats,
                metadata={"formatted": report},
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _get_learning_context(self) -> SkillResult:
        """Get learning context for LLM prompt injection."""
        try:
            context_str = self.memory.get_learning_context()
            return SkillResult(
                success=True,
                data={"learning_context": context_str},
                metadata={"formatted": context_str},
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))
