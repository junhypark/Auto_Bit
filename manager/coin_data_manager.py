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
from calculator.coins_indicators_calculator import calculate_indicators
from calculator.target_calculator import classify_targets
from manager.webhook_manager import send_error_webhook
from manager.websocket_manager import public_websocket_connect
import shared_resources


async def update_prices(trading_dict, trading_lock):
    """
    웹소켓을 사용해 target_dict에 있는 코인들의 가격(trade_price)을 1초마다 업데이트합니다.
    error_send/rcv_limit:
        오류 제한 횟수를 의미합니다. 일정 횟수 이상 업데이트에 실패한다면, 프로그램을 종료합니다.
    """
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
                    # print(f"[{datetime.now()}] 구독 메시지 전송: {subscribe_msg}")

                # 오류 발생시 웹훅으로 전달
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

                # 구독한 코인 수만큼 응답 받기
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
                            message_recv_webhook = f"웹소켓 데이터 수신 오류 및 재연결 10회 실패 : {e}. 프로그램을 종료합니다"
                            await send_error_webhook(message_recv_webhook)

                            sys.exit(0)
                        message = f"[{datetime.now()}]" + message_snd + f"{e} 웹소켓 재연결을 시도합니다."

                        # 웹소켓 재연결 시도
                        await public_websocket_connect()

                        await send_error_webhook(message)
                        continue

                error_rcv_limit = 10

                # print(f"[{datetime.now()}] trading_dict 업데이트 완료.")
            # else:
            # print(f"[{datetime.now()}] 업데이트할 타겟 코인이 없습니다.")

        # 1초마다 반복
        await asyncio.sleep(1)


async def update_indicators_periodically(indicators_dict, target_dict, target_lock):
    """
    매 분(분이 바뀔 때) 동기 함수인 지표 계산 및 타겟 분류를 실행합니다.
    asyncio.to_thread를 사용하여 해당 작업이 진행되는 동안에도 이벤트 루프의 다른 작업(예: target_dict 업데이트)은 계속됩니다.
    """
    previous_minute = datetime.now().minute
    while True:
        current_minute = datetime.now().minute
        if current_minute != previous_minute:
            previous_minute = current_minute

            start_time = time.time()

            print(f"\n[{datetime.now()}] 지표 업데이트 시작")
            # calculate_indicators와 classify_targets를 별도 스레드에서 실행하여 이벤트 루프 블로킹 방지
            await asyncio.to_thread(calculate_indicators, indicators_dict, 2)
            print(f"[{datetime.now()}] 지표 업데이트 완료")

            # indicators_dict를 분류해서 특정 코인들을 target_dict에 저장
            # 업데이트 실패(락을 해제하지 못하는 경우) 관리

            async with target_lock:
                target_dict.clear()  # target_dict 초기화
                await asyncio.to_thread(classify_targets, indicators_dict, target_dict)
                print(f"[{datetime.now()}] 타겟 분류 후 target_dict: [{', '.join(target_dict.keys())}]")

            end_time = time.time()

            duration = end_time - start_time

            # 보조지표 연산 예상 범주 시간 초과시 알람 전송.
            if duration > 30:
                duration_msg = f"보조지표 연산에 소요시간 30초 초과. 총 {duration}초 소요."
                asyncio.create_task(send_error_webhook(duration_msg))

        await asyncio.sleep(1)


async def update_trading_dict(trading_dict, target_dict, trading_lock, target_lock):
    """
    target_dict에서 랜덤하게 항목을 선택하여 trading_dict를 3초마다 업데이트합니다.
    trading_dict의 항목 수가 5개이면 추가하지 않고, 5개 미만이면 부족한 개수만큼 target_dict에서
    (이미 trading_dict에 없는 항목들 중에서) 랜덤하게 선택하여 추가합니다.
    """
    while True:
        async with target_lock, trading_lock:
            if target_dict:
                if len(trading_dict) < 5:
                    # trading_dict에 추가해야 할 개수 계산
                    needed = 5 - len(trading_dict)

                    # target_dict의 키 중 이미 trading_dict에 없는 키만 선택
                    available_keys = [key for key in target_dict.keys() if key not in trading_dict]

                    if available_keys:
                        # available_keys에서 부족한 개수만큼 랜덤 샘플링
                        sample_keys = random.sample(available_keys, k=min(needed, len(available_keys)))

                        # trading_dict에 추가한 이후 target_dict에서 제거
                        # 거래종료 즉시 추가 등록 방지
                        for key in sample_keys:
                            trading_dict[key] = target_dict[key]
                            target_dict.pop(key)

                        print(f"[{datetime.now()}] trading_dict: [{', '.join(trading_dict.keys())}] 업데이트")
                    # else:print(f"[{datetime.now()}] 새로운 항목이 없어 trading_dict 업데이트 안함. 현재 trading_dict: {trading_dict}")
                # else:
                #     print(f"[{datetime.now()}] trading_dict가 이미 5개입니다: {trading_dict}")
            # else:print(f"[{datetime.now()}] target_dict에 항목이 없어 trading_dict 업데이트 안함.")

        await asyncio.sleep(3)


