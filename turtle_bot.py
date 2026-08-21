# ==========================================
# 🚀 AI 하이브리드 터틀 봇 V36.6 Safe Defender Live
# (4슬롯 분산 / 코스피 통합 방어막 패치 🌟 / 스마트 익절 / IP 밴 원천차단)
# ==========================================
import os
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import requests
import time
import math
import json 
from datetime import datetime, timedelta
import pytz
import warnings
import logging

warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# 🌟 1. 환경 변수 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip() 
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
KIS_APP_KEY = os.environ.get("KIS_APP_KEY", "").strip()
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET", "").strip()
KIS_ACCOUNT = os.environ.get("KIS_ACCOUNT", "").strip()
SHEET_WEBHOOK_URL = os.environ.get("SHEET_WEBHOOK_URL", "").strip() 
RUN_MARKET = os.environ.get("RUN_MARKET", "AUTO").strip()

if not all([DISCORD_WEBHOOK_URL, KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT, SHEET_WEBHOOK_URL]):
    print("🚨 필수 API 키 또는 깃허브 시크릿 누락!")
    exit(1)

KIS_URL = "https://openapivts.koreainvestment.com:29443" 
kr_time = datetime.now(pytz.timezone('Asia/Seoul'))
today_str = kr_time.strftime('%Y-%m-%d')

# 💡 실시간 환율 동적 조회
EXCHANGE_RATE = 1350.0
try:
    ex_df = fdr.DataReader('USD/KRW', start=(kr_time - timedelta(days=7)).strftime('%Y-%m-%d'))
    if not ex_df.empty: EXCHANGE_RATE = float(ex_df['Close'].iloc[-1])
except: pass

if RUN_MARKET == 'KOSPI': target_market, market_title = 'KR_KOSPI', "🇰🇷 코스피 전용"
elif RUN_MARKET == 'KOSDAQ': target_market, market_title = 'KR_KOSDAQ', "🚀 코스닥 전용"
elif RUN_MARKET == 'US': target_market, market_title = 'US', "🇺🇸 미국장 전용"
else: target_market, market_title = 'ALL', "🌐 통합장"

print(f"⏰ 현재 한국시간: {kr_time.strftime('%Y-%m-%d %H:%M:%S')} (적용 환율: {EXCHANGE_RATE:,.1f}원)")
print(f"🎯 V36.6 Safe Defender 가동 (4슬롯 분산 / 코스피 통합 방어막 / {market_title})\n")

# 🌟 2. KIS API 통신 모듈
def get_kis_token():
    url = f"{KIS_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        return res.json().get("access_token") if res.status_code == 200 else None
    except Exception as e: 
        print(f"⚠️ 토큰 발급 에러: {e}")
        return None

kis_token = get_kis_token()
print("✅ KIS 토큰 발급 완료!" if kis_token else "❌ KIS 토큰 발급 실패. 임무를 보류합니다.")

