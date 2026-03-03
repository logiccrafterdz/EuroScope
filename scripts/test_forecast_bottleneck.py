import asyncio
import os
import sys
import time
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
logging.basicConfig(level=logging.INFO)

from euroscope.config import Config
from euroscope.bot.telegram_bot import EuroScopeBot
from dotenv import load_dotenv

load_dotenv()

async def debug_forecast():
    config = Config.from_env()
    bot = EuroScopeBot(config)
    
    # We will manually step through generate_forecast logic to see the bottleneck
    print("[1/5] Starting Orchestrator...", flush=True)
    t0 = time.time()
    ctx = await bot.orchestrator.run_full_analysis_pipeline()
    t_orchestrator = time.time() - t0
    print(f"Orchestrator pipeline took: {t_orchestrator:.2f}s", flush=True)

    t0 = time.time()
    price_info = ctx.get_result("market_data")["data"] if ctx.get_result("market_data") else {}
    ta_results = ctx.get_result("technical_analysis")["data"] if ctx.get_result("technical_analysis") else {}
    news_text = "MOCK NEWS"
    
    learning = await bot.forecaster._build_learning_context(
        price_info=price_info,
        ta_results=ta_results,
        timeframe="H1",
    )
    t_learning = time.time() - t0
    print(f"[2/5] Build Learning Context took: {t_learning:.2f}s", flush=True)

    ta_timeframe = "H1"
    ta_str = bot.forecaster._format_ta_for_prompt(ta_results, ta_timeframe)
    patterns_str = bot.forecaster._format_patterns_for_prompt(ta_results.get("patterns", []))
    levels_str = bot.forecaster._format_levels_for_prompt(
        ta_results.get("levels", {}), 
        ta_results.get("fibonacci", {})
    )

    t0 = time.time()
    print("[3/5] Starting Agent LLM forecast call...", flush=True)
    try:
        forecast_text = await asyncio.wait_for(
            bot.agent.forecast(
                price_data="MOCK PRICE",
                technical_summary=ta_str,
                patterns=patterns_str,
                levels=levels_str,
                news=news_text,
                strategy_signal="MOCK SIGNAL",
                prediction_history=learning,
                timeframe="H1",
            ),
            timeout=30.0
        )
        t_forecast = time.time() - t0
        print(f"Agent LLM forecast took: {t_forecast:.2f}s", flush=True)
    except Exception as e:
        print(f"Agent LLM Failed: {e}", flush=True)

    print("--- Done ---")

if __name__ == "__main__":
    asyncio.run(debug_forecast())
