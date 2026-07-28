# ==========================================
# 🐢 AI 터틀 트레이딩 v7.0 (장부 기록형: 기억 상실증 극복)
# ==========================================
import os
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import requests
from google import genai
import time
import math
import json # 🌟 장부(DB) 관리를 위한 라이브러리 추가

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
    print("🚨 API 키나 웹훅 URL이 없습니다!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 1. 자본 및 리스크 설정
# ==========================================
TOTAL_CAPITAL = 500000   
RISK_PERCENT = 0.01      
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
MIN_TURNOVER_KRW = 10000000000 
MIN_VOLATILITY_RATIO = 1.5 
PORTFOLIO_FILE = 'portfolio.json' # 🌟 로봇의 기억 장부 파일명

print(f"💰 터틀 시스템 가동: 총자본 {TOTAL_CAPITAL:,}원 (1Unit 리스크: {RISK_AMOUNT:,.0f}원)")

# 🌟 장부(기억) 불러오기
if os.path.exists(PORTFOLIO_FILE):
    with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
        portfolio = json.load(f)
    print(f"📖 장부 로드 완료: 현재 {len(portfolio)}개 종목 보유 중")
else:
    portfolio = {}
    print("📖 새 장부를 펼쳤습니다. (보유 종목 없음)")

exchange_rate = 1350
try:
    ex_df = fdr.DataReader('USD/KRW')
    exchange_rate = ex_df['Close'].iloc[-1].item()
except Exception:
    pass

buy_signals = []
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
except Exception: pass

us_stocks = {}
try:
    us_df = fdr.StockListing('SP500')
    col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
    col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
    for _, row in us_df.iterrows():
        us_stocks[str(row[col_sym])] = str(row[col_name])
except Exception: pass

all_stocks = {**korea_stocks, **us_stocks}
print(f"\n🤖 총 {len(all_stocks)}개 종목 검사 시작!\n")

# ==========================================
# 3. 데이터 검증 및 터틀 로직 처리 (장부 연동)
# ==========================================
for ticker, name in all_stocks.items():
    try:
        stock_data = yf.download(ticker, period='1y', progress=False)
        if len(stock_data) < 200: continue
            
        current_price = stock_data['Close'].iloc[-1].item()
        
        # N값 (ATR) 계산 공통
        high_low = stock_data['High'] - stock_data['Low']
        high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
        low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        N = tr.rolling(window=20).mean().iloc[-1].item()
        
        N_krw = N if ticker.endswith('.KS') else N * exchange_rate
        unit_size = math.floor(RISK_AMOUNT / N_krw)
        unit_size = 1 if unit_size == 0 else unit_size

        # 차트 링크 생성기
        chart_link = f"https://finance.naver.com/item/fchart.naver?code={ticker.replace('.KS', '')}" if ticker.endswith('.KS') else f"https://finance.yahoo.com/quote/{ticker}/chart"

        # ------------------------------------------------
        # 📂 A. 이미 장부에 있는 종목 (보유 종목 관리)
        # ------------------------------------------------
        if ticker in portfolio:
            pos = portfolio[ticker]
            
            # 1. 청산 및 손절 검사 (가격이 손절가 밑이거나, 10일 저점 이탈 시)
            low_10 = stock_data['Low'].iloc[-11:-1].min().item()
            if current_price <= pos['stop_loss'] or current_price <= low_10:
                sell_signals.append(f"- [{name}] 전량 청산 (현재: {current_price:.2f} / 사유: 손절 또는 추세 이탈) [📊 차트 보기]({chart_link})")
                del portfolio[ticker] # 장부에서 삭제
                continue
                
            # 2. 피라미딩(불타기) 검사 (마지막 매수가 대비 0.5N 상승 시 추가 매수)
            if pos['units'] < 4 and current_price >= pos['last_buy_price'] + (0.5 * N):
                pos['units'] += 1
                pos['last_buy_price'] = current_price
                pos['stop_loss'] = current_price - (2 * N) # 손절가 끌어올리기 (Trailing Stop)
                buy_signals.append(f"- [{name}] 🔥 {pos['units']}차 불타기 진입: {unit_size}주 추가 매수 (현재: {current_price:.2f} / 새 손절가: {pos['stop_loss']:.2f}) [📊 차트 보기]({chart_link})")

        # ------------------------------------------------
        # 📂 B. 장부에 없는 종목 (신규 진입 검사)
        # ------------------------------------------------
        else:
            ma_200 = stock_data['Close'].rolling(window=200).mean().iloc[-1].item()
            if current_price < ma_200: continue
                
            today_volume = stock_data['Volume'].iloc[-1].item()
            turnover_krw = current_price * today_volume if ticker.endswith('.KS') else current_price * today_volume * exchange_rate
            if turnover_krw < MIN_TURNOVER_KRW: continue
                
            volatility_ratio = (N / current_price) * 100
            if volatility_ratio < MIN_VOLATILITY_RATIO: continue
            
            high_20 = stock_data['High'].iloc[-21:-1].max().item()
            
            # 신규 돌파 성공!
            if current_price >= high_20:
                stop_loss_price = current_price - (2 * N)
                
                # 장부에 새롭게 기록
                portfolio[ticker] = {
                    'name': name,
                    'units': 1,
                    'last_buy_price': current_price,
                    'stop_loss': stop_loss_price
                }
                buy_signals.append(f"- [{name}] ✨ 신규 1차 진입: {unit_size}주 매수 (현재: {current_price:.2f} / 손절가: {stop_loss_price:.2f}) [📊 차트 보기]({chart_link})")

    except Exception: pass
    time.sleep(0.5)

# 🌟 4. 오늘 일과가 끝난 후 변경된 장부를 파일로 저장
with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f:
    json.dump(portfolio, f, indent=4, ensure_ascii=False)

# ==========================================
# 5. 브리핑 작성 및 전송
# ==========================================
print(f"\n✅ 검사 완료! (신규/추가매수: {len(buy_signals)}건, 청산: {len(sell_signals)}건)")

if buy_signals or sell_signals:
    buy_text = '\n'.join(buy_signals[:15]) if buy_signals else '신호 없음'
    sell_text = '\n'.join(sell_signals[:15]) if sell_signals else '신호 없음'

    prompt = f"""
    아래는 상태 기억(State Management) 기능이 탑재된 터틀 봇의 포트폴리오 관리 결과입니다.
    
    [신규 진입 및 불타기 신호]
    {buy_text}
    
    [청산 및 손절 신호]
    {sell_text}
    
    위 데이터를 바탕으로 객관적이고 논리적인 퀀트 브리핑 문서를 작성하십시오. 감정적 표현을 배제하십시오.
    마크다운 링크 형태인 [📊 차트 보기](URL) 부분은 글자를 훼손하지 말고 원본 그대로 복사해서 출력하십시오.
    """
    
    response_text = ""
    for _ in range(3):
        try:
            response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
            response_text = response.text 
            break 
        except Exception: time.sleep(5)
            
    if not response_text:
        response_text = f"**오류 발생 원본 데이터 전송**\n\n**매수/불타기**\n{buy_text}\n\n**청산**\n{sell_text}"
    
    final_content = f"🐢 **무인 펀드 매니저 v7.0 리포트 (총자본 {TOTAL_CAPITAL:,}원)** 🐢\n{response_text}"
    if len(final_content) > 1900: final_content = final_content[:1900] + "\n\n... (⚠️ 신호 초과로 요약됨)"

    requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content})
else:
    requests.post(DISCORD_WEBHOOK_URL, json={"content": f"🐢 **무인 펀드 매니저 v7.0 리포트** 🐢\n오늘 포트폴리오 신규 진입이나 청산/불타기 조건이 발생하지 않았습니다. 기존 포지션을 유지하며 관망합니다."})
