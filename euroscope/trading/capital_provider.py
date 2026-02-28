import aiohttp
import json
import logging
import asyncio
import pandas as pd
from datetime import datetime, UTC
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class CapitalProvider:
    """
    Interface for Capital.com REST & WebSocket API.
    Handles session management, market data, and order execution.
    """
    
    DEMO_URL = "https://api-capital.backend-capital.com/api/v1"
    WS_DEMO_URL = "wss://api-ws.capital.com/api/v1"
    
    # Epic mappings
    EPICS = {
        "EURUSD": "EURUSD",
        "GBPUSD": "GBPUSD",
    }
    
    # Resolution mappings
    RESOLUTIONS = {
        "M1": "MINUTE",
        "M15": "MINUTE_15",
        "H1": "HOUR",
        "H4": "HOUR_4",
        "D1": "DAY",
        "W1": "WEEK",
    }
    
    def __init__(self, api_key: str, identifier: str, password: str):
        self.api_key = api_key
        self.identifier = identifier
        self.password = password
        
        self.session_token = None  # CST
        self.security_token = None # X-SECURITY-TOKEN
        self.account_id = None
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def login(self) -> bool:
        """Authenticate and establish session tokens with RSA encryption support."""
        # 1. Get Encryption Key & TimeStamp
        url_enc = f"{self.DEMO_URL}/session/encryptionKey"
        headers_enc = {"X-CAP-API-KEY": self.api_key}
        
        encryption_key = None
        timestamp = None
        
        try:
            session = await self._get_session()
            async with session.get(url_enc, headers=headers_enc) as resp:
                if resp.status == 200:
                    data_enc = await resp.json()
                    encryption_key = data_enc.get("encryptionKey")
                    timestamp = data_enc.get("timeStamp")
        except Exception as e:
            logger.warning(f"Could not fetch encryption key: {e}")

        # 2. Encrypt password if key is available
        login_password = self.password
        if encryption_key and timestamp:
            try:
                from Crypto.PublicKey import RSA
                from Crypto.Cipher import PKCS1_v1_5
                import base64
                
                key_der = base64.b64decode(encryption_key)
                public_key = RSA.importKey(key_der)
                cipher = PKCS1_v1_5.new(public_key)
                
                # Format: password|timestamp
                message = f"{self.password}|{timestamp}".encode('utf-8')
                encrypted_bytes = cipher.encrypt(message)
                login_password = base64.b64encode(encrypted_bytes).decode('utf-8')
                logger.info("Using encrypted password for login.")
            except Exception as e:
                logger.error(f"Encryption failed: {e}")
                # Fallback to plain password

        # 3. Establish Session
        url = f"{self.DEMO_URL}/session"
        headers = {
            "X-CAP-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "identifier": self.identifier,
            "password": login_password,
            "encryptedPassword": True if encryption_key else False
        }
        
        try:
            session = await self._get_session()
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"Capital.com login failed: {response.status} - {text}")
                    return False
                
                self.session_token = response.headers.get("CST")
                self.security_token = response.headers.get("X-SECURITY-TOKEN")
                
                data = await response.json()
                self.account_id = data.get("currentAccountId")
                
                logger.info(f"Successfully logged into Capital.com. Account: {self.account_id}")
                return True
        except Exception as e:
            logger.error(f"Capital.com login exception: {e}")
            return False

    async def get_price(self, symbol: str = "EURUSD") -> Optional[Dict[str, float]]:
        """Fetch current market prices for a symbol."""
        if not self.session_token:
            if not await self.login(): return None
            
        url = f"{self.DEMO_URL}/markets/{symbol}"
        headers = {
            "X-CAP-API-KEY": self.api_key,
            "CST": self.session_token,
            "X-SECURITY-TOKEN": self.security_token
        }
        
        try:
            session = await self._get_session()
            async with session.get(url, headers=headers) as response:
                if response.status == 401:
                    await self.login() # Retry once
                    return await self.get_price(symbol)
                
                response.raise_for_status()
                data = await response.json()
                snapshot = data.get("snapshot", {})
                
                bid = snapshot.get("bid")
                ask = snapshot.get("offer")
                
                if bid is None or ask is None:
                    return None
                    
                price = (bid + ask) / 2
                
                return {
                    "symbol": symbol,
                    "price": round(price, 5),
                    "bid": bid,
                    "ask": ask,
                    "high": snapshot.get("high"),
                    "low": snapshot.get("low"),
                    "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
                }
        except Exception as e:
            logger.error(f"Failed to fetch price for {symbol}: {e}")
            return None

    async def get_candles(self, symbol: str, timeframe: str = "H1", count: int = 100) -> Optional[pd.DataFrame]:
        """Fetch historical candles."""
        if not self.session_token:
            if not await self.login(): return None
            
        resolution = self.RESOLUTIONS.get(timeframe.upper(), "HOUR")
        url = f"{self.DEMO_URL}/prices/{symbol}"
        params = {
            "resolution": resolution,
            "max": count
        }
        headers = {
            "X-CAP-API-KEY": self.api_key,
            "CST": self.session_token,
            "X-SECURITY-TOKEN": self.security_token
        }
        
        try:
            session = await self._get_session()
            async with session.get(url, params=params, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
                prices = data.get("prices", [])
                
                if not prices:
                    return None
                    
                records = []
                for p in prices:
                    snapshot = p.get("snapshotTimeUTC", "").replace("T", " ")
                    records.append({
                        "time": pd.to_datetime(snapshot),
                        "Open": p["openPrice"]["mid"],
                        "High": p["highPrice"]["mid"],
                        "Low": p["lowPrice"]["mid"],
                        "Close": p["closePrice"]["mid"],
                        "Volume": float(p.get("lastTradedVolume", 0))
                    })
                    
                df = pd.DataFrame(records)
                df.set_index("time", inplace=True)
                return df
        except Exception as e:
            logger.error(f"Failed to fetch candles for {symbol}: {e}")
            return None

    async def execute_trade(self, symbol: str, direction: str, size: float, 
                      stop_loss: float = None, take_profit: float = None) -> Dict[str, Any]:
        """Place a market order."""
        if not self.session_token:
            if not await self.login(): return {"success": False, "error": "Login failed"}
            
        url = f"{self.DEMO_URL}/positions"
        headers = {
            "X-CAP-API-KEY": self.api_key,
            "CST": self.session_token,
            "X-SECURITY-TOKEN": self.security_token
        }
        
        payload = {
            "epic": symbol,
            "direction": "BUY" if direction.upper() == "BUY" else "SELL",
            "size": size,
            "stopLevel": stop_loss,
            "profitLevel": take_profit,
            "guaranteedStop": False
        }
        
        try:
            session = await self._get_session()
            async with session.post(url, json=payload, headers=headers) as response:
                response.raise_for_status()
                res_data = await response.json()
                return {"success": True, "data": res_data}
        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            return {"success": False, "error": str(e)}

    async def close(self):
        if self._session:
            await self._session.close()
