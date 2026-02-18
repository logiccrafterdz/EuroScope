import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from euroscope.data.fundamental import FundamentalDataProvider
from euroscope.skills.base import SkillContext, SkillResult
from euroscope.skills.fundamental_analysis.skill import FundamentalAnalysisSkill
from euroscope.brain.orchestrator import Orchestrator

@pytest.fixture
async def provider():
    """Asynchronous fixture for FundamentalDataProvider."""
    p = FundamentalDataProvider(fred_api_key="test_key")
    yield p
    await p.close()

@pytest.mark.asyncio
async def test_fetch_series_retry_logic(provider):
    """Verify exponential backoff and retry logic."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = [Exception("Fail 1"), Exception("Fail 2"), MagicMock()]
    mock_resp.json.return_value = {"observations": [{"date": "2025-01-01", "value": "5.0"}]}
    
    with patch.object(provider.session, 'get', AsyncMock(return_value=mock_resp)) as mock_get:
        with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
            data = await provider._fetch_series("TEST")
            assert len(data) == 1
            assert data[0]["value"] == 5.0
            assert mock_get.call_count == 3
            assert mock_sleep.call_count == 2

@pytest.mark.asyncio
async def test_cache_fallback_quality(provider):
    """Verify quality flags when using cached data."""
    provider._set_cache("fed_funds_rate", {"rate": 5.25, "date": "2025-01-01", "source": "FRED"})
    
    # Simulate API failure
    with patch.object(provider, '_fetch_series', AsyncMock(return_value=[])):
        data = await provider.get_fed_funds_rate()
        assert data["rate"] == 5.25
        assert data["quality"] == "cached"
        assert any("Using cached data" in w for w in provider.warnings)

@pytest.mark.asyncio
async def test_skill_confidence_penalty():
    """Verify that FundamentalAnalysisSkill reduces confidence for partial data."""
    mock_provider = AsyncMock()
    mock_provider.fetch_complete_macro_data.return_value = {
        "quality": "partial_eu",
        "us_data": {"fed": {"rate": 5.0}},
        "eu_data": {},
        "warnings": ["ECB Missing"]
    }
    mock_provider.get_macro_context_for_ai.return_value = "Macro summary..."
    
    skill = FundamentalAnalysisSkill(macro_provider=mock_provider)
    ctx = SkillContext()
    
    # FundamentalAnalysisSkill._get_macro is what we want to test
    result = await skill._get_macro(ctx)
    
    assert result.success
    assert result.data["data_quality"] == "partial_eu"
    # Base confidence 0.85 * 0.6 = 0.51
    assert result.data["confidence"] == pytest.approx(0.51)
    assert ctx.metadata["macro_quality"] == "partial_eu"

@pytest.mark.asyncio
async def test_orchestrator_confidence_adjustment():
    """Verify Orchestrator applies penalties to final confidence."""
    # Orchestrator init has no args
    orch = Orchestrator()
    ctx = SkillContext()
    
    # Set quality warning in context
    ctx.metadata["data_quality_warning"] = True
    ctx.metadata["data_quality_details"] = {"quality": "minimal"}
    
    # Base confidence from conflict arbiter
    base_conf = 0.8
    
    # Minimal penalty is 50%
    final_conf = orch._calculate_final_confidence(base_conf, ctx)
    assert final_conf == pytest.approx(0.4)
