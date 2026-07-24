# ==========================================
# 🐢 AI 터틀 트레이딩 v6.2 (진행률 표시 및 JSON 전송 복구)
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
# 1. 자본 및 리스크 설정
# ==========================================
TOTAL_CAPITAL = 500000   # 총 투자금 50만 원
RISK_PERCENT = 0.01      # 1회 최대 허용 리스크 (1%)
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
MIN_TURNOVER_KRW = 10000000000 # 최소 일일 거래대금 (100억 원)

# 🌟 [신규 추가] 터틀 DNA 필터 (최소 변동성)
MIN_VOLATILITY_RATIO = 1.5 # 하루 평균 변동폭(N)이 주가의 1.5% 이상인 종목만 타겟팅

print(f"💰 터틀 시스템 가동: 총자본 {TOTAL_CAPITAL:,}원 (1Unit 리스크: {RISK_AMOUNT:,.0f}원)")

exchange_rate = 1480
try:
    ex_df = fdr.DataReader('USD/KRW')
    exchange_rate = ex_df['Close'].iloc[-1].item()
    print(f"💱 실시간 환율 적용: 1달러 = {exchange_rate:,.2f}원")
except Exception:
    print("⚠️ 실시간 환율 실패. 기본값 1,480원을 적용합니다.")

buy_signals_sys1 = []
buy_signals_sys2 = []
sell_signals = []

# ==========================================
# 2. 명단 수집 
# ==========================================
korea_stocks = {}
try:
    kr_df = pd.read_csv('kospi_list.csv')
    col_sym, col_name = kr_df.columns[0], kr_df.columns[1]
    for _, row in kr_df.iterrows():
        ticker = str(row[col_sym]).replace('.0', '').strip().zfill(6) + '.KS'
        korea_stocks[ticker] = str(row[col_name])
    print(f"🇰🇷 코스피 전체 {len(korea_stocks)}개 준비 완료!")
except Exception:
    print("💡 kospi_list.csv 파일 로드 실패. 한국 주식 패스.")

us_stocks = {}
try:
    us_df = fdr.StockListing('SP500')
    col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
    col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
    for _, row in us_df.iterrows():
        us_stocks[str(row[col_sym])] = str(row[col_name])
    print(f"🇺🇸 미국 S&P500 전체 {len(us_stocks)}개 준비 완료!")
except Exception:
    print("🚨 미국 S&P 500 명단 로드 실패.")

all_stocks = {**korea_stocks, **us_stocks}
print(f"\n🤖 총 {len(all_stocks)}개 거대 유동성(100억 이상) 종목 정밀 검사 시작! (약 13분 소요)\n")

# ==========================================
# 3. 데이터 검증 및 터틀 로직 처리
# ==========================================
for ticker, name in all_stocks.items():
    try:
        stock_data = yf.download(ticker, period='1y', progress=False)
        
        if len(stock_data) >= 200:
            current_price = stock_data['Close'].iloc[-1].item()
            today_volume = stock_data['Volume'].iloc[-1].item()
            
            turnover = current_price * today_volume
            turnover_krw = turnover if ticker.endswith('.KS') else turnover * exchange_rate
            
            if turnover_krw < MIN_TURNOVER_KRW:
                continue
            
            high_20 = stock_data['High'].iloc[-21:-1].max().item()
            high_55 = stock_data['High'].iloc[-56:-1].max().item()
            low_10 = stock_data['Low'].iloc[-11:-1].min().item()
            low_20 = stock_data['Low'].iloc[-21:-1].min().item()
            ma_200 = stock_data['Close'].rolling(window=200).mean().iloc[-1].item()
            
            # N값 (ATR) 계산
            high_low = stock_data['High'] - stock_data['Low']
            high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
            low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=20).mean()
            N = atr.iloc[-1].item()
            
            # 🌟 [신규 추가] 터틀 적합도(변동성) 검사
            # 주가 대비 N값의 비율(%)을 계산합니다.
            volatility_ratio = (N / current_price) * 100
            
            # 변동성이 우리가 설정한 1.5%보다 작으면, 너무 무거운 주식이므로 패스!
            if volatility_ratio < MIN_VOLATILITY_RATIO:
                continue
                
            N_krw = N if ticker.endswith('.KS') else N * exchange_rate
            unit_size = math.floor(RISK_AMOUNT / N_krw)
            unit_size = 1 if unit_size == 0 else unit_size
            
            # --- Sys1 ---
            if current_price >= high_20 and current_price > ma_200:
                price_diff = current_price - high_20
                pyramid_stage = math.floor(price_diff / (0.5 * N)) + 1
                if pyramid_stage <= 4:
                    stop_loss_price = high_20 - (2 * N)
                    signal_str = f"- [{name}] Sys1 {pyramid_stage}차 진입: {unit_size}주 매수 (현재: {current_price:.2f} / 손절가: {stop_loss_price:.2f})"
                    buy_signals_sys1.append(signal_str)
                    print(f"🚀 [Sys1 포착] {name}")
                    
            elif current_price <= low_10:
                sell_signals.append(f"- [{name}] Sys1 청산 (10일선 이탈)")
            
            # --- Sys2 ---
            if current_price >= high_55 and current_price > ma_200:
                price_diff = current_price - high_55
                pyramid_stage = math.floor(price_diff / (0.5 * N)) + 1
                if pyramid_stage <= 4:
                    stop_loss_price = high_55 - (2 * N)
                    signal_str = f"- [{name}] Sys2 {pyramid_stage}차 진입: {unit_size}주 매수 (현재: {current_price:.2f} / 손절가: {stop_loss_price:.2f})"
                    buy_signals_sys2.append(signal_str)
                    print(f"🚀 [Sys2 포착] {name}")
                    
            elif current_price <= low_20:
                if f"- [{name}] Sys1 청산 (10일선 이탈)" not in sell_signals:
                    sell_signals.append(f"- [{name}] Sys2 청산 (20일선 이탈)")
                
    except Exception:
        pass 
        
    time.sleep(0.5)

