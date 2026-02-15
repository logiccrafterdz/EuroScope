from datetime import datetime

from euroscope.testing.behavioral_validator import BehavioralScenario, ExpectedBehavior


def build_scenario(validator):
    start = datetime(2023, 9, 21, 17, 0)
    end = datetime(2023, 9, 21, 20, 0)
    data = validator.load_yfinance_data(
        symbol="EURUSD=X",
        start=start,
        end=end,
        interval="1m",
        cache_key="macro_override_sept2023",
    )
    expected = [
        ExpectedBehavior(
            component="fundamental_analysis",
            metric="macro_confidence_adjustment",
            operator=">=",
            threshold=0.3,
            tolerance=0.05,
        ),
        ExpectedBehavior(
            component="risk_management",
            metric="position_size_multiplier",
            operator=">=",
            threshold=0.5,
            tolerance=0.1,
        ),
    ]
    return BehavioralScenario(
        name="Macro Override Validation (Sept 21, 2023 17:00–19:00 UTC)",
        start_time=start,
        end_time=end,
        data=data,
        expected_behaviors=expected,
        interval="1m",
        context_overrides={
            "analysis": {
                "macro_data": {
                    "differential": {
                        "bias": "USD stronger",
                        "confidence": 0.9,
                    }
                }
            }
        },
    )
