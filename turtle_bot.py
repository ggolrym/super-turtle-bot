# ==========================================
# 🚀 AI 하이브리드 터틀 봇 V36.6 Safe Defender Live
# (미장 모의투자 X-Ray 진단 패치 / 누락 변수 완벽 복원 🛡️)
# ==========================================
import os
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import requests
import time
import math
import json 
import re
import random
from datetime import datetime, timedelta
import pytz
import warnings
import logging

warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# 🌟 0. 핵심 스위치: 구글 시트 강제 초기화
FORCE_RESET_SHEET = True  

# 🌟 1. 환경 변수 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip() 
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
KIS_APP_KEY = os.environ.get("KIS_APP_KEY", "").strip()
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET", "").strip()
KIS_ACCOUNT = os.environ.get("KIS_ACCOUNT", "").strip()
SHEET_WEBHOOK_URL = os.environ.get("SHEET_WEBHOOK_URL", "").strip() 
RUN_MARKET = os.environ.get("RUN_MARKET", "AUTO").strip()

if not all([DISCORD_WEBHOOK_URL, KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT, SHEET_WEBHOOK_URL]):
    print("🚨 필수 API 키 누락!")
    exit(1)

KIS_URL = "https://openapivts.koreainvestment.com:29443" 
kr_time = datetime.now(pytz.timezone('Asia/Seoul'))
today_str = kr_time.strftime('%Y-%m-%d')

EXCHANGE_RATE = 1350.0
try:
    ex_df = fdr.DataReader('USD/KRW', start=(kr_time - timedelta(days=7)).strftime('%Y-%m-%d'))
    if not ex_df.empty: EXCHANGE_RATE = float(ex_df['Close'].iloc[-1])
except: pass

# 💡 [버그 픽스] 실수로 누락되었던 시장 구분 설정 4줄 복원 완료!
if RUN_MARKET == 'KOSPI': target_market, market_title = 'KR_KOSPI', "🇰🇷 코스피 전용"
elif RUN_MARKET == 'KOSDAQ': target_market, market_title = 'KR_KOSDAQ', "🚀 코스닥 전용"
elif RUN_MARKET == 'US': target_market, market_title = 'US', "🇺🇸 미국장 전용"
else: target_market, market_title = 'ALL', "🌐 통합장"

print(f"⏰ 현재 한국시간: {kr_time.strftime('%Y-%m-%d %H:%M:%S')} (적용 환율: {EXCHANGE_RATE:,.1f}원)")
print(f"🎯 V36.6 Safe Defender 가동 (4슬롯 분산 / 시트 강제초기화 모드: {FORCE_RESET_SHEET})\n")

def get_kis_token():
    url = f"{KIS_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    for attempt in range(3):
        try:
            res = requests.post(url, headers=headers, data=json.dumps(body), timeout=30)
            if res.status_code == 200: return res.json().get("access_token")
            time.sleep(2)
        except: time.sleep(2)
    return None

kis_token = get_kis_token()

def execute_order(ticker, qty, side="BUY", price=0.0):
    if not kis_token: return {"success": False, "msg": "토큰 없음"}
    if qty <= 0: return {"success": False, "msg": "수량 부족"}
    time.sleep(0.5) 
    
    is_kr = ticker.endswith('.KS') or ticker.endswith('.KQ')
    clean_ticker = ticker.split('.')[0]
    cano = KIS_ACCOUNT.replace("-", "")[:8]
    prdt_cd = KIS_ACCOUNT.replace("-", "")[8:10] if len(KIS_ACCOUNT.replace("-", "")) >= 10 else "01"
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
        if clean_ticker in ['SPLG', 'QQQM', 'SOXX', 'SPY', 'GLDM', 'GLD', 'TLT', 'DBC', 'VNQ', 'SH', 'PSQ']: excg_cd = 'AMS'
        body = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "OVRS_EXCG_CD": excg_cd, "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), "OVRS_ORD_UNPR": f"{round(price, 2):.2f}", "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"}
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        data = res.json()
        if data.get("rt_cd") == "0": return {"success": True, "msg": "체결성공"}
        else: return {"success": False, "msg": f"거절({data.get('msg1')})"}
    except Exception: return {"success": False, "msg": f"통신에러"}

