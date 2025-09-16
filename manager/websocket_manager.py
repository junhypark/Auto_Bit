import asyncio
import sys
import certifi
import websockets
from datetime import datetime
import ssl
from manager.webhook_manager import send_webhook, send_error_webhook
import shared_resources

async def public_websocket_connect():
    """"
    업비트 websocket_public 용으로 사용할 웹소켓을 반환합니다.
    """
    url = "wss://api.upbit.com/websocket/v1"
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    try:
        websocket = await websockets.connect(url, ssl=ssl_context, compression="deflate")
        msg = f"✅ 웹소켓 연결 성공!"
        asyncio.create_task(send_webhook(msg))
        print(f"[{datetime.now()}]" + msg)
        shared_resources.upbit_websocket = websocket
    except Exception as e:
        msg = f"웹소켓 연결 실패: {e}"
        await send_error_webhook(msg)
        print(f"[{datetime.now()}]" + msg)
        sys.exit(0)
