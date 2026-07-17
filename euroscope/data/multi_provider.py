"""
Multi-Source Data Provider

Aggregates price data from multiple sources with automatic failover.
Primary: BiQuote (Free, No API Key) | Secondary: yfinance | Fallback: Alpha Vantage
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Optional

import pandas as pd

from .provider import PriceProvider
from .alpha_vantage import AlphaVantageProvider
from .tiingo import TiingoProvider
from .oanda import OandaProvider
from .biquote import BiQuoteProvider

logger = logging.getLogger("euroscope.data.multi")


class CandleCache:
    """SQLite-backed candle cache that persists across restarts."""

    def __init__(self, db_path: str = "data/candle_cache.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path, timeout=5)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL, high REAL, low REAL, close REAL, volume REAL DEFAULT 0,
                    source TEXT DEFAULT 'unknown',
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (timeframe, timestamp)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_candles_tf_ts ON candles (timeframe, timestamp DESC)")
            conn.commit()
        finally:
            conn.close()

    def get(self, timeframe: str, count: int, max_age_seconds: int = 300) -> Optional[pd.DataFrame]:
        """Return cached candles if fresh enough."""
        cutoff = (datetime.now(UTC) - timedelta(seconds=max_age_seconds)).isoformat()
        conn = sqlite3.connect(self._db_path, timeout=5)
        try:
            rows = conn.execute(
                "SELECT timestamp, open, high, low, close, volume FROM candles "
                "WHERE timeframe = ? AND cached_at >= ? ORDER BY timestamp DESC LIMIT ?",
                (timeframe, cutoff, count),
            ).fetchall()
            # Adaptive minimum: D1/W1 only have 1-2 candles per hour
            min_rows = {"M1": 10, "M5": 10, "M15": 10, "H1": 10, "H4": 5, "D1": 1, "W1": 1}.get(timeframe, 5)
            if len(rows) < min_rows:
                return None
            rows.reverse()
            df = pd.DataFrame(rows, columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
            df["Datetime"] = pd.to_datetime(df["Datetime"])
            df = df.set_index("Datetime")
            return df
        finally:
            conn.close()

    def put(self, timeframe: str, df: pd.DataFrame, source: str = "unknown"):
        """Store candles in cache."""
        if df is None or df.empty:
            return
        now = datetime.now(UTC).isoformat()
        conn = sqlite3.connect(self._db_path, timeout=5)
        try:
            for idx, row in df.iterrows():
                ts = str(idx)
                conn.execute(
                    "INSERT OR REPLACE INTO candles (timeframe, timestamp, open, high, low, close, volume, source, cached_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (timeframe, ts, float(row["Open"]), float(row["High"]),
                     float(row["Low"]), float(row["Close"]), float(row.get("Volume", 0)),
                     source, now),
                )
            conn.commit()
        finally:
            conn.close()

    def clear(self, timeframe: Optional[str] = None):
        """Clear cached candles."""
        conn = sqlite3.connect(self._db_path, timeout=5)
        try:
            if timeframe:
                conn.execute("DELETE FROM candles WHERE timeframe = ?", (timeframe,))
            else:
                conn.execute("DELETE FROM candles")
            conn.commit()
        finally:
            conn.close()


class MultiSourceProvider:
    """
    Unified price provider that tries multiple data sources.

    Price: BiQuote → OANDA → Tiingo → yfinance → Alpha Vantage
    Candles: yfinance (cached) → OANDA → Tiingo → BiQuote (live) → Alpha Vantage
    """

    def __init__(self, alphavantage_key: str = "", tiingo_key: str = "", oanda_key: str = "", oanda_account: str = "", oanda_practice: bool = True):
        self.biquote = BiQuoteProvider()  # Free, no API key needed
        self.oanda = OandaProvider(oanda_key, oanda_account, oanda_practice) if oanda_key else None
        self.tiingo = TiingoProvider(tiingo_key) if tiingo_key else None
        self.legacy = PriceProvider() # yfinance
        self.fallback = AlphaVantageProvider(alphavantage_key) if alphavantage_key else None
        self._candle_cache = CandleCache()

        self._last_source = "biquote"

    @property
    def last_source(self) -> str:
        """Which data source was used for the last successful call."""
        return self._last_source

    async def get_price(self) -> dict:
        """Get current EUR/USD price with automatic failover."""
        # Try BiQuote first (Free, No API Key)
        try:
            result = await self.biquote.get_price()
            if "error" not in result:
                self._last_source = "biquote"
                result["source"] = "biquote"
                return result
            logger.warning(f"BiQuote price failed: {result.get('error')}, trying OANDA...")
        except Exception as e:
            logger.warning(f"BiQuote exception: {e}, trying OANDA...")

        # Try OANDA
        if self.oanda:
            result = await self.oanda.get_price()
            if "error" not in result:
                self._last_source = "oanda"
                result["source"] = "oanda"
                return result
            logger.warning(f"OANDA price failed: {result.get('error')}, trying yfinance...")

        # Try Tiingo (Institutional Grade REST API - No 15m delay)
        if self.tiingo:
            result = await self.tiingo.get_price()
            if "error" not in result:
                self._last_source = "tiingo"
                result["source"] = "tiingo"
                return result
            logger.warning(f"Tiingo price failed: {result.get('error')}, trying yfinance...")

        # Try yfinance (Legacy/Delayed 15m)
        result = await self.legacy.get_price()
        if "error" not in result:
            self._last_source = "yfinance"
            result["source"] = "yfinance"
            if "error" not in result:
                result["warning"] = "Data delayed 15m (Yahoo Finance Fallback)"
            return result

        # Try fallback (Alpha Vantage)
        if self.fallback:
            result = self.fallback.get_price()
            if "error" not in result:
                self._last_source = "alphavantage"
                return result
            logger.error(f"Alpha Vantage also failed: {result.get('error')}")

    async def close(self):
        """Close all underlying provider sessions."""
        tasks = []
        if self.biquote: tasks.append(self.biquote.close())
        if self.oanda: tasks.append(self.oanda.close())
        if self.tiingo: # Tiingo uses context managers per call, but we can add close() for future-proofing
            pass
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("MultiSourceProvider: All sessions closed.")

    async def get_candles(self, timeframe: str = "H1", count: int = 100, symbol: str = "EURUSD", **kwargs) -> Optional[pd.DataFrame]:
        """Get OHLCV candles with automatic failover + local SQLite cache.

        Priority: SQLite cache → yfinance → OANDA → Tiingo → BiQuote → Alpha Vantage
        """
        tf = timeframe.upper()

        # 0) SQLite cache — fast, zero network
        # Adaptive TTL: D1/W1 candles rarely change, use longer cache
        cache_ttl = {"M1": 60, "M5": 60, "M15": 120, "H1": 300, "H4": 600, "D1": 3600, "W1": 7200}.get(tf, 300)
        cached = self._candle_cache.get(tf, count, max_age_seconds=cache_ttl)
        if cached is not None and len(cached) >= min(count, 20):
            logger.debug(f"Candle cache hit for {tf}: {len(cached)} candles")
            return cached

        # 1) yfinance — only real historical source
        df = await self.legacy.get_candles(tf, count)
        if df is not None and not df.empty:
            df = self._validate_data(df)
            if df is not None:
                self._last_source = "yfinance"
                self._candle_cache.put(tf, df, source="yfinance")
                return df
        logger.debug(f"yfinance candles unavailable for {tf}, trying other sources...")

        # 2) OANDA
        if self.oanda:
            df = await self.oanda.get_candles(tf, count)
            if df is not None and not df.empty:
                df = self._validate_data(df)
                if df is not None:
                    self._last_source = "oanda"
                    self._candle_cache.put(tf, df, source="oanda")
                    return df
            logger.debug(f"OANDA candles failed for {tf}")

        # 3) Tiingo
        if self.tiingo:
            df = await self.tiingo.get_candles(tf, count)
            if df is not None and not df.empty:
                df = self._validate_data(df)
                if df is not None:
                    self._last_source = "tiingo"
                    self._candle_cache.put(tf, df, source="tiingo")
                    return df
            logger.debug(f"Tiingo candles failed for {tf}")

        # 4) BiQuote — live snapshot only (single candle)
        df = await self.biquote.get_candles(tf, count)
        if df is not None and not df.empty:
            self._last_source = "biquote"
            return df

        # 5) Alpha Vantage
        if self.fallback:
            df = self.fallback.get_candles(tf, count)
            if df is not None and not df.empty:
                df = self._validate_data(df)
                if df is not None:
                    self._last_source = "alphavantage"
                    self._candle_cache.put(tf, df, source="alphavantage")
                    return df

        logger.warning(f"All candle sources failed for {tf}")
        return None

    async def get_multi_timeframe(self) -> dict[str, Optional[pd.DataFrame]]:
        timeframes = ["M15", "H1", "H4", "D1", "W1"]
        tasks: dict[str, object] = {}
        for tf in timeframes:
            try:
                tasks[tf] = self.get_candles(tf)
            except Exception as e:
                logger.warning(f"Failed to create task for {tf}: {e}")
                tasks[tf] = None

        valid_tasks = {k: v for k, v in tasks.items() if v is not None}
        if not valid_tasks:
            logger.error("No valid timeframe tasks created")
            return {}

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*valid_tasks.values(), return_exceptions=True),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.error("Multi-timeframe fetch timed out after 30s")
            return {}

        output: dict[str, Optional[pd.DataFrame]] = {}
        for tf, result in zip(valid_tasks, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to fetch {tf}: {result}")
                output[tf] = None
            else:
                output[tf] = result

        return output

    @staticmethod
    def _validate_data(df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Validate OHLCV data quality.

        Checks:
        - No excessive NaN values (> 20% threshold)
        - OHLC relationships are valid (High >= Low)
        - Prices are in a reasonable range for EUR/USD
        """
        if df is None or df.empty:
            return None

        required = ["Open", "High", "Low", "Close"]
        for col in required:
            if col not in df.columns:
                logger.error(f"Missing column: {col}")
                return None

        # Check NaN ratio
        nan_ratio = df[required].isna().sum().sum() / (len(df) * len(required))
        if nan_ratio > 0.2:
            logger.warning(f"Data has {nan_ratio:.0%} NaN values — too many")
            return None

        # Drop rows with NaN
        df = df.dropna(subset=required)

        # Check High >= Low
        invalid = df[df["High"] < df["Low"]]
        if len(invalid) > 0:
            logger.warning(f"Found {len(invalid)} rows with High < Low — fixing")
            df.loc[df["High"] < df["Low"], ["High", "Low"]] = \
                df.loc[df["High"] < df["Low"], ["Low", "High"]].values

        # EUR/USD sanity range (0.80 - 1.60 is generous)
        price_range = df["Close"]
        if price_range.min() < 0.80 or price_range.max() > 1.60:
            logger.warning(f"Prices outside EUR/USD range: {price_range.min():.4f} - {price_range.max():.4f}")
            return None

        return df

    def clear_cache(self):
        """Clear all caches."""
        if self.oanda:
            self.oanda.clear_cache()
        self.legacy.clear_cache()
        if self.fallback:
            self.fallback.clear_cache()
        self._candle_cache.clear()
