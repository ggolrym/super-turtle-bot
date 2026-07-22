# ==========================================
# 🐢 AI 터틀 트레이딩 (실시간 웹 크롤링 자동화 버전)
# ==========================================
import os
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup # 인터넷 페이지를 읽는 마법의 돋보기!
from google import genai
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

print("🔍 로봇이 인터넷을 돌아다니며 실시간 1등~50등 명단을 수집합니다...")

# ==========================================
# 🇰🇷 1. 네이버 증권에서 코스피 실시간 Top 50 긁어오기
# ==========================================
korea_stocks = {}
try:
    print("🇰🇷 네이버 증권 잠입 중...")
    # 네이버 시가총액(1등~50등) 페이지 주소
    url = "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0"
    res = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 표 안에서 주식 이름과 6자리 코드번호(href) 빼내기
    for a_tag in soup.select('table.type_2 tbody tr td a'):
        if 'code=' in a_tag.get('href', ''):
            name = a_tag.text.strip()
            code = a_tag['href'].split('code=')[-1]
            if code.isdigit():
                korea_stocks[f"{code}.KS"] = name
            
            # 딱 50개가 모이면 그만!
            if len(korea_stocks) >= 50:
                break
    print(f"✅ 코스피 실시간 Top 50 수집 완료! (예: {list(korea_stocks.values())[0]})")
except Exception as e:
    print(f"🚨 한국 명단 수집 실패: {e}")

# ==========================================
# 🇺🇸 2. 위키백과에서 미국 S&P 100 대장주 실시간 긁어오기
# ==========================================
us_stocks = {}
try:
    print("🇺🇸 위키백과 잠입 중...")
    url = 'https://en.wikipedia.org/wiki/S%26P_100'
    tables = pd.read_html(url)
    
    # 위키백과 페이지에 있는 여러 표 중에서 'Symbol(기호)'이 있는 진짜 주식 표 찾기
    for table in tables:
        if 'Symbol' in table.columns:
            # 앞에서부터 50개만 딱 자르기
            df = table.head(50)
            for _, row in df.iterrows():
                # 야후 파이낸스 검색을 위해 기호의 점(.)을 짝대기(-)로 바꿔줌 (예: BRK.B -> BRK-B)
                symbol = str(row['Symbol']).replace('.', '-')
                us_stocks[symbol] = row['Name']
            break
    print(f"✅ 미국 대장주 Top 50 수집 완료! (예: {list(us_stocks.values())[0]})")
except Exception as e:
    print(f"🚨 미국 명단 수집 실패: {e}")

# ------------------------------------------
# 한국 50개 + 미국 50개 = 총 100개 합치기!
all_stocks = {**korea_stocks, **us_stocks}
print(f"\n🤖 실시간 수집된 총 {len(all_stocks)}개 대장주 감시를 시작합니다!\n")

# ==========================================
# 3. 100개 주식 컨베이어 벨트 시작!
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
            
            # 🟢 [매수 조건] 20일선 + 200일선 + 거래량 100만 주!
            if (current_price >= recent_20_high) and (current_price > ma_200) and (today_volume >= 1000000):
                buy_signals.append(f"{name}")
                print(f"🚀 [발견!] {name}")
                
            # 🔴 [매도 조건] 10일 최저가 붕괴
            elif current_price <= recent_10_low:
                sell_signals.append(f"{name}")
                
    except Exception as e:
        pass 
        
    time.sleep(0.5) 

print(f"\n✅ 실시간 100개 검사 끝! 살 주식 {len(buy_signals)}개 발견.")

# ==========================================
# 4. 제미나이 보고서 작성 및 디스코드 전송
# ==========================================
if len(buy_signals) > 0 or len(sell_signals) > 0:
    prompt = f"""
    너는 12살도 이해하기 쉽게 설명해주는 최고의 퀀트 투자 비서야.
    방금 인터넷에서 '실시간'으로 수집한 한국 코스피 Top 50, 미국 대장주 Top 50을 검사했어.
    
    - 🟢 매수 추천 (200일선 뚫고 폭발하는 우량주!): {buy_signals if buy_signals else '없음'}
    - 🔴 매도 경고 (10일 최저가 깨져서 도망쳐야 할 주식): {sell_signals if sell_signals else '없음'}
    
    이 결과를 바탕으로 디스코드 알림 메시지를 작성해줘. 이모티콘 듬뿍 넣어서!
    """
    
    response = client.models.generate_content(
        model='gemini-1.5-flash', 
        contents=prompt,
    )
    
    message_data = {"content": f"📡 **실시간 크롤링 한/미 Top 100 브리핑** 📡\n{response.text}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
    print("디스코드 알림 발사 성공! 👏")
    
else:
    print("오늘은 살만한 주식이 없네요! 😴")
    message_data = {"content": "📡 **실시간 크롤링 한/미 Top 100 브리핑** 📡\n주인님! 오늘 네이버 증권과 위키백과를 해킹(?)해서 실시간 100대 기업을 검사했지만 깐깐한 조건에 맞는 주식이 없습니다! 현금 쥐고 푹 쉬세요! 😴"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
