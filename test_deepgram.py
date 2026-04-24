import asyncio
import os
import websockets
from dotenv import load_dotenv

load_dotenv()
_DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

async def test_connection():
    """Test Deepgram WebSocket connection"""
    url = (
        f"wss://api.deepgram.com/v1/listen"
        f"?model=nova-2&encoding=linear16&sample_rate=16000&channels=1"
        f"&smart_format=true&interim_results=true&utterance_end_ms=1500"
    )
    
    print(f"[TEST] API key present: {bool(_DEEPGRAM_API_KEY)}")
    print(f"[TEST] API key length: {len(_DEEPGRAM_API_KEY) if _DEEPGRAM_API_KEY else 0}")
    print(f"[TEST] Connecting to: {url[:100]}...")
    
    try:
        async with websockets.connect(url, additional_headers={"Authorization": f"Token {_DEEPGRAM_API_KEY}"}) as ws:
            print("[TEST] [OK] Connected to Deepgram!")
            await ws.send(b'\x00' * 1024)  # Send dummy audio
            result = await asyncio.wait_for(ws.recv(), timeout=2)
            print(f"[TEST] Received: {result[:100]}")
            return True
    except asyncio.TimeoutError:
        print("[TEST] [TIMEOUT] Timeout (but connection may have worked)")
        return True
    except Exception as e:
        print(f"[TEST] [ERROR] {type(e).__name__}: {e}")
        return False

asyncio.run(test_connection())
