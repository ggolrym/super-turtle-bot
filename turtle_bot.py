# ==========================================
# 🐢 AI 멀티 에셋 터틀 봇 v8.0 (한국투자증권 모의투자 자동매매 탑재)
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

# 🌟 1. 환경 변수 로드 (API 키 및 시크릿)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
KIS_APP_KEY = os.environ.get("KIS_APP_KEY")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")
KIS_ACCOUNT = os.environ.get("KIS_ACCOUNT")

if not all([GEMINI_API_KEY, DISCORD_WEBHOOK_URL, KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT]):
    print("🚨 API 키 또는 깃허브 시크릿이 누락되었습니다! (증권사 키 확인 필수)")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

# 🌟 2. 한국투자증권 API 통신 설정 (모의투자 서버)
KIS_URL = "https://openapivts.koreainvestment.com:29443" # 모의투자 전용 도메인

def get_kis_token():
    """한국투자증권 서버에서 암호화 토큰 발급"""
    url = f"{KIS_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET
    }
    res = requests.post(url, headers=headers, data=json.dumps(body))
    if res.status_code == 200:
        return res.json().get("access_token")
    else:
        print(f"🚨 KIS 토큰 발급 실패: {res.text}")
        return None

# 글로벌 토큰 발급
kis_token = get_kis_token()
print("✅ 한국투자증권 API 통신 토큰 발급 완료!" if kis_token else "❌ 토큰 발급 실패. 자동매매 기능이 중지됩니다.")

def execute_order(ticker, qty, side="BUY"):
    """증권사 서버로 실제 매수/매도 주문을 쏘는 핵심 엔진"""
    if not kis_token: return "❌ 토큰 없음"
    
    is_krw = ticker.endswith('.KS')
    clean_ticker = ticker.replace('.KS', '')
    
    # 한국 주식과 해외 주식의 주문 TR_ID 및 URL 분기 처리
    if is_krw:
        url = f"{KIS_URL}/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = "VTTC0802U" if side == "BUY" else "VTTC0801U" # 모의투자 국내 매수/매도
    else:
        url = f"{KIS_URL}/uapi/overseas-stock/v1/trading/order"
        tr_id = "VTTT1002U" if side == "BUY" else "VTTT1006U" # 모의투자 해외 매수/매도 (시장가)

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {kis_token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": tr_id
    }
    
    # 01: 시장가 주문 (국내/해외 동일)
    body = {
        "CANO": KIS_ACCOUNT[:8],
        "ACNT_PRDT_CD": KIS_ACCOUNT[8:10] if len(KIS_ACCOUNT) >= 10 else "01",
        "PDNO": clean_ticker,
        "ORD_QTY": str(int(qty)),
        "ORD_DVSN": "01" if is_krw else "00", # 한국 시장가 01, 미국 시장가 00 (증권사 정책에 따라 다를 수 있음)
        "ORD_UNPR": "0" 
    }
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body))
        data = res.json()
        if data.get("rt_cd") == "0":
            return "✅ 주문 성공"
        else:
            return f"❌ 주문 실패 ({data.get('msg1')})"
    except Exception as e:
        return f"❌ 네트워크 에러 ({e})"

# ==========================================
# 3. 자본 및 리스크 설정
# ==========================================
TOTAL_CAPITAL = 5000000     
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
MIN_TURNOVER_KRW = 10000000000 
MIN_VOLATILITY_RATIO = 1.5 
PORTFOLIO_FILE = 'portfolio.json' 
MAX_TOTAL_UNITS = 12       
MAX_SECTOR_UNITS = 6       

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
skipped_signals = [] 

def get_sector(ticker):
    if ticker == 'GLD': return 'Gold'
    elif ticker == 'TLT': return 'Bond'
    elif ticker == 'DBC': return 'Commodity'
    elif ticker == 'VNQ': return 'Real_Estate'
    else: return 'Stock'

# 명단 수집 
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

current_total_units = sum(pos['units'] for pos in portfolio.values())
current_sector_units = {'Stock': 0, 'Gold': 0, 'Bond': 0, 'Commodity': 0, 'Real_Estate': 0}
for t, pos in portfolio.items():
    current_sector_units[get_sector(t)] += pos['units']

print(f"\n🤖 총 {len(all_stocks)}개 자산 정밀 검사 시작!\n")

