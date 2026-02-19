"""
Phase 4 Integration Test — EuroScope
Verifies that FundamentalAnalysisSkill correctly integrates with ORCHESTRATOR
and FundamentalDataProvider to provide institutional macro context.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from euroscope.brain.orchestrator import Orchestrator
from euroscope.skills.fundamental_analysis.skill import FundamentalAnalysisSkill
from euroscope.data.fundamental import FundamentalDataProvider
from euroscope.skills.base import SkillContext

@pytest.mark.asyncio
async def test_macro_integration_flow():
    # 1. Setup Orchestrator and Skill
    orch = Orchestrator() # SkillRegistry is created internally
    skill = FundamentalAnalysisSkill()
    orch.registry.register(skill)
    
    # 2. Mock Macro Provider
    mock_macro = MagicMock(spec=FundamentalDataProvider)
    mock_macro.get_macro_context_for_ai = AsyncMock(return_value="Institutional Analysis: Fed 5% vs ECB 4% (Stronger USD)")
    mock_macro.get_interest_rate_differential = AsyncMock(return_value={"differential": 1.0})
    mock_macro.get_yield_spread = AsyncMock(return_value={"spread": 2.0})
    mock_macro.get_us_cpi = AsyncMock(return_value={"value": 3.0})
    mock_macro.fetch_complete_macro_data = AsyncMock(return_value={
        "us_data": {"fed": {"rate": 5.0}, "cpi": {"value": 3.0}},
        "eu_data": {"ecb": {"value": 4.0}, "yield_spread": {"spread": 2.0}},
        "quality": "complete",
        "warnings": [],
    })
    
    # 3. Inject Dependency
    orch.inject_dependencies(macro_provider=mock_macro)
    
    # 4. Run 'get_macro' action
    context = SkillContext()
    result = await orch.run_skill("fundamental_analysis", "get_macro", context=context)
    
    # 5. Assertions
    assert result.success
    assert result.data["macro_data"]["us_data"]["fed"]["rate"] == 5.0
    assert "Institutional Analysis" in result.metadata["formatted"]
    assert "macro_data" in context.analysis
    
    # 6. Run 'full' analysis to ensure it includes macro
    # We need to mock other engines for 'full'
    skill.set_engines(news_engine=MagicMock(), calendar=MagicMock())
    
    result_full = await orch.run_skill("fundamental_analysis", "full", context=context)
    assert result_full.success
    assert "macro" in result_full.data
    assert result_full.data["macro"]["macro_data"]["us_data"]["fed"]["rate"] == 5.0

if __name__ == "__main__":
    asyncio.run(test_macro_integration_flow())
