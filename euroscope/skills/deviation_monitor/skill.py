import logging
import time
from datetime import datetime
from typing import Optional

import pandas as pd

from ..base import BaseSkill, SkillCategory, SkillContext, SkillResult
from ...automation.events import Event

logger = logging.getLogger("euroscope.skills.deviation_monitor")


class DeviationMonitorSkill(BaseSkill):
    name = "deviation_monitor"
    description = "Detects sudden regime shifts via volume/volatility/velocity anomalies"
    emoji = "🚨"
    category = SkillCategory.SYSTEM
    version = "1.0.0"
    capabilities = ["start"]

    def __init__(self, event_bus=None, market_data_skill=None, storage=None, global_context=None):
        super().__init__()
        self._bus = event_bus
        self._market_data_skill = market_data_skill
        self._storage = storage
        self._context = global_context
        self._subscribed = False

    def set_event_bus(self, event_bus):
        self._bus = event_bus
        self._subscribe()

    def set_market_data_skill(self, market_data_skill):
        self._market_data_skill = market_data_skill

    def set_storage(self, storage):
        self._storage = storage

    def set_global_context(self, context):
        self._context = context

    async def execute(self, context: SkillContext, action: str, **params) -> SkillResult:
        if action == "start":
            self._subscribe()
            return SkillResult(success=True, data={"running": self._subscribed})
        return SkillResult(success=False, error=f"Unknown action: {action}")

    def _subscribe(self):
        if self._bus and not self._subscribed:
            self._bus.subscribe("tick.30s", self._on_tick)
            self._subscribed = True

    async def _on_tick(self, event):
        await self._check_once()

    async def _check_once(self):
        context = self._context
        if context is None:
            return

        now_val = context.metadata.get("now")
        if isinstance(now_val, datetime):
            now_dt = now_val
            now = now_val.timestamp()
        else:
            now_dt = datetime.fromtimestamp(now_val) if now_val else datetime.utcnow()
            now = now_val or time.time()
        last = context.metadata.get("deviation_monitor_last_activation", 0)
        if last and now - last < 600:
            return

        buffer = self._get_buffer()
        if not buffer:
            logger.warning("DeviationMonitor: no market data buffer available")
            return

        candles = buffer.get("candles")
        timeframe = buffer.get("timeframe", "M1")
        if candles is None or len(candles) < 3:
            logger.warning("DeviationMonitor: insufficient candle data")
            return

        result = self._detect_deviation(candles)
        if not result:
            return
        session = result.get("session") or self._detect_trading_session(now_dt)
        emergency_seconds = 480 if session == "overlap" else 86400 if session == "weekend" else 300
        context.metadata["emergency_mode"] = True
        context.metadata["emergency_until"] = now + emergency_seconds
        context.metadata["deviation_monitor_last_activation"] = now
        context.metadata["deviation_monitor_last_trigger"] = result

        await self._emit_event(result)
        self._log_deviation(result, candles, timeframe)

    def _get_buffer(self) -> Optional[dict]:
        if self._market_data_skill and hasattr(self._market_data_skill, "get_buffer"):
            return self._market_data_skill.get_buffer()
        return None

    def _detect_deviation(self, candles) -> Optional[dict]:
        df = candles.tail(20) if hasattr(candles, "tail") else candles
        now_val = self._context.metadata.get("now") if self._context else None
        if isinstance(now_val, datetime):
            now_dt = now_val
        else:
            now_dt = datetime.fromtimestamp(now_val) if now_val else datetime.utcnow()
        if self._context:
            session = self._context.metadata.get("session_regime") or self._detect_trading_session(now_dt)
        else:
            session = self._detect_trading_session(now_dt)
        thresholds = self._session_thresholds(session)
        triggers = self._check_deviation_triggers(df, thresholds, session=session)
        if not triggers:
            return None
        primary = triggers[0]
        return {
            "trigger": primary["type"],
            "magnitude": primary["magnitude"],
            "details": triggers,
            "session": session,
        }

    @staticmethod
    def _detect_trading_session(current_utc: datetime) -> str:
        if current_utc.weekday() >= 5:
            return "weekend"
        hour = current_utc.hour
        if 12 <= hour < 16:
            return "overlap"
        if 7 <= hour < 16:
            return "london"
        if 12 <= hour < 21:
            return "newyork"
        if 0 <= hour < 7:
            return "asian"
        return "asian"

    @staticmethod
    def _session_thresholds(session: str) -> dict:
        if session in ("asian", "weekend"):
            return {"volume": 3.0, "velocity": 0.0015, "volatility": 2.5}
        if session == "overlap":
            return {"volume": 5.0, "velocity": 0.0030, "volatility": 4.0}
        if session in ("london", "newyork"):
            return {"volume": 4.5, "velocity": 0.0025, "volatility": 3.5}
        return {"volume": 3.0, "velocity": 0.0015, "volatility": 2.5}

    def _check_deviation_triggers(self, df, thresholds: dict, session: str | None = None) -> list[dict]:
        if self._context:
            session = self._context.metadata.get("session_regime", session or "asian")
        else:
            session = session or "asian"
        base_velocity = 0.15
        velocity_threshold = {
            "asian": base_velocity,
            "london": base_velocity * 1.4,
            "overlap": base_velocity * 1.8,
            "newyork": base_velocity * 1.6,
            "weekend": base_velocity * 0.8,
        }.get(session, base_velocity)
        volume_threshold = {
            "overlap": 5.0,
            "london": 4.5,
            "newyork": 4.0,
            "asian": 3.0,
        }.get(session, 3.0)
        volume_trigger = self._volume_spike(df, volume_threshold)
        volatility_trigger = self._volatility_spike(df, thresholds["volatility"])
        velocity_trigger = self._price_velocity(df, velocity_threshold)
        return [t for t in (volume_trigger, volatility_trigger, velocity_trigger) if t]

    def _volume_spike(self, df, threshold: float) -> Optional[dict]:
        if "Volume" not in df:
            return None
        if len(df) < 5:
            return None
        volume = pd.to_numeric(df["Volume"], errors="coerce")
        current = volume.iloc[-1]
        sma = volume.iloc[-5:].mean()
        if pd.isna(current) or pd.isna(sma) or sma == 0:
            return None
        ratio = current / sma
        if ratio > threshold:
            return {"type": "volume_spike", "magnitude": round(float(ratio), 2)}
        return None

    def _volatility_spike(self, df, threshold: float) -> Optional[dict]:
        required = {"High", "Low", "Close"}
        if not required.issubset(df.columns):
            return None
        if len(df) < 20:
            return None
        high = pd.to_numeric(df["High"], errors="coerce")
        low = pd.to_numeric(df["Low"], errors="coerce")
        close = pd.to_numeric(df["Close"], errors="coerce")
        prev_close = close.shift(1)
        tr = pd.concat(
            [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(14).mean()
        recent_atr = atr.dropna()
        if len(recent_atr) < 10:
            return None
        current_atr = recent_atr.iloc[-1]
        atr_sma = recent_atr.iloc[-10:].mean()
        if pd.isna(current_atr) or pd.isna(atr_sma) or atr_sma == 0:
            return None
        ratio = current_atr / atr_sma
        if ratio > threshold:
            return {"type": "volatility_spike", "magnitude": round(float(ratio), 2)}
        return None

    def _price_velocity(self, df, threshold: float) -> Optional[dict]:
        if "Close" not in df:
            return None
        if len(df) < 3:
            return None
        close = pd.to_numeric(df["Close"], errors="coerce")
        current = close.iloc[-1]
        past = close.iloc[-3]
        prev = close.iloc[-2]
        if pd.isna(current) or pd.isna(past) or pd.isna(prev) or current == 0:
            return None
        change = max(abs(current - past), abs(current - prev))
        change_pct = (change / current) * 100
        if change_pct > threshold:
            return {"type": "price_velocity", "magnitude": round(float(change_pct), 4)}
        return None

    async def _emit_event(self, result: dict):
        if not self._bus:
            return
        await self._bus.emit(Event("market.regime_shift", "deviation_monitor", result))

    def _log_deviation(self, result: dict, candles, timeframe: str):
        if not self._storage:
            return
        try:
            close = float(candles["Close"].iloc[-1])
            self._storage.save_trade_journal(
                direction="ALERT",
                entry_price=close,
                strategy="deviation_monitor",
                timeframe=timeframe,
                regime=result.get("trigger", ""),
                confidence=0.0,
                indicators={"deviation": result},
                patterns=[],
                reasoning=f"{result.get('trigger')}:{result.get('magnitude')}",
            )
        except Exception as e:
            logger.warning(f"DeviationMonitor: journal log failed {e}")
