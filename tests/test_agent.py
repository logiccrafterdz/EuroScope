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
