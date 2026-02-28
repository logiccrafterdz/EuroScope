import asyncio
import websockets

async def inspect_ws():
    url = "wss://api-streaming-capital.backend-capital.com/connect"
    try:
        async with websockets.connect(url) as ws:
            print(f"WS Type: {type(ws)}")
            print(f"State: {ws.state}")
            print(f"State Name: {ws.state.name}")
            # print(f"Attributes: {dir(ws)}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_ws())
