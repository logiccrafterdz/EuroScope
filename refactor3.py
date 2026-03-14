import re

filepath = r"c:\Users\Hp\Desktop\EuroScope\euroscope\automation\cron.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Replace the redundant run_skill("trading_strategy") in auto_trade_task
old_block = """                # 1. Run the full analytical pipeline
                ctx = await orchestrator.run_full_analysis_pipeline(timeframe="H1")
                
                # 2. Re-evaluate strategy with fresh context
                strat_res = await orchestrator.run_skill("trading_strategy", "detect_signal", context=ctx)
                if not strat_res.success:
                    return
                    
                signal_data = strat_res.data
                direction = signal_data.get("direction", "WAIT")
                confidence = signal_data.get("confidence", 0)"""

new_block = """                # 1. Run the full analytical pipeline
                ctx = await orchestrator.run_full_analysis_pipeline(timeframe="H1")
                
                # 2. Extract signal directly from the pipeline context
                signal_data = ctx.signals if isinstance(ctx.signals, dict) else {}
                direction = signal_data.get("direction", "WAIT")
                confidence = signal_data.get("confidence", 0)"""

content = content.replace(old_block, new_block)

# Fix the bug identified in AC-2:
# auto_trader calls orchestrator.run_full_analysis_pipeline(timeframe="H1") 
# but the method expects **market_params (a dict). A kwarg is correct in this context, 
# although the pipeline parses `market_params.get("timeframe")` so kwargs do work if unpacked.
# But let's be explicit and match the intended usage `market_params={"timeframe": "H1"}` if needed,
# Actually, the signature `def run_full_analysis_pipeline(self, context=None, **market_params):` 
# means `timeframe="H1"` is passed into `market_params` as `{"timeframe": "H1"}`. 
# This works fine in Python. The audit report was slightly mistaken about the severity of `timeframe="H1"`. 
# However, `cron.py`'s manual `trading_strategy` call *was* a duplication of the pipeline's built-in step.

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("cron.py updated.")
