import requests
import tulipy as ti
import numpy as np
import time
import threading

def get_all_krw_coins():
    """
    업비트 API를 통해 KRW 마켓의 모든 코인 이름을 가져옴.
    """
    url = "https://api.upbit.com/v1/market/all"
    response = requests.get(url)
    response.raise_for_status()
    markets = response.json()

    # KRW 마켓 코인 필터링
    krw_coins = [market["market"] for market in markets if market["market"].startswith("KRW-")]
    return krw_coins

def get_minute_candles(coin, count=102):
    """
    업비트 API를 통해 지정된 코인의 분봉 데이터를 가져옴.
    429 오류가 발생하면, 정상 응답이 올 때까지 계속 재요청함.

    :param coin: 코인 이름 (예: KRW-BTC)
    :param count: 가져올 캔들 개수
    """
    url = "https://api.upbit.com/v1/candles/minutes/1"
    params = {"market": coin, "count": count}

    while True:
        try:
            response = requests.get(url, params=params)
            # 429 오류가 발생하면 재시도
            sec=0.1
            if response.status_code == 429:
                # print(f"429 오류 발생 ({coin}). {sec}초 후 재시도합니다.")
                time.sleep(sec)
                continue

            response.raise_for_status()  # 429가 아니라면 오류 발생 시 예외 처리
            candles = response.json()

            # 시간 역순으로 반환되므로 뒤집어서 정렬
            candles.reverse()
            return candles

        except requests.exceptions.HTTPError as http_err:
            # 만약 429 오류 외 다른 HTTP 오류가 발생해도 재시도하도록 함
            if response.status_code == 429:
                print(f"HTTPError 429 발생 ({coin}). {sec}초 후 재시도합니다.")
            else:
                print(f"HTTPError 발생 ({coin}): {http_err}. {sec}초 후 재시도합니다.")
            time.sleep(sec)
        except Exception as e:
            print(f"기타 오류 발생 ({coin}): {e}. {sec}초 후 재시도합니다.")
            time.sleep(sec)

def calculate_indicators_for_coins(coins, indicators_dict):
    """
    주어진 코인 리스트에 대해 지표를 계산하고 dictionary에 저장.
    """
    for coin in coins:
        try:
            # 분봉 데이터 가져오기
            candles = get_minute_candles(coin)

            # 종가(close)와 거래량(volume) 추출 - 최근 시간대가 배열 맨 앞 위치
            close_prices = [candle["trade_price"] for candle in candles]
            volumes = [candle["candle_acc_trade_volume"] for candle in candles]

            # 오류 발생시 저장하지 않음
            if close_prices is None or volumes is None or len(close_prices) != 102:
                print(f"{coin} 응답 오류, indicators_dict 에 저장하지 않음.")
                continue

            # NumPy 배열로 변환
            close_prices = np.array(close_prices, dtype=float)
            volumes = np.array(volumes, dtype=float)

            # 20분 SMA 계산
            if len(close_prices) >= 20:
                ma_20 = ti.sma(close_prices, period=20)
                t_1_ma_20 = ma_20[-2]
                t_2_ma_20 = ma_20[-3]
            else:
                t_1_ma_20, t_2_ma_20 = None, None

            # 100분 VWMA 계산
            if len(close_prices) >= 100:
                vwma_100 = ti.vwma(close_prices, volumes, period=100)
                t_1_vwma_100 = vwma_100[-2]
                t_2_vwma_100 = vwma_100[-3]
            else:
                t_1_vwma_100, t_2_vwma_100 = None, None
            # 현재가
            t_close = close_prices[-1]
            # T-1의 종가
            t_1_close = close_prices[-2] if len(close_prices) > 1 else None
            # T-2의 종가
            t_2_close = close_prices[-3] if len(close_prices) > 1 else None
            # T-1의 누적 거래량
            t_1_volume = volumes[-2] if len(volumes) > 1 else None
            # T-2의 누적 거래량
            t_2_volume = volumes[-3] if len(volumes) > 1 else None
            # 결과 저장
            # 구조: {코인명: [T-2 종가, T-1 종가, T-2 거래량, T-1 거래량, T-2 20 이동평균, T-1 20 이동평균, T-2 100 VWMA, T-1 100 VWMA, 현재가]}
            indicators_dict[coin] = [t_2_close, t_1_close, t_2_volume, t_1_volume,
                                     t_2_ma_20, t_1_ma_20, t_2_vwma_100, t_1_vwma_100, t_close]

            # API 요청 제한 고려 (업비트는 초당 요청 수 제한 있음)
            # time.sleep(0.5)

        except Exception as e:
            print(f"Error processing {coin}: {e}")

def calculate_indicators(indicators_dict, num_threads):
    """
    모든 KRW 코인에 대해 지표를 멀티 스레드를 사용해 계산하고 dictionary에 저장.
    :param indicators_dict: 결과를 저장할 dictionary
    :param num_threads: 사용할 스레드의 개수
    """
    krw_coins = get_all_krw_coins()

    # 스레드 리스트
    threads = []

    # 코인을 나누어서 할당
    if num_threads > len(krw_coins):
        # 스레드 수가 코인 수보다 많으면, 스레드 수를 코인 수로 제한
        num_threads = len(krw_coins)

    chunk_size = len(krw_coins) // num_threads

    for i in range(num_threads):
        start_index = i * chunk_size
        if i == num_threads - 1:
            # 마지막 스레드는 나머지 코인을 모두 할당
            end_index = len(krw_coins)
        else:
            end_index = (i + 1) * chunk_size

        # 스레드에 할당할 코인 목록
        coins_slice = krw_coins[start_index:end_index]

        t = threading.Thread(target=calculate_indicators_for_coins, args=(coins_slice, indicators_dict))
        threads.append(t)
        t.start()

    # 스레드가 모두 종료될 때까지 대기
    for t in threads:
        t.join()