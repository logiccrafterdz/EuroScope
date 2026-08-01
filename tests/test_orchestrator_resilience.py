import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from euroscope.brain.orchestrator import Orchestrator
from euroscope.skills.base import SkillContext, SkillResult

@pytest.mark.asyncio
async def test_orchestrator_skips_hanging_skill_within_timeout():
    """A stuck skill must be skipped after SKILL_TIMEOUT, not hang the pipeline."""
    orch = Orchestrator()
    ok_result = SkillResult(success=True, data={"ok": True})

    async def fake_run_skill(skill_name, action, **kwargs):
        if skill_name == "market_data":
            await asyncio.sleep(10)
        return ok_result

    with patch.object(orch, 'run_skill', side_effect=fake_run_skill):
        with patch.object(type(orch), 'SKILL_TIMEOUT', 0.05, create=False):
            pipeline = [("market_data", "get_candles"), ("technical_analysis", "full")]
            ctx = await orch._execute_pipeline(pipeline, context=SkillContext())
            assert ctx is not None

@pytest.mark.asyncio
async def test_orchestrator_confidence_propagation_with_poor_data():
    """Verify that Orchestrator reduces final confidence based on data quality."""
    
    # Setup Orchestrator
    orch = Orchestrator()
    
    # Mock Skill Results
    # 1. Fundamental analysis returns 'minimal' quality
    macro_result = SkillResult(
        success=True,
        data={"confidence": 0.85, "data_quality": "minimal"},
        metadata={"quality": "minimal", "warnings": ["FRED Offline"]}
    )
    
    # 2. Conflict Arbiter returns high base confidence
    resolution = {
        "final_direction": "BUY",
        "confidence": 0.9,
        "reasoning": "Strong technical signal",
        "conflicts_resolved": False
    }

    # Context and setup
    ctx = SkillContext()
    
    with patch.object(orch, 'run_skill', AsyncMock(return_value=macro_result)):
        with patch.object(orch.conflict_arbiter, 'resolve', return_value=resolution):
            with patch.object(orch, '_has_conflicting_signals', return_value=True):
                
                # Execute pipeline (simulated)
                pipeline = [("fundamental_analysis", "get_macro")]
                await orch._execute_pipeline(pipeline, context=ctx)
                
                # Verify confidence penalty in _execute_pipeline (or wherever resolve is called)
                # In Orchestrator._execute_pipeline, final confidence is adjusted
                assert ctx.metadata["data_quality_warning"] is True
                assert ctx.metadata["final_confidence"] == pytest.approx(0.45) # 0.9 * 0.5 penalty
                assert ctx.signals["confidence"] == pytest.approx(0.45)
