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

Partial Exits:
    - Close 50% at 1:1 R:R
    - Trail remainder with chandelier
    - Time-based: reduce after N bars
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
    highest_price: float = 0.0
    lowest_price: float = 999.0
    trail_distance: float = 0.0
    moved_to_breakeven: bool = False
    updates: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    partial_exit_done: bool = False
    partial_exit_pips: float = 0.0
    time_reduce_done: bool = False
    bars_held: int = 0


@dataclass
class PartialExitAction:
    """Action to execute a partial exit."""
    trade_id: str
    close_fraction: float
    reason: str
    current_stop: float


class TrailingStopEngine:
    """
    Manages trailing stops for active trades.
    Adapts trail distance based on the chosen method and market conditions.
    Supports partial exits and time-based position reduction.
    """

    def __init__(
        self,
        default_method: TrailMethod = TrailMethod.ATR,
        atr_multiplier: float = 1.5,
        trail_pct: float = 0.003,
        breakeven_pips: float = 15.0,
        partial_exit_rr: float = 1.0,
        partial_exit_fraction: float = 0.5,
        time_reduce_bars: int = 0,
        time_reduce_fraction: float = 0.5,
    ):
        self.default_method = default_method
        self.atr_multiplier = atr_multiplier
        self.trail_pct = trail_pct
        self.breakeven_pips = breakeven_pips
        self.partial_exit_rr = partial_exit_rr
        self.partial_exit_fraction = partial_exit_fraction
        self.time_reduce_bars = time_reduce_bars
        self.time_reduce_fraction = time_reduce_fraction
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

    # ── Partial Exit ──────────────────────────────────────────

    def check_partial_exit(self, trade_id: str, current_price: float,
                           stop_pips: float = None) -> Optional[PartialExitAction]:
        """
        Check if partial exit should trigger (close 50% at 1:1 R:R).

        Returns PartialExitAction if triggered, None otherwise.
        """
        state = self._tracking.get(trade_id)
        if not state or state.partial_exit_done:
            return None

        if not stop_pips:
            stop_pips = abs(state.entry_price - state.initial_stop) * 10000

        is_buy = state.direction == "BUY"
        if is_buy:
            profit_pips = (current_price - state.entry_price) * 10000
        else:
            profit_pips = (state.entry_price - current_price) * 10000

        target_pips = stop_pips * self.partial_exit_rr

        if profit_pips >= target_pips - 0.1:
            state.partial_exit_done = True
            state.partial_exit_pips = profit_pips

            new_stop = state.entry_price + (0.0001 if is_buy else -0.0001)
            state.current_stop = round(new_stop, 5)
            state.moved_to_breakeven = True

            logger.info(
                f"📍 Partial exit triggered for {trade_id}: "
                f"close {self.partial_exit_fraction * 100:.0f}% at {profit_pips:+.1f} pips, "
                f"stop moved to breakeven"
            )

            return PartialExitAction(
                trade_id=trade_id,
                close_fraction=self.partial_exit_fraction,
                reason=f"1:{self.partial_exit_rr} R:R reached ({profit_pips:.1f} pips)",
                current_stop=state.current_stop,
            )

        return None

    # ── Time-Based Reduction ──────────────────────────────────

    def tick_bar(self, trade_id: str) -> Optional[PartialExitAction]:
        """
        Increment bar count and check for time-based reduction.

        After time_reduce_bars, closes fraction of position.
        """
        if self.time_reduce_bars <= 0:
            return None

        state = self._tracking.get(trade_id)
        if not state or state.time_reduce_done:
            return None

        state.bars_held += 1

        if state.bars_held >= self.time_reduce_bars:
            state.time_reduce_done = True
            logger.info(
                f"📍 Time-based reduction for {trade_id}: "
                f"close {self.time_reduce_fraction * 100:.0f}% after {state.bars_held} bars"
            )
            return PartialExitAction(
                trade_id=trade_id,
                close_fraction=self.time_reduce_fraction,
                reason=f"Time-based: {state.bars_held} bars held",
                current_stop=state.current_stop,
            )

        return None

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
