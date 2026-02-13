"""
Backtesting Skill — Wraps BacktestEngine for the skills framework.
"""

from ...analytics.backtest_engine import BacktestEngine, BacktestResult
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class BacktestingSkill(BaseSkill):
    name = "backtesting"
    description = "Historical strategy replay and performance measurement"
    emoji = "🔬"
    category = SkillCategory.ANALYTICS
    version = "1.0.0"
    capabilities = ["run", "compare", "format_result", "walk_forward"]

    def __init__(self):
        super().__init__()
        self.engine = BacktestEngine()

    def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "run":
            return self._run(context, **params)
        elif action == "compare":
            return self._compare(context, **params)
        elif action == "format_result":
            return self._format(**params)
        elif action == "walk_forward":
            return self._walk_forward(context, **params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    def _run(self, context: SkillContext, **params) -> SkillResult:
        candles = params.get("candles", [])
        strategy = params.get("strategy_filter")
        lookback = params.get("lookback", 50)
        slippage = params.get("slippage", 0.5)
        commission = params.get("commission", 0.7)
        try:
            result = self.engine.run(candles, strategy_filter=strategy, 
                                     lookback=lookback, 
                                     slippage_pips=slippage, 
                                     commission_pips=commission)
            data = {
                "strategy": result.strategy,
                "total_trades": result.total_trades,
                "wins": result.wins,
                "losses": result.losses,
                "win_rate": result.win_rate,
                "total_pnl": result.total_pnl,
                "avg_pnl": result.avg_pnl,
                "max_drawdown": result.max_drawdown,
                "profit_factor": result.profit_factor,
                "sharpe_ratio": result.sharpe_ratio,
                "bars_tested": result.bars_tested,
                "equity_curve": result.equity_curve,
            }
            return SkillResult(success=True, data=data)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _compare(self, context: SkillContext, **params) -> SkillResult:
        candles = params.get("candles", [])
        strategies = params.get("strategies")
        slippage = params.get("slippage", 0.5)
        commission = params.get("commission", 0.7)
        try:
            results = self.engine.compare_strategies(candles, strategies, 
                                                     slippage=slippage, 
                                                     commission=commission)
            data = {}
            for name, r in results.items():
                data[name] = {
                    "total_trades": r.total_trades,
                    "win_rate": r.win_rate,
                    "total_pnl": r.total_pnl,
                    "profit_factor": r.profit_factor,
                    "sharpe_ratio": r.sharpe_ratio,
                }
            return SkillResult(success=True, data=data)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _walk_forward(self, context: SkillContext, **params) -> SkillResult:
        candles = params.get("candles", [])
        strategy = params.get("strategy")
        window_size = params.get("window_size", 500)
        step_size = params.get("step_size", 100)
        slippage = params.get("slippage", 0.5)
        commission = params.get("commission", 0.7)
        try:
            results = self.engine.walk_forward_analysis(candles, strategy, 
                                                        window_size=window_size, 
                                                        step_size=step_size,
                                                        slippage=slippage,
                                                        commission=commission)
            data = []
            for r in results:
                data.append({
                    "total_trades": r.total_trades,
                    "win_rate": r.win_rate,
                    "total_pnl": r.total_pnl,
                })
            return SkillResult(success=True, data=data)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _format(self, **params) -> SkillResult:
        result = params.get("result")
        if not result:
            return SkillResult(success=False, error="No result to format")
        if isinstance(result, BacktestResult):
            text = BacktestEngine.format_result(result)
        else:
            text = str(result)
        return SkillResult(success=True, data=text)
