import asyncio
import websockets
import ssl
import certifi
import json

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
# websocket 주소

# WebSocket을 사용하는 이유? (RestAPI대신)
# 서버와 클라이언트 간 실시간 양방향 통신이 가능하다
# 한 번 연결되면 지속적으로 데이터를 주고받을 수 있음
# 서버에서 데이터가 변경되면 즉시 클라이언트에 전송됨
# 평균 1 ~ 10 ms / REST => 100~200ms

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ssl_context.load_verify_locations(cafile=certifi.where())

# TSL 층을 사용하여 Authorization 확실의 목적성 부여

async def connect_to_websocket(connection_id):
    try:
        async with websockets.connect(UPBIT_WS_URL, ssl=ssl_context) as websocket:
            subscribe_msg = [
                {"ticket": f"test-{connection_id}"},
                {"type": "ticker", "codes": ["KRW-BTC"]}
            ]   # websocket 요청 내용

            await websocket.send(json.dumps(subscribe_msg))
            print(f"WebSocket {connection_id} connected and subscribed.")

            while True:
                response = await websocket.recv()
                print(f"WebSocket {connection_id} received data: {response}")
    except Exception as e:
        print(f"WebSocket {connection_id} error: {e}")
    
async def main():
    num_connections = 5
    tasks = [connect_to_websocket(i) for i in range(num_connections)]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())