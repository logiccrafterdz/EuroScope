import logging

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult

logger = logging.getLogger("euroscope.skills.portfolio_context")


class PortfolioContextSkill(BaseSkill):
    name = "portfolio_context"
    description = "Tracks portfolio health, margin utilization, daily drawdown, and active exposure"
    emoji = "💼"
    category = SkillCategory.SYSTEM
    version = "1.0.0"
    capabilities = ["assess_health", "get_exposure"]

    def __init__(self, storage=None, config=None):
        super().__init__()
        self.storage = storage
        self.config = config

    def set_storage(self, storage):
        self.storage = storage
        
    def set_config(self, config):
        self.config = config

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "assess_health":
            return await self._assess_health(context, **params)
        elif action == "get_exposure":
            return await self._get_exposure(context, **params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _assess_health(self, context: SkillContext, **params) -> SkillResult:
        if not self.storage:
            return SkillResult(success=False, error="Storage dependency not injected")
            
        try:
            # Get daily stats
            stats = await self.storage.get_trade_journal_stats()
            daily_pnl = stats.get("total_pnl", 0.0)
            
            # Fetch max daily drawdown limit from config (default to -50 pips if not set)
            max_daily_drawdown = -50.0
            if self.config:
                max_daily_drawdown = getattr(self.config.risk, "max_daily_drawdown_pips", -50.0)
            
            # Evaluate health
            halt_recommended = False
            health_status = "Healthy"
            
            if daily_pnl <= max_daily_drawdown:
                halt_recommended = True
                health_status = "Daily Drawdown Exceeded"
                
            data = {
                "daily_pnl_pips": daily_pnl,
                "max_drawdown_pips": max_daily_drawdown,
                "halt_recommended": halt_recommended,
                "status": health_status
            }
            
            # Inject into context for risk_management to read
            context.metadata["portfolio_health"] = data
            
            formatted = f"💼 *Portfolio Health*\nStatus: {health_status}\nDaily PnL: {daily_pnl:.1f} pips\nLimit: {max_daily_drawdown} pips"
            
            return SkillResult(success=True, data=data, metadata={"formatted": formatted})
        except Exception as e:
            logger.error(f"Failed to assess portfolio health: {e}")
            return SkillResult(success=False, error=str(e))

    async def _get_exposure(self, context: SkillContext, **params) -> SkillResult:
        if not self.storage:
            return SkillResult(success=False, error="Storage dependency not injected")
            
        try:
            # Fetch active trades
            active_trades = await self.storage.get_trade_journal(status="open")
            
            total_long = 0
            total_short = 0
            count = len(active_trades)
            
            for trade in active_trades:
                # Mocking position size logic as 1 unit per trade if sizing not present
                size = trade.get("size", 1.0)
                if trade.get("direction") == "BUY":
                    total_long += size
                elif trade.get("direction") == "SELL":
                    total_short += size
                    
            net_exposure = total_long - total_short
            
            data = {
                "active_trades_count": count,
                "total_long": total_long,
                "total_short": total_short,
                "net_exposure": net_exposure,
                "currency_pair": "EUR/USD"
            }
            
            # Inject into context
            context.metadata["portfolio_exposure"] = data
            
            formatted = f"📊 *Portfolio Exposure*\nOpen Trades: {count}\nNet Exposure: {net_exposure:.2f} (Long: {total_long}, Short: {total_short})"
            
            return SkillResult(success=True, data=data, metadata={"formatted": formatted})
        except Exception as e:
            logger.error(f"Failed to get portfolio exposure: {e}")
            return SkillResult(success=False, error=str(e))
