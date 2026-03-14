"""
Risk Management Skill — Wraps RiskManager for the skills framework.
"""

from ...automation.events import Event
from ...trading.risk_manager import RiskManager, RiskConfig
from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class RiskManagementSkill(BaseSkill):
    name = "risk_management"
    description = "Position sizing, stop loss, take profit, and drawdown control"
    emoji = "🛡️"
    category = SkillCategory.TRADING
    version = "1.0.0"
    capabilities = ["assess_trade", "position_size", "stop_loss", "take_profit"]

    def __init__(self, config: RiskConfig = None):
        super().__init__()
        self.manager = RiskManager(config or RiskConfig())
        self._bus = None
        self._storage = None

    def set_risk_manager(self, manager):
        """Inject the RiskManager instance."""
        self.manager = manager

    def set_event_bus(self, event_bus):
        self._bus = event_bus

    def set_storage(self, storage):
        self._storage = storage

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "assess_trade":
            return await self._assess(context, **params)
        elif action == "position_size":
            return await self._position_size(**params)
        elif action == "stop_loss":
            return await self._stop_loss(**params)
        elif action == "take_profit":
            return await self._take_profit(**params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _assess(self, context: SkillContext, **params) -> SkillResult:
        direction = params.get("direction") or context.signals.get("direction") or "BUY"
        entry = params.get("entry_price") or context.signals.get("entry_price") or 0
        atr = params.get("atr")
        avg_atr = params.get("avg_atr")
        support = params.get("support", context.analysis.get("levels", {}).get("support", []))
        resistance = params.get("resistance", context.analysis.get("levels", {}).get("resistance", []))

        if not entry:
            price_data = context.market_data.get("price", {})
            entry = price_data.get("price", 0)

        if not atr:
            ind = context.analysis.get("indicators", {})
            atr_data = ind.get("indicators", {}).get("ATR", {})
            atr = atr_data.get("value")
            if not avg_atr:
                avg_atr = atr_data.get("sma") or atr_data.get("moving_average") or atr_data.get("avg")

        try:
            result = self.manager.assess_trade(
                direction, entry, atr=atr, avg_atr=avg_atr, support=support, resistance=resistance,
            )
            session_regime = context.metadata.get("session_regime", "unknown")
            liquidity_zones = context.metadata.get("liquidity_zones", [])
            market_intent = context.metadata.get("market_intent", {})
            intent_confidence = market_intent.get("confidence", context.metadata.get("market_intent_confidence"))
            macro_adjustment = context.metadata.get("confidence_adjustment")
            if (intent_confidence is None or intent_confidence < 0.4) and macro_adjustment is not None and macro_adjustment >= 0.6:
                intent_confidence = max(intent_confidence or 0.0, 0.6)
            adaptive_stop = self._calculate_adaptive_stop(
                direction=direction,
                entry_price=result.entry_price,
                atr=atr,
                liquidity_zones=liquidity_zones,
                session_regime=session_regime,
            )
            stop_loss = adaptive_stop["stop_loss"]
            take_profit = self.manager.calculate_take_profit(
                result.entry_price, stop_loss, direction, self.manager.config.default_rr_ratio
            )
            slippage_pips = 4.0 if (
                context.metadata.get("emergency_mode")
                or context.metadata.get("deviation_monitor_active")
                or context.metadata.get("deviation_monitor_last_trigger")
            ) else 1.5
            realistic_rr = self._calculate_realistic_rr(
                direction=direction,
                entry_price=result.entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                slippage_pips=slippage_pips,
            )
            base_position_size = result.position_size
            base_risk_pct = self._get_base_risk_pct(context.user_prefs)
            recent_drawdown = self._get_recent_drawdown_pct()
            correlation_data = context.market_data.get("correlation", {})
            sizing = self._calculate_dynamic_size(
                base_position_size=base_position_size,
                session_regime=session_regime,
                intent_confidence=intent_confidence,
                base_risk_pct=base_risk_pct,
                recent_drawdown=recent_drawdown,
                correlation_data=correlation_data,
                direction=direction,
            )
            dynamic_size = sizing["position_size"]
            risk_pips = abs((result.entry_price - stop_loss) * 10000)
            reward_pips = abs((take_profit - result.entry_price) * 10000)
            risk_reward_ratio = reward_pips / risk_pips if risk_pips else 0
            warnings = result.warnings or []
            factors = []
            if any("drawdown" in w.lower() for w in warnings):
                factors.append("drawdown_risk")
            if any("stop too wide" in w.lower() for w in warnings):
                factors.append("max_risk_pct")
            if abs(risk_pips) >= 60:
                factors.append("volatility")
            reason = ", ".join(factors) if factors else "normal"
            status = "approved"
            rejection_reasons = []
            if not result.approved:
                rejection_reasons.append("risk_limits")
            if adaptive_stop.get("rejection_reason"):
                rejection_reasons.append(adaptive_stop["rejection_reason"])
            if sizing.get("rejection_reason"):
                rejection_reasons.append(sizing["rejection_reason"])
            if realistic_rr < 1.3:
                rejection_reasons.append("insufficient_risk_reward")
                warnings.append("Rejected: minimum risk-reward not met")
            rejection_reason = self._resolve_rejection_reason(rejection_reasons)
            if rejection_reason:
                status = "rejected"
                reason = rejection_reason
            data = {
                "approved": result.approved and status == "approved",
                "direction": result.direction,
                "entry_price": result.entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "position_size": dynamic_size,
                "risk_pips": round(risk_pips, 1),
                "reward_pips": round(reward_pips, 1),
                "risk_reward_ratio": round(risk_reward_ratio, 2) if risk_reward_ratio else 0,
                "reason": reason,
                "status": status,
            }
            context.risk = data
            context.metadata["risk_assessment"] = {
                "status": status,
                "stop_valid": status == "approved" and not adaptive_stop.get("rejection_reason"),
                "session_regime": session_regime,
                "liquidity_zone": adaptive_stop["liquidity_zone"],
                "stop_buffer_pips": adaptive_stop["buffer_pips"],
                "stop_distance_pips": adaptive_stop["stop_distance_pips"],
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "base_position_size": base_position_size,
                "adjusted_position_size": dynamic_size,
                "adjusted_position_size_pct": sizing["adjusted_risk_pct"],
                "session_multiplier": sizing["session_multiplier"],
                "confidence_multiplier": sizing["confidence_multiplier"],
                "drawdown_multiplier": sizing["drawdown_multiplier"],
                "correlation_multiplier": sizing.get("correlation_multiplier", 1.0),
                "risk_multiplier": sizing["risk_multiplier"],
                "base_risk_pct": sizing["base_risk_pct"],
                "realistic_rr": round(realistic_rr, 2),
                "realistic_risk_reward": round(realistic_rr, 2),
                "slippage_pips": slippage_pips,
                "rejection_reason": rejection_reason,
            }
            if status == "rejected":
                await self._record_rejection(context, params, rejection_reason)
            return SkillResult(
                success=True,
                data=data,
                metadata={"status": status, "rejection_reason": rejection_reason},
                next_skill=None if status == "rejected" else "trading_strategy",
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _calculate_adaptive_stop(
        self,
        direction: str,
        entry_price: float,
        atr: float,
        liquidity_zones: list,
        session_regime: str,
    ) -> dict:
        rejection_reason = "avoid_weekend" if session_regime in ("weekend", "holiday") else None
        base_buffer = self._get_session_buffer(session_regime)
        atr_pips = atr * 10000 if atr else 0.0
        volatility_buffer = min(atr_pips * 0.2, 15.0) if atr_pips and atr_pips > 30 else 0.0
        base_buffer = base_buffer + volatility_buffer
        zone = self._find_relevant_zone(direction, entry_price, liquidity_zones)
        buffer_pips = base_buffer
        stop_loss = entry_price
        if zone:
            total_buffer_pips = 10 + base_buffer
            if direction.upper() == "BUY":
                stop_loss = zone["price_level"] - (total_buffer_pips * 0.0001)
            else:
                stop_loss = zone["price_level"] + (total_buffer_pips * 0.0001)
            buffer_pips = total_buffer_pips
        else:
            if direction.upper() == "BUY":
                stop_loss = entry_price - (base_buffer * 0.0001)
            else:
                stop_loss = entry_price + (base_buffer * 0.0001)
        noise_band_pips = (atr_pips * 0.6) if atr_pips else 0.0
        stop_distance_pips = abs((entry_price - stop_loss) * 10000)
        if noise_band_pips and stop_distance_pips < noise_band_pips:
            rejection_reason = "stop_inside_noise_band"
        return {
            "stop_loss": round(stop_loss, 5),
            "buffer_pips": round(buffer_pips, 1),
            "stop_distance_pips": round(stop_distance_pips, 1),
            "safety_margin_pips": round(buffer_pips, 1),
            "liquidity_zone": zone,
            "rejection_reason": rejection_reason,
        }

    def _calculate_dynamic_size(
        self,
        base_position_size: float,
        session_regime: str,
        intent_confidence,
        base_risk_pct: float,
        recent_drawdown: float,
        correlation_data: dict = None,
        direction: str = "BUY",
    ) -> dict:
        rejection_reason = None
        config_risk = self.manager.config.risk_per_trade or 1.0
        risk_multiplier = base_risk_pct / config_risk
        session_multiplier = self._get_session_multiplier(session_regime)
        confidence_multiplier = self._get_confidence_multiplier(intent_confidence)
        drawdown_multiplier = self._get_drawdown_multiplier(recent_drawdown)
        correlation_multiplier = self._get_correlation_multiplier(correlation_data)
        
        if session_multiplier == 0.0:
            rejection_reason = "avoid_weekend"
        if confidence_multiplier == 0.0:
            rejection_reason = self._resolve_rejection_reason([rejection_reason, "low_intent_confidence"])
        if drawdown_multiplier == 0.0:
            rejection_reason = self._resolve_rejection_reason([rejection_reason, "excessive_drawdown"])
            
        adjusted_risk_pct = base_risk_pct * session_multiplier * confidence_multiplier * drawdown_multiplier * correlation_multiplier
        if rejection_reason:
            adjusted_risk_pct = 0.0
        if adjusted_risk_pct:
            adjusted_risk_pct = min(2.0, max(0.25, adjusted_risk_pct))
        position_size = 0.0
        if adjusted_risk_pct > 0:
            adjusted = base_position_size * (adjusted_risk_pct / config_risk)
            position_size = round(max(0.01, adjusted), 2)
        return {
            "position_size": position_size,
            "base_risk_pct": base_risk_pct,
            "risk_multiplier": risk_multiplier,
            "session_multiplier": session_multiplier,
            "confidence_multiplier": confidence_multiplier,
            "drawdown_multiplier": drawdown_multiplier,
            "correlation_multiplier": correlation_multiplier,
            "adjusted_risk_pct": round(adjusted_risk_pct, 2),
            "rejection_reason": rejection_reason,
        }

    def _calculate_realistic_rr(
        self,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        slippage_pips: float,
    ) -> float:
        if direction.upper() == "BUY":
            reward = (take_profit - entry_price) * 10000
            risk = (entry_price - stop_loss) * 10000
        else:
            reward = (entry_price - take_profit) * 10000
            risk = (stop_loss - entry_price) * 10000
        if risk <= 0:
            return 0.0
        return reward / (risk + slippage_pips)

    def _find_relevant_zone(self, direction: str, entry_price: float, liquidity_zones: list) -> dict | None:
        if not liquidity_zones:
            return None
        zones = [z for z in liquidity_zones if isinstance(z, dict) and "price_level" in z]
        if direction.upper() == "BUY":
            below = [z for z in zones if z["price_level"] < entry_price]
            return max(below, key=lambda z: z["price_level"]) if below else None
        above = [z for z in zones if z["price_level"] > entry_price]
        return min(above, key=lambda z: z["price_level"]) if above else None

    def _get_session_buffer(self, session_regime: str) -> float:
        if session_regime == "asian":
            return 8.0
        if session_regime == "london":
            return 12.0
        if session_regime == "newyork":
            return 15.0
        if session_regime == "overlap":
            return 18.0
        return 15.0

    def _get_session_multiplier(self, session_regime: str) -> float:
        if session_regime == "asian":
            return 0.6
        if session_regime == "london":
            return 1.0
        if session_regime == "newyork":
            return 1.0
        if session_regime == "overlap":
            return 1.2
        if session_regime in ("weekend", "holiday"):
            return 0.0
        return 0.8

    def _get_confidence_multiplier(self, intent_confidence) -> float:
        if intent_confidence is None:
            return 0.8
        confidence = float(intent_confidence)
        if confidence > 1.0:
            confidence = confidence / 100 if confidence <= 100 else 1.0
        if confidence < 0.4:
            return 0.0
        if confidence < 0.6:
            return 0.6
        if confidence >= 0.8:
            return 1.0
        return 0.8

    def _get_drawdown_multiplier(self, recent_drawdown: float) -> float:
        if recent_drawdown > 5.0:
            return 0.0
        if recent_drawdown > 3.0:
            return 0.5
        return 1.0

    def _get_recent_drawdown_pct(self) -> float:
        if self.manager.config.account_balance <= 0 or self.manager._daily_pnl >= 0:
            return 0.0
        return abs(self.manager._daily_pnl / self.manager.config.account_balance * 100)

    def _get_base_risk_pct(self, user_prefs: dict) -> float:
        risk_pref = user_prefs.get("risk_tolerance", "")
        if risk_pref == "low":
            return 0.5
        if risk_pref == "high":
            return 1.5
        return 1.0

    def _get_correlation_multiplier(self, correlation_data: dict) -> float:
        if not correlation_data:
            return 1.0
            
        multiplier = 1.0
        
        # GBP/USD (Usually moves with EUR/USD)
        gbp_corr = correlation_data.get("GBP_USD")
        if gbp_corr is not None:
            if gbp_corr > 0.75:
                multiplier += 0.15
            elif gbp_corr < 0.2:
                multiplier -= 0.15
                
        # USD/CHF (Usually moves inverse to EUR/USD)
        chf_corr = correlation_data.get("USD_CHF")
        if chf_corr is not None:
            if chf_corr < -0.75:
                multiplier += 0.15
            elif chf_corr > -0.2:
                multiplier -= 0.15
                
        return min(max(multiplier, 0.5), 1.5)

    @staticmethod
    def _resolve_rejection_reason(reasons: list) -> str:
        priority = {
            "avoid_weekend": 5,
            "excessive_drawdown": 4,
            "risk_limits": 3,
            "low_intent_confidence": 3,
            "stop_inside_noise_band": 2,
            "insufficient_risk_reward": 1,
        }
        filtered = [r for r in reasons if r]
        if not filtered:
            return ""
        return max(filtered, key=lambda r: priority.get(r, 0))

    async def _record_rejection(self, context: SkillContext, params: dict, reason: str):
        signal = context.signals or params
        risk = context.risk or {}
        entry_price = signal.get("entry_price", risk.get("entry_price", 0))
        stop_loss = risk.get("stop_loss", 0)
        take_profit = risk.get("take_profit", 0)
        strategy = signal.get("strategy", "manual")
        timeframe = context.market_data.get("timeframe", "H1")
        regime = context.metadata.get("regime", "")
        confidence = signal.get("confidence", 0.0)
        indicators = context.analysis.get("indicators", {})
        patterns = context.analysis.get("patterns", [])
        if self._storage:
            await self._storage.save_trade_journal(
                direction=signal.get("direction", "BUY"),
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy=strategy,
                timeframe=timeframe,
                regime=regime,
                confidence=confidence,
                indicators=indicators,
                patterns=patterns if isinstance(patterns, list) else [],
                reasoning=reason,
            )
        if self._bus:
            await self._bus.emit(Event("trade.rejected", "risk_management", {
                "reason": reason,
                "direction": signal.get("direction", "BUY"),
                "strategy": strategy,
                "timeframe": timeframe,
            }))

    async def _position_size(self, **params) -> SkillResult:
        balance = params.get("balance", 10000)
        risk_pct = params.get("risk_pct", 0.01)
        stop_pips = params.get("stop_pips", 30)
        try:
            size = self.manager.calculate_position_size(balance, risk_pct, stop_pips)
            return SkillResult(success=True, data={"position_size": size})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _stop_loss(self, **params) -> SkillResult:
        direction = params.get("direction", "BUY")
        entry = params.get("entry_price", 0)
        atr = params.get("atr", 0.001)
        try:
            sl = self.manager.calculate_stop_loss(direction, entry, atr)
            return SkillResult(success=True, data={"stop_loss": sl})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _take_profit(self, **params) -> SkillResult:
        direction = params.get("direction", "BUY")
        entry = params.get("entry_price", 0)
        sl = params.get("stop_loss", 0)
        try:
            tp = self.manager.calculate_take_profit(direction, entry, sl)
            return SkillResult(success=True, data={"take_profit": tp})
        except Exception as e:
            return SkillResult(success=False, error=str(e))
