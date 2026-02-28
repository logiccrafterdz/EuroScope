import asyncio
import json
import logging
import websockets
from typing import List, Callable, Optional, Dict, Any

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
        
        # Keep references to background tasks so they don't get garbage collected
        self._listen_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None

    def add_callback(self, callback: Callable[[str, float, float], None]):
        """Register a callback for incoming tick updates."""
        self._callbacks.append(callback)

    async def connect(self):
        """Establish connection and start listener tasks."""
        if not self.provider.session_token:
            success = await self.provider.login()
            if not success:
                logger.error("Capital.com WS failed: Broker not authenticated.")
                return False

        logger.info(f"Connecting to Capital.com WebSocket: {self.WS_URL}...")
        try:
            # ping_interval=None because Capital.com expects custom "ping" messages
            self.ws = await websockets.connect(self.WS_URL, ping_interval=None)
            self._running = True
            
            # Start background tasks
            loop = asyncio.get_running_loop()
            self._listen_task = loop.create_task(self._listen())
            self._ping_task = loop.create_task(self._ping_loop())
            
            logger.info("Capital.com WebSocket Connected.")
            
            # Re-subscribe to any existing epics upon connection
            if self._subscribed_epics:
                await self._send_subscription(list(self._subscribed_epics))
                
            return True
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            self._running = False
            return False

    async def _ping_loop(self):
        """Capital.com requires a ping message every 5-10 minutes. We'll send one every 5 minutes."""
        while self._running:
            await asyncio.sleep(300) # 5 minutes
            if self.ws and getattr(self.ws.state, 'name', '') == 'OPEN':
                try:
                    payload = {
                        "destination": "ping",
                        "cst": self.provider.session_token,
                        "securityToken": self.provider.security_token
                    }
                    await self.ws.send(json.dumps(payload))
                    logger.debug("Sent WS Ping")
                except Exception as e:
                    logger.warning(f"WS ping failed: {e}")

    async def subscribe(self, epics: List[str]):
        """Subscribe to live market data (ticks)."""
        new_epics = [e for e in epics if e not in self._subscribed_epics]
        if not new_epics:
            return
            
        self._subscribed_epics.update(new_epics)
        if self.ws and getattr(self.ws.state, 'name', '') == 'OPEN':
            await self._send_subscription(list(self._subscribed_epics))
        else:
            # If not connected yet, it will automatically subscribe upon connect()
            logger.info("Saved subscription; will execute when connected.")

    async def _send_subscription(self, epics: List[str]):
        payload = {
            "destination": "marketData.subscribe",
            "cst": self.provider.session_token,
            "securityToken": self.provider.security_token,
            "payload": {
                "epics": epics
            }
        }
        try:
            await self.ws.send(json.dumps(payload))
            logger.info(f"Subscribed to WS ticks for: {epics}")
        except Exception as e:
            logger.error(f"Failed to send WS subscription data: {e}")

    async def _listen(self):
        """Continuously listen for incoming WebSocket messages."""
        while self._running:
            try:
                message = await self.ws.recv()
                data = json.loads(message)
                
                # Handle tick updates
                if data.get("destination") == "quote" and "payload" in data:
                    payload = data["payload"]
                    epic = payload.get("epic")
                    bid = payload.get("bid")
                    ask = payload.get("ofr") # Capital.com uses 'ofr' for offer/ask
                    
                    if epic and bid and ask:
                        logger.debug(f"Tick received: {epic} {bid}/{ask}")
                        for cb in self._callbacks:
                            asyncio.create_task(self._safe_invoke(cb, epic, float(bid), float(ask)))
                                
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Capital.com WS Connection closed. Attempting reconnect...")
                self._running = False
                await asyncio.sleep(5)
                await self.connect()
            except json.JSONDecodeError:
                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Capital.com WS Listen Error: {e}")

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
        if self._ping_task:
            self._ping_task.cancel()
        if self._listen_task:
            self._listen_task.cancel()
            
        if self.ws:
            await self.ws.close()
            logger.info("Capital.com WebSocket connection closed.")
