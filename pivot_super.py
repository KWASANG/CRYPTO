# -*- coding: utf-8 -*-

import pyupbit
import pandas as pd
import talib as ta
import time
import numpy as np
import requests
import datetime
import yaml
from decimal import Decimal

with open('config.yaml', encoding='UTF-8') as f:
    _cfg = yaml.load(f, Loader=yaml.FullLoader)

# Set API keys
access_key = _cfg['access_key']
secret_key = _cfg['secret_key']
upbit = pyupbit.Upbit(access_key, secret_key)
DISCORD_WEBHOOK_URL = _cfg['DISCORD_WEBHOOK_URL']

# Set trading parameters
tickers = pyupbit.get_tickers("KRW")
interval_daily = 'day'
interval_weekly = 'week'
min_order_amount = 6000
max_order_amount = 50000
trailing_start_percentage = 0.04
trailing_stop_percentage = 0.027 
stop_loss_percentage = 0.024

def send_message(msg):

    """디스코드 메세지 전송"""
    now = datetime.datetime.now()
    message = {"content": f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] {str(msg)}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message)
    print(message)
    

def calculate_pivot_supertrend(df):
    high = df['high']
    low = df['low']
    close = df['close']

    pivot_point = (high + low + close) / 3
    ATR = ta.ATR(high, low, close, timeperiod=14)

    supertrend = pd.Series(np.zeros(len(df)), index=df.index)
    supertrend_prev = pd.Series(np.zeros(len(df)), index=df.index)
    for i in range(1, len(df)):
        upper_band = (high[i] + low[i]) / 2 + (2 * ATR[i])
        lower_band = (high[i] + low[i]) / 2 - (2 * ATR[i])

        if close[i] > supertrend_prev[i - 1]:
            supertrend[i] = upper_band
        elif close[i] < supertrend_prev[i - 1]:
            supertrend[i] = lower_band
        else:
            supertrend[i] = supertrend_prev[i - 1]

        supertrend_prev[i] = supertrend[i]

    return supertrend


# Get owned stocks
def get_owned_stocks():
    owned_stocks = []
    balances = upbit.get_balances()
    for balance in balances:
        if balance['currency'] != 'KRW':
            owned_stocks.append('KRW-' + balance['currency'])
    return owned_stocks

def stock_selection(ticker):
    # 피벗 포인트 슈퍼트렌드 계산
    def calculate_pivot_supertrend(df):
        high = df['high']
        low = df['low']
        close = df['close']

        pivot_point = (high + low + close) / 3
        ATR = ta.ATR(high, low, close, timeperiod=14)

        supertrend = pd.Series(np.zeros(len(df)), index=df.index)
        supertrend_prev = pd.Series(np.zeros(len(df)), index=df.index)
        for i in range(1, len(df)):
            upper_band = (high[i] + low[i]) / 2 + (2 * ATR[i])
            lower_band = (high[i] + low[i]) / 2 - (2 * ATR[i])

            if close[i] > supertrend_prev[i - 1]:
                supertrend[i] = upper_band
            elif close[i] < supertrend_prev[i - 1]:
                supertrend[i] = lower_band
            else:
                supertrend[i] = supertrend_prev[i - 1]

            supertrend_prev[i] = supertrend[i]

        return supertrend
    
    # Get daily, weekly, 3-min, and 5-min candlestick data
    daily_df = pyupbit.get_ohlcv(ticker, interval=interval_daily)
    weekly_df = pyupbit.get_ohlcv(ticker, interval=interval_weekly)
    three_min_df = pyupbit.get_ohlcv(ticker, interval="minute3")
    five_min_df = pyupbit.get_ohlcv(ticker, interval="minute5")
    daily_supertrend = calculate_pivot_supertrend(daily_df)
    
    if daily_df is None or weekly_df is None or three_min_df is None or five_min_df is None:
        return False
    
    # 추가 조건 1: 거래량 - 일봉 0봉전 기준, 이전 5일 평균 거래량보다 200% 이상 증가한 종목
    avg_volume_5d = daily_df.iloc[-6:-1]['volume'].mean()
    if daily_df.iloc[-1]['volume'] < avg_volume_5d * 2:
        return False
    
    # 추가 조건 2: RSI - RSI 지표를 이용하여 과매수 상태가 아닌 종목 (RSI 값이 70 미만)
    rsi = ta.RSI(daily_df['close'], timeperiod=14)
    if rsi.iloc[-1] >= 70:
        return False
    
    # 추가 조건 3: 3분 주기 0봉전 기준 거래가가 최근 5봉 고가의 평균값 보다 15% 초과하는 종목
    # avg_high_5candles = three_min_df.iloc[-6:-1]['high'].mean()
    # if three_min_df.iloc[-1]['close'] <= avg_high_5candles * 1.15:
      #   return False

    # 추가 조건 4: 5분 주기 1봉전 저가와 0봉전 저가가 5일선 위에 있는 종목
    # five_min_ma5 = five_min_df['close'].rolling(window=5).mean()
    # if five_min_df.iloc[-2]['low'] < five_min_ma5.iloc[-2] or five_min_df.iloc[-1]['low'] < five_min_ma5.iloc[-1]:
     #    return False
    
    # 추가 조건 5: 이평선 교차 - 5일 이평선이 20일 이평선을 상향 돌파한 종목
    # ma5 = daily_df['close'].rolling(window=5).mean()
    # ma20 = daily_df['close'].rolling(window=20).mean()
    # if ma5.iloc[-1] <= ma20.iloc[-1] or ma5.iloc[-2] > ma20.iloc[-2]:
    #     return False
    
    # 피벗 포인트 슈퍼트렌드 매수 조건 확인
    if not (daily_df['close'][-1] > daily_supertrend[-1] and daily_df['close'][-2] <= daily_supertrend[-2]):
        return False



    return True

