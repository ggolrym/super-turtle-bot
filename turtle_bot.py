# ==========================================
# 🐢 AI 터틀 트레이딩 (1,400개 풀스케일 + ATR 탑재)
# ==========================================
import os
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import requests
from google import genai
import time
from datetime import datetime
import random

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
    print("🚨 금고에 API 키나 웹훅 URL이 없습니다!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

buy_signals = []
sell_signals = []

print("🌊 1,400개의 거대한 글로벌 주식 바다로 출항합니다...")

# ==========================================
# 1. 명단 수집 (코스피 전체 + S&P 500 전체)
# ==========================================
try:
    # 🇰🇷 한국: 깃허브에 있는 kospi_list.csv에서 '전체' 가져오기 (가위질 제거!)
    kr_df = pd.read_csv('kospi_list.csv', dtype={'Symbol': str})
    korea_stocks = {}
    for index, row in kr_df.iterrows():
        korea_stocks[row['Symbol'] + '.KS'] = row['Name']
    print(f"🇰🇷 코스피 전체 {len(korea_stocks)}개 준비 완료!")
        
    # 🇺🇸 미국: S&P 500 '전체' 가져오기 (가위질 제거!)
    us_df = fdr.StockListing('SP500')
    us_stocks = {}
    for index, row in us_df.iterrows():
        us_stocks[row['Symbol']] = row['Name']
    print(f"🇺🇸 미국 S&P500 전체 {len(us_stocks)}개 준비 완료!")
        
except Exception as e:
    print(f"🚨 명단 수집 실패! (에러: {e})")
    print("💡 kospi_list.csv 파일이 깃허브에 있는지 꼭 확인해주세요!")
    exit()

all_stocks = {**korea_stocks, **us_stocks}
print(f"\n🤖 총 {len(all_stocks)}개 대장주 정밀 검사를 시작합니다! (약 15분 소요 예상)\n")

# ==========================================
# 2. 1,400개 주식 컨베이어 벨트 (ATR 분석)
# ==========================================
for ticker, name in all_stocks.items():
    try:
        stock_data = yf.download(ticker, period='1y', progress=False)
        
        if len(stock_data) >= 200:
            recent_20_high = stock_data['High'].iloc[-20:].max().item()
            ma_200 = stock_data['Close'].rolling(window=200).mean().iloc[-1].item()
            today_volume = stock_data['Volume'].iloc[-1].item()
            recent_10_low = stock_data['Low'].iloc[-10:].min().item()
            current_price = stock_data['Close'].iloc[-1].item()
            
            # 터틀 트레이딩 N값(ATR) 계산
            high_low = stock_data['High'] - stock_data['Low']
            high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
            low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=20).mean()
            current_n = atr.iloc[-1].item()
            
            # 🟢 [매수 조건] 20일선 + 200일선 + 거래량 100만 주
            if (current_price >= recent_20_high) and (current_price > ma_200) and (today_volume >= 1000000):
                buy_signals.append(f"{name} (현재가: {current_price:.2f}, N값: {current_n:.2f})")
                print(f"🚀 [매수 신호] {name}")
                
            # 🔴 [매도 조건] 10일 최저가 붕괴
            elif current_price <= recent_10_low:
                sell_signals.append(f"{name} (현재가: {current_price:.2f})")
                
    except Exception as e:
        pass 
        
    # 🌟 안전장치 1: 야후 파이낸스 경찰 피하기 (1400개니까 0.6초로 살짝 늘림)
    time.sleep(0.6) 

print(f"\n✅ 1,400개 검사 끝! 매수 신호 {len(buy_signals)}개 발견.")

# ==========================================
# 3. 브리핑 작성 및 전송 (과부하 방지 컷오프)
# ==========================================
if len(buy_signals) > 0 or len(sell_signals) > 0:
    
    # 🌟 안전장치 2: 디스코드 글자 수 초과 방지 (신호가 너무 많으면 상위 20개만 자르기)
    if len(buy_signals) > 20:
        buy_signals = buy_signals[:20] + ["... (너무 많아서 20개까지만 표시)"]
    if len(sell_signals) > 20:
        sell_signals = sell_signals[:20] + ["... (너무 많아서 20개까지만 표시)"]

    prompt = f"""
    너는 데이터를 기반으로 냉철하게 분석하는 전문 퀀트 투자 비서야.
    오늘 한국 코스피 전체, 미국 S&P500 전체 (총 1,400개)를 오리지널 터틀 트레이딩 기법으로 샅샅이 뒤졌어.
    
    - 🟢 시스템1 매수 신호 (20일 고점 돌파 + 200일선 지지): {buy_signals if buy_signals else '없음'}
    - 🔴 매도 및 손절 신호 (10일 저점 이탈): {sell_signals if sell_signals else '없음'}
    
    이 결과를 바탕으로 디스코드 브리핑 메시지를 아주 프로페셔널하게 작성해줘. 
    """
    
    # 🌟 안전장치 3: 1400개를 처리하느라 지친 깃허브를 위해 제미나이 호출 3회 재시도 기능 추가
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash', 
                contents=prompt,
            )
            break # 성공하면 멈춤
        except Exception as e:
            print(f"제미나이 호출 실패... {attempt+1}차 재시도 중 ({e})")
            time.sleep(5)
    
    message_data = {"content": f"🌊 **글로벌 풀스케일 퀀트 리포트 (1,400 종목)** 🌊\n{response.text}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
    print("디스코드 알림 발사 성공! 👏")
    
else:
    print("오늘은 매수/매도 신호가 발생하지 않았습니다.")
    message_data = {"content": "🌊 **글로벌 풀스케일 퀀트 리포트 (1,400 종목)** 🌊\n오늘 무려 1,400개의 기업을 샅샅이 뒤졌지만, 터틀 시스템1에 완벽히 부합하는 타점이 발생하지 않았습니다. 총알을 아끼고 폭풍을 기다리십시오."}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
