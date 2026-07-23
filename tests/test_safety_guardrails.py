import pytest
import time

from euroscope.config import Config
from euroscope.skills.base import SkillContext
from euroscope.trading.safety_guardrails import SafetyGuardrail, CircuitBreaker, CircuitBreakerConfig


def _context():
    ctx = SkillContext()
    ctx.signals = {"direction": "BUY", "entry_price": 1.0850, "strategy": "trend_following", "confidence": 80.0}
    ctx.risk = {"entry_price": 1.0850, "stop_loss": 1.0835, "take_profit": 1.0900, "position_size": 1.0}
    ctx.metadata["session_regime"] = "overlap"
    ctx.metadata["macro_quality"] = "complete"
    return ctx


@pytest.mark.asyncio
async def test_blocks_high_impact_news():
    ctx = _context()
    ctx.analysis["calendar"] = [{"impact": "high", "minutes_to_event": 15, "event": "NFP"}]
    guardrail = SafetyGuardrail(Config())
    blocked, reason = await guardrail.should_block_signal(ctx)
    assert blocked is True
    assert "High-impact news" in reason


@pytest.mark.asyncio
async def test_blocks_asian_reversal_weak_confidence():
    ctx = _context()
    ctx.metadata["session_regime"] = "asian"
    ctx.signals["strategy"] = "mean_reversion"
    ctx.signals["confidence"] = 60.0
    guardrail = SafetyGuardrail(Config(safety_asian_min_confidence=0.75))
    blocked, reason = await guardrail.should_block_signal(ctx)
    assert blocked is True
    assert "Asian session" in reason


@pytest.mark.asyncio
async def test_allows_asian_trend_strong_confidence():
    ctx = _context()
    ctx.metadata["session_regime"] = "asian"
    ctx.signals["strategy"] = "trend_following"
    ctx.signals["confidence"] = 90.0
    guardrail = SafetyGuardrail(Config(safety_asian_min_confidence=0.75))
    blocked, _ = await guardrail.should_block_signal(ctx)
    assert blocked is False


@pytest.mark.asyncio
async def test_blocks_emergency_mode():
    ctx = _context()
    ctx.metadata["emergency_mode"] = True
    guardrail = SafetyGuardrail(Config())
    blocked, reason = await guardrail.should_block_signal(ctx)
    assert blocked is True
    assert "EMERGENCY" in reason


@pytest.mark.asyncio
async def test_blocks_minimal_macro_quality():
    ctx = _context()
    ctx.metadata["macro_quality"] = "minimal"
    guardrail = SafetyGuardrail(Config())
    blocked, reason = await guardrail.should_block_signal(ctx)
    assert blocked is True
    assert "macro data" in reason


@pytest.mark.asyncio
async def test_enhances_stop_loss_in_high_volatility():
    ctx = _context()
    ctx.metadata["volatility"] = "high"
    guardrail = SafetyGuardrail(Config(safety_volatility_stop_min=25))
    await guardrail.enhance_signal_safety(ctx)
    assert ctx.metadata.get("stop_loss_pips", 0) >= 25
    assert ctx.risk["stop_loss"] < 1.0835


@pytest.mark.asyncio
async def test_reduces_position_size_on_uncertainty():
    ctx = _context()
    ctx.metadata["composite_uncertainty"] = 0.7
    guardrail = SafetyGuardrail(Config())
    await guardrail.enhance_signal_safety(ctx)
    assert ctx.risk["position_size"] == 0.7


# ── Circuit Breaker Tests ────────────────────────────────────

class TestCircuitBreaker:

    def test_initial_state_not_blocked(self):
        cb = CircuitBreaker()
        blocked, reason = cb.is_blocked()
        assert blocked is False
        assert reason == ""

    def test_llm_success_resets_failures(self):
        cb = CircuitBreaker()
        cb.record_llm_failure()
        cb.record_llm_failure()
        cb.record_llm_success()
        assert cb._llm_consecutive_failures == 0

    def test_llm_failure_blocks_after_max(self):
        cb = CircuitBreaker(CircuitBreakerConfig(llm_max_consecutive_failures=3))
        cb.record_llm_failure()
        cb.record_llm_failure()
        blocked, _ = cb.is_blocked()
        assert blocked is False
        cb.record_llm_failure()
        blocked, reason = cb.is_blocked()
        assert blocked is True
        assert "LLM" in reason

    def test_api_error_blocks_after_max(self):
        cb = CircuitBreaker(CircuitBreakerConfig(api_max_errors_in_window=3))
        cb.record_api_error()
        cb.record_api_error()
        blocked, _ = cb.is_blocked()
        assert blocked is False
        cb.record_api_error()
        blocked, reason = cb.is_blocked()
        assert blocked is True
        assert "API" in reason

    def test_data_stale_blocks(self):
        cb = CircuitBreaker(CircuitBreakerConfig(connectivity_timeout_seconds=1.0))
        cb._last_successful_data_fetch = time.time() - 2.0
        blocked, reason = cb.is_blocked()
        assert blocked is True
        assert "Connectivity" in reason

    def test_auto_reset_after_cooldown(self):
        cb = CircuitBreaker(CircuitBreakerConfig(auto_reset_after_seconds=0.1))
        cb._block("test")
        assert cb.is_blocked()[0] is True
        time.sleep(0.15)
        blocked, _ = cb.is_blocked()
        assert blocked is False

    def test_force_reset(self):
        cb = CircuitBreaker()
        cb._block("test")
        assert cb.is_blocked()[0] is True
        cb.force_reset()
        assert cb.is_blocked()[0] is False

    def test_get_status(self):
        cb = CircuitBreaker()
        status = cb.get_status()
        assert "blocked" in status
        assert "llm_consecutive_failures" in status
        assert "api_errors_in_window" in status
        assert "seconds_since_last_data" in status
