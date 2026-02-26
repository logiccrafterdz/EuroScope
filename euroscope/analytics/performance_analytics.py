"""
Performance Analytics — Advanced Trading Metrics

Calculates Sharpe ratio, Sortino ratio, max drawdown, equity curve,
expectancy, and breakdowns by strategy/session/day-of-week.
Persists snapshots via Storage.save_performance_metric().
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..data.storage import Storage

logger = logging.getLogger("euroscope.analytics.performance")

# Trading sessions (UTC hours)
SESSIONS = {
    "Asia": (0, 8),
    "London": (8, 16),
    "New_York": (16, 24),
}


@dataclass
class PerformanceSnapshot:
    """Complete performance metrics snapshot."""
    period: str = "daily"
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    expectancy: float = 0.0
    avg_risk_reward: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_duration_hours: float = 0.0
    equity_curve: list[float] = field(default_factory=list)
    by_strategy: dict = field(default_factory=dict)
    by_day: dict = field(default_factory=dict)
    by_session: dict = field(default_factory=dict)


class PerformanceAnalytics:
    """
    Advanced performance analytics engine.

    Calculates comprehensive trading metrics from closed signals
    and persists periodic snapshots.
    """

    RISK_FREE_RATE = 0.0  # Annualized, for Sharpe/Sortino

    def __init__(self, storage: Storage):
        self.storage = storage

    async def calculate(self, period: str = "daily") -> PerformanceSnapshot:
        """
        Calculate full performance snapshot from closed trades in DB.
        """
        closed = await self.storage.get_signals(status="closed", limit=500)
        snap = self.compute_from_trades(closed)
        snap.period = period
        return snap

    def compute_from_trades(self, trades: list[dict]) -> PerformanceSnapshot:
        """
        Calculate metrics from a list of trade dictionaries.
        """
        snap = PerformanceSnapshot()
        if not trades:
            return snap

        # Basic counts
        pnls = [t.get("pnl_pips", 0) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        snap.total_trades = len(trades)
        snap.wins = len(wins)
        snap.losses = len(losses)
        snap.win_rate = round(len(wins) / len(trades) * 100, 1) if trades else 0
        snap.total_pnl = round(sum(pnls), 1)
        snap.avg_pnl = round(snap.total_pnl / len(trades), 1) if trades else 0
        snap.best_trade = round(max(pnls), 1) if pnls else 0
        snap.worst_trade = round(min(pnls), 1) if pnls else 0

        # Profit Factor
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        snap.profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

        # Equity Curve & Max Drawdown
        snap.equity_curve = self._build_equity_curve(pnls)
        snap.max_drawdown = self._max_drawdown(snap.equity_curve)
        peak = max(snap.equity_curve) if snap.equity_curve else 0
        snap.max_drawdown_pct = round(snap.max_drawdown / peak * 100, 1) if peak > 0 else 0

        # Sharpe Ratio (annualized, daily returns)
        snap.sharpe_ratio = self._sharpe_ratio(pnls)

        # Sortino Ratio
        snap.sortino_ratio = self._sortino_ratio(pnls)

        # Expectancy
        snap.expectancy = self._expectancy(wins, losses, snap.win_rate / 100)

        # Average Risk-Reward
        snap.avg_risk_reward = self._avg_risk_reward(trades)

        # Average Duration
        snap.avg_duration_hours = self._avg_duration(trades)

        # Breakdowns
        snap.by_strategy = self._breakdown_by_strategy(trades)
        snap.by_day = self._breakdown_by_day(trades)
        snap.by_session = self._breakdown_by_session(trades)

        return snap

    async def save_snapshot(self, snap: PerformanceSnapshot) -> int:
        """Persist a snapshot to the database."""
        return await self.storage.save_performance_metric(
            period=snap.period,
            total_signals=snap.total_trades,
            winning_signals=snap.wins,
            losing_signals=snap.losses,
            win_rate=snap.win_rate,
            total_pnl_pips=snap.total_pnl,
            avg_pnl_pips=snap.avg_pnl,
            max_drawdown_pips=snap.max_drawdown,
            profit_factor=snap.profit_factor,
            sharpe_ratio=snap.sharpe_ratio,
            avg_risk_reward=snap.avg_risk_reward,
            best_trade_pips=snap.best_trade,
            worst_trade_pips=snap.worst_trade,
            avg_trade_duration_hours=snap.avg_duration_hours,
        )

    async def get_latest(self, period: str = "daily") -> Optional[dict]:
        """Get the most recent saved snapshot."""
        return await self.storage.get_latest_metrics(period)

    # ── Metric Calculations ──────────────────────────────────

    @staticmethod
    def _build_equity_curve(pnls: list[float]) -> list[float]:
        """Build cumulative equity curve from P/L series."""
        curve = []
        cumulative = 0.0
        for p in pnls:
            cumulative += p
            curve.append(round(cumulative, 1))
        return curve

    @staticmethod
    def _max_drawdown(equity_curve: list[float]) -> float:
        """Calculate maximum drawdown in pips from equity curve."""
        if not equity_curve:
            return 0.0

        peak = equity_curve[0]
        max_dd = 0.0

        for val in equity_curve:
            if val > peak:
                peak = val
            dd = peak - val
            if dd > max_dd:
                max_dd = dd

        return round(max_dd, 1)

    @staticmethod
    def _sharpe_ratio(pnls: list[float], periods_per_year: int = 252) -> float:
        """
        Calculate annualized Sharpe ratio.

        Uses daily PnL values, annualized assuming 252 trading days.
        """
        if len(pnls) < 2:
            return 0.0

        mean = sum(pnls) / len(pnls)
        variance = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        std = math.sqrt(variance) if variance > 0 else 0

        if std == 0:
            return 0.0

        return round((mean / std) * math.sqrt(periods_per_year), 2)

    @staticmethod
    def _sortino_ratio(pnls: list[float], periods_per_year: int = 252) -> float:
        """
        Calculate Sortino ratio (only penalizes downside volatility).
        """
        if len(pnls) < 2:
            return 0.0

        mean = sum(pnls) / len(pnls)
        downside = [p for p in pnls if p < 0]

        if not downside:
            return float("inf") if mean > 0 else 0.0

        down_variance = sum(p ** 2 for p in downside) / len(downside)
        down_std = math.sqrt(down_variance)

        if down_std == 0:
            return 0.0

        return round((mean / down_std) * math.sqrt(periods_per_year), 2)

    @staticmethod
    def _expectancy(wins: list[float], losses: list[float], win_rate: float) -> float:
        """
        Calculate trade expectancy (expected pips per trade).

        E = (Win% × Avg Win) - (Loss% × Avg Loss)
        """
        if not wins and not losses:
            return 0.0

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0

        return round(win_rate * avg_win - (1 - win_rate) * avg_loss, 2)

    @staticmethod
    def _avg_risk_reward(closed: list[dict]) -> float:
        """Calculate average risk-reward ratio from closed trades."""
        rrs = [t.get("risk_reward_ratio", 0) for t in closed if t.get("risk_reward_ratio", 0) > 0]
        return round(sum(rrs) / len(rrs), 2) if rrs else 0.0

    @staticmethod
    def _avg_duration(closed: list[dict]) -> float:
        """Calculate average trade duration in hours."""
        durations = []
        for t in closed:
            created = t.get("created_at", "")
            closed_at = t.get("closed_at", "")
            if created and closed_at:
                try:
                    dt_open = datetime.fromisoformat(created)
                    dt_close = datetime.fromisoformat(closed_at)
                    hours = (dt_close - dt_open).total_seconds() / 3600
                    durations.append(hours)
                except (ValueError, TypeError):
                    pass
        return round(sum(durations) / len(durations), 1) if durations else 0.0

    # ── Breakdowns ───────────────────────────────────────────

    @staticmethod
    def _breakdown_by_strategy(closed: list[dict]) -> dict:
        """Group performance by strategy (source column)."""
        strategies: dict[str, list[float]] = {}
        for t in closed:
            strat = t.get("source", "unknown")
            strategies.setdefault(strat, []).append(t.get("pnl_pips", 0))

        result = {}
        for strat, pnls in strategies.items():
            wins = [p for p in pnls if p > 0]
            result[strat] = {
                "trades": len(pnls),
                "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
                "total_pnl": round(sum(pnls), 1),
            }
        return result

    @staticmethod
    def _breakdown_by_day(closed: list[dict]) -> dict:
        """Group performance by day of week."""
        days: dict[str, list[float]] = {}
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        for t in closed:
            created = t.get("created_at", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    day = day_names[dt.weekday()]
                    days.setdefault(day, []).append(t.get("pnl_pips", 0))
                except (ValueError, TypeError):
                    pass

        result = {}
        for day, pnls in days.items():
            result[day] = {
                "trades": len(pnls),
                "total_pnl": round(sum(pnls), 1),
            }
        return result

    @staticmethod
    def _breakdown_by_session(closed: list[dict]) -> dict:
        """Group performance by trading session (Asia/London/NY)."""
        sessions: dict[str, list[float]] = {}

        for t in closed:
            created = t.get("created_at", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    hour = dt.hour
                    session = "Unknown"
                    for name, (start, end) in SESSIONS.items():
                        if start <= hour < end:
                            session = name
                            break
                    sessions.setdefault(session, []).append(t.get("pnl_pips", 0))
                except (ValueError, TypeError):
                    pass

        result = {}
        for session, pnls in sessions.items():
            result[session] = {
                "trades": len(pnls),
                "total_pnl": round(sum(pnls), 1),
            }
        return result

    # ── Formatting ───────────────────────────────────────────

    def format_full_report(self, snap: PerformanceSnapshot) -> str:
        """Format a complete performance report for Telegram."""
        if snap.total_trades == 0:
            return "📊 *Performance Analytics*\n\nNo closed trades yet."

        lines = [
            "📊 *Performance Analytics*\n",
            f"📈 Total Trades: {snap.total_trades}",
            f"✅ Win Rate: {snap.win_rate}%",
            f"💰 Total P/L: {snap.total_pnl:+.1f} pips",
            f"📊 Avg P/L: {snap.avg_pnl:+.1f} pips/trade",
            f"🎯 Expectancy: {snap.expectancy:+.2f} pips",
            "",
            f"📉 Max Drawdown: {snap.max_drawdown:.1f} pips ({snap.max_drawdown_pct:.1f}%)",
            f"⚖️ Profit Factor: {snap.profit_factor}",
            f"📐 Sharpe Ratio: {snap.sharpe_ratio}",
            f"📐 Sortino Ratio: {snap.sortino_ratio}",
            f"📏 Avg R:R: {snap.avg_risk_reward}",
            "",
            f"🏆 Best: {snap.best_trade:+.1f} pips",
            f"💀 Worst: {snap.worst_trade:+.1f} pips",
        ]

        if snap.by_strategy:
            lines.append("\n📋 *By Strategy*")
            for strat, data in snap.by_strategy.items():
                lines.append(
                    f"  {strat}: {data['trades']} trades, "
                    f"{data['win_rate']}% WR, {data['total_pnl']:+.1f} pips"
                )

        if snap.by_session:
            lines.append("\n🕐 *By Session*")
            for session, data in snap.by_session.items():
                lines.append(
                    f"  {session}: {data['trades']} trades, "
                    f"{data['total_pnl']:+.1f} pips"
                )

        return "\n".join(lines)