def execute_order(ticker, qty, side="BUY", price=0.0):
    if not kis_token: return {"success": False, "msg": "토큰 없음"}
    if qty <= 0: return {"success": False, "msg": "수량 부족"}
    time.sleep(0.5) 
    
    is_kr = ticker.endswith('.KS') or ticker.endswith('.KQ')
    clean_ticker = ticker.split('.')[0]
    clean_account = KIS_ACCOUNT.replace("-", "")
    cano = clean_account[:8]
    prdt_cd = clean_account[8:10] if len(clean_account) >= 10 else "01"
    tr_prefix = "V" if "openapivts" in KIS_URL else "T"
    headers = {"Content-Type": "application/json; charset=utf-8", "authorization": f"Bearer {kis_token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    
    if is_kr:
        url = f"{KIS_URL}/uapi/domestic-stock/v1/trading/order-cash"
        headers["tr_id"] = f"{tr_prefix}TTC0802U" if side == "BUY" else f"{tr_prefix}TTC0801U"
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
        if clean_ticker in ['SPLG', 'QQQM', 'SOXX', 'SPY', 'GLDM', 'GLD', 'TLT', 'DBC', 'VNQ', 'SH', 'PSQ']: excg_cd = 'AMS'
            
        target_price = round(price, 2)
        body = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "OVRS_EXCG_CD": excg_cd, "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), "OVRS_ORD_UNPR": f"{target_price:.2f}", "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"}
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        data = res.json()
        if data.get("rt_cd") == "0": return {"success": True, "msg": "체결성공"}
        else: return {"success": False, "msg": f"거절({data.get('msg1')})"}
    except Exception as e: return {"success": False, "msg": f"통신에러"}

# ==========================================
# 🌟 3. 자본 및 방어막 세팅 (4슬롯, 50만 원)
# ==========================================
INITIAL_CAPITAL = 500000         
POSITION_SIZE_RATIO = 0.25       # 4슬롯 분산
MAX_POSITIONS = 4                
MAX_KR_POSITIONS = 2             
MAX_US_POSITIONS = 2             

FIXED_STOP_LOSS_KR = 0.08  
FIXED_STOP_LOSS_US = 0.1   
MAX_HOLD_DAYS = 20         

# 정밀 수수료 설정
KR_FEE = 0.00015
KR_TAX = 0.0018
US_FEE = 0.0025        
US_SEC_FEE = 0.0000206 

buy_signals, sell_signals = [], []
dashboard_list = [] 
portfolio = {}
bot_cash = INITIAL_CAPITAL 
cooldown_tracker = {} 

# 단기 매크로 서킷브레이커 (MA20 & MA50 동시 충족)
def check_macro_regime(index_ticker):
    try:
        if index_ticker.startswith('^'): df = yf.Ticker(index_ticker).history(period='1y')
        else: df = fdr.DataReader(index_ticker, start=(kr_time - timedelta(days=150)).strftime('%Y-%m-%d'))
        if df.empty or len(df) < 50: return True
        curr_close = float(df['Close'].iloc[-1])
        ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
        ma50 = float(df['Close'].rolling(50).mean().iloc[-1])
        return (curr_close >= ma20) and (curr_close >= ma50)
    except: return True

# 💡 [패치 1] 코스닥 지수 수집 제거 및 코스피/미국장으로 통합
macro_bull = {
    'KR': check_macro_regime('KS11'), # 한국장은 코스피 하나로 통합
    'US': check_macro_regime('^GSPC')
}

print(f"🛡️ 단기 방어막(MA20 & MA50) 상태:")
print(f" - KR(한국장 전체): {'🟢 안전' if macro_bull['KR'] else '🔴 하락장 방어 중'}")
print(f" - US(미국장 전체): {'🟢 안전' if macro_bull['US'] else '🔴 하락장 방어 중'}\n")

# DB 불러오기
if SHEET_WEBHOOK_URL:
    for attempt in range(3):
        try:
            res = requests.get(SHEET_WEBHOOK_URL, timeout=30, allow_redirects=True)
            if res.status_code == 200:
                raw_text = res.text.strip()
                if raw_text.startswith('{') and raw_text.endswith('}'):
                    data = json.loads(raw_text)
                    if isinstance(data, dict): 
                        portfolio = data.get('portfolio', data) 
                        cooldown_tracker = data.get('cooldown_tracker', {})
                        if 'bot_cash' in data: 
                            bot_cash = float(data['bot_cash'])
                        else:
                            invested = sum(p.get('buy_price', 0) * p.get('units', 0) * (1 if str(p.get('market', '')).startswith('KR') else EXCHANGE_RATE) for p in portfolio.values() if isinstance(p, dict))
                            bot_cash = INITIAL_CAPITAL - invested
                break
            time.sleep(5)
        except: time.sleep(5)

active_cooldowns = {}
for t, expire_date in cooldown_tracker.items():
    try:
        if datetime.strptime(expire_date, '%Y-%m-%d').date() > kr_time.date():
            active_cooldowns[t] = expire_date
    except: pass
cooldown_tracker = active_cooldowns

# 잔고 이중 검증 및 서버 장중 손절 감지
def sync_portfolio_with_kis_balance(current_portfolio):
    if not kis_token: return current_portfolio
    clean_account = KIS_ACCOUNT.replace("-", "")
    cano, prdt_cd = clean_account[:8], (clean_account[8:10] if len(clean_account) >= 10 else "01")
    tr_prefix = "V" if "openapivts" in KIS_URL else "T"
    
    kr_tickers, us_tickers = {}, {}
    kr_api_success, us_api_success = False, False 
    headers = {"Content-Type": "application/json; charset=utf-8", "authorization": f"Bearer {kis_token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    
    try: 
        headers["tr_id"] = f"{tr_prefix}TTC8434R"
        params = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "01", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}
        res = requests.get(f"{KIS_URL}/uapi/domestic-stock/v1/trading/inquire-balance", headers=headers, params=params, timeout=10)
        data = res.json()
        if res.status_code == 200 and data.get('rt_cd') == '0':
            kr_api_success = True
            for item in data.get('output1', []):
                qty = int(item.get('hldg_qty', 0))
                if qty > 0: kr_tickers[item.get('pdno')] = {'qty': qty, 'avg_price': float(item.get('pchs_avg_pric', 0))}
    except: pass

    try: 
        headers["tr_id"] = f"{tr_prefix}TTS3012R"
        params = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "WCRC_FRCR_DVSN_CD": "02", "NATN_CD": "840", "TR_MKET_CD": "00", "INQR_DVSN_CD": "00"}
        res = requests.get(f"{KIS_URL}/uapi/overseas-stock/v1/trading/inquire-present-balance", headers=headers, params=params, timeout=10)
        data = res.json()
        if res.status_code == 200 and data.get('rt_cd') == '0':
            us_api_success = True
            for item in data.get('output1', []):
                qty = int(max(float(item.get('ccld_qty_smtl1', 0)), float(item.get('cblc_qty13', 0)))) 
                if qty > 0:
                    sym = item.get('ovrs_pdno', '').replace('.', '-').replace('/', '-')
                    if sym: us_tickers[sym] = {'qty': qty, 'avg_price': float(item.get('pchs_avg_pric', 0))}
    except: pass

    global bot_cash
    synced = {}
    for t, p in current_portfolio.items():
        if not isinstance(p, dict): continue 
        clean_t = t.split('.')[0]
        is_kr = t.endswith('.KS') or t.endswith('.KQ')
        
        if is_kr and kr_api_success and (clean_t not in kr_tickers and t not in kr_tickers):
            print(f"⚠️ {t} 잔고 없음 (장중 서버 자동손절 감지) ➔ 쿨다운 5일 적용")
            sell_signals.append(f"🔪 서버 장중 손절 감지: {p.get('name')} (현금 회수 완료)")
            bot_cash += (p['units'] * p['buy_price'] * (1 - FIXED_STOP_LOSS_KR) * (1 - KR_FEE - KR_TAX))
            cooldown_tracker[t] = (kr_time + timedelta(days=5)).strftime('%Y-%m-%d')
            continue
            
        if not is_kr and us_api_success and (clean_t not in us_tickers and t not in us_tickers):
            print(f"⚠️ {t} 잔고 없음 (장중 서버 자동손절 감지) ➔ 쿨다운 5일 적용")
            sell_signals.append(f"🔪 서버 장중 손절 감지: {p.get('name')} (현금 회수 완료)")
            bot_cash += (p['units'] * p['buy_price'] * (1 - FIXED_STOP_LOSS_US) * (1 - US_FEE - US_SEC_FEE) * EXCHANGE_RATE)
            cooldown_tracker[t] = (kr_time + timedelta(days=5)).strftime('%Y-%m-%d')
            continue
            
        if is_kr:
            if not kr_api_success: 
                synced[t] = p
                continue
            match_k = clean_t if clean_t in kr_tickers else t
            p['units'] = kr_tickers[match_k]['qty']
            if p.get('buy_price', 0) == 0: p['buy_price'] = kr_tickers[match_k]['avg_price']
            synced[t] = p
            del kr_tickers[match_k] 
        else:
            if not us_api_success: 
                synced[t] = p
                continue
            match_k = clean_t if clean_t in us_tickers else t
            p['units'] = us_tickers[match_k]['qty']
            if p.get('buy_price', 0) == 0: p['buy_price'] = us_tickers[match_k]['avg_price']
            synced[t] = p
            del us_tickers[match_k] 

    if us_api_success:
        for sym, data in us_tickers.items(): synced[sym] = {'name': sym, 'units': data['qty'], 'buy_price': data['avg_price'], 'market': 'US', 'buy_date': today_str, 'hold_days': 0}
    if kr_api_success:
        for code, data in kr_tickers.items(): synced[f"{code}.KS"] = {'name': code, 'units': data['qty'], 'buy_price': data['avg_price'], 'market': 'KR_KOSPI', 'buy_date': today_str, 'hold_days': 0}
    return synced

