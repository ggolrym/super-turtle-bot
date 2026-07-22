# ==========================================
# 🐢 AI 터틀 트레이딩 (ATR N값 탑재 + 실시간 수집 진화 버전)
# ==========================================
import os
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
from google import genai
import time
from datetime import datetime

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
    print("🚨 금고에 API 키나 웹훅 URL이 없습니다!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

buy_signals = []
sell_signals = []

print("🔍 한국과 미국의 상위 50개 대장주 명단을 수집합니다...")

# ==========================================
# 🇰🇷 1. 네이버 증권에서 코스피 실시간 Top 50 긁어오기
# ==========================================
korea_stocks = {}
try:
    print("🇰🇷 코스피 명단 수집 중...")
    url = "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0"
    res = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    
    for a_tag in soup.select('table.type_2 tbody tr td a'):
        if 'code=' in a_tag.get('href', ''):
            name = a_tag.text.strip()
            code = a_tag['href'].split('code=')[-1]
            if code.isdigit():
                korea_stocks[f"{code}.KS"] = name
            if len(korea_stocks) >= 50:
                break
    print("✅ 코스피 Top 50 수집 완료!")
except Exception as e:
    print(f"🚨 한국 명단 수집 실패: {e}")

# ==========================================
# 🇺🇸 2. FinanceDataReader로 미국 S&P 500 상위 50개 안전하게 가져오기
# (구글파이낸스/위키백과의 403 에러를 원천 차단하는 가장 견고한 방법)
# ==========================================
us_stocks = {}
try:
    print("🇺🇸 미국 S&P 대장주 명단 수집 중...")
    # 시가총액 순으로 정렬된 S&P 500 명단을 가져와 상위 50개만 추출
    sp500_df = fdr.StockListing('SP500').head(50)
    for _, row in sp500_df.iterrows():
        us_stocks[row['Symbol']] = row['Name']
    print("✅ 미국 Top 50 수집 완료!")
except Exception as e:
    print(f"🚨 미국 명단 수집 실패: {e}")

all_stocks = {**korea_stocks, **us_stocks}
print(f"\n🤖 총 {len(all_stocks)}개 대장주에 대한 정밀 ATR(N값) 분석을 시작합니다!\n")

# ==========================================
# 3. 100개 주식 컨베이어 벨트 (오리지널 터틀 규칙 적용)
# ==========================================
for ticker, name in all_stocks.items():
    try:
        stock_data = yf.download(ticker, period='1y', progress=False)
        
        if len(stock_data) >= 200:
            # 1. 기본 지표 계산
            recent_20_high = stock_data['High'].iloc[-20:].max().item()
            ma_200 = stock_data['Close'].rolling(window=200).mean().iloc[-1].item()
            today_volume = stock_data['Volume'].iloc[-1].item()
            recent_10_low = stock_data['Low'].iloc[-10:].min().item()
            current_price = stock_data['Close'].iloc[-1].item()
            
            # 2. 터틀 트레이딩의 핵심: N값(ATR) 계산
            # TR = max(당일고가-당일저가, abs(당일고가-전일종가), abs(당일저가-전일종가))
            high_low = stock_data['High'] - stock_data['Low']
            high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
            low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
            
            # pandas.concat으로 수정하여 DeprecationWarning 방지
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            
            # ATR (20일 이동평균)
            atr = tr.rolling(window=20).mean()
            current_n = atr.iloc[-1].item()
            
            # 🟢 [매수 조건] 20일선 + 200일선 + 거래량 100만 주!
            if (current_price >= recent_20_high) and (current_price > ma_200) and (today_volume >= 1000000):
                # N값을 함께 기록하여 리스크 관리에 활용할 수 있도록 함
                buy_signals.append(f"{name} (현재가: {current_price:.2f}, N값: {current_n:.2f})")
                print(f"🚀 [매수 신호] {name} - N값: {current_n:.2f}")
                
            # 🔴 [매도 조건] 10일 최저가 붕괴
            elif current_price <= recent_10_low:
                sell_signals.append(f"{name} (현재가: {current_price:.2f})")
                
    except Exception as e:
        pass 
        
    time.sleep(0.5) 

print(f"\n✅ 실시간 검사 끝! 매수 신호 {len(buy_signals)}개 발견.")

# ==========================================
# 4. 제미나이 퀀트 리포트 작성 및 디스코드 전송
# ==========================================
if len(buy_signals) > 0 or len(sell_signals) > 0:
    # 봇의 프롬프트를 좀 더 전문적인 퀀트 비서의 톤으로 업그레이드
    prompt = f"""
    너는 데이터를 기반으로 냉철하게 분석하는 전문 퀀트 투자 비서야.
    오늘 한국 코스피 Top 50, 미국 대장주 Top 50을 오리지널 터틀 트레이딩 기법(ATR 기반)으로 분석했어.
    
    - 🟢 시스템1 매수 신호 (20일 고점 돌파 + 200일선 지지): {buy_signals if buy_signals else '없음'}
    - 🔴 매도 및 손절 신호 (10일 저점 이탈): {sell_signals if sell_signals else '없음'}
    
    이 결과를 바탕으로 디스코드 브리핑 메시지를 작성해줘. 
    매수 신호가 발생한 종목은 N값(변동성)을 바탕으로 자금 관리(Position Sizing)의 중요성도 짧게 언급해줘.
    """
    
    response = client.models.generate_content(
        model='gemini-1.5-flash', 
        contents=prompt,
    )
    
    message_data = {"content": f"📈 **오리지널 터틀 퀀트 리포트** 📈\n{response.text}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
    print("디스코드 알림 발사 성공! 👏")
    
else:
    print("오늘은 매수/매도 신호가 발생하지 않았습니다.")
    message_data = {"content": "📈 **터틀 퀀트 브리핑** 📈\n오늘 실시간으로 한/미 대장주 100개를 분석한 결과, 터틀 시스템1에 부합하는 매수/매도 타점이 발생하지 않았습니다. 자본을 지키며 다음 추세를 기다리십시오."}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
