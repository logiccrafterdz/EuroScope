import asyncio
import logging
import os
import sys

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from euroscope.config import Config
from euroscope.utils.logger import setup_structured_logging
from euroscope.container import ServiceContainer, set_container

logger = logging.getLogger("euroscope.simulation")

async def main():
    print("🚀 EuroScope Full System Simulation Starting...")
    
    # Setup App
    config = Config.from_env()
    setup_structured_logging(config.log_level)
    
    container = ServiceContainer(config)
    
    # Needs async initialize for some modules
    if hasattr(container, "initialize") and callable(getattr(container, "initialize")):
        await container.initialize()
    
    set_container(container)
    
    # Access key components natively
    orchestrator = container.orchestrator
    
    print("\n--- PHASE 1: Forced Conflict Deliberation Mocking ---")
    
    # We will invoke the ConflictArbiter directly with a highly conflicting Context
    from euroscope.skills.base import SkillContext
    
    mock_context = SkillContext()
    mock_context.metadata["regime"] = "trending"
    mock_context.metadata["session_regime"] = "overlap"
    
    # High conflict signals (Technical says BUY, Fundamental says SELL)
    mock_context.metadata["technical_bias"] = "BULLISH"
    mock_context.metadata["fundamental_bias"] = "BEARISH"
    mock_context.metadata["liquidity_signal"] = "BEARISH"
    mock_context.metadata["pattern_signal"] = "BULLISH"
    
    print("🕵️ Triggering Conflict Arbiter with Technical=BULLISH vs Fundamental=BEARISH...")
    resolution = await orchestrator.conflict_arbiter.resolve(mock_context)
    
    print(f"⚖️ Final Verdict: {resolution.get('final_direction')} (Confidence: {resolution.get('confidence'):.2f})")
    print(f"📖 Reasoning: {resolution.get('reasoning')}")
    print(f"🔎 Committee Notes: {resolution.get('committee_notes', 'No notes found')}")
    
    print("\n--- PHASE 2: Background Counterfactual Engine & Data Flow ---")
    
    print("📈 Creating a dummy trade and closing it instantly...")
    from euroscope.trading.signal_executor import SignalExecutor
    from euroscope.trading.execution_simulator import ExecutionSimulator
    
    signal_executor = SignalExecutor(
        storage=container.storage,
        broker=container.broker,
        risk_manager=container.risk_manager if hasattr(container, "risk_manager") else None,
        execution_sim=ExecutionSimulator()
    )
    
    trade_id = await signal_executor.open_signal(
        direction="BUY",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        strategy="manual_test"
    )
    
    if trade_id > 0:
        print(f"✔️ Trade opened successfully with ID {trade_id}")
        await asyncio.sleep(1) # simulate slight delay
        close_res = await signal_executor.close_signal(trade_id, 1.0960, reason="stop_loss")
        print(f"✔️ Trade closed: PnL {close_res.get('pnl_pips')} pips.")
    else:
        print("❌ Failed to open mock trade.")
        
    print("\n--- PHASE 3: Sentiment Graph Construction ---")
    
    from euroscope.data.sentiment_graph import NarrativeGraph
    print("🕸️ Injecting Mock News into Sentiment Graph...")
    graph = NarrativeGraph()
    mock_relations = [
        {"source": "FED", "target": "USD", "relation": "strengthens", "weight": 0.8},
        {"source": "NFP", "target": "FED", "relation": "forces_hike", "weight": 0.6},
        {"source": "ECB", "target": "EUR", "relation": "weakens", "weight": 0.4}
    ]
    graph.update_from_news(mock_relations)
    narratives = graph.get_central_narratives(top_n=3)
    print(narratives)
    
    # Wait for background tasks (like CounterfactualEngine) to wrap up output
    print("⏳ Waiting 3 seconds for background asyncio tasks to complete...")
    await asyncio.sleep(3)

    print("\n🎉 Full System Simulation Complete. Shutting down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
