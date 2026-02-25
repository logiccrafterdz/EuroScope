import ast

class MethodRemover(ast.NodeTransformer):
    def __init__(self, methods_to_drop):
        super().__init__()
        self.methods_to_drop = methods_to_drop

    def visit_FunctionDef(self, node):
        if node.name in self.methods_to_drop:
            return None
        return self.generic_visit(node)
        
    def visit_AsyncFunctionDef(self, node):
        if node.name in self.methods_to_drop:
            return None
        return self.generic_visit(node)

methods_to_remove = [
    "cmd_settings", "cmd_alert", "cmd_menu", "cmd_price", "cmd_analysis", 
    "cmd_smart_analysis", "cmd_comprehensive_analysis", "cmd_quick_analysis", 
    "cmd_chart", "cmd_patterns", "cmd_levels", "cmd_signals", "cmd_news", 
    "cmd_calendar", "cmd_forecast", "cmd_report", "cmd_accuracy", "cmd_macro", 
    "cmd_daily_summary", "cmd_backtest", "cmd_strategy", "cmd_risk", "cmd_trades", 
    "cmd_performance", "cmd_ask", "cmd_daily_briefing", "cmd_system_evolution", 
    "handle_message", "callback_handler", "_bot_send_and_handle"
]

with open("euroscope/bot/telegram_bot.py", "r", encoding="utf-8") as f:
    source = f.read()

tree = ast.parse(source)
remover = MethodRemover(methods_to_remove)
new_tree = remover.visit(tree)

with open("euroscope/bot/telegram_bot.py", "w", encoding="utf-8") as f:
    f.write(ast.unparse(new_tree))

print("Cleaned!")
