# ==========================================
# 🐢 AI 터틀 트레이딩 (한미 대장주 150 압축 버전)
# ==========================================
import os
import yfinance as yf
import FinanceDataReader as fdr
from google import genai
import requests
import time
from datetime import datetime

# 1. 금고에서 비밀번호 꺼내기
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
    print("🚨 금고에 비밀번호가 없어요!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

buy_signals = []
sell_signals = []

print("📚 한국과 미국의 진짜 1등 기업들만 불러옵니다...")

# ==========================================
# 🌟 변경된 부분: 인터넷에서 상위 150개 명단만 긁어오기!
# ==========================================
try:
    # 한국: 시가총액 상위 50개 (KOSPI 50) 가져오기!
    print("🇰🇷 코스피 Top 50 명단 가져오는 중...")
    kr_df = fdr.StockListing('KOSPI50')
    korea_stocks = {}
    for index, row in kr_df.iterrows():
        # 한국 주식은 티커 뒤에 .KS를 붙여야 야후가 알아먹어요
        korea_stocks[row['Symbol'] + '.KS'] = row['Name']
        
    # 미국: 나스닥 상위 100개 (NASDAQ 100) 가져오기!
    print("🇺🇸 나스닥 Top 100 명단 가져오는 중...")
    us_df = fdr.StockListing('NASDAQ100')
    us_stocks = {}
    for index, row in us_df.iterrows():
        us_stocks[row['Symbol']] = row['Name']
        
except Exception as e:
    print(f"🚨 명단 가져오기 실패! (에러: {e})")
    exit() # 명단이 없으면 그냥 로봇을 재웁니다.

# 한국 50 + 미국 100 합치기 (총 150개!)
all_stocks = {**korea_stocks, **us_stocks}

print(f"🤖 엄선된 글로벌 대장주 {len(all_stocks)}개 감시를 시작합니다!\n")

# ==========================================
# 3. 150개 주식 컨베이어 벨트 시작!
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
            
            # 🟢 [매수 조건] 20일선 돌파 + 200일선 돌파 + 거래량 폭발!
            # 대장주들이니까 거래량 기준을 100만 주로 깐깐하게 잡았어!
            if (current_price >= recent_20_high) and (current_price > ma_200) and (today_volume >= 1000000):
                buy_signals.append(f"{name}")
                print(f"🚀 [발견!] {name}")
                
            # 🔴 [매도 조건] 10일 최저가 붕괴
            elif current_price <= recent_10_low:
                sell_signals.append(f"{name}")
                
    except Exception as e:
        pass # 에러 나면 조용히 패스
        
    time.sleep(0.5) # 150개니까 금방 끝나요!

print(f"\n✅ 150개 검사 끝! 살 주식 {len(buy_signals)}개 발견.")

# ==========================================
# 4. 제미나이 보고서 작성 및 디스코드 전송
# ==========================================
if len(buy_signals) > 0 or len(sell_signals) > 0:
    prompt = f"""
    너는 12살도 이해하기 쉽게 설명해주는 최고의 퀀트 투자 비서야.
    오늘 한국 코스피 Top 50, 미국 나스닥 Top 100 대장주만 엄선해서 검사했어.
    
    - 🟢 매수 추천 (200일선 뚫고 폭발하는 초특급 우량주!): {buy_signals if buy_signals else '없음'}
    - 🔴 매도 경고 (10일 최저가 깨져서 도망쳐야 할 주식): {sell_signals if sell_signals else '없음'}
    
    이 결과를 바탕으로 디스코드 알림 메시지를 작성해줘. 이모티콘 듬뿍 넣어서!
    """
    
    # 💥 리미트 에러 방지 팁! 여기서 무거운 2.0 대신 빠르고 가벼운 1.5를 쓰면 에러 확률이 훨씬 줄어들어.
    response = client.models.generate_content(
        model='gemini-1.5-flash', 
        contents=prompt,
    )
    
    message_data = {"content": f"💎 **한/미 Top 150 엄선 브리핑** 💎\n{response.text}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
    print("디스코드 알림 발사 성공! 👏")
    
else:
    print("오늘은 살만한 주식이 없네요! 😴")
    # 조건에 맞는 주식이 없어도 매일 생존 신고를 합니다.
    message_data = {"content": "💎 **한/미 Top 150 엄선 브리핑** 💎\n주인님! 오늘 한국과 미국의 1등 기업 150개를 전부 검사했지만, 깐깐한 조건에 완벽히 맞는 주식이 단 한 개도 없습니다. 무리해서 사지 말고 푹 쉬세요! 😴"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
