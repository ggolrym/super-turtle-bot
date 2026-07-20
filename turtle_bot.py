import os
import yfinance as yf
# fdr(파이낸스데이터리더) 대신 다른 방법으로 출석부를 가져올 거야!
import pandas as pd 
# 제미나이의 새로운 뇌 연결선(genai)으로 바꿨어!
from google import genai
import requests
import time
from datetime import datetime

# 1. 금고에서 비밀번호 꺼내오기
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
    print("🚨 금고에 비밀번호가 없어요!")
    exit()

# 2. 미국 나스닥(NASDAQ) 상위 주식들만 감시하도록 변경!
# 문지기를 피해서 가장 유명한 주식들의 이름표를 직접 준비했어.
stock_dict = {
    'AAPL': '애플', 'MSFT': '마이크로소프트', 'NVDA': '엔비디아',
    'GOOGL': '구글', 'AMZN': '아마존', 'META': '메타', 
    'TSLA': '테슬라', 'AMD': 'AMD', 'NFLX': '넷플릭스', 'INTC': '인텔'
}

print("🤖 슈퍼 터틀 로봇 가동 시작! (미국 주식 감시 중...)\n")

# 새로운 버전의 제미나이 뇌 켜기!
client = genai.Client(api_key=GEMINI_API_KEY)

buy_signals = []
sell_signals = []

# 3. 준비한 미국 주식들을 하나씩 검사하기
for ticker, name in stock_dict.items():
    try:
        # 미국 주식은 이름표(티커) 그대로 쓰면 돼!
        stock_data = yf.download(ticker, period='1y', progress=False)
        
        if len(stock_data) >= 200:
            recent_20_high = stock_data['High'].iloc[-20:].max().item()
            ma_200 = stock_data['Close'].rolling(window=200).mean().iloc[-1].item()
            today_volume = stock_data['Volume'].iloc[-1].item()
            recent_10_low = stock_data['Low'].iloc[-10:].min().item()
            current_price = stock_data['Close'].iloc[-1].item()
            
            # 🟢 [매수 조건] (미국 주식은 거래량이 엄청 많아서 10만 주는 항상 넘으니까, 더 깐깐하게 '100만 주'로 올렸어!)
            if (current_price >= recent_20_high) and (current_price > ma_200) and (today_volume >= 1000000):
                buy_signals.append(name)
                print(f"🚀 [발견!] {name}")
                
            # 🔴 [매도 조건] 10일 최저가 붕괴
            elif current_price <= recent_10_low:
                sell_signals.append(name)
                
    except Exception as e:
        print(f"[{name}] 데이터를 가져오지 못했어요. 패스!")
        
    time.sleep(1) # 미국 경찰 피해서 1초씩 넉넉히 쉬기!

# 4. 제미나이에게 보고서 쓰라고 시키기
if len(buy_signals) > 0 or len(sell_signals) > 0:
    prompt = f"""
    너는 12살도 이해하기 쉽게 설명해주는 최고의 주식 비서야.
    오늘 한국 시간으로 {datetime.now().strftime('%Y년 %m월 %d일')}이야.
    
    - 🟢 미국 주식 매수 추천 (200일선 뚫고 폭발하는 주식!): {buy_signals if buy_signals else '없음'}
    - 🔴 매도 경고 (10일 최저가 깨져서 도망쳐야 할 주식): {sell_signals if sell_signals else '없음'}
    
    이 결과를 바탕으로 디스코드 알림 메시지를 작성해줘. 이모티콘 듬뿍 넣어서!
    """
    
    # 새로운 제미나이에게 말 거는 방식이야!
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    # 5. 디스코드로 메시지 전송!
    message_data = {"content": f"🐢 **슈퍼 터틀 미국 주식 브리핑** 🐢\n{response.text}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