portfolio = sync_portfolio_with_kis_balance(portfolio)
current_kr_positions = sum(1 for p in portfolio.values() if isinstance(p, dict) and p.get('market', '').startswith('KR'))
current_us_positions = sum(1 for p in portfolio.values() if isinstance(p, dict) and p.get('market') == 'US')

# ==========================================
# 🌟 4. 거래대금 필터링 & 유니버스 구축
# ==========================================
MIN_TURNOVER_KRW = 10000000000 
MIN_PRICE_KRW = 1000           
all_stocks = {}

print(f"⏳ 유니버스 사전 필터링 중... ({market_title})")

if target_market in ['KR_KOSPI', 'ALL']:
    try:
        kr_df = fdr.StockListing('KOSPI')
        for _, row in kr_df.iterrows(): 
            try:
                if float(row.get('Close', 0)) < MIN_PRICE_KRW or float(row.get('Amount', 0)) < MIN_TURNOVER_KRW: continue
                code = str(row.get('Code', row.get('Symbol', ''))).zfill(6) + '.KS'
                all_stocks[code] = ('KR_KOSPI', str(row.get('Name', '')), code)
            except: continue
    except: pass

if target_market in ['KR_KOSDAQ', 'ALL']:
    try:
        kq_df = fdr.StockListing('KOSDAQ')
        for _, row in kq_df.iterrows():
            try:
                if float(row.get('Close', 0)) < MIN_PRICE_KRW or float(row.get('Amount', 0)) < MIN_TURNOVER_KRW: continue
                code = str(row.get('Code', row.get('Symbol', ''))).zfill(6) + '.KQ'
                all_stocks[code] = ('KR_KOSDAQ', str(row.get('Name', '')), code)
            except: continue
    except: pass

