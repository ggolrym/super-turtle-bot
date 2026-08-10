# ==========================================
# 🐢 AI 하이브리드 터틀 봇 V15.0 (기관급 트레일링 스탑 & 슬리피지 방어 탑재판 - 오타 수정 완료)
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
from datetime import datetime, timedelta
import pytz

# 🌟 1. 환경 변수 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
KIS_APP_KEY = os.environ.get("KIS_APP_KEY")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")
KIS_ACCOUNT = os.environ.get("KIS_ACCOUNT")
SHEET_WEBHOOK_URL = os.environ.get("SHEET_WEBHOOK_URL") 
RUN_MARKET = os.environ.get("RUN_MARKET", "AUTO") 

if not all([GEMINI_API_KEY, DISCORD_WEBHOOK_URL, KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT, SHEET_WEBHOOK_URL]):
    print("🚨 API 키 또는 깃허브 시크릿 누락!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)
KIS_URL = "https://openapivts.koreainvestment.com:29443" 
kr_time = datetime.now(pytz.timezone('Asia/Seoul'))

# 👇 [수정 완료] 코스닥 부분의 변수 누락 에러 완벽 해결
if RUN_MARKET == 'KOSPI': target_market, market_title = 'KR_KOSPI', "🇰🇷 코스피 전용 스캔"
elif RUN_MARKET == 'KOSDAQ': target_market, market_title = 'KR_KOSDAQ', "🚀 코스닥 전용 스캔"
elif RUN_MARKET == 'US': target_market, market_title = 'US', "🇺🇸 미국장 전용 스캔"
else: target_market, market_title = 'ALL', "🌐 통합 테스트 모드"

print(f"⏰ 현재 한국시간: {kr_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"🎯 깃허브 하달 명령: {market_title}\n")

# 🌟 2. KIS API 통신 모듈
def get_kis_token():
    url = f"{KIS_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        return res.json().get("access_token") if res.status_code == 200 else None
    except: return None

kis_token = get_kis_token()
print("✅ KIS 토큰 발급 완료!" if kis_token else "❌ KIS 토큰 발급 실패. 임무를 보류합니다.")

# [V15.0 패치] 슬리피지 방어 (시장가 01 -> 지정가 00으로 강제 변경하여 최신가 쏘기)
def execute_order(ticker, qty, side="BUY", price=0.0):
    if not kis_token: return {"success": False, "msg": "토큰 없음"}
    time.sleep(0.5) 
    
    is_krw = ticker.endswith('.KS') or ticker.endswith('.KQ')
    clean_ticker = ticker.split('.')[0]
    clean_account = KIS_ACCOUNT.replace("-", "").strip()
    cano = clean_account[:8]
    prdt_cd = clean_account[8:10] if len(clean_account) >= 10 else "01"
    
    tr_prefix = "V" if "openapivts" in KIS_URL else "T"
    headers = {"Content-Type": "application/json; charset=utf-8", "authorization": f"Bearer {kis_token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    
    if is_krw:
        url = f"{KIS_URL}/uapi/domestic-stock/v1/trading/order-cash"
        headers["tr_id"] = f"{tr_prefix}TTC0802U" if side == "BUY" else f"{tr_prefix}TTC0801U"
        # 한국장 지정가(00) 주문으로 1호가 미끄러짐 방어
        body = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), "ORD_DVSN": "00", "ORD_UNPR": str(int(price))}
    else:
        url = f"{KIS_URL}/uapi/overseas-stock/v1/trading/order"
        headers["tr_id"] = f"{tr_prefix}TTT1002U" if side == "BUY" else f"{tr_prefix}TTT1006U"
        
        excg_cd = 'NAS' 
        try:
            ex_info = yf.Ticker(clean_ticker).info.get('exchange', '')
            if ex_info in ['NYQ', 'NYSE']: excg_cd = 'NYS'
            elif ex_info in ['ASE', 'NYSE MKT', 'PNK', 'PCX']: excg_cd = 'AMS'
        except: pass
        if clean_ticker in ['SPLG', 'SPY', 'GLDM', 'GLD', 'TLT', 'DBC', 'VNQ', 'SH', 'PSQ', 'QQQM']: excg_cd = 'AMS'
            
        target_price = round(price, 2)
        body = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "OVRS_EXCG_CD": excg_cd, "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), "OVRS_ORD_UNPR": f"{target_price:.2f}", "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"}
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        data = res.json()
        if data.get("rt_cd") == "0": return {"success": True, "msg": "✅ 체결"}
        else: return {"success": False, "msg": f"❌ 거절({data.get('msg1')})"}
    except Exception as e: return {"success": False, "msg": f"❌ 에러({e})"}

# ==========================================
# 🌟 3. 자본 세팅 / 구글 DB / 실잔고 동기화
# ==========================================
TOTAL_CAPITAL = 500000      
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT

MIN_TURNOVER_KRW = 3000000000 
MIN_MARKET_CAP_KRW = 100000000000 
MIN_PRICE_KRW = 2000 
KOSDAQ_MIN_TURNOVER = 50000000000 

MAX_POSITIONS = 4          
MAX_KR_POSITIONS = 2        
MAX_US_POSITIONS = 2        
MAX_SECTOR_POSITIONS = 2       
MAX_POSITION_KRW = 150000     

buy_signals, sell_signals, skipped_signals = [], [], []
dashboard_list = [] 
portfolio = {}
print("구글 시트(DB)에서 포트폴리오를 불러옵니다...")

if SHEET_WEBHOOK_URL:
    db_loaded = False
    for attempt in range(3):
        try:
            res = requests.get(SHEET_WEBHOOK_URL, timeout=30, allow_redirects=True)
            if res.status_code == 200:
                raw_text = res.text.strip()
                if raw_text and raw_text.startswith('{') and raw_text.endswith('}'):
                    data = json.loads(raw_text)
                    if isinstance(data, dict): portfolio = data
                db_loaded = True
                break
            else: time.sleep(5)
        except: time.sleep(5)
            
    if not db_loaded:
        error_msg = f"🚨 **시스템 자동 정지** [{market_title}] 구글 DB 응답 없음."
        try: requests.post(DISCORD_WEBHOOK_URL, json={"content": error_msg}, timeout=10)
        except: pass
        exit() 

def sync_portfolio_with_kis_balance(current_portfolio):
    if not kis_token: return current_portfolio
    clean_account = KIS_ACCOUNT.replace("-", "").strip()
    cano, prdt_cd = clean_account[:8], (clean_account[8:10] if len(clean_account) >= 10 else "01")
    tr_prefix = "V" if "openapivts" in KIS_URL else "T"
    
    actual_tickers = {} 
    headers = {"Content-Type": "application/json; charset=utf-8", "authorization": f"Bearer {kis_token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    
    try:
        headers["tr_id"] = f"{tr_prefix}TTC8434R"
        params = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "01", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}
        res = requests.get(f"{KIS_URL}/uapi/domestic-stock/v1/trading/inquire-balance", headers=headers, params=params, timeout=10)
        for item in res.json().get('output1', []):
            qty = int(item.get('hldg_qty', 0))
            if qty > 0: actual_tickers[item.get('pdno')] = qty
    except: pass

    try:
        headers["tr_id"] = f"{tr_prefix}TTS3012R"
        params = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "WCRC_FRS_EXCG_CD": "USD", "NATN_CD": "840", "TR_MKET_CD": "00", "INQR_DVSN_CD": "0"}
        res = requests.get(f"{KIS_URL}/uapi/overseas-stock/v1/trading/inquire-present-balance", headers=headers, params=params, timeout=10)
        for item in res.json().get('output1', []):
            qty = int(float(item.get('ccld_qty_smtl1', 0)))
            if qty > 0:
                sym = item.get('ovrs_pdno', '').replace('.', '-').replace('/', '-')
                if sym: actual_tickers[sym] = qty
    except: pass

    synced_portfolio = {}
    for t, p in current_portfolio.items():
        clean_t = t.split('.')[0]
        if clean_t in actual_tickers or t in actual_tickers: 
            actual_qty = actual_tickers.get(clean_t, actual_tickers.get(t, p['units']))
            p['units'] = actual_qty
            synced_portfolio[t] = p
        else: skipped_signals.append(f"- 🔄 [{p['name']}] 장부 불일치 ➞ 실제 계좌 잔고가 없어 DB 동기화 삭제 처리")
    return synced_portfolio

