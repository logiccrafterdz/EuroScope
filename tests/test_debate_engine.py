import pytest
from unittest.mock import AsyncMock, MagicMock
from euroscope.brain.debate_engine import DebateEngine
from euroscope.brain.llm_router import LLMRouter
from euroscope.skills.base import SkillContext


@pytest.fixture
def mock_llm_router():
    router = MagicMock(spec=LLMRouter)
    router.chat_json = AsyncMock()
    return router


@pytest.fixture
def debate_engine(mock_llm_router):
    return DebateEngine(mock_llm_router)


@pytest.fixture
def sample_context():
    ctx = SkillContext()
    ctx.analysis = {
        "indicators": {
            "overall_bias": "BULLISH",
            "indicators": {
                "RSI": {"value": 45.0},
                "MACD": {"signal": "BUY"}
            }
        }
    }
    return ctx


@pytest.mark.asyncio
async def test_run_investment_debate_success(debate_engine, mock_llm_router, sample_context):
    # Mock LLM responses
    mock_llm_router.chat_json.side_effect = [
        # Bull case response
        {
            "direction": "BUY",
            "conviction": 85.0,
            "key_arguments": ["Strong RSI", "MACD crossover"],
            "supporting_indicators": ["RSI", "MACD"]
        },
        # Bear case response
        {
            "counter_arguments": ["RSI is still below 50"],
            "risk_factors": ["Upcoming news"],
            "invalidation_levels": [1.0500]
        },
        # Judgment response
        {
            "final_direction": "BUY",
            "confidence": 75.0,
            "reasoning": "Bull case is stronger due to MACD.",
            "bull_weight": 0.7,
            "bear_weight": 0.3
        }
    ]

    result = await debate_engine.run_investment_debate(sample_context, "BUY")
    
    assert result["judgment"]["final_direction"] == "BUY"
    assert result["judgment"]["confidence"] == 75.0
    assert "bull_case" in result
    assert "bear_case" in result
    assert mock_llm_router.chat_json.call_count == 3


@pytest.mark.asyncio
async def test_run_investment_debate_fallback_on_bull_failure(debate_engine, mock_llm_router, sample_context):
    # Mock LLM response to fail on Bull case (e.g. returns empty dict or error dict that doesn't match schema)
    # Actually, the implementation just checks if truthy. Let's return None or empty dict.
    mock_llm_router.chat_json.return_value = {}

    result = await debate_engine.run_investment_debate(sample_context, "BUY")
    
    assert result["judgment"]["final_direction"] == "HOLD"
    assert "error" in result["bull_case"]
    assert result["judgment"]["confidence"] == 0.0


@pytest.mark.asyncio
async def test_format_context(debate_engine, sample_context):
    formatted = debate_engine._format_context(sample_context)
    assert "--- Technical Analysis ---" in formatted
    assert "Overall Bias: BULLISH" in formatted
    assert "RSI: 45.0" in formatted
