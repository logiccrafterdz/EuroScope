"""
Risk Manager — Position Sizing & Trade Risk Control

Calculates position sizes, stop losses, take profits, and enforces
drawdown limits for disciplined EUR/USD trading.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Optional

logger = logging.getLogger("euroscope.trading.risk_manager")


@dataclass
class RiskConfig:
    """Risk management configuration."""
    account_balance: float = 10000.0       # Account balance in USD
    risk_per_trade: float = 1.0            # Risk % per trade
    max_daily_drawdown: float = 3.0        # Max daily loss %
    max_open_trades: int = 3               # Max simultaneous positions
    max_consecutive_losses: int = 3        # Pause after N consecutive losses
    default_rr_ratio: float = 2.0          # Default risk:reward (1:2)
    pip_value: float = 10.0                # Value per pip for 1 standard lot
    min_stop_pips: float = 10.0            # Minimum stop loss in pips
    max_stop_pips: float = 100.0           # Maximum stop loss in pips


@dataclass
class TradeRisk:
    """Calculated risk parameters for a trade."""
    direction: str               # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_pips: float
    tp_pips: float
    risk_reward: float
    position_size: float         # In lots
    risk_amount: float           # Dollar amount at risk
    risk_score: int              # 1-10 (10 = highest risk)
    warnings: list[str] = field(default_factory=list)
    approved: bool = True        # Whether risk checks pass


class RiskManager:
    """
    Manages trade risk: position sizing, stop loss placement,
    and drawdown control.
    """

    def __init__(self, config: RiskConfig = None, storage: Optional['Storage'] = None):
        self.config = config or RiskConfig()
        self.storage = storage
        self._daily_pnl: float = 0.0
        self._daily_pnl_date: str = ""
        self._consecutive_losses: int = 0
        self._open_trade_count: int = 0

    async def load_state(self):
        """Load risk state from storage."""
        if not self.storage:
            return

        state = await self.storage.load_json("risk_manager_state")
        if state:
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            if state.get("daily_pnl_date") == today:
                self._daily_pnl = state.get("daily_pnl", 0.0)
                self._daily_pnl_date = today
            else:
                self._daily_pnl = 0.0
                self._daily_pnl_date = today
                
            self._consecutive_losses = state.get("consecutive_losses", 0)
            logger.info(f"RiskManager state loaded: PnL={self._daily_pnl:.2f}, Streak={self._consecutive_losses}")

    async def save_state(self):
        """Save risk state to storage."""
        if not self.storage:
            return

        state = {
            "daily_pnl": self._daily_pnl,
            "daily_pnl_date": self._daily_pnl_date,
            "consecutive_losses": self._consecutive_losses,
            "updated_at": datetime.now(UTC).isoformat()
        }
        await self.storage.save_json("risk_manager_state", state)
        logger.debug("RiskManager state saved.")

    # ─── Position Sizing ─────────────────────────────────────

    def calculate_position_size(
        self, stop_pips: float, *,
        atr: float = None, avg_atr: float = None,
        regime: str = None, regime_strength: float = 0.5,
    ) -> float:
        """
        Calculate position size with volatility and regime adaptation.

        Args:
            stop_pips: Distance to stop loss in pips
            atr: Current ATR value (for volatility scaling)
            avg_atr: Average ATR over lookback (for relative comparison)
            regime: Market regime ("trending", "ranging", "breakout")
            regime_strength: Confidence in regime classification (0-1)

        Returns:
            Position size in standard lots
        """
        if stop_pips <= 0:
            return 0.0

        base_risk_pct = self.config.risk_per_trade

        # ── ATR volatility scaling ──
        # High volatility → reduce size; low volatility → normal/slightly larger
        atr_factor = 1.0
        if atr and avg_atr and avg_atr > 0:
            atr_ratio = avg_atr / atr  # < 1 when vol is high, > 1 when low
            atr_factor = max(0.5, min(1.5, atr_ratio))
            logger.debug(f"ATR scaling: ratio={atr_ratio:.2f}, factor={atr_factor:.2f}")

        # ── Regime-aware scaling ──
        regime_factor = 1.0
        if regime:
            regime_factors = {
                "trending": 1.0,    # Full size in confirmed trends
                "ranging": 0.8,     # Smaller in choppy conditions
                "breakout": 0.7,    # Smaller on breakout attempts (higher risk)
            }
            base_factor = regime_factors.get(regime, 0.8)
            # Stronger regime confidence → closer to base_factor
            # Weak confidence → blend toward 0.8 (cautious)
            regime_factor = base_factor * regime_strength + 0.8 * (1 - regime_strength)
            logger.debug(f"Regime scaling: {regime} (str={regime_strength:.2f}), factor={regime_factor:.2f}")

        # ── Streak-based de-risking ──
        streak_factor = 1.0
        if self._consecutive_losses >= 3:
            streak_factor = 0.5
        elif self._consecutive_losses >= 2:
            streak_factor = 0.75

        # ── Combined adaptive risk ──
        adjusted_risk_pct = base_risk_pct * atr_factor * regime_factor * streak_factor
        adjusted_risk_pct = max(0.25, min(adjusted_risk_pct, base_risk_pct * 1.5))  # Clamp

        risk_amount = self.config.account_balance * (adjusted_risk_pct / 100)
        pip_value = self.calculate_pip_value()
        lots = risk_amount / (stop_pips * pip_value)

        result = round(max(0.01, min(lots, 10.0)), 2)
        logger.debug(
            f"Position size: {result} lots | risk={adjusted_risk_pct:.2f}% "
            f"(base={base_risk_pct}% × atr={atr_factor:.2f} × regime={regime_factor:.2f} × streak={streak_factor:.2f})"
        )
        return result

    @staticmethod
    def calculate_pip_value(lot_size: float = 1.0) -> float:
        """
        Calculate pip value for EUR/USD.

        For EUR/USD (USD quote currency):
        - Standard lot (1.0): $10.00 per pip
        - Mini lot (0.1): $1.00 per pip
        - Micro lot (0.01): $0.10 per pip
        """
        return lot_size * 10.0  # $10 per pip per standard lot for EUR/USD

    # ─── Stop Loss Calculation ───────────────────────────────

    def calculate_atr_stop(self, atr: float, direction: str,
                           entry_price: float, multiplier: float = 1.5) -> float:
        """
        Calculate stop loss based on ATR.

        Args:
            atr: Average True Range value
            direction: "BUY" or "SELL"
            entry_price: Entry price
            multiplier: ATR multiplier (default 1.5)

        Returns:
            Stop loss price
        """
        stop_distance = atr * multiplier

        if direction.upper() == "BUY":
            sl = entry_price - stop_distance
        else:
            sl = entry_price + stop_distance

        return round(sl, 5)

    def calculate_level_stop(self, direction: str, entry_price: float,
                             support_levels: list[float],
                             resistance_levels: list[float],
                             buffer_pips: float = 5.0) -> Optional[float]:
        """
        Calculate stop loss based on nearest support/resistance level.

        Places stop just beyond the nearest relevant level with a buffer.
        """
        buffer = buffer_pips * 0.0001  # Convert pips to price

        if direction.upper() == "BUY":
            # Stop below nearest support
            valid = [s for s in support_levels if s < entry_price]
            if valid:
                return round(valid[0] - buffer, 5)
        else:
            # Stop above nearest resistance
            valid = [r for r in resistance_levels if r > entry_price]
            if valid:
                return round(valid[0] + buffer, 5)

        return None

    # ─── Take Profit ─────────────────────────────────────────

    def calculate_take_profit(self, entry_price: float, stop_loss: float,
                              direction: str,
                              rr_ratio: float = None) -> float:
        """
        Calculate take profit based on risk:reward ratio.

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            direction: "BUY" or "SELL"
            rr_ratio: Risk-reward ratio (default from config)
        """
        rr = rr_ratio or self.config.default_rr_ratio
        risk_distance = abs(entry_price - stop_loss)
        reward_distance = risk_distance * rr

        if direction.upper() == "BUY":
            tp = entry_price + reward_distance
        else:
            tp = entry_price - reward_distance

        return round(tp, 5)

    # ─── Full Trade Risk Assessment ──────────────────────────

    def assess_trade(self, direction: str, entry_price: float,
                     atr: float = None, support: list[float] = None,
                     resistance: list[float] = None,
                     rr_ratio: float = None,
                     regime: str = None) -> TradeRisk:
        """
        Full risk assessment for a proposed trade.

        Returns a TradeRisk with position size, SL, TP, and risk score.
        """
        warnings = []
        approved = True

        # ── Calculate stop loss ──
        sl_atr = None
        sl_level = None

        if atr:
            sl_atr = self.calculate_atr_stop(atr, direction, entry_price)

        if support or resistance:
            sl_level = self.calculate_level_stop(
                direction, entry_price,
                support or [], resistance or []
            )

        # Choose the tighter stop (closer to entry)
        if sl_atr and sl_level:
            if direction.upper() == "BUY":
                stop_loss = max(sl_atr, sl_level)  # Higher = tighter for BUY
            else:
                stop_loss = min(sl_atr, sl_level)  # Lower = tighter for SELL
        elif sl_atr:
            stop_loss = sl_atr
        elif sl_level:
            stop_loss = sl_level
        else:
            # Fallback: 30 pip stop
            fallback_pips = 30 * 0.0001
            stop_loss = entry_price - fallback_pips if direction.upper() == "BUY" else entry_price + fallback_pips
            warnings.append("Using fallback 30-pip stop (no ATR/levels)")

        # ── Validate stop distance ──
        stop_pips = abs(entry_price - stop_loss) * 10000

        if stop_pips < self.config.min_stop_pips:
            stop_pips = self.config.min_stop_pips
            if direction.upper() == "BUY":
                stop_loss = entry_price - (stop_pips * 0.0001)
            else:
                stop_loss = entry_price + (stop_pips * 0.0001)
            warnings.append(f"Stop widened to minimum {self.config.min_stop_pips} pips")

        if stop_pips > self.config.max_stop_pips:
            warnings.append(f"⚠️ Stop too wide ({stop_pips:.0f} pips > max {self.config.max_stop_pips})")
            approved = False

        # ── Take profit ──
        take_profit = self.calculate_take_profit(entry_price, stop_loss, direction, rr_ratio)
        tp_pips = abs(take_profit - entry_price) * 10000
        rr = round(tp_pips / stop_pips, 2) if stop_pips > 0 else 0

        # ── Position sizing (volatility & regime adaptive) ──
        atr_data = None
        avg_atr_val = None
        if atr:
            atr_data = atr
            # Use atr as both current and avg if we don't have separate avg
            avg_atr_val = atr  # Caller can override
        position_size = self.calculate_position_size(
            stop_pips, atr=atr, avg_atr=avg_atr_val, regime=regime
        )
        risk_amount = round(self.config.account_balance * (self.config.risk_per_trade / 100), 2)

        # ── Drawdown checks ──
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._daily_pnl_date != today:
            self._daily_pnl = 0.0
            self._daily_pnl_date = today

        daily_loss_pct = abs(self._daily_pnl / self.config.account_balance * 100) if self._daily_pnl < 0 else 0
        if daily_loss_pct >= self.config.max_daily_drawdown:
            warnings.append(f"🛑 Daily drawdown limit reached ({daily_loss_pct:.1f}%)")
            approved = False

        if self._open_trade_count >= self.config.max_open_trades:
            warnings.append(f"🛑 Max open trades reached ({self._open_trade_count})")
            approved = False

        if self._consecutive_losses >= self.config.max_consecutive_losses:
            warnings.append(f"⚠️ {self._consecutive_losses} consecutive losses — consider pausing")

        # ── Risk score (1-10) ──
        risk_score = self._calculate_risk_score(stop_pips, rr, daily_loss_pct)

        return TradeRisk(
            direction=direction.upper(),
            entry_price=round(entry_price, 5),
            stop_loss=round(stop_loss, 5),
            take_profit=round(take_profit, 5),
            stop_pips=round(stop_pips, 1),
            tp_pips=round(tp_pips, 1),
            risk_reward=rr,
            position_size=position_size,
            risk_amount=risk_amount,
            risk_score=risk_score,
            warnings=warnings,
            approved=approved,
        )

    def _calculate_risk_score(self, stop_pips: float, rr: float,
                              daily_loss_pct: float) -> int:
        """Calculate risk score from 1 (low) to 10 (high)."""
        score = 3  # Base

        # Wide stop = more risk
        if stop_pips > 60:
            score += 2
        elif stop_pips > 40:
            score += 1

        # Poor R:R = more risk
        if rr < 1.0:
            score += 3
        elif rr < 1.5:
            score += 1

        # Accumulated daily losses
        if daily_loss_pct > 2.0:
            score += 2
        elif daily_loss_pct > 1.0:
            score += 1

        # Consecutive losses
        if self._consecutive_losses >= 2:
            score += 1

        return min(max(score, 1), 10)

    # ─── Trade Result Tracking ───────────────────────────────

    def record_trade_result(self, pnl: float):
        """Record a closed trade's PnL for drawdown tracking."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._daily_pnl_date != today:
            self._daily_pnl = 0.0
            self._daily_pnl_date = today
            
        self._daily_pnl += pnl

        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        if not self.storage:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.save_state())
        else:
            loop.create_task(self.save_state())

    def update_open_count(self, count: int):
        """Update the number of currently open trades."""
        self._open_trade_count = count

    def format_risk(self, trade: TradeRisk) -> str:
        """Format risk assessment for Telegram display."""
        icon = "🟢" if trade.approved else "🔴"
        dir_icon = "📈" if trade.direction == "BUY" else "📉"

        lines = [
            f"🛡️ *Risk Assessment*\n",
            f"{dir_icon} *{trade.direction}* at `{trade.entry_price}`",
            f"🔴 Stop Loss: `{trade.stop_loss}` ({trade.stop_pips:.0f} pips)",
            f"🟢 Take Profit: `{trade.take_profit}` ({trade.tp_pips:.0f} pips)",
            f"📊 R:R = 1:{trade.risk_reward}",
            f"📐 Position: {trade.position_size} lots",
            f"💰 Risk: ${trade.risk_amount}",
            f"⚡ Risk Score: {trade.risk_score}/10",
            f"\n{icon} **{'APPROVED' if trade.approved else 'BLOCKED'}**",
        ]

        if trade.warnings:
            lines.append("\n⚠️ *Warnings:*")
            for w in trade.warnings:
                lines.append(f"  {w}")

        return "\n".join(lines)
