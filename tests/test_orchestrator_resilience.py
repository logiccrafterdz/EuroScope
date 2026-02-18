import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from euroscope.brain.orchestrator import Orchestrator
from euroscope.brain.agent import Agent
from euroscope.brain.skill_registry import SkillRegistry
from euroscope.skills.base import SkillContext, SkillResult

@pytest.fixture
async def orchestrator():
    registry = SkillRegistry()
    # Mock dependencies
    agent = MagicMock(spec=Agent)
    config = MagicMock()
    return Orchestrator(agent=agent, config=config, registry=registry)

@pytest.mark.asyncio
async def test_orchestrator_confidence_propagation_with_poor_data():
    """Verify that Orchestrator reduces final confidence based on data quality."""
    
    # Setup Orchestrator
    agent = MagicMock()
    config = MagicMock()
    orch = Orchestrator(agent=agent, config=config)
    
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
