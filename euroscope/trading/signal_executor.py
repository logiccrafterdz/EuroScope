"""
Signal Executor — Paper Trading Order Management

Manages the lifecycle of trading signals: open, monitor, close.
Tracks PnL and performance metrics. Uses existing Storage API.
"""

import logging
from datetime import datetime
from typing import Optional

from ..data.storage import Storage

logger = logging.getLogger("euroscope.trading.signal_executor")


class SignalExecutor:
    """
    Manages trading signals through their full lifecycle.

    Paper trading only — no real orders. Persists signals to DB
    and tracks performance via Storage.save_signal / get_signals.
    """

    def __init__(self, storage: Storage):
        self.storage = storage

    def open_signal(self, direction: str, entry_price: float,
                    stop_loss: float, take_profit: float,
                    strategy: str = "manual", timeframe: str = "H1",
                    confidence: float = 50.0, reasoning: str = "") -> int:
        """
        Open a new trading signal (paper trade).

        Args:
            strategy: stored in the 'source' column of trading_signals

        Returns:
            Signal ID
        """
        rr = 0.0
        sl_dist = abs(entry_price - stop_loss)
        tp_dist = abs(take_profit - entry_price)
        if sl_dist > 0:
            rr = round(tp_dist / sl_dist, 2)

        signal_id = self.storage.save_signal(
            direction=direction.upper(),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            timeframe=timeframe,
            source=strategy,
            reasoning=reasoning,
            risk_reward_ratio=rr,
        )

        # Set status to 'open' (default is 'pending')
        self.storage.update_signal_status(signal_id, "open")

        logger.info(
            f"Opened signal #{signal_id}: {direction.upper()} @ {entry_price} "
            f"SL={stop_loss} TP={take_profit} ({strategy})"
        )

        return signal_id

    def check_signals(self, current_price: float) -> list[dict]:
        """
        Check all open signals against current price.

        Triggers stop loss or take profit if hit.

        Returns:
            List of closed signal dicts with PnL
        """
        open_signals = self.get_open_signals()
        closed = []

        for signal in open_signals:
            sig_id = signal["id"]
            direction = signal["direction"]
            sl = signal["stop_loss"]
            tp = signal["take_profit"]

            reason = None
            exit_price = None

            if direction == "BUY":
                if current_price <= sl:
                    reason = "stop_loss"
                    exit_price = sl
                elif current_price >= tp:
                    reason = "take_profit"
                    exit_price = tp
            elif direction == "SELL":
                if current_price >= sl:
                    reason = "stop_loss"
                    exit_price = sl
                elif current_price <= tp:
                    reason = "take_profit"
                    exit_price = tp

            if reason:
                result = self.close_signal(sig_id, exit_price, reason)
                if result:
                    closed.append(result)

        return closed

    def close_signal(self, signal_id: int, exit_price: float,
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
        # Find the signal
        signals = self.storage.get_signals(status="open")
        signal = next((s for s in signals if s["id"] == signal_id), None)

        if not signal:
            logger.warning(f"Signal #{signal_id} not found or not open")
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

        # Update in DB — store reason in reasoning via pnl_pips
        self.storage.update_signal_status(signal_id, "closed", pnl_pips=pnl_pips)

        logger.info(
            f"Closed signal #{signal_id}: {direction} "
            f"{'✅' if is_win else '❌'} {pnl_pips:+.1f} pips ({reason})"
        )

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

    def get_open_signals(self) -> list[dict]:
        """Get all currently open signals."""
        return self.storage.get_signals(status="open")

    def get_closed_signals(self, limit: int = 50) -> list[dict]:
        """Get recently closed signals."""
        return self.storage.get_signals(status="closed", limit=limit)

    def get_performance(self) -> dict:
        """
        Calculate performance metrics from closed trades.

        Returns:
            {
                "total_trades", "wins", "losses", "win_rate",
                "total_pips", "avg_pips", "best_trade", "worst_trade",
                "profit_factor", "consecutive_wins", "consecutive_losses"
            }
        """
        closed = self.get_closed_signals(limit=200)

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

    def format_open_signals(self) -> str:
        """Format open signals for Telegram."""
        signals = self.get_open_signals()
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

    def format_performance(self) -> str:
        """Format performance report for Telegram."""
        perf = self.get_performance()

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

        return "\n".join(lines)
