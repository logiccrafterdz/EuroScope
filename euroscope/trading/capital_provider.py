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

    async def get_price(self, symbol: str = "EURUSD", _retry_count: int = 0) -> Optional[Dict[str, float]]:
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
                if response.status == 401 and _retry_count < 1:
                    logger.warning("get_price: 401 received, re-authenticating...")
                    if await self.login():
                        return await self.get_price(symbol, _retry_count=_retry_count + 1)
                    logger.error("get_price: re-login failed after 401")
                    return None
                
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
                    
                def _extract_mid(price_block: dict | None) -> Optional[float]:
                    if not price_block:
                        return None
                    if "mid" in price_block and price_block["mid"] is not None:
                        return price_block["mid"]
                    bid = price_block.get("bid")
                    ask = price_block.get("ask")
                    if bid is not None and ask is not None:
                        return (bid + ask) / 2
                    return bid if bid is not None else ask

                records = []
                for p in prices:
                    snapshot = p.get("snapshotTimeUTC", "").replace("T", " ")
                    open_mid = _extract_mid(p.get("openPrice"))
                    high_mid = _extract_mid(p.get("highPrice"))
                    low_mid = _extract_mid(p.get("lowPrice"))
                    close_mid = _extract_mid(p.get("closePrice"))
                    if open_mid is None or high_mid is None or low_mid is None or close_mid is None:
                        continue
                    records.append({
                        "time": pd.to_datetime(snapshot),
                        "Open": open_mid,
                        "High": high_mid,
                        "Low": low_mid,
                        "Close": close_mid,
                        "Volume": float(p.get("lastTradedVolume", 0))
                    })
                    
                if not records:
                    return None
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

    async def get_account_info(self, _retry_count: int = 0) -> Dict[str, Any]:
        """Fetch account balance, equity, and other financial metrics."""
        if not self.session_token:
            if not await self.login(): return {"success": False, "error": "Login failed"}
            
        url = f"{self.DEMO_URL}/accounts"
        headers = {
            "X-CAP-API-KEY": self.api_key,
            "CST": self.session_token,
            "X-SECURITY-TOKEN": self.security_token
        }
        
        try:
            session = await self._get_session()
            async with session.get(url, headers=headers) as response:
                if response.status == 401 and _retry_count < 1:
                    logger.warning("get_account_info: 401 received, re-authenticating...")
                    if await self.login():
                        return await self.get_account_info(_retry_count=_retry_count + 1)
                    return {"success": False, "error": "Re-authentication failed"}
                
                response.raise_for_status()
                data = await response.json()
                # Capital.com returns a list of accounts
                accounts = data.get("accounts", [])
                for acc in accounts:
                    if acc.get("accountId") == self.account_id or not self.account_id:
                        raw_balance = acc.get("balance")
                        raw_equity = acc.get("equity")
                        
                        balance_val = 0.0
                        if isinstance(raw_balance, dict):
                            balance_val = float(raw_balance.get("balance", 0.0))
                        elif isinstance(raw_balance, (int, float)):
                            balance_val = float(raw_balance)
                            
                        equity_val = None
                        if isinstance(raw_equity, dict):
                            # Default to balance + profitLoss if equity key not found
                            eq_base = float(raw_equity.get("equity", raw_equity.get("balance", balance_val)))
                            profit = float(raw_equity.get("profitLoss", 0.0))
                            # Capital.com equity dict might just give balance and profitLoss
                            if "equity" not in raw_equity and "balance" in raw_equity:
                                equity_val = eq_base + profit
                            else:
                                equity_val = eq_base
                        elif isinstance(raw_equity, (int, float)):
                            equity_val = float(raw_equity)
                            
                        if equity_val is None:
                            equity_val = balance_val
                            
                        return {
                            "success": True,
                            "account_id": acc.get("accountId"),
                            "account_name": acc.get("accountName"),
                            "balance": balance_val,
                            "equity": equity_val,
                            "available": acc.get("available"),
                            "currency": acc.get("currency"),
                            "status": acc.get("status")
                        }
                return {"success": False, "error": "Account not found"}
        except Exception as e:
            logger.error(f"Failed to fetch account info: {e}")
            return {"success": False, "error": str(e)}

    async def close(self):
        if self._session:
            await self._session.close()
