# ==========================================
# 🐢 AI 멀티 에셋 터틀 봇 v8.1 (한국투자증권 글로벌 주문 패치)
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
KIS_APP_KEY = os.environ.get("KIS_APP_KEY")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")
KIS_ACCOUNT = os.environ.get("KIS_ACCOUNT")

if not all([GEMINI_API_KEY, DISCORD_WEBHOOK_URL, KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT]):
    print("🚨 API 키 또는 깃허브 시크릿 누락!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)
KIS_URL = "https://openapivts.koreainvestment.com:29443" 

def get_kis_token():
    url = f"{KIS_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    res = requests.post(url, headers=headers, data=json.dumps(body))
    return res.json().get("access_token") if res.status_code == 200 else None

kis_token = get_kis_token()
print("✅ KIS 토큰 발급 완료!" if kis_token else "❌ 토큰 발급 실패.")

# 🌟 [수정됨] 가격(price) 파라미터 추가 및 해외 거래소 자동 식별 로직 탑재
def execute_order(ticker, qty, side="BUY", price=0.0):
    if not kis_token: return "❌ 토큰 없음"
    
    is_krw = ticker.endswith('.KS')
    clean_ticker = ticker.replace('.KS', '')
    clean_account = KIS_ACCOUNT.replace("-", "").strip()
    cano = clean_account[:8]
    prdt_cd = clean_account[8:10] if len(clean_account) >= 10 else "01"
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {kis_token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET
    }
    
    if is_krw:
        # 국내 주식 주문 양식
        url = f"{KIS_URL}/uapi/domestic-stock/v1/trading/order-cash"
        headers["tr_id"] = "VTTC0802U" if side == "BUY" else "VTTC0801U"
        body = {
            "CANO": cano, "ACNT_PRDT_CD": prdt_cd, "PDNO": clean_ticker,
            "ORD_QTY": str(int(qty)), "ORD_DVSN": "01", "ORD_UNPR": "0" 
        }
    else:
        # 해외 주식 주문 양식
        url = f"{KIS_URL}/uapi/overseas-stock/v1/trading/order"
        headers["tr_id"] = "VTTT1002U" if side == "BUY" else "VTTT1006U"
        
        # 야후 파이낸스에서 실시간으로 소속 거래소 판독
        try:
            ex_info = yf.Ticker(clean_ticker).info.get('exchange', 'NYQ').upper()
            if 'NAS' in ex_info or 'NMS' in ex_info: excg_cd = 'NAS'
            elif 'PCX' in ex_info or 'ARCA' in ex_info or 'BATS' in ex_info or 'AMEX' in ex_info: excg_cd = 'AMS'
            else: excg_cd = 'NYS'
        except:
            excg_cd = 'NYS'
            
        body = {
            "CANO": cano, "ACNT_PRDT_CD": prdt_cd, 
            "OVRS_EXCG_CD": excg_cd,  # 추출한 거래소 코드 입력
            "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), 
            "OVRS_ORD_UNPR": str(round(price, 2)), # 지정가(현재가) 세팅
            "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"
        }
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body))
        data = res.json()
        if data.get("rt_cd") == "0": return "✅ 주문 성공"
        else: return f"❌ 실패({data.get('msg1')})"
    except Exception as e: return f"❌ 네트워크 에러"

# ==========================================
# 3. 리스크 및 포트폴리오 세팅
# ==========================================
TOTAL_CAPITAL = 500000
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
MIN_TURNOVER_KRW = 10000000000 
MIN_VOLATILITY_RATIO = 1.5 
PORTFOLIO_FILE = 'portfolio.json' 
MAX_TOTAL_UNITS = 12       
MAX_SECTOR_UNITS = 6       

if os.path.exists(PORTFOLIO_FILE):
    with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f: portfolio = json.load(f)
else: portfolio = {}

exchange_rate = 1350
try:
    ex_df = fdr.DataReader('USD/KRW')
    exchange_rate = ex_df['Close'].iloc[-1].item()
except Exception: pass

buy_signals, sell_signals, skipped_signals = [], [], []

def get_sector(ticker):
    if ticker == 'GLD': return 'Gold'
    elif ticker == 'TLT': return 'Bond'
    elif ticker == 'DBC': return 'Commodity'
    elif ticker == 'VNQ': return 'Real_Estate'
    else: return 'Stock'

all_stocks = {
    'QQQ': 'Invesco QQQ (나스닥 기술주)', 'SPY': 'SPDR S&P 500 ETF (미국 대형주)',
    'GLD': 'SPDR Gold Shares (금 실물)', 'TLT': 'iShares 20+ Year Treasury Bond (미국 장기채)',
    'DBC': 'Invesco DB Commodity Index (원자재)', 'VNQ': 'Vanguard Real Estate ETF (미국 부동산)'
}
try:
    kr_df = pd.read_csv('kospi_list.csv')
    for _, row in kr_df.iterrows(): all_stocks[str(row.iloc[0]).replace('.0', '').strip().zfill(6) + '.KS'] = str(row.iloc[1])
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
for t, pos in portfolio.items(): current_sector_units[get_sector(t)] += pos['units']