INITIAL_CAPITAL = 500000         
POSITION_SIZE_RATIO = 0.25       
MAX_PRICE_LIMIT = 150000         
MAX_POSITIONS = 4                
MAX_KR_POSITIONS = 2             
MAX_US_POSITIONS = 2             

FIXED_STOP_LOSS_KR = 0.08  
FIXED_STOP_LOSS_US = 0.08   
MAX_HOLD_DAYS = 20         

KR_FEE, KR_KOSPI_TAX, KR_KOSDAQ_TAX = 0.00015, 0.0020, 0.0020
US_FEE, US_SEC_FEE = 0.0025, 0.0000206 

buy_signals, sell_signals = [], []
dashboard_list = [] 
portfolio = {}
bot_cash = INITIAL_CAPITAL 
cooldown_tracker = {} 
yearly_us_profit = 0
current_year = kr_time.year
us_balance_error_log = "" 
us_xray_logs = []

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

macro_bull = {'KR': check_macro_regime('KQ11'), 'US': check_macro_regime('^GSPC')}

if SHEET_WEBHOOK_URL:
    for attempt in range(3):
        try:
            res = requests.get(SHEET_WEBHOOK_URL, timeout=30)
            if res.status_code == 200:
                data = json.loads(res.text.strip())
                if FORCE_RESET_SHEET:
                    portfolio, cooldown_tracker, bot_cash = {}, {}, INITIAL_CAPITAL
                else:
                    portfolio = data.get('portfolio', data) 
                    cooldown_tracker = data.get('cooldown_tracker', {})
                    if 'bot_cash' in data: bot_cash = float(data['bot_cash'])
                break
            time.sleep(5)
        except: time.sleep(5)

active_cooldowns = {t: exp for t, exp in cooldown_tracker.items() if datetime.strptime(exp, '%Y-%m-%d').date() > kr_time.date()}
cooldown_tracker = active_cooldowns