portfolio = sync_portfolio_with_kis_balance(portfolio)

exchange_rate = 1350.0
try:
    ex_df = fdr.DataReader('USD/KRW')
    if not ex_df.empty: exchange_rate = float(ex_df['Close'].iloc[-1])
except: pass

def get_sector(ticker):
    if ticker in ['GLDM', 'GLD']: return 'Gold'
    elif ticker == 'DBC': return 'Commodity'
    elif ticker == 'TLT': return 'Bond'
    elif ticker == 'VNQ': return 'RealEstate'
    elif ticker in ['SH', 'PSQ']: return 'Inverse' 
    return 'Stock'

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, float('nan'))
    rsi = 100 - (100 / (1 + rs))
    rsi[loss == 0] = 100
    return rsi

# ==========================================
# 🌟 4. [런타임 극비 최적화] 사전 필터링 유니버스
# ==========================================
all_stocks = {}
print("⏳ 시장 유니버스 사전 필터링 중... (속도 10배 향상 엔진)")

if target_market in ['KR_KOSPI', 'ALL']:
    try:
        kr_df = fdr.StockListing('KOSPI')
        for _, row in kr_df.iterrows(): 
            try:
                price = float(row.get('Close', 0))
                amount = float(row.get('Amount', 0)) 
                marcap = float(row.get('Marcap', 0))
                if price < MIN_PRICE_KRW or amount < MIN_TURNOVER_KRW or marcap < MIN_MARKET_CAP_KRW: continue
                code = str(row.get('Code', row.get('Symbol', ''))).zfill(6) + '.KS'
                all_stocks[code] = str(row.get('Name', ''))
            except: continue
    except: pass

