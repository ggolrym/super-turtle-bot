# ==========================================
# 🐢 AI 멀티 에셋 터틀 봇 v9.5.2 (소액 오버드라이브 + 장부 강제 리셋 패치)
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
TOTAL_CAPITAL = 500000      # 💰 총 자본금 50만 원
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT

MIN_TURNOVER_KRW = 50000000 # 거래대금 5천만 원 이상
MAX_POSITION_KRW = 100000   # 한 종목 최대 10만 원 제한

PORTFOLIO_FILE = 'portfolio.json' 
MAX_POSITIONS = 10          # 최대 10개 종목
MAX_SECTOR_POSITIONS = 5       

# 🚨 [장부 강제 리셋 패치] 과거 파일 무시하고 무조건 빈 장부로 시작!
portfolio = {}

exchange_rate = 1350
try:
    exchange_rate = float(fdr.DataReader('USD/KRW')['Close'].iloc[-1])
except: pass

buy_signals, sell_signals, skipped_signals = [], [], []

def get_sector(ticker):
    if ticker == 'GLDM': return 'Gold'
    elif ticker == 'DBC': return 'Commodity'
    elif ticker in ['SH', 'PSQ']: return 'Inverse' 
    return 'Stock'

all_stocks = {
    'SPLG': 'SPDR Portfolio S&P 500 (미니 S&P500)', 
    'GLDM': 'SPDR Gold MiniShares (미니 금 실물)', 
    'DBC': 'Invesco DB Commodity Index (원자재)', 
    'SH': 'ProShares Short S&P500 (🔥 S&P500 인버스)', 
    'PSQ': 'ProShares Short QQQ (🔥 나스닥 인버스)' 
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

# 이제 portfolio는 무조건 {} 이므로 현재 보유량은 0에서 깔끔하게 출발합니다.
current_positions = len(portfolio)
current_sector_positions = {'Stock': 0, 'Gold': 0, 'Commodity': 0, 'Inverse': 0}

print(f"\n🤖 총 {len(all_stocks)}개 자산 소액 오버드라이브 스캔 시작 (v9.5.2 강제리셋)!\n")

# ==========================================
# 🌟 데이터 검증 및 묻지마 매수 집행
# ==========================================
error_count = 0 
if kis_token: 
    for ticker, name in all_stocks.items():
        if current_positions >= MAX_POSITIONS: 
            print("🛑 포트폴리오 10종목(소액 한도) 꽉 참! 스캔을 조기 종료합니다.")
            break 

        try:
            stock_data = yf.download(ticker, period='3mo', progress=False)
            if isinstance(stock_data.columns, pd.MultiIndex):
                stock_data.columns = stock_data.columns.get_level_values(0)
            stock_data = stock_data.dropna() 
            
            if len(stock_data) < 10: continue
                
            current_price = float(stock_data['Close'].iloc[-1])
            yesterday_close = float(stock_data['Close'].iloc[-2]) 
            
            is_krw = ticker.endswith('.KS')
            current_price_krw = current_price if is_krw else current_price * exchange_rate
            
            # 🚨 [소액 보호] 1주 가격이 10만 원을 넘으면 패스
            if current_price_krw > MAX_POSITION_KRW: continue
            
            high_low = stock_data['High'] - stock_data['Low']
            high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
            low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            N = float(tr.rolling(window=10).mean().iloc[-1])
            if pd.isna(N) or N <= 0: continue
            
            N_krw = N if is_krw else N * exchange_rate
            unit_size = math.floor(RISK_AMOUNT / N_krw)
            unit_size = 1 if unit_size == 0 else unit_size

            # 🚨 [오버사이징 방지] 10만 원 넘게 사지 않도록 수량 강제 조절
            if unit_size * current_price_krw > MAX_POSITION_KRW:
                unit_size = math.floor(MAX_POSITION_KRW / current_price_krw)
                if unit_size == 0: continue 

            chart_link = f"https://finance.naver.com/item/fchart.naver?code={ticker.replace('.KS', '')}" if is_krw else f"https://finance.yahoo.com/quote/{ticker}/chart"
            sector = get_sector(ticker)

            # 📂 A. 기존 포지션 관리 (초기화되어서 여긴 실행 안 됨)
            if ticker in portfolio:
                continue
                    
            # 📂 B. 신규 진입 (무조건 매수)
            else:
                # 🌟 "오늘 어제보다 1원이라도 올랐으면 무조건 줍는다!"
                is_above_5 = current_price >= float(stock_data['Close'].rolling(window=5).mean().iloc[-1])
                is_green_today = current_price > yesterday_close
                
                if is_above_5 and is_green_today:
                    if current_positions + 1 > MAX_POSITIONS: pass
                    elif current_sector_positions[sector] + 1 > MAX_SECTOR_POSITIONS: pass
                    else:
                        order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                        buy_signals.append(f"- [{name}] 🚀 쾌속 진입 ({unit_size}주) ➞ {order_res['msg']} [📊 차트]({chart_link})")
                        
                        if order_res['success']:
                            portfolio[ticker] = {'name': name, 'units': unit_size, 'chunks': 1, 'last_buy_price': current_price, 'stop_loss': current_price - (2 * N)}
                            current_positions += 1
                            current_sector_positions[sector] += 1

        except Exception as e: 
            error_count += 1
            if error_count <= 2: print(f"⚠️ [{ticker}] 에러: {e}")
            continue
        time.sleep(0.1)

# 깨끗해진 새 장부를 깃허브에 덮어쓰기 저장!
with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f: json.dump(portfolio, f, indent=4, ensure_ascii=False)

# ==========================================
# 🌟 브리핑 전송
# ==========================================
buy_text = '\n'.join(buy_signals[:15]) if buy_signals else '신호 없음'
sell_text = '\n'.join(sell_signals[:15]) if sell_signals else '신호 없음'

if buy_signals or sell_signals:
    final_content = f"🤖 **터틀 펀드 v9.5.2 (소액 장부 리셋 테스트)** 🤖\n\n**[🚀 폭풍 신규 매수]**\n{buy_text}"
else:
    final_content = f"🤖 **터틀 펀드 v9.5.2 가동 중** 🤖\n조건을 최하로 낮췄음에도 오늘 시장에 오르는 주식이 전멸했습니다."

if len(final_content) > 1900: final_content = final_content[:1900] + "\n\n... (⚠️ 내역 요약됨)"
requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content})

if SHEET_WEBHOOK_URL:
    kr_time = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    requests.post(SHEET_WEBHOOK_URL, json={
        "date": kr_time, 
        "total_positions": f"{current_positions} / {MAX_POSITIONS}",
        "buys": len(buy_signals), 
        "sells": len(sell_signals),
        "message": f"매수 {len(buy_signals)}건 포착!" if buy_signals else "관망"
    }, timeout=5)
