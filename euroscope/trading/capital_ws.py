import asyncio
import json
import logging
import websockets # type: ignore
from typing import List, Callable, Optional, Dict, Any, cast

logger = logging.getLogger(__name__)

class CapitalWebsocketClient:
    """
    WebSocket client for streaming live ticks from Capital.com.
    Handles connection, authentication, pinging, and dispatching tick callbacks.
    """
    WS_URL = "wss://api-streaming-capital.backend-capital.com/connect"
    
    def __init__(self, provider):
        """
        :param provider: An authenticated CapitalProvider instance.
        """
        self.provider = provider
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._callbacks: List[Callable[[str, float, float], None]] = [] # func(symbol, bid, ask)
        self._subscribed_epics: set[str] = set()
        
        # Reconnection and health tracking
        self._reconnect_count = 0
        self._last_msg_time: float = 0
        self._listen_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        
        # Tick volume buffer: epic -> list of tick timestamps
        self._tick_volume: Dict[str, List[float]] = {}

    def get_tick_volume(self, epic: str, window_seconds: int = 60) -> int:
        """Get the number of ticks received for a symbol in the last N seconds."""
        if epic not in self._tick_volume:
            return 0
        try:
            now = asyncio.get_running_loop().time()
            # Prune old ticks
            self._tick_volume[epic] = [ts for ts in self._tick_volume[epic] if now - ts <= window_seconds]
            return len(self._tick_volume[epic])
        except RuntimeError:
            return 0

    def add_callback(self, callback: Callable[[str, float, float], None]):
        """Register a callback for incoming tick updates."""
        self._callbacks.append(callback)

    async def connect(self):
        """Establish connection and ensure listener tasks are running."""
        # Use a local for ws to satisfy the linter
        ws = self.ws
        if self._running and ws and getattr(ws.state, 'name', '') == 'OPEN':
            return True

        if not await self._establish_connection():
            return False

        self._running = True
        self._reconnect_count = 0
        loop = asyncio.get_running_loop()
        
        # Start background tasks ONLY if not already running
        lt = self._listen_task
        if not lt or lt.done():
            self._listen_task = loop.create_task(self._listen())
            logger.debug("Started WS Listener task.")
            
        pt = self._ping_task
        if not pt or pt.done():
            self._ping_task = loop.create_task(self._ping_loop())
            logger.debug("Started WS Ping task.")

        return True

    async def _establish_connection(self) -> bool:
        """Internal helper to handle the raw socket connection and auth."""
        # Force a fresh login if we've failed multiple times previously
        if not self.provider.session_token or self._reconnect_count > 1:
            logger.info("Capital.com WS: Requesting fresh session tokens...")
            success = await self.provider.login()
            if not success:
                logger.error("Capital.com WS auth failed: Broker login failed.")
                return False

        logger.info(f"Connecting to Capital.com WebSocket: {self.WS_URL}...")
        try:
            # ping_interval=None because Capital.com expects custom "ping" messages
            self.ws = await websockets.connect(self.WS_URL, ping_interval=None)
            
            # Re-subscribe to any existing epics upon connection
            if self._subscribed_epics:
                await self._send_subscription(list(self._subscribed_epics))
                
            logger.info("Capital.com WebSocket Socket Established.")
            return True
        except Exception as e:
            logger.error(f"WebSocket socket connection failed: {e}")
            return False

    async def _ping_loop(self):
        """Capital.com requires a ping message every 5-10 minutes. We'll send one every 5 minutes."""
        while self._running:
            try:
                await asyncio.sleep(300) # 5 minutes
                ws = self.ws
                if ws and getattr(ws.state, 'name', '') == 'OPEN':
                    payload = {
                        "destination": "ping",
                        "cst": self.provider.session_token,
                        "securityToken": self.provider.security_token
                    }
                    await ws.send(json.dumps(payload))
                    logger.debug("Sent WS Ping")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"WS ping loop error: {e}")

    async def subscribe(self, epics: List[str]):
        """Subscribe to live market data (ticks)."""
        new_epics = [e for e in epics if e not in self._subscribed_epics]
        if not new_epics:
            return
            
        self._subscribed_epics.update(new_epics)
        ws = self.ws
        if self._running and ws and getattr(ws.state, 'name', '') == 'OPEN':
            await self._send_subscription(list(self._subscribed_epics))
        else:
            logger.info("Saved subscription; will execute when socket is open.")

    async def _send_subscription(self, epics: List[str]):
        ws = self.ws
        if not ws or getattr(ws.state, 'name', '') != 'OPEN':
            return
            
        payload = {
            "destination": "marketData.subscribe",
            "cst": self.provider.session_token,
            "securityToken": self.provider.security_token,
            "payload": {
                "epics": epics
            }
        }
        try:
            # Cast for the linter as it might lose narrowing in try blocks
            await cast(Any, ws).send(json.dumps(payload))
            logger.info(f"Subscribed to WS ticks for: {epics}")
        except Exception as e:
            logger.error(f"Failed to send WS subscription data: {e}")

    async def _listen(self):
        """Continuously listen for incoming WebSocket messages."""
        reconnect_delay = 5.0
        max_delay = 60.0
        
        while self._running:
            try:
                ws = self.ws
                if not ws or getattr(ws.state, 'name', '') != 'OPEN':
                    logger.warning(f"WS socket not open in listener; attempting reconnect in {reconnect_delay}s...")
                    if await self._establish_connection():
                        reconnect_delay = 5.0  # Reset on success
                        continue
                    else:
                        await asyncio.sleep(reconnect_delay)
                        reconnect_delay = min(max_delay, reconnect_delay * 1.5)
                        continue

                message = await cast(Any, ws).recv()
                self._last_msg_time = asyncio.get_running_loop().time()
                self._reconnect_count = 0 # Reset on successful message receive
                reconnect_delay = 5.0  
                data = json.loads(message)
                
                # Handle tick updates
                if data.get("destination") == "quote" and "payload" in data:
                    payload = data["payload"]
                    epic = payload.get("epic")
                    bid = payload.get("bid")
                    ask = payload.get("ofr") # Capital.com uses 'ofr' for offer/ask
                    
                    if epic and bid and ask:
                        # Record tick for volume tracking
                        now = asyncio.get_running_loop().time()
                        if epic not in self._tick_volume:
                            self._tick_volume[epic] = []
                        self._tick_volume[epic].append(now)

                        logger.debug(f"Tick received: {epic} {bid}/{ask}")
                        for cb in self._callbacks:
                            asyncio.create_task(self._safe_invoke(cb, epic, float(bid), float(ask)))
                                
            except websockets.exceptions.ConnectionClosed as e:
                self._reconnect_count += 1
                logger.warning(f"Capital.com WS Connection closed ({e.code}). Re-establishing in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(max_delay, reconnect_delay * 1.5)
            except json.JSONDecodeError:
                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._reconnect_count += 1
                logger.error(f"Capital.com WS Listen Error: {e}")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(max_delay, reconnect_delay * 1.5)

    async def _safe_invoke(self, cb: Callable, symbol: str, bid: float, ask: float):
        try:
            if asyncio.iscoroutinefunction(cb):
                await cb(symbol, bid, ask)
            else:
                cb(symbol, bid, ask)
        except Exception as e:
            logger.error(f"Error in WS callback: {e}")

    async def close(self):
        """Cleanly close the WebSocket connection."""
        self._running = False
        pt = self._ping_task
        if pt:
            pt.cancel()
        lt = self._listen_task
        if lt:
            lt.cancel()
            
        ws = self.ws
        if ws:
            await ws.close()
            logger.info("Capital.com WebSocket connection closed.")
