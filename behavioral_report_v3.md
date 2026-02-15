# Behavioral Validation Report

## Summary
Scenarios: 5
Checks: 12
Passed: 6
Failed: 6
Pass rate: 50.0%
Failed checks: risk_management:position_size_multiplier, deviation_monitor:emergency_response_time, uncertainty_assessment:composite_uncertainty_ratio, signal_executor:behavioral_rejection_ratio, liquidity_awareness:liquidity_sweep_detected, orchestrator:alerts_suppressed_until

## Scenario Analysis
| Scenario | Pass Rate | Failed Checks |
| --- | --- | --- |
| Sideways Market Trap (July 10–20, 2023) | 33.3% | uncertainty_assessment:composite_uncertainty_ratio, signal_executor:behavioral_rejection_ratio |
| Lagarde Speech Shock (June 15, 2023 12:45–13:30 UTC) | 0.0% | orchestrator:alerts_suppressed_until, deviation_monitor:emergency_response_time |
| Liquidity Sweep + Reversal (March 8, 2024 08:15–09:00 UTC) | 50.0% | liquidity_awareness:liquidity_sweep_detected |
| Session Transition Failure (April 3, 2024 06:45–07:15 UTC) | 100.0% | None |
| Macro Override Validation (Sept 21, 2023 17:00–19:00 UTC) | 50.0% | risk_management:position_size_multiplier |

## Component Contribution Analysis
- uncertainty_assessment: composite_uncertainty_ratio
- signal_executor: behavioral_rejection_ratio
- deviation_monitor: emergency_response_time
- orchestrator: alerts_suppressed_until
- liquidity_awareness: liquidity_sweep_detected
- risk_management: position_size_multiplier

## Behavioral Corrections & Overrides Observed
- Sideways Market Trap (July 10–20, 2023): macro confidence adjustment 0.80
- Sideways Market Trap (July 10–20, 2023): session transition detected
- Lagarde Speech Shock (June 15, 2023 12:45–13:30 UTC): macro confidence adjustment 0.80
- Liquidity Sweep + Reversal (March 8, 2024 08:15–09:00 UTC): macro confidence adjustment 0.80
- Liquidity Sweep + Reversal (March 8, 2024 08:15–09:00 UTC): session transition detected
- Session Transition Failure (April 3, 2024 06:45–07:15 UTC): macro confidence adjustment 0.80
- Session Transition Failure (April 3, 2024 06:45–07:15 UTC): session transition detected
- Macro Override Validation (Sept 21, 2023 17:00–19:00 UTC): macro confidence adjustment 1.20

## Improvement Recommendations
- Review deviation_monitor for emergency_response_time threshold mismatches.
- Review liquidity_awareness for liquidity_sweep_detected threshold mismatches.
- Review orchestrator for alerts_suppressed_until threshold mismatches.
- Review risk_management for position_size_multiplier threshold mismatches.
- Review signal_executor for behavioral_rejection_ratio threshold mismatches.
- Review uncertainty_assessment for composite_uncertainty_ratio threshold mismatches.
