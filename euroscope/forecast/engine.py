"""
AI Forecasting Engine

Combines all data sources to generate directional forecasts
and tracks accuracy over time.
"""

import logging
import re
import json
from typing import Optional

from ..brain.agent import Agent
from ..brain.memory import Memory
from ..brain.orchestrator import Orchestrator, SkillContext

logger = logging.getLogger("euroscope.forecast")


class Forecaster:
    """Generates AI-powered EUR/USD forecasts with self-learning."""

    def __init__(self, agent: Agent, memory: Memory, orchestrator: Orchestrator, pattern_tracker=None):
        self.agent = agent
        self.memory = memory
        self.orchestrator = orchestrator
        self.pattern_tracker = pattern_tracker

    async def generate_forecast(self, timeframe: str = "24 hours") -> dict:
        """Generate a comprehensive AI forecast for EUR/USD."""

        # Use Orchestrator to gather all necessary data via Skills
        ctx = await self.orchestrator.run_full_analysis_pipeline()

        # Explicitly fetch LIVE price (pipeline only runs get_candles which gives historical OHLC)
        try:
            price_res = await self.orchestrator.run_skill("market_data", "get_price", context=ctx)
            if price_res.success and isinstance(price_res.data, dict):
                price_info = price_res.data
            else:
                price_info = ctx.market_data.get("price", {})
        except Exception as e:
            logger.warning(f"Forecast: Failed to fetch live price: {e}")
            price_info = ctx.market_data.get("price", {})

        # Extract data from context
        ta_results = ctx.get_result("technical_analysis")["data"] if ctx.get_result("technical_analysis") else {}

        # The pipeline only runs get_macro (interest rates, CPI), NOT get_news.
        # We must explicitly fetch news so the LLM always has geopolitical context.
        news_text = "No news available"
        try:
            news_res = await self.orchestrator.run_skill("fundamental_analysis", "get_news", context=ctx)
            if news_res.success and news_res.metadata and news_res.metadata.get("formatted"):
                news_text = news_res.metadata["formatted"]
            elif news_res.success and news_res.data:
                # Fallback: format articles if formatted text is missing
                articles = news_res.data if isinstance(news_res.data, list) else []
                if articles:
                    news_text = "\n".join(
                        f"- {a.get('title', 'Untitled')} ({a.get('source', '?')})"
                        for a in articles[:10]
                    )
        except Exception as e:
            logger.warning(f"Forecast: Failed to fetch news: {e}")

        # Also include macro context if available
        macro_result = ctx.get_result("fundamental_analysis")
        macro_text = ""
        if macro_result and macro_result.get("metadata", {}).get("formatted"):
            macro_text = macro_result["metadata"]["formatted"]

        # Combine news + macro for comprehensive fundamental context
        if macro_text and news_text != "No news available":
            news_text = f"{news_text}\n\n--- MACRO CONTEXT ---\n{macro_text}"
        elif macro_text and news_text == "No news available":
            news_text = macro_text
        signal_data = {}
        strat_entry = ctx.get_result("trading_strategy")
        if strat_entry and isinstance(strat_entry.get("data"), dict):
            signal_data = strat_entry.get("data") or {}
        elif isinstance(ctx.signals, dict) and ctx.signals:
            signal_data = ctx.signals
        strategy_signal = "No strategy signal available."
        if signal_data:
            direction = signal_data.get("direction", "NEUTRAL")
            strategy = signal_data.get("strategy", "unknown")
            confidence = signal_data.get("confidence", 0)
            regime = signal_data.get("regime") or ""
            reasoning = signal_data.get("reasoning") or ""
            entry_price = signal_data.get("entry_price")
            parts = [
                f"Direction: {direction}",
                f"Strategy: {strategy}",
                f"Confidence: {confidence}",
            ]
            if regime:
                parts.append(f"Regime: {regime}")
            if entry_price not in (None, 0, 0.0):
                parts.append(f"Entry: {entry_price}")
            if reasoning:
                parts.append(f"Reasoning: {reasoning}")
            strategy_signal = "\n".join(parts)

        # Learning context
        learning = await self._build_learning_context(
            price_info=price_info,
            ta_results=ta_results,
            timeframe=timeframe,
        )

        # Build data strings for the AI
        if isinstance(price_info, dict) and price_info:
            price_str = "\n".join(f"  {k}: {v}" for k, v in price_info.items())
        elif hasattr(price_info, 'empty') and not price_info.empty:
            price_str = price_info.head(20).to_string()
        else:
            price_str = "N/A"
        
        # Use existing formatting helpers or results from skills
        ta_timeframe = ta_results.get("timeframe") or price_info.get("timeframe") or "H1"
        ta_str = self._format_ta_for_prompt(ta_results, ta_timeframe)
        
        patterns_str = self._format_patterns_for_prompt(ta_results.get("patterns", []))
        levels_str = self._format_levels_for_prompt(
            ta_results.get("levels", {}), 
            ta_results.get("fibonacci", {})
        )

        # Generate AI forecast (Ensemble)
        forecast_texts_raw = await self.agent.forecast_ensemble(
            price_data=price_str,
            technical_summary=ta_str,
            patterns=patterns_str,
            levels=levels_str,
            news=news_text,
            strategy_signal=strategy_signal,
            prediction_history=learning,
            timeframe=timeframe,
        )

        if not forecast_texts_raw:
            # Fallback if both fail
            parsed_json = self._parse_forecast("❌ Ensemble forecasting failed.")
            forecast_text = "❌ Ensemble forecasting failed."
        else:
            # Process all responses
            all_parsed = [self._parse_forecast(text) for text in forecast_texts_raw]
            
            # Aggregate Logic
            bullish_conf = sum(p.get("confidence", 50.0) for p in all_parsed if p.get("direction") == "BULLISH")
            bearish_conf = sum(p.get("confidence", 50.0) for p in all_parsed if p.get("direction") == "BEARISH")
            
            if bullish_conf > bearish_conf:
                final_dir = "BULLISH"
                final_conf = bullish_conf / len(all_parsed)
            elif bearish_conf > bullish_conf:
                final_dir = "BEARISH"
                final_conf = bearish_conf / len(all_parsed)
            else:
                final_dir = "NEUTRAL"
                final_conf = sum(p.get("confidence", 50.0) for p in all_parsed) / len(all_parsed) if all_parsed else 50.0

            # Build a unified JSON structure
            primary_res = all_parsed[0]
            parsed_json = {
                "direction": final_dir,
                "confidence": round(final_conf, 1),
                "core_signal": f"[Ensemble Consensus: {len(all_parsed)} models] {primary_res.get('core_signal', '')}",
                "scenario_a": primary_res.get("scenario_a", ""),
                "scenario_b": primary_res.get("scenario_b", ""),
                "fundamental_alignment": primary_res.get("fundamental_alignment", ""),
                "key_levels": primary_res.get("key_levels", "")
            }
            forecast_text = forecast_texts_raw[0]

        direction = parsed_json.get("direction", "NEUTRAL")
        confidence = parsed_json.get("confidence", 50.0)

        # Build readable markdown from JSON for Telegram
        telegram_output = self._build_telegram_output(parsed_json)

        # Record prediction for accuracy tracking
        pred_id = None
        if direction:
            pred_id = await self.memory.record_prediction(
                direction=direction,
                confidence=confidence,
                reasoning=forecast_text,
                target_price=price_info.get("price"),
                timeframe=timeframe,
            )
            if self.agent.vector_memory:
                # Use the generated output as the text to store
                self.agent.vector_memory.store_analysis(
                    telegram_output,
                    metadata={
                        "timeframe": timeframe,
                        "direction": direction,
                        "confidence": confidence,
                    },
                )

        return {
            "text": telegram_output,  # Send the formatted Markdown to Telegram
            "raw_json": parsed_json,  # Keep the raw JSON for programmatic use
            "direction": direction,
            "confidence": confidence,
            "prediction_id": pred_id,
            "price": price_info.get("price"),
        }

    async def _build_learning_context(self, price_info: dict, ta_results: dict, timeframe: str) -> str:
        parts = [await self.memory.get_learning_context()]

        patterns = ta_results.get("patterns", []) if ta_results else []
        if self.pattern_tracker and patterns:
            rates = await self.pattern_tracker.get_success_rates()
            tf = ta_results.get("timeframe") or price_info.get("timeframe") or "H1"
            lines = []
            for p in patterns:
                name = p.get("name") or p.get("pattern")
                key = f"{name}_{tf}"
                entry = rates.get(key)
                if entry:
                    lines.append(
                        f"- {entry['pattern']} ({entry['timeframe']}): {entry['success_rate']}% "
                        f"({entry['successes']}/{entry['total']})"
                    )
            if lines:
                parts.append("Pattern performance for similar setups:\n" + "\n".join(lines))

        if self.agent.vector_memory:
            bias = ta_results.get("indicators", {}).get("overall_bias", "")
            context_seed = f"EUR/USD price {price_info.get('price')} bias {bias} timeframe {timeframe}"
            historical = self.agent.vector_memory.get_relevant_context(context_seed)
            if historical:
                parts.append(historical)

        return "\n\n".join(p for p in parts if p)

    def _parse_forecast(self, text: str) -> dict:
        """Extract structured JSON from the AI forecast text."""
        try:
            # 1. Strip potential markdown code blocks like ```json ... ```
            clean_text = text.strip()
            if clean_text.startswith("```"):
                # Remove first line of code block (e.g. ```json)
                clean_text = "\n".join(clean_text.split("\n")[1:])
            if clean_text.endswith("```"):
                # Remove last line
                clean_text = "\n".join(clean_text.split("\n")[:-1])
            clean_text = clean_text.strip()
            
            # 2. Extract the JSON object intelligently to avoid text outside braces
            start_idx = clean_text.find('{')
            end_idx = clean_text.rfind('}')
            
            if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
                raise json.JSONDecodeError("No JSON object found in text", clean_text, 0)
                
            json_str = clean_text[start_idx:end_idx+1]
            parsed = json.loads(json_str)
            
            # Normalize enum values
            direction = str(parsed.get("direction", "NEUTRAL")).upper()
            if direction not in ("BULLISH", "BEARISH", "NEUTRAL"):
                direction = "NEUTRAL"
            parsed["direction"] = direction
            
            # Normalize confidence
            try:
                conf = float(parsed.get("confidence", 50.0))
                parsed["confidence"] = max(0.0, min(100.0, conf))
            except (ValueError, TypeError):
                parsed["confidence"] = 50.0
                
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON forecast: {e}\nRaw Text: {text}")
            # Fallback
            return {
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "core_signal": "Failed to parse AI response.",
                "scenario_a": "",
                "scenario_b": "",
                "fundamental_alignment": "",
                "key_levels": ""
            }

    def _build_telegram_output(self, parsed: dict) -> str:
        """Constructs a clean Markdown string from the structured JSON."""
        direction = parsed.get("direction", "NEUTRAL")
        conf = parsed.get("confidence", 0)
        
        icon = "🟢" if direction == "BULLISH" else "🔴" if direction == "BEARISH" else "⚪"
        
        parts = [
            f"{icon} **AI Bias:** {direction}",
            f"🎯 **Conviction:** {conf}%",
            "",
            f"**Core Signal:**\n{parsed.get('core_signal', 'N/A')}",
            "",
            "📈 **Primary Scenario (A):**",
            parsed.get('scenario_a', 'N/A'),
            "",
            "📉 **Alternative Scenario (B):**",
            parsed.get('scenario_b', 'N/A'),
            "",
            "📰 **Fundamental Alignment:**",
            parsed.get('fundamental_alignment', 'N/A'),
            "",
            "🧱 **Key Levels:**",
            parsed.get('key_levels', 'N/A')
        ]
        return "\n".join(parts)

    @staticmethod
    def _format_ta_for_prompt(ta: dict, tf: str) -> str:
        if "error" in ta:
            return f"{tf}: {ta['error']}"
        if not ta.get("indicators"):
            return f"{tf}: No data"
        ind = ta["indicators"]
        return (
            f"\n{tf} Timeframe:"
            f"\n  RSI: {ind.get('RSI', {}).get('value', 'N/A')} ({ind.get('RSI', {}).get('signal', 'N/A')})"
            f"\n  MACD: {ind.get('MACD', {}).get('signal_text', 'N/A')}"
            f"\n  Trend: {ind.get('EMA', {}).get('trend', 'N/A')}"
            f"\n  ADX: {ind.get('ADX', {}).get('value', 'N/A')} ({ind.get('ADX', {}).get('strength', 'N/A')})"
            f"\n  Overall: {ta.get('overall_bias', 'N/A')}"
        )

    @staticmethod
    def _format_patterns_for_prompt(patterns: list) -> str:
        if not patterns:
            return "No patterns detected"
        return "\n".join(f"  - {p['pattern']} ({p['type']}, confidence: {p.get('confidence', '?')}%)" for p in patterns)

    @staticmethod
    def _format_levels_for_prompt(sr: dict, fib: dict) -> str:
        parts = []
        if sr.get("support"):
            parts.append(f"Support: {', '.join(str(s) for s in sr['support'][:3])}")
        if sr.get("resistance"):
            parts.append(f"Resistance: {', '.join(str(r) for r in sr['resistance'][:3])}")
        if fib.get("levels"):
            parts.append(f"Fibonacci ({fib.get('direction', 'N/A')}): 38.2% = {fib['levels'].get('38%', 'N/A')}, 50% = {fib['levels'].get('50%', 'N/A')}, 61.8% = {fib['levels'].get('61%', 'N/A')}")
        return "\n".join(parts) if parts else "No level data"