print(f"\n🤖 총 {len(all_stocks)}개 자산 검사 시작!\n")

# ==========================================
# 4. 검사 및 주문 집행
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

        chart_link = f"https://finance.naver.com/item/fchart.naver?code={ticker.replace('.KS', '')}" if is_krw else f"https://finance.yahoo.com/quote/{ticker}/chart"
        sector = get_sector(ticker)

        # 📂 A. 기존 포지션 관리
        if ticker in portfolio:
            pos = portfolio[ticker]
            low_10 = stock_data['Low'].iloc[-11:-1].min().item()
            
            if current_price <= pos['stop_loss'] or current_price <= low_10:
                order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price) # 🌟 가격 전달
                sell_signals.append(f"- [{name}] 전량 청산 ({pos['units']}주) ➞ {order_res} [📊 차트]({chart_link})")
                current_total_units -= pos['units']
                current_sector_units[sector] -= pos['units']
                del portfolio[ticker] 
                continue
                
            if pos['units'] < 4 and current_price >= pos['last_buy_price'] + (0.5 * N):
                if current_total_units + 1 > MAX_TOTAL_UNITS: skipped_signals.append(f"- [{name}] 총 Unit 초과로 불타기 보류")
                elif current_sector_units[sector] + 1 > MAX_SECTOR_UNITS: skipped_signals.append(f"- [{name}] 섹터 초과로 불타기 보류")
                else:
                    order_res = execute_order(ticker, unit_size, side="BUY", price=current_price) # 🌟 가격 전달
                    pos['units'] += unit_size
                    pos['last_buy_price'] = current_price
                    pos['stop_loss'] = current_price - (2 * N)
                    current_total_units += 1
                    current_sector_units[sector] += 1
                    buy_signals.append(f"- [{name}] 🔥 {pos['units']}차 불타기 ({unit_size}주) ➞ {order_res} [📊 차트]({chart_link})")

        # 📂 B. 신규 진입
        else:
            if current_price < stock_data['Close'].rolling(window=200).mean().iloc[-1].item(): continue
            turnover_krw = (current_price * stock_data['Volume'].iloc[-1].item()) if is_krw else (current_price * stock_data['Volume'].iloc[-1].item() * exchange_rate)
            if turnover_krw < MIN_TURNOVER_KRW: continue
            if (N / current_price) * 100 < MIN_VOLATILITY_RATIO: continue
            
            if current_price >= stock_data['High'].iloc[-21:-1].max().item():
                if current_total_units + 1 > MAX_TOTAL_UNITS: skipped_signals.append(f"- [{name}] 총 Unit 초과로 신규 매수 보류")
                elif current_sector_units[sector] + 1 > MAX_SECTOR_UNITS: skipped_signals.append(f"- [{name}] 섹터 초과로 신규 매수 보류")
                else:
                    order_res = execute_order(ticker, unit_size, side="BUY", price=current_price) # 🌟 가격 전달
                    stop_loss_price = current_price - (2 * N)
                    portfolio[ticker] = {'name': name, 'units': unit_size, 'last_buy_price': current_price, 'stop_loss': stop_loss_price}
                    current_total_units += 1
                    current_sector_units[sector] += 1
                    buy_signals.append(f"- [{name}] ✨ 신규 1차 진입 ({unit_size}주) ➞ {order_res} [📊 차트]({chart_link})")

    except Exception: pass
    time.sleep(0.3)

with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f: json.dump(portfolio, f, indent=4, ensure_ascii=False)

# ==========================================
# 5. 브리핑 작성 및 전송
# ==========================================
if buy_signals or sell_signals or skipped_signals:
    buy_text = '\n'.join(buy_signals[:10]) if buy_signals else '신호 없음'
    sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '신호 없음'
    skip_text = '\n'.join(skipped_signals[:5]) if skipped_signals else '보류 없음'

    prompt = f"""
    아래는 증권사 API 자동 매매가 연동된 터틀 봇 v8.1의 주문 집행 결과입니다.
    
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
    
    final_content = f"🤖 **무인 퀀트 자동매매 v8.1 결산 (모의투자)** 🤖\n{response_text}"
    if len(final_content) > 1900: final_content = final_content[:1900] + "\n\n... (⚠️ 내용 요약됨)"
    requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content})
else:
    requests.post(DISCORD_WEBHOOK_URL, json={"content": f"🤖 **무인 퀀트 자동매매 v8.1 가동 중 (모의투자)** 🤖\n현재 계좌 리스크 {current_total_units}/{MAX_TOTAL_UNITS} Units. 오늘 발송된 주문은 없습니다."})
