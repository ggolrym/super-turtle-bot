# ==========================================
# 🐢 AI 터틀 트레이딩 v6.0 (System 1&2, 자금관리, 거래대금, 피라미딩 통합)
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
    print("API Key 또는 Webhook URL이 설정되지 않았습니다.")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 1. 자본 및 리스크 설정
# ==========================================
TOTAL_CAPITAL = 1000000 # 총 투자금 (100만 원)
RISK_PERCENT = 0.01      # 1회 최대 허용 리스크 (1%)
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
MIN_TURNOVER_KRW = 10000000000 # 최소 일일 거래대금 (100억 원)

# 실시간 환율 (미국 주식 거래대금 및 N값 원화 환산용)
exchange_rate = 1480
try:
    ex_df = fdr.DataReader('USD/KRW')
    exchange_rate = ex_df['Close'].iloc[-1].item()
except Exception:
    pass

buy_signals_sys1 = []
buy_signals_sys2 = []
sell_signals = []

# ==========================================
# 2. 명단 수집 (코스피 전체, S&P 500)
# ==========================================
korea_stocks = {}
try:
    kr_df = pd.read_csv('kospi_list.csv')
    col_sym, col_name = kr_df.columns[0], kr_df.columns[1]
    for _, row in kr_df.iterrows():
        ticker = str(row[col_sym]).replace('.0', '').strip().zfill(6) + '.KS'
        korea_stocks[ticker] = str(row[col_name])
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

# ==========================================
# 3. 데이터 검증 및 터틀 로직 처리
# ==========================================
for ticker, name in all_stocks.items():
    try:
        stock_data = yf.download(ticker, period='1y', progress=False)
        
        if len(stock_data) >= 200:
            current_price = stock_data['Close'].iloc[-1].item()
            today_volume = stock_data['Volume'].iloc[-1].item()
            
            # 거래대금 계산 (한국은 원화, 미국은 달러를 원화로 환산)
            turnover = current_price * today_volume
            turnover_krw = turnover if ticker.endswith('.KS') else turnover * exchange_rate
            
            # 거래대금 100억 미만 종목 필터링 (작전주 및 유동성 부족 차단)
            if turnover_krw < MIN_TURNOVER_KRW:
                continue
            
            # 돌파 기준가 (과거 기준)
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
            
            # N값 원화 환산 및 Unit 산출
            N_krw = N if ticker.endswith('.KS') else N * exchange_rate
            unit_size = math.floor(RISK_AMOUNT / N_krw)
            unit_size = 1 if unit_size == 0 else unit_size
            
           # -----------------------------------
            # 시스템 1 (20일 돌파 / 10일 이탈) 및 피라미딩
            # -----------------------------------
            if current_price >= high_20 and current_price > ma_200:
                price_diff = current_price - high_20
                pyramid_stage = math.floor(price_diff / (0.5 * N)) + 1
                
                if pyramid_stage <= 4:
                    # 🌟 손절가 계산 로직 추가 (돌파 기준가 - 2N)
                    stop_loss_price = high_20 - (2 * N)
                    
                    signal_str = f"- [{name}] Sys1 {pyramid_stage}차 진입: {unit_size}주 매수 (기준: {high_20:.2f} / 현재가: {current_price:.2f} / 🛑 손절가: {stop_loss_price:.2f})"
                    buy_signals_sys1.append(signal_str)
                    
            elif current_price <= low_10:
                sell_signals.append(f"- [{name}] Sys1 청산 (10일선 이탈)")
            
            # -----------------------------------
            # 시스템 2 (55일 돌파 / 20일 이탈) 및 피라미딩
            # -----------------------------------
            if current_price >= high_55 and current_price > ma_200:
                price_diff = current_price - high_55
                pyramid_stage = math.floor(price_diff / (0.5 * N)) + 1
                
                if pyramid_stage <= 4:
                    # 🌟 손절가 계산 로직 추가 (돌파 기준가 - 2N)
                    stop_loss_price = high_55 - (2 * N)
                    
                    signal_str = f"- [{name}] Sys2 {pyramid_stage}차 진입: {unit_size}주 매수 (기준: {high_55:.2f} / 현재가: {current_price:.2f} / 🛑 손절가: {stop_loss_price:.2f})"
                    buy_signals_sys2.append(signal_str)
                    
            elif current_price <= low_20:
                if f"- [{name}] Sys1 청산 (10일선 이탈)" not in sell_signals:
                    sell_signals.append(f"- [{name}] Sys2 청산 (20일선 이탈)")
                
    except Exception:
        pass 
        
    time.sleep(0.5)

# ==========================================
# 4. 브리핑 작성 및 전송
# ==========================================
if buy_signals_sys1 or buy_signals_sys2 or sell_signals:
    
    # Discord 글자 수 제한 방지 (카테고리별 최대 10개 출력)
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
        except Exception:
            time.sleep(5)
            
    if not response_text:
        response_text = f"**오류 발생 원본 데이터 전송**\n\n**Sys1**\n{sys1_text}\n\n**Sys2**\n{sys2_text}\n\n**청산**\n{sell_text}"
    
    message_data = {"content": f"**터틀 시스템 v6.0 분석 리포트 (총자본 100만 원)**\n{response_text}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
    
else:
    message_data = {"content": "**터틀 시스템 v6.0 분석 리포트**\n현재 거래대금 100억 원 이상 종목 중 시스템 1, 2 진입 및 청산 기준을 충족한 종목이 없습니다."}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
