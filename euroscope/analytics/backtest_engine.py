"""
Backtest Engine — Historical Strategy Testing

Replays historical candles through StrategyEngine → RiskManager
to simulate trades and measure strategy performance.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from ..analysis.technical import TechnicalAnalyzer
from ..analysis.patterns import PatternDetector
from ..analysis.levels import LevelAnalyzer
from ..trading.risk_manager import RiskManager, RiskConfig
from ..trading.strategy_engine import StrategyEngine

logger = logging.getLogger("euroscope.analytics.backtest")


@dataclass
class BacktestTrade:
    """A single simulated trade."""
    direction: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    exit_price: float = 0.0
    pnl_pips: float = 0.0
    is_win: bool = False
    strategy: str = ""
    entry_bar: int = 0
    exit_bar: int = 0
    slippage_pips: float = 0.0


@dataclass
class BacktestResult:
    """Complete backtest result."""
    strategy: str = "all"
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    equity_curve: list[float] = field(default_factory=list)
    trades: list[BacktestTrade] = field(default_factory=list)
    bars_tested: int = 0


class BacktestEngine:
    """
    Replays historical candles through strategy + risk management.

    Simulates paper trades and collects performance metrics.
    """

    def __init__(self, risk_config: Optional[RiskConfig] = None):
        self.technical = TechnicalAnalyzer()
        self.patterns = PatternDetector()
        self.levels = LevelAnalyzer()
        self.strategy_engine = StrategyEngine()
        self.risk_manager = RiskManager(risk_config or RiskConfig())

    def run(self, candles: list[dict], strategy_filter: Optional[str] = None,
            lookback: int = 50, slippage_pips: float = 1.5,
            commission_pips: float = 0.7, slippage_enabled: bool = True) -> BacktestResult:
        """
        Run a backtest on historical candles.

        Args:
            candles: List of OHLCV dicts with 'open', 'high', 'low', 'close'
            strategy_filter: Only test this strategy (or all if None)
            lookback: Min bars for indicator warmup
            slippage_pips: Pips to subtract from each trade's profit
            commission_pips: Pips to subtract per round turn

        Returns:
            BacktestResult with complete metrics
        """
        result = BacktestResult(
            strategy=strategy_filter or "all",
            bars_tested=len(candles),
        )

        if len(candles) < lookback + 10:
            logger.warning("Not enough candles for backtest")
            return result

        open_trade: Optional[BacktestTrade] = None

        for i in range(lookback, len(candles)):
            current = candles[i]
            price = current["close"]
            high = current["high"]
            low = current["low"]

            # If we have an open trade, check SL/TP
            if open_trade:
                applied_slippage = open_trade.slippage_pips if slippage_enabled else 0.0
                closed = self._check_exit(open_trade, high, low, i, slippage=applied_slippage, commission=commission_pips)
                if closed:
                    result.trades.append(closed)
                    open_trade = None
                continue  # Only one trade at a time

            # Convert candle window to DataFrame for analysis
            window = candles[max(0, i - lookback):i + 1]
            df = pd.DataFrame(window).rename(columns={
                "open": "Open", "high": "High",
                "low": "Low", "close": "Close",
                "volume": "Volume",
            })

            # Generate strategy signal
            ta = self.technical.analyze(df)
            sr = self.levels.find_support_resistance(df)
            detected = self.patterns.detect_all(df)

            indicators = {
                "adx": ta.get("indicators", {}).get("ADX", {}).get("value"),
                "rsi": ta.get("indicators", {}).get("RSI", {}).get("value"),
                "overall_bias": ta.get("overall_bias"),
                "macd": ta.get("indicators", {}).get("MACD", {}),
            }

            if indicators["adx"] is None or indicators["rsi"] is None:
                continue

            levels_data = {
                "current_price": price,
                "support": sr.get("support", []),
                "resistance": sr.get("resistance", []),
            }

            sig = self.strategy_engine.detect_strategy(indicators, levels_data, detected)

            # Apply filter
            if strategy_filter and sig.strategy != strategy_filter:
                continue

            if sig.direction not in ("BUY", "SELL"):
                continue

            if sig.confidence < 50:
                continue

            # Risk assessment
            atr = ta.get("indicators", {}).get("ATR", {}).get("value")
            trade_risk = self.risk_manager.assess_trade(
                sig.direction, price, atr=atr,
                support=sr.get("support", []),
                resistance=sr.get("resistance", []),
            )

            if not trade_risk.approved:
                continue

            slippage_pips_applied = 0.0
            slippage_price = 0.0
            if slippage_enabled:
                volume = df["Volume"].iloc[-1] if "Volume" in df.columns else None
                avg_volume = df["Volume"].tail(20).mean() if "Volume" in df.columns else None
                regime = self._get_volatility_regime(
                    indicators,
                    volume,
                    avg_volume,
                    deviation_triggered=current.get("deviation_triggered"),
                    emergency_mode=current.get("emergency_mode"),
                    regime_override=current.get("volatility_regime"),
                )
                slippage_pips_applied, slippage_price = self._calculate_realistic_slippage(
                    regime, base_normal=slippage_pips
                )

            entry_price, stop_loss, take_profit = self._simulate_fill(
                sig.direction,
                price,
                trade_risk.stop_loss,
                trade_risk.take_profit,
                slippage_price,
            )

            # Open virtual trade
            open_trade = BacktestTrade(
                direction=sig.direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy=sig.strategy,
                entry_bar=i,
                slippage_pips=slippage_pips_applied,
            )

        # Close any remaining open trade at last bar's close
        if open_trade:
            last_price = candles[-1]["close"]
            open_trade.exit_price = last_price
            open_trade.exit_bar = len(candles) - 1
            if open_trade.direction == "BUY":
                open_trade.pnl_pips = round((last_price - open_trade.entry_price) * 10000, 1)
            else:
                open_trade.pnl_pips = round((open_trade.entry_price - last_price) * 10000, 1)
            open_trade.is_win = open_trade.pnl_pips > 0
            result.trades.append(open_trade)

        # Calculate summary metrics
        self._compute_metrics(result)
        return result

    def run_fast(self, candles: list[dict], strategy_filter: Optional[str] = None,
                 lookback: int = 50, slippage_pips: float = 1.0,
                 commission_pips: float = 0.5) -> BacktestResult:
        """
        Fast backtest — pre-computes all indicators once as arrays,
        then iterates through pre-computed values.

        ~50x faster than run() because it avoids creating DataFrames
        and re-computing indicators for each bar.
        """
        result = BacktestResult(
            strategy=strategy_filter or "all",
            bars_tested=len(candles),
        )

        if len(candles) < lookback + 10:
            logger.warning("Not enough candles for backtest")
            return result

        # ── Step 1: Build ONE DataFrame from all candles ──
        df = pd.DataFrame(candles).rename(columns={
            "open": "Open", "high": "High",
            "low": "Low", "close": "Close",
            "volume": "Volume",
        })

        close = df["Close"].astype(float)
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        n = len(df)

        # ── Step 2: Pre-compute ALL indicators as arrays (ONE pass) ──
        from ..analysis.technical import rsi, macd, ema, bollinger_bands, atr, adx

        rsi_arr = rsi(close)
        macd_data = macd(close)
        macd_hist = macd_data["histogram"]
        ema20_arr = ema(close, 20)
        ema50_arr = ema(close, 50)
        bb = bollinger_bands(close)
        bb_upper = bb["upper"]
        bb_lower = bb["lower"]
        bb_middle = bb["middle"]
        atr_arr = atr(high, low, close)
        adx_arr = adx(high, low, close)
        # Rolling average ATR (14-period lookback)
        atr_avg14 = atr_arr.rolling(14, min_periods=1).mean()
        # Simple S/R from rolling highs/lows (20-period window)
        rolling_high = high.rolling(20, min_periods=5).max()
        rolling_low = low.rolling(20, min_periods=5).min()

        logger.debug(f"Fast backtest: pre-computed {n} bars of indicators")

        # ── Step 3: Iterate through pre-computed values ──
        open_trade: Optional[BacktestTrade] = None

        for i in range(lookback, n):
            c_price = float(close.iloc[i])
            c_high = float(high.iloc[i])
            c_low = float(low.iloc[i])

            # Check open trade SL/TP
            if open_trade:
                closed = self._check_exit(open_trade, c_high, c_low, i,
                                          slippage=slippage_pips, commission=commission_pips)
                if closed:
                    result.trades.append(closed)
                    open_trade = None
                continue

            # Build indicators dict from pre-computed arrays
            r = float(rsi_arr.iloc[i]) if not pd.isna(rsi_arr.iloc[i]) else None
            a = float(adx_arr.iloc[i]) if not pd.isna(adx_arr.iloc[i]) else None
            a_prev = float(adx_arr.iloc[i-1]) if i > 0 and not pd.isna(adx_arr.iloc[i-1]) else None
            e20 = float(ema20_arr.iloc[i]) if not pd.isna(ema20_arr.iloc[i]) else None
            e50 = float(ema50_arr.iloc[i]) if not pd.isna(ema50_arr.iloc[i]) else None
            hist = float(macd_hist.iloc[i]) if not pd.isna(macd_hist.iloc[i]) else None
            atr_v = float(atr_arr.iloc[i]) if not pd.isna(atr_arr.iloc[i]) else None
            atr_a = float(atr_avg14.iloc[i]) if not pd.isna(atr_avg14.iloc[i]) else None
            bb_u = float(bb_upper.iloc[i]) if not pd.isna(bb_upper.iloc[i]) else None
            bb_l = float(bb_lower.iloc[i]) if not pd.isna(bb_lower.iloc[i]) else None

            if r is None or a is None:
                continue

            # Determine overall bias from EMAs + RSI
            if e20 and e50:
                if c_price > e20 > e50 and r > 50:
                    bias = "bullish"
                elif c_price < e20 < e50 and r < 50:
                    bias = "bearish"
                else:
                    bias = "neutral"
            else:
                bias = "neutral"

            indicators = {
                "adx": a,
                "adx_prev": a_prev,
                "rsi": r,
                "overall_bias": bias,
                "ema_20": e20,
                "ema_50": e50,
                "macd": {"histogram_latest": hist},
                "atr": {"current": atr_v, "avg_14": atr_a},
                "bollinger": {
                    "upper": bb_u,
                    "lower": bb_l,
                    "current_price": c_price,
                },
            }

            # Simple S/R from rolling highs/lows
            res_level = float(rolling_high.iloc[i]) if not pd.isna(rolling_high.iloc[i]) else c_price + 0.005
            sup_level = float(rolling_low.iloc[i]) if not pd.isna(rolling_low.iloc[i]) else c_price - 0.005

            levels_data = {
                "current_price": c_price,
                "support": [sup_level],
                "resistance": [res_level],
            }

            # Detect strategy (cheap — just conditional logic)
            sig = self.strategy_engine.detect_strategy(indicators, levels_data, [])

            if strategy_filter and sig.strategy != strategy_filter:
                continue
            if sig.direction not in ("BUY", "SELL"):
                continue
            if sig.confidence < 50:
                continue

            # Risk assessment
            trade_risk = self.risk_manager.assess_trade(
                sig.direction, c_price, atr=atr_v,
                support=[sup_level],
                resistance=[res_level],
            )

            if not trade_risk.approved:
                continue

            # Simulate fill with slippage
            slip_price = slippage_pips * 0.0001
            entry_price, stop_loss, take_profit = self._simulate_fill(
                sig.direction, c_price,
                trade_risk.stop_loss, trade_risk.take_profit,
                slip_price,
            )

            open_trade = BacktestTrade(
                direction=sig.direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy=sig.strategy,
                entry_bar=i,
                slippage_pips=slippage_pips,
            )

        # Close remaining trade
        if open_trade:
            last_price = float(close.iloc[-1])
            open_trade.exit_price = last_price
            open_trade.exit_bar = n - 1
            if open_trade.direction == "BUY":
                open_trade.pnl_pips = round((last_price - open_trade.entry_price) * 10000, 1)
            else:
                open_trade.pnl_pips = round((open_trade.entry_price - last_price) * 10000, 1)
            open_trade.is_win = open_trade.pnl_pips > 0
            result.trades.append(open_trade)

        self._compute_metrics(result)
        return result

    def compare_strategies(self, candles: list[dict],
                            strategies: list[str] = None,
                            slippage: float = 1.5,
                            commission: float = 0.7,
                            slippage_enabled: bool = True) -> dict[str, BacktestResult]:
        """
        Run backtest for multiple strategies on the same data.

        Args:
            candles: Historical candle data
            strategies: List of strategy names to compare
            slippage: Realistic slippage in pips
            commission: Realistic commission in pips

        Returns:
            Dict mapping strategy name → BacktestResult
        """
        if strategies is None:
            strategies = ["trend_following", "mean_reversion", "breakout"]

        results = {}
        for strat in strategies:
            results[strat] = self.run(candles, strategy_filter=strat, 
                                      slippage_pips=slippage, 
                                      commission_pips=commission,
                                      slippage_enabled=slippage_enabled)
        return results

    def walk_forward_analysis(self, candles: list[dict], strategy: str,
                               window_size: int = 500, step_size: int = 100,
                               slippage: float = 1.5,
                               commission: float = 0.7,
                               slippage_enabled: bool = True) -> list[BacktestResult]:
        """
        Perform Walk-Forward analysis by running backtests on sliding windows.

        Args:
            candles: Total historical data
            strategy: Strategy to test
            window_size: Size of the rolling window
            step_size: How much to slide the window forward
        """
        results = []
        for start in range(0, len(candles) - window_size + 1, step_size):
            end = start + window_size
            window_candles = candles[start:end]
            res = self.run(window_candles, strategy_filter=strategy,
                           slippage_pips=slippage, commission_pips=commission,
                           slippage_enabled=slippage_enabled)
            results.append(res)
        return results

    # ── Internal ─────────────────────────────────────────────

    @staticmethod
    def _get_volatility_regime(indicators: dict, volume: Optional[float],
                               avg_volume: Optional[float],
                               deviation_triggered: bool = False,
                               emergency_mode: bool = False,
                               regime_override: Optional[str] = None) -> str:
        if regime_override in ("normal", "elevated", "high", "extreme"):
            return regime_override
        if emergency_mode:
            return "extreme"
        if deviation_triggered:
            return "high"

        adx = indicators.get("adx")
        volume_ratio = None
        if volume is not None and avg_volume and avg_volume > 0:
            volume_ratio = volume / avg_volume

        if (adx is not None and adx > 35) or (volume_ratio is not None and volume_ratio > 3.0):
            return "high"
        if (adx is not None and 25 <= adx <= 35) or (volume_ratio is not None and 1.5 <= volume_ratio <= 3.0):
            return "elevated"
        if (adx is not None and adx < 25) and (volume_ratio is None or volume_ratio < 1.5):
            return "normal"
        if volume_ratio is not None and volume_ratio < 1.5:
            return "normal"
        return "elevated"

    @staticmethod
    def _calculate_realistic_slippage(regime: str, base_normal: float = 1.5) -> tuple[float, float]:
        default_map = {
            "normal": 1.5,
            "elevated": 2.5,
            "high": 4.0,
            "extreme": 7.0,
        }
        scale = base_normal / 1.5 if base_normal else 0.0
        base = default_map.get(regime, 1.5) * scale
        slippage_price = base * 0.0001
        return round(base, 2), slippage_price

    @staticmethod
    def _simulate_fill(direction: str, entry_price: float,
                       stop_loss: float, take_profit: float,
                       slippage_price: float) -> tuple[float, float, float]:
        if slippage_price == 0:
            return entry_price, stop_loss, take_profit
        if direction == "BUY":
            return entry_price + slippage_price, stop_loss + slippage_price, take_profit + slippage_price
        return entry_price - slippage_price, stop_loss - slippage_price, take_profit - slippage_price

    @staticmethod
    def _check_exit(trade: BacktestTrade, high: float, low: float,
                    bar_idx: int, slippage: float = 0.0,
                    commission: float = 0.0) -> Optional[BacktestTrade]:
        """Check if a bar's high/low hits SL or TP."""
        total_cost = slippage + commission
        if trade.direction == "BUY":
            if low <= trade.stop_loss:
                trade.exit_price = trade.stop_loss
                trade.pnl_pips = round((trade.stop_loss - trade.entry_price) * 10000 - total_cost, 1)
                trade.is_win = trade.pnl_pips > 0
                trade.exit_bar = bar_idx
                return trade
            if high >= trade.take_profit:
                trade.exit_price = trade.take_profit
                trade.pnl_pips = round((trade.take_profit - trade.entry_price) * 10000 - total_cost, 1)
                trade.is_win = trade.pnl_pips > 0
                trade.exit_bar = bar_idx
                return trade
        else:  # SELL
            if high >= trade.stop_loss:
                trade.exit_price = trade.stop_loss
                trade.pnl_pips = round((trade.entry_price - trade.stop_loss) * 10000 - total_cost, 1)
                trade.is_win = trade.pnl_pips > 0
                trade.exit_bar = bar_idx
                return trade
            if low <= trade.take_profit:
                trade.exit_price = trade.take_profit
                trade.pnl_pips = round((trade.entry_price - trade.take_profit) * 10000 - total_cost, 1)
                trade.is_win = trade.pnl_pips > 0
                trade.exit_bar = bar_idx
                return trade

        return None

    @staticmethod
    def _compute_metrics(result: BacktestResult):
        """Compute summary metrics from trades list."""
        if not result.trades:
            return

        pnls = [t.pnl_pips for t in result.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        result.total_trades = len(pnls)
        result.wins = len(wins)
        result.losses = len(losses)
        result.win_rate = round(len(wins) / len(pnls) * 100, 1)
        result.total_pnl = round(sum(pnls), 1)
        result.avg_pnl = round(result.total_pnl / len(pnls), 1)
        result.best_trade = round(max(pnls), 1) if pnls else 0
        result.worst_trade = round(min(pnls), 1) if pnls else 0

        # Profit Factor
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        result.profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

        # Equity Curve & Max DD
        cumulative = 0.0
        curve = []
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            cumulative += p
            curve.append(round(cumulative, 1))
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        result.equity_curve = curve
        result.max_drawdown = round(max_dd, 1)

        # Sharpe
        if len(pnls) >= 2:
            mean = sum(pnls) / len(pnls)
            variance = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
            std = math.sqrt(variance) if variance > 0 else 0
            result.sharpe_ratio = round((mean / std) * math.sqrt(252), 2) if std > 0 else 0

    # ── Formatting ───────────────────────────────────────────

    @staticmethod
    def format_result(result: BacktestResult) -> str:
        """Format backtest result for Telegram."""
        if result.total_trades == 0:
            return f"📊 *Backtest: {result.strategy}*\n\nNo trades generated ({result.bars_tested} bars)."

        lines = [
            f"📊 *Backtest: {result.strategy.replace('_', ' ').title()}*\n",
            f"📈 Bars Tested: {result.bars_tested}",
            f"📋 Total Trades: {result.total_trades}",
            f"✅ Win Rate: {result.win_rate}%",
            f"💰 Total P/L: {result.total_pnl:+.1f} pips",
            f"📊 Avg P/L: {result.avg_pnl:+.1f} pips/trade",
            f"📉 Max Drawdown: {result.max_drawdown:.1f} pips",
            f"⚖️ Profit Factor: {result.profit_factor}",
            f"📐 Sharpe: {result.sharpe_ratio}",
            f"🏆 Best: {result.best_trade:+.1f} | 💀 Worst: {result.worst_trade:+.1f}",
        ]

        return "\n".join(lines)

    @staticmethod
    def format_comparison(results: dict[str, BacktestResult]) -> str:
        """Format strategy comparison table."""
        lines = ["📊 *Strategy Comparison*\n"]

        for name, r in results.items():
            icon = "🟢" if r.total_pnl > 0 else "🔴" if r.total_pnl < 0 else "⚪"
            lines.append(
                f"{icon} *{name.replace('_', ' ').title()}*: "
                f"{r.total_trades} trades, {r.win_rate}% WR, "
                f"{r.total_pnl:+.1f} pips, PF={r.profit_factor}"
            )

        return "\n".join(lines)