# ==========================================
# 4. 브리핑 작성 및 전송
# ==========================================
print(f"\n✅ 검사 완료! (Sys1: {len(buy_signals_sys1)}건, Sys2: {len(buy_signals_sys2)}건, 청산: {len(sell_signals)}건)")

if buy_signals_sys1 or buy_signals_sys2 or sell_signals:
    
    sys1_text = '\n'.join(buy_signals_sys1[:10]) if buy_signals_sys1 else '신호 없음'
    sys2_text = '\n'.join(buy_signals_sys2[:10]) if buy_signals_sys2 else '신호 없음'
    sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '신호 없음'

    prompt = f"""
    아래는 총 자본 {TOTAL_CAPITAL:,}원을 기준으로 1% 리스크(1 Unit) 로직, 일일 거래대금 100억 이상 필터, 그리고 0.5N 단위 피라미딩 추적이 적용된 결과입니다.
    
    [시스템 1: 20일 돌파]
    {sys1_text}
    
    [시스템 2: 55일 장기 돌파]
    {sys2_text}
    
    [청산 및 손절 신호]
    {sell_text}
    
    위 데이터를 바탕으로 객관적이고 논리적인 퀀트 브리핑 문서를 작성하십시오. 감정적 표현을 배제하고 사실 전달에 집중하십시오.
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
            print(f"⚠️ 제미나이 호출 실패... {attempt+1}차 재시도 중 ({e})")
            time.sleep(5)
            
    if not response_text:
        print("🚨 플랜 B 가동: 원본 데이터 디스코드 전송")
        response_text = f"**오류 발생 원본 데이터 전송**\n\n**Sys1**\n{sys1_text}\n\n**Sys2**\n{sys2_text}\n\n**청산**\n{sell_text}"
    
   # 수정 전 (v6.2): f"🐢 **터틀 시스템 v6.2 분석 리포트 (총자본 100만 원)** 🐢\n{response_text}"
    
    # 수정 후 (자동 인식):
    message_data = {"content": f"🐢 **터틀 시스템 v6.2 분석 리포트 (총자본 {TOTAL_CAPITAL:,}원)** 🐢\n{response_text}"}
    
    # 🌟 핵심: data= 대신 json= 을 사용하여 디스코드 400 에러를 원천 차단!
    res = requests.post(DISCORD_WEBHOOK_URL, json=message_data)
    if res.status_code in [200, 204]:
        print("🚀 디스코드 알림 발송 성공!")
    else:
        print(f"🚨 디스코드 발송 실패: {res.status_code} - {res.text}")
    
else:
    print("오늘의 진입/청산 신호가 없어 생존 신고만 보냅니다.")
    message_data = {"content": "🐢 **터틀 시스템 v6.2 분석 리포트** 🐢\n현재 거래대금 100억 원 이상 종목 중 시스템 1, 2 진입 및 청산 기준을 충족한 종목이 없습니다."}
    requests.post(DISCORD_WEBHOOK_URL, json=message_data)
    print("🚀 디스코드 생존 신고 발송 성공!")
