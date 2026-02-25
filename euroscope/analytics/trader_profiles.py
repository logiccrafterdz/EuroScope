"""
Virtual Trader Profiles for Behavioral Simulation.
These profiles do not trade real money. They listen to Orchestrator outputs
(signals and alerts) and record theoretical entries/exits to measure
the behavioral value of the assistant's insights.
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class VirtualTrade:
    trade_id: str
    direction: str
    entry_price: float
    entry_bar: int
    entry_time: str
    take_profit: float
    stop_loss: float
    exit_price: float = 0.0
    exit_bar: int = 0
    exit_time: str = ""
    pnl_pips: float = 0.0
    status: str = "open"
    reason: str = ""


class TraderProfile:
    """Base class for a behavioral evaluation profile."""
    name = "Base"
    description = "Generic profile"

    def __init__(self):
        self.trades: List[VirtualTrade] = []
        self.open_trade: Optional[VirtualTrade] = None
        self._trade_counter = 0

    def evaluate_signal(self, orchestrator_output: dict, current_price: float, bar_idx: int, timestamp: str) -> Optional[str]:
        """
        Evaluate an Orchestrator output.
        Returns a string reason if a trade was taken, else None.
        """
        raise NotImplementedError

    def manage_open_trade(self, current_price: float, bar_idx: int, timestamp: str, orchestrator_output: dict = None):
        """Check TP, SL, or invalidation signals."""
        if not self.open_trade:
            return

        t = self.open_trade
        # Basic TP/SL hit
        if t.direction == "BUY":
            if current_price >= t.take_profit:
                self._close_trade(current_price, bar_idx, timestamp, "TP Hit")
            elif current_price <= t.stop_loss:
                self._close_trade(current_price, bar_idx, timestamp, "SL Hit")
        else:
            if current_price <= t.take_profit:
                self._close_trade(current_price, bar_idx, timestamp, "TP Hit")
            elif current_price >= t.stop_loss:
                self._close_trade(current_price, bar_idx, timestamp, "SL Hit")

    def _open_trade(self, direction: str, price: float, sl: float, tp: float, bar_idx: int, timestamp: str, reason: str):
        self._trade_counter += 1
        t = VirtualTrade(
            trade_id=f"{self.name}-{self._trade_counter}",
            direction=direction,
            entry_price=price,
            entry_bar=bar_idx,
            entry_time=timestamp,
            stop_loss=sl,
            take_profit=tp,
            reason=reason
        )
        self.open_trade = t

    def _close_trade(self, price: float, bar_idx: int, timestamp: str, reason: str):
        if not self.open_trade:
            return
        t = self.open_trade
        t.exit_price = price
        t.exit_bar = bar_idx
        t.exit_time = timestamp
        t.status = "closed"
        
        if t.direction == "BUY":
            t.pnl_pips = (price - t.entry_price) * 10000
        else:
            t.pnl_pips = (t.entry_price - price) * 10000
            
        t.pnl_pips = round(t.pnl_pips, 1)
        self.trades.append(t)
        self.open_trade = None


class ScalperProfile(TraderProfile):
    name = "Scalper"
    description = "Hunts for short term momentum shifts (M15/H1). Enters on moderate confidence."

    def evaluate_signal(self, orchestrator_output: dict, current_price: float, bar_idx: int, timestamp: str):
        if self.open_trade:
            # Scalper bails quickly if sentiment flips
            signal = orchestrator_output.get("signal_data", {})
            new_dir = signal.get("direction", "WAIT").upper()
            if new_dir in ("BUY", "SELL") and new_dir != self.open_trade.direction:
                self._close_trade(current_price, bar_idx, timestamp, "Opposite Signal (Scalp Bail)")
            return None

        # Scalper enters easily
        signal = orchestrator_output.get("signal_data", {})
        direction = signal.get("direction", "WAIT").upper()
        conf = signal.get("raw_confidence", 0)

        # Scalper enters easily
        if direction in ("BUY", "SELL") and conf >= 50:
            sl_dist = 0.0015  # 15 pips tight SL
            tp_dist = 0.0020  # 20 pips fast TP
            if direction == "BUY":
                sl, tp = current_price - sl_dist, current_price + tp_dist
            else:
                sl, tp = current_price + sl_dist, current_price - tp_dist
            
            self._open_trade(direction, current_price, sl, tp, bar_idx, timestamp, f"Scalp {direction} conf={conf}")
            return f"{self.name} entered {direction}"
        return None


class SwingProfile(TraderProfile):
    name = "SwingTrader"
    description = "Only acts on high conviction structure shifts. Ignores M15 noise."

    def evaluate_signal(self, orchestrator_output: dict, current_price: float, bar_idx: int, timestamp: str):
        if self.open_trade:
            # Swing trader holds unless a major regime shift happens
            bias = orchestrator_output.get("technical", {}).get("overall_bias", "neutral")
            if self.open_trade.direction == "BUY" and bias == "bearish":
                self._close_trade(current_price, bar_idx, timestamp, "Bearish Regime Shift")
            elif self.open_trade.direction == "SELL" and bias == "bullish":
                self._close_trade(current_price, bar_idx, timestamp, "Bullish Regime Shift")
            return None

        signal = orchestrator_output.get("signal_data", {})
        direction = signal.get("direction", "WAIT").upper()
        conf = signal.get("raw_confidence", 0)

        # Swing needs high confidence
        if direction in ("BUY", "SELL") and conf >= 75:
            sl_dist = 0.0050  # 50 pips wide SL
            tp_dist = 0.0100  # 100 pips wide TP
            if direction == "BUY":
                sl, tp = current_price - sl_dist, current_price + tp_dist
            else:
                sl, tp = current_price + sl_dist, current_price - tp_dist
                
            self._open_trade(direction, current_price, sl, tp, bar_idx, timestamp, f"Swing {direction} conf={conf}")
            return f"{self.name} entered {direction}"
        return None
