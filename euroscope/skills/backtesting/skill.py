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
    capabilities = ["run", "run_backtest", "compare", "format_result", "walk_forward"]

    def __init__(self, price_provider=None):
        super().__init__()
        self._provider = price_provider
        self.engine = BacktestEngine()

    def set_price_provider(self, provider):
        """Standard setter for auto-injection."""
        self._provider = provider

    def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action in ("run", "run_backtest"):
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
        days = params.get("days", 30)

        # Fetch candles if not provided (V3 automation)
        if not candles and self._provider:
            # Approx 24 H1 candles per day
            candles = self._provider.get_candles("H1", count=days * 24)

        if not candles:
            return SkillResult(success=False, error="No historical data available for backtest")

        strategy = params.get("strategy_filter")
        lookback = params.get("lookback", 50)
        slippage = params.get("slippage", 0.5)
        commission = params.get("commission", 0.7)
        try:
            if not strategy:
                # Run comparison of all strategies
                results = self.engine.compare_strategies(candles, slippage=slippage, commission=commission)
                formatted = self.engine.format_comparison(results)
                return SkillResult(success=True, data={k: v.__dict__ for k, v in results.items()}, metadata={"formatted": formatted})

            result = self.engine.run(candles, strategy_filter=strategy, 
                                     lookback=lookback, 
                                     slippage_pips=slippage, 
                                     commission_pips=commission)
            formatted = self.engine.format_result(result)
            return SkillResult(success=True, data=result.__dict__, metadata={"formatted": formatted})
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
