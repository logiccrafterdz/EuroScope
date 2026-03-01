"""
AI Agent — LLM Integration

Connects to OpenRouter/OpenAI for intelligent EUR/USD analysis,
forecasting, and Q&A.
"""

import asyncio
import json
import logging
import re
import time
from typing import Optional, Any

import httpx

from ..config import LLMConfig
from .prompts import SYSTEM_PROMPT, ANALYSIS_PROMPT, FORECAST_PROMPT, QUESTION_PROMPT
from .llm_router import LLMRouter
from .function_schema import get_all_function_schemas, FUNCTION_SCHEMAS, SkillFunction
from .vector_memory import VectorMemory

logger = logging.getLogger("euroscope.brain.agent")


class Agent:
    """LLM-powered EUR/USD expert agent."""

    def __init__(self, config: LLMConfig, router: Optional[LLMRouter] = None,
                 vector_memory: Optional[VectorMemory] = None, orchestrator=None,
                 forecaster=None, cost_tracker=None):
        self.config = config
        self.router = router
        self.vector_memory = vector_memory
        self.orchestrator = orchestrator
        self.forecaster = forecaster
        self.skill_function_enum = SkillFunction  # Resolves Scope/NameError
        # Per-user conversation histories: {chat_id: {"messages": [...], "last_active": float}}
        self._histories: dict[int, dict] = {}
        self.max_history = 20
        self.max_users = 100
        self.history_ttl = 7200  # 2 hours in seconds
        self.tool_timeout = 10
        # LLM cost tracking
        from .cost_tracker import CostTracker
        self.cost_tracker = cost_tracker or CostTracker()

    def _get_history(self, chat_id: int) -> list[dict]:
        """Get or create per-user conversation history with TTL cleanup."""
        now = time.time()
        # Evict expired histories
        expired = [uid for uid, h in self._histories.items()
                   if now - h["last_active"] > self.history_ttl]
        for uid in expired:
            del self._histories[uid]
        # LRU eviction if at capacity
        if chat_id not in self._histories and len(self._histories) >= self.max_users:
            oldest = min(self._histories, key=lambda k: self._histories[k]["last_active"])
            del self._histories[oldest]
        # Get or create
        if chat_id not in self._histories:
            self._histories[chat_id] = {"messages": [], "last_active": now}
        self._histories[chat_id]["last_active"] = now
        return self._histories[chat_id]["messages"]

    def _trim_history(self, chat_id: int):
        """Trim per-user history to max_history messages."""
        hist = self._histories.get(chat_id)
        if hist and len(hist["messages"]) > self.max_history * 2:
            hist["messages"] = hist["messages"][-self.max_history:]

    async def chat(self, user_message: str, system_override: str = None, chat_id: int = 0) -> str:
        """Send a message to the LLM and get a response."""
        system = system_override or SYSTEM_PROMPT

        # Add vector memory context if available
        if self.vector_memory:
            context = self.vector_memory.get_relevant_context(user_message)
            if context:
                system += f"\n\n### LONG-TERM MEMORY (PAST CONTEXT)\n{context}"

        # Build messages
        messages = [{"role": "system", "content": system}]

        # Add recent conversation history for this user
        user_history = self._get_history(chat_id)
        messages.extend(user_history[-self.max_history:])
        messages.append({"role": "user", "content": user_message})

        # Use router if available
        if self.router:
            reply = await self.router.chat(messages)
            if not reply.startswith("❌"):
                # Save to per-user history
                user_history = self._get_history(chat_id)
                user_history.append({"role": "user", "content": user_message})
                user_history.append({"role": "assistant", "content": reply})
                self._trim_history(chat_id)
            return reply

        # Fallback to direct call if no router
        if not self.config.api_key:
            return "⚠️ AI features disabled — no API key configured."

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

            # Save to per-user history
            user_history = self._get_history(chat_id)
            user_history.append({"role": "user", "content": user_message})
            user_history.append({"role": "assistant", "content": reply})
            self._trim_history(chat_id)

            return reply

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API error: {e.response.status_code} — {e.response.text[:500]}")
            return f"❌ AI error: {e.response.status_code}"
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return f"❌ AI unavailable: {str(e)[:100]}"

    async def stateless_chat(self, user_message: str, system_override: str = None) -> str:
        """Send a message to the LLM WITHOUT polluting the user's conversation history."""
        system = system_override or self._get_system_prompt_with_tools()

        # Add vector memory context if available
        if self.vector_memory:
            context = self.vector_memory.get_relevant_context(user_message)
            if context:
                system += f"\n\n### LONG-TERM MEMORY (PAST CONTEXT)\n{context}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message}
        ]

        if self.router:
            reply = await self.router.chat(messages)
            return reply

        if not self.config.api_key:
            return "⚠️ AI features disabled — no API key configured."

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
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Stateless LLM API error: {e.response.status_code} — {e.response.text[:500]}")
            return f"❌ AI error: {e.response.status_code}"
        except Exception as e:
            logger.error(f"Stateless LLM call failed: {e}")
            return f"❌ AI unavailable: {str(e)[:100]}"

    async def chat_with_tools(self, user_message: str, max_iterations: int = 3, chat_id: int = 0) -> str:
        """Simple tool-enabled chat with synthesis."""
        system = self._get_system_prompt_with_tools()
        if not self.router or not hasattr(self.router, "chat_with_functions"):
            return await self.chat(user_message, system_override=system, chat_id=chat_id)

        messages = [{"role": "system", "content": system}]
        messages.extend(self._get_history(chat_id)[-self.max_history:])
        messages.append({"role": "user", "content": user_message})

        for _ in range(max_iterations):
            response = await self.router.chat_with_functions(messages=messages)
            content = response.get("content")
            function_calls = response.get("function_calls") or []
            raw_message = response.get("raw_message")
            
            # Check for pseudo-tool calls in text if no formal function calls
            if not function_calls and content:
                function_calls = self._parse_text_tool_calls(content)

            if not function_calls:
                return content or "❌ No response from AI."

            # Append the assistant's tool call message
            # CRITICAL: If no formal tool_calls exist in the raw_message, we MUST create them
            raw_message = response.get("raw_message")
            if raw_message and raw_message.get("tool_calls"):
                messages.append(raw_message)
            else:
                messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": call.get("id") or f"call_{i}",
                            "type": "function",
                            "function": {"name": call["name"], "arguments": json.dumps(call.get("arguments", {}))}
                        } for i, call in enumerate(function_calls)
                    ]
                })

            for i, call in enumerate(function_calls):
                name = call.get("name")
                args = call.get("arguments") or {}
                call_id = call.get("id") or f"call_{i}"
                try:
                    result = await asyncio.wait_for(
                        self._execute_tool(name, args),
                        timeout=self.tool_timeout,
                    )
                except Exception as e:
                    result = {"success": False, "error": str(e)}

                observation = self._format_tool_observation(name, result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": observation,
                })
            # After tool results, ask for synthesis
            messages.append({
                "role": "user", 
                "content": "Synthesize the above tool results into a final actionable analysis for the user."
            })
            
        final_response = await self.router.chat(messages)
        return final_response

    async def chat_with_react_loop(
        self,
        user_message: str,
        max_iterations: int = 5,
        max_tokens_per_iteration: int = 1500,
        custom_functions: Optional[list[dict]] = None,
        system_override: Optional[str] = None,
    ) -> dict[str, Any]:
        if not self.router or not hasattr(self.router, "chat_with_functions"):
            final_answer = await self.chat(user_message, system_override=self._get_system_prompt_with_tools())
            return {
                "final_answer": final_answer,
                "reasoning_steps": [],
                "tools_used": [],
                "iterations": 0,
                "confidence": self._calculate_confidence(final_answer, []),
            }
        system = system_override or self._get_react_system_prompt()
        if self.vector_memory:
            context = self.vector_memory.get_relevant_context(user_message)
            if context:
                system += f"\n\n### LONG-TERM MEMORY (PAST CONTEXT)\n{context}"

        functions = custom_functions if custom_functions is not None else get_all_function_schemas()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]

        reasoning_steps: list[str] = []
        tools_used: list[str] = []
        iteration = 0
        start_time = time.time()
        max_total_time = 60

        while iteration < max_iterations:
            if time.time() - start_time > max_total_time:
                final_answer = await self._force_final_answer(messages)
                confidence = self._calculate_confidence(final_answer, tools_used, incomplete=True)
                return {
                    "final_answer": final_answer,
                    "reasoning_steps": reasoning_steps,
                    "tools_used": tools_used,
                    "iterations": iteration,
                    "confidence": confidence,
                    "warning": "Reached max time — answer may be incomplete",
                }

            iteration += 1
            try:
                response = await asyncio.wait_for(
                    self.router.chat_with_functions(
                        messages=messages,
                        functions=functions,
                        function_call="auto",
                        max_tokens=max_tokens_per_iteration,
                    ),
                    timeout=15,
                )
            except Exception as e:
                final_answer = await self._force_final_answer(messages)
                confidence = self._calculate_confidence(final_answer, tools_used, incomplete=True)
                return {
                    "final_answer": final_answer,
                    "reasoning_steps": reasoning_steps,
                    "tools_used": tools_used,
                    "iterations": iteration,
                    "confidence": confidence,
                    "warning": f"Iteration timeout or error: {str(e)[:100]}",
                }

            content = response.get("content")
            function_calls = response.get("function_calls") or []

            # Check for pseudo-tool calls in text if no formal function calls
            if not function_calls and content:
                function_calls = self._parse_text_tool_calls(content)

            if content:
                # Anti-hallucination: if the model wrote "Observation:" itself, it's hallucinating result.
                # Truncate content at the first sign of hallucination.
                for trigger in ["Observation:", "OBSERVE:", "Result:", "RESULT:"]:
                    if trigger in content:
                        logger.warning(f"Detected hallucinated {trigger} in iteration {iteration}")
                        content = content.split(trigger)[0].strip()
                        break
                
                reasoning = self._extract_reasoning(content)
                if reasoning:
                    reasoning_steps.append(f"Iteration {iteration}: {reasoning}")

            # If the model provided a final answer without tools, or explicitly said it's finished
            if content and not function_calls:
                # Check if it's actually a final answer or just reasoning without action
                lowered = content.lower()
                if (
                    "get_" not in lowered
                    and not any(x in lowered for x in ["reason:", "act:", "thought:", "observation:", "observe:"])
                ):
                    clean_content = content
                    for marker in ["REASON:", "ACT:", "THOUGHT:", "FINAL ANALYSIS:"]:
                        clean_content = clean_content.replace(marker, "").strip()
                    confidence = self._calculate_confidence(clean_content, tools_used)
                    return {
                        "final_answer": clean_content,
                        "reasoning_steps": reasoning_steps,
                        "tools_used": tools_used,
                        "iterations": iteration,
                        "confidence": confidence,
                    }
                if any(x in lowered for x in ["final analysis:", "answer:", "comprehensive analysis", "summary:"]):
                    # Clean up the final answer from any leftover ReAct markers
                    clean_content = content
                    for marker in ["REASON:", "ACT:", "THOUGHT:", "FINAL ANALYSIS:"]:
                        clean_content = clean_content.replace(marker, "").strip()
                    
                    confidence = self._calculate_confidence(clean_content, tools_used)
                    return {
                        "final_answer": clean_content,
                        "reasoning_steps": reasoning_steps,
                        "tools_used": tools_used,
                        "iterations": iteration,
                        "confidence": confidence,
                    }
                else:
                    # If it's just talking without taking action, prompt for action or final answer
                    messages.append({
                        "role": "user",
                        "content": "You provided reasoning but no action. Either call a tool or provide 'FINAL ANALYSIS:' if you are finished."
                    })
                    continue

            if not function_calls:
                final_answer = await self._force_final_answer(messages)
                confidence = self._calculate_confidence(final_answer, tools_used, incomplete=True)
                return {
                    "final_answer": final_answer,
                    "reasoning_steps": reasoning_steps,
                    "tools_used": tools_used,
                    "iterations": iteration,
                    "confidence": confidence,
                    "warning": "No tools selected — answer may be incomplete",
                }

            proactive_call = next(
                (call for call in function_calls if call.get("name") == "proactive_alert_decision"),
                None,
            )
            if proactive_call:
                return {
                    "final_answer": content or "",
                    "reasoning_steps": reasoning_steps,
                    "tools_used": tools_used,
                    "iterations": iteration,
                    "confidence": self._calculate_confidence(content or "", tools_used),
                    "function_call_result": proactive_call.get("arguments") or {},
                }

            # Append assistant message with tool calls
            # CRITICAL: If no formal tool_calls exist in the raw_message, we MUST create them
            # so the API accepts the subsequent 'tool' role messages.
            raw_message = response.get("raw_message")
            if raw_message and raw_message.get("tool_calls"):
                messages.append(raw_message)
            else:
                # Create a synthetic assistant message with tool_calls for history
                messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": call.get("id") or f"call_{iteration}_{i}",
                            "type": "function",
                            "function": {"name": call["name"], "arguments": json.dumps(call.get("arguments", {}))}
                        } for i, call in enumerate(function_calls)
                    ]
                })

            tool_results = []
            for i, call in enumerate(function_calls):
                name = call.get("name")
                args = call.get("arguments") or {}
                call_id = call.get("id") or f"call_{iteration}_{i}"
                if name == "proactive_alert_decision":
                    continue
                
                try:
                    result = await asyncio.wait_for(
                        self._execute_tool(name, args),
                        timeout=self.tool_timeout,
                    )
                except Exception as e:
                    result = {"success": False, "error": str(e)}

                tools_used.append(name)
                observation = self._format_tool_observation(name, result)
                tool_results.append(observation)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": observation,
                })

            # Removed the intermediate user message to maintain a clean sequence:
            # assistant(tool_calls) -> tool(results) -> assistant(response)

        final_answer = await self._force_final_answer(messages)
        confidence = self._calculate_confidence(final_answer, tools_used, incomplete=True)
        return {
            "final_answer": final_answer,
            "reasoning_steps": reasoning_steps,
            "tools_used": tools_used,
            "iterations": iteration,
            "confidence": confidence,
            "warning": "Reached max iterations — answer may be incomplete",
        }

    async def stateless_chat_with_react_loop(
        self,
        user_message: str,
        max_iterations: int = 5,
        max_tokens_per_iteration: int = 1500,
        custom_functions: Optional[list[dict]] = None,
        system_override: Optional[str] = None,
    ) -> dict[str, Any]:
        """A ReAct loop that does NOT include the user's conversational history."""
        if not self.router or not hasattr(self.router, "chat_with_functions"):
            final_answer = await self.stateless_chat(user_message, system_override=self._get_system_prompt_with_tools())
            return {
                "final_answer": final_answer,
                "reasoning_steps": [],
                "tools_used": [],
                "iterations": 0,
                "confidence": self._calculate_confidence(final_answer, []),
            }
        
        system = system_override or self._get_react_system_prompt()
        if self.vector_memory:
            context = self.vector_memory.get_relevant_context(user_message)
            if context:
                system += f"\n\n### LONG-TERM MEMORY (PAST CONTEXT)\n{context}"

        functions = custom_functions if custom_functions is not None else get_all_function_schemas()
        # NOTICE: No self.conversation_history loaded here
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]

        reasoning_steps: list[str] = []
        tools_used: list[str] = []
        iteration = 0
        start_time = time.time()
        max_total_time = 75  # Slightly longer for background analysis

        while iteration < max_iterations:
            if time.time() - start_time > max_total_time:
                final_answer = await self._force_final_answer(messages)
                confidence = self._calculate_confidence(final_answer, tools_used, incomplete=True)
                return {
                    "final_answer": final_answer,
                    "reasoning_steps": reasoning_steps,
                    "tools_used": tools_used,
                    "iterations": iteration,
                    "confidence": confidence,
                    "warning": "Reached max time — answer may be incomplete",
                }

            iteration += 1
            try:
                response = await asyncio.wait_for(
                    self.router.chat_with_functions(
                        messages=messages,
                        functions=functions,
                        function_call="auto",
                        max_tokens=max_tokens_per_iteration,
                    ),
                    timeout=20, # Higher timeout for background processing
                )
            except Exception as e:
                final_answer = await self._force_final_answer(messages)
                if not reasoning_steps and not tools_used:
                    # In case of early timeout
                    final_answer = "Timeout during background task before any data was processed."
                confidence = self._calculate_confidence(final_answer, tools_used, incomplete=True)
                return {
                    "final_answer": final_answer,
                    "reasoning_steps": reasoning_steps,
                    "tools_used": tools_used,
                    "iterations": iteration,
                    "confidence": confidence,
                    "warning": f"Iteration timeout or error: {str(e)[:100]}",
                }

            content = response.get("content")
            function_calls = response.get("function_calls") or []

            if not function_calls and content:
                function_calls = self._parse_text_tool_calls(content)

            if content:
                for trigger in ["Observation:", "OBSERVE:", "Result:", "RESULT:"]:
                    if trigger in content:
                        logger.warning(f"Detected hallucinated {trigger} in stateless iteration {iteration}")
                        content = content.split(trigger)[0].strip()
                        break
                
                reasoning = self._extract_reasoning(content)
                if reasoning:
                    reasoning_steps.append(f"Iteration {iteration}: {reasoning}")

            if content and not function_calls:
                lowered = content.lower()
                if (
                    "get_" not in lowered
                    and not any(x in lowered for x in ["reason:", "act:", "thought:", "observation:", "observe:"])
                ):
                    clean_content = content
                    for marker in ["REASON:", "ACT:", "THOUGHT:", "FINAL ANALYSIS:"]:
                        clean_content = clean_content.replace(marker, "").strip()
                    confidence = self._calculate_confidence(clean_content, tools_used)
                    return {
                        "final_answer": clean_content,
                        "reasoning_steps": reasoning_steps,
                        "tools_used": tools_used,
                        "iterations": iteration,
                        "confidence": confidence,
                    }
                if any(x in lowered for x in ["final analysis:", "answer:", "comprehensive analysis", "summary:"]):
                    clean_content = content
                    for marker in ["REASON:", "ACT:", "THOUGHT:", "FINAL ANALYSIS:"]:
                        clean_content = clean_content.replace(marker, "").strip()
                    
                    confidence = self._calculate_confidence(clean_content, tools_used)
                    return {
                        "final_answer": clean_content,
                        "reasoning_steps": reasoning_steps,
                        "tools_used": tools_used,
                        "iterations": iteration,
                        "confidence": confidence,
                    }
                else:
                    messages.append({
                        "role": "user",
                        "content": "You provided reasoning but no action. Either call a tool or provide 'FINAL ANALYSIS:' if you are finished."
                    })
                    continue

            if not function_calls:
                final_answer = await self._force_final_answer(messages)
                confidence = self._calculate_confidence(final_answer, tools_used, incomplete=True)
                return {
                    "final_answer": final_answer,
                    "reasoning_steps": reasoning_steps,
                    "tools_used": tools_used,
                    "iterations": iteration,
                    "confidence": confidence,
                    "warning": "No tools selected — answer may be incomplete",
                }

            proactive_call = next(
                (call for call in function_calls if call.get("name") == "proactive_alert_decision"),
                None,
            )
            if proactive_call:
                return {
                    "final_answer": content or "",
                    "reasoning_steps": reasoning_steps,
                    "tools_used": tools_used,
                    "iterations": iteration,
                    "confidence": self._calculate_confidence(content or "", tools_used),
                    "function_call_result": proactive_call.get("arguments") or {},
                }

            raw_message = response.get("raw_message")
            if raw_message and raw_message.get("tool_calls"):
                messages.append(raw_message)
            else:
                messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": call.get("id") or f"call_{iteration}_{i}",
                            "type": "function",
                            "function": {"name": call["name"], "arguments": json.dumps(call.get("arguments", {}))}
                        } for i, call in enumerate(function_calls)
                    ]
                })

            tool_results = []
            for i, call in enumerate(function_calls):
                name = call.get("name")
                args = call.get("arguments") or {}
                call_id = call.get("id") or f"call_{iteration}_{i}"
                if name == "proactive_alert_decision":
                    continue
                
                try:
                    result = await asyncio.wait_for(
                        self._execute_tool(name, args),
                        timeout=self.tool_timeout,
                    )
                except Exception as e:
                    result = {"success": False, "error": str(e)}

                tools_used.append(name)
                observation = self._format_tool_observation(name, result)
                tool_results.append(observation)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": observation,
                })

        final_answer = await self._force_final_answer(messages)
        confidence = self._calculate_confidence(final_answer, tools_used, incomplete=True)
        return {
            "final_answer": final_answer,
            "reasoning_steps": reasoning_steps,
            "tools_used": tools_used,
            "iterations": iteration,
            "confidence": confidence,
            "warning": "Reached max iterations — answer may be incomplete",
        }

    async def run_proactive_analysis(self) -> dict[str, Any]:
        """
        Autonomous market analysis for proactive alerts (Phase 3A+).
        """
        # Fetch live data and run advanced skills so the LLM works with a deep understanding
        current_price = "Unavailable"
        recent_candles = "Unavailable"
        advanced_analysis = "No advanced analysis available."
        
        if hasattr(self, "orchestrator") and self.orchestrator:
            try:
                # 1. Get raw price quickly
                res = await self.orchestrator.run_skill("market_data", "get_price")
                if res.success and "price" in res.data:
                    current_price = f"{res.data['price']:.5f}"
                
                # 2. Get recent candles
                res_c = await self.orchestrator.run_skill("market_data", "get_candles", timeframe="H1", limit=6)
                if res_c.success and "df" in res_c.data:
                    df = res_c.data["df"]
                    recent_candles = df[["open", "high", "low", "close"]].tail(6).to_string()
                    
                # 3. Run the complete autonomous pipeline to get Liquidity, Fundamentals, Risk, etc.
                ctx = await self.orchestrator.run_full_analysis_pipeline(timeframe="H1")
                advanced_analysis = ctx.metadata.get("formatted", "Pipeline executed but yielded no formatted summary.")
                
            except Exception as e:
                logger.warning(f"Proactive analysis: failed to run full advanced pipeline: {e}")

        proactive_prompt = (
            "You are EuroScope, a highly proactive, intelligent, and autonomous EUR/USD trading companion.\n"
            "Your goal is to digest the raw market data AND the deep advanced analysis provided below to decide if an alert is warranted.\n\n"
            f"--- LIVE MARKET STATE ---\n- EUR/USD Price: {current_price}\n- Recent H1 Candles:\n{recent_candles}\n\n"
            f"--- ADVANCED SKILLS ANALYSIS ---\n{advanced_analysis}\n\n"
            "MULTI-LAYER DETECTION SYSTEM:\n"
            "1. **Layer 1: Technical & Price Action**: Breakouts, bounces off key levels (Support/Resistance/Fib), or interesting candle formations.\n"
            "2. **Layer 2: Liquidity Events**: Order blocks, sweeps of session highs/lows, or institutional accumulation/distribution.\n"
            "3. **Layer 3: Macro Catalysts**: Post-news reactions or upcoming high-impact events within the next 60 minutes.\n"
            "4. **Layer 4: Regime & Volatility**: Sudden deviations in volatility, trend direction changes, or notable compression/ranging.\n\n"
            "ALERT PRIORITIZATION (Critical, High, Medium, Low):\n"
            "- CRITICAL: Immediate action! Liquidity sweep + breakout or extreme high-impact event < 15m.\n"
            "- HIGH: Strong setup! Technical breakout with sentiment and liquidity alignment.\n"
            "- MEDIUM: Market Pulse & Insights! Pattern completing, approaching key level, or regime change confirmed. You are simply sharing your thoughts on the current situation.\n"
            "- LOW: Informational baseline (Asian session setup, minor levels).\n\n"
            "GUIDELINES:\n"
            "- BE PROACTIVE AND VOCAL: Share your insights! If the market is ranging/quiet, explain *why* and what level you are waiting for.\n"
            "- Provide a clear, narrative 'Market Pulse' or 'Insight' if no direct trade setup is found.\n"
            "- Use emojis naturally to make the update readable.\n"
            "- Call proactive_alert_decision with your final decision. You should ALMOST ALWAYS choose to alert (should_alert=True), using MEDIUM or LOW priority for general market commentary and insights."
        )

        decision_functions = get_all_function_schemas()
        response = await self.stateless_chat_with_react_loop(
            user_message="Scan EUR/USD multilayer events for proactive intelligence. Check current price, technical indicators, and news.",
            max_iterations=4,
            custom_functions=decision_functions,
            system_override=proactive_prompt,
        )
        decision = self._extract_proactive_decision(response)
        decision["analysis_summary"] = "\n".join(response.get("reasoning_steps", []))
        
        # Make sure memory knows about this discovery
        if decision.get("should_alert") and decision.get("message") and self.vector_memory:
            self.vector_memory.store_analysis(
                text=decision["message"],
                metadata={"priority": decision.get("priority", "low"), "type": "proactive_insight"}
            )
        return decision

    async def run_periodic_observation(self) -> str:
        """
        Generate a regular 'Market Pulse' summary showing continuous thinking.
        """
        from ..learning.pattern_tracker import PatternTracker
        storage = getattr(self, "storage", None)
        tracker = PatternTracker(storage=storage)
        lessons = await tracker.get_recent_lessons(limit=3)

        # Force fetch current price, recent candles, AND advanced context so the pulse is deeply informative
        current_price = "Unavailable"
        recent_action = "Unavailable"
        advanced_analysis = "No advanced analysis available."
        
        if hasattr(self, "orchestrator") and self.orchestrator:
            try:
                res_price = await self.orchestrator.run_skill("market_data", "get_price")
                if res_price.success and "price" in res_price.data:
                    current_price = f"{res_price.data['price']:.5f}"
                
                res_candles = await self.orchestrator.run_skill("market_data", "get_candles", timeframe="H1", limit=4)
                if res_candles.success and "df" in res_candles.data:
                    df = res_candles.data["df"]
                    recent_action = df[["open", "high", "low", "close"]].tail(4).to_string()
                    
                # Run the full pipeline to inject liquidity and macro context into the pulse
                ctx = await self.orchestrator.run_full_analysis_pipeline(timeframe="H1")
                advanced_analysis = ctx.metadata.get("formatted", "Pipeline executed but yielded no formatted summary.")
            except Exception as e:
                logger.warning(f"Market Pulse: failed to fetch live advanced data: {e}")

        pulse_prompt = (
            "You are EuroScope, an intelligent, persistent EUR/USD AI expert providing your regular 'Market Pulse'.\n"
            "Your goal is to demonstrate continuous analysis, self-learning, and active monitoring.\n\n"
            "## CRITICAL INSTRUCTION:\n"
            "Read the context below carefully. Provide the final output directly without asking for tools.\n\n"
            "--- CURRENT LIVE STATE ---\n"
            f"- Last Known Price: {current_price}\n"
            f"- Recent H1 Action:\n{recent_action}\n\n"
            "--- ADVANCED SKILLS ANALYSIS ---\n"
            f"{advanced_analysis}\n\n"
            "CONTENT GUIDELINES:\n"
            "1. **Market Context**: Brief summary of current price action, momentum, and session context based on *actual live data*.\n"
            "2. **Learning Update**: How does this map to our recent findings or failures? Have we invalidated any prior thesis?\n"
            "3. **Current Focus**: What you are watching right now (e.g., waiting for session open, monitoring a level).\n\n"
            f"RECENT LESSONS LEARNED:\n{lessons}\n\n"
            "Keep the reply concise, professional, and insightful. Use bullet points."
        )

        # Run via simple stateless chat without tools to force output generation
        try:
            response = await self.stateless_chat(
                user_message="Using the REAL-TIME CONDITIONS provided in the system prompt, generate the Market Pulse update directly NOW.",
                system_override=pulse_prompt,
            )
        except Exception as e:
            logger.error(f"Market Pulse LLM generation failed: {e}")
            response = ""
        # Add a fallback just in case the final answer is empty
        if not response.strip():
            response = "Market is currently consolidating. Awaiting clearer direction."
            
        # Log this to memory so it remembers its last pulse
        if self.vector_memory:
             self.vector_memory.store_analysis(
                 text=f"Market Pulse sent: {response}",
                 metadata={"type": "periodic", "category": "market_pulse_log"}
             )
        
        return response

    def _extract_proactive_decision(self, response: dict[str, Any]) -> dict[str, Any]:
        func_result = response.get("function_call_result") or {}
        should_alert = bool(func_result.get("should_alert", False))
        return {
            "should_alert": should_alert,
            "message": func_result.get("message") if should_alert else None,
            "priority": func_result.get("priority") if should_alert else None,
            "reason": func_result.get("reason", "No specific reason"),
        }

    def _get_system_prompt_with_tools(self) -> str:
        try:
            from ..workspace import WorkspaceManager

            ws = WorkspaceManager()
            return ws.build_system_prompt()
        except Exception:
            return SYSTEM_PROMPT

    def _get_react_system_prompt(self) -> str:
        return (
            "You are EuroScope, an AI trading analyst for EUR/USD. Use the strict ReAct "
            "(Reason-Act-Observe) framework. This is a multi-step process.\n\n"
            "## PROTOCOL RULES:\n"
            "1. **REASON**: State what you are thinking and why you need specific data.\n"
            "2. **ACT**: Call ONE OR MORE tools to get that data. Use formal function calls.\n"
            "3. **STOP**: You MUST stop after an 'ACT' block. DO NOT write 'Observation:' or 'Result:'.\n"
            "   The system will provide the Observations following your tool calls.\n"
            "4. **OBSERVE**: You will receive data from the system. Do not hallucinate it.\n"
            "5. **REPEAT**: Continue until you have a complete picture.\n"
            "6. **FINAL**: When finished, start your response with 'FINAL ANALYSIS:' and provide your conclusion.\n\n"
            "## CRITICAL: NEVER HALLUCINATE TOOL RESULTS.\n"
            "If you write 'Observation:' or list data that wasn't provided by the system, you are failing the protocol.\n\n"
            "## AVAILABLE TOOLS:\n"
            "- get_price: Current price and OHLCV data\n"
            "- get_technical_analysis: RSI, MACD, ADX, trend bias\n"
            "- get_fundamental_analysis: Macro data (rates, CPI, GDP)\n"
            "- get_news_sentiment: Recent news and market sentiment\n"
            "- get_patterns: Chart patterns (H&S, Double Top, etc.)\n"
            "- get_risk_assessment: Trade risk and position sizing\n"
            "- get_signals: Active trading signals\n"
            "- get_liquidity: Liquidity pools, order blocks, session sweeps\n"
            "- get_market_shifts: Regime shifts and volatility deviations\n"
            "- get_forecast: AI directional forecast\n\n"
            "## THINKING PROCESS:\n"
            "- You only analyze EUR/USD.\n"
            "- Be surgical: only call tools you actually need for the specific request.\n"
            "- Synthesize all data into a professional, actionable report."
        )

    def _extract_reasoning(self, content: str) -> str:
        """Extract clean reasoning from the response content."""
        # Truncate at tool calls if they are in the text (pseudo-calls)
        clean = content
        if "get_" in content and "(" in content:
            clean = content.split("get_")[0].strip()
        
        # Truncate at ReAct markers if listed sequentially
        for marker in ["ACT:", "**ACT:**", "ACT ", "Observation:", "OBSERVE:", "Result:", "RESULT:", "FINAL ANALYSIS:"]:
            if marker in clean:
                clean = clean.split(marker)[0].strip()

        lowered = clean.lower()
        # Triggers for what constitutes a "thought" worth showing
        triggers = ("reason", "thought", "i need", "let me", "i should", "step ", "analyzing", "planning")
        if any(t in lowered for t in triggers):
            # Clean up Reasoning headers
            for header in ["REASON:", "**REASON:**", "THOUGHT:", "**THOUGHT:**", "PLANNING:", "**PLANNING:**", "ANALYSIS:", "**ANALYSIS:**"]:
                clean = clean.replace(header, "").strip()
            
            # Don't return if it's just a tiny fragment or if it contains final markers
            if len(clean) < 10 or "FINAL" in clean.upper():
                return ""
            return clean
        
        return ""

    def _parse_text_tool_calls(self, text: str) -> list[dict]:
        """Attempt to parse function calls from text when model fails to use API."""
        calls = []
        allowed_names = set(FUNCTION_SCHEMAS.keys())
        skill_enum = self.skill_function_enum
        # Look for code blocks with get_skill()
        pattern = r"(get_[a-z0-9_]+)\((.*?)\)"
        matches = re.finditer(pattern, text)
        for match in matches:
            name = match.group(1)
            # Find schemas to validate name
            if name in allowed_names or (skill_enum and any(s.value == name for s in skill_enum)):
                calls.append({"name": name, "arguments": {}})
        
        # Look for JSON blocks
        json_pattern = r"```json\s*(\{.*?\})\s*```"
        json_matches = re.finditer(json_pattern, text, re.DOTALL)
        for match in json_matches:
            try:
                data = json.loads(match.group(1))
                if data.get("action") == "call_tools" or "tools" in data:
                    tools = data.get("tools", [])
                    for t in tools:
                        if isinstance(t, str):
                            if t in allowed_names:
                                calls.append({"name": t, "arguments": {}})
                        elif isinstance(t, dict) and "name" in t:
                            name = t["name"]
                            if name in allowed_names:
                                calls.append({"name": name, "arguments": t.get("arguments", {})})
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return calls

    def _format_tool_observation(self, tool_name: str, result: dict) -> str:
        if not isinstance(result, dict):
            return str(result)
        if not result.get("success"):
            return f"Error executing {tool_name}: {result.get('error', 'Unknown error')}"

        metadata = result.get("metadata") or {}
        if isinstance(metadata, dict) and metadata.get("formatted"):
            return str(metadata.get("formatted"))

        data = result.get("data", {})
        if tool_name == "get_price":
            return (
                f"Price: {data.get('price')} | Change: {data.get('change')} | "
                f"Range: {data.get('spread_pips')} pips"
            )
        if tool_name == "get_technical_analysis":
            if isinstance(data, dict):
                indicators = data.get("indicators") or {}
                bias = data.get("overall_bias") or data.get("bias")
                rsi = indicators.get("RSI", {}).get("value") if isinstance(indicators, dict) else None
                macd = indicators.get("MACD", {}).get("histogram") if isinstance(indicators, dict) else None
                adx = indicators.get("ADX", {}).get("value") if isinstance(indicators, dict) else None
                return f"RSI: {rsi} | MACD: {macd} | ADX: {adx} | Bias: {bias}"
        if tool_name == "get_news_sentiment":
            if isinstance(data, dict):
                return f"Sentiment: {data.get('sentiment')} | Score: {data.get('score')}"
        if tool_name in ["get_fundamental_analysis", "get_patterns", "get_risk_assessment", "get_signals", "get_forecast"]:
            pass # Fall through to default safe JSON dump

        try:
            # Strip dataframes and extremely long lists to protect context window
            safe_data = {}
            for k, v in data.items():
                if hasattr(v, "empty"): continue
                if isinstance(v, list) and len(v) > 20:
                    safe_data[k] = v[:20] + ["...truncated..."]
                else:
                    safe_data[k] = v
            
            raw = json.dumps(safe_data, default=str)
            if len(raw) > 3000:
                return raw[:3000] + "... [truncated due to length]"
            return raw
        except Exception:
            return str(data)[:3000] + "... [truncated]"

    def _summarize_observations(self, observations: list[str]) -> str:
        return " | ".join(observations)

    async def _force_final_answer(self, messages: list[dict]) -> str:
        messages.append({
            "role": "user",
            "content": "You've reached the maximum reasoning steps. Please provide your best analysis based on the information so far.",
        })
        if self.router:
            reply = await self.router.chat(messages)
            if reply:
                return reply
        if not self.config.api_key:
            return "⚠️ AI features disabled — no API key configured."
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
        return data["choices"][0]["message"]["content"]

    def _calculate_confidence(
        self,
        answer: str,
        tools_used: list[str],
        incomplete: bool = False,
    ) -> float:
        base_confidence = 0.3
        tool_bonus = min(len(tools_used) * 0.15, 0.5)
        lowered = answer.lower()
        quality_indicators = [
            "recommend" in lowered,
            "suggest" in lowered,
            "wait" in lowered,
            "avoid" in lowered,
            any(x in lowered for x in ["bullish", "bearish", "neutral"]),
        ]
        quality_bonus = sum(quality_indicators) * 0.05
        confidence = min(1.0, base_confidence + tool_bonus + quality_bonus)
        if incomplete:
            confidence *= 0.7
        return round(confidence, 2)

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
            data_result = await orchestrator.run_skill(
                "market_data",
                "get_candles",
                context=ctx,
                timeframe=tf,
                count=200,
            )
            if not data_result.success:
                return self._skill_result_payload(data_result)
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
            result = await orchestrator.run_skill("fundamental_analysis", "get_news", context=ctx)
            return self._skill_result_payload(result)

        if tool_name == "get_liquidity":
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
                "liquidity_awareness",
                "analyze",
                context=ctx,
                timeframe=tf
            )
            return self._skill_result_payload(result)

        if tool_name == "get_market_shifts":
            result = await orchestrator.run_skill(
                "deviation_monitor",
                "analyze",
                context=ctx
            )
            return self._skill_result_payload(result)

        if tool_name == "proactive_alert_decision":
            result = await orchestrator.run_skill("fundamental_analysis", "get_calendar", context=ctx)
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
                  market_status: str = "N/A", advanced_context: str = "No advanced data provided.") -> str:
        """Answer a free-form question about EUR/USD."""
        prompt = QUESTION_PROMPT.format(
            current_price=current_price,
            market_status=market_status,
            advanced_context=advanced_context,
            question=question,
        )
        return await self.chat(prompt)

    def clear_history(self, chat_id: int = None):
        """Clear conversation history for a user or all users."""
        if chat_id is not None:
            self._histories.pop(chat_id, None)
        else:
            self._histories.clear()