special_tickers = {'BRKB': 'BRK-B', 'BFB': 'BF-B'}
if target_market in ['US', 'ALL']:
    try:
        us_df = fdr.StockListing('SP500')
        col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
        col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
        for _, row in us_df.iterrows(): 
            raw_sym = str(row[col_sym])
            clean_sym = special_tickers.get(raw_sym, raw_sym.replace('.', '-').replace('/', '-'))
            all_stocks[clean_sym] = ('US', str(row[col_name]), clean_sym)
        all_stocks['SPLG'] = ('US', 'SPDR S&P 500 ETF', 'SPLG')
        all_stocks['QQQM'] = ('US', 'Invesco NASDAQ 100 ETF', 'QQQM')
        all_stocks['SOXX'] = ('US', 'iShares Semiconductor ETF', 'SOXX')
    except: pass

for t in portfolio.keys():
    if t not in all_stocks:
        m = 'KR_KOSPI' if t.endswith('.KS') else 'KR_KOSDAQ' if t.endswith('.KQ') else 'US'
        all_stocks[t] = (m, portfolio[t].get('name', t), t)

# ==========================================
# 🌟 5. 지표 계산 및 거래 판단 (💡 IP 밴 원천차단 안전수집 로직)
# ==========================================
data_store, prices_cache = {}, {}
fdr_start_date = (kr_time - timedelta(days=250)).strftime('%Y-%m-%d')
error_count = 0

