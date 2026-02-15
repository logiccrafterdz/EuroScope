from datetime import datetime

from euroscope.testing.behavioral_validator import BehavioralScenario, ExpectedBehavior


async def build_scenario(validator):
    start = datetime(2023, 7, 10, 0, 0)
    end = datetime(2023, 7, 20, 23, 59)
    data = await validator.load_yfinance_data(
        symbol="EURUSD=X",
        start=start,
        end=end,
        interval="1h",
        cache_key="sideways_july2023",
    )
    expected = [
        ExpectedBehavior(
            component="uncertainty_assessment",
            metric="composite_uncertainty_ratio",
            operator=">=",
            threshold=0.8,
            tolerance=0.05,
        ),
        ExpectedBehavior(
            component="trading_strategy",
            metric="neutral_signal_ratio",
            operator=">=",
            threshold=0.95,
            tolerance=0.02,
        ),
        ExpectedBehavior(
            component="signal_executor",
            metric="behavioral_rejection_ratio",
            operator=">=",
            threshold=0.80,
            tolerance=0.03,
        ),
    ]
    return BehavioralScenario(
        name="Sideways Market Trap (July 10–20, 2023)",
        start_time=start,
        end_time=end,
        data=data,
        expected_behaviors=expected,
        interval="1h",
    )