def sync_portfolio_with_kis_balance(current_portfolio):
    global bot_cash, us_balance_error_log, us_xray_logs
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
        if data.get('rt_cd') == '0':
            kr_api_success = True
            for item in data.get('output1', []):
                qty = int(item.get('hldg_qty', 0))
                if qty > 0: kr_tickers[item.get('pdno')] = {'name': item.get('prdt_name', item.get('pdno')), 'qty': qty, 'avg_price': float(item.get('pchs_avg_pric', 0))}
    except: pass

    # 2. 💡 미국장 잔고 조회 (초당 요청 초과 방지 1초 딜레이 및 시장 코드 보강)
    for excg in ["NAS", "NYS", "AMS"]:
        time.sleep(1.0)  # 👈 초당 거래건수 초과 방지 필수 딜레이 (1초 휴식)
        try: 
            headers["tr_id"] = f"{tr_prefix}TTS3012R"
            params = {
                "CANO": cano, 
                "ACNT_PRDT_CD": prdt_cd, 
                "OVRS_EXCG_CD": excg,
                "TR_CRCY_CD": "USD",
                "TR_MKET_CD": "00",  # 👈 전체 시장 대상
                "CTX_AREA_FK200": "", 
                "CTX_AREA_NK200": ""
            }
            res = requests.get(f"{KIS_URL}/uapi/overseas-stock/v1/trading/inquire-present-balance", headers=headers, params=params, timeout=10)
            data = res.json()
            if data.get('rt_cd') == '0':
                us_api_success = True
                items = data.get('output1', [])
                us_xray_logs.append(f"{excg}: {len(items)}개")
                
                for item in items:
                    qty = 0
                    for k, v in item.items():
                        if ('qty' in k or 'cblc' in k) and str(v).replace('.', '', 1).isdigit():
                            if float(v) > qty: qty = float(v)
                    
                    if qty > 0:
                        sym = item.get('ovrs_pdno', '').replace('.', '-').replace('/', '-')
                        name = item.get('ovrs_item_name', item.get('prdt_name', sym))
                        if sym: 
                            us_tickers[sym] = {'name': name, 'qty': int(qty), 'avg_price': float(item.get('pchs_avg_pric', 0))}
            else:
                err_msg = data.get('msg1', '에러 불명')
                us_xray_logs.append(f"{excg}: 실패({err_msg})")
                if not us_api_success: 
                    us_balance_error_log = err_msg
        except Exception as e: 
            us_xray_logs.append(f"{excg}: 통신에러")
            if not us_api_success: 
                us_balance_error_log = str(e)

    synced = {}
    for t, p in current_portfolio.items():
        if not isinstance(p, dict): continue 
        clean_t = t.split('.')[0]
        is_kr = t.endswith('.KS') or t.endswith('.KQ')
        
        if is_kr and kr_api_success and (clean_t not in kr_tickers and t not in kr_tickers):
            sell_signals.append(f"🔪 서버 장중 손절 감지: {p.get('name')} (현금 회수 완료)")
            bot_cash += (p['units'] * p['buy_price'] * (1 - FIXED_STOP_LOSS_KR) * (1 - KR_FEE - KR_KOSPI_TAX))
            cooldown_tracker[t] = (kr_time + timedelta(days=5)).strftime('%Y-%m-%d')
            continue
            
        if not is_kr and us_api_success and (clean_t not in us_tickers and t not in us_tickers):
            sell_signals.append(f"🔪 서버 장중 손절 감지: {p.get('name')} (현금 회수 완료)")
            bot_cash += (p['units'] * p['buy_price'] * (1 - FIXED_STOP_LOSS_US) * (1 - US_FEE - 0.0000206) * EXCHANGE_RATE)
            cooldown_tracker[t] = (kr_time + timedelta(days=5)).strftime('%Y-%m-%d')
            continue
            
        if is_kr:
            if not kr_api_success: 
                synced[t] = p; continue
            match_k = clean_t if clean_t in kr_tickers else t
            p['units'] = kr_tickers[match_k]['qty']
            if p.get('buy_price', 0) == 0: p['buy_price'] = kr_tickers[match_k]['avg_price']
            synced[t] = p
            del kr_tickers[match_k] 
        else:
            if not us_api_success: 
                synced[t] = p; continue
            match_k = clean_t if clean_t in us_tickers else t
            p['units'] = us_tickers[match_k]['qty']
            if p.get('buy_price', 0) == 0: p['buy_price'] = us_tickers[match_k]['avg_price']
            synced[t] = p
            del us_tickers[match_k] 

    if us_api_success:
        for sym, data in us_tickers.items(): synced[sym] = {'name': data['name'], 'units': data['qty'], 'buy_price': data['avg_price'], 'market': 'US', 'buy_date': today_str, 'hold_days': 0}
    if kr_api_success:
        for code, data in kr_tickers.items(): synced[f"{code}.KS"] = {'name': data['name'], 'units': data['qty'], 'buy_price': data['avg_price'], 'market': 'KR_KOSPI', 'buy_date': today_str, 'hold_days': 0}
    
    if FORCE_RESET_SHEET:
        invested = sum(p['buy_price'] * p['units'] * (1 if str(p['market']).startswith('KR') else EXCHANGE_RATE) for p in synced.values())
        bot_cash = INITIAL_CAPITAL - invested

    return synced

portfolio = sync_portfolio_with_kis_balance(portfolio)
current_kr_positions = sum(1 for p in portfolio.values() if isinstance(p, dict) and p.get('market', '').startswith('KR'))
current_us_positions = sum(1 for p in portfolio.values() if isinstance(p, dict) and p.get('market') == 'US')

