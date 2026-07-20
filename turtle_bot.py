# ==========================================
# 🐢 AI 터틀 트레이딩 (미국 S&P 500 자동화 버전)
# ==========================================
import os
import yfinance as yf
import FinanceDataReader as fdr  # 다시 출석부 마법 도구를 부릅니다!
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

# 2. 미국 상위 500개 기업(S&P 500) 출석부 자동 다운로드!
print("📚 미국 S&P 500 전체 출석부를 가져오는 중입니다...")
sp500_info = fdr.StockListing('SP500')
stock_list = sp500_info['Symbol'].tolist()
stock_names = sp500_info['Name'].tolist()

# 500개를 다 하면 약 8~10분 정도 걸려요! (원하면 숫자를 바꿔서 줄일 수 있어요)
TEST_COUNT = 0 
if TEST_COUNT > 0:
    stock_list = stock_list[:TEST_COUNT]
    stock_names = stock_names[:TEST_COUNT]
    print(f"⏱️ 시간 절약을 위해 상위 {TEST_COUNT}개만 검사할게요.\n")

print(f"🤖 총 {len(stock_list)}개의 미국 주식 감시를 시작합니다!\n")

client = genai.Client(api_key=GEMINI_API_KEY)

buy_signals = []
sell_signals = []

# 3. 500개 주식 컨베이어 벨트 시작!
for i in range(len(stock_list)):
    ticker = stock_list[i]
    name = stock_names[i]
    
    try:
        # 1년(1y)치 주가 데이터 가져오기
        stock_data = yf.download(ticker, period='1y', progress=False)
        
        # 200일 이상 튼튼하게 살아남은 주식만 검사
        if len(stock_data) >= 200:
            recent_20_high = stock_data['High'].iloc[-20:].max().item()
            ma_200 = stock_data['Close'].rolling(window=200).mean().iloc[-1].item()
            today_volume = stock_data['Volume'].iloc[-1].item()
            recent_10_low = stock_data['Low'].iloc[-10:].min().item()
            current_price = stock_data['Close'].iloc[-1].item()
            
            # 🟢 [매수 조건] 20일 최고가 돌파 + 200일선 위 + 거래량 100만 주 이상!
            if (current_price >= recent_20_high) and (current_price > ma_200) and (today_volume >= 1000000):
                buy_signals.append(f"{name}({ticker})")
                print(f"🚀 [발견!] {name}")
                
            # 🔴 [매도 조건] 10일 최저가 붕괴 (도망쳐!)
            elif current_price <= recent_10_low:
                sell_signals.append(f"{name}({ticker})")
                
    except Exception as e:
        pass # 에러가 나거나 데이터가 없는 주식은 조용히 넘어갑니다.
        
    # 야후 파이낸스 경찰을 피해 0.5초씩 쿨쿨 자기! (500개니까 조금 짧게 0.5초로 했어)
    time.sleep(0.5) 

print(f"\n✅ 500개 검사 끝! 살 주식 {len(buy_signals)}개, 팔 주식 {len(sell_signals)}개 발견.")

# 4. 발견된 주식이 하나라도 있으면 제미나이에게 디스코드 알림 시키기!
if len(buy_signals) > 0 or len(sell_signals) > 0:
    prompt = f"""
    너는 12살도 이해하기 쉽게 설명해주는 최고의 퀀트 투자 비서야.
    오늘 한국 시간으로 {datetime.now().strftime('%Y년 %m월 %d일')}이야.
    미국 S&P 500 주식들을 검사했어.
    
    - 🟢 매수 추천 (200일선 뚫고 거래량 100만 넘은 초강력 주식!): {buy_signals if buy_signals else '없음'}
    - 🔴 매도 경고 (10일 최저가 깨져서 도망쳐야 할 주식): {sell_signals if sell_signals else '없음'}
    
    이 결과를 바탕으로 디스코드 알림 메시지를 작성해줘. 이모티콘 듬뿍 넣어서!
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    message_data = {"content": f"🗽 **미국 S&P 500 자동화 브리핑** 🗽\n{response.text}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
    print("디스코드로 알림 쏘기 성공! 👏")
else:
    print("오늘은 그 많은 500개 기업 중에서도 이 깐깐한 조건을 통과한 완벽한 주식이 없네요! 돈을 아끼세요! 😴")
