from datetime import datetime

from euroscope.testing.behavioral_validator import BehavioralScenario, ExpectedBehavior


def build_scenario(validator):
    start = datetime(2023, 6, 15, 12, 0)
    end = datetime(2023, 6, 15, 14, 0)
    data = validator.load_yfinance_data(
        symbol="EURUSD=X",
        start=start,
        end=end,
        interval="1m",
        cache_key="lagarde_shock_june2023",
    )
    expected = [
        ExpectedBehavior(
            component="deviation_monitor",
            metric="emergency_response_time",
            operator="<=",
            threshold=30,
            tolerance=10,
        ),
        ExpectedBehavior(
            component="orchestrator",
            metric="alerts_suppressed_until",
            operator=">",
            threshold=0,
            tolerance=0,
        ),
    ]
    return BehavioralScenario(
        name="Lagarde Speech Shock (June 15, 2023 12:45–13:30 UTC)",
        start_time=start,
        end_time=end,
        data=data,
        expected_behaviors=expected,
        interval="1m",
        event_start=datetime(2023, 6, 15, 12, 45),
        event_end=datetime(2023, 6, 15, 13, 30),
    )