MIN_TURNOVER_KRW, MIN_PRICE_KRW = 10000000000, 1000           
all_stocks = {}

print(f"⏳ 유니버스 사전 필터링 중... ({market_title})")

def get_naver_universe(sosok, suffix, market_tag):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    for page in range(1, 5): 
        try:
            url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
            res = requests.get(url, headers=headers, timeout=10)
            matches = re.findall(r'href="/item/main\.naver\?code=(\d{6})" class="tltle">(.*?)</a>', res.text)
            for code, name in matches: all_stocks[f"{code}{suffix}"] = (market_tag, name, f"{code}{suffix}")
            time.sleep(random.uniform(0.5, 1.5)) 
        except Exception: pass

if target_market in ['KR_KOSPI', 'ALL']: get_naver_universe(0, '.KS', 'KR_KOSPI')
if target_market in ['KR_KOSDAQ', 'ALL']: get_naver_universe(1, '.KQ', 'KR_KOSDAQ')

if target_market in ['US', 'ALL']:
    try:
        us_df = fdr.StockListing('SP500')
        col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
        col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
        for _, row in us_df.iterrows(): 
            raw_sym = str(row[col_sym])
            clean_sym = {'BRKB': 'BRK-B', 'BFB': 'BF-B'}.get(raw_sym, raw_sym.replace('.', '-').replace('/', '-'))
            all_stocks[clean_sym] = ('US', str(row[col_name]), clean_sym)
    except: pass
    for etf in ['SPLG', 'QQQM', 'SOXX']: all_stocks[etf] = ('US', etf, etf)

for t in portfolio.keys():
    if t not in all_stocks:
        m = 'KR_KOSPI' if t.endswith('.KS') else 'KR_KOSDAQ' if t.endswith('.KQ') else 'US'
        all_stocks[t] = (m, portfolio[t].get('name', t), t)

data_store, prices_cache = {}, {}
fdr_start_date = (kr_time - timedelta(days=250)).strftime('%Y-%m-%d')
error_count = 0

shuffled_stocks = list(all_stocks.items())
random.shuffle(shuffled_stocks)

for i, (ticker, (market, name, code)) in enumerate(shuffled_stocks):
    if (i + 1) % 100 == 0: print(f"🔄 스캐닝 진행 중... ({i + 1}/{len(shuffled_stocks)}) 종목 완료")
    if ticker in cooldown_tracker and ticker not in portfolio: continue
    
    try:
        stock_data = pd.DataFrame()
        if market.startswith('KR'):
            for _ in range(3):
                try:
                    temp_data = fdr.DataReader(code.split('.')[0], start=fdr_start_date)
                    if not temp_data.empty and len(temp_data) > 120:
                        stock_data = temp_data; break
                except: pass
                time.sleep(random.uniform(0.2, 0.6)) 
        else:
            ticker_obj = yf.Ticker(ticker)
            for _ in range(3):
                try:
                    temp_data = ticker_obj.history(period='1y')
                    if not temp_data.empty and len(temp_data) > 120:
                        stock_data = temp_data; break
                except: pass
                time.sleep(random.uniform(0.4, 0.9)) 

        if stock_data.empty or len(stock_data) < 120: continue 

        current_price = float(stock_data['Close'].iloc[-1])
        avg_volume = float(stock_data['Volume'].iloc[-20:].mean())
        if market.startswith('KR') and (current_price < MIN_PRICE_KRW or (current_price * avg_volume) < MIN_TURNOVER_KRW): continue

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
        prices_cache[ticker] = float(data_store[ticker]['Close'].iloc[-1]) 
    except: continue

kr_candidates, us_candidates = [], []
def fmt_price(p, is_kr): return f"{p:,.0f}" if is_kr else f"{p:,.2f}"

total_bot_equity = bot_cash + sum(p['units'] * prices_cache.get(t, p.get('buy_price', 0)) * (1 if str(p.get('market', '')).startswith('KR') else EXCHANGE_RATE) for t, p in portfolio.items())

