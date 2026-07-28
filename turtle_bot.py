# ==========================================
# 🐢 AI 멀티 에셋 터틀 봇 v7.2 (포트폴리오 총 위험 통제 탑재)
# ==========================================
import os
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import requests
from google import genai
import time
import math
import json 

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
    print("🚨 API 키나 웹훅 URL이 없습니다!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 1. 자본 및 리스크 한도 설정
# ==========================================
TOTAL_CAPITAL = 500000     
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
MIN_TURNOVER_KRW = 10000000000 
MIN_VOLATILITY_RATIO = 1.5 
PORTFOLIO_FILE = 'portfolio.json' 

# 🌟 [핵심 추가] 오리지널 터틀 리스크 한도 (Heat Limit)
MAX_TOTAL_UNITS = 12       # 계좌 전체를 통틀어 최대 12 Unit까지만 보유
MAX_SECTOR_UNITS = 6       # 같은 섹터(예: 주식)는 최대 6 Unit까지만 보유

print(f"💰 멀티 에셋 터틀 시스템 가동: 총자본 {TOTAL_CAPITAL:,}원 (1Unit: {RISK_AMOUNT:,.0f}원)")
print(f"🛡️ 리스크 한도: 총 보유 {MAX_TOTAL_UNITS} Units / 섹터별 최대 {MAX_SECTOR_UNITS} Units")

if os.path.exists(PORTFOLIO_FILE):
    with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
        portfolio = json.load(f)
else:
    portfolio = {}

exchange_rate = 1350
try:
    ex_df = fdr.DataReader('USD/KRW')
    exchange_rate = ex_df['Close'].iloc[-1].item()
except Exception: pass

buy_signals = []
sell_signals = []
skipped_signals = [] # 리스크 한도 초과로 매수를 보류한 기록

# 🌟 [핵심 추가] 자산별 섹터 판별기
def get_sector(ticker):
    if ticker == 'GLD': return 'Gold'
    elif ticker == 'TLT': return 'Bond'
    elif ticker == 'DBC': return 'Commodity'
    elif ticker == 'VNQ': return 'Real_Estate'
    else: return 'Stock' # QQQ, SPY 및 모든 개별 주식은 'Stock'으로 묶음

# ==========================================
# 2. 명단 수집 
# ==========================================
all_stocks = {
    'QQQ': 'Invesco QQQ (나스닥 기술주)',
    'SPY': 'SPDR S&P 500 ETF (미국 대형주)',
    'GLD': 'SPDR Gold Shares (금 실물)',
    'TLT': 'iShares 20+ Year Treasury Bond (미국 장기채)',
    'DBC': 'Invesco DB Commodity Index (원자재 묶음)',
    'VNQ': 'Vanguard Real Estate ETF (미국 부동산 리츠)'
}
try:
    kr_df = pd.read_csv('kospi_list.csv')
    for _, row in kr_df.iterrows():
        all_stocks[str(row.iloc[0]).replace('.0', '').strip().zfill(6) + '.KS'] = str(row.iloc[1])
except Exception: pass

try:
    us_df = fdr.StockListing('SP500')
    col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
    col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
    for _, row in us_df.iterrows():
        sym = str(row[col_sym])
        if sym not in all_stocks: all_stocks[sym] = str(row[col_name])
except Exception: pass

# ==========================================
# 3. 현재 포트폴리오 리스크(Heat) 계산
# ==========================================
current_total_units = sum(pos['units'] for pos in portfolio.values())
current_sector_units = {'Stock': 0, 'Gold': 0, 'Bond': 0, 'Commodity': 0, 'Real_Estate': 0}
for t, pos in portfolio.items():
    current_sector_units[get_sector(t)] += pos['units']

# ==========================================
# 4. 데이터 검증 및 터틀 로직 처리
# ==========================================
for ticker, name in all_stocks.items():
    try:
        stock_data = yf.download(ticker, period='1y', progress=False)
        if len(stock_data) < 200: continue
            
        current_price = stock_data['Close'].iloc[-1].item()
        
        high_low = stock_data['High'] - stock_data['Low']
        high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
        low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        N = tr.rolling(window=20).mean().iloc[-1].item()
        
        is_krw = ticker.endswith('.KS')
        N_krw = N if is_krw else N * exchange_rate
        unit_size = math.floor(RISK_AMOUNT / N_krw)
        unit_size = 1 if unit_size == 0 else unit_size

        if is_krw: chart_link = f"https://finance.naver.com/item/fchart.naver?code={ticker.replace('.KS', '')}"
        else: chart_link = f"https://finance.yahoo.com/quote/{ticker}/chart"

        sector = get_sector(ticker)

        # ------------------------------------------------
        # 📂 A. 이미 장부에 있는 자산 (청산 & 불타기)
        # ------------------------------------------------
        if ticker in portfolio:
            pos = portfolio[ticker]
            low_10 = stock_data['Low'].iloc[-11:-1].min().item()
            
            # 청산 로직
            if current_price <= pos['stop_loss'] or current_price <= low_10:
                sell_signals.append(f"- [{name}] 전량 청산 (현재: {current_price:.2f}) [📊 차트 보기]({chart_link})")
                current_total_units -= pos['units']
                current_sector_units[sector] -= pos['units']
                del portfolio[ticker] 
                continue
                
            # 불타기 로직 (리스크 한도 검사 포함)
            if pos['units'] < 4 and current_price >= pos['last_buy_price'] + (0.5 * N):
                if current_total_units + 1 > MAX_TOTAL_UNITS:
                    skipped_signals.append(f"- [{name}] ⚠️ 총 Unit({MAX_TOTAL_UNITS}) 초과로 불타기 보류")
                elif current_sector_units[sector] + 1 > MAX_SECTOR_UNITS:
                    skipped_signals.append(f"- [{name}] ⚠️ {sector} 섹터 Unit({MAX_SECTOR_UNITS}) 초과로 불타기 보류")
                else:
                    pos['units'] += 1
                    pos['last_buy_price'] = current_price
                    pos['stop_loss'] = current_price - (2 * N)
                    current_total_units += 1
                    current_sector_units[sector] += 1
                    buy_signals.append(f"- [{name}] 🔥 {pos['units']}차 불타기: 1Unit 추가 매수 (손절가: {pos['stop_loss']:.2f}) [📊 차트 보기]({chart_link})")

        # ------------------------------------------------
        # 📂 B. 장부에 없는 자산 (신규 진입)
        # ------------------------------------------------
        else:
            if current_price < stock_data['Close'].rolling(window=200).mean().iloc[-1].item(): continue
            turnover_krw = (current_price * stock_data['Volume'].iloc[-1].item()) if is_krw else (current_price * stock_data['Volume'].iloc[-1].item() * exchange_rate)
            if turnover_krw < MIN_TURNOVER_KRW: continue
            if (N / current_price) * 100 < MIN_VOLATILITY_RATIO: continue
            
            if current_price >= stock_data['High'].iloc[-21:-1].max().item():
                # 신규 진입 시 리스크 한도 검사
                if current_total_units + 1 > MAX_TOTAL_UNITS:
                    skipped_signals.append(f"- [{name}] ⚠️ 총 Unit({MAX_TOTAL_UNITS}) 초과로 신규 매수 보류")
                elif current_sector_units[sector] + 1 > MAX_SECTOR_UNITS:
                    skipped_signals.append(f"- [{name}] ⚠️ {sector} 섹터 Unit({MAX_SECTOR_UNITS}) 초과로 신규 매수 보류")
                else:
                    stop_loss_price = current_price - (2 * N)
                    portfolio[ticker] = {'name': name, 'units': 1, 'last_buy_price': current_price, 'stop_loss': stop_loss_price}
                    current_total_units += 1
                    current_sector_units[sector] += 1
                    buy_signals.append(f"- [{name}] ✨ 신규 1차 진입: {unit_size}주 매수 (손절가: {stop_loss_price:.2f}) [📊 차트 보기]({chart_link})")

    except Exception: pass
    time.sleep(0.3)

with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f:
    json.dump(portfolio, f, indent=4, ensure_ascii=False)

# ==========================================
# 5. 브리핑 작성 및 전송
# ==========================================
print(f"\n✅ 검사 완료! (매수: {len(buy_signals)}건, 청산: {len(sell_signals)}건, 보류: {len(skipped_signals)}건)")

if buy_signals or sell_signals or skipped_signals:
    buy_text = '\n'.join(buy_signals[:10]) if buy_signals else '신호 없음'
    sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '신호 없음'
    skip_text = '\n'.join(skipped_signals[:5]) if skipped_signals else '보류 없음'

    prompt = f"""
    아래는 리스크 한도(Sector Cap)가 탑재된 터틀 봇 v7.2의 결과입니다.
    
    [신규 진입 및 불타기]
    {buy_text}
    
    [청산 및 손절]
    {sell_text}
    
    [리스크 한도 초과로 매수 보류된 종목]
    {skip_text}
    
    위 데이터를 바탕으로 객관적이고 논리적인 퀀트 브리핑 문서를 작성하십시오. 마크다운 링크 [📊 차트 보기](URL)는 원본 그대로 복사하십시오.
    """
    
    response_text = ""
    for _ in range(3):
        try:
            response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
            response_text = response.text 
            break 
        except Exception: time.sleep(5)
            
    if not response_text: response_text = f"**원본 데이터**\n\n**매수**\n{buy_text}\n\n**청산**\n{sell_text}\n\n**보류**\n{skip_text}"
    
    final_content = f"🛡️ **철벽 방어 터틀 봇 v7.2 리포트** 🛡️\n{response_text}"
    if len(final_content) > 1900: final_content = final_content[:1900] + "\n\n... (⚠️ 신호 초과로 요약됨)"
    requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content})
else:
    requests.post(DISCORD_WEBHOOK_URL, json={"content": f"🛡️ **철벽 방어 터틀 봇 v7.2 리포트** 🛡️\n현재 계좌 총 {current_total_units}/{MAX_TOTAL_UNITS} Units 가동 중. 새로운 진입/청산 신호는 없습니다."})