async def update_wallet_realtime(ACCESS_KEY, SECRET_KEY, wallet_dict):
    error_limit = 100  # 연속으로 발생하는 오류 한도
    while True:
        # JWT 페이로드 생성: access_key와 nonce (중복되지 않는 임의의 값)
        payload = {
            "access_key": ACCESS_KEY,
            "nonce": str(uuid.uuid4()),
        }

        # HS256 알고리즘을 사용하여 JWT 토큰 생성
        jwt_token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

        # Authorization 헤더에 JWT 토큰 포함
        headers = {"Authorization": f"Bearer {jwt_token}"}

        # 업비트 전체 계좌 조회 API 엔드포인트
        url = "https://api.upbit.com/v1/accounts"

        ssl_context = ssl.create_default_context(cafile=certifi.where())

        # GET 요청 전송, 오류 발생시 sec 초 후 재시도
        sec = 1

        # 오류 발생 빈도 확인 및 시스템 종료 함수
        async def error_limit_count():
            nonlocal error_limit
            error_limit -= 1

            if error_limit == 0:
                await send_error_webhook(f"wallet_dict Rest API {error_limit}회 이상 오류 발생. 시스템 종료.")
                sys.exit(0)

        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                async with session.get(url, headers=headers) as response:

                    if response.status == 429:
                        print(f"wallet_dict 업데이트 429 오류 발생 . {sec}초 후 재시도합니다.")
                        await error_limit_count()
                        await asyncio.sleep(sec)
                        continue
                    # 200 OK가 아닌 경우 재시도 (필요에 따라 세부 처리 가능)
                    if response.status != 200:
                        print(f"wallet_dict 업데이트 HTTP 오류 상태 {response.status} 발생. {sec}초 후 재시도합니다.")
                        await error_limit_count()
                        await asyncio.sleep(sec)
                        continue

                    try:
                        response_data = await response.json()
                    except Exception as e:
                        print("JSON 디코딩 오류: 응답 데이터를 확인하세요.", e)
                        await error_limit_count()
                        await asyncio.sleep(sec)
                        continue

        except aiohttp.ClientError as e:
            print(f"wallet_dict 업데이트 기타 오류 발생 : {e}. {sec}초 후 재시도합니다.")
            await error_limit_count()
            await asyncio.sleep(sec)
            continue

        # 정상 요청 시 error_limit 초기화
        error_limit = 100

        # 응답 데이터에 전체 오류가 포함된 경우 오류 출력 및 즉시 종료
        if "error" in response_data:
            error_msg = f"wallet_dict Rest API 응답 오류: {response_data['error']} 프로그램 종료."
            print(error_msg)
            await send_error_webhook(error_msg)  # 오류 전송 완료까지 대기

            sys.exit(0)

        # wallet_dict의 기존 내용을 모두 삭제
        wallet_dict.clear()

        # 응답 받은 각 계좌 정보를 순회
        for account in response_data:
            currency = account.get("currency")

            # currency가 "KRW"인 항목은 제외
            if currency == "KRW":
                continue

            # 매수 평균 가격과 매수 수량 추출
            avg_buy_price = account.get("avg_buy_price")
            balance = account.get("balance")

            # 코인명을 "KRW-{통화}" 형태로 생성 (예: ONDO -> KRW-ONDO)
            coin_name = f"KRW-{currency}"

            # wallet_dict에 {코인명: [매수 평균 가격, 매수 수량]} 형식으로 저장
            wallet_dict[coin_name] = [float(avg_buy_price), balance]

        # print(f"wallet_dict [{', '.join(wallet_dict.keys())}] 업데이트 완료")

        await asyncio.sleep(1)
