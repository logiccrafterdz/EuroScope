"""
AI Agent — LLM Integration

Connects to OpenRouter/OpenAI for intelligent EUR/USD analysis,
forecasting, and Q&A.
"""

import asyncio
import json
import logging
from typing import Optional

import httpx

from ..config import LLMConfig
from .prompts import SYSTEM_PROMPT, ANALYSIS_PROMPT, FORECAST_PROMPT, QUESTION_PROMPT
from .llm_router import LLMRouter
from .vector_memory import VectorMemory

logger = logging.getLogger("euroscope.brain.agent")


class Agent:
    """LLM-powered EUR/USD expert agent."""

    def __init__(self, config: LLMConfig, router: Optional[LLMRouter] = None,
                 vector_memory: Optional[VectorMemory] = None, orchestrator=None,
                 forecaster=None):
        self.config = config
        self.router = router
        self.vector_memory = vector_memory
        self.orchestrator = orchestrator
        self.forecaster = forecaster
        self.conversation_history: list[dict] = []
        self.max_history = 20
        self.tool_timeout = 10

    async def chat(self, user_message: str, system_override: str = None) -> str:
        """Send a message to the LLM and get a response."""
        system = system_override or SYSTEM_PROMPT

        # Add vector memory context if available
        if self.vector_memory:
            context = self.vector_memory.get_relevant_context(user_message)
            if context:
                system += f"\n\n### LONG-TERM MEMORY (PAST CONTEXT)\n{context}"

        # Build messages
        messages = [{"role": "system", "content": system}]

        # Add recent conversation history for context
        messages.extend(self.conversation_history[-self.max_history:])
        messages.append({"role": "user", "content": user_message})

        # Use router if available
        if self.router:
            reply = await self.router.chat(messages)
            if not reply.startswith("❌"):
                # Save to history
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "assistant", "content": reply})
                # Trim history
                if len(self.conversation_history) > self.max_history * 2:
                    self.conversation_history = self.conversation_history[-self.max_history:]
            return reply

        # Fallback to direct call if no router
        if not self.config.api_key:
            return "⚠️ AI features disabled — no API key configured."

        system = system_override or SYSTEM_PROMPT

        # Build messages
        messages = [{"role": "system", "content": system}]

        # Add recent conversation history for context
        messages.extend(self.conversation_history[-self.max_history:])
        messages.append({"role": "user", "content": user_message})

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.config.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.config.model,
                        "messages": messages,
                        "max_tokens": self.config.max_tokens,
                        "temperature": self.config.temperature,
                    },
                )
                response.raise_for_status()
                data = response.json()

            reply = data["choices"][0]["message"]["content"]

            # Save to history
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": reply})

            # Trim history
            if len(self.conversation_history) > self.max_history * 2:
                self.conversation_history = self.conversation_history[-self.max_history:]

            return reply

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API error: {e.response.status_code} — {e.response.text[:500]}")
            return f"❌ AI error: {e.response.status_code}"
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return f"❌ AI unavailable: {str(e)[:100]}"

    async def chat_with_tools(self, user_message: str, max_iterations: int = 3) -> str:
        system = self._get_system_prompt_with_tools()
        if not self.router or not hasattr(self.router, "chat_with_functions"):
            return await self.chat(user_message, system_override=system)

        messages = [{"role": "system", "content": system}]
        messages.extend(self.conversation_history[-self.max_history:])
        messages.append({"role": "user", "content": user_message})

        tool_results = {}
        for _ in range(max_iterations):
            response = await self.router.chat_with_functions(
                messages=messages,
            )

            content = response.get("content")
            function_calls = response.get("function_calls") or []
            if content and not function_calls:
                return content

            if not function_calls:
                break

            for call in function_calls:
                name = call.get("name")
                args = call.get("arguments") or {}
                try:
                    result = await asyncio.wait_for(
                        self._execute_tool(name, args),
                        timeout=self.tool_timeout,
                    )
                except Exception as e:
                    result = {"success": False, "error": str(e)}

                tool_results[name] = result
                messages.append({
                    "role": "function",
                    "name": name,
                    "content": json.dumps(result),
                })

        summary = self._summarize_tool_results(tool_results)
        return summary if summary else await self.chat(user_message, system_override=system)

    def _get_system_prompt_with_tools(self) -> str:
        try:
            from ..workspace import WorkspaceManager

            ws = WorkspaceManager()
            return ws.build_system_prompt()
        except Exception:
            return SYSTEM_PROMPT

    async def _execute_tool(self, tool_name: str, arguments: dict) -> dict:
        from .orchestrator import Orchestrator
        from ..skills.base import SkillContext
        from ..utils.charts import generate_chart

        orchestrator = self.orchestrator or Orchestrator()
        self.orchestrator = orchestrator
        ctx = SkillContext()

        if tool_name == "get_price":
            result = await orchestrator.run_skill("market_data", "get_price", context=ctx)
            return self._skill_result_payload(result)

        if tool_name == "get_market_status":
            result = await orchestrator.run_skill("market_data", "check_market_status", context=ctx)
            return self._skill_result_payload(result)

        if tool_name == "get_technical_analysis":
            tf = arguments.get("timeframe") or "H1"
            data_result = await orchestrator.run_skill(
                "market_data",
                "get_candles",
                context=ctx,
                timeframe=tf,
                count=200,
            )
            if not data_result.success:
                return self._skill_result_payload(data_result)
            result = await orchestrator.run_skill(
                "technical_analysis",
                "full",
                context=ctx,
                timeframe=tf,
            )
            return self._skill_result_payload(result)

        if tool_name == "get_patterns":
            tf = arguments.get("timeframe") or "H1"
            data_result = await orchestrator.run_skill(
                "market_data",
                "get_candles",
                context=ctx,
                timeframe=tf,
                count=200,
            )
            if not data_result.success:
                return self._skill_result_payload(data_result)
            result = await orchestrator.run_skill(
                "technical_analysis",
                "detect_patterns",
                context=ctx,
                timeframe=tf,
            )
            return self._skill_result_payload(result)

        if tool_name == "get_levels":
            tf = arguments.get("timeframe") or "H1"
            data_result = await orchestrator.run_skill(
                "market_data",
                "get_candles",
                context=ctx,
                timeframe=tf,
                count=200,
            )
            if not data_result.success:
                return self._skill_result_payload(data_result)
            result = await orchestrator.run_skill(
                "technical_analysis",
                "find_levels",
                context=ctx,
                timeframe=tf,
            )
            return self._skill_result_payload(result)

        if tool_name == "get_signals":
            tf = arguments.get("timeframe") or "H1"
            ta_result = await orchestrator.run_skill(
                "technical_analysis",
                "full",
                context=ctx,
                timeframe=tf,
            )
            if not ta_result.success:
                return self._skill_result_payload(ta_result)
            result = await orchestrator.run_skill(
                "trading_strategy",
                "detect_signal",
                context=ctx,
            )
            return self._skill_result_payload(result)

        if tool_name == "get_strategy":
            ta_result = await orchestrator.run_skill(
                "technical_analysis",
                "full",
                context=ctx,
            )
            if not ta_result.success:
                return self._skill_result_payload(ta_result)
            result = await orchestrator.run_skill(
                "trading_strategy",
                "detect_signal",
                context=ctx,
            )
            return self._skill_result_payload(result)

        if tool_name == "get_risk_assessment":
            tf = arguments.get("timeframe") or "H1"
            if not arguments.get("entry_price"):
                await orchestrator.run_skill("market_data", "get_price", context=ctx)
            if not arguments.get("atr"):
                data_result = await orchestrator.run_skill(
                    "market_data",
                    "get_candles",
                    context=ctx,
                    timeframe=tf,
                    count=200,
                )
                if data_result.success:
                    await orchestrator.run_skill(
                        "technical_analysis",
                        "analyze",
                        context=ctx,
                        timeframe=tf,
                    )
            result = await orchestrator.run_skill(
                "risk_management",
                "assess_trade",
                context=ctx,
                **arguments,
            )
            return self._skill_result_payload(result)

        if tool_name == "get_fundamental_analysis":
            result = await orchestrator.run_skill("fundamental_analysis", "get_macro", context=ctx)
            return self._skill_result_payload(result)

        if tool_name == "get_news_sentiment":
            result = await orchestrator.run_skill("fundamental_analysis", "get_sentiment", context=ctx)
            return self._skill_result_payload(result)

        if tool_name == "get_calendar":
            result = await orchestrator.run_skill("fundamental_analysis", "get_calendar", context=ctx)
            return self._skill_result_payload(result)

        if tool_name == "get_macro":
            result = await orchestrator.run_skill("fundamental_analysis", "get_macro", context=ctx)
            return self._skill_result_payload(result)

        if tool_name == "get_performance":
            result = await orchestrator.run_skill("performance_analytics", "get_snapshot", context=ctx)
            return self._skill_result_payload(result)

        if tool_name == "get_trades":
            params = {}
            if arguments.get("status"):
                params["status"] = arguments.get("status")
            if arguments.get("limit"):
                params["limit"] = arguments.get("limit")
            result = await orchestrator.run_skill("trade_journal", "get_journal", context=ctx, **params)
            return self._skill_result_payload(result)

        if tool_name == "get_chart":
            tf = arguments.get("timeframe") or "H1"
            count = arguments.get("count") or 200
            data_result = await orchestrator.run_skill(
                "market_data",
                "get_candles",
                context=ctx,
                timeframe=tf,
                count=count,
            )
            if not data_result.success:
                return self._skill_result_payload(data_result)
            chart_path = generate_chart(ctx.market_data.get("candles"), timeframe=tf)
            if not chart_path:
                return {"success": False, "error": "Chart generation failed"}
            return {"success": True, "data": {"chart_path": chart_path}}

        if tool_name == "get_forecast":
            if not self.forecaster:
                return {"success": False, "error": "Forecast engine not available"}
            tf = arguments.get("timeframe") or "24 hours"
            result = await self.forecaster.generate_forecast(tf)
            return {"success": True, "data": result}

        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    @staticmethod
    def _skill_result_payload(result):
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "metadata": result.metadata,
        }

    @staticmethod
    def _summarize_tool_results(tool_results: dict) -> str:
        if not tool_results:
            return ""
        lines = []
        for name, payload in tool_results.items():
            if not isinstance(payload, dict):
                lines.append(f"{name}: {payload}")
                continue
            if payload.get("success"):
                data = payload.get("data")
                lines.append(f"{name}: {data}")
            else:
                lines.append(f"{name}: {payload.get('error')}")
        return "\n".join(lines)

    async def analyze(self, market_data: str, technical_data: str,
                      patterns_data: str, levels_data: str,
                      news_data: str, calendar_context: str) -> str:
        """Generate comprehensive EUR/USD analysis."""
        prompt = ANALYSIS_PROMPT.format(
            market_data=market_data,
            technical_data=technical_data,
            patterns_data=patterns_data,
            levels_data=levels_data,
            news_data=news_data,
            calendar_context=calendar_context,
        )
        return await self.chat(prompt, system_override=SYSTEM_PROMPT)

    async def forecast(self, price_data: str, technical_summary: str,
                       patterns: str, levels: str, news: str,
                       prediction_history: str, timeframe: str = "24 hours") -> str:
        """Generate directional forecast."""
        prompt = FORECAST_PROMPT.format(
            price_data=price_data,
            technical_summary=technical_summary,
            patterns=patterns,
            levels=levels,
            news=news,
            prediction_history=prediction_history,
            timeframe=timeframe,
        )
        return await self.chat(prompt, system_override=SYSTEM_PROMPT)

    async def ask(self, question: str, current_price: str = "N/A",
                  current_bias: str = "N/A", support: str = "N/A",
                  resistance: str = "N/A", market_status: str = "N/A") -> str:
        """Answer a free-form question about EUR/USD."""
        prompt = QUESTION_PROMPT.format(
            current_price=current_price,
            current_bias=current_bias,
            support=support,
            resistance=resistance,
            market_status=market_status,
            question=question,
        )
        return await self.chat(prompt)

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history.clear()
