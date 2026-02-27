"""
Execution Simulator — Realistic Paper Trade Execution

Applies spread, slippage, and fill simulation to paper trades,
making performance metrics more realistic. Real execution typically
degrades raw numbers by 20-40%.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("euroscope.trading.execution_simulator")


@dataclass
class ExecutionConfig:
    """Configuration for execution simulation."""
    # Spread (EUR/USD typical: 1.0-1.5 pips, widens in volatility)
    spread_pips: float = 1.2
    spread_volatility_factor: float = 0.3  # How much spread widens with ATR
    max_spread_pips: float = 5.0

    # Slippage
    slippage_mean_pips: float = 0.3
    slippage_std_pips: float = 0.5
    max_slippage_pips: float = 3.0

    # Slippage multipliers by exit reason
    sl_slippage_mult: float = 1.8    # Stop losses get worse fills (market order in momentum)
    tp_slippage_mult: float = 0.3    # Take profits get better fills (limit order)
    manual_slippage_mult: float = 1.0

    # Fill simulation
    fill_rate: float = 0.98  # 98% base fill rate

    # Enabled flag (allows disabling for backtests that want raw numbers)
    enabled: bool = True


@dataclass
class ExecutionResult:
    """Result of an execution simulation."""
    filled: bool
    requested_price: float
    fill_price: float
    slippage_pips: float
    spread_cost_pips: float
    total_cost_pips: float   # slippage + spread
    execution_quality: str   # "excellent", "good", "fair", "poor"
    details: str = ""


class ExecutionSimulator:
    """
    Simulates realistic order execution for paper trading.

    Models three key effects that degrade real trading performance:
    1. Spread — bid/ask gap costs on every entry/exit
    2. Slippage — price moves between order submission and fill
    3. Fill rate — occasional order rejections
    """

    def __init__(self, config: ExecutionConfig = None):
        self.config = config or ExecutionConfig()
        # Track stats
        self._total_entries = 0
        self._total_exits = 0
        self._total_slippage = 0.0
        self._total_spread_cost = 0.0
        self._rejections = 0
        self._fills = 0

    def simulate_entry(
        self, direction: str, price: float,
        atr: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Simulate order entry with spread and slippage.

        BUY: Fill above requested price (pay ask)
        SELL: Fill below requested price (receive bid)
        """
        if not self.config.enabled:
            return ExecutionResult(
                filled=True, requested_price=price, fill_price=price,
                slippage_pips=0, spread_cost_pips=0, total_cost_pips=0,
                execution_quality="simulated", details="Simulation disabled",
            )

        self._total_entries += 1

        # Check fill rate
        if random.random() > self.config.fill_rate:
            self._rejections += 1
            logger.info(f"Entry REJECTED: {direction} @ {price} (fill rate simulation)")
            return ExecutionResult(
                filled=False, requested_price=price, fill_price=price,
                slippage_pips=0, spread_cost_pips=0, total_cost_pips=0,
                execution_quality="rejected", details="Order not filled (market rejection)",
            )

        # Calculate spread
        spread = self._get_spread(atr)
        half_spread = spread / 2

        # Calculate slippage (entry = moderate)
        slippage = self._get_slippage(1.0)

        # Apply to price
        if direction.upper() == "BUY":
            fill_price = price + (half_spread + slippage) * 0.0001
        else:
            fill_price = price - (half_spread + slippage) * 0.0001

        fill_price = round(fill_price, 5)
        total_cost = half_spread + slippage

        self._fills += 1
        self._total_slippage += slippage
        self._total_spread_cost += half_spread

        quality = self._assess_quality(total_cost)

        logger.debug(
            f"Entry {direction}: {price} → {fill_price} "
            f"(spread={half_spread:.1f}, slip={slippage:.1f}, quality={quality})"
        )

        return ExecutionResult(
            filled=True,
            requested_price=price,
            fill_price=fill_price,
            slippage_pips=round(slippage, 2),
            spread_cost_pips=round(half_spread, 2),
            total_cost_pips=round(total_cost, 2),
            execution_quality=quality,
            details=f"Spread: {half_spread:.1f} pips, Slippage: {slippage:.1f} pips",
        )

    def simulate_exit(
        self, direction: str, price: float, reason: str,
        atr: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Simulate order exit with reason-specific slippage.

        - stop_loss: WORSE fills (market order against momentum)
        - take_profit: BETTER fills (limit order, passive fill)
        - manual: moderate fills
        """
        if not self.config.enabled:
            return ExecutionResult(
                filled=True, requested_price=price, fill_price=price,
                slippage_pips=0, spread_cost_pips=0, total_cost_pips=0,
                execution_quality="simulated", details="Simulation disabled",
            )

        self._total_exits += 1

        # Reason-specific slippage multiplier
        multipliers = {
            "stop_loss": self.config.sl_slippage_mult,
            "take_profit": self.config.tp_slippage_mult,
            "manual": self.config.manual_slippage_mult,
            "trailing_stop": self.config.sl_slippage_mult * 0.8,  # Slightly better than hard SL
        }
        mult = multipliers.get(reason, 1.0)

        # Calculate spread and slippage
        spread = self._get_spread(atr)
        half_spread = spread / 2
        slippage = self._get_slippage(mult)

        # Apply exit slippage (exits are always adverse)
        if direction.upper() == "BUY":
            # Closing a BUY = selling → fill below price
            fill_price = price - (half_spread + slippage) * 0.0001
        else:
            # Closing a SELL = buying → fill above price
            fill_price = price + (half_spread + slippage) * 0.0001

        fill_price = round(fill_price, 5)
        total_cost = half_spread + slippage

        self._fills += 1
        self._total_slippage += slippage
        self._total_spread_cost += half_spread

        quality = self._assess_quality(total_cost)

        logger.debug(
            f"Exit {direction} ({reason}): {price} → {fill_price} "
            f"(spread={half_spread:.1f}, slip={slippage:.1f}, quality={quality})"
        )

        return ExecutionResult(
            filled=True,
            requested_price=price,
            fill_price=fill_price,
            slippage_pips=round(slippage, 2),
            spread_cost_pips=round(half_spread, 2),
            total_cost_pips=round(total_cost, 2),
            execution_quality=quality,
            details=f"{reason}: spread={half_spread:.1f}, slip={slippage:.1f} pips",
        )

    def _get_spread(self, atr: Optional[float] = None) -> float:
        """
        Calculate current spread in pips.
        Widens under high volatility (ATR-adaptive).
        """
        base_spread = self.config.spread_pips

        if atr:
            # EUR/USD avg ATR ≈ 0.005 (50 pips)
            avg_atr = 0.005
            atr_ratio = atr / avg_atr
            # High vol → wider spread
            vol_adjustment = 1.0 + (atr_ratio - 1.0) * self.config.spread_volatility_factor
            spread = base_spread * max(0.8, min(vol_adjustment, 3.0))
        else:
            spread = base_spread

        # Add small randomness
        spread += random.uniform(-0.2, 0.3)
        return max(0.5, min(spread, self.config.max_spread_pips))

    def _get_slippage(self, multiplier: float = 1.0) -> float:
        """
        Generate slippage in pips using Normal distribution.
        Slippage is always >= 0 (negative slippage = price improvement, rare).
        """
        slip = random.gauss(
            self.config.slippage_mean_pips * multiplier,
            self.config.slippage_std_pips * multiplier,
        )
        # 10% chance of price improvement (negative slippage)
        if random.random() < 0.10:
            slip = -abs(slip) * 0.3  # Small improvement
        else:
            slip = abs(slip)  # Normal adverse slippage

        return max(-0.5, min(slip, self.config.max_slippage_pips))

    def _assess_quality(self, total_cost_pips: float) -> str:
        """Assess execution quality based on total cost."""
        if total_cost_pips <= 0.5:
            return "excellent"
        elif total_cost_pips <= 1.0:
            return "good"
        elif total_cost_pips <= 2.0:
            return "fair"
        else:
            return "poor"

    def get_execution_stats(self) -> dict:
        """Get cumulative execution statistics."""
        total_orders = self._fills + self._rejections
        return {
            "total_orders": total_orders,
            "filled": self._fills,
            "rejected": self._rejections,
            "fill_rate": round(self._fills / total_orders * 100, 1) if total_orders > 0 else 100.0,
            "avg_slippage_pips": round(self._total_slippage / self._fills, 2) if self._fills > 0 else 0,
            "avg_spread_cost_pips": round(self._total_spread_cost / self._fills, 2) if self._fills > 0 else 0,
            "total_execution_cost_pips": round(self._total_slippage + self._total_spread_cost, 1),
        }

    def format_stats(self) -> str:
        """Format execution stats for display."""
        s = self.get_execution_stats()
        return (
            f"⚡ **Execution Quality**\n"
            f"├ Orders: {s['total_orders']} ({s['filled']} filled, {s['rejected']} rejected)\n"
            f"├ Fill Rate: {s['fill_rate']}%\n"
            f"├ Avg Slippage: {s['avg_slippage_pips']} pips\n"
            f"├ Avg Spread: {s['avg_spread_cost_pips']} pips\n"
            f"└ Total Execution Cost: {s['total_execution_cost_pips']} pips"
        )
