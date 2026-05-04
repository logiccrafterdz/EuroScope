from dataclasses import dataclass, field
from typing import List, Literal, Optional


@dataclass
class BullCase:
    """The argument FOR taking a trade in the detected direction."""
    direction: Literal["BUY", "SELL", "NEUTRAL"]
    conviction: float  # 0.0 to 100.0
    key_arguments: List[str]
    supporting_indicators: List[str]


@dataclass
class BearCase:
    """The argument AGAINST the trade, or for the opposite direction."""
    counter_arguments: List[str]
    risk_factors: List[str]
    invalidation_levels: List[float]


@dataclass
class InvestmentJudgment:
    """The Research Manager's synthesized decision after the debate."""
    final_direction: Literal["BUY", "SELL", "HOLD", "NEUTRAL"]
    confidence: float  # 0.0 to 100.0
    reasoning: str
    bull_weight: float  # 0.0 to 1.0 (how much weight given to bull case)
    bear_weight: float  # 0.0 to 1.0 (how much weight given to bear case)


@dataclass
class RiskProfile:
    """The finalized execution parameters after the Risk Debate."""
    position_size_lots: float
    stop_loss_pips: float
    take_profit_pips: float
    risk_reward_ratio: float
    risk_rating: Literal["low", "medium", "high"]
    reasoning: str = ""