if kis_token:
    for ticker in list(portfolio.keys()):
        if ticker not in data_store: continue
        df = data_store[ticker]
        pos = portfolio[ticker]
        
        market, name, _ = all_stocks[ticker]
        curr_price = float(df['Close'].iloc[-1])
        is_kr = market.startswith('KR')
        
        buy_price = float(pos.get('buy_price', 0))
        if buy_price <= 0: buy_price = curr_price
        
        portfolio[ticker]['hold_days'] = pos.get('hold_days', 0) + 1
        
        sl_pct = FIXED_STOP_LOSS_KR if is_kr else FIXED_STOP_LOSS_US
        tp_ma = float(df['MA10'].iloc[-1]) if is_kr else (float(df['MA10'].iloc[-1]) if ((curr_price / buy_price) - 1.0) >= 0.10 else float(df['MA20'].iloc[-1]))
        
        sell_reason = None
        if curr_price <= buy_price * (1.0 - sl_pct): sell_reason = f"하드스탑(-{sl_pct*100}%)"
        elif curr_price > buy_price and curr_price < tp_ma: sell_reason = "스마트 이평선 익절" 
        elif pos['hold_days'] >= MAX_HOLD_DAYS and curr_price <= buy_price: sell_reason = "타임스탑 탈출"
                
        if sell_reason:
            res = execute_order(ticker, pos['units'], side="SELL", price=curr_price)
            if res['success']:
                sell_signals.append(f"🔴 청산: {name} | 사유: {sell_reason}")
                bot_cash += pos['units'] * curr_price * (1 if is_kr else EXCHANGE_RATE) * (1 - ((KR_FEE + KR_KOSPI_TAX) if is_kr else (US_FEE + 0.0000206))) 
                if is_kr: current_kr_positions -= 1
                else: current_us_positions -= 1
                del portfolio[ticker] 

    target_pos_size_krw = total_bot_equity * POSITION_SIZE_RATIO 
    for ticker, df in data_store.items():
        if ticker in portfolio: continue
        market, name, _ = all_stocks[ticker]
        if not macro_bull.get('US' if market == 'US' else 'KR', True): continue 
        
        curr_price = float(df['Close'].iloc[-1])
        is_kr = market.startswith('KR')
        krw_price = curr_price if is_kr else curr_price * EXCHANGE_RATE
        
        if krw_price > MAX_PRICE_LIMIT or krw_price > target_pos_size_krw: continue 
        unit_size = math.floor(target_pos_size_krw / krw_price)
        if unit_size == 0: continue
            
        ma_120 = float(df['MA120'].iloc[-1])

        if market == 'US':
            vol_cond = (float(df['Volume'].iloc[-1]) >= float(df['VolMA20'].iloc[-1]) * 1.2) if float(df['VolMA20'].iloc[-1]) > 0 else True
            if curr_price > ma_120 and curr_price >= float(df['Recent20High'].iloc[-1]) and vol_cond:
                us_candidates.append({'ticker': ticker, 'name': name, 'market': market, 'price': curr_price, 'units': unit_size, 'krw_price': krw_price, 'score': (curr_price / ma_120)})
        elif is_kr:
            if curr_price > ma_120 and float(df['RSI_2'].iloc[-1]) < 10.0:
                kr_candidates.append({'ticker': ticker, 'name': name, 'market': market, 'price': curr_price, 'units': unit_size, 'krw_price': krw_price, 'score': float(df['RSI_2'].iloc[-1])})

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
            buy_signals.append(f"🟢 매수: {cand['name']} | {fmt_price(cand['price'], is_kr)} x {cand['units']}주")
            portfolio[cand['ticker']] = {'name': cand['name'], 'units': cand['units'], 'buy_price': cand['price'], 'market': cand['market'], 'buy_date': today_str, 'hold_days': 0}
            bot_cash -= (tot_amt * (1 + (KR_FEE if is_kr else US_FEE))) 
            if is_kr: current_kr_positions += 1
            else: current_us_positions += 1

