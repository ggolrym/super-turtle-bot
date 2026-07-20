import os
import yfinance as yf
import pandas as pd  # 엑셀/CSV 파일을 읽어주는 아주 강력한 마법 도구야!
from google import genai
import requests
import time
from datetime import datetime

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
    print("🚨 금고에 비밀번호가 없어요!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

buy_signals = []
sell_signals = []

print("📚 비밀 출석부를 펼칩니다...")

# ==========================================
# 🌟 핵심 포인트: 파일에서 코스피 900개 명단 읽어오기!
# ==========================================
try:
    # 깃허브 방에 올려둔 kospi_list.csv 파일을 읽어와! (숫자 0이 안 지워지게 dtype=str로 설정)
    korea_df = pd.read_csv('kospi_list.csv', dtype={'Code': str})
    
    # 읽어온 표를 파이썬 리스트로 싹 변환하기
    korea_tickers = korea_df['Code'].tolist()
    korea_names = korea_df['Name'].tolist()
    
    # 딕셔너리로 만들기 (티커 뒤에 '.KS'를 붙여야 야후 파이낸스가 알아들어!)
    korea_stocks = {}
    for i in range(len(korea_tickers)):
        ticker = korea_tickers[i] + '.KS'
        name = korea_names[i]
        korea_stocks[ticker] = name
        
    print(f"🇰🇷 코스피 주식 {len(korea_stocks)}개 준비 완료!")
except Exception as e:
    print("🚨 앗! kospi_list.csv 파일이 깃허브에 없거나 읽을 수 없어요. 파일을 꼭 올려주세요!")
    korea_stocks = {} # 파일이 없으면 일단 빈칸으로 둠

# 미국 대장주 10개 (원하면 더 추가 가능!)
us_stocks = {
    'AAPL': '애플', 'MSFT': '마이크로소프트', 'NVDA': '엔비디아',
    'GOOGL': '구글', 'AMZN': '아마존', 'META': '메타', 
    'TSLA': '테슬라', 'AMD': 'AMD', 'NFLX': '넷플릭스', 'INTC': '인텔'
}

# 한국 900개 + 미국 10개를 하나의 거대한 바구니로 합치기!
all_stocks = {**korea_stocks, **us_stocks}

print(f"🤖 총 {len(all_stocks)}개의 글로벌 주식 감시를 시작합니다!\n")

# 900개가 넘으니까 야후 파이낸스에서 데이터를 가져올 때 좀 더 안전하게 처리할게!
for ticker, name in all_stocks.items():
    try:
        stock_data = yf.download(ticker, period='1y', progress=False)
        
        if len(stock_data) >= 200:
            recent_20_high = stock_data['High'].iloc[-20:].max().item()
            ma_200 = stock_data['Close'].rolling(window=200).mean().iloc[-1].item()
            today_volume = stock_data['Volume'].iloc[-1].item()
            recent_10_low = stock_data['Low'].iloc[-10:].min().item()
            current_price = stock_data['Close'].iloc[-1].item()
            
            # 🟢 [매수 조건] 20일선 + 200일선 + 거래량 10만 주! 
            # (한국 코스피 전체를 감시하니까 거래량 기준을 50만에서 10만으로 살짝 낮췄어)
            if (current_price >= recent_20_high) and (current_price > ma_200) and (today_volume >= 100000):
                buy_signals.append(f"{name}")
                print(f"🚀 [발견!] {name}")
                
            elif current_price <= recent_10_low:
                sell_signals.append(f"{name}")
                
    except Exception as e:
        pass # 에러 나면 조용히 패스
        
    time.sleep(0.5) # 경찰 피해서 0.5초씩 휴식 (900개니까 총 7~10분 정도 걸려!)

print(f"\n✅ 글로벌 검사 끝! 살 주식 {len(buy_signals)}개 발견.")

if len(buy_signals) > 0 or len(sell_signals) > 0:
    prompt = f"""
    너는 12살도 이해하기 쉽게 설명해주는 최고의 퀀트 투자 비서야.
    오늘 한국 코스피 900개와 미국 대장주를 모두 싹쓸이 검사했어.
    
    - 🟢 매수 추천 (200일선 뚫고 폭발!): {buy_signals if buy_signals else '없음'}
    - 🔴 매도 경고 (10일 최저가 붕괴): {sell_signals if sell_signals else '없음'}
    
    이 결과를 바탕으로 디스코드 알림 메시지를 작성해줘. 이모티콘 듬뿍 넣어서!
    """
    
        response = client.models.generate_content(
        model='gemini-2.0-flash',  # 👈 여기를 2.0으로 바꿨어!
        contents=prompt,
    )

    
    message_data = {"content": f"🌍 **코스피 전체 장악! 터틀 로봇** 🌍\n{response.text}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
else:
    print("오늘은 살만한 주식이 없네요! 😴")
