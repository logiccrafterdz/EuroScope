from datetime import datetime

from euroscope.testing.behavioral_validator import BehavioralScenario, ExpectedBehavior


def build_scenario(validator):
    start = datetime(2024, 4, 3, 6, 0)
    end = datetime(2024, 4, 3, 8, 0)
    data = validator.load_yfinance_data(
        symbol="EURUSD=X",
        start=start,
        end=end,
        interval="1m",
        cache_key="session_transition_april2024",
    )
    expected = [
        ExpectedBehavior(
            component="session_context",
            metric="session_transition_detected",
            operator="truthy",
            threshold=True,
        ),
        ExpectedBehavior(
            component="risk_management",
            metric="stop_buffer_asian",
            operator="==",
            threshold=8.0,
        ),
        ExpectedBehavior(
            component="risk_management",
            metric="stop_buffer_london",
            operator="==",
            threshold=12.0,
        ),
    ]
    return BehavioralScenario(
        name="Session Transition Failure (April 3, 2024 06:45–07:15 UTC)",
        start_time=start,
        end_time=end,
        data=data,
        expected_behaviors=expected,
        interval="1m",
    )
