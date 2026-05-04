import pytest
from unittest.mock import AsyncMock, MagicMock
from euroscope.brain.orchestrator import Orchestrator
from euroscope.skills.base import SkillContext
from euroscope.brain.llm_router import LLMRouter
from euroscope.config import Config


@pytest.fixture
def mock_llm_router():
    router = MagicMock(spec=LLMRouter)
    # Return mock responses that pass schema validation
    router.chat_json = AsyncMock(side_effect=[
        # Bull case
        {"direction": "BUY", "conviction": 80.0, "key_arguments": [], "supporting_indicators": []},
        # Bear case
        {"counter_arguments": [], "risk_factors": [], "invalidation_levels": []},
        # Judgment
        {"final_direction": "BUY", "confidence": 85.0, "reasoning": "Test judgment", "bull_weight": 0.8, "bear_weight": 0.2},
        # Risk Aggressive
        {"proposed_lots": 1.0, "proposed_stop_loss_pips": 20.0, "proposed_take_profit_pips": 40.0, "reasoning": "A"},
        # Risk Conservative
        {"proposed_lots": 0.1, "proposed_stop_loss_pips": 40.0, "proposed_take_profit_pips": 20.0, "reasoning": "C"},
        # Risk Neutral
        {"proposed_lots": 0.5, "proposed_stop_loss_pips": 30.0, "proposed_take_profit_pips": 30.0, "reasoning": "N"},
        # Risk Judge
        {"position_size_lots": 0.5, "stop_loss_pips": 30.0, "take_profit_pips": 30.0, "risk_reward_ratio": 1.0, "risk_rating": "medium", "reasoning": "Balanced"}
    ])
    return router


@pytest.fixture
def test_config():
    config = Config()
    config.debate_enabled = True
    config.debate_min_confidence = 0.55
    return config


@pytest.mark.asyncio
async def test_debate_integration_in_orchestrator(test_config, mock_llm_router):
    # Setup Orchestrator with mock router
    orchestrator = Orchestrator(config=test_config, llm_router=mock_llm_router)
    
    # Mock the skill pipeline execution
    original_execute = orchestrator._execute_pipeline
    
    async def mock_execute(pipeline, context, params):
        if "risk_management" in [p[0] for p in pipeline]:
            # Simulate basic risk management
            if not context.risk:
                context.risk = {"lots": 0.1, "stop_loss": 50, "take_profit": 50}
            return context
            
        # Simulate base signal detection
        context.signals = {"direction": "BUY", "confidence": 60.0}
        return context
        
    orchestrator._execute_pipeline = mock_execute
    
    # Run pipeline
    ctx = SkillContext()
    ctx = await orchestrator.run_full_analysis_pipeline(ctx)
    
    # Verify debate was triggered (confidence 60 >= 55)
    assert mock_llm_router.chat_json.call_count == 7  # 3 investment + 4 risk
    
    # Verify context was updated with debate results
    assert "investment_debate" in ctx.metadata
    assert "risk_debate" in ctx.metadata
    assert "decision_id" in ctx.metadata
    
    # Verify risk parameters were overridden by debate
    assert ctx.risk["lots"] == 0.5
    assert ctx.risk["stop_loss"] == 30.0
    assert ctx.risk["take_profit"] == 30.0
    assert "DEBATE CONSENSUS" in ctx.risk["reasoning"]