for ticker, pos in portfolio.items():
    cp = prices_cache.get(ticker, pos.get('buy_price', 0))
    bp = pos.get('buy_price', 0)
    units = pos.get('units', 0)
    ret_pct = ((cp / bp) - 1) * 100 if bp > 0 else 0
    is_kr = pos.get('market', '').startswith('KR')
    sl_pct = FIXED_STOP_LOSS_KR if is_kr else FIXED_STOP_LOSS_US
    
    trend_exit_price = 0
    if ticker in data_store:
        trend_exit_price = float(data_store[ticker]['MA10'].iloc[-1]) if is_kr else (float(data_store[ticker]['MA10'].iloc[-1]) if ret_pct >= 10.0 else float(data_store[ticker]['MA20'].iloc[-1]))
    
    dashboard_list.append({"name": pos.get('name', ticker), "units": units, "buy_price": round(bp, 2), "current_price": round(cp, 2), "invested": round(bp * units, 2), "return_pct": round(ret_pct, 2), "stop_loss": round(bp * (1 - sl_pct), 2), "trend_exit": round(trend_exit_price, 2)})

msg_lines = [f"🤖 **V36.6 Safe Defender Live** 🤖\n"]
if FORCE_RESET_SHEET: msg_lines.append("⚠️ **주의:** 현재 시트 강제 초기화 모드가 켜져있습니다. 이 알림을 확인 후 반드시 `FORCE_RESET_SHEET = False`로 변경하세요!\n")
msg_lines.append(f"💰 **추정 총자산:** 약 {int(total_bot_equity):,}원 (가용현금: {int(bot_cash):,}원)")

if us_xray_logs: msg_lines.append(f"🔍 **[미장 API 엑스레이]** {' / '.join(us_xray_logs)}")
if us_balance_error_log: msg_lines.append(f"⚠️ **미장 잔고 API 통신 경고:** {us_balance_error_log}\n")

if not kis_token: msg_lines.append(f"🚨 **시스템 경보:** API 토큰 발급 실패")
else:
    if buy_signals or sell_signals:
        if buy_signals:
            msg_lines.append("**[🚀 오늘의 신규 매수]**")
            msg_lines.extend(buy_signals); msg_lines.append("")
        if sell_signals:
            msg_lines.append("**[💰 오늘의 청산/익절]**")
            msg_lines.extend(sell_signals); msg_lines.append("")
    else: msg_lines.append("💤 오늘 발생한 신규 매수/청산 신호가 없습니다.\n")

msg_lines.append("**[💼 현재 보유 포트폴리오]**")
if not portfolio: msg_lines.append("보유 중인 종목이 없습니다. (현금 대기 중)")
else:
    for d in dashboard_list:
        msg_lines.append(f"🔸 {d['name']}: {fmt_price(d['buy_price'], d['name'][-1] in 'SQ')} ➔ {fmt_price(d['current_price'], d['name'][-1] in 'SQ')} ({d['return_pct']:+.2f}%)")

final_content = "\n".join(msg_lines)
if len(final_content) > 1900: final_content = final_content[:1850] + "\n\n... (생략)"

try: requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content}, timeout=10)
except: pass

if SHEET_WEBHOOK_URL:
    try: requests.post(SHEET_WEBHOOK_URL, json={"date": kr_time.strftime('%Y-%m-%d %H:%M:%S'), "message": "강제초기화 완료" if FORCE_RESET_SHEET else "정상동기화", "dashboard": dashboard_list, "portfolio": portfolio, "bot_cash": bot_cash, "cooldown_tracker": cooldown_tracker, "yearly_us_profit": yearly_us_profit, "current_year": current_year}, timeout=30)
    except: pass

print("🏁 봇 실행 완료 (Exit Code 0)")
