import asyncio
import logging
import sys
from euroscope.config import Config
from euroscope.automation.cron import CronScheduler
from euroscope.brain.orchestrator import Orchestrator
from euroscope.skills.base import SkillContext

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("test_auto_trader")

class MockPriceProvider:
    def __init__(self, price):
        self.price = price
        
    async def get_price(self):
        return {"price": self.price}

class MockBot:
    def __init__(self, config, orchestrator):
        self.config = config
        self.orchestrator = orchestrator
        self.price_provider = MockPriceProvider(1.0500)

async def test_trader_loop():
    config = Config.from_env()
    orchestrator = Orchestrator()
    bot = MockBot(config=config, orchestrator=orchestrator)
    cron = CronScheduler(bot=bot)
    
    # Disable Quiet Hours for testing
    config.proactive_quiet_hours = None
    config.proactive_disable_weekends = False
    
    print(f"\n[!] Available Cron Tasks: {list(cron.tasks.keys())}")
    
    print("\n[+] Injecting Mock Open Trade (Buy @ 1.0500)...")
    signal_executor = orchestrator.registry.get("signal_executor")
    if signal_executor:
        ctx = SkillContext()
        ctx.signals = {"direction": "BUY"}
        ctx.metadata = {"execution_mode": "paper"}
        ctx.risk = {
            "entry_price": 1.0500,
            "stop_loss": 1.0450,
            "take_profit": 1.0600
        }
        
        res_open = await signal_executor.safe_execute(
            ctx, "open_trade",
            direction="BUY",
            confidence=0.8
        )
        print(f"Open Trade Result: {res_open}")
        
        # Verify it was opened
        res = await signal_executor.safe_execute(ctx, "list_trades")
        if res.data:
            trade_id = res.data[0].get("trade_id") or res.data[0].get("id")
            print(f"Mock trade created: {trade_id}")
            print(f"Trade details: {res.data[0]}")
        else:
            print("Failed to open mock trade. Stopping test.")
            return
        
    print("\n[+] Triggering Trade Monitor Task (Simulate price rising to 1.0525)...")
    bot.price_provider.price = 1.0525
    
    trade_monitor_task = cron.tasks.get("trade_monitor")
    if trade_monitor_task:
        await trade_monitor_task.callback()
        
        # Verify if trailing stop was updated 
        # (1.0500 + 20 pips logic should kick in because 25 pips in profit)
        res = await signal_executor.safe_execute(ctx, "list_trades")
        trade = res.data[0]
        print(f"Trade after monitor run: SL={trade['stop_loss']} (Was 1.0450)")
    else:
        print("Warning: 'trade_monitor' task not found in scheduler.")
        
    print("\n[+] Triggering Trade Monitor Task (Simulate price dropping to hit new SL)...")
    bot.price_provider.price = 1.0490 # Hits old SL but not new SL if trailing failed
    if trade_monitor_task:
        await trade_monitor_task.callback()
        
        res = await signal_executor.safe_execute(ctx, "list_trades")
        open_trades = [t for t in res.data if str(t.get('status', '')).upper() == 'OPEN']
        print(f"Open trades remaining: {len(open_trades)}")

if __name__ == "__main__":
    asyncio.run(test_trader_loop())
