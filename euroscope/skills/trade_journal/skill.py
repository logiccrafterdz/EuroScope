"""Trade Journal Skill — Full context trade logging and analysis."""

import logging
import json
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult
from ...data.storage import Storage

logger = logging.getLogger("euroscope.skills.trade_journal")

class TradeJournalSkill(BaseSkill):
    """
    Records trades with full market context (indicators, patterns, regime)
    and provides aggregate performance analytics per strategy.
    """

    name = "trade_journal"
    description = "Full-context trade logging and performance analysis"
    emoji = "📓"
    category = SkillCategory.ANALYTICS
    version = "1.0.0"
    capabilities = ["log_trade", "close_trade", "get_journal", "get_stats"]

    def __init__(self):
        super().__init__()
        self.storage = None

    def set_storage(self, storage):
        """Inject shared storage."""
        self.storage = storage

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "log_trade":
            return await self._log_trade(context, **params)
        elif action == "close_trade":
            return await self._close_trade(**params)
        elif action == "get_journal":
            return await self._get_journal(**params)
        elif action == "get_stats":
            return await self._get_stats(**params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _log_trade(self, context: SkillContext, **params) -> SkillResult:
        """Log a new trade with full context snapshot."""
        try:
            # Enrich from context if available
            indicators = params.get("indicators") or context.analysis.get("indicators", {})
            patterns = params.get("patterns") or context.analysis.get("patterns", [])
            causal_chain = params.get("causal_chain") or context.metadata.get("causal_chain")

            trade_id = await self.storage.save_trade_journal(
                direction=params.get("direction", "BUY"),
                entry_price=params.get("entry_price", 0.0),
                stop_loss=params.get("stop_loss", 0.0),
                take_profit=params.get("take_profit", 0.0),
                strategy=params.get("strategy", ""),
                timeframe=params.get("timeframe", "H1"),
                regime=params.get("regime", ""),
                confidence=params.get("confidence", 0.0),
                indicators=indicators,
                patterns=patterns if isinstance(patterns, list) else [],
                reasoning=params.get("reasoning", ""),
                causal_chain=causal_chain,
            )
            return SkillResult(
                success=True,
                data={"trade_id": trade_id},
                metadata={"formatted": f"📓 Trade #{trade_id} logged successfully."},
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _close_trade(self, **params) -> SkillResult:
        """Close a trade with outcome and extract learning insights."""
        try:
            trade_id = params["trade_id"]
            exit_price = params["exit_price"]
            pnl_pips = params["pnl_pips"]
            is_win = params.get("is_win", pnl_pips > 0)

            # Phase 3B: Continuous Learning Loop
            trade_data = await self.storage.get_trade_with_causal(trade_id)
            if trade_data:
                from ...learning.post_trade_analyzer import PostTradeAnalyzer
                analyzer = PostTradeAnalyzer()
                
                # Market context for analyzer (partially from recorded snapshots)
                try:
                    raw_ind = trade_data.get("indicators_snapshot", "{}")
                    indicators = json.loads(raw_ind) if isinstance(raw_ind, str) else (raw_ind or {})
                except (json.JSONDecodeError, TypeError):
                    indicators = {}
                
                # Handle potential string causal_chain
                causal = trade_data.get("causal_chain")
                if isinstance(causal, str):
                    try:
                        causal = json.loads(causal)
                    except:
                        causal = {}
                elif not isinstance(causal, dict):
                    causal = {}

                market_context = {
                    "regime": trade_data.get("regime"),
                    "liquidity_aligned": causal.get("liquidity_aligned", False),
                    "data_quality": causal.get("data_quality", "unknown"),
                    "indicators": indicators
                }
                
                insight = analyzer.analyze_trade_outcome(trade_data, market_context)
                await self.storage.save_learning_insight(
                    trade_id=str(trade_id),
                    accuracy=insight.accuracy,
                    factors=insight.key_factors,
                    recommendations=insight.recommendations
                )
                logger.info(f"Learning insight saved for trade #{trade_id}: {insight.key_factors}")

                # Task 3.3: Store regime snapshot in VectorMemory
                try:
                    from ...container import get_container
                    container = get_container()
                    if container and hasattr(container, "vector_memory") and container.vector_memory:
                        state = {
                            "adx": indicators.get("adx"),
                            "rsi": indicators.get("rsi"),
                            "macd": indicators.get("macd", {}).get("histogram", 0) if isinstance(indicators.get("macd"), dict) else indicators.get("macd"),
                            "trend": trade_data.get("regime"),
                            "volatility": "high" if isinstance(indicators.get("atr"), dict) and indicators["atr"].get("value", 0) > 0.0020 else "low",
                            "macro_bias": "neutral"
                        }
                        outcome = "WIN" if is_win else "LOSS"
                        container.vector_memory.store_regime_snapshot(state, outcome)
                        logger.info(f"Regime snapshot stored for trade #{trade_id} ({outcome})")
                except Exception as e:
                    logger.debug(f"Failed to store regime snapshot for trade #{trade_id}: {e}")

            await self.storage.close_trade_journal(trade_id, exit_price, pnl_pips, is_win)

            icon = "✅" if is_win else "❌"
            return SkillResult(
                success=True,
                data={"trade_id": trade_id, "pnl_pips": pnl_pips, "is_win": is_win},
                metadata={"formatted": f"{icon} Trade #{trade_id} closed: {pnl_pips:+.1f} pips"},
            )
        except Exception as e:
            logger.error(f"Error closing trade: {e}", exc_info=True)
            return SkillResult(success=False, error=str(e))

    async def _get_journal(self, **params) -> SkillResult:
        """Retrieve trade journal entries."""
        try:
            trades = await self.storage.get_trade_journal(
                strategy=params.get("strategy"),
                status=params.get("status"),
                limit=params.get("limit", 50),
            )

            lines = ["📓 *Trade Journal*\n"]
            for t in trades[:10]:
                icon = "✅" if t["is_win"] else "❌" if t["status"] == "closed" else "⏳"
                lines.append(
                    f"{icon} #{t['id']} {t['direction']} @ `{t['entry_price']}` "
                    f"[{t['strategy']}] {t['pnl_pips']:+.1f}p"
                )
                chain = t.get("causal_chain")
                if isinstance(chain, dict):
                    reaction = chain.get("reaction") or chain.get("price_reaction")
                    lines.append(
                        f"↳ Causal: {chain.get('trigger')} / {reaction} / "
                        f"{chain.get('indicator_response')} / {chain.get('outcome')}"
                    )
            if len(trades) > 10:
                lines.append(f"\n_...and {len(trades) - 10} more_")

            return SkillResult(
                success=True,
                data=trades,
                metadata={"formatted": "\n".join(lines)},
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_stats(self, **params) -> SkillResult:
        """Get trade journal aggregate stats."""
        try:
            stats = await self.storage.get_trade_journal_stats(
                strategy=params.get("strategy")
            )

            lines = [
                "📊 *Trade Journal Stats*\n",
                f"Total Trades: {stats['total']}",
                f"Win Rate: {stats['win_rate']}%",
                f"Total P/L: {stats['total_pnl']:+.1f} pips",
                f"Avg P/L: {stats['avg_pnl']:+.1f} pips",
            ]

            by_strat = stats.get("by_strategy", {})
            if by_strat:
                lines.append("\n*By Strategy:*")
                for s, d in by_strat.items():
                    lines.append(f"  {s}: {d['win_rate']}% WR, {d['pnl']:+.1f}p")

            return SkillResult(
                success=True,
                data=stats,
                metadata={"formatted": "\n".join(lines)},
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))
