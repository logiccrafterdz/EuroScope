"""
Tests for euroscope.analysis.patterns module.
"""

import numpy as np
import pandas as pd
import pytest

from euroscope.skills.base import SkillContext
from euroscope.skills.technical_analysis import TechnicalAnalysisSkill

from euroscope.analysis.patterns import PatternDetector, find_swing_points
from euroscope.data.storage import Storage
from euroscope.learning.pattern_tracker import PatternTracker


class TestSwingPoints:
    """Test swing point detection."""

    def test_finds_swing_highs(self, sample_ohlcv):
        highs, lows = find_swing_points(sample_ohlcv["Close"], window=5)
        assert isinstance(highs, list)
        assert len(highs) > 0
        # Each swing high should be a tuple (index, price)
        for idx, price in highs:
            assert isinstance(price, (float, np.floating))

    def test_finds_swing_lows(self, sample_ohlcv):
        highs, lows = find_swing_points(sample_ohlcv["Close"], window=5)
        assert isinstance(lows, list)
        assert len(lows) > 0

    def test_small_data_no_crash(self, small_ohlcv):
        highs, lows = find_swing_points(small_ohlcv["Close"], window=3)
        assert isinstance(highs, list)
        assert isinstance(lows, list)

    def test_window_parameter_affects_result(self, sample_ohlcv):
        highs_3, _ = find_swing_points(sample_ohlcv["Close"], window=3)
        highs_7, _ = find_swing_points(sample_ohlcv["Close"], window=7)
        # Larger window should find fewer or equal swing points
        assert len(highs_7) <= len(highs_3)


class TestPatternDetector:
    """Test pattern detection."""

    def test_detect_all_returns_list(self, sample_ohlcv):
        detector = PatternDetector()
        patterns = detector.detect_all(sample_ohlcv)
        assert isinstance(patterns, list)

    def test_pattern_dict_structure(self, sample_ohlcv):
        detector = PatternDetector()
        patterns = detector.detect_all(sample_ohlcv)
        for p in patterns:
            assert "pattern" in p
            assert "type" in p  # "bullish" or "bearish"
            assert p["type"] in ("bullish", "bearish", "neutral")

    def test_empty_dataframe(self):
        detector = PatternDetector()
        patterns = detector.detect_all(pd.DataFrame())
        assert patterns == []

    def test_insufficient_data(self, small_ohlcv):
        detector = PatternDetector()
        patterns = detector.detect_all(small_ohlcv)
        assert isinstance(patterns, list)

    def test_format_patterns_no_patterns(self):
        detector = PatternDetector()
        formatted = detector.format_patterns([])
        assert isinstance(formatted, str)

    def test_format_patterns_with_patterns(self, sample_ohlcv):
        detector = PatternDetector()
        patterns = detector.detect_all(sample_ohlcv)
        formatted = detector.format_patterns(patterns)
        assert isinstance(formatted, str)

    def test_tolerance_parameter(self):
        d1 = PatternDetector(tolerance=0.0005)
        d2 = PatternDetector(tolerance=0.002)
        assert d1.tolerance != d2.tolerance


class TestPatternTrackerCausal:
    @pytest.mark.asyncio
    async def test_match_causal_pattern_high_confidence(self, tmp_path):
        storage = Storage(str(tmp_path / "test.db"))
        tracker = PatternTracker(storage=storage)
        chain = {
            "trigger": "macro_event",
            "price_reaction": "strong_break",
            "indicator_response": "confirmed",
            "outcome": "profitable",
        }
        pid = await tracker.record_detection(
            "head_and_shoulders", "H1", "SELL", 1.085, causal_chain=chain
        )
        await tracker.resolve(pid, "SUCCESS", 1.08, True)
        context = {
            "trigger": "macro_event",
            "price_reaction": "strong_break",
            "indicator_response": "confirmed",
            "pattern_name": "head_and_shoulders",
            "timeframe": "H1",
        }
        multiplier = await tracker.match_causal_pattern(context)
        assert multiplier >= 1.1

    @pytest.mark.asyncio
    async def test_match_causal_pattern_macro_mismatch(self, tmp_path):
        storage = Storage(str(tmp_path / "test.db"))
        tracker = PatternTracker(storage=storage)
        chain = {
            "trigger": "quiet_market",
            "price_reaction": "consolidation",
            "indicator_response": "neutral",
            "outcome": "profitable",
        }
        pid = await tracker.record_detection(
            "head_and_shoulders", "H1", "SELL", 1.085, causal_chain=chain
        )
        await tracker.resolve(pid, "SUCCESS", 1.08, True)
        context = {
            "trigger": "macro_event",
            "price_reaction": "strong_break",
            "indicator_response": "confirmed",
            "pattern_name": "head_and_shoulders",
            "timeframe": "H1",
        }
        multiplier = await tracker.match_causal_pattern(context)
        assert multiplier <= 0.5

    @pytest.mark.asyncio
    async def test_match_causal_pattern_without_causal_chain(self, tmp_path):
        storage = Storage(str(tmp_path / "test.db"))
        tracker = PatternTracker(storage=storage)
        pid = await tracker.record_detection("double_top", "H1", "SELL", 1.085)
        await tracker.resolve(pid, "SUCCESS", 1.08, True)
        context = {
            "trigger": "macro_event",
            "price_reaction": "strong_break",
            "indicator_response": "confirmed",
            "pattern_name": "double_top",
            "timeframe": "H1",
        }
        multiplier = await tracker.match_causal_pattern(context)
        assert multiplier >= 1.0


