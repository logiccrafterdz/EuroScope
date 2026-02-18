"""
Post-Trade Analysis Engine — Extracts learning insights from trading outcomes.
Phase 3B implementation.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional

logger = logging.getLogger("euroscope.learning.post_trade")

@dataclass
class LearningInsight:
    """Actionable insight extracted from a trade outcome."""
    trade_id: str
    accuracy: float
    key_factors: List[str]
    recommendations: List[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

class PostTradeAnalyzer:
    """
    Analyzes why a trade succeeded or failed and extracts actionable insights.
    """
    
    def analyze_trade_outcome(self, trade_data: Dict[str, Any], market_context: Dict[str, Any]) -> LearningInsight:
        """
        Analyzes why a trade succeeded or failed and extracts actionable insights.
        
        Args:
            trade_data: Dictionary containing trade details (id, status, pips, expected_direction, etc.)
            market_context: Dictionary containing market state at time of entry/exit.
        """
        trade_id = trade_data.get("id", "unknown")
        is_profitable = trade_data.get("pips", 0) > 0
        
        # 1. Compare predicted vs actual outcome
        prediction_accuracy = self._calculate_prediction_accuracy(trade_data)
        
        # 2. Identify contributing factors
        if is_profitable:
            factors = self._identify_success_factors(trade_data, market_context)
        else:
            factors = self._identify_failure_factors(trade_data, market_context)
            
        # 3. Generate improvement recommendations
        recommendations = self._generate_recommendations(factors, prediction_accuracy)
        
        return LearningInsight(
            trade_id=trade_id,
            accuracy=prediction_accuracy,
            key_factors=factors,
            recommendations=recommendations
        )

    def _calculate_prediction_accuracy(self, trade: Dict) -> float:
        """
        Calculates accuracy based on distance from targets.
        1.0 = Full Take Profit hit.
        0.0 = Stop Loss hit.
        0.5 = Exit at breakeven.
        """
        pips = trade.get("pips", 0)
        tp = trade.get("tp_pips", 30)
        sl = trade.get("sl_pips", 15)
        
        if pips >= tp:
            return 1.0
        if pips <= -sl:
            return 0.0
        
        # Linear interp between SL and TP
        total_range = tp + sl
        if total_range == 0:
            return 0.5
        return round((pips + sl) / total_range, 2)

    def _identify_success_factors(self, trade: Dict, context: Dict) -> List[str]:
        factors = ["trend_alignment"]
        if context.get("liquidity_aligned"):
            factors.append("institutional_flow_confirmation")
        if context.get("data_quality") == "complete":
            factors.append("high_quality_macro_foundation")
        return factors

    def _identify_failure_factors(self, trade: Dict, context: Dict) -> List[str]:
        factors = []
        
        # Check if market regime was misidentified
        if context.get("regime") != trade.get("expected_regime"):
            factors.append("regime_misidentification")
        
        # Check if liquidity analysis was wrong
        if context.get("liquidity_intent") != trade.get("direction"):
            factors.append("liquidity_analysis_error")
            
        # Check if technical indicators failed
        if context.get("technical_confidence", 0) > 0.7:
             factors.append("technical_indicator_failure")
             
        # Check if fundamental data was incomplete
        if context.get("data_quality") != "complete":
            factors.append("incomplete_fundamental_data")
            
        if not factors:
            factors.append("market_noise")
            
        return factors

    def _generate_recommendations(self, factors: List[str], accuracy: float) -> List[str]:
        recommendations = []
        
        if "regime_misidentification" in factors:
            recommendations.append("Increase deviation_monitor sensitivity for regime transitions.")
            
        if "liquidity_analysis_error" in factors:
            recommendations.append("Require tighter alignment between order blocks and breakout volume.")
            
        if "incomplete_fundamental_data" in factors:
            recommendations.append("Avoid high-risk setups when data health is below 80%.")
            
        if "technical_indicator_failure" in factors:
            recommendations.append("Weight LLM sentiment higher in conflicting technical signals.")
            
        return recommendations