if target_market in ['KR_KOSDAQ', 'ALL']:
    try:
        kq_df = fdr.StockListing('KOSDAQ')
        for _, row in kq_df.iterrows():
            try:
                price = float(row.get('Close', 0))
                amount = float(row.get('Amount', 0))
                if price < MIN_PRICE_KRW or amount < KOSDAQ_MIN_TURNOVER: continue
                code = str(row.get('Code', row.get('Symbol', ''))).zfill(6) + '.KQ'
                all_stocks[code] = str(row.get('Name', ''))
            except: continue
    except: pass

if target_market in ['US', 'ALL']:
    all_stocks.update({'SPLG': 'SPDR S&P 500', 'GLDM': 'SPDR Gold', 'DBC': 'Invesco Commodity', 'SH': 'Short S&P500', 'PSQ': 'Short QQQ'})
    try:
        us_df = fdr.StockListing('SP500')
        col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
        col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
        special_tickers = {'BRKB': 'BRK-B', 'BFB': 'BF-B'}
        for _, row in us_df.iterrows(): 
            raw_sym = str(row[col_sym])
            clean_sym = special_tickers.get(raw_sym, raw_sym.replace('.', '-').replace('/', '-'))
            all_stocks[clean_sym] = str(row[col_name])
    except: pass

for t in portfolio.keys():
    t_mark = 'KR_KOSPI' if t.endswith('.KS') else 'KR_KOSDAQ' if t.endswith('.KQ') else 'US'
    if t_mark == target_market and t not in all_stocks: all_stocks[t] = portfolio[t]['name']

current_positions = len(portfolio)
current_kr_positions = sum(1 for p in portfolio.values() if p.get('strategy') in ['KR_SWING', 'KQ_BREAKOUT'])
current_us_positions = sum(1 for p in portfolio.values() if p.get('strategy') == 'US_TURTLE')
current_sector_positions = {'Stock': 0, 'Gold': 0, 'Commodity': 0, 'Bond': 0, 'RealEstate': 0, 'Inverse': 0}
for t in portfolio.keys(): 
    sec = get_sector(t)
    if sec in current_sector_positions: current_sector_positions[sec] += 1

print(f"📊 동기화된 계좌: 한국장 {current_kr_positions}개 / 미국장 {current_us_positions}개")
print(f"⚡ 사전 필터링 완료! 살아남은 {len(all_stocks)}개 정예 종목 정밀 스캔 시작!")

# ==========================================
# 🌟 5. [지능형 랭킹 엔진] 스캔 및 로직
# ==========================================
kr_swing_candidates = []      
kq_breakout_candidates = []   
us_candidates = []            
prices_cache = {}
fdr_start_date = (kr_time - timedelta(days=730)).strftime('%Y-%m-%d')
scanned_tickers = set()

