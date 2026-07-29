# ==========================================
# 🐢 AI 멀티 에셋 터틀 봇 v9.4.4 (시뮬레이션 오버드라이브 - 무조건 매수 모드)
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
        print(f"🚨 KIS 토큰 에러: {e}")
        return None

kis_token = get_kis_token()
print("✅ KIS 토큰 발급 완료!" if kis_token else "❌ 토큰 발급 실패.")

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
        body = {
            "CANO": cano, "ACNT_PRDT_CD": prdt_cd, "PDNO": clean_ticker,
            "ORD_QTY": str(int(qty)), "ORD_DVSN": "01", "ORD_UNPR": "0" 
        }
    else:
        url = f"{KIS_URL}/uapi/overseas-stock/v1/trading/order"
        headers["tr_id"] = "VTTT1002U" if side == "BUY" else "VTTT1006U"
        try:
            ex_info = yf.Ticker(clean_ticker).info.get('exchange', 'NYQ').upper()
            if 'NAS' in ex_info or 'NMS' in ex_info: excg_cd = 'NAS'
            elif 'PCX' in ex_info or 'ARCA' in ex_info or 'BATS' in ex_info or 'AMEX' in ex_info: excg_cd = 'AMS'
            else: excg_cd = 'NYS'
        except: excg_cd = 'NYS'
            
        target_price = price * 1.01 if side == "BUY" else price * 0.99
            
        body = {
            "CANO": cano, "ACNT_PRDT_CD": prdt_cd, "OVRS_EXCG_CD": excg_cd, 
            "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), 
            "OVRS_ORD_UNPR": str(round(target_price, 2)), "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"
        }
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        data = res.json()
        if data.get("rt_cd") == "0": return {"success": True, "msg": "✅ 체결"}
        else: return {"success": False, "msg": f"❌ 거절({data.get('msg1')})"}
    except Exception as e: return {"success": False, "msg": f"❌ 에러({e})"}

# ==========================================
# 🌟 포트폴리오 세팅
# ==========================================
TOTAL_CAPITAL = 5000000     
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
MIN_TURNOVER_KRW = 50000000 # 5천만 원으로 하향
PORTFOLIO_FILE = 'portfolio.json' 
MAX_TOTAL_UNITS = 30       
MAX_SECTOR_UNITS = 15       

if os.path.exists(PORTFOLIO_FILE):
    with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f: portfolio = json.load(f)
else: portfolio = {}

exchange_rate = 1350
try:
    exchange_rate = float(fdr.DataReader('USD/KRW')['Close'].iloc[-1])
except: pass

buy_signals, sell_signals, skipped_signals = [], [], []

def get_sector(ticker):
    if ticker in ['SH', 'PSQ']: return 'Inverse' 
    return 'Stock'

all_stocks = {
    'QQQ': 'Invesco QQQ', 'SPY': 'SPDR S&P 500',
    'SH': 'ProShares Short S&P500', 'PSQ': 'ProShares Short QQQ'
}
try:
    kr_df = pd.read_csv('kospi_list.csv')
    for _, row in kr_df.iterrows(): all_stocks[str(row.iloc[0]).replace('.0', '').strip().zfill(6) + '.KS'] = str(row.iloc[1])
except: pass
try:
    us_df = fdr.StockListing('SP500')
    col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
    col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
    for _, row in us_df.iterrows(): all_stocks[str(row[col_sym])] = str(row[col_name])
except: pass

current_total_units = sum(pos['units'] for pos in portfolio.values())
current_sector_units = {'Stock': 0, 'Inverse': 0}
for t, pos in portfolio.items(): 
    sec = get_sector(t)
    if sec in current_sector_units: current_sector_units[sec] += pos['units']

print(f"\n🤖 총 {len(all_stocks)}개 자산 오버드라이브 스캔 시작 (v9.4.4)!\n")

