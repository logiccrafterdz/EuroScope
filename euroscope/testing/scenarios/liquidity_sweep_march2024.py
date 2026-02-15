from datetime import datetime

from euroscope.testing.behavioral_validator import BehavioralScenario, ExpectedBehavior


def build_scenario(validator):
    start = datetime(2024, 3, 8, 7, 0)
    end = datetime(2024, 3, 8, 10, 0)
    data = validator.load_yfinance_data(
        symbol="EURUSD=X",
        start=start,
        end=end,
        interval="1m",
        cache_key="liquidity_sweep_march2024",
    )
    expected = [
        ExpectedBehavior(
            component="liquidity_awareness",
            metric="liquidity_sweep_detected",
            operator="truthy",
            threshold=True,
        ),
        ExpectedBehavior(
            component="uncertainty_assessment",
            metric="behavioral_uncertainty_peak",
            operator=">=",
            threshold=0.2,
            tolerance=0.05,
        ),
    ]
    return BehavioralScenario(
        name="Liquidity Sweep + Reversal (March 8, 2024 08:15–09:00 UTC)",
        start_time=start,
        end_time=end,
        data=data,
        expected_behaviors=expected,
        interval="1m",
    )
