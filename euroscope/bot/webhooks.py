"""
Webhook Dispatcher

Sends real-time HTTP POST alerts to user-configured webhook URLs
whenever a key event (e.g., Trade Opened, Trade Closed, New Signal) occurs.
"""

import json
import logging
import asyncio
import httpx
from typing import Dict, Any, List

logger = logging.getLogger("euroscope.api.webhooks")


class WebhookDispatcher:
    def __init__(self, config):
        self.config = config
        self.client = httpx.AsyncClient(timeout=5.0)
        
    def _get_urls(self) -> List[str]:
        """Fetch configured webhook URLs from bot settings or environment."""
        # Using environment variable for simplicity in this demo implementation
        # In a real app, this should be fetched from the bot's dynamic settings dictionary
        urls_str = getattr(self.config, "webhook_urls", "")
        if not urls_str:
            # Fallback to env var
            import os
            urls_str = os.getenv("EUROSCOPE_WEBHOOKS", "")
            
        if not urls_str:
            return []
            
        return [url.strip() for url in urls_str.split(",") if url.strip().startswith("http")]

    async def dispatch(self, event_type: str, payload: Dict[str, Any]):
        """
        Send a webhook event to all configured URLs.
        Runs fire-and-forget in the background to avoid blocking the bot.
        """
        urls = self._get_urls()
        if not urls:
            return
            
        data = {
            "event": event_type,
            "data": payload,
        }
        
        asyncio.create_task(self._send_all(urls, data))

    async def _send_all(self, urls: List[str], payload: dict):
        for url in urls:
            try:
                response = await self.client.post(url, json=payload)
                if response.status_code >= 400:
                    logger.warning(f"Webhook {url} failed with status {response.status_code}")
                else:
                    logger.debug(f"Webhook {event_type} delivered to {url}")
            except Exception as e:
                logger.error(f"Failed to dispatch webhook to {url}: {e}")

    async def close(self):
        await self.client.aclose()

