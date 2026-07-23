"""
Tests for COT 3-Stage Filter Pipeline.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from euroscope.skills.cot_positioning.skill import COTPositioningSkill
from euroscope.skills.base import SkillContext


class TestStage1ExtremeDetection:

    def test_bullish_extreme(self):
        result = COTPositioningSkill._stage1_extreme_detection(150000)
        assert result["is_extreme"] is True
        assert "bullish" in result["direction"]
        assert result["confidence"] > 60

    def test_bearish_extreme(self):
        result = COTPositioningSkill._stage1_extreme_detection(-150000)
        assert result["is_extreme"] is True
        assert "bearish" in result["direction"]
        assert result["confidence"] > 60

    def test_normal_positioning(self):
        result = COTPositioningSkill._stage1_extreme_detection(50000)
        assert result["is_extreme"] is False
        assert result["direction"] == "normal"

    def test_zero_positioning(self):
        result = COTPositioningSkill._stage1_extreme_detection(0)
        assert result["is_extreme"] is False

    def test_borderline_bullish(self):
        result = COTPositioningSkill._stage1_extreme_detection(100000)
        assert result["is_extreme"] is False


class TestStage2MacroConfirmation:

    def test_no_extreme_no_confirm(self):
        ctx = SkillContext()
        stage1 = {"is_extreme": False}
        result = COTPositioningSkill._stage2_macro_confirmation(ctx, stage1)
        assert result["confirmed"] is False

    def test_extreme_with_high_vol_confirms(self):
        ctx = SkillContext()
        ctx.metadata["macro_quality"] = "complete"
        ctx.metadata["volatility"] = "high"
        stage1 = {"is_extreme": True}
        result = COTPositioningSkill._stage2_macro_confirmation(ctx, stage1)
        assert result["confirmed"] is True
        assert "high_volatility" in result["indicators"]

    def test_extreme_without_macro_no_confirm(self):
        ctx = SkillContext()
        ctx.metadata["macro_quality"] = "minimal"
        stage1 = {"is_extreme": True}
        result = COTPositioningSkill._stage2_macro_confirmation(ctx, stage1)
        assert result["confirmed"] is False


class TestStage3OrderflowTiming:

    def test_no_extreme_no_timing(self):
        ctx = SkillContext()
        stage1 = {"is_extreme": False}
        result = COTPositioningSkill._stage3_orderflow_timing(ctx, stage1)
        assert result["timing_ok"] is False

    def test_extreme_with_sweep_ok(self):
        ctx = SkillContext()
        ctx.analysis["microstructure"] = {"liquidity_sweep_detected": True}
        stage1 = {"is_extreme": True}
        result = COTPositioningSkill._stage3_orderflow_timing(ctx, stage1)
        assert result["timing_ok"] is True
        assert "liquidity_sweep" in result["indicators"]

    def test_extreme_with_volume_ok(self):
        ctx = SkillContext()
        ctx.analysis["microstructure"] = {"volume_expansion": True}
        stage1 = {"is_extreme": True}
        result = COTPositioningSkill._stage3_orderflow_timing(ctx, stage1)
        assert result["timing_ok"] is True
        assert "volume_expansion" in result["indicators"]


class TestFilterSignal:

    @pytest.mark.asyncio
    async def test_filter_signal_no_cache(self):
        skill = COTPositioningSkill()
        skill.provider = MagicMock()
        skill.provider.get_latest_positioning = AsyncMock(return_value={
            "report_date": "2025-01-01",
            "non_commercial": {"net": 150000, "bias": "bullish"},
        })
        skill._positioning_cache = None
        ctx = SkillContext()
        result = await skill.execute(ctx, "filter_signal", direction="SELL")
        assert result.success
        assert "action" in result.data

    @pytest.mark.asyncio
    async def test_filter_signal_with_cache(self):
        skill = COTPositioningSkill()
        skill._positioning_cache = {
            "report_date": "2025-01-01",
            "non_commercial": {"net": -150000, "bias": "bearish"},
        }
        ctx = SkillContext()
        result = await skill.execute(ctx, "filter_signal", direction="BUY")
        assert result.success
        assert result.data["net_positions"] == -150000

    @pytest.mark.asyncio
    async def test_format_report(self):
        stage1 = {"is_extreme": True, "direction": "bullish_extreme", "confidence": 80, "net_positions": 150000}
        stage2 = {"confirmed": True, "confidence": 70}
        stage3 = {"timing_ok": True, "confidence": 65}
        formatted = COTPositioningSkill._format_filter_report(
            stage1, stage2, stage3, "contrarian_signal", 75.0
        )
        assert "COT 3-Stage Filter" in formatted
        assert "CONTRARIAN SIGNAL READY" in formatted
