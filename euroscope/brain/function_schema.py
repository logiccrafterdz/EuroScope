from enum import Enum
from typing import Any, Dict, List


class SkillFunction(Enum):
    GET_PRICE = "get_price"
    GET_TECHNICAL_ANALYSIS = "get_technical_analysis"
    GET_FUNDAMENTAL_ANALYSIS = "get_fundamental_analysis"
    GET_NEWS_SENTIMENT = "get_news_sentiment"
    GET_PATTERNS = "get_patterns"
    GET_RISK_ASSESSMENT = "get_risk_assessment"
    GET_SIGNALS = "get_signals"
    GET_CHART = "get_chart"
    GET_FORECAST = "get_forecast"
    GET_LEVELS = "get_levels"
    GET_CALENDAR = "get_calendar"
    GET_MACRO = "get_macro"
    GET_PERFORMANCE = "get_performance"
    GET_TRADES = "get_trades"
    GET_STRATEGY = "get_strategy"
    GET_MARKET_STATUS = "get_market_status"


FUNCTION_SCHEMAS: Dict[str, Dict[str, Any]] = {
    SkillFunction.GET_PRICE.value: {
        "name": "get_price",
        "description": "Get current EUR/USD price and OHLCV data",
        "parameters": {
            "type": "object",
            "properties": {
                "timeframe": {
                    "type": "string",
                    "enum": ["1m", "5m", "15m", "1h", "4h", "1d"],
                    "description": "Timeframe for price context"
                }
            },
            "required": []
        },
    },
    SkillFunction.GET_TECHNICAL_ANALYSIS.value: {
        "name": "get_technical_analysis",
        "description": "Perform technical analysis (RSI, MACD, ADX, etc.)",
        "parameters": {
            "type": "object",
            "properties": {
                "indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Indicators to emphasize"
                },
                "timeframe": {"type": "string"}
            },
            "required": []
        },
    },
    SkillFunction.GET_FUNDAMENTAL_ANALYSIS.value: {
        "name": "get_fundamental_analysis",
        "description": "Get macro context and fundamentals summary",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
    },
    SkillFunction.GET_NEWS_SENTIMENT.value: {
        "name": "get_news_sentiment",
        "description": "Get current news sentiment and headlines",
        "parameters": {
            "type": "object",
            "properties": {
                "hours_back": {
                    "type": "integer",
                    "description": "How many hours of news to fetch"
                }
            },
            "required": []
        },
    },
    SkillFunction.GET_PATTERNS.value: {
        "name": "get_patterns",
        "description": "Detect chart patterns for EUR/USD",
        "parameters": {
            "type": "object",
            "properties": {
                "timeframe": {"type": "string"}
            },
            "required": []
        },
    },
    SkillFunction.GET_RISK_ASSESSMENT.value: {
        "name": "get_risk_assessment",
        "description": "Assess trade risk and position sizing",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {"type": "string"},
                "entry_price": {"type": "number"},
                "atr": {"type": "number"},
                "balance": {"type": "number"},
                "risk_pct": {"type": "number"}
            },
            "required": []
        },
    },
    SkillFunction.GET_SIGNALS.value: {
        "name": "get_signals",
        "description": "Get active trading signals",
        "parameters": {
            "type": "object",
            "properties": {
                "timeframe": {"type": "string"}
            },
            "required": []
        },
    },
    SkillFunction.GET_CHART.value: {
        "name": "get_chart",
        "description": "Generate a candlestick chart image for EUR/USD",
        "parameters": {
            "type": "object",
            "properties": {
                "timeframe": {"type": "string"},
                "count": {"type": "integer"}
            },
            "required": []
        },
    },
    SkillFunction.GET_FORECAST.value: {
        "name": "get_forecast",
        "description": "Get AI directional forecast for EUR/USD",
        "parameters": {
            "type": "object",
            "properties": {
                "timeframe": {"type": "string"}
            },
            "required": []
        },
    },
    SkillFunction.GET_LEVELS.value: {
        "name": "get_levels",
        "description": "Get support, resistance, and Fibonacci levels",
        "parameters": {
            "type": "object",
            "properties": {
                "timeframe": {"type": "string"}
            },
            "required": []
        },
    },
    SkillFunction.GET_CALENDAR.value: {
        "name": "get_calendar",
        "description": "Get upcoming economic calendar events",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
    },
    SkillFunction.GET_MACRO.value: {
        "name": "get_macro",
        "description": "Get macro data such as rates, spreads, and CPI",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
    },
    SkillFunction.GET_PERFORMANCE.value: {
        "name": "get_performance",
        "description": "Get performance analytics and stats",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
    },
    SkillFunction.GET_TRADES.value: {
        "name": "get_trades",
        "description": "Get trade journal history",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "limit": {"type": "integer"}
            },
            "required": []
        },
    },
    SkillFunction.GET_STRATEGY.value: {
        "name": "get_strategy",
        "description": "Get current strategy recommendation",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
    },
    SkillFunction.GET_MARKET_STATUS.value: {
        "name": "get_market_status",
        "description": "Check if EUR/USD market is open",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
    },
    "proactive_alert_decision": {
        "name": "proactive_alert_decision",
        "description": "Report whether current market conditions warrant a proactive alert",
        "parameters": {
            "type": "object",
            "properties": {
                "should_alert": {"type": "boolean"},
                "message": {"type": "string", "description": "Concise alert message (<150 chars)"},
                "priority": {"type": "string", "enum": ["urgent", "medium", "low"]},
                "reason": {"type": "string", "description": "Internal reasoning for logging"},
            },
            "required": ["should_alert"],
        },
    },
}


def get_all_function_schemas() -> List[Dict[str, Any]]:
    return list(FUNCTION_SCHEMAS.values())
