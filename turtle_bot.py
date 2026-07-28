# ==========================================
# 🐢 AI 터틀 트레이딩 v6.4 (200일선 절대 방어선 & 변동성 필터 탑재)
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
    print("🚨 API 키나 웹훅 URL이 없습니다!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 1. 자본 및 리스크 설정
# ==========================================
TOTAL_CAPITAL = 500000   # 총 투자금 50만 원
RISK_PERCENT = 0.01      # 1회 최대 허용 리스크 (1%)
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
MIN_TURNOVER_KRW = 10000000000 # 최소 일일 거래대금 (100억 원)
MIN_VOLATILITY_RATIO = 1.5 # 터틀 DNA: 하루 변동성 1.5% 이상 종목만 타겟팅

print(f"💰 터틀 시스템 가동: 총자본 {TOTAL_CAPITAL:,}원 (1Unit 리스크: {RISK_AMOUNT:,.0f}원)")

exchange_rate = 1350
try:
    ex_df = fdr.DataReader('USD/KRW')
    exchange_rate = ex_df['Close'].iloc[-1].item()
    print(f"💱 실시간 환율 적용: 1달러 = {exchange_rate:,.2f}원")
except Exception:
    print("⚠️ 실시간 환율 로드 실패. 기본값 1,350원 적용.")

buy_signals_sys1 = []
buy_signals_sys2 = []
sell_signals = []

# ==========================================
# 2. 명단 수집 
# ==========================================
korea_stocks = {}
try:
    kr_df = pd.read_csv('kospi_list.csv')
    for _, row in kr_df.iterrows():
        ticker = str(row.iloc[0]).replace('.0', '').strip().zfill(6) + '.KS'
        korea_stocks[ticker] = str(row.iloc[1])
except Exception:
    pass

us_stocks = {}
try:
    us_df = fdr.StockListing('SP500')
    col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
    col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
    for _, row in us_df.iterrows():
        us_stocks[str(row[col_sym])] = str(row[col_name])
except Exception:
    pass

all_stocks = {**korea_stocks, **us_stocks}
print(f"\n🤖 총 {len(all_stocks)}개 종목 검사 시작! (200일선 및 유동성 필터링 중...)\n")

# ==========================================
# 3. 데이터 검증 및 터틀 로직 처리 (최적화)
# ==========================================
for ticker, name in all_stocks.items():
    try:
        stock_data = yf.download(ticker, period='1y', progress=False)
        
        if len(stock_data) >= 200:
            current_price = stock_data['Close'].iloc[-1].item()
            ma_200 = stock_data['Close'].rolling(window=200).mean().iloc[-1].item()
            
            # 🛡️ [전술 1단계] 200일선 장기 추세 필터 (절대 방어선)
            # 200일선 아래에 있는 녀석들은 아예 뒤도 안 돌아보고 패스합니다! (속도 대폭 향상)
            if current_price < ma_200:
                continue
                
            today_volume = stock_data['Volume'].iloc[-1].item()
            turnover = current_price * today_volume
            turnover_krw = turnover if ticker.endswith('.KS') else turnover * exchange_rate
            
            # 유동성 필터 (100억 미만 작전주 컷)
            if turnover_krw < MIN_TURNOVER_KRW:
                continue
            
            # 돌파 기준선 설정
            high_20 = stock_data['High'].iloc[-21:-1].max().item()
            high_55 = stock_data['High'].iloc[-56:-1].max().item()
            low_10 = stock_data['Low'].iloc[-11:-1].min().item()
            low_20 = stock_data['Low'].iloc[-21:-1].min().item()
            
            # N값 (ATR) 계산
            high_low = stock_data['High'] - stock_data['Low']
            high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
            low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=20).mean()
            N = atr.iloc[-1].item()
            
            # 🧬 변동성 필터 (터틀 DNA 검사)
            volatility_ratio = (N / current_price) * 100
            if volatility_ratio < MIN_VOLATILITY_RATIO:
                continue
                
            # 자금 관리 (매수 수량 계산)
            N_krw = N if ticker.endswith('.KS') else N * exchange_rate
            unit_size = math.floor(RISK_AMOUNT / N_krw)
            unit_size = 1 if unit_size == 0 else unit_size
            
            # ⚔️ [전술 2단계] 20일 / 55일 고점 돌파 (매수 타이밍 포착)
            # 이미 위에서 200일선 위라는 조건을 통과했으므로, 돌파만 확인하면 무조건 발사!
            
            # --- Sys1 (단기 돌파) ---
            if current_price >= high_20:
                price_diff = current_price - high_20
                pyramid_stage = math.floor(price_diff / (0.5 * N)) + 1
                if pyramid_stage <= 4:
                    stop_loss_price = high_20 - (2 * N)
                    signal_str = f"- [{name}] Sys1 {pyramid_stage}차 진입: {unit_size}주 매수 (현재: {current_price:.2f} / 손절가: {stop_loss_price:.2f})"
                    buy_signals_sys1.append(signal_str)
                    print(f"🚀 [Sys1 포착] {name}")
                    
            elif current_price <= low_10:
                sell_signals.append(f"- [{name}] Sys1 청산 (10일선 이탈)")
            
            # --- Sys2 (장기 돌파) ---
            if current_price >= high_55:
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
    아래는 총 자본 {TOTAL_CAPITAL:,}원을 기준으로 200일선 추세 필터, 1.5% 변동성 제한, 1 Unit 리스크 관리 시스템을 통과한 완벽한 매수/매도 타점입니다.
    
    [시스템 1: 20일 돌파]
    {sys1_text}
    
    [시스템 2: 55일 장기 돌파]
    {sys2_text}
    
    [청산 및 손절 신호]
    {sell_text}
    
    위 데이터를 바탕으로 객관적이고 논리적인 퀀트 브리핑 문서를 작성하십시오. 감정적 표현을 배제하고 숫자에 집중하십시오.
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
    
    message_data = {"content": f"🐢 **터틀 시스템 v6.4 분석 리포트 (총자본 {TOTAL_CAPITAL:,}원)** 🐢\n{response_text}"}
    
    res = requests.post(DISCORD_WEBHOOK_URL, json=message_data)
    if res.status_code in [200, 204]:
        print("🚀 디스코드 알림 발송 성공!")
    else:
        print(f"🚨 디스코드 발송 실패: {res.status_code} - {res.text}")
    
else:
    print("오늘의 진입/청산 신호가 없어 생존 신고만 보냅니다.")
    message_data = {"content": f"🐢 **터틀 시스템 v6.4 분석 리포트 (총자본 {TOTAL_CAPITAL:,}원)** 🐢\n현재 200일선 위에서 강한 변동성을 유지하며 시스템 돌파 기준을 충족한 종목이 없습니다. 관망을 유지합니다."}
    requests.post(DISCORD_WEBHOOK_URL, json=message_data)
    print("🚀 디스코드 생존 신고 발송 성공!")
