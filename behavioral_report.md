# Behavioral Validation Report

## Summary
Scenarios: 5
Checks: 12
Passed: 7
Failed: 5
Pass rate: 58.3%
Failed checks: liquidity_awareness:liquidity_sweep_detected, deviation_monitor:emergency_response_time, orchestrator:alerts_suppressed_until, uncertainty_assessment:composite_uncertainty_ratio, signal_executor:behavioral_rejection_ratio

## Scenario Analysis
| Scenario | Pass Rate | Failed Checks |
| --- | --- | --- |
| Sideways Market Trap (July 10–20, 2023) | 33.3% | signal_executor:behavioral_rejection_ratio, uncertainty_assessment:composite_uncertainty_ratio |
| Lagarde Speech Shock (June 15, 2023 12:45–13:30 UTC) | 0.0% | deviation_monitor:emergency_response_time, orchestrator:alerts_suppressed_until |
| Liquidity Sweep + Reversal (March 8, 2024 08:15–09:00 UTC) | 50.0% | liquidity_awareness:liquidity_sweep_detected |
| Session Transition Failure (April 3, 2024 06:45–07:15 UTC) | 100.0% | None |
| Macro Override Validation (Sept 21, 2023 17:00–19:00 UTC) | 100.0% | None |

## Component Contribution Analysis
- uncertainty_assessment: composite_uncertainty_ratio
- signal_executor: behavioral_rejection_ratio
- deviation_monitor: emergency_response_time
- orchestrator: alerts_suppressed_until
- liquidity_awareness: liquidity_sweep_detected

## Behavioral Corrections & Overrides Observed
- Sideways Market Trap (July 10–20, 2023): emergency mode triggered
- Sideways Market Trap (July 10–20, 2023): macro confidence adjustment 0.80
- Sideways Market Trap (July 10–20, 2023): session transition detected
- Lagarde Speech Shock (June 15, 2023 12:45–13:30 UTC): macro confidence adjustment 1.00
- Liquidity Sweep + Reversal (March 8, 2024 08:15–09:00 UTC): macro confidence adjustment 1.00
- Liquidity Sweep + Reversal (March 8, 2024 08:15–09:00 UTC): session transition detected
- Session Transition Failure (April 3, 2024 06:45–07:15 UTC): macro confidence adjustment 1.00
- Session Transition Failure (April 3, 2024 06:45–07:15 UTC): session transition detected
- Macro Override Validation (Sept 21, 2023 17:00–19:00 UTC): macro confidence adjustment 1.30

## Improvement Recommendations
- Review deviation_monitor for emergency_response_time threshold mismatches.
- Review liquidity_awareness for liquidity_sweep_detected threshold mismatches.
- Review orchestrator for alerts_suppressed_until threshold mismatches.
- Review signal_executor for behavioral_rejection_ratio threshold mismatches.
- Review uncertainty_assessment for composite_uncertainty_ratio threshold mismatches.
