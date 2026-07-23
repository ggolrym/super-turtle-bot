# ==========================================
# 🐢 AI 터틀 트레이딩 (1,400개 풀스케일 + 방탄 스마트 인식)
# ==========================================
import os
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import requests
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

print("🌊 1,400개의 거대한 글로벌 주식 바다로 출항합니다...")

# ==========================================
# 1. 방탄(Crash-proof) 명단 수집 
# ==========================================
korea_stocks = {}
try:
    kr_df = pd.read_csv('kospi_list.csv')
    
    # 🌟 스마트 인식: 이름표가 'Symbol'이든 'Code'든 상관없이, 무조건 1열과 2열을 가져옵니다!
    col_sym = kr_df.columns[0] 
    col_name = kr_df.columns[1]
    
    for index, row in kr_df.iterrows():
        # 혹시 엑셀에서 '005930'이 그냥 '5930' 숫자로 저장됐어도, 앞에 0을 채워서 무조건 6자리(zfill)로 완벽 복원!
        raw_code = str(row[col_sym]).replace('.0', '').strip()
        ticker = raw_code.zfill(6) + '.KS'
        name = str(row[col_name])
        korea_stocks[ticker] = name
        
    print(f"🇰🇷 코스피 전체 {len(korea_stocks)}개 준비 완료!")
except Exception as e:
    print(f"🚨 한국 명단 수집 실패: {e}")
    print("💡 깃허브 첫 화면에 'kospi_list.csv' 파일이 진짜로 있는지 꼭 확인해주세요!")

us_stocks = {}
try:
    us_df = fdr.StockListing('SP500')
    
    # 🌟 스마트 인식: 미국 쪽 이름표가 'Symbol'일 수도, 'Ticker'일 수도 있으니 안전하게 확인!
    col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
    col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
    
    for index, row in us_df.iterrows():
        us_stocks[str(row[col_sym])] = str(row[col_name])
        
    print(f"🇺🇸 미국 S&P500 전체 {len(us_stocks)}개 준비 완료!")
except Exception as e:
    print(f"🚨 미국 명단 수집 실패: {e}")

# ------------------------------------------
all_stocks = {**korea_stocks, **us_stocks}

if len(all_stocks) == 0:
    print("🚨 한/미 주식을 단 한 개도 가져오지 못했습니다. 파일이 없거나 도서관이 닫혔습니다!")
    exit()

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
        
    time.sleep(0.6) # 경찰 피해서 0.6초 휴식

print(f"\n✅ 글로벌 풀스케일 검사 끝! 매수 신호 {len(buy_signals)}개 발견.")

# ==========================================
# 3. 브리핑 작성 및 전송 (안전망 플랜 B 탑재!)
# ==========================================
if len(buy_signals) > 0 or len(sell_signals) > 0:
    
    if len(buy_signals) > 20:
        buy_signals = buy_signals[:20] + ["... (종목이 너무 많아 상위 20개만 표시)"]
    if len(sell_signals) > 20:
        sell_signals = sell_signals[:20] + ["... (종목이 너무 많아 상위 20개만 표시)"]

    prompt = f"""
    너는 데이터를 기반으로 냉철하게 분석하는 전문 퀀트 투자 비서야.
    오늘 한국 코스피 전체와 미국 S&P500 전체 명단을 오리지널 터틀 트레이딩 기법으로 샅샅이 뒤졌어.
    
    - 🟢 시스템1 매수 신호 (20일 고점 돌파 + 200일선 지지): {buy_signals if buy_signals else '없음'}
    - 🔴 매도 및 손절 신호 (10일 저점 이탈): {sell_signals if sell_signals else '없음'}
    
    이 결과를 바탕으로 디스코드 브리핑 메시지를 아주 프로페셔널하게 작성해줘. 
    """
    
    # 🌟 안전망(Plan B) 준비: 제미나이가 실패할 경우를 대비해 빈 칸을 만들어 둡니다.
    response_text = ""
    
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                # 내일 아침 자동 실행을 위해, 가장 똑똑한 2.0으로 다시 고정해둡니다!
                model='gemini-1.5-flash-8b', 
                contents=prompt,
            )
            response_text = response.text # 성공하면 제미나이의 멋진 글을 담습니다.
            break 
        except Exception as e:
            print(f"제미나이 호출 실패... {attempt+1}차 재시도 중 ({e})")
            time.sleep(5)
            
    # 🌟 플랜 B 발동! 3번 다 실패해서 response_text가 여전히 빈 칸이라면?
    if not response_text:
        print("🚨 제미나이가 완전히 뻗었습니다! 플랜 B(원본 데이터 전송)를 가동합니다.")
        response_text = f"⚠️ **AI 비서 휴식 중! (시스템 원본 데이터 전송)**\n\n🟢 **매수 신호:**\n{buy_signals}\n\n🔴 **매도 신호:**\n{sell_signals}\n\n(AI 할당량이 초과되어 로봇이 직접 원본 데이터를 전송했습니다.)"
    
    message_data = {"content": f"🌊 **글로벌 풀스케일 퀀트 리포트 (1,400 종목)** 🌊\n{response_text}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
    print("디스코드 알림 발사 성공! 👏")
    
else:
    print("오늘은 매수/매도 신호가 발생하지 않았습니다.")
    message_data = {"content": "🌊 **글로벌 풀스케일 퀀트 리포트 (1,400 종목)** 🌊\n오늘 무려 1,400여 개의 기업을 샅샅이 뒤졌지만, 터틀 시스템1에 완벽히 부합하는 타점이 발생하지 않았습니다. 총알을 아끼고 폭풍을 기다리십시오."}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
