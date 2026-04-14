"""
Market Data Skill — Wraps PriceProvider for the skills framework.
"""

from datetime import datetime

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult


class MarketDataSkill(BaseSkill):
    name = "market_data"
    description = "Fetches real-time and historical EUR/USD price data"
    emoji = "📊"
    category = SkillCategory.DATA
    version = "1.0.0"
    capabilities = ["get_price", "get_candles", "check_market_status", "get_correlation"]

    def __init__(self, provider=None):
        super().__init__()
        self._provider = provider
        self._ws_client = None
        self._buffer: dict = {}

    def set_provider(self, provider):
        """Standard setter for price provider (DI)."""
        self._provider = provider

    def set_ws_client(self, ws_client):
        """Standard setter for WebSocket client (DI)."""
        self._ws_client = ws_client

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "get_price":
            return await self._get_price(context)
        elif action == "get_candles":
            return await self._get_candles(context, **params)
        elif action == "check_market_status":
            return await self._check_status(context)
        elif action == "get_correlation":
            return await self._get_correlation(context, **params)
        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _get_price(self, context: SkillContext) -> SkillResult:
        if not self._provider:
            return SkillResult(success=False, error="No price provider configured")
        try:
            data = await self._provider.get_price()
            if "error" in data:
                return SkillResult(success=False, error=data["error"])
            context.market_data["price"] = data
            return SkillResult(success=True, data=data, next_skill="technical_analysis")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_candles(self, context: SkillContext, **params) -> SkillResult:
        if not self._provider:
            return SkillResult(success=False, error="No price provider configured")
        try:
            timeframe = params.get("timeframe", "H1")
            count = params.get("count", 250)
            symbol = params.get("symbol", "EUR_USD")
            df = await self._provider.get_candles(timeframe=timeframe, count=count, symbol=symbol)
            if df is None or (hasattr(df, 'empty') and df.empty):
                return SkillResult(success=False, error="No candle data returned")
            context.market_data["candles"] = df
            context.market_data["timeframe"] = timeframe
            
            # Inject live tick volume if WS is available
            if self._ws_client:
                # Default to EURUSD since the system is currently hardcoded for it
                tick_vol = self._ws_client.get_tick_volume("EURUSD", window_seconds=300)
            else:
                context.market_data["tick_volume_5m"] = 0
                
            # Phase 3: Causal Impact Attribution
            try:
                if len(df) >= 2:
                    last_candle = df.iloc[-1]
                    pip_range = abs(last_candle['High'] - last_candle['Low']) * 10000
                    
                    # 15+ pips is a significant sudden move in EUR/USD M5 or H1
                    if pip_range >= 15.0:
                        spike_dir = "bullish" if last_candle['Close'] > last_candle['Open'] else "bearish"
                        
                        import logging
                        logging.getLogger("euroscope.skill.market_data").warning(
                            f"Abnormal price spike detected: {pip_range:.1f} pips {spike_dir}. Causal Attribution required."
                        )
                        
                        # Set context flag so News/Macro skills know they should prioritize explaining this
                        context.metadata["causal_trigger"] = {
                            "pip_range": pip_range,
                            "direction": spike_dir,
                            "timestamp": str(last_candle.name) if df.index.name else ""
                        }
                        
                        from euroscope.container import get_container
                        container = get_container()
                        if container and hasattr(container, "vector_memory") and container.vector_memory:
                            container.vector_memory.store_market_event(
                                f"Sudden {pip_range:.1f} pip {spike_dir} spike. Initiated Causal Attribution.",
                                impact="high",
                                metadata={"pip_range": pip_range, "direction": spike_dir}
                            )
            except Exception as e:
                import logging
                logging.getLogger("euroscope.skill.market_data").debug(f"Causal Attribution attribution failed: {e}")
                
            from datetime import timezone
            self._buffer = {
                "candles": df,
                "timeframe": timeframe,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            return SkillResult(success=True, data=df, next_skill="technical_analysis")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def get_buffer(self) -> dict:
        return dict(self._buffer)

    async def _check_status(self, context: SkillContext) -> SkillResult:
        """Check if the EUR/USD market is currently open (Sun 5PM - Fri 5PM ET)."""
        from datetime import datetime, timezone, timedelta
        
        # ET is UTC-5
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc - timedelta(hours=5)
        
        weekday = now_et.weekday() # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        hour = now_et.hour
        
        is_open = True
        reason = "Trading sessions are active."
        
        # Closed: Friday after 5PM ET
        if weekday == 4 and hour >= 17:
            is_open = False
            reason = "Market closed for the weekend (Friday 5PM ET)."
        # Closed: All Saturday
        elif weekday == 5:
            is_open = False
            reason = "Market closed (Saturday)."
        # Closed: Sunday before 5PM ET
        elif weekday == 6 and hour < 17:
            is_open = False
            reason = "Market opening soon (opens Sunday 5PM ET)."
            
        data = {
            "is_open": is_open,
            "status": "OPEN" if is_open else "CLOSED",
            "reason": reason,
            "current_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S ET")
        }
        
        context.metadata["market_status"] = data
        return SkillResult(success=True, data=data)

    async def _get_correlation(self, context: SkillContext, **params) -> SkillResult:
        """Calculates Pearson correlation between EUR/USD and other pairs."""
        if not self._provider:
            return SkillResult(success=False, error="No price provider configured")
        try:
            timeframe = params.get("timeframe", "H1")
            count = params.get("count", 100)
            base_symbol = params.get("base_symbol", "EUR_USD")
            compare_symbols = params.get("compare_symbols", ["GBP_USD", "USD_CHF"])
            
            import pandas as pd
            import asyncio
            
            # Fetch base pair
            base_df = await self._provider.get_candles(timeframe=timeframe, count=count, symbol=base_symbol)
            if base_df is None or base_df.empty:
                 return SkillResult(success=False, error=f"No data for {base_symbol}")
            
            close_prices = {base_symbol: base_df["Close"]}
            
            # Fetch comparisons concurrently
            async def fetch_sym(sym):
                df = await self._provider.get_candles(timeframe=timeframe, count=count, symbol=sym)
                if df is not None and not df.empty:
                    return sym, df["Close"]
                return sym, None
                
            results = await asyncio.gather(*(fetch_sym(sym) for sym in compare_symbols))
            for sym, series in results:
                if series is not None:
                    close_prices[sym] = series
                    
            combined_df = pd.DataFrame(close_prices).dropna()
            if combined_df.empty:
                return SkillResult(success=False, error="Failed to align timeframes for correlation")
                
            corr_matrix = combined_df.corr(method="pearson")
            
            correlations = {}
            for sym in compare_symbols:
                if sym in corr_matrix.columns:
                    correlations[sym] = round(corr_matrix.loc[base_symbol, sym], 3)
                    
            context.market_data["correlation"] = correlations
            return SkillResult(success=True, data=correlations)
        except Exception as e:
            return SkillResult(success=False, error=str(e))
