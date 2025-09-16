import asyncio
import ssl
import time
import urllib
import uuid
from datetime import datetime
import aiohttp
import certifi
import jwt
from manager.webhook_manager import send_webhook, send_error_webhook
from shared_resources import PURCHASE_VOLUME, KST, last_buy_date, save_purchase, clear_purchase, persistent_purchases
import shared_resources

from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, time as dtime

if not hasattr(shared_resources, "lasy_buy_date"):
    shared_resources.last_buy_date = {}

KST = ZoneInfo("Asia/Seoul")

def _nexㅅ_morning_9_kst(now: datetime):
    target_today = now.replace(hour=9, minute=0, second=0, microsecond=0, tzinfo=KST)
    return target_today if now <= target_today else (target_today + timedelta(days=1))

async def order(ACCESS_KEY, SECRET_KEY, coin, type, volume):
    """
    Upbit 시장가 주문 함수.

    매개변수:
      - ACCESS_KEY: Upbit API Access Key
      - SECRET_KEY: Upbit API Secret Key
      - type: 주문 타입 ("bid"이면 매수, "ask"이면 매도)
      - volume: 주문 금액(매수 시) 또는 코인 수량(매도 시)

    리턴:
      - API 응답 JSON (dict)
    """
    # Upbit 주문 API 엔드포인트
    url = "https://api.upbit.com/v1/orders"
    # nonce 생성 (고유값)
    nonce = str(uuid.uuid4())
    # 거래할 마켓 (필요에 따라 변경)
    market = coin

    # 주문 파라미터 설정 (주문 종류에 따라 price 혹은 volume 사용)
    if type == "bid":
        # 매수(시장가) 주문: 'price' 파라미터에 주문 금액을 지정
        data = {
            "market": market,
            "side": "bid",
            "price": str(volume),  # 주문 금액 (원화)
            "ord_type": "price"  # 시장가 매수 주문은 ord_type이 "price"
        }
    elif type == "ask":
        # 매도(시장가) 주문: 'volume' 파라미터에 주문 수량을 지정
        data = {
            "market": market,
            "side": "ask",
            "volume": str(volume),  # 주문 코인 수량
            "ord_type": "market"  # 시장가 매도 주문은 ord_type이 "market"
        }
    else:
        raise ValueError("유효하지 않은 주문 타입입니다. 'bid' 또는 'ask'여야 합니다.")

    # JWT 페이로드에 필요한 값 설정 (쿼리 스트링 포함)
    payload = {
        "access_key": ACCESS_KEY,
        "nonce": nonce,
        "query": urllib.parse.urlencode(data)
    }

    # JWT 토큰 생성 (HS256 알고리즘 사용)
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    # ssl 적용
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    # aiohttp를 사용하여 비동기로 POST 요청 전송
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers, ssl=ssl_context) as response:
            # API 응답 JSON 반환
            return await response.json()