print(f"⚡ 전체 시장 데이터({len(all_stocks)}개) 100% 안전 스캔 중... (API 보호를 위해 시간이 소요됩니다)")

for ticker, (market, name, code) in all_stocks.items():
    if ticker in cooldown_tracker and ticker not in portfolio: continue
    
    try:
        stock_data = pd.DataFrame()
        if market.startswith('KR'):
            for _ in range(3):
                try:
                    temp_data = fdr.DataReader(code.split('.')[0], start=fdr_start_date)
                    if not temp_data.empty and len(temp_data) > 120:
                        stock_data = temp_data
                        break
                except: pass
                time.sleep(0.1) 
        else:
            ticker_obj = yf.Ticker(ticker)
            for _ in range(3):
                try:
                    temp_data = ticker_obj.history(period='1y')
                    if not temp_data.empty and len(temp_data) > 120:
                        stock_data = temp_data
                        break
                except: pass
                time.sleep(0.3) 

        if stock_data.empty or len(stock_data) < 120: 
            error_count += 1
            continue 

        stock_data['MA10'] = stock_data['Close'].rolling(10).mean()
        stock_data['MA20'] = stock_data['Close'].rolling(20).mean()
        stock_data['MA120'] = stock_data['Close'].rolling(120).mean()
        stock_data['VolMA20'] = stock_data['Volume'].rolling(20).mean().shift(1)
        
        delta = stock_data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(2).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(2).mean()
        stock_data['RSI_2'] = (100 - (100 / (1 + (gain / loss.replace(0, float('nan')))))).fillna(50)
        stock_data['Recent20High'] = stock_data['High'].rolling(20).max().shift(1)
        
        data_store[ticker] = stock_data.dropna()
        prices_cache[ticker] = float(stock_data['Close'].iloc[-1])
        
    except: 
        error_count += 1
        continue

print(f"✅ 안전 스캔 완료! (성공: {len(data_store)}개 / 실패: {error_count}개)")

kr_candidates, us_candidates = [], []
def fmt_price(p, is_kr): return f"{p:,.0f}" if is_kr else f"{p:,.2f}"

