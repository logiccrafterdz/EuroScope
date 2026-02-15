import pytest

from euroscope.testing.behavioral_validator import (
    BehavioralScenario,
    BehavioralValidator,
    ExpectedBehavior,
)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_behavioral_validator_smoke(sample_ohlcv):
    validator = BehavioralValidator(lookahead_bars=3)
    start = sample_ohlcv.index[0].to_pydatetime()
    end = sample_ohlcv.index[-1].to_pydatetime()
    scenario = BehavioralScenario(
        name="Smoke Scenario",
        start_time=start,
        end_time=end,
        data=sample_ohlcv,
        expected_behaviors=[
            ExpectedBehavior(
                component="uncertainty_assessment",
                metric="composite_uncertainty_ratio",
                operator=">=",
                threshold=0.0,
            )
        ],
        interval="1h",
    )
    result = await validator.run_scenario(scenario)
    assert result.checks
    assert all(check.passed for check in result.checks)
    report = validator.render_report([result])
    assert "Behavioral Validation Report" in report
