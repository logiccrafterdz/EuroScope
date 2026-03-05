import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from euroscope.forecast.engine import Forecaster

def test_parsing():
    mock_ai_outputs = [
        # 1. Perfect Match (New Prompt)
        (
            "**AI Bias:** BULLISH\n"
            "**AI Conviction:** 85%\n"
            "1. The Core Algorithmic Signal: The system is incredibly bullish.\n"
            "2. Fundamental Alignment: Inflation dropped by 2% which is bullish."
        ),
        
        # 2. Previous Vulnerable Output (Missing Explicit Format)
        (
            "Overall, the technicals show a BULLISH pattern.\n"
            "Inflation rose by 7%, which means the Euro is strong.\n"
            "The conviction of this trade is HIGH."
        ),
        
        # 3. Lowercase / Variations
        (
            "AI bIASt: BEARISH\n"
            "AI Confidence: 40 \n"
            "The market is moving."
        )
    ]
    
    # Instantiate a dummy forecaster (only need the parse method)
    class DummyAgent: pass
    class DummyMemory: pass
    class DummyOrch: pass
    forecaster = Forecaster(DummyAgent(), DummyMemory(), DummyOrch())
    
    for i, text in enumerate(mock_ai_outputs):
        parsed = forecaster._parse_forecast(text)
        direction = parsed.get("direction")
        confidence = parsed.get("confidence")
        print(f"--- Test Case {i+1} ---")
        print(f"Output Direction: {direction}")
        print(f"Output Confidence: {confidence}%\n")

if __name__ == "__main__":
    test_parsing()