if kis_token: 
    for ticker, name in all_stocks.items():
        try:
            stock_data = pd.DataFrame()
            is_kr_kospi = ticker.endswith('.KS')
            is_kr_kosdaq = ticker.endswith('.KQ')
            is_us = not (is_kr_kospi or is_kr_kosdaq)
            clean_ticker = ticker.split('.')[0]
            
            if is_kr_kospi or is_kr_kosdaq:
                for attempt in range(3):
                    temp_data = fdr.DataReader(clean_ticker, start=fdr_start_date)
                    min_len = 20 if ticker in portfolio else 200 
                    if not temp_data.empty and len(temp_data) >= min_len:
                        stock_data = temp_data
                        break
                    time.sleep(0.1) 
            else:
                ticker_obj = yf.Ticker(ticker)
                for attempt in range(3):
                    temp_data = ticker_obj.history(period='2y')
                    min_len = 20 if ticker in portfolio else 200
                    if not temp_data.empty and len(temp_data) >= min_len:
                        stock_data = temp_data
                        break
                    time.sleep(0.5)
                
            if stock_data.empty: continue 
            
            scanned_tickers.add(ticker)
            if isinstance(stock_data.columns, pd.MultiIndex): stock_data.columns = stock_data.columns.get_level_values(0)
            stock_data = stock_data.dropna()
                
            current_price = float(stock_data['Close'].iloc[-1])
            prices_cache[ticker] = current_price 
            
            current_price_krw = current_price if (is_kr_kospi or is_kr_kosdaq) else current_price * exchange_rate
            sector = get_sector(ticker)
            chart_link = f"https://finance.naver.com/item/fchart.naver?code={clean_ticker}" if (is_kr_kospi or is_kr_kosdaq) else f"https://finance.yahoo.com/quote/{ticker}/chart"

            # ------------------------------------
            # 🇺🇸 미국장 로직 (터틀 추세추종)
            # ------------------------------------
            if is_us and target_market in ['US', 'ALL']:
                low_10 = float(stock_data['Low'].iloc[-11:-1].min())
                high_low = stock_data['High'] - stock_data['Low']
                high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
                low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
                tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                N = float(tr.rolling(window=20).mean().iloc[-1])
                ma_120 = float(stock_data['Close'].rolling(window=120).mean().iloc[-1])
                rsi_14 = float(calculate_rsi(stock_data['Close'], 14).iloc[-1])
                
                if pd.isna(N) or N <= 0 or current_price_krw > MAX_POSITION_KRW: continue
                N_krw = N * exchange_rate
                unit_size = math.floor(RISK_AMOUNT / N_krw)
                unit_size = 1 if unit_size == 0 else unit_size
                if unit_size * current_price_krw > MAX_POSITION_KRW:
                    unit_size = math.floor(MAX_POSITION_KRW / current_price_krw)
                    if unit_size == 0: continue 

                if ticker in portfolio:
                    pos = portfolio[ticker]
                    pos['trailing_stop'] = low_10
                    if current_price <= pos['stop_loss'] or current_price <= low_10:
                        order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                        sell_signals.append(f"- [{name}] 전량 청산 ({pos['units']}주) ➞ {order_res['msg']}")
                        if order_res['success']:
                            current_positions -= 1; current_sector_positions[sector] -= 1; current_us_positions -= 1
                            del portfolio[ticker] 
                    else:
                        chunks = pos.get('chunks', 1)
                        if chunks < 4 and current_price >= pos['last_buy_price'] + (0.5 * N):
                            order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                            buy_signals.append(f"- [{name}] 🔥 {chunks+1}차 불타기 ➞ {order_res['msg']}")
                            if order_res['success']:
                                pos['units'] += unit_size; pos['chunks'] = chunks + 1
                                pos['last_buy_price'] = current_price; pos['stop_loss'] = current_price - (2 * N)

                elif ticker not in portfolio:
                    turnover_krw = (current_price * float(stock_data['Volume'].iloc[-21:-1].mean())) * exchange_rate
                    if turnover_krw < MIN_TURNOVER_KRW: continue
                    if sector == 'Stock' and current_price < ma_120: continue      

                    recent_20_high = float(stock_data['High'].iloc[-21:-1].max())
                    if current_price >= recent_20_high:
                        if rsi_14 >= 80.0: continue
                        momentum = current_price / ma_120 
                        us_candidates.append({
                            'ticker': ticker, 'name': name, 'unit_size': unit_size, 'price': current_price,
                            'N': N, 'low_10': low_10, 'momentum': momentum, 'sector': sector, 'market': 'US', 'chart_link': chart_link
                        })

            # ------------------------------------
            # 🇰🇷 코스피 로직 (스윙: 반반 익절 + 트레일링 스탑 적용)
            # ------------------------------------
            elif is_kr_kospi and target_market in ['KR_KOSPI', 'ALL']:
                if current_price < MIN_PRICE_KRW or current_price_krw > MAX_POSITION_KRW: continue
                avg_volume = float(stock_data['Volume'].iloc[-21:-1].mean())
                turnover_krw = current_price * avg_volume
                if turnover_krw < MIN_TURNOVER_KRW: continue
                
                rsi_14 = float(calculate_rsi(stock_data['Close'], 14).iloc[-1])
                ma_20 = float(stock_data['Close'].rolling(window=20).mean().iloc[-1])
                std_20 = float(stock_data['Close'].rolling(window=20).std().iloc[-1])
                bb_lower = ma_20 - (2 * std_20)
                
                unit_size = math.floor(MAX_POSITION_KRW / current_price_krw)
                if unit_size == 0: continue

                if ticker in portfolio:
                    pos = portfolio[ticker]
                    profit_pct = (current_price - pos['last_buy_price']) / pos['last_buy_price'] * 100
                    
                    half_sell_flag = pos.get('half_sold', False)
                    
                    if profit_pct >= 5.0 and not half_sell_flag and pos['units'] > 1:
                        sell_qty = math.floor(pos['units'] / 2)
                        order_res = execute_order(ticker, sell_qty, side="SELL", price=current_price)
                        sell_signals.append(f"- [{name}] 🎯 1차 5% 익절 ({sell_qty}주) ➞ {order_res['msg']}")
                        if order_res['success']:
                            pos['units'] -= sell_qty
                            pos['half_sold'] = True
                            pos['stop_loss'] = pos['last_buy_price'] 
                            
                    elif current_price <= pos['stop_loss'] or (half_sell_flag and current_price < ma_20):
                        reason = "🔪 손절/본전컷" if current_price <= pos['last_buy_price'] else "💰 트레일링 스탑 익절"
                        order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                        sell_signals.append(f"- [{name}] {reason} ({pos['units']}주) ➞ {order_res['msg']}")
                        if order_res['success']:
                            current_positions -= 1; current_sector_positions[sector] -= 1; current_kr_positions -= 1
                            del portfolio[ticker] 

                elif ticker not in portfolio:
                    if rsi_14 <= 30.0 and current_price <= bb_lower:
                        kr_swing_candidates.append({
                            'ticker': ticker, 'name': name, 'unit_size': unit_size, 'price': current_price,
                            'rsi': rsi_14, 'ma_20': ma_20, 'sector': sector, 'market': 'KR_KOSPI', 'chart_link': chart_link
                        })

            # ------------------------------------
            # 🚀 코스닥 로직 (돌파: 윗꼬리 가짜돌파 필터링)
            # ------------------------------------
            elif is_kr_kosdaq and target_market in ['KR_KOSDAQ', 'ALL']:
                if current_price < MIN_PRICE_KRW or current_price_krw > MAX_POSITION_KRW: continue
                avg_volume = float(stock_data['Volume'].iloc[-21:-1].mean())
                turnover_krw = current_price * avg_volume
                
                if turnover_krw < KOSDAQ_MIN_TURNOVER: continue
                
                high_low = stock_data['High'] - stock_data['Low']
                high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
                low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
                tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                N = float(tr.rolling(window=20).mean().iloc[-1])
                
                if pd.isna(N) or N <= 0: continue
                unit_size = math.floor(MAX_POSITION_KRW / current_price_krw)
                if unit_size == 0: continue

                if ticker in portfolio:
                    pos = portfolio[ticker]
                    if current_price <= pos['stop_loss']:
                        order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                        sell_signals.append(f"- [{name}] 코스닥 추세이탈 청산 ({pos['units']}주) ➞ {order_res['msg']}")
                        if order_res['success']:
                            current_positions -= 1; current_sector_positions[sector] -= 1; current_kr_positions -= 1
                            del portfolio[ticker] 
                    else:
                        new_stop = current_price - (2 * N)
                        if new_stop > pos['stop_loss']: pos['stop_loss'] = new_stop

                elif ticker not in portfolio:
                    recent_20_high = float(stock_data['High'].iloc[-21:-1].max())
                    ma_120 = float(stock_data['Close'].rolling(window=120).mean().iloc[-1])
                    
                    daily_high = float(stock_data['High'].iloc[-1])
                    daily_low = float(stock_data['Low'].iloc[-1])
                    if daily_high > daily_low:
                        close_position_ratio = (daily_high - current_price) / (daily_high - daily_low)
                    else: close_position_ratio = 1.0 
                    
                    if current_price >= recent_20_high and current_price > ma_120 and close_position_ratio <= 0.30:
                        kq_breakout_candidates.append({
                            'ticker': ticker, 'name': name, 'unit_size': unit_size, 'price': current_price,
                            'turnover': turnover_krw, 'N': N, 'sector': sector, 'market': 'KR_KOSDAQ', 'chart_link': chart_link
                        })

        except Exception: continue
        
    ghost_tickers = []
    for t in list(portfolio.keys()):
        t_mark = 'KR_KOSPI' if t.endswith('.KS') else 'KR_KOSDAQ' if t.endswith('.KQ') else 'US'
        if target_market in ['ALL', t_mark] and t not in scanned_tickers:
            ghost_tickers.append(t)
    
    for ghost in ghost_tickers:
        g_name = portfolio[ghost]['name']
        g_sec = get_sector(ghost)
        g_strat = portfolio[ghost].get('strategy', 'UNKNOWN')
        skipped_signals.append(f"- 👻 [{g_name}] 데이터 누락 감지 ➞ 장부 임시 소각")
        current_positions -= 1; current_sector_positions[g_sec] -= 1
        if g_strat in ['KR_SWING', 'KQ_BREAKOUT']: current_kr_positions -= 1
        elif g_strat == 'US_TURTLE': current_us_positions -= 1
        del portfolio[ghost]

    # ==================================================
    # 🌟 6. 3대장 랭킹 정렬 및 밸런싱 매수 실행
    # ==================================================
    us_candidates.sort(key=lambda x: x['momentum'], reverse=True)     
    kr_swing_candidates.sort(key=lambda x: x['rsi'])                  
    kq_breakout_candidates.sort(key=lambda x: x['turnover'], reverse=True) 
    
    kr_all_candidates = kq_breakout_candidates + kr_swing_candidates
    all_candidates = us_candidates + kr_all_candidates
    
    for cand in all_candidates:
        if current_positions >= MAX_POSITIONS: 
            skipped_signals.append(f"- [{cand['name']}] 전체 계좌 꽉참 (보류)")
            break
            
        if cand['market'].startswith('KR') and current_kr_positions >= MAX_KR_POSITIONS:
            skipped_signals.append(f"- [{cand['name']}] 한국장(KR) {MAX_KR_POSITIONS}개 한도 초과 (보류)")
            continue
            
        if cand['market'] == 'US' and current_us_positions >= MAX_US_POSITIONS:
            skipped_signals.append(f"- [{cand['name']}] 미국장(US) {MAX_US_POSITIONS}개 한도 초과 (보류)")
            continue
            
        if current_sector_positions[cand['sector']] >= MAX_SECTOR_POSITIONS: 
            continue
            
        order_res = execute_order(cand['ticker'], cand['unit_size'], side="BUY", price=cand['price'])
        
        if cand['market'] == 'KR_KOSPI':
            buy_signals.append(f"- 🥇 [{cand['name']}] 📉 코스피 스윙(RSI: {cand['rsi']:.1f}) ➞ {order_res['msg']} [차트]({cand['chart_link']})")
            if order_res['success']:
                portfolio[cand['ticker']] = {'name': cand['name'], 'units': cand['unit_size'], 'chunks': 1, 'last_buy_price': cand['price'], 'stop_loss': cand['price'] * 0.95, 'trailing_stop': cand['ma_20'], 'strategy': 'KR_SWING', 'half_sold': False}
                current_positions += 1; current_sector_positions[cand['sector']] += 1; current_kr_positions += 1
        elif cand['market'] == 'KR_KOSDAQ':
            buy_signals.append(f"- 🥇 [{cand['name']}] 🚀 코스닥 돌파(대장주) ➞ {order_res['msg']} [차트]({cand['chart_link']})")
            if order_res['success']:
                portfolio[cand['ticker']] = {'name': cand['name'], 'units': cand['unit_size'], 'chunks': 1, 'last_buy_price': cand['price'], 'stop_loss': cand['price'] - (2 * cand['N']), 'trailing_stop': cand['price'] - (2 * cand['N']), 'strategy': 'KQ_BREAKOUT'}
                current_positions += 1; current_sector_positions[cand['sector']] += 1; current_kr_positions += 1
        else:
            buy_signals.append(f"- 🥇 [{cand['name']}] ✨ 미국장 추세(모멘텀: {cand['momentum']:.2f}) ➞ {order_res['msg']} [차트]({cand['chart_link']})")
            if order_res['success']:
                portfolio[cand['ticker']] = {'name': cand['name'], 'units': cand['unit_size'], 'chunks': 1, 'last_buy_price': cand['price'], 'stop_loss': cand['price'] - (2 * cand['N']), 'trailing_stop': cand['low_10'], 'strategy': 'US_TURTLE'}
                current_positions += 1; current_sector_positions[cand['sector']] += 1; current_us_positions += 1

