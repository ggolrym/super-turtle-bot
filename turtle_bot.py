# ==========================================
# 🐢 AI 터틀 트레이딩 v5.0 (자금 관리 자동 계산 탑재)
# ==========================================
import os
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import requests
from google import genai
import time
import math

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
    print("🚨 금고에 API 키나 웹훅 URL이 없습니다!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 💰 1. 퀀트 트레이더의 자금 설정 (중요!)
# ==========================================
TOTAL_CAPITAL = 1000000 # 총 투자금: 100만 원 (원하는 대로 수정하세요!)
RISK_PERCENT = 0.01     # 1회 매수 시 허용 리스크 (총 자산의 1%)
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT # 내가 잃을 수 있는 최대 금액 (1만 원)

print(f"💰 총 투자금: {TOTAL_CAPITAL:,}원 / 1회 최대 허용 손실: {RISK_AMOUNT:,.0f}원")

# 실시간 원/달러 환율 가져오기 (미국 주식 계산용)
exchange_rate = 1350 # 환율 가져오기 실패 시 기본값
try:
    ex_df = fdr.DataReader('USD/KRW')
    exchange_rate = ex_df['Close'].iloc[-1].item()
    print(f"💱 실시간 환율 적용: 1달러 = {exchange_rate:,.2f}원")
except Exception as e:
    print(f"⚠️ 환율 가져오기 실패, 기본 환율({exchange_rate}원)을 사용합니다.")

buy_signals = []
sell_signals = []

# ==========================================
# 2. 방탄(Crash-proof) 명단 수집 
# ==========================================
korea_stocks = {}
try:
    kr_df = pd.read_csv('kospi_list.csv')
    col_sym = kr_df.columns[0] 
    col_name = kr_df.columns[1]
    
    for index, row in kr_df.iterrows():
        raw_code = str(row[col_sym]).replace('.0', '').strip()
        ticker = raw_code.zfill(6) + '.KS'
        korea_stocks[ticker] = str(row[col_name])
    print(f"🇰🇷 코스피 전체 {len(korea_stocks)}개 준비 완료!")
except:
    print("💡 kospi_list.csv 파일이 없습니다. 한국 주식은 패스합니다.")

us_stocks = {}
try:
    us_df = fdr.StockListing('SP500')
    col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
    col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
    
    for index, row in us_df.iterrows():
        us_stocks[str(row[col_sym])] = str(row[col_name])
    print(f"🇺🇸 미국 S&P500 전체 {len(us_stocks)}개 준비 완료!")
except:
    print("🚨 미국 명단 수집 실패")

all_stocks = {**korea_stocks, **us_stocks}
print(f"\n🤖 총 {len(all_stocks)}개 대장주 정밀 검사 시작!\n")

# ==========================================
# 3. 1,400개 컨베이어 벨트 (ATR + 수량 계산)
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
            
            # 터틀 N값(ATR) 계산
            high_low = stock_data['High'] - stock_data['Low']
            high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
            low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=20).mean()
            current_n = atr.iloc[-1].item() # N값
            
            # 🟢 [매수 조건] 20일선 + 200일선 + 거래량 100만 주
            if (current_price >= recent_20_high) and (current_price > ma_200) and (today_volume >= 1000000):
                
                # 🌟 자금 관리 (매수 수량 계산) 🌟
                if ticker.endswith('.KS'): 
                    # 한국 주식 (원화)
                    n_krw = current_n
                    currency_mark = "원"
                else: 
                    # 미국 주식 (달러를 원화로 변환해서 계산)
                    n_krw = current_n * exchange_rate
                    currency_mark = "달러"
                
                # 리스크 금액(1만 원) ÷ N값(원화) = 매수할 주식 수! (소수점은 내림)
                unit_size = math.floor(RISK_AMOUNT / n_krw)
                
                # N값이 너무 커서 1주도 못 사는 경우(0주) 방지
                if unit_size == 0:
                    unit_size = 1
                
                # 필요한 실제 투자금
                required_money = unit_size * current_price
                if ticker.endswith('.KS'):
                    req_money_krw = required_money
                else:
                    req_money_krw = required_money * exchange_rate

                buy_info = f"- **{name}**: 🎯 **{unit_size}주 매수 요망** (현재가: {current_price:,.2f}{currency_mark}, 필요 투자금: 약 {req_money_krw:,.0f}원)"
                buy_signals.append(buy_info)
                print(f"🚀 [매수 신호] {name} -> {unit_size}주 사세요!")
                
            # 🔴 [매도 조건] 10일 최저가 붕괴
            elif current_price <= recent_10_low:
                sell_signals.append(f"- {name} (현재가: {current_price:,.2f})")
                
    except Exception as e:
        pass 
        
    time.sleep(0.6)

print(f"\n✅ 검사 끝! 매수 신호 {len(buy_signals)}개 발견.")

# ==========================================
# 4. 브리핑 작성 및 전송 (플랜 B 탑재)
# ==========================================
if len(buy_signals) > 0 or len(sell_signals) > 0:
    
    if len(buy_signals) > 20:
        buy_signals = buy_signals[:20] + ["... (종목이 너무 많아 상위 20개만 표시)"]
    if len(sell_signals) > 20:
        sell_signals = sell_signals[:20] + ["... (종목이 너무 많아 상위 20개만 표시)"]

    buy_text = '\n'.join(buy_signals) if buy_signals else '없음'
    sell_text = '\n'.join(sell_signals) if sell_signals else '없음'

    prompt = f"""
    너는 데이터를 기반으로 냉철하게 분석하는 전문 퀀트 투자 비서야.
    총 투자금 {TOTAL_CAPITAL:,}원을 바탕으로 1% 리스크(1 Unit) 관리 룰을 적용하여 주식 매수 수량을 계산했어.
    
    - 🟢 매수 신호 및 수량 (1 Unit):\n{buy_text}
    - 🔴 매도 및 손절 신호:\n{sell_text}
    
    이 결과를 바탕으로 디스코드 브리핑 메시지를 아주 프로페셔널하게 작성해줘. 숫자는 그대로 살려서 꼭 적어줘.
    """
    
    response_text = ""
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=prompt,
            )
            response_text = response.text 
            break 
        except Exception as e:
            print(f"제미나이 호출 실패... {attempt+1}차 재시도 중 ({e})")
            time.sleep(5)
            
    if not response_text:
        print("🚨 플랜 B(원본 데이터 전송)를 가동합니다.")
        response_text = f"⚠️ **AI 비서 휴식 중! (시스템 원본 데이터 전송)**\n\n🟢 **매수 추천 (100만원 기준):**\n{buy_text}\n\n🔴 **매도 신호:**\n{sell_text}"
    
    message_data = {"content": f"🐢 **터틀 시스템 자금 관리 리포트 (총자산 100만 원)** 🐢\n{response_text}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
    
else:
    message_data = {"content": "🐢 **터틀 시스템 자금 관리 리포트** 🐢\n오늘 무려 1,400여 개의 기업을 샅샅이 뒤졌지만, 터틀 시스템에 부합하는 타점이 발생하지 않았습니다. 현금 비중을 유지하십시오."}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
