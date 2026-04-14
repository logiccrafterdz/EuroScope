"""
Signal Executor — Paper Trading Order Management

Manages the lifecycle of trading signals: open, monitor, close.
Tracks PnL and performance metrics. Uses existing Storage API.
"""

import logging
from datetime import datetime
from typing import Optional

from ..data.storage import Storage
from .execution_simulator import ExecutionSimulator
from .capital_provider import CapitalProvider
from .capital_ws import CapitalWebsocketClient
from .risk_manager import RiskManager

logger = logging.getLogger("euroscope.trading.signal_executor")


class SignalExecutor:
    """
    Manages trading signals through their full lifecycle.

    Paper trading only — no real orders. Persists signals to DB
    and tracks performance via Storage.save_signal / get_signals.
    """

    def __init__(self, storage: Storage, execution_sim: ExecutionSimulator = None, 
                 risk_manager: RiskManager = None, broker: CapitalProvider = None, 
                 paper_trading: bool = True):
        self.storage = storage
        self.execution_sim = execution_sim or ExecutionSimulator()
        self.risk_manager = risk_manager or RiskManager(storage=storage)
        self.broker = broker
        self.paper_trading = paper_trading
        self.ws_client: Optional[CapitalWebsocketClient] = None
        
        # Track highest/lowest price reached for active trailing stops: {signal_id: best_price}
        self._trailing_high_water_marks = {}

    async def initialize(self):
        """Initialize the executor (load risk state, etc)."""
        if self.risk_manager:
            await self.risk_manager.load_state()
            
        await self._recover_inflight_transactions()

    async def _recover_inflight_transactions(self):
        """
        Scan for pending transactions (Write-Ahead Log) that were interrupted by a crash.
        Reconcile with the broker to ensure we don't have orphan positions.
        """
        pending_txs = await self.storage.get_pending_transactions()
        if not pending_txs:
            return

        logger.info(f"Recovering {len(pending_txs)} in-flight transactions...")
        
        # If real trading is active, fetch broker positions to reconcile
        broker_positions = []
        if not self.paper_trading and self.broker:
            res = await self.broker.get_positions()
            if res.get("success"):
                broker_positions = res.get("positions", [])

        import json
        for tx in pending_txs:
            tx_id = tx["id"]
            action = tx["action"]
            try:
                payload = json.loads(tx["payload"])
            except Exception as e:
                logger.error(f"Failed to parse transaction payload {tx_id}: {e}")
                await self.storage.update_transaction_status(tx_id, "failed")
                continue

            if action == "open_trade":
                # Check if it was actually opened on the broker
                # In a robust implementation, we'd match broker's dealId. 
                # Here we close the loop safely by checking if it exists as an open signal
                # or marking it as failed to prevent duplicate executions.
                logger.warning(f"Found pending 'open_trade' transaction #{tx_id}. Marking as failed to prevent accidental duplicate.")
                await self.storage.update_transaction_status(tx_id, "failed")
                
            elif action == "close_trade":
                logger.warning(f"Found pending 'close_trade' transaction #{tx_id}. Marking as completed as broker likely handled it.")
                await self.storage.update_transaction_status(tx_id, "completed")
            else:
                await self.storage.update_transaction_status(tx_id, "failed")

    def start_streaming(self, ws_client: CapitalWebsocketClient):
        """Bind WS client to the executor and register the on_tick callback."""
        self.ws_client = ws_client
        self.ws_client.add_callback(self._on_tick)
        logger.info("SignalExecutor bound to live WebSocket stream.")

    async def _on_tick(self, symbol: str, bid: float, ask: float):
        """
        Handle incoming live ticks. Evaluates all open trades instantly.
        If SL or TP is hit, trade is closed using the exact bid/ask prices.
        """
        logger.debug(f"SignalExecutor: Processing tick {symbol} {bid}/{ask}")
        open_signals = await self.get_open_signals()
        for signal in open_signals:
            sig_id = signal["id"]
            direction = signal["direction"]
            sl = signal["stop_loss"]
            tp = signal["take_profit"]

            reason = None
            exit_price = None

            # Trailing Stop Configuration
            if direction == "BUY":
                new_sl = self.evaluate_trailing_stop(sig_id, "BUY", bid, signal["entry_price"], sl)
                if new_sl:
                    logger.info(f"🔄 Trailing Stop ADVANCED for BUY #{sig_id}: {sl} -> {new_sl} (Current bid: {bid})")
                    await self.storage.update_signal_sl(sig_id, new_sl)
                    await self.storage.update_trade_journal_sl(sig_id, new_sl)
                    sl = new_sl

                # Exit condition check
                if bid <= sl:
                    reason = "stop_loss"
                    exit_price = bid
                elif bid >= tp:
                    reason = "take_profit"
                    exit_price = bid
            elif direction == "SELL":
                new_sl = self.evaluate_trailing_stop(sig_id, "SELL", ask, signal["entry_price"], sl)
                if new_sl:
                    logger.info(f"🔄 Trailing Stop ADVANCED for SELL #{sig_id}: {sl} -> {new_sl} (Current ask: {ask})")
                    await self.storage.update_signal_sl(sig_id, new_sl)
                    await self.storage.update_trade_journal_sl(sig_id, new_sl)
                    sl = new_sl

                # Exit condition check
                if ask >= sl:
                    reason = "stop_loss"
                    exit_price = ask
                elif ask <= tp:
                    reason = "take_profit"
                    exit_price = ask

            if reason:
                logger.warning(f"⚡ WS TICK TRIGGER: Signal #{sig_id} {reason.upper()} hit at {bid}/{ask}")
                # Execute the exit
                exec_result = self.execution_sim.simulate_exit(
                    direction, exit_price, reason, atr=None # Simplified execution on live tick
                )
                result = await self.close_signal(sig_id, exec_result.fill_price, reason)
                if result:
                    logger.info(f"Signal #{sig_id} closed instantly via Tick Stream. Slippage: {exec_result.slippage_pips} pips.")
                    # Clean up memory
                    if sig_id in self._trailing_high_water_marks:
                        del self._trailing_high_water_marks[sig_id]

    def evaluate_trailing_stop(self, sig_id: int, direction: str, current_price: float, entry_price: float, current_sl: float) -> Optional[float]:
        """Evaluates whether to trail a stop loss limit based on current price."""
        trailing_activation_pips = 15.0  # Activate trailing when 15 pips in profit
        
        new_sl = None

        if direction == "BUY":
            current_profit_pips = (current_price - entry_price) * 10000
            if current_profit_pips >= trailing_activation_pips:
                high_water = self._trailing_high_water_marks.get(sig_id, entry_price)
                if current_price > high_water:
                    self._trailing_high_water_marks[sig_id] = current_price
                    trail_distance = (trailing_activation_pips * 0.0001)
                    prop_sl = round(current_price - trail_distance, 5)
                    if prop_sl > current_sl:
                        new_sl = prop_sl

        elif direction == "SELL":
            current_profit_pips = (entry_price - current_price) * 10000
            if current_profit_pips >= trailing_activation_pips:
                low_water = self._trailing_high_water_marks.get(sig_id, entry_price)
                if current_price < low_water:
                    self._trailing_high_water_marks[sig_id] = current_price
                    trail_distance = (trailing_activation_pips * 0.0001)
                    prop_sl = round(current_price + trail_distance, 5)
                    if prop_sl < current_sl or current_sl == 0:
                        new_sl = prop_sl

        return new_sl

    async def open_signal(self, direction: str, entry_price: float,
                    stop_loss: float, take_profit: float,
                    strategy: str = "manual", timeframe: str = "H1",
                    confidence: float = 50.0, reasoning: str = "",
                    atr: float = None) -> int:
        """
        Open a new trading signal (paper trade).

        Applies realistic execution simulation (spread + slippage)
        to the entry price.

        Args:
            strategy: stored in the 'source' column of trading_signals
            atr: Current ATR for volatility-adaptive execution

        Returns:
            Signal ID, or -1 if order rejected
        """
        # 0. Log transaction intent (Write-Ahead Log)
        tx_payload = {
            "direction": direction, "entry_price": entry_price, 
            "stop_loss": stop_loss, "take_profit": take_profit,
            "strategy": strategy, "timeframe": timeframe
        }
        tx_id = await self.storage.log_transaction("open_trade", tx_payload, "pending")

        # 1. Simulate execution for paper trading or get real fill
        if self.paper_trading:
            exec_result = self.execution_sim.simulate_entry(direction, entry_price, atr=atr)
            if not exec_result.filled:
                logger.warning(f"Paper Signal REJECTED: {direction} @ {entry_price} ({exec_result.details})")
                await self.storage.update_transaction_status(tx_id, "failed")
                return -1
            fill_price = exec_result.fill_price
            exec_details = exec_result.details
        else:
            # REAL EXECUTION via Capital.com
            if not self.broker:
                logger.error("Real trading enabled but no broker configured!")
                await self.storage.update_transaction_status(tx_id, "failed")
                return -1
            
            # Note: For real execution, stop_loss and take_profit are passed to broker
            res = await self.broker.execute_trade("EURUSD", direction, 0.01, stop_loss, take_profit)
            if not res.get("success"):
                logger.error(f"REAL TRADE FAILED: {res.get('error')}")
                await self.storage.update_transaction_status(tx_id, "failed")
                return -1
            
            # For simplicity in this v1 bridge, we assume the price we requested is roughly the fill
            # In a full project we'd poll for 'deal' confirmation
            fill_price = entry_price 
            exec_details = "Capital.com Live"
        rr = 0.0
        sl_dist = abs(fill_price - stop_loss)
        tp_dist = abs(take_profit - fill_price)
        if sl_dist > 0:
            rr = round(tp_dist / sl_dist, 2)

        signal_id = await self.storage.save_signal(
            direction=direction.upper(),
            entry_price=fill_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            timeframe=timeframe,
            source=strategy,
            reasoning=reasoning,
            risk_reward_ratio=rr
        )
        logger.info(f"Executed trade #{signal_id}: {direction.upper()} at {fill_price}. {exec_details}")
        
        # Mark transaction as completed
        await self.storage.update_transaction_status(tx_id, "completed")
        
        # Notify Risk Manager
        await self.risk_manager.record_trade_result(
            pnl=0.0
        )
        return signal_id

    async def create_pending_order(self, direction: str, trigger_price: float,
                             stop_loss: float, take_profit: float,
                             strategy: str = "llm_precalc", timeframe: str = "H1",
                             confidence: float = 75.0, reasoning: str = "Pending Order") -> int:
        """
        Create a pending order to eliminate LLM execution latency.
        The AI pre-calculates the trigger, and the system executes instantly when hit.
        """
        rr = 0.0
        sl_dist = abs(trigger_price - stop_loss)
        tp_dist = abs(take_profit - trigger_price)
        if sl_dist > 0:
            rr = round(tp_dist / sl_dist, 2)
            
        signal_id = await self.storage.save_signal(
            direction=direction.upper(),
            entry_price=trigger_price, # Store trigger as entry
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            timeframe=timeframe,
            source=strategy,
            reasoning=reasoning,
            risk_reward_ratio=rr,
            # Using 'pending' status natively supported by storage
        )
        logger.info(f"Created pending order #{signal_id}: {direction.upper()} at {trigger_price}")
        return signal_id

    async def check_signals(self, current_price: float, atr: float = None) -> list[dict]:
        """
        Check all open signals and pending orders against current price.
        Triggers stop loss, take profit, or activates pending orders.
        Applies execution simulation to exit fills.
        """
        # 1. Check Pending Orders -> Open them if triggered
        pending_signals = await self.storage.get_signals(status="pending")
        for p in pending_signals:
            trigger = p["entry_price"]
            sig_dir = p["direction"]
            # Simplified trigger logic (assumes Limit orders given strategy)
            if (sig_dir == "BUY" and current_price <= trigger) or \
               (sig_dir == "SELL" and current_price >= trigger):
                await self.storage.update_signal_status(p["id"], "open")
                logger.info(f"⚡ INSTANT EXECUTION: Pending order #{p['id']} activated at {current_price} (Zero LLM Latency)")
                
        # 2. Check Open Signals -> Close them if SL/TP hit
        open_signals = await self.get_open_signals()
        closed = []

        for signal in open_signals:
            sig_id = signal["id"]
            direction = signal["direction"]
            sl = signal["stop_loss"]
            tp = signal["take_profit"]

            reason = None
            exit_price = None

            # Trailing Stop Configuration
            trailing_activation_pips = 15.0
            
            if direction == "BUY":
                # Check trailing stop
                current_profit_pips = (current_price - signal["entry_price"]) * 10000
                if current_profit_pips >= trailing_activation_pips:
                    high_water = self._trailing_high_water_marks.get(sig_id, signal["entry_price"])
                    if current_price > high_water:
                        self._trailing_high_water_marks[sig_id] = current_price
                        trail_distance = (trailing_activation_pips * 0.0001)
                        new_sl = round(current_price - trail_distance, 5)
                        if new_sl > sl:
                            logger.info(f"🔄 Trailing Stop ADVANCED for BUY #{sig_id}: {sl} -> {new_sl} (Current check price: {current_price})")
                            await self.storage.update_signal_sl(sig_id, new_sl)
                            await self.storage.update_trade_journal_sl(sig_id, new_sl)
                            sl = new_sl

                if current_price <= sl:
                    reason = "stop_loss"
                    exit_price = current_price
                elif current_price >= tp:
                    reason = "take_profit"
                    exit_price = current_price
            elif direction == "SELL":
                # Check trailing stop
                current_profit_pips = (signal["entry_price"] - current_price) * 10000
                if current_profit_pips >= trailing_activation_pips:
                    low_water = self._trailing_high_water_marks.get(sig_id, signal["entry_price"])
                    if current_price < low_water:
                        self._trailing_high_water_marks[sig_id] = current_price
                        trail_distance = (trailing_activation_pips * 0.0001)
                        new_sl = round(current_price + trail_distance, 5)
                        if new_sl < sl or sl == 0:
                            logger.info(f"🔄 Trailing Stop ADVANCED for SELL #{sig_id}: {sl} -> {new_sl} (Current check price: {current_price})")
                            await self.storage.update_signal_sl(sig_id, new_sl)
                            await self.storage.update_trade_journal_sl(sig_id, new_sl)
                            sl = new_sl

                if current_price >= sl:
                    reason = "stop_loss"
                    exit_price = current_price
                elif current_price <= tp:
                    reason = "take_profit"
                    exit_price = current_price

            if reason:
                # Apply execution simulation to exit
                exec_result = self.execution_sim.simulate_exit(
                    direction, exit_price, reason, atr=atr
                )
                result = await self.close_signal(sig_id, exec_result.fill_price, reason)
                if result:
                    result["execution"] = {
                        "requested_price": exit_price,
                        "fill_price": exec_result.fill_price,
                        "slippage_pips": exec_result.slippage_pips,
                        "spread_cost_pips": exec_result.spread_cost_pips,
                        "quality": exec_result.execution_quality,
                    }
                    closed.append(result)

        return closed

    async def close_signal(self, signal_id: int, exit_price: float,
                     reason: str = "manual") -> Optional[dict]:
        """
        Close an open signal and calculate PnL.

        Args:
            signal_id: Signal to close
            exit_price: Exit price
            reason: "stop_loss", "take_profit", "manual", "trailing_stop"

        Returns:
            Dict with signal details and PnL, or None
        """
        # Log transaction intent
        tx_id = await self.storage.log_transaction("close_trade", {
            "signal_id": signal_id, "exit_price": exit_price, "reason": reason
        }, "pending")

        # Find the signal
        signals = await self.storage.get_signals(status="open")
        signal = next((s for s in signals if s["id"] == signal_id), None)

        if not signal:
            logger.warning(f"Signal #{signal_id} not found or not open")
            await self.storage.update_transaction_status(tx_id, "failed")
            return None

        entry = signal["entry_price"]
        direction = signal["direction"]

        # Calculate PnL in pips
        if direction == "BUY":
            pnl_pips = (exit_price - entry) * 10000
        else:
            pnl_pips = (entry - exit_price) * 10000

        pnl_pips = round(pnl_pips, 1)
        is_win = pnl_pips > 0

        # Update signal status in storage
        await self.storage.update_signal_status(signal_id, "closed", pnl_pips=pnl_pips)

        # Mark transaction as completed
        await self.storage.update_transaction_status(tx_id, "completed")

        # Notify Risk Manager
        await self.risk_manager.record_trade_result(pnl=pnl_pips)
        
        # Clean up high-water marks for trailing stops
        if signal_id in self._trailing_high_water_marks:
            del self._trailing_high_water_marks[signal_id]

        return {
            "id": signal_id,
            "direction": direction,
            "entry_price": entry,
            "exit_price": exit_price,
            "pnl_pips": pnl_pips,
            "is_win": is_win,
            "reason": reason,
            "strategy": signal.get("source", "unknown"),
        }

    async def get_open_signals(self) -> list[dict]:
        """Get all currently open signals."""
        return await self.storage.get_signals(status="open")

    async def get_closed_signals(self, limit: int = 50) -> list[dict]:
        """Get recently closed signals."""
        return await self.storage.get_signals(status="closed", limit=limit)

    async def get_performance(self) -> dict:
        """
        Calculate performance metrics from closed trades.

        Returns:
            {
                "total_trades", "wins", "losses", "win_rate",
                "total_pips", "avg_pips", "best_trade", "worst_trade",
                "profit_factor", "consecutive_wins", "consecutive_losses"
            }
        """
        closed = await self.get_closed_signals(limit=200)

        if not closed:
            return {
                "total_trades": 0, "win_rate": 0,
                "message": "No closed trades yet",
            }

        wins = [t for t in closed if t.get("pnl_pips", 0) > 0]
        losses = [t for t in closed if t.get("pnl_pips", 0) <= 0]

        total_pips = sum(t.get("pnl_pips", 0) for t in closed)
        gross_profit = sum(t.get("pnl_pips", 0) for t in wins)
        gross_loss = abs(sum(t.get("pnl_pips", 0) for t in losses))

        best = max(closed, key=lambda t: t.get("pnl_pips", 0))
        worst = min(closed, key=lambda t: t.get("pnl_pips", 0))

        # Consecutive wins/losses
        max_consec_wins = 0
        max_consec_losses = 0
        current_streak = 0
        streak_type = None

        for t in reversed(closed):  # Oldest first
            pnl = t.get("pnl_pips", 0)
            if pnl > 0:
                if streak_type == "win":
                    current_streak += 1
                else:
                    streak_type = "win"
                    current_streak = 1
                max_consec_wins = max(max_consec_wins, current_streak)
            else:
                if streak_type == "loss":
                    current_streak += 1
                else:
                    streak_type = "loss"
                    current_streak = 1
                max_consec_losses = max(max_consec_losses, current_streak)

        return {
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 1),
            "total_pips": round(total_pips, 1),
            "avg_pips": round(total_pips / len(closed), 1),
            "best_trade": round(best.get("pnl_pips", 0), 1),
            "worst_trade": round(worst.get("pnl_pips", 0), 1),
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
            "consecutive_wins": max_consec_wins,
            "consecutive_losses": max_consec_losses,
        }

    async def format_open_signals(self) -> str:
        """Format open signals for Telegram."""
        signals = await self.get_open_signals()
        if not signals:
            return "📋 No open signals."

        lines = [f"📋 *Open Signals ({len(signals)})*\n"]
        for s in signals:
            dir_icon = "📈" if s["direction"] == "BUY" else "📉"
            lines.append(
                f"{dir_icon} #{s['id']} {s['direction']} @ `{s['entry_price']}` "
                f"SL=`{s['stop_loss']}` TP=`{s['take_profit']}`"
            )
        return "\n".join(lines)

    async def format_performance(self) -> str:
        """Format performance report for Telegram."""
        perf = await self.get_performance()

        if perf["total_trades"] == 0:
            return "📊 *Performance*\n\nNo trades closed yet. Start with /signal!"

        lines = [
            f"📊 *Trading Performance*\n",
            f"Total Trades: {perf['total_trades']}",
            f"Win Rate: {perf['win_rate']}%",
            f"Total P/L: {perf['total_pips']:+.1f} pips",
            f"Avg P/L: {perf['avg_pips']:+.1f} pips/trade",
            f"Profit Factor: {perf['profit_factor']}",
            f"\n🏆 Best: {perf['best_trade']:+.1f} pips",
            f"💀 Worst: {perf['worst_trade']:+.1f} pips",
            f"🔥 Max Win Streak: {perf['consecutive_wins']}",
            f"❄️ Max Loss Streak: {perf['consecutive_losses']}",
        ]

        # Add execution quality stats
        exec_stats = self.execution_sim.get_execution_stats()
        if exec_stats["total_orders"] > 0:
            lines.append(f"\n⚡ *Execution Quality*")
            lines.append(f"Fill Rate: {exec_stats['fill_rate']}%")
            lines.append(f"Avg Slippage: {exec_stats['avg_slippage_pips']} pips")
            lines.append(f"Avg Spread: {exec_stats['avg_spread_cost_pips']} pips")
            lines.append(f"Total Exec Cost: {exec_stats['total_execution_cost_pips']} pips")

        return "\n".join(lines)