# 대시보드 리스트 생성
for ticker, pos in portfolio.items():
    if ticker not in prices_cache:
        try:
            if pos['strategy'] in ['KR_SWING', 'KQ_BREAKOUT']:
                temp = fdr.DataReader(ticker.split('.')[0])
                prices_cache[ticker] = float(temp['Close'].iloc[-1])
            else:
                temp = yf.Ticker(ticker).history(period='5d')
                prices_cache[ticker] = float(temp['Close'].iloc[-1])
        except: pass
    cp = prices_cache.get(ticker, pos['last_buy_price'])
    dashboard_list.append({
        "name": pos['name'], "units": pos['units'], "current_price": round(cp, 2), 
        "buy_price": round(pos['last_buy_price'], 2), "stop_loss": round(pos['stop_loss'], 2), "trailing_stop": round(pos.get('trailing_stop', 0), 2)
    })

# ==========================================
# 🌟 7. 브리핑 전송 및 구글 DB 저장
# ==========================================
if not kis_token:
    final_content = "🚨 **시스템 경보** API 토큰 발급 실패"
else:
    buy_text = '\n'.join(buy_signals[:10]) if buy_signals else '신호 없음'
    sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '신호 없음'
    skip_text = '\n'.join(skipped_signals[:5]) if skipped_signals else '보류 없음'

    if buy_signals or sell_signals or skipped_signals:
        prompt = f"[매수] {buy_text}\n[청산] {sell_text}\n[보류] {skip_text}"
        response_text = ""
        for _ in range(3):
            try:
                response_text = client.models.generate_content(model='gemini-2.0-flash', contents=prompt).text 
                break 
            except Exception: time.sleep(5)
                
        if not response_text: response_text = f"**매수**\n{buy_text}\n\n**청산**\n{sell_text}"
        final_content = f"🤖 **V15.0 ({market_title})** 🤖\n{response_text}"
    else:
        final_content = f"🤖 **V15.0 ({market_title} 관망)** 🤖\n감시 {len(all_stocks)}개 / 잔고: 한국 {current_kr_positions}/{MAX_KR_POSITIONS}개, 미국 {current_us_positions}/{MAX_US_POSITIONS}개."

if len(final_content) > 1900: final_content = final_content[:1900] + "\n\n... (⚠️ 요약됨)"

try:
    requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content}, timeout=10)
except Exception as e:
    print(f"⚠️ 디스코드 발송 실패: {e}")

if SHEET_WEBHOOK_URL:
    kr_time = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    buy_count = len([s for s in buy_signals if '신규 진입' in s or '픽' in s or '돌파' in s])
    sell_count = len(sell_signals)
    summary_msg = f"매수/익절 {buy_count}건, 청산 {sell_count}건" if (buy_count > 0 or sell_count > 0) else "관망 중"
    
    sheet_data = {
        "date": kr_time,
        "message": f"[{market_title}] {summary_msg}",
        "dashboard": dashboard_list,
        "portfolio": portfolio 
    }
    try: 
        requests.post(SHEET_WEBHOOK_URL, json=sheet_data, timeout=30)
    except Exception as e:
        print(f"⚠️ 구글 시트 저장 실패: {e}")
