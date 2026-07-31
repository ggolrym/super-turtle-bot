# ==========================================
# 🐢 AI 멀티 에셋 터틀 봇 v9.7 (대시보드 + 구글 DB 락 회피 적용판)
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
from datetime import datetime
import pytz

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
KIS_APP_KEY = os.environ.get("KIS_APP_KEY")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")
KIS_ACCOUNT = os.environ.get("KIS_ACCOUNT")
SHEET_WEBHOOK_URL = os.environ.get("SHEET_WEBHOOK_URL") 

if not all([GEMINI_API_KEY, DISCORD_WEBHOOK_URL, KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT]):
    print("🚨 API 키 또는 깃허브 시크릿 누락!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)
KIS_URL = "https://openapivts.koreainvestment.com:29443" 

def get_kis_token():
    url = f"{KIS_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        return res.json().get("access_token") if res.status_code == 200 else None
    except Exception as e:
        return None

kis_token = get_kis_token()

def execute_order(ticker, qty, side="BUY", price=0.0):
    if not kis_token: return {"success": False, "msg": "토큰 없음"}
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
        url = f"{KIS_URL}/uapi/domestic-stock/v1/trading/order-cash"
        headers["tr_id"] = "VTTC0802U" if side == "BUY" else "VTTC0801U"
        body = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), "ORD_DVSN": "01", "ORD_UNPR": "0"}
    else:
        url = f"{KIS_URL}/uapi/overseas-stock/v1/trading/order"
        headers["tr_id"] = "VTTT1002U" if side == "BUY" else "VTTT1006U"
        excg_cd = 'AMS' if clean_ticker in ['SPLG', 'SPY', 'GLDM', 'GLD', 'TLT', 'DBC', 'VNQ', 'SH', 'PSQ'] else 'NAS'
        target_price = price * 1.01 if side == "BUY" else price * 0.99
        body = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "OVRS_EXCG_CD": excg_cd, "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), "OVRS_ORD_UNPR": str(round(target_price, 2)), "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"}
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        data = res.json()
        if data.get("rt_cd") == "0": return {"success": True, "msg": "✅ 체결"}
        else: return {"success": False, "msg": f"❌ 거절({data.get('msg1')})"}
    except Exception as e: return {"success": False, "msg": f"❌ 에러"}

TOTAL_CAPITAL = 500000 
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
MIN_TURNOVER_KRW = 5000000000
MAX_POSITION_KRW = 100000     
MAX_POSITIONS = 10          
MAX_SECTOR_POSITIONS = 5       

# 🌟 락(Lock) 회피 1단계: 깃허브 파일(portfolio.json) 대신 구글 시트에서 장부 읽기
portfolio = {}
print("구글 시트(DB)에서 포트폴리오를 불러옵니다...")
if SHEET_WEBHOOK_URL:
    try:
        res = requests.get(SHEET_WEBHOOK_URL, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict):
                portfolio = data
            else:
                print("DB 데이터 형식이 잘못되었습니다. 빈 장부로 시작합니다.")
    except Exception as e:
        print(f"장부 불러오기 실패 (빈 장부로 시작): {e}")

exchange_rate = 1350.0
try:
    ex_df = fdr.DataReader('USD/KRW')
    if not ex_df.empty: exchange_rate = float(ex_df['Close'].iloc[-1])
except Exception: pass

buy_signals, sell_signals, skipped_signals = [], [], []
dashboard_list = [] 

def get_sector(ticker):
    if ticker == 'GLDM': return 'Gold'
    elif ticker == 'DBC': return 'Commodity'
    elif ticker in ['SH', 'PSQ']: return 'Inverse' 
    return 'Stock'

all_stocks = {'SPLG': 'SPDR 미니 S&P500', 'GLDM': 'SPDR 미니 금', 'DBC': 'Invesco 원자재', 'SH': 'S&P500 인버스', 'PSQ': '나스닥 인버스'}

current_positions = len(portfolio)
current_sector_positions = {'Stock': 0, 'Gold': 0, 'Commodity': 0, 'Inverse': 0}
for t in portfolio.keys(): 
    if get_sector(t) in current_sector_positions: current_sector_positions[get_sector(t)] += 1

