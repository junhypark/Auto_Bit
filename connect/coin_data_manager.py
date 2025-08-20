import asyncio
import random
import json
import ssl
import sys
import time

import aiohttp
import certifi
import jwt
import uuid
from datetime import datetime
# from calculator.coins_indicators_calculator import calculate_indicators
# from calculator.target_calculator import classify_targets
from connect.webhook_manager import send_error_webhook
from connect.websocket_manager import public_websocket_connect
import shared_resources

async def update_prices(trading_dict, trading_lock):
    error_send_limit = 10
    error_rcv_limit = 10

    while True:
        async with trading_lock:
            symbols = list(trading_dict.keys())
            if symbols:
                subscribe_msg = json.dumps([
                    {"ticket": "ticker_websocket"},
                    {"type": "ticker", "codes": symbols, "is_only_snapshot": True},
                    {"format": "DEFAULT"}
                ])
                try:
                    await shared_resources.upbit_websocket.send(subscribe_msg)
                except Exception as e:
                    message_snd = f"구독 메시지 전송 실패: "
                    error_send_limit -= 1

                    if error_send_limit == 0:
                        message_snd_webhook = f"웹소켓 데이터 수신 오류 및 재연결 10회 실패 : {e}. 프로그램을 종료합니다"
                        await send_error_webhook(message_snd_webhook)

                        sys.exit(0)
                    message = f"[{datetime.now()}]" + message_snd + f"{e} 웹소켓 재연결을 시도합니다."
                    await send_error_webhook(message)

                    # 웹소켓 재연결 시도
                    await public_websocket_connect()
                    await asyncio.sleep(1)
                    continue

                error_send_limit = 10

                for _ in range(len(symbols)):
                    try:
                        response = await shared_resources.upbit_websocket.recv()
                        data = json.loads(response)
                        code = data.get("code")
                        trade_price = data.get("trade_price")
                        if code and trade_price is not None:
                            trading_dict[code] = trade_price
                    except Exception as e:
                        message_recv = f"웹소켓 데이터 수신 오류: {e}"
                        print(f"[{datetime.now()}]", message_recv)
                        error_rcv_limit -= 1

                        if error_rcv_limit == 0:
                            message_recv_webhook = f"웹소켓 데이터 수신 오류 및 재연결 10회 실패: {e}. 프로그램을 종료합니다"
                            await send_error_webhook(message_recv_webhook)

                            sys.exit(0)

                        message = f"[{datetime.now()}]" + message_snd + f"{e} 웹소켓 재연결을 시도합니다."

                        await public_websocket_connect()
                        await send_error_webhook(message)
                        continue

                error_rcv_limit = 10
        await asyncio.sleep(10)

async def update_indicators_periodically(indicators_dict, target_dict, target_lock):
    