def buy_and_sell(ticker):
    # Buy the selected stock at the current price
    current_price = pyupbit.get_current_price(ticker)
    if current_price is None:
        send_message("Failed to get current price for {}".format(ticker))
        # print(f"Failed to get current price for {ticker}")
        return
    buy_amount = min(max_order_amount, upbit.get_balance("KRW"))
    if buy_amount < min_order_amount:
        return
    upbit.buy_market_order(ticker, buy_amount)
    send_message("Buy {} at {} KRW, Amount: {}".format(ticker, current_price, buy_amount))
    # print(f"Buy {ticker} at {current_price} KRW, Amount: {buy_amount}")

    # Monitor and sell the stock
    bought_price = current_price
    trailing_high_price = bought_price

#    send_message("업비트 자동매매 프로그램 시작")
    while True:
        current_price = pyupbit.get_current_price(ticker)
        if current_price is None:
            send_message("Failed to get current price for {}".format(ticker))
            # print(f"Failed to get current price for {ticker}")
            continue
        '''
        # Update trailing high price
        if current_price >= bought_price * (1 + trailing_start_percentage):
            trailing_high_price = max(trailing_high_price, current_price)
        
        # Check if the stock should be sold due to trailing stop
        if trailing_high_price * (1 - trailing_stop_percentage) >= current_price:
            units = upbit.get_balance(ticker)
            upbit.sell_market_order(ticker, units)
            print("Sell {} at {} KRW, Trailing Stop".format(ticker, current_price))
            # print(f"Sell {ticker} at {current_price} KRW, Trailing Stop")
            break
        '''
        # Update pivot supertrend
        daily_df = pyupbit.get_ohlcv(ticker, interval=interval_daily)
        if daily_df is None:
            continue
        daily_supertrend = calculate_pivot_supertrend(daily_df)

        # Check if the stock should be sold due to pivot point supertrend
        if daily_supertrend[-1] > current_price:
            units = upbit.get_balance(ticker)
            upbit.sell_market_order(ticker, units)
            send_message("{}를 {} KRW에 피벗 포인트 슈퍼트렌드로 매도".format(ticker, current_price))
            break
        # Check if the stock should be sold due to stop loss
        if bought_price * (1 - stop_loss_percentage) >= current_price:
            units = upbit.get_balance(ticker)
            upbit.sell_market_order(ticker, units)
            send_message("Sell {} at {} KRW, Stop Loss".format(ticker, current_price))
            # print(f"Sell {ticker} at {current_price} KRW, Stop Loss")
            break

        # Wait for 10 seconds before checking again
        time.sleep(10)

import threading

def asset_summary():
    threading.Timer(3600, asset_summary).start()

    krw_balance = Decimal(upbit.get_balance("KRW"))
    balances = upbit.get_balances()
    total_assets = krw_balance

    message = "보유 종목:\n"

    for balance in balances:
        if balance['currency'] != 'KRW':
            ticker = 'KRW-' + balance['currency']
            
            if ticker not in tickers:
                continue

            amount = Decimal(balance['balance'])
            avg_buy_price = Decimal(balance['avg_buy_price'])

            # 주문 내역에서 미체결 매도 주문 수량 가져오기
            orders = upbit.get_order(ticker, state="wait")
            for order in orders:
                if order['side'] == 'ask':
                    amount += Decimal(order['remaining_volume'])

            total_value = avg_buy_price * amount
            total_assets += total_value

            message += f"{ticker}: 수량 {amount}, 총액(KRW) {total_value:.0f}\n"

    message += f"원화 보유액: {krw_balance:.0f} KRW\n"
    message += f"자산 총액: {total_assets:.0f} KRW"

    send_message(message)

asset_summary()

send_message("업비트 자동매매 프로그램 시작")

while True:
    
    owned_stocks = get_owned_stocks()

    for ticker in tickers:
        try:
            # Check if the stock is already owned
            if ticker in owned_stocks:
                continue

            if stock_selection(ticker):
                buy_and_sell(ticker)
            time.sleep(0.05)

        except Exception as e:
            send_message("Error trading {}: {}".format(ticker, e))
            # print(f"Error trading {ticker}: {e}")

       

