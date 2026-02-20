"""
Trailing Stop Engine — Dynamic stop-loss management.

Moves the stop loss as price moves in favor, locking in profits
while giving the trade room to breathe. Supports multiple
trailing strategies adapted to market conditions.

Strategies:
    - ATR-based: trails at N × ATR behind price
    - Percentage: trails at a fixed percentage behind price
    - Chandelier: trails from the highest high (BUY) or lowest low (SELL)
    - Breakeven: moves to breakeven once price reaches a pip threshold
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional
from enum import Enum

logger = logging.getLogger("euroscope.trading.trailing_stop")


class TrailMethod(Enum):
    ATR = "atr"
    PERCENTAGE = "percentage"
    CHANDELIER = "chandelier"
    BREAKEVEN = "breakeven"


@dataclass
class TrailingState:
    """State for a single trailing stop tracker."""
    trade_id: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    initial_stop: float
    current_stop: float
    method: TrailMethod
    highest_price: float = 0.0  # For BUY: highest since entry
    lowest_price: float = 999.0  # For SELL: lowest since entry
    trail_distance: float = 0.0  # Current trail distance in price
    moved_to_breakeven: bool = False
    updates: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))


class TrailingStopEngine:
    """
    Manages trailing stops for active trades.
    Adapts trail distance based on the chosen method and market conditions.
    """

    def __init__(
        self,
        default_method: TrailMethod = TrailMethod.ATR,
        atr_multiplier: float = 1.5,
        trail_pct: float = 0.003,  # 0.3% for forex
        breakeven_pips: float = 15.0,
    ):
        self.default_method = default_method
        self.atr_multiplier = atr_multiplier
        self.trail_pct = trail_pct
        self.breakeven_pips = breakeven_pips
        self._tracking: dict[str, TrailingState] = {}

    # ── Registration ───────────────────────────────────────────

    def register_trade(
        self,
        trade_id: str,
        direction: str,
        entry_price: float,
        initial_stop: float,
        method: TrailMethod = None,
        atr_value: float = None,
    ) -> TrailingState:
        """
        Start tracking a trailing stop for a trade.

        Args:
            trade_id: Unique trade identifier
            direction: "BUY" or "SELL"
            entry_price: Entry price
            initial_stop: Initial stop loss price
            method: Trailing method (defaults to engine default)
            atr_value: Current ATR (required for ATR method)
        """
        m = method or self.default_method

        trail_dist = self._calc_initial_trail(m, entry_price, initial_stop, atr_value)

        state = TrailingState(
            trade_id=trade_id,
            direction=direction.upper(),
            entry_price=entry_price,
            initial_stop=initial_stop,
            current_stop=initial_stop,
            method=m,
            highest_price=entry_price if direction.upper() == "BUY" else 999.0,
            lowest_price=entry_price if direction.upper() == "SELL" else 0.0,
            trail_distance=trail_dist,
        )
        self._tracking[trade_id] = state
        logger.info(
            f"📍 Trailing stop registered: {trade_id} ({m.value}) "
            f"stop={initial_stop:.5f} trail={trail_dist:.5f}"
        )
        return state

    # ── Update ─────────────────────────────────────────────────

    def update(
        self,
        trade_id: str,
        current_price: float,
        atr_value: float = None,
    ) -> Optional[TrailingState]:
        """
        Update a trailing stop with the latest price.

        Returns updated state if stop moved, None if unchanged.
        """
        state = self._tracking.get(trade_id)
        if not state:
            return None

        is_buy = state.direction == "BUY"
        moved = False

        # Update high/low watermarks
        if is_buy:
            if current_price > state.highest_price:
                state.highest_price = current_price
        else:
            if current_price < state.lowest_price:
                state.lowest_price = current_price

        # Calculate new stop based on method
        new_stop = self._calculate_new_stop(state, current_price, atr_value)

        # Only move stop in favorable direction (never away)
        if is_buy and new_stop > state.current_stop:
            state.current_stop = round(new_stop, 5)
            moved = True
        elif not is_buy and new_stop < state.current_stop:
            state.current_stop = round(new_stop, 5)
            moved = True

        # Check breakeven upgrade
        if not state.moved_to_breakeven:
            be_stop = self._check_breakeven(state, current_price)
            if be_stop is not None:
                if is_buy and be_stop > state.current_stop:
                    state.current_stop = round(be_stop, 5)
                    state.moved_to_breakeven = True
                    moved = True
                elif not is_buy and be_stop < state.current_stop:
                    state.current_stop = round(be_stop, 5)
                    state.moved_to_breakeven = True
                    moved = True

        if moved:
            state.updates += 1
            state.last_updated = datetime.now(UTC)
            pnl_pips = self._pnl_pips(state)
            logger.debug(
                f"📍 Trail update {trade_id}: stop → {state.current_stop:.5f} "
                f"(locked {pnl_pips:+.1f} pips)"
            )

        return state if moved else None

    def update_all(self, current_price: float, atr_value: float = None) -> list[TrailingState]:
        """Update all tracked trades. Returns list of states that moved."""
        moved = []
        for tid in list(self._tracking.keys()):
            result = self.update(tid, current_price, atr_value)
            if result:
                moved.append(result)
        return moved

    # ── Stop Calculation ───────────────────────────────────────

    def _calculate_new_stop(
        self, state: TrailingState, price: float, atr: float = None
    ) -> float:
        """Calculate the ideal new stop based on method."""
        is_buy = state.direction == "BUY"

        if state.method == TrailMethod.ATR:
            if atr and atr > 0:
                dist = atr * self.atr_multiplier
            else:
                dist = state.trail_distance
            anchor = state.highest_price if is_buy else state.lowest_price
            return anchor - dist if is_buy else anchor + dist

        elif state.method == TrailMethod.PERCENTAGE:
            anchor = state.highest_price if is_buy else state.lowest_price
            dist = anchor * self.trail_pct
            return anchor - dist if is_buy else anchor + dist

        elif state.method == TrailMethod.CHANDELIER:
            # Like ATR but from highest/lowest
            dist = state.trail_distance
            if atr and atr > 0:
                dist = atr * self.atr_multiplier
            anchor = state.highest_price if is_buy else state.lowest_price
            return anchor - dist if is_buy else anchor + dist

        # Default: don't move
        return state.current_stop

    def _check_breakeven(self, state: TrailingState, price: float) -> Optional[float]:
        """Check if we should move to breakeven."""
        is_buy = state.direction == "BUY"
        pips_in_favor = (price - state.entry_price) * 10_000 if is_buy else (state.entry_price - price) * 10_000

        if pips_in_favor >= self.breakeven_pips:
            # Move to entry + 1 pip buffer
            buffer = 0.0001  # 1 pip
            return state.entry_price + buffer if is_buy else state.entry_price - buffer
        return None

    def _calc_initial_trail(
        self, method: TrailMethod, entry: float, stop: float, atr: float = None
    ) -> float:
        """Calculate initial trail distance."""
        if method == TrailMethod.ATR and atr:
            return atr * self.atr_multiplier
        elif method == TrailMethod.PERCENTAGE:
            return entry * self.trail_pct
        else:
            return abs(entry - stop)

    # ── Queries ────────────────────────────────────────────────

    def get_state(self, trade_id: str) -> Optional[TrailingState]:
        return self._tracking.get(trade_id)

    def get_all_states(self) -> list[TrailingState]:
        return list(self._tracking.values())

    def is_stopped_out(self, trade_id: str, current_price: float) -> bool:
        """Check if the current price has hit the trailing stop."""
        state = self._tracking.get(trade_id)
        if not state:
            return False
        if state.direction == "BUY":
            return current_price <= state.current_stop
        return current_price >= state.current_stop

    def remove_trade(self, trade_id: str):
        """Remove a trade from tracking."""
        self._tracking.pop(trade_id, None)

    def _pnl_pips(self, state: TrailingState) -> float:
        """Calculate locked-in P/L in pips from stop position."""
        diff = state.current_stop - state.entry_price
        if state.direction == "SELL":
            diff = -diff
        return round(diff * 10_000, 1)

    # ── Formatting ─────────────────────────────────────────────

    def format_status(self) -> str:
        """Format all trailing stops for Telegram display."""
        states = self.get_all_states()
        if not states:
            return "📍 *Trailing Stops*\n\nNo active trailing stops."

        lines = ["📍 *Trailing Stops*", ""]
        for s in states:
            pnl = self._pnl_pips(s)
            be = "🔒 BE" if s.moved_to_breakeven else ""
            icon = "🟢" if pnl > 0 else "🔴"
            lines.append(
                f"{icon} `{s.trade_id}` ({s.direction}) — "
                f"Stop: `{s.current_stop:.5f}` ({pnl:+.1f}p) "
                f"{be}"
            )
            lines.append(
                f"   Method: `{s.method.value}` | Updates: `{s.updates}`"
            )
        return "\n".join(lines)
