"""
Comprehensive Live Trading Simulation Test

Tests the full simulation system with real-time BiQuote data.
Includes: Live price feed, trade execution, SL/TP management, and performance tracking.
"""

import sys
import asyncio
import time
from datetime import datetime

# Add the project root to path
sys.path.insert(0, '.')

from euroscope.data.biquote import BiQuoteProvider
from euroscope.simulation.trading_simulator import TradingSimulator, TradeDirection, TradeStatus


class SimpleMovingAverageStrategy:
    """Simple SMA crossover strategy for testing."""
    
    def __init__(self, short_period: int = 5, long_period: int = 20):
        self.short_period = short_period
        self.long_period = long_period
        self.prices = []
        self.short_sma = None
        self.long_sma = None
        self.last_signal = None
    
    def update(self, price: float) -> dict:
        """Update with new price and generate signal."""
        self.prices.append(price)
        
        # Keep only needed history
        if len(self.prices) > self.long_period + 1:
            self.prices = self.prices[-(self.long_period + 1):]
        
        # Calculate SMAs if we have enough data
        if len(self.prices) >= self.long_period:
            self.short_sma = sum(self.prices[-self.short_period:]) / self.short_period
            self.long_sma = sum(self.prices[-self.long_period:]) / self.long_period
            
            # Generate signal
            if self.short_sma > self.long_sma and self.last_signal != "BUY":
                self.last_signal = "BUY"
                return {
                    "action": "BUY",
                    "stop_loss": price - 0.0015,
                    "take_profit": price + 0.0030
                }
            elif self.short_sma < self.long_sma and self.last_signal != "SELL":
                self.last_signal = "SELL"
                return {
                    "action": "SELL",
                    "stop_loss": price + 0.0015,
                    "take_profit": price - 0.0030
                }
        
        return {"action": "WAIT"}


async def test_live_simulation():
    """Test live trading simulation with BiQuote data."""
    print("=" * 70)
    print("LIVE TRADING SIMULATION TEST")
    print("=" * 70)
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: 60 seconds")
    print("=" * 70)
    
    # Initialize components
    provider = BiQuoteProvider()
    simulator = TradingSimulator(initial_balance=100000.0)
    simulator.set_provider(provider)
    strategy = SimpleMovingAverageStrategy(short_period=3, long_period=10)
    
    # Statistics
    start_time = time.time()
    price_updates = 0
    max_trades = 5
    
    # Callbacks
    def on_price_update(price, status):
        nonlocal price_updates
        price_updates += 1
        elapsed = time.time() - start_time
        
        # Print status every 5 seconds
        if price_updates % 5 == 0:
            print(f"\n[{elapsed:.0f}s] Price: {price:.5f} | Trades: {status['open_trades']} open | PnL: ${status['total_pnl']:.2f}")
            if strategy.short_sma and strategy.long_sma:
                print(f"       SMA Short: {strategy.short_sma:.5f} | SMA Long: {strategy.long_sma:.5f}")
    
    def on_trade_opened(trade):
        print(f"\n{'='*50}")
        print(f"TRADE OPENED: {trade.direction.value} @ {trade.entry_price:.5f}")
        print(f"SL: {trade.stop_loss:.5f} | TP: {trade.take_profit:.5f}")
        print(f"{'='*50}")
    
    def on_trade_closed(trade):
        print(f"\n{'='*50}")
        print(f"TRADE CLOSED: {trade.status.value}")
        print(f"Entry: {trade.entry_price:.5f} -> Close: {trade.close_price:.5f}")
        print(f"PnL: ${trade.pnl:.2f}")
        print(f"{'='*50}")
    
    simulator.on_price_update = on_price_update
    simulator.on_trade_opened = on_trade_opened
    simulator.on_trade_closed = on_trade_closed
    
    # Signal generator using strategy
    async def signal_generator(current_price: float):
        if len(simulator.open_trades) >= max_trades:
            return {"action": "WAIT"}
        return strategy.update(current_price)
    
    print("\nStarting live simulation...")
    print("Strategy: SMA Crossover (3/10)")
    print("Max concurrent trades:", max_trades)
    print("\n" + "-" * 70)
    
    # Run simulation for 60 seconds
    try:
        await asyncio.wait_for(
            simulator.start(signal_generator=signal_generator),
            timeout=60.0
        )
    except asyncio.TimeoutError:
        simulator.stop()
    
    # Final report
    status = simulator.get_status()
    elapsed = time.time() - start_time
    
    print("\n" + "=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)
    print(f"Duration: {elapsed:.1f} seconds")
    print(f"Price Updates: {price_updates}")
    print(f"Update Frequency: {price_updates/elapsed:.2f} Hz")
    print("-" * 70)
    print(f"Initial Balance: ${status['initial_balance']:,.2f}")
    print(f"Final Balance: ${status['balance']:,.2f}")
    print(f"Total PnL: ${status['total_pnl']:,.2f}")
    print(f"Unrealized PnL: ${status['unrealized_pnl']:,.2f}")
    print(f"Equity: ${status['equity']:,.2f}")
    print("-" * 70)
    print(f"Open Trades: {status['open_trades']}")
    print(f"Closed Trades: {status['closed_trades']}")
    print(f"Winning Trades: {status['winning_trades']}")
    print(f"Losing Trades: {status['losing_trades']}")
    print(f"Win Rate: {status['win_rate']}%")
    print("=" * 70)
    
    # Trade history
    if status['trades']:
        print("\nTRADE HISTORY:")
        print("-" * 70)
        for t in status['trades'][-10:]:  # Last 10 trades
            print(f"  {t['direction']:4} @ {t['entry_price']:.5f} -> {t.get('close_price', 'OPEN'):>10} | PnL: ${t['pnl']:>8.2f} | {t['status']}")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_live_simulation())
    sys.exit(0 if success else 1)