async def process_trade(ACCESS_KEY, SECRET_KEY, coin, trading_dict, indicators_dict,
                        active_trades, wallet_dict, trading_lock, active_lock):
    """
    변경 후 규칙:
      • 매수: 매일 KST 09:00에 코인별 1회 매수
      • 매도: 현재가 >= (매수가 * 1.03)일 때 전량 매도
    """
    print(f"[{datetime.now()}] {coin} 거래 시작")

    purchase_volume = PURCHASE_VOLUME
    err_flag = False

    # 1) 당일 매수 여부 확인
    now = datetime.now(KST)
    today = now.date()
    if last_buy_date.get(coin) == today:
        print(f"[{datetime.now()}] {coin}는 이미 오늘({today}) 매수 완료. 거래 스킵.")
        async with trading_lock, active_lock:
            active_trades.discard(coin)
            trading_dict.pop(coin, None)
        return

    # 2) 09:00까지 대기(이미 지났으면 즉시 매수)
    target_dt = _next_morning_9_kst(now)
    if target_dt.date() == today and now < target_dt:
        while True:
            if datetime.now(KST) >= target_dt:
                break
            await asyncio.sleep(1)

    # 3) 매수 실행 (시장가, 금액 기준)
    try:
        result = await order(ACCESS_KEY, SECRET_KEY, coin, "bid", purchase_volume)
        if "error" in result:
            err_flag = True
            print(f"[{datetime.now()}] {coin} 매수 실패, 서버 오류: {result.get('error')}")
        else:
            message = f"{coin} 매수 완료 (일 1회 규칙)"
            print(f"[{datetime.now()}]", message)
            asyncio.create_task(send_webhook(message))
    except Exception as e:
        err_flag = True
        print(f"[{datetime.now()}] {coin} 매수 실패, 예외: {e}")

    # 4) 매수 실패 시 종료
    if err_flag:
        async with trading_lock, active_lock:
            active_trades.discard(coin)
            trading_dict.pop(coin, None)
        return

    # 5) 지갑에서 평균매수가/수량 확보 (Upbit 계좌 동기화 딕셔너리)
    #    실패/지연 대비: persistent_purchases fallback 사용
    avg_buy_price, balance = None, None
    timeout = datetime.now().timestamp() + 30  # 최대 30초 대기
    while datetime.now().timestamp() < timeout:
        if coin in wallet_dict and wallet_dict[coin] is not None:
            # shared wallet: { "KRW-ETH": [avg_buy_price(float), balance(str)] }
            avg_buy_price = float(wallet_dict[coin][0])
            balance = wallet_dict[coin][1]
            break
        await asyncio.sleep(1)

    # 5-1) fallback: 방금 체결되었으나 API 반영 지연/에러 시, 현재가 기반 임시 저장
    if avg_buy_price is None:
        # 티커 스냅샷에서 근사 (시장가 매수이므로 큰 오차는 없다고 가정)
        approx_price = float(trading_dict.get(coin, 0.0))
        if approx_price <= 0:
            approx_price = 0.0
        avg_buy_price = approx_price
        # 매수 금액 / 가격 = 수량 추정
        try:
            est_qty = purchase_volume / approx_price if approx_price > 0 else 0.0
        except Exception:
            est_qty = 0.0
        balance = str(est_qty)

    # 6) 구매 기록 영속 저장 (재시작 대비)
    save_purchase(coin, avg_buy_price, float(balance) if isinstance(balance, (int, float)) else float(balance))

    # 7) +3% 익절 조건 모니터링
    take_profit_price = avg_buy_price * 1.03
    while True:
        price = trading_dict.get(coin)
        if price is not None and price >= take_profit_price:
            result = await order(ACCESS_KEY, SECRET_KEY, coin, "ask", balance)
            if "error" in result and "message" in result["error"]:
                msg = f"Error: {result['error']['message']}, 코인 개별 매도 필요"
                await send_error_webhook(msg)
            else:
                print(f"[{datetime.now()}] {coin} 매도 완료 (+3% 익절)")
                # 매도 완료 시 로컬 구매 기록 정리(같은 날 재매수 금지 유지 원하면 주석 처리)
                clear_purchase(coin)
            break
        await asyncio.sleep(1)

    # 8) 종료 정리
    async with trading_lock, active_lock:
        active_trades.discard(coin)
        trading_dict.pop(coin, None)
        print(f"[{datetime.now()}] {coin} 거래 종료. trading_dict, active_trades 에서 삭제됨.")


async def execute_trades(ACCESS_KEY, SECRET_KEY, trading_dict, active_trades, indicators_dict, wallet_dict
                         , trading_lock, active_lock):
    """
    trading_dict에 존재하는 코인에 대해 개별 비동기 거래를 실행합니다.
    이미 거래 중인 코인(active_trades에 포함된 코인)은 건너뛰며,
    거래가 완료되면 각 작업이 trading_dict에서 해당 코인을 삭제합니다.

    함수 동작 방식:
      1. trading_dict는 외부에서 1초마다 업데이트됩니다.
      2. trading_dict에 있는 코인에 대해 거래를 개별 비동기 작업(Task)으로 진행합니다.
      3. 각 작업은 완료되면 trading_dict에서 자신의 코인을 삭제합니다.
      4. 이후 trading_dict 업데이트 시, 삭제된 코인의 자리는 다시 채워져 추가 거래가 진행됩니다.
    """

    while True:
        # trading_dict는 매 1초마다 업데이트되므로, 그 시점의 거래 대상 코인 목록을 확인
        for coin in list(trading_dict.keys()):
            async with active_lock:
                # 거래중이 아닌, trading_dict에 존재하는 코인만 거래를 시작함
                if coin not in active_trades:
                    active_trades.add(coin)
                    asyncio.create_task(
                        process_trade(ACCESS_KEY, SECRET_KEY, coin, trading_dict, indicators_dict,
                                      active_trades, wallet_dict, trading_lock, active_lock)
                    )
        await asyncio.sleep(1)
