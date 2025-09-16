import asyncio
import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from pathlib import Path
from datetime import datetime as _dt
import json

load_dotenv()  # .env 파일 로드

KST = ZoneInfo("Asia/Seoul")
DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)
PURCHASES_FILE = DATA_DIR / "purchases.json"

# 공유 자원 (각 Task들이 사용하는 데이터)
indicators_dict = {}
target_dict = {}
trading_dict = {}
wallet_dict = {}
active_trades = set()
upbit_websocket = None


# 비동기 락 (각 공유 자원별로 생성)
target_lock = asyncio.Lock()
trading_lock = asyncio.Lock()
active_lock = asyncio.Lock()

# 업비트 API 키
ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")

# 웹훅 주소
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
WEBHOOK_ERROR_URL = os.environ.get("WEBHOOK_ERROR_URL")

# 개별 거래 구매 금액
PURCHASE_VOLUME = int(os.environ.get("PURCHASE_VOLUME"))

last_buy_date = {}            # { "KRW-BTC": date, ... }
persistent_purchases = {}     # { "KRW-BTC": {"date":"YYYY-MM-DD","buy_price":float,"volume":float} }

def load_purchases():
    """구매 기록 로드 (프로그램 시작 시 1회)"""
    global persistent_purchases, last_buy_date
    if PURCHASES_FILE.exists():
        try:
            with open(PURCHASES_FILE, "r", encoding="utf-8") as f:
                persistent_purchases = json.load(f)
            # 날짜 hydrates
            for coin, rec in persistent_purchases.items():
                if "date" in rec:
                    last_buy_date[coin] = _dt.fromisoformat(rec["date"]).date()
        except Exception:
            persistent_purchases = {}

def save_purchase(coin: str, buy_price: float, volume: float):
    """매수 직후 구매 기록 저장"""
    persistent_purchases[coin] = {
        "date": _dt.now(KST).date().isoformat(),
        "buy_price": float(buy_price),
        "volume": float(volume),
    }
    with open(PURCHASES_FILE, "w", encoding="utf-8") as f:
        json.dump(persistent_purchases, f, ensure_ascii=False, indent=2)
    # 당일 1회 규칙 반영
    last_buy_date[coin] = _dt.now(KST).date()

def clear_purchase(coin: str):
    """매도 완료 후 로컬 구매 기록 삭제(선택적)"""
    last_buy_date.pop(coin, None)
    if coin in persistent_purchases:
        persistent_purchases.pop(coin)
        with open(PURCHASES_FILE, "w", encoding="utf-8") as f:
            json.dump(persistent_purchases, f, ensure_ascii=False, indent=2)

# 모듈 import 시 자동 로드
load_purchases()