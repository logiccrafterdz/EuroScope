import pytest
from unittest.mock import AsyncMock, MagicMock
from euroscope.brain.risk_debate import RiskDebate
from euroscope.brain.llm_router import LLMRouter
from euroscope.skills.base import SkillContext


@pytest.fixture
def mock_llm_router():
    router = MagicMock(spec=LLMRouter)
    router.chat_json = AsyncMock()
    return router


@pytest.fixture
def risk_debate(mock_llm_router):
    return RiskDebate(mock_llm_router)


@pytest.fixture
def sample_context():
    ctx = SkillContext()
    ctx.metadata = {
        "regime": "trending",
        "volatility": "normal",
        "active_session": "London"
    }
    ctx.analysis = {
        "indicators": {
            "indicators": {
                "ATR": {"pips": 15.5}
            }
        }
    }
    return ctx


@pytest.fixture
def sample_judgment():
    return {
        "final_direction": "BUY",
        "confidence": 80.0,
        "reasoning": "Strong trend."
    }


@pytest.mark.asyncio
async def test_run_risk_debate_success(risk_debate, mock_llm_router, sample_context, sample_judgment):
    # Mock LLM responses: 3 analysts + 1 judge
    mock_llm_router.chat_json.side_effect = [
        # Aggressive
        {"proposed_lots": 1.0, "proposed_stop_loss_pips": 15.0, "proposed_take_profit_pips": 45.0, "reasoning": "A"},
        # Conservative
        {"proposed_lots": 0.2, "proposed_stop_loss_pips": 30.0, "proposed_take_profit_pips": 30.0, "reasoning": "C"},
        # Neutral
        {"proposed_lots": 0.5, "proposed_stop_loss_pips": 20.0, "proposed_take_profit_pips": 40.0, "reasoning": "N"},
        # Judge
        {
            "position_size_lots": 0.5,
            "stop_loss_pips": 20.0,
            "take_profit_pips": 40.0,
            "risk_reward_ratio": 2.0,
            "risk_rating": "medium",
            "reasoning": "Balanced approach."
        }
    ]

    result = await risk_debate.run_risk_debate(sample_context, sample_judgment)
    
    assert result["final_profile"]["position_size_lots"] == 0.5
    assert result["final_profile"]["risk_rating"] == "medium"
    assert mock_llm_router.chat_json.call_count == 4


@pytest.mark.asyncio
async def test_run_risk_debate_skip_on_hold(risk_debate, mock_llm_router, sample_context):
    judgment = {
        "final_direction": "HOLD",
        "confidence": 0.0,
        "reasoning": "No clear signal."
    }
    
    result = await risk_debate.run_risk_debate(sample_context, judgment)
    
    assert mock_llm_router.chat_json.call_count == 0
    assert result["final_profile"]["position_size_lots"] == 0.0
    assert "skipped" in result["final_profile"]["reasoning"]