if kis_token: 
    for ticker, name in all_stocks.items():
        try:
            stock_data = yf.download(ticker, period='2y', progress=False)
            if isinstance(stock_data.columns, pd.MultiIndex): stock_data.columns = stock_data.columns.get_level_values(0)
            stock_data = stock_data.dropna()
            
            if len(stock_data) < 200: continue
                
            current_price = float(stock_data['Close'].iloc[-1])
            is_krw = ticker.endswith('.KS')
            current_price_krw = current_price if is_krw else current_price * exchange_rate
            if current_price_krw > MAX_POSITION_KRW: continue
            
            high_low = stock_data['High'] - stock_data['Low']
            high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
            low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            N = float(tr.rolling(window=20).mean().iloc[-1])
            if pd.isna(N) or N <= 0: continue
            
            low_10 = float(stock_data['Low'].iloc[-11:-1].min())
            
            N_krw = N if is_krw else N * exchange_rate
            unit_size = math.floor(RISK_AMOUNT / N_krw)
            unit_size = 1 if unit_size == 0 else unit_size
            if unit_size * current_price_krw > MAX_POSITION_KRW: unit_size = math.floor(MAX_POSITION_KRW / current_price_krw)
            if unit_size == 0: continue 

            sector = get_sector(ticker)

            if ticker in portfolio:
                pos = portfolio[ticker]
                if current_price <= pos['stop_loss'] or current_price <= low_10:
                    order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                    sell_signals.append(f"- [{name}] 청산 ➞ {order_res['msg']}")
                    if order_res['success']:
                        current_positions -= 1
                        current_sector_positions[sector] -= 1
                        del portfolio[ticker] 
                else:
                    chunks = pos.get('chunks', 1)
                    if chunks < 4 and current_price >= pos['last_buy_price'] + (0.5 * N):
                        order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                        buy_signals.append(f"- [{name}] {chunks+1}차 불타기 ➞ {order_res['msg']}")
                        if order_res['success']:
                            pos['units'] += unit_size; pos['chunks'] = chunks + 1; pos['last_buy_price'] = current_price; pos['stop_loss'] = current_price - (2 * N)

            elif ticker not in portfolio:
                turnover_krw = (current_price * float(stock_data['Volume'].iloc[-21:-1].mean())) * (1 if is_krw else exchange_rate)
                if turnover_krw < MIN_TURNOVER_KRW: continue
                volatility_ratio = (N / current_price) * 100
                is_above_200 = current_price >= float(stock_data['Close'].rolling(window=200).mean().iloc[-1])
                is_above_120 = current_price >= float(stock_data['Close'].rolling(window=120).mean().iloc[-1]) 
                is_above_60 = current_price >= float(stock_data['Close'].rolling(window=60).mean().iloc[-1])   
                
                if sector == 'Stock' and (not is_above_120 or volatility_ratio < 1.0): continue 
                elif sector == 'Inverse' and (not is_above_60 or volatility_ratio < 0.5): continue
                elif sector not in ['Stock', 'Inverse'] and (not is_above_200 or volatility_ratio < 0.5): continue

                if current_price >= float(stock_data['High'].iloc[-21:-1].max()):
                    if current_positions + 1 <= MAX_POSITIONS and current_sector_positions[sector] + 1 <= MAX_SECTOR_POSITIONS:
                        order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                        buy_signals.append(f"- [{name}] 신규 진입 ➞ {order_res['msg']}")
                        if order_res['success']:
                            portfolio[ticker] = {'name': name, 'units': unit_size, 'chunks': 1, 'last_buy_price': current_price, 'stop_loss': current_price - (2 * N)}
                            current_positions += 1
                            current_sector_positions[sector] += 1

            if ticker in portfolio:
                pos = portfolio[ticker]
                dashboard_list.append({
                    "name": name,
                    "units": pos['units'],
                    "current_price": round(current_price, 2),
                    "buy_price": round(pos['last_buy_price'], 2),
                    "stop_loss": round(pos['stop_loss'], 2),
                    "trailing_stop": round(low_10, 2)
                })
        except Exception: continue
        time.sleep(0.15)

# (삭제됨) with open(PORTFOLIO_FILE, 'w' ... 로컬 저장 로직 완전 제거

if not kis_token: final_content = "🚨 **터틀 펀드 시스템 경보** 🚨\nAPI 접속 실패로 스캔을 보류합니다."
else:
    buy_text = '\n'.join(buy_signals[:10]) if buy_signals else '신호 없음'
    sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '신호 없음'
    if buy_signals or sell_signals:
        prompt = f"봇 체결결과 요약해라. 매수:{buy_text} 청산:{sell_text}"
        res_text = ""
        try: res_text = client.models.generate_content(model='gemini-2.0-flash', contents=prompt).text
        except: res_text = f"매수:\n{buy_text}\n청산:\n{sell_text}"
        final_content = f"🤖 **터틀 펀드 v9.7** 🤖\n{res_text}"
    else: final_content = f"🤖 **터틀 펀드 v9.7** 🤖\n보유 종목 {current_positions}/{MAX_POSITIONS} 개. 시장 관망 중."

requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content[:1900]})

# 🌟 락(Lock) 회피 2단계: 구글 시트로 대시보드와 함께 장부(portfolio) 덮어쓰기
if SHEET_WEBHOOK_URL:
    sheet_data = {
        "date": datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S'),
        "message": f"매수 {len(buy_signals)}건, 청산 {len(sell_signals)}건" if (buy_signals or sell_signals) else "특이사항 없음",
        "dashboard": dashboard_list,
        "portfolio": portfolio # 🌟 깃허브 파일 변조 없이 구글 DB에 저장
    }
    try: requests.post(SHEET_WEBHOOK_URL, json=sheet_data, timeout=10)
    except Exception as e: print(f"구글 시트 저장 실패: {e}")
