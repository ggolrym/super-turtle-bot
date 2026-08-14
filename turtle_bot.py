# ==========================================
# 🚀 AI 하이브리드 터틀 봇 V35.0 (상세 브리핑 및 글자수 방어 패치)
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
import concurrent.futures
import warnings
import logging

warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# 🌟 1. 환경 변수 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip() # 호환성 유지를 위해 변수만 남김
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

if RUN_MARKET == 'KOSPI': target_market, market_title = 'KR_KOSPI', "🇰🇷 코스피 (트렌드 라이더)"
elif RUN_MARKET == 'KOSDAQ': target_market, market_title = 'KR_KOSDAQ', "🚀 코스닥 (트렌드 라이더)"
elif RUN_MARKET == 'US': target_market, market_title = 'US', "🇺🇸 미국장 (트렌드 라이더)"
else: target_market, market_title = 'ALL', "🌐 통합 트렌드 라이더 모드"

print(f"⏰ 현재 한국시간: {kr_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"🎯 V35.0 실전 라이브 가동: {market_title}\n")

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
    if qty <= 0: return {"success": False, "msg": "수량 부족(0주)"}
    time.sleep(0.5) 
    
    is_krw = ticker.endswith('.KS') or ticker.endswith('.KQ')
    clean_ticker = ticker.split('.')[0]
    clean_account = KIS_ACCOUNT.replace("-", "")
    cano = clean_account[:8]
    prdt_cd = clean_account[8:10] if len(clean_account) >= 10 else "01"
    tr_prefix = "V" if "openapivts" in KIS_URL else "T"
    headers = {"Content-Type": "application/json; charset=utf-8", "authorization": f"Bearer {kis_token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    
    if is_krw:
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
        if clean_ticker in ['SPLG', 'SPY', 'GLDM', 'GLD', 'TLT', 'DBC', 'VNQ', 'SH', 'PSQ', 'QQQM']: excg_cd = 'AMS'
            
        target_price = round(price, 2)
        body = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "OVRS_EXCG_CD": excg_cd, "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), "OVRS_ORD_UNPR": f"{target_price:.2f}", "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"}
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        data = res.json()
        if data.get("rt_cd") == "0": return {"success": True, "msg": "체결성공"}
        else: return {"success": False, "msg": f"거절({data.get('msg1')})"}
    except Exception as e: return {"success": False, "msg": f"에러"}

# ==========================================
# 🌟 3. 자본 세팅 및 독립 마켓 방어막
# ==========================================
TOTAL_CAPITAL = 500000        
MAX_POSITIONS = 4          
MAX_KR_POSITIONS = 2        
MAX_US_POSITIONS = 2        
POSITION_SIZE_KRW = TOTAL_CAPITAL * 0.25  

FIXED_STOP_LOSS_KR = 0.08  
FIXED_STOP_LOSS_US = 0.08  
MAX_HOLD_DAYS = 25         

buy_signals, sell_signals, skipped_signals = [], [], []
dashboard_list = [] 
portfolio = {}

def check_market_regime(index_ticker):
    try:
        if index_ticker.startswith('^'): df = yf.Ticker(index_ticker).history(period='1y')
        else: df = fdr.DataReader(index_ticker, start=(datetime.now() - timedelta(days=300)).strftime('%Y-%m-%d'))
        if df.empty: return True
        return float(df['Close'].iloc[-1]) >= float(df['Close'].rolling(200).mean().iloc[-1])
    except: return True

is_kospi_bullish = check_market_regime('KS11')
is_kosdaq_bullish = check_market_regime('KQ11')
is_us_bullish = check_market_regime('^GSPC')

# DB 보호막
db_loaded = False
if SHEET_WEBHOOK_URL:
    for attempt in range(3):
        try:
            res = requests.get(SHEET_WEBHOOK_URL, timeout=30, allow_redirects=True)
            if res.status_code == 200:
                raw_text = res.text.strip()
                if raw_text.startswith('{') and raw_text.endswith('}'):
                    data = json.loads(raw_text)
                    if isinstance(data, dict): portfolio = data.get('portfolio', data) 
                db_loaded = True
                break
            time.sleep(5)
        except: time.sleep(5)

if not db_loaded:
    try: requests.post(DISCORD_WEBHOOK_URL, json={"content": f"🚨 [{market_title}] 구글 DB 응답 없음. 봇 강제 종료."}, timeout=10)
    except: pass
    exit(1)

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
        if res.status_code == 200:
            kr_api_success = True
            for item in res.json().get('output1', []):
                if int(item.get('hldg_qty', 0)) > 0: kr_tickers[item.get('pdno')] = int(item.get('hldg_qty', 0))
    except: pass

    try: 
        headers["tr_id"] = f"{tr_prefix}TTS3012R"
        params = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "WCRC_FRS_EXCG_CD": "USD", "NATN_CD": "840", "TR_MKET_CD": "00", "INQR_DVSN_CD": "0"}
        res = requests.get(f"{KIS_URL}/uapi/overseas-stock/v1/trading/inquire-present-balance", headers=headers, params=params, timeout=10)
        if res.status_code == 200:
            us_api_success = True
            for item in res.json().get('output1', []):
                qty = int(float(item.get('ccld_qty_smtl1', 0)))
                if qty > 0:
                    sym = item.get('ovrs_pdno', '').replace('.', '-').replace('/', '-')
                    if sym: us_tickers[sym] = qty
    except: pass

    synced = {}
    today_str = kr_time.strftime('%Y-%m-%d')
    for t, p in current_portfolio.items():
        if not isinstance(p, dict): continue 
        clean_t = t.split('.')[0]
        if 'buy_price' not in p: p['buy_price'] = 0.0
        if 'units' not in p: p['units'] = 1
        if 'buy_date' not in p: p['buy_date'] = today_str
        if 'name' not in p: p['name'] = t
        
        is_kr = t.endswith('.KS') or t.endswith('.KQ')
        if is_kr:
            if not kr_api_success: synced[t] = p 
            elif clean_t in kr_tickers or t in kr_tickers:
                p['units'] = kr_tickers.get(clean_t, kr_tickers.get(t, p['units']))
                synced[t] = p
        else:
            if not us_api_success: synced[t] = p 
            elif clean_t in us_tickers or t in us_tickers:
                p['units'] = us_tickers.get(clean_t, us_tickers.get(t, p['units']))
                synced[t] = p
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

if target_market in ['US', 'ALL']:
    try:
        us_df = fdr.StockListing('SP500')
        col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
        col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
        special_tickers = {'BRKB': 'BRK-B', 'BFB': 'BF-B'}
        for _, row in us_df.iterrows(): 
            raw_sym = str(row[col_sym])
            clean_sym = special_tickers.get(raw_sym, raw_sym.replace('.', '-').replace('/', '-'))
            all_stocks[clean_sym] = ('US', str(row[col_name]), clean_sym)
        all_stocks['SPLG'] = ('US', 'SPDR S&P 500 ETF', 'SPLG')
        all_stocks['QQQ'] = ('US', 'Invesco QQQ Trust', 'QQQ')
        all_stocks['SOXX'] = ('US', 'iShares Semiconductor ETF', 'SOXX')
    except: pass

for t in portfolio.keys():
    if t not in all_stocks:
        m = 'KR_KOSPI' if t.endswith('.KS') else 'KR_KOSDAQ' if t.endswith('.KQ') else 'US'
        all_stocks[t] = (m, portfolio[t].get('name', t), t)

# ==========================================
# 🌟 5. 순차 데이터 수집 및 매매 심사
# ==========================================
data_store, prices_cache = {}, {}
fdr_start_date = (kr_time - timedelta(days=250)).strftime('%Y-%m-%d')

for ticker, (market, name, code) in all_stocks.items():
    try:
        stock_data = pd.DataFrame()
        if market.startswith('KR'):
            for _ in range(3):
                temp_data = fdr.DataReader(code.split('.')[0], start=fdr_start_date)
                if not temp_data.empty and len(temp_data) > 120:
                    stock_data = temp_data
                    break
                time.sleep(0.05) 
        else:
            ticker_obj = yf.Ticker(ticker)
            for _ in range(3):
                temp_data = ticker_obj.history(period='1y')
                if not temp_data.empty and len(temp_data) > 120:
                    stock_data = temp_data
                    break
                time.sleep(0.1) 

        if stock_data.empty or len(stock_data) < 120: continue 

        stock_data['MA10'] = stock_data['Close'].rolling(10).mean()
        stock_data['MA20'] = stock_data['Close'].rolling(20).mean()
        stock_data['MA120'] = stock_data['Close'].rolling(120).mean()
        delta = stock_data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(2).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(2).mean()
        stock_data['RSI_2'] = (100 - (100 / (1 + (gain / loss.replace(0, float('nan')))))).fillna(50)
        stock_data['Recent20High'] = stock_data['High'].rolling(20).max().shift(1)
        
        data_store[ticker] = stock_data.dropna()
        prices_cache[ticker] = float(stock_data['Close'].iloc[-1])
    except: continue

kr_candidates, us_candidates = [], []

def fmt_price(p, is_kr): return f"{p:,.0f}" if is_kr else f"{p:,.2f}"

if kis_token:
    for ticker, df in data_store.items():
        market, name, _ = all_stocks[ticker]
        curr_price = float(df['Close'].iloc[-1])
        is_kr = market.startswith('KR')
        krw_price = curr_price if is_kr else curr_price * 1350.0

        # [A] 매도 심사
        if ticker in portfolio:
            pos = portfolio[ticker]
            sell_reason = None
            buy_price = float(pos.get('buy_price', 0))
            if buy_price <= 0: buy_price = curr_price
            
            days_held = (kr_time.date() - datetime.strptime(pos.get('buy_date', kr_time.strftime('%Y-%m-%d')), '%Y-%m-%d').date()).days
            ma_10, ma_20 = float(df['MA10'].iloc[-1]), float(df['MA20'].iloc[-1])
            profit_pct = ((curr_price / buy_price) - 1) * 100

            if is_kr:
                sl_price = buy_price * (1.0 - FIXED_STOP_LOSS_KR)
                if curr_price <= sl_price: sell_reason = "손절(-6%)"
                elif curr_price > buy_price and curr_price < ma_10: sell_reason = "10일선 익절"
                elif days_held >= MAX_HOLD_DAYS and curr_price <= buy_price: sell_reason = "타임스탑"
            else:
                sl_price = buy_price * (1.0 - FIXED_STOP_LOSS_US)
                if curr_price <= sl_price: sell_reason = "손절(-8%)"
                elif curr_price > buy_price and curr_price < ma_20: sell_reason = "20일선 익절"
                elif days_held >= MAX_HOLD_DAYS and curr_price <= buy_price: sell_reason = "타임스탑"
                
            if sell_reason:
                res = execute_order(ticker, pos['units'], side="SELL", price=curr_price)
                if res['success']:
                    sell_signals.append(f"🔴 청산: {name} | 사유: {sell_reason} | 수익: {profit_pct:+.2f}%")
                    if is_kr: current_kr_positions -= 1
                    else: current_us_positions -= 1
                    del portfolio[ticker] 

        # [B] 매수 심사
        elif ticker not in portfolio:
            if krw_price > POSITION_SIZE_KRW: continue
            unit_size = math.floor(POSITION_SIZE_KRW / krw_price)
            if unit_size == 0: continue
            
            ma_120, rsi_2, r20h = float(df['MA120'].iloc[-1]), float(df['RSI_2'].iloc[-1]), float(df['Recent20High'].iloc[-1])

            if market == 'US' and target_market in ['US', 'ALL'] and is_us_bullish:
                if curr_price > ma_120 and curr_price >= r20h:
                    us_candidates.append({'ticker': ticker, 'name': name, 'market': 'US', 'price': curr_price, 'units': unit_size, 'krw_price': krw_price, 'score': (curr_price / ma_120)})
            elif market == 'KR_KOSPI' and target_market in ['KR_KOSPI', 'ALL'] and is_kospi_bullish:
                if curr_price > ma_120 and rsi_2 < 10.0:
                    kr_candidates.append({'ticker': ticker, 'name': name, 'market': market, 'price': curr_price, 'units': unit_size, 'krw_price': krw_price, 'score': rsi_2})
            elif market == 'KR_KOSDAQ' and target_market in ['KR_KOSDAQ', 'ALL'] and is_kosdaq_bullish:
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
            sl_pct = FIXED_STOP_LOSS_KR if is_kr else FIXED_STOP_LOSS_US
            sl_price = cand['price'] * (1 - sl_pct)
            tp_cond = "10일선" if is_kr else "20일선"
            tot_amt = int(cand['units'] * cand['krw_price'])
            
            buy_signals.append(f"🟢 매수: {cand['name']} | {fmt_price(cand['price'], is_kr)} x {cand['units']}주 (총 {tot_amt:,}원) | SL: {fmt_price(sl_price, is_kr)} | TP: {tp_cond}")
            
            portfolio[cand['ticker']] = {
                'name': cand['name'], 'units': cand['units'], 'buy_price': cand['price'], 
                'market': cand['market'], 'buy_date': kr_time.strftime('%Y-%m-%d')
            }
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

# 💡 [핵심 패치] 디스코드 텍스트 생성 (AI 생략, 1900자 제한 방어)
msg_lines = [f"🤖 **V35.0 실전 라이브 ({market_title})** 🤖\n"]

if not kis_token:
    msg_lines.append("🚨 **시스템 경보:** API 토큰 발급 실패 (매매 보류)")
else:
    if buy_signals or sell_signals:
        if buy_signals:
            msg_lines.append("**[🚀 오늘의 신규 매수]**")
            msg_lines.extend(buy_signals)
            msg_lines.append("")
        if sell_signals:
            msg_lines.append("**[💰 오늘의 청산/익절]**")
            msg_lines.extend(sell_signals)
            msg_lines.append("")
    else:
        msg_lines.append("💤 오늘 발생한 신규 매수/청산 신호가 없습니다.\n")

msg_lines.append("**[💼 현재 보유 포트폴리오]**")
if not portfolio:
    msg_lines.append("보유 중인 종목이 없습니다. (현금 100%)")
else:
    for ticker, pos in portfolio.items():
        cp = prices_cache.get(ticker, pos.get('buy_price', 0))
        bp = pos.get('buy_price', 0)
        ret = ((cp / bp) - 1) * 100 if bp > 0 else 0
        is_kr = pos.get('market', '').startswith('KR')
        sl_pct = FIXED_STOP_LOSS_KR if is_kr else FIXED_STOP_LOSS_US
        sl_price = bp * (1 - sl_pct)
        msg_lines.append(f"🔸 {pos.get('name')}: {fmt_price(bp, is_kr)} ➔ {fmt_price(cp, is_kr)} ({ret:+.2f}%) | SL: {fmt_price(sl_price, is_kr)}")

final_content = "\n".join(msg_lines)

# 2000자 초과 방어
if len(final_content) > 1900:
    final_content = final_content[:1850] + "\n\n... (글자수 제한으로 이하 생략)"

try: requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content}, timeout=10)
except Exception as e: print(f"🚨 디스코드 통신 에러: {e}")

if SHEET_WEBHOOK_URL:
    sheet_data = {"date": kr_time.strftime('%Y-%m-%d %H:%M:%S'), "message": f"진입 {len(buy_signals)}건, 청산 {len(sell_signals)}건", "dashboard": dashboard_list, "portfolio": portfolio}
    try: requests.post(SHEET_WEBHOOK_URL, json=sheet_data, timeout=30)
    except Exception as e: print(f"🚨 구글 시트 통신 에러: {e}")
