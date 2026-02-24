import asyncio
import logging
import sys
from euroscope.config import Config
from euroscope.brain.agent import Agent
from euroscope.brain.orchestrator import Orchestrator

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def test_ask():
    config = Config.from_env()
    orchestrator = Orchestrator()
    agent = Agent(config=config.llm, orchestrator=orchestrator)
    
    print("\n[+] Running Full Analysis Pipeline to generate advanced_context...")
    ctx = await orchestrator.run_full_analysis_pipeline(timeframe="H1")
    advanced_context = ctx.metadata.get("formatted", "No advanced data")
    
    print("\n[+] Advanced Context Generated. Asking Agent...")
    print("-" * 50)
    
    question = "Is the current liquidity suggesting we are in a ranging market or a breakout scenario?"
    answer = await agent.ask(
        question=question,
        current_price="1.0500",
        market_status="OPEN",
        advanced_context=advanced_context
    )
    
    print("\n[RESULT]")
    print(answer)

if __name__ == "__main__":
    asyncio.run(test_ask())
