import threading

def process_coin(coin, values, target_dict, lock):
    """
    개별 코인에 대해 조건을 확인하여, 조건에 부합하면 target_dict에 추가하는 함수.

    indicators 리스트의 구조:
      [T-2 종가, T-1 종가, T-2 거래량, T-1 거래량,
       T-2 20 이동평균, T-1 20 이동평균, T-2 100 VWMA, T-1 100 VWMA, 현재가]

    조건:
      1. T-2 20 이동평균과 T-2 100 VWMA가 T-2 종가보다 낮아야 함.
      2. T-1 20 이동평균과 T-1 100 VWMA가 T-1 종가보다 낮아야 함.
      3. T-1 거래량이 T-2 거래량의 3배보다 커야 함.
      4. 현재가가 T-1 종가보다 높아야 함.
      5. T-1 거래량 x T-1 종가 > 30_000_000
    """
    # 각 값 추출
    t2_close    = values[0]
    t1_close    = values[1]
    t2_volume   = values[2]
    t1_volume   = values[3]
    t2_ma20     = values[4]
    t1_ma20     = values[5]
    t2_vwma100  = values[6]
    t1_vwma100  = values[7]
    current_price = values[8]

    # 조건 계산
    with lock:
        target_dict[coin] = current_price

def classify_targets(indicators_dict, target_dict):
    """
    indicators_dict에 저장된 모든 코인에 대해 조건을 평가하여, 조건에 부합하는 코인을
    쓰레드를 병렬로 처리한 후 target_dict에 (코인명:현재가) 형태로 저장합니다.

    :parameter
      - indicators_dict: dict
            구조: {코인명: [T-2 종가, T-1 종가, T-2 거래량, T-1 거래량,
                           T-2 20 이동평균, T-1 20 이동평균, T-2 100 VWMA, T-1 100 VWMA, 현재가]}
      - target_dict: dict
            구조: {코인명: 현재가}
    """
    lock = threading.Lock()
    threads = []

    for coin, values in indicators_dict.items():
        thread = threading.Thread(target=process_coin, args=(coin, values, target_dict, lock))
        threads.append(thread)
        thread.start()

    # 모든 쓰레드가 종료될 때까지 대기
    for thread in threads:
        thread.join()