# ==========================================
# 🌟 데이터 검증 및 극한 매수 집행
# ==========================================
error_count = 0 
if kis_token: 
    for ticker, name in all_stocks.items():
        if current_total_units >= MAX_TOTAL_UNITS: 
            print("🛑 포트폴리오 30개 한도 도달! 스캔을 조기 종료합니다.")
            break # 30개 꽉 차면 더 이상 무의미한 검사 중단

        try:
            # 데이터 로드 및 NaN(결측치) 완벽 제거
            stock_data = yf.download(ticker, period='3mo', progress=False)
            if isinstance(stock_data.columns, pd.MultiIndex):
                stock_data.columns = stock_data.columns.get_level_values(0)
            stock_data = stock_data.dropna() # 🌟 빈 데이터 싹둑
            
            if len(stock_data) < 10: continue
                
            current_price = float(stock_data['Close'].iloc[-1])
            yesterday_close = float(stock_data['Close'].iloc[-2]) # 어제 종가
            
            # ATR 계산
            high_low = stock_data['High'] - stock_data['Low']
            high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
            low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            N = float(tr.rolling(window=10).mean().iloc[-1])
            if pd.isna(N) or N <= 0: continue
            
            is_krw = ticker.endswith('.KS')
            N_krw = N if is_krw else N * exchange_rate
            unit_size = math.floor(RISK_AMOUNT / N_krw)
            unit_size = 1 if unit_size == 0 else unit_size
            chart_link = f"https://finance.naver.com/item/fchart.naver?code={ticker.replace('.KS', '')}" if is_krw else f"https://finance.yahoo.com/quote/{ticker}/chart"
            sector = get_sector(ticker)

            # 📂 A. 기존 포지션 관리
            if ticker in portfolio:
                pos = portfolio[ticker]
                # 🌟 [오버드라이브] 수익실현/손절 기준 빡빡하게 (어제 종가보다 2% 떨어지면 무조건 던짐)
                if current_price <= pos['stop_loss'] or current_price < yesterday_close * 0.98:
                    order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                    sell_signals.append(f"- [{name}] 쾌속 청산 ➞ {order_res['msg']}")
                    if order_res['success']:
                        current_total_units -= pos['units']
                        del portfolio[ticker] 
                    continue
                    
            # 📂 B. 신규 진입 (무조건 매수 로직)
            else:
                # 🌟 [오버드라이브 방아쇠] "5일선 위에 있고, 어제보다 1원이라도 올랐으면 무조건 산다!"
                is_above_5 = current_price >= float(stock_data['Close'].rolling(window=5).mean().iloc[-1])
                is_green_today = current_price > yesterday_close
                
                if is_above_5 and is_green_today:
                    if current_total_units + 1 > MAX_TOTAL_UNITS: pass
                    else:
                        order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                        buy_signals.append(f"- [{name}] 🚀 오버드라이브 진입 ({unit_size}주) ➞ {order_res['msg']} [📊 차트]({chart_link})")
                        
                        if order_res['success']:
                            portfolio[ticker] = {'name': name, 'units': unit_size, 'last_buy_price': current_price, 'stop_loss': current_price - (2 * N)}
                            current_total_units += 1

        except Exception as e: 
            error_count += 1
            if error_count <= 2: print(f"⚠️ [{ticker}] 에러: {e}")
            continue
        time.sleep(0.1)

with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f: json.dump(portfolio, f, indent=4, ensure_ascii=False)

# ==========================================
# 🌟 브리핑 전송
# ==========================================
buy_text = '\n'.join(buy_signals[:30]) if buy_signals else '신호 없음'
sell_text = '\n'.join(sell_signals[:30]) if sell_signals else '신호 없음'

if buy_signals or sell_signals:
    final_content = f"🤖 **터틀 펀드 v9.4.4 (오버드라이브 모드)** 🤖\n\n**[🚀 폭주 매수]**\n{buy_text}\n\n**[💥 쾌속 청산]**\n{sell_text}"
else:
    final_content = f"🤖 **터틀 펀드 v9.4.4 가동 중** 🤖\n조건을 최하로 낮췄음에도 오늘 시장에 오르는 주식이 전멸했습니다."

if len(final_content) > 1900: final_content = final_content[:1900] + "\n\n... (⚠️ 30종목 달성으로 내용 요약됨)"
requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content})

if SHEET_WEBHOOK_URL:
    kr_time = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    requests.post(SHEET_WEBHOOK_URL, json={
        "date": kr_time, "total_units": f"{current_total_units} / {MAX_TOTAL_UNITS}",
        "buys": len(buy_signals), "sells": len(sell_signals),
        "message": f"매수 {len(buy_signals)}건 포착!" if buy_signals else "관망"
    }, timeout=5)
