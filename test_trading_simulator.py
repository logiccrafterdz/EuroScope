"""
Test Trading Simulator

Test the trading simulation engine with BiQuote data.
"""

import sys
import asyncio

# Add the project root to path
sys.path.insert(0, '.')

from euroscope.data.biquote import BiQuoteProvider
from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection


async def simple_signal_generator(current_price: float):
    """Simple signal generator for testing."""
    # Simple strategy: Buy if price < 1.1465, Sell if price > 1.1466
    # (More aggressive levels to trigger trades during testing)
    if current_price < 1.1465:
        return {
            "action": "BUY",
            "stop_loss": current_price - 0.0010,
            "take_profit": current_price + 0.0020
        }
    elif current_price > 1.1466:
        return {
            "action": "SELL",
            "stop_loss": current_price + 0.0010,
            "take_profit": current_price - 0.0020
        }
    return {"action": "WAIT"}


async def test_trading_simulator():
    """Test the trading simulator."""
    print("=" * 60)
    print("Testing Trading Simulator with BiQuote")
    print("=" * 60)
    
    # Create provider
    provider = BiQuoteProvider()
    
    # Create simulator
    simulator = TradingSimulator(initial_balance=100000.0)
    simulator.set_provider(provider)
    
    # Set up callbacks
    def on_price_update(price, status):
        print(f"[{status['open_trades']} open] EUR/USD: {price:.5f} | Balance: ${status['balance']:,.2f} | PnL: ${status['total_pnl']:,.2f}")
    
    def on_trade_opened(trade):
        print(f"\n>>> TRADE OPENED: {trade.direction.value} @ {trade.entry_price:.5f}")
        print(f"    SL: {trade.stop_loss:.5f} | TP: {trade.take_profit:.5f}\n")
    
    def on_trade_closed(trade):
        print(f"\n<<< TRADE CLOSED: {trade.status.value}")
        print(f"    Entry: {trade.entry_price:.5f} -> Close: {trade.close_price:.5f}")
        print(f"    PnL: ${trade.pnl:,.2f}\n")
    
    simulator.on_price_update = on_price_update
    simulator.on_trade_opened = on_trade_opened
    simulator.on_trade_closed = on_trade_closed
    
    print("\nStarting simulation for 10 seconds...")
    print("(Using simple strategy: Buy < 1.1465, Sell > 1.1466)\n")
    
    # Run simulation for 10 seconds
    try:
        await asyncio.wait_for(
            simulator.start(signal_generator=simple_signal_generator),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        simulator.stop()
    
    # Print final status
    status = simulator.get_status()
    
    print("\n" + "=" * 60)
    print("Simulation Complete!")
    print("=" * 60)
    print(f"Initial Balance: ${status['initial_balance']:,.2f}")
    print(f"Final Balance: ${status['balance']:,.2f}")
    print(f"Total PnL: ${status['total_pnl']:,.2f}")
    print(f"Open Trades: {status['open_trades']}")
    print(f"Closed Trades: {status['closed_trades']}")
    print(f"Win Rate: {status['win_rate']}%")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_trading_simulator())
    sys.exit(0 if success else 1)