class TestPatternContextAdjustments:
    def test_asian_reversal_penalty(self, sample_ohlcv):
        skill = TechnicalAnalysisSkill()
        ctx = SkillContext()
        pattern = {"pattern": "Double Top", "type": "bearish", "confidence": 80, "level": 1.08}
        adjusted = skill._adjust_pattern_confidence(
            pattern, "asian", {}, [], ctx, sample_ohlcv
        )
        assert adjusted["confidence"] == 0.6
        assert "session_penalty: asian" in adjusted["context_notes"]

    def test_weekend_penalty_clamps(self, sample_ohlcv):
        skill = TechnicalAnalysisSkill()
        ctx = SkillContext()
        pattern = {"pattern": "Triangle", "type": "neutral", "confidence": 0.1}
        adjusted = skill._adjust_pattern_confidence(
            pattern, "weekend", {}, [], ctx, sample_ohlcv
        )
        assert adjusted["confidence"] == 0.0
        assert adjusted["confidence_breakdown"]["final_confidence"] == 0.0

    def test_liquidity_conflict_penalty(self, sample_ohlcv):
        skill = TechnicalAnalysisSkill()
        ctx = SkillContext()
        market_intent = {"next_likely_move": "up"}
        pattern = {"pattern": "Head & Shoulders", "type": "bearish", "confidence": 0.7, "head": 1.085}
        adjusted = skill._adjust_pattern_confidence(
            pattern, "london", market_intent, [], ctx, sample_ohlcv
        )
        assert adjusted["confidence"] == 0.45
        assert "liquidity_conflict: reversal_vs_up" in adjusted["context_notes"]

    def test_strong_break_bonus(self, sample_ohlcv):
        skill = TechnicalAnalysisSkill()
        ctx = SkillContext()
        zones = [{"price_level": 1.05, "strength": 0.8}]
        df = sample_ohlcv.copy()
        df.loc[df.index[-1], "Close"] = 1.07
        pattern = {"pattern": "Ascending Channel", "type": "bullish", "confidence": 0.6}
        adjusted = skill._adjust_pattern_confidence(
            pattern, "london", {}, zones, ctx, df
        )
        assert adjusted["confidence"] == 0.75
        assert "liquidity_bonus: strong_break" in adjusted["context_notes"]

    @pytest.mark.asyncio
    async def test_full_pipeline_pattern_enrichment(self, sample_ohlcv):
        skill = TechnicalAnalysisSkill()
        ctx = SkillContext()
        ctx.market_data["candles"] = sample_ohlcv
        ctx.market_data["timeframe"] = "H1"
        ctx.metadata["session_regime"] = "asian"
        ctx.metadata["market_intent"] = {"next_likely_move": "down", "current_phase": "liquidity_sweep"}
        ctx.metadata["liquidity_zones"] = [{"price_level": float(sample_ohlcv["Close"].iloc[-1]), "zone_type": "session_low"}]
        result = await skill.execute(ctx, "full")
        assert result.success
        assert ctx.metadata.get("pattern_context_applied") is True
        assert isinstance(ctx.metadata.get("patterns"), list)
        if ctx.metadata["patterns"]:
            assert "context_notes" in ctx.metadata["patterns"][0]
