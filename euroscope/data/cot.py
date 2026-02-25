"""
Commitments of Traders (COT) Data Provider

Fetches institutional positioning data for EUR/USD from the CFTC API
or an alternative public source.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger("euroscope.data.cot")

class COTProvider:
    """
    Fetches COT positioning data for the Euro FX contract.
    CFTC Socrata API Endpoint: https://publicreporting.cftc.gov/resource/6dca-aqww.json
    Commodity Code for Euro FX: 099741
    """

    def __init__(self):
        self.base_url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
        self.cftc_contract_code = "099741" # Euro FX
        self.client = httpx.AsyncClient(timeout=15.0)

    async def get_latest_positioning(self) -> dict:
        """
        Fetch the most recent COT report for Euro FX.
        Returns net non-commercial (speculative) positioning.
        """
        try:
            # Socrata SoQL query:
            # Filter by market_and_exchange_names containing 'EURO FX' or cftc_contract_market_code='099741'
            # Order by report_date_as_yyyy_mm_dd descending
            # Limit to 1
            
            params = {
                "cftc_contract_market_code": self.cftc_contract_code,
                "$order": "report_date_as_yyyy_mm_dd DESC",
                "$limit": 1
            }

            response = await self.client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data:
                logger.warning("No COT data returned from CFTC API")
                return {"error": "No COT data found"}

            latest = data[0]
            
            # Non-commercial (Speculative) Positions
            nc_long = int(latest.get("noncomm_positions_long_all", 0))
            nc_short = int(latest.get("noncomm_positions_short_all", 0))
            nc_net = nc_long - nc_short
            
            # Commercial (Hedging) Positions
            comm_long = int(latest.get("comm_positions_long_all", 0))
            comm_short = int(latest.get("comm_positions_short_all", 0))
            comm_net = comm_long - comm_short
            
            report_date = latest.get("report_date_as_yyyy_mm_dd", "")

            # Determine bias
            bias = "neutral"
            if nc_net > 10000:
                bias = "bullish"
            elif nc_net < -10000:
                bias = "bearish"

            return {
                "report_date": report_date[:10] if report_date else "Unknown",
                "contract": "Euro FX",
                "non_commercial": {
                    "long": nc_long,
                    "short": nc_short,
                    "net": nc_net,
                    "bias": bias
                },
                "commercial": {
                    "long": comm_long,
                    "short": comm_short,
                    "net": comm_net
                },
                "raw_timestamp": report_date
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"CFTC API error: {e.response.status_code}")
            return {"error": f"API Error: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Failed to fetch COT data: {e}")
            return {"error": str(e)}

    async def close(self):
        await self.client.aclose()
