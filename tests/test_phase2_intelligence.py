"""
Tests for Phase 2 Intelligence Skills: Multi-Timeframe Confluence & Correlation Monitor.
"""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import numpy as np
from datetime import datetime, UTC, timedelta

# Mock optional dependencies before imports
sys.modules.setdefault("yfinance", MagicMock())
sys.modules.setdefault("mplfinance", MagicMock())
sys.modules.setdefault("matplotlib", MagicMock())
sys.modules.setdefault("matplotlib.pyplot", MagicMock())

from euroscope.skills.base import SkillContext, SkillResult


# ── Helpers ──────────────────────────────────────────────────────────

def _make_candles(n=200, base_price=1.0800, trend="up"):
    """Generate realistic candle DataFrame."""
    dates = pd.date_range(end=datetime.now(UTC), periods=n, freq="1h")
    np.random.seed(42)
    noise = np.random.normal(0, 0.0005, n)
    if trend == "up":
        drift = np.linspace(0, 0.005, n)
    elif trend == "down":
        drift = np.linspace(0, -0.005, n)
    else:
        drift = np.zeros(n)
    
    close = base_price + drift + np.cumsum(noise)
    high = close + abs(np.random.normal(0.001, 0.0003, n))
    low = close - abs(np.random.normal(0.001, 0.0003, n))
    open_ = close + np.random.normal(0, 0.0003, n)
    volume = np.random.randint(1000, 10000, n).astype(float)
    
    return pd.DataFrame({
        "Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume
    }, index=dates)


# ── Multi-Timeframe Confluence Tests ──────────────────────────────────

class TestMultiTimeframeConfluence:
    """Test the MTF confluence skill."""

    def test_skill_metadata(self):
        from euroscope.skills.multi_timeframe_confluence.skill import MultiTimeframeConfluenceSkill
        skill = MultiTimeframeConfluenceSkill()
        assert skill.name == "multi_timeframe_confluence"
        assert "confluence" in skill.capabilities
        assert "check_alignment" in skill.capabilities

    @pytest.mark.asyncio
    async def test_no_provider_returns_error(self):
        from euroscope.skills.multi_timeframe_confluence.skill import MultiTimeframeConfluenceSkill
        skill = MultiTimeframeConfluenceSkill()
        ctx = SkillContext()
        result = await skill.execute(ctx, "confluence")
        assert not result.success
        assert "provider" in result.error.lower()

    @pytest.mark.asyncio
    async def test_confluence_all_bullish(self):
        from euroscope.skills.multi_timeframe_confluence.skill import MultiTimeframeConfluenceSkill
        skill = MultiTimeframeConfluenceSkill()
        
        # Mock provider returning bullish data for all timeframes
        provider = AsyncMock()
        provider.get_candles = AsyncMock(return_value=_make_candles(200, trend="up"))
        skill.set_price_provider(provider)
        
        ctx = SkillContext()
        result = await skill.execute(ctx, "confluence")
        
        assert result.success
        assert "verdict" in result.data
        assert result.data["timeframes_analyzed"] > 0
        assert "formatted" in result.metadata
        assert "confluence" in ctx.analysis

    @pytest.mark.asyncio
    async def test_confluence_mixed_signals(self):
        from euroscope.skills.multi_timeframe_confluence.skill import MultiTimeframeConfluenceSkill
        skill = MultiTimeframeConfluenceSkill()
        
        call_count = 0
        async def alternating_candles(**kwargs):
            nonlocal call_count
            call_count += 1
            trend = "up" if call_count % 2 == 0 else "down"
            return _make_candles(200, trend=trend)
        
        provider = AsyncMock()
        provider.get_candles = AsyncMock(side_effect=alternating_candles)
        skill.set_price_provider(provider)
        
        ctx = SkillContext()
        result = await skill.execute(ctx, "confluence")
        assert result.success
        # With alternating signals, confidence should be lower
        assert result.data["confidence"] <= 95

    @pytest.mark.asyncio
    async def test_check_alignment_action(self):
        from euroscope.skills.multi_timeframe_confluence.skill import MultiTimeframeConfluenceSkill
        skill = MultiTimeframeConfluenceSkill()
        
        provider = AsyncMock()
        provider.get_candles = AsyncMock(return_value=_make_candles(200, trend="up"))
        skill.set_price_provider(provider)
        
        ctx = SkillContext()
        result = await skill.execute(ctx, "check_alignment")
        assert result.success
        assert "aligned" in result.data
        assert "direction" in result.data

    @pytest.mark.asyncio
    async def test_insufficient_data_handled(self):
        from euroscope.skills.multi_timeframe_confluence.skill import MultiTimeframeConfluenceSkill
        skill = MultiTimeframeConfluenceSkill()
        
        provider = AsyncMock()
        provider.get_candles = AsyncMock(return_value=_make_candles(10))  # Too few candles
        skill.set_price_provider(provider)
        
        ctx = SkillContext()
        result = await skill.execute(ctx, "confluence")
        # Should either fail gracefully or succeed with error notes
        if result.success:
            assert len(result.data.get("errors", [])) > 0

    @pytest.mark.asyncio
    async def test_context_metadata_set(self):
        from euroscope.skills.multi_timeframe_confluence.skill import MultiTimeframeConfluenceSkill
        skill = MultiTimeframeConfluenceSkill()
        
        provider = AsyncMock()
        provider.get_candles = AsyncMock(return_value=_make_candles(200, trend="down"))
        skill.set_price_provider(provider)
        
        ctx = SkillContext()
        result = await skill.execute(ctx, "confluence")
        assert result.success
        assert "mtf_bias" in ctx.metadata
        assert "mtf_confidence" in ctx.metadata
        assert ctx.metadata["mtf_bias"] in ("BULLISH", "BEARISH", "MIXED")

    def test_extract_signals(self):
        from euroscope.skills.multi_timeframe_confluence.skill import MultiTimeframeConfluenceSkill
        skill = MultiTimeframeConfluenceSkill()
        
        ta = {
            "overall_bias": "Bullish",
            "indicators": {
                "RSI": {"value": 65, "signal": "Bullish"},
                "MACD": {"signal_text": "Bullish Crossover"},
                "EMA": {"trend": "Bullish"},
                "ADX": {"value": 30},
            }
        }
        signals = skill._extract_signals(ta, "H1")
        assert signals["rsi"]["signal"] == "BULLISH"
        assert signals["macd"]["signal"] == "BULLISH"
        assert signals["ema"]["signal"] == "BULLISH"
        assert signals["adx"]["trending"] is True

    def test_compute_confluence_all_bullish(self):
        from euroscope.skills.multi_timeframe_confluence.skill import MultiTimeframeConfluenceSkill
        skill = MultiTimeframeConfluenceSkill()
        
        tf_results = {}
        for tf in ["M15", "H1", "H4", "D1"]:
            tf_results[tf] = {
                "timeframe": tf,
                "rsi": {"value": 65, "signal": "BULLISH"},
                "macd": {"signal": "BULLISH"},
                "ema": {"signal": "BULLISH", "trend": "up"},
                "adx": {"value": 30, "trending": True},
                "overall_bias": "BULLISH",
            }
        
        result = skill._compute_confluence(tf_results)
        assert result["verdict"] == "BULLISH"
        assert result["confidence"] > 50
        assert result["timeframes_aligned"] == 4