if kis_token:
    # -----------------------------------
    # [A] 매도 심사 (스마트 트레일링 익절 탑재)
    # -----------------------------------
    for ticker in list(portfolio.keys()):
        if ticker not in data_store: continue
        df = data_store[ticker]
        pos = portfolio[ticker]
        
        market, name, _ = all_stocks[ticker]
        curr_price = float(df['Close'].iloc[-1])
        is_kr = market.startswith('KR')
        
        buy_price = float(pos.get('buy_price', 0))
        if buy_price <= 0: buy_price = curr_price
        
        hold_days = pos.get('hold_days', 0) + 1
        portfolio[ticker]['hold_days'] = hold_days
        
        profit_pct = ((curr_price / buy_price) - 1.0)
        sell_reason = None
        
        sl_pct = FIXED_STOP_LOSS_KR if is_kr else FIXED_STOP_LOSS_US
        sl_price = buy_price * (1.0 - sl_pct)
        
        if is_kr:
            tp_ma = float(df['MA10'].iloc[-1])
        else:
            tp_ma = float(df['MA10'].iloc[-1]) if profit_pct >= 0.10 else float(df['MA20'].iloc[-1])
        
        if curr_price <= sl_price: 
            sell_reason = f"하드스탑(-{sl_pct*100}%)"
            cooldown_tracker[ticker] = (kr_time + timedelta(days=5)).strftime('%Y-%m-%d')
        elif curr_price > buy_price and curr_price < tp_ma: 
            sell_reason = "스마트 이평선 익절" 
        elif hold_days >= MAX_HOLD_DAYS and curr_price <= buy_price: 
            sell_reason = "타임스탑 탈출"
                
        if sell_reason:
            res = execute_order(ticker, pos['units'], side="SELL", price=curr_price)
            if res['success']:
                sell_signals.append(f"🔴 청산: {name} | 사유: {sell_reason} | 수익: {profit_pct*100:+.2f}%")
                
                sell_amt = pos['units'] * curr_price * (1 if is_kr else EXCHANGE_RATE)
                fee_deduct = (KR_FEE + KR_TAX) if is_kr else (US_FEE + US_SEC_FEE)
                bot_cash += sell_amt * (1 - fee_deduct) 
                
                if is_kr: current_kr_positions -= 1
                else: current_us_positions -= 1
                del portfolio[ticker] 

    # -----------------------------------
    # [B] 매수 심사
    # -----------------------------------
    current_portfolio_value = sum(p['units'] * prices_cache[t] * (1 if str(p.get('market', '')).startswith('KR') else EXCHANGE_RATE) for t, p in portfolio.items() if t in prices_cache)
    
    total_bot_equity = bot_cash + current_portfolio_value
    target_pos_size_krw = total_bot_equity * POSITION_SIZE_RATIO 
    
    for ticker, df in data_store.items():
        if ticker in portfolio: continue
        market, name, _ = all_stocks[ticker]
        
        # 💡 [패치 2] 코스닥 종목이어도 무조건 코스피(KR) 방어막을 따르도록 강제 이식
        m_key = 'US' if market == 'US' else 'KR'
        if not macro_bull.get(m_key, True): continue 
        
        curr_price = float(df['Close'].iloc[-1])
        is_kr = market.startswith('KR')
        krw_price = curr_price if is_kr else curr_price * EXCHANGE_RATE
        
        if krw_price > target_pos_size_krw: continue
        unit_size = math.floor(target_pos_size_krw / krw_price)
        if unit_size == 0: continue
            
        ma_120 = float(df['MA120'].iloc[-1])

        if market == 'US':
            vol_cond = (float(df['Volume'].iloc[-1]) >= float(df['VolMA20'].iloc[-1]) * 1.2) if float(df['VolMA20'].iloc[-1]) > 0 else True
            if curr_price > ma_120 and curr_price >= float(df['Recent20High'].iloc[-1]) and vol_cond:
                us_candidates.append({'ticker': ticker, 'name': name, 'market': market, 'price': curr_price, 'units': unit_size, 'krw_price': krw_price, 'score': (curr_price / ma_120)})
        elif is_kr:
            rsi_2 = float(df['RSI_2'].iloc[-1])
            if curr_price > ma_120 and rsi_2 < 10.0:
                kr_candidates.append({'ticker': ticker, 'name': name, 'market': market, 'price': curr_price, 'units': unit_size, 'krw_price': krw_price, 'score': rsi_2})

    us_candidates.sort(key=lambda x: x['score'], reverse=True) 
    kr_candidates.sort(key=lambda x: x['score'])               
    
    for cand in (us_candidates + kr_candidates):
        is_kr = cand['market'].startswith('KR')
        if len(portfolio) >= MAX_POSITIONS: break
        if is_kr and current_kr_positions >= MAX_KR_POSITIONS: continue
        if not is_kr and current_us_positions >= MAX_US_POSITIONS: continue
            
        res = execute_order(cand['ticker'], cand['units'], side="BUY", price=cand['price'])
        if res['success']:
            tot_amt = int(cand['units'] * cand['krw_price'])
            buy_signals.append(f"🟢 매수: {cand['name']} | {fmt_price(cand['price'], is_kr)} x {cand['units']}주 (총 {tot_amt:,}원)")
            
            portfolio[cand['ticker']] = {
                'name': cand['name'], 'units': cand['units'], 'buy_price': cand['price'], 
                'market': cand['market'], 'buy_date': today_str, 'hold_days': 0
            }
            # 💡 매수 정밀 수수료 적용
            fee_add = KR_FEE if is_kr else US_FEE
            bot_cash -= (tot_amt * (1 + fee_add)) 
            
            if is_kr: current_kr_positions += 1
            else: current_us_positions += 1

