import asyncio
import os
from dotenv import load_dotenv

load_dotenv('./env')

indicators_dict = {}
target_dict = {}
trading_dict = {}
wallet_dict = {}
active_trades = set()
upbit_websocket = None

# 비동기 락
target_lock = asyncio.Lock()
trading_lock = asyncio.Lock()
active_lock = asyncio.Lock()

ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")

# 서버 측에서 이벤트 발생 시 전달할 내용을 위한 webhook
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
WEBHOOK_ERROR_URL = os.environ.get("WEBHOOK_ERROR_URL")

# 개별 거래 구매 금액
PURCHASE_VOLUME = int(os.environ.get("PURCHASE_VOLUME"))