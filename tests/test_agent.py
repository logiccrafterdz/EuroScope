import pytest
from unittest.mock import AsyncMock, MagicMock

from euroscope.brain.agent import Agent
from euroscope.config import LLMConfig


@pytest.mark.asyncio
async def test_chat_with_tools_price_request():
    router = MagicMock()
    router.chat_with_functions = AsyncMock(side_effect=[
        {"content": None, "function_calls": [{"name": "get_price", "arguments": {}}]},
        {"content": "Price is 1.08", "function_calls": []},
    ])
    agent = Agent(LLMConfig(), router=router)
    agent._execute_tool = AsyncMock(return_value={"success": True, "data": {"price": 1.08}})

    response = await agent.chat_with_tools("What's the current EUR/USD price?")
    assert "1.08" in response or "price" in response.lower()


@pytest.mark.asyncio
async def test_chat_with_tools_comprehensive_analysis():
    router = MagicMock()
    router.chat_with_functions = AsyncMock(side_effect=[
        {
            "content": None,
            "function_calls": [
                {"name": "get_technical_analysis", "arguments": {}},
                {"name": "get_news_sentiment", "arguments": {}},
            ],
        },
        {
            "content": "Technical outlook shows RSI at 55 with neutral momentum. "
                       "News sentiment remains supportive after ECB commentary. "
                       "Overall bias stays mildly bullish with cautious risk.",
            "function_calls": [],
        },
    ])

    async def execute_tool(name, _args):
        if name == "get_technical_analysis":
            return {"success": True, "data": {"RSI": 55}}
        if name == "get_news_sentiment":
            return {"success": True, "data": {"sentiment": "bullish"}}
        return {"success": False, "error": "unknown"}

    agent = Agent(LLMConfig(), router=router)
    agent._execute_tool = AsyncMock(side_effect=execute_tool)

    response = await agent.chat_with_tools(
        "Give me a full analysis of EUR/USD including technicals and news"
    )
    assert len(response) > 100
    assert "technical" in response.lower() or "rsi" in response


@pytest.mark.asyncio
async def test_react_loop_multi_step():
    router = MagicMock()
    router.chat_with_functions = AsyncMock(side_effect=[
        {
            "content": "Reason: need price and news sentiment",
            "function_calls": [
                {"name": "get_price", "arguments": {}},
                {"name": "get_news_sentiment", "arguments": {}},
            ],
        },
        {
            "content": "Market is neutral with light bullish sentiment. "
                       "Recommend waiting for confirmation before entering.",
            "function_calls": [],
        },
    ])
    router.chat = AsyncMock(return_value="Fallback answer")

    agent = Agent(LLMConfig(), router=router)
    agent._execute_tool = AsyncMock(return_value={"success": True, "data": {"price": 1.08}})

    result = await agent.chat_with_react_loop(
        "Should I trade EUR/USD right now?",
        max_iterations=3,
    )
    assert len(result["tools_used"]) >= 2
    assert result["iterations"] >= 2
    assert result["final_answer"] is not None
    assert len(result["final_answer"]) > 50
    assert 0.3 <= result["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_react_loop_confidence_calculation():
    router = MagicMock()
    router.chat_with_functions = AsyncMock(side_effect=[
        {
            "content": "Reason: need price",
            "function_calls": [{"name": "get_price", "arguments": {}}],
        },
        {"content": "Price is 1.08.", "function_calls": []},
        {
            "content": "Reason: need technicals, news, and risk",
            "function_calls": [
                {"name": "get_technical_analysis", "arguments": {}},
                {"name": "get_news_sentiment", "arguments": {}},
                {"name": "get_risk_assessment", "arguments": {}},
            ],
        },
        {
            "content": "Technicals are bullish and momentum is strong. "
                       "I recommend waiting for a pullback before entering.",
            "function_calls": [],
        },
    ])
    router.chat = AsyncMock(return_value="Fallback answer")

    agent = Agent(LLMConfig(), router=router)
    agent._execute_tool = AsyncMock(return_value={"success": True, "data": {"price": 1.08}})

    simple_result = await agent.chat_with_react_loop("What's the price?")
    complex_result = await agent.chat_with_react_loop(
        "Full analysis including technicals, fundamentals, and risk assessment"
    )

    assert simple_result["confidence"] < 0.7
    assert complex_result["confidence"] >= 0.6