# ==========================================
# 4. 데이터 검증 및 실제 API 주문 집행
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
        # 📂 A. 청산 및 불타기 (실제 API 매도/매수)
        # ------------------------------------------------
        if ticker in portfolio:
            pos = portfolio[ticker]
            low_10 = stock_data['Low'].iloc[-11:-1].min().item()
            
            # 청산 로직 (API 시장가 매도)
            if current_price <= pos['stop_loss'] or current_price <= low_10:
                order_res = execute_order(ticker, pos['units'], side="SELL") # 🚀 증권사 매도 주문
                sell_signals.append(f"- [{name}] 전량 청산 ({pos['units']}주) ➞ {order_res} [📊 차트]({chart_link})")
                current_total_units -= pos['units']
                current_sector_units[sector] -= pos['units']
                del portfolio[ticker] 
                continue
                
            # 불타기 로직 (API 시장가 매수)
            if pos['units'] < 4 and current_price >= pos['last_buy_price'] + (0.5 * N):
                if current_total_units + 1 > MAX_TOTAL_UNITS:
                    skipped_signals.append(f"- [{name}] ⚠️ 총 Unit({MAX_TOTAL_UNITS}) 초과로 불타기 보류")
                elif current_sector_units[sector] + 1 > MAX_SECTOR_UNITS:
                    skipped_signals.append(f"- [{name}] ⚠️ {sector} 섹터 초과로 불타기 보류")
                else:
                    order_res = execute_order(ticker, unit_size, side="BUY") # 🚀 증권사 매수 주문
                    pos['units'] += unit_size
                    pos['last_buy_price'] = current_price
                    pos['stop_loss'] = current_price - (2 * N)
                    current_total_units += 1
                    current_sector_units[sector] += 1
                    buy_signals.append(f"- [{name}] 🔥 {pos['units']}차 불타기 ({unit_size}주) ➞ {order_res} [📊 차트]({chart_link})")

        # ------------------------------------------------
        # 📂 B. 신규 진입 (실제 API 매수)
        # ------------------------------------------------
        else:
            if current_price < stock_data['Close'].rolling(window=200).mean().iloc[-1].item(): continue
            turnover_krw = (current_price * stock_data['Volume'].iloc[-1].item()) if is_krw else (current_price * stock_data['Volume'].iloc[-1].item() * exchange_rate)
            if turnover_krw < MIN_TURNOVER_KRW: continue
            if (N / current_price) * 100 < MIN_VOLATILITY_RATIO: continue
            
            if current_price >= stock_data['High'].iloc[-21:-1].max().item():
                if current_total_units + 1 > MAX_TOTAL_UNITS:
                    skipped_signals.append(f"- [{name}] ⚠️ 총 Unit({MAX_TOTAL_UNITS}) 초과로 신규 매수 보류")
                elif current_sector_units[sector] + 1 > MAX_SECTOR_UNITS:
                    skipped_signals.append(f"- [{name}] ⚠️ {sector} 섹터 초과로 신규 매수 보류")
                else:
                    order_res = execute_order(ticker, unit_size, side="BUY") # 🚀 증권사 매수 주문
                    stop_loss_price = current_price - (2 * N)
                    portfolio[ticker] = {'name': name, 'units': unit_size, 'last_buy_price': current_price, 'stop_loss': stop_loss_price}
                    current_total_units += 1
                    current_sector_units[sector] += 1
                    buy_signals.append(f"- [{name}] ✨ 신규 1차 진입 ({unit_size}주) ➞ {order_res} [📊 차트]({chart_link})")

    except Exception: pass
    time.sleep(0.3)

with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f:
    json.dump(portfolio, f, indent=4, ensure_ascii=False)

# ==========================================
# 5. 브리핑 작성 및 전송
# ==========================================
if buy_signals or sell_signals or skipped_signals:
    buy_text = '\n'.join(buy_signals[:10]) if buy_signals else '신호 없음'
    sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '신호 없음'
    skip_text = '\n'.join(skipped_signals[:5]) if skipped_signals else '보류 없음'

    prompt = f"""
    아래는 증권사 API 자동 매매가 연동된 터틀 봇 v8.0의 실제 주문 집행 결과입니다.
    
    [신규 진입 및 불타기 내역]
    {buy_text}
    
    [청산 및 손절 내역]
    {sell_text}
    
    [리스크 한도 초과로 진입 포기]
    {skip_text}
    
    위 데이터를 바탕으로 간결하고 전문적인 트레이딩 브리핑을 작성하십시오. API 주문 성공/실패 여부를 명확히 강조하십시오. 마크다운 링크는 그대로 유지하십시오.
    """
    
    response_text = ""
    for _ in range(3):
        try:
            response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
            response_text = response.text 
            break 
        except Exception: time.sleep(5)
            
    if not response_text: response_text = f"**원본 데이터**\n\n**매수**\n{buy_text}\n\n**청산**\n{sell_text}"
    
    final_content = f"🤖 **무인 퀀트 자동매매 v8.0 결산 (모의투자)** 🤖\n{response_text}"
    if len(final_content) > 1900: final_content = final_content[:1900] + "\n\n... (⚠️ 내용 요약됨)"
    requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content})
else:
    requests.post(DISCORD_WEBHOOK_URL, json={"content": f"🤖 **무인 퀀트 자동매매 v8.0 가동 중 (모의투자)** 🤖\n현재 계좌 리스크 {current_total_units}/{MAX_TOTAL_UNITS} Units. 오늘 증권사 서버로 발송된 신규 주문은 없습니다."})