# ── Correlation Monitor Tests ──────────────────────────────────────

class TestCorrelationMonitor:
    """Test the correlation monitor skill."""

    def test_skill_metadata(self):
        from euroscope.skills.correlation_monitor.skill import CorrelationMonitorSkill
        skill = CorrelationMonitorSkill()
        assert skill.name == "correlation_monitor"
        assert "check_correlations" in skill.capabilities
        assert "detect_divergence" in skill.capabilities

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        from euroscope.skills.correlation_monitor.skill import CorrelationMonitorSkill
        skill = CorrelationMonitorSkill()
        ctx = SkillContext()
        result = await skill.execute(ctx, "invalid_action")
        assert not result.success

    @pytest.mark.asyncio
    async def test_check_correlations_with_mock_data(self):
        from euroscope.skills.correlation_monitor.skill import CorrelationMonitorSkill
        skill = CorrelationMonitorSkill()
        ctx = SkillContext()
        
        dates = pd.date_range(end=datetime.now(UTC), periods=30, freq="1D")
        np.random.seed(42)
        
        # EUR/USD data
        eurusd_data = pd.DataFrame(
            {"Close": 1.08 + np.cumsum(np.random.normal(0, 0.002, 30))},
            index=dates
        )
        
        # DXY data (inverse)
        dxy_data = pd.DataFrame(
            {"Close": 104.0 - np.cumsum(np.random.normal(0, 0.1, 30))},
            index=dates
        )
        
        gold_data = pd.DataFrame(
            {"Close": 2000 + np.cumsum(np.random.normal(0, 5, 30))},
            index=dates
        )
        
        tnx_data = pd.DataFrame(
            {"Close": 4.2 + np.cumsum(np.random.normal(0, 0.02, 30))},
            index=dates
        )
        
        download_map = {
            "EURUSD=X": eurusd_data,
            "DX-Y.NYB": dxy_data,
            "GC=F": gold_data,
            "^TNX": tnx_data,
        }
        
        def mock_download(ticker, **kwargs):
            return download_map.get(ticker, pd.DataFrame())
        
        mock_yf_module = MagicMock()
        mock_yf_module.download = mock_download
        
        with patch.dict("sys.modules", {"yfinance": mock_yf_module}):
            # Need a fresh import to pick up our mock
            import importlib
            import euroscope.skills.correlation_monitor.skill as corr_mod
            importlib.reload(corr_mod)
            skill_cls = corr_mod.CorrelationMonitorSkill
            skill = skill_cls()
            ctx = SkillContext()
            result = await skill.execute(ctx, "check_correlations")
        
        assert result.success
        assert "instruments" in result.data
        assert "divergences" in result.data
        assert "correlations" in ctx.analysis

    @pytest.mark.asyncio
    async def test_detect_divergence_action(self):
        from euroscope.skills.correlation_monitor.skill import CorrelationMonitorSkill
        skill = CorrelationMonitorSkill()
        ctx = SkillContext()
        
        dates = pd.date_range(end=datetime.now(UTC), periods=30, freq="1D")
        np.random.seed(42)
        
        eurusd_data = pd.DataFrame(
            {"Close": 1.08 + np.cumsum(np.random.normal(0, 0.002, 30))},
            index=dates
        )
        
        # All instruments return same-direction data (unusual divergence)
        same_data = pd.DataFrame(
            {"Close": 100 + np.cumsum(np.random.normal(0, 0.5, 30))},
            index=dates
        )
        
        def mock_download(ticker, **kwargs):
            if ticker == "EURUSD=X":
                return eurusd_data
            return same_data
        
        mock_yf_module = MagicMock()
        mock_yf_module.download = mock_download
        
        with patch.dict("sys.modules", {"yfinance": mock_yf_module}):
            import importlib
            import euroscope.skills.correlation_monitor.skill as corr_mod
            importlib.reload(corr_mod)
            skill = corr_mod.CorrelationMonitorSkill()
            ctx = SkillContext()
            result = await skill.execute(ctx, "detect_divergence")
        
        assert result.success
        assert "has_divergence" in result.data

    def test_rolling_corr(self):
        from euroscope.skills.correlation_monitor.skill import CorrelationMonitorSkill
        a = pd.Series(np.random.randn(50))
        b = pd.Series(np.random.randn(50))
        result = CorrelationMonitorSkill._rolling_corr(a, b, 20)
        assert result is not None
        assert -1.0 <= result <= 1.0

    def test_rolling_corr_insufficient_data(self):
        from euroscope.skills.correlation_monitor.skill import CorrelationMonitorSkill
        a = pd.Series([1, 2, 3])
        b = pd.Series([4, 5, 6])
        result = CorrelationMonitorSkill._rolling_corr(a, b, 20)
        assert result is None

    def test_format_correlations(self):
        from euroscope.skills.correlation_monitor.skill import CorrelationMonitorSkill
        skill = CorrelationMonitorSkill()
        
        data = {
            "instruments": {
                "DX-Y.NYB": {
                    "label": "DXY (Dollar Index)",
                    "correlation_full": -0.82,
                    "expected": -0.85,
                    "is_diverging": False,
                    "eur_direction": "UP",
                    "instrument_direction": "DOWN",
                    "emoji": "💵",
                },
            },
            "divergences": [],
            "divergence_count": 0,
        }
        
        formatted = skill._format_correlations(data)
        assert "Correlation Monitor" in formatted
        assert "DXY" in formatted
        assert "Normal" in formatted


# ── Auto-Discovery Test ──────────────────────────────────────────

class TestPhase2Discovery:
    """Verify new skills are auto-discovered by the registry."""

    def test_new_skills_discoverable(self):
        from euroscope.skills.registry import SkillsRegistry
        registry = SkillsRegistry()
        discovered = registry.discover()
        
        assert "multi_timeframe_confluence" in discovered, \
            f"multi_timeframe_confluence not found in: {discovered}"
        assert "correlation_monitor" in discovered, \
            f"correlation_monitor not found in: {discovered}"

    def test_new_skills_have_providers(self):
        from euroscope.skills.registry import SkillsRegistry
        registry = SkillsRegistry()
        registry.discover()
        
        mtf = registry.get("multi_timeframe_confluence")
        assert mtf is not None
        assert hasattr(mtf, "set_price_provider")
        
        corr = registry.get("correlation_monitor")
        assert corr is not None
        assert hasattr(corr, "set_price_provider")
