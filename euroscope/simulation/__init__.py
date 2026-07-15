"""
Trading Simulation Module

Provides real-time paper trading simulation using live market data.
"""

from .trading_simulator import TradingSimulator, Trade, TradeDirection, TradeStatus

__all__ = ["TradingSimulator", "Trade", "TradeDirection", "TradeStatus"]
