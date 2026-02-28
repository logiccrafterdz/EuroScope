import asyncio
import websockets
import json
from euroscope.config import Config
from euroscope.trading.capital_provider import CapitalProvider

# Some common Capital.com WS endpoints found in docs
WS_URLS = [
    "wss://api-streaming-capital.backend-capital.com/connect",
    "wss://api-ws.capital.com/api/v1",
    "wss://api-capital.backend-capital.com/api/v1"
]

async def test_ws():
    config = Config.from_env()
    provider = CapitalProvider(
        config.data.capital_api_key, 
        config.data.capital_identifier, 
        config.data.capital_password
    )
    if not await provider.login():
        print("Login failed.")
        return
        
    print(f"Logged in. CST: {provider.session_token[:10]}...")
    
    success = False
    for url in WS_URLS:
        print(f"\n--- Testing WS URL: {url} ---")
        try:
            async with websockets.connect(url, ping_interval=None) as ws:
                print("Connected!")
                payload = {
                    "destination": "marketData.subscribe",
                    "cst": provider.session_token,
                    "securityToken": provider.security_token,
                    "payload": {
                        "epics": ["BTCUSD"]
                    }
                }
                await ws.send(json.dumps(payload))
                print(f"Sent subscription for BTCUSD")
                
                # Wait for 1 message (a 1-minute bar close)
                for i in range(1):
                    msg = await asyncio.wait_for(ws.recv(), timeout=65.0)
                    print(f"Msg {i+1}: {msg}")
                    
                success = True
                break
        except asyncio.TimeoutError:
            print("Timeout waiting for message. Subscription might have failed or no ticks.")
        except Exception as e:
            print(f"Error: {e}")
            
    await provider.close()

if __name__ == "__main__":
    asyncio.run(test_ws())
