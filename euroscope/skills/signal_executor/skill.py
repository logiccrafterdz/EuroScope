from ...data.storage import Storage
from ...config import Config
from ...trading.safety_guardrails import SafetyGuardrail
from ...trading.signal_executor import SignalExecutor

logger = logging.getLogger("euroscope.skills.signal_executor")


@dataclass
class PaperTrade:
    """A virtual paper trade."""
    trade_id: str = ""
    direction: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    strategy: str = ""
    timestamp: float = 0.0
    status: str = "open"  # open, closed
    exit_price: float = 0.0
    pnl_pips: float = 0.0
    execution_mode: str = "paper"


class SignalExecutorSkill(BaseSkill):
    name = "signal_executor"
    description = "Converts signals to paper trade orders with tracking"
    emoji = "⚡"
    category = SkillCategory.TRADING
    version = "1.0.0"
    capabilities = ["open_trade", "close_trade", "list_trades", "trade_history", "update_trade"]

    def __init__(self):
        super().__init__()
        self._storage: Storage | None = None
        self._bus = None
        self._emergency_halt = False
        self._emergency_halt_until = 0.0
        self._paper_trading_only = True
        self._config = None
        self._guardrail = None
        self._broker = None
        self._executor: Optional[SignalExecutor] = None

    def set_config(self, config):
        self._config = config
        self._guardrail = SafetyGuardrail(config)
        value = getattr(config, "paper_trading_only", None)
        if value is None:
            value = getattr(config, "EUROSCOPE_PAPER_TRADING_ONLY", None)
        if value is None:
            value = True
        self._paper_trading_only = bool(value)
        self._init_executor()

    def _init_executor(self):
        """Initialize or update the trading executor."""
        if self._storage and self._config:
            self._executor = SignalExecutor(
                storage=self._storage,
                broker=self._broker,
                paper_trading=self._paper_trading_only
            )
            logger.info("SignalExecutorSkill: Trading executor initialized.")

    def set_storage(self, storage):
        self._storage = storage
        self._init_executor()

    def set_broker(self, broker):
        self._broker = broker
        self._init_executor()

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "open_trade":
            return await self._open_trade(context, **params)
        elif action == "close_trade":
            return await self._close_trade(context, **params)
        elif action == "list_trades":
            return await self._list_trades()
        elif action == "trade_history":
            return await self._trade_history()
        elif action == "update_trade":
            return await self._update_trade(context, **params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def execute_trade(self, context: SkillContext, **params) -> SkillResult:
        return await self._open_trade(context, **params)

    def start_streaming(self, ws_client):
        """Bind WS client to the internal executor for live ticks."""
        if self._executor:
            self._executor.start_streaming(ws_client)
            logger.info("SignalExecutorSkill: WebSocket streaming started.")
        else:
            logger.error("SignalExecutorSkill: Cannot start streaming, executor not initialized.")

    async def _open_trade(self, context: SkillContext, **params) -> SkillResult:
        if self._guardrail is None:
            self._guardrail = SafetyGuardrail(self._config or Config())
        
        if self._guardrail:
            should_block, reason = await self._guardrail.should_block_signal(context)
            if should_block:
                await self._record_abort(context, params, reason)
                return SkillResult(success=False, error=reason, data={"aborted": True, "reason": reason})
            await self._guardrail.enhance_signal_safety(context)

        abort_reason = self._guard_trade(context)
        if abort_reason:
            await self._record_abort(context, params, abort_reason)
            return SkillResult(success=False, error=abort_reason, data={"aborted": True, "reason": abort_reason})

        signal = context.signals or params
        risk = context.risk or {}
        
        direction = signal.get("direction", "BUY")
        entry_price = signal.get("entry_price", 0.0)
        stop_loss = risk.get("stop_loss", 0.0)
        take_profit = risk.get("take_profit", 0.0)
        strategy = signal.get("strategy", "manual")
        timeframe = context.market_data.get("timeframe", "H1")
        confidence = signal.get("confidence", 50.0)
        reasoning = signal.get("reasoning", "")
        atr = context.analysis.get("indicators", {}).get("atr")

        if not self._executor:
            self._init_executor()
            
        if not self._executor:
            return SkillResult(success=False, error="Executor not initialized")

        signal_id = await self._executor.open_signal(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=strategy,
            timeframe=timeframe,
            confidence=confidence,
            reasoning=reasoning,
            atr=atr
        )

        if signal_id == -1:
            return SkillResult(success=False, error="Order rejected by executor")

        # Sync back to context
        trade_data = {
            "id": signal_id,
            "trade_id": f"T-{signal_id}",
            "direction": direction,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "status": "open"
        }
        context.open_positions.append(trade_data)
        
        return SkillResult(success=True, data=trade_data, metadata={"signal_id": signal_id})

    def _guard_trade(self, context: SkillContext) -> str | None:
        now = time.time()
        if self._emergency_halt and now < self._emergency_halt_until:
            return "EMERGENCY: market regime shift"
        if self._emergency_halt and now >= self._emergency_halt_until:
            self._emergency_halt = False
        if context.metadata.get("emergency_mode") is True:
            return "EMERGENCY: market regime shift"
        if self._paper_trading_only:
            mode = context.metadata.get("execution_mode")
            if mode and str(mode).lower() not in {"paper", "sim", "simulation"}:
                return "PAPER_ONLY: live execution disabled"
        if context.metadata.get("uncertainty_score", 0) > 0.65:
            return "UNCERTAINTY: confidence too low"
        if context.metadata.get("confidence_adjustment", 1.0) < 0.5:
            return "CONFIDENCE: signal degraded"
        return None

    def set_emergency_halt(self, duration_seconds: int = 300):
        self._emergency_halt = True
        self._emergency_halt_until = time.time() + duration_seconds

    async def _record_abort(self, context: SkillContext, params: dict, reason: str):
        signal = context.signals or params
        risk = context.risk or {}
        entry_price = signal.get("entry_price", risk.get("entry_price", 0))
        stop_loss = risk.get("stop_loss", 0)
        take_profit = risk.get("take_profit", 0)
        strategy = signal.get("strategy", "manual")
        timeframe = context.market_data.get("timeframe", "H1")
        regime = context.metadata.get("regime", "")
        confidence = signal.get("confidence", 0.0)
        indicators = self._build_indicators(context)
        patterns = self._build_patterns(context)
        if self._storage:
            self._storage.save_trade_journal(
                direction=signal.get("direction", "BUY"),
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy=strategy,
                timeframe=timeframe,
                regime=regime,
                confidence=confidence,
                indicators=indicators,
                patterns=patterns,
                reasoning=f"paper rejection: {reason}",
                status="rejected",
            )
        if self._bus:
            await self._bus.emit(Event("trade.aborted", "signal_executor", {
                "reason": reason,
                "direction": signal.get("direction", "BUY"),
                "strategy": strategy,
                "timeframe": timeframe,
            }))

    @staticmethod
    def _build_patterns(context: SkillContext) -> list:
        patterns = context.analysis.get("patterns", [])
        if isinstance(patterns, list):
            return patterns
        return []

    @staticmethod
    def _build_indicators(context: SkillContext) -> dict:
        indicators = context.analysis.get("indicators", {})
        if not isinstance(indicators, dict):
            indicators = {}
        indicators = dict(indicators)
        if "uncertainty_score" in context.metadata:
            indicators["uncertainty_score"] = context.metadata.get("uncertainty_score")
        if "uncertainty_reasoning" in context.metadata:
            indicators["uncertainty_reasoning"] = context.metadata.get("uncertainty_reasoning")
        return indicators

    async def _close_trade(self, context: SkillContext, **params) -> SkillResult:
        signal_id = params.get("signal_id") or params.get("id")
        exit_price = params.get("exit_price", 0.0)
        
        if not self._executor:
            return SkillResult(success=False, error="Executor not initialized")

        result = await self._executor.close_signal(signal_id, exit_price, reason="manual")
        if result:
            return SkillResult(success=True, data=result)
        return SkillResult(success=False, error=f"Signal #{signal_id} not found or not open")

    async def _update_trade(self, context: SkillContext, **params) -> SkillResult:
        """Modify SL/TP of an active open trade."""
        signal_id = params.get("signal_id") or params.get("id")
        new_sl = params.get("stop_loss")
        new_tp = params.get("take_profit")
        
        if not signal_id:
            return SkillResult(success=False, error="signal_id is required")
            
        if self._storage:
            await self._storage.update_signal_levels(signal_id, stop_loss=new_sl, take_profit=new_tp)
            return SkillResult(success=True, data={"id": signal_id, "stop_loss": new_sl, "take_profit": new_tp})
                
        return SkillResult(success=False, error="Storage not available")

    async def _list_trades(self) -> SkillResult:
        if not self._executor:
            return SkillResult(success=False, error="Executor not initialized")
        trades = await self._executor.get_open_signals()
        formatted = await self._executor.format_open_signals()
        return SkillResult(success=True, data=trades, metadata={"formatted": formatted})

    async def _trade_history(self) -> SkillResult:
        if not self._executor:
            return SkillResult(success=False, error="Executor not initialized")
        trades = await self._executor.get_closed_signals()
        formatted = await self._executor.format_performance()
        return SkillResult(success=True, data=trades, metadata={"formatted": formatted})

    def _format_trades(self, trades: list[dict], title: str) -> str:
        if not trades:
            return "📋 No open trades."
        lines = [f"{title} ({len(trades)})\n"]
        for t in trades:
            direction = str(t.get("direction", "")).upper()
            icon = "📈" if direction == "BUY" else "📉"
            trade_id = t.get("trade_id", "")
            entry = self._format_price(t.get("entry_price"))
            stop = self._format_price(t.get("stop_loss"))
            target = self._format_price(t.get("take_profit"))
            lines.append(f"{icon} {trade_id} {direction} @ `{entry}` SL=`{stop}` TP=`{target}`")
        return "\n".join(lines)

    @staticmethod
    def _format_price(value) -> str:
        try:
            return f"{float(value):.5f}"
        except (TypeError, ValueError):
            return str(value)