# ==========================================
# 🌟 6. 시트 데이터 생성 및 디스코드 발송
# ==========================================
for ticker, pos in portfolio.items():
    cp = prices_cache.get(ticker, pos.get('buy_price', 0))
    bp = pos.get('buy_price', 0)
    units = pos.get('units', 0)
    ret_pct = ((cp / bp) - 1) * 100 if bp > 0 else 0
    sl_pct = FIXED_STOP_LOSS_KR if pos.get('market', '').startswith('KR') else FIXED_STOP_LOSS_US
    sl_price = bp * (1 - sl_pct)
    
    dashboard_list.append({
        "name": pos.get('name', ticker), "units": units, 
        "buy_price": round(bp, 2), "current_price": round(cp, 2), 
        "invested": round(bp * units, 2), "return_pct": round(ret_pct, 2), "stop_loss": round(sl_price, 2)
    })

msg_lines = [f"🤖 **V36.6 Safe Defender Live (코스피 통합방어막)** 🤖\n"]
msg_lines.append(f"💰 **추정 총자산:** 약 {int(total_bot_equity):,}원 (가용현금: {int(bot_cash):,}원)\n")

if not kis_token:
    msg_lines.append(f"🚨 **시스템 경보:** API 토큰 발급 실패")
else:
    if buy_signals or sell_signals:
        if buy_signals:
            msg_lines.append("**[🚀 오늘의 신규 매수 (서버 자동주문 필수!)]**")
            msg_lines.extend(buy_signals)
            msg_lines.append("")
        if sell_signals:
            msg_lines.append("**[💰 오늘의 청산/익절]**")
            msg_lines.extend(sell_signals)
            msg_lines.append("")
    else:
        msg_lines.append("💤 오늘 발생한 신규 매수/청산 신호가 없습니다.\n")

msg_lines.append(f"**[📊 상태 보고]** 정예 종목 {len(data_store)}개 스캔 완료 | 활성 쿨다운: {len(cooldown_tracker)}종목\n")

msg_lines.append("**[💼 현재 보유 포트폴리오]**")
if not portfolio:
    msg_lines.append("보유 중인 종목이 없습니다. (현금 대기 중)")
else:
    for ticker, pos in portfolio.items():
        cp = prices_cache.get(ticker, pos.get('buy_price', 0))
        bp = pos.get('buy_price', 0)
        ret = ((cp / bp) - 1) * 100 if bp > 0 else 0
        is_kr = pos.get('market', '').startswith('KR')
        sl_pct = FIXED_STOP_LOSS_KR if is_kr else FIXED_STOP_LOSS_US
        msg_lines.append(f"🔸 {pos.get('name')}: {fmt_price(bp, is_kr)} ➔ {fmt_price(cp, is_kr)} ({ret:+.2f}%) | 서버SL: {fmt_price(bp*(1-sl_pct), is_kr)}")

final_content = "\n".join(msg_lines)
if len(final_content) > 1900: final_content = final_content[:1850] + "\n\n... (글자수 제한으로 이하 생략)"

print("\n📡 디스코드 알림 발송 시도 중...")
try: 
    req = requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content}, timeout=10)
    if req.status_code in [200, 204]: print("✅ 디스코드 알림 발송 성공!")
    else: print(f"⚠️ 디스코드 발송 실패 (HTTP {req.status_code})")
except Exception as e: print(f"🚨 디스코드 통신 에러: {e}")

print("📡 구글 시트 데이터 전송 시도 중...")
if SHEET_WEBHOOK_URL:
    sheet_data = {
        "date": kr_time.strftime('%Y-%m-%d %H:%M:%S'), 
        "message": f"자산 {int(total_bot_equity):,}원 / 진입 {len(buy_signals)}건", 
        "dashboard": dashboard_list, 
        "portfolio": portfolio,
        "bot_cash": bot_cash,
        "cooldown_tracker": cooldown_tracker 
    }
    try: 
        req = requests.post(SHEET_WEBHOOK_URL, json=sheet_data, timeout=30)
        if req.status_code == 200: print("✅ 구글 시트 데이터 전송 성공!")
        else: print(f"⚠️ 구글 시트 전송 실패 (HTTP {req.status_code})")
    except Exception as e: print(f"🚨 구글 시트 통신 에러: {e}")

print("🏁 봇 실행 완료 (Exit Code 0)")
