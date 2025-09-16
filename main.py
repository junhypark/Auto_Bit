from manager.websocket_manager import public_websocket_connect
from manager.coin_data_manager import update_prices, update_indicators_periodically, update_trading_dict, update_wallet_realtime
from trading import execute_trades
from shared_resources import *

async def main():
    """
    프로그램을 실행하는 메인함수입니다. 비동기적인 작업을 동시에 실행합니다.

    indicators_dict:
        특정 코인의 여러 지표를 저장하는 딕셔너리
        구조: {코인명: [T-2 종가, T-1 종가, T-2 거래량, T-1 거래량,
                        T-2 20 이동평균, T-1 20 이동평균,
                        T-2 100 VWMA, T-1 100 VWMA, 현재가]}
        업데이트 주기 : 매 분

    target_dict:
        거래 대상이 되는 코인과 현재가를 저장하는 딕셔너리
        구조: {코인명: 현재가}
        * target_dict 현재가도 1초마다 업데이트를 진행하면, 요청 수 초과 우려가 있음.
        trading_dict에서 거래로 넘어가는 도중 trading_dict가 업데이트 됨.
        따라서 현재가를 따로 업데이트 하지는 않고 코인 정보만 업데이트.

    trading_dict:
        target_dict에서 랜덤하게 선택된 최대 5개의 코인을 저장하는 딕셔너리
        구조: {코인명: 현재가}
        코인 업데이트 주기 : 3초
        현재가 업데이트 주기 : 1초

    wallet_dict:
        매수한 코인의 내역을 기록하는 딕셔너리
        구조: {코인명: [매수 평균 가격, 매수 수량]}

    ACCESS_KEY, SECRET_KEY: 환경 변수로 저장된 키 값
    """

    # 웹소켓 연결
    await public_websocket_connect()

    # 별도의 Task로 작업을 동시에 실행

    # indicators_dict, target_dict 업데이트 - 매 분
    task_indicators = asyncio.create_task(update_indicators_periodically
                                    (indicators_dict, target_dict, target_lock))

    # target_dict 5개 랜덤 -> trading_dict - 3초
    task_transactions = asyncio.create_task(update_trading_dict
                                    (trading_dict, target_dict, trading_lock, target_lock))

    # trading_dict 가격 업데이트 - 1초
    task_prices = asyncio.create_task(update_prices
                                      (trading_dict, trading_lock))

    # 거래 시작
    task_trades = asyncio.create_task(execute_trades
                                      (ACCESS_KEY, SECRET_KEY, trading_dict, active_trades, indicators_dict
                                       , wallet_dict, trading_lock, active_lock))

    # wallet_dict 업데이트 - 1 초
    task_wallet = asyncio.create_task(update_wallet_realtime
                                      (ACCESS_KEY, SECRET_KEY, wallet_dict))

    # 모든 Task를 동시에 실행 (각 Task는 무한 루프로 동작)
    await asyncio.gather(task_indicators, task_prices, task_transactions, task_trades, task_wallet)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program terminated by user")