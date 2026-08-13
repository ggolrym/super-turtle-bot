# ==========================================
# 🚀 AI 하이브리드 터틀 봇 V35.0 (트렌드 라이더 - 실전 EOD 라이브)
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
KIS_URL = "https://openapivts.koreainvestment.com:29443" # 모의투자 전용 도메인

kr_time = datetime.now(pytz.timezone('Asia/Seoul'))

if RUN_MARKET == 'KOSPI': target_market, market_title = 'KR_KOSPI', "🇰🇷 코스피 (트렌드 라이더)"
elif RUN_MARKET == 'KOSDAQ': target_market, market_title = 'KR_KOSDAQ', "🚀 코스닥 (트렌드 라이더)"
elif RUN_MARKET == 'US': target_market, market_title = 'US', "🇺🇸 미국장 (트렌드 라이더)"
else: target_market, market_title = 'ALL', "🌐 통합 트렌드 라이더 모드"

print(f"⏰ 현재 한국시간: {kr_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"🎯 V35.0 트렌드 라이더 가동: {market_title}\n")

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
# 🌟 3. 마켓 레짐(독립 200일선 방어막) 및 자본 세팅
# ==========================================
TOTAL_CAPITAL = 500000      
MAX_POSITIONS = 4          
MAX_KR_POSITIONS = 2        
MAX_US_POSITIONS = 2        
POSITION_SIZE_KRW = TOTAL_CAPITAL * 0.25 

# V35.0 트렌드 라이더 파라미터
FIXED_STOP_LOSS_KR = 0.06  # 한국장 고정 손절 (-6%)
FIXED_STOP_LOSS_US = 0.08  # 미국장 고정 손절 (-8%)
MAX_HOLD_DAYS = 20         # 20거래일 무수익 타임스탑

buy_signals, sell_signals, skipped_signals = [], [], []
dashboard_list = [] 
portfolio = {}

def check_market_regime(index_ticker):
    try:
        if index_ticker.startswith('^'): 
            df = yf.Ticker(index_ticker).history(period='1y')
        else: 
            df = fdr.DataReader(index_ticker, start=(datetime.now() - timedelta(days=300)).strftime('%Y-%m-%d'))
            
        if df.empty: return True
        return float(df['Close'].iloc[-1]) >= float(df['Close'].rolling(200).mean().iloc[-1])
    except: return True

is_kospi_bullish = check_market_regime('KS11')
is_kosdaq_bullish = check_market_regime('KQ11')
is_us_bullish = check_market_regime('^GSPC')

print(f"🛡️ 독립 방어막(200일선) 상태:")
print(f"   - 🇰🇷 코스피: {'🟢 상승장 (매수 허용)' if is_kospi_bullish else '🔴 하락장 (매수 차단)'}")
print(f"   - 🚀 코스닥: {'🟢 상승장 (매수 허용)' if is_kosdaq_bullish else '🔴 하락장 (매수 차단)'}")
print(f"   - 🇺🇸 미국장: {'🟢 상승장 (매수 허용)' if is_us_bullish else '🔴 하락장 (매수 차단)'}\n")

if SHEET_WEBHOOK_URL:
    for attempt in range(3):
        try:
            res = requests.get(SHEET_WEBHOOK_URL, timeout=30)
            if res.status_code == 200:
                data = json.loads(res.text.strip())
                if isinstance(data, dict): portfolio = data.get('portfolio', data) 
                break
        except: time.sleep(5)

def sync_portfolio_with_kis_balance(current_portfolio):
    if not kis_token: return current_portfolio
    clean_account = KIS_ACCOUNT.replace("-", "").strip()
    cano, prdt_cd = clean_account[:8], (clean_account[8:10] if len(clean_account) >= 10 else "01")
    tr_prefix = "V" if "openapivts" in KIS_URL else "T"
    
    kr_tickers, us_tickers = {}, {}
    headers = {"Content-Type": "application/json; charset=utf-8", "authorization": f"Bearer {kis_token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    
    try: 
        headers["tr_id"] = f"{tr_prefix}TTC8434R"
        params = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "01", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}
        res = requests.get(f"{KIS_URL}/uapi/domestic-stock/v1/trading/inquire-balance", headers=headers, params=params, timeout=10)
        for item in res.json().get('output1', []):
            if int(item.get('hldg_qty', 0)) > 0: kr_tickers[item.get('pdno')] = int(item.get('hldg_qty', 0))
    except: pass

    try: 
        headers["tr_id"] = f"{tr_prefix}TTS3012R"
        params = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "WCRC_FRS_EXCG_CD": "USD", "NATN_CD": "840", "TR_MKET_CD": "00", "INQR_DVSN_CD": "0"}
        res = requests.get(f"{KIS_URL}/uapi/overseas-stock/v1/trading/inquire-present-balance", headers=headers, params=params, timeout=10)
        for item in res.json().get('output1', []):
            qty = int(float(item.get('ccld_qty_smtl1', 0)))
            if qty > 0:
                sym = item.get('ovrs_pdno', '').replace('.', '-').replace('/', '-')
                if sym: us_tickers[sym] = qty
    except: pass

    synced = {}
    today_str = kr_time.strftime('%Y-%m-%d')
    for t, p in current_portfolio.items():
        clean_t = t.split('.')[0]
        if 'buy_date' not in p: p['buy_date'] = today_str # 기존 장부에 없으면 오늘로 초기화
        
        if t.endswith('.KS') or t.endswith('.KQ'):
            if clean_t in kr_tickers or t in kr_tickers:
                p['units'] = kr_tickers.get(clean_t, kr_tickers.get(t, p['units']))
                synced[t] = p
            else: skipped_signals.append(f"- 🔄 [{p.get('name', t)}] 계좌 잔고 없음 ➞ 장부 삭제")
        else:
            if clean_t in us_tickers or t in us_tickers:
                p['units'] = us_tickers.get(clean_t, us_tickers.get(t, p['units']))
                synced[t] = p
            else: skipped_signals.append(f"- 🔄 [{p.get('name', t)}] 계좌 잔고 없음 ➞ 장부 삭제")
    return synced

portfolio = sync_portfolio_with_kis_balance(portfolio)
current_kr_positions = sum(1 for p in portfolio.values() if p.get('market', '').startswith('KR'))
current_us_positions = sum(1 for p in portfolio.values() if p.get('market') == 'US')

# ==========================================
# 🌟 4. 유니버스 구축 및 트렌드 라이더 엔진 작동
# ==========================================
tickers_dict = {}
if target_market in ['KR_KOSPI', 'ALL']:
    try:
        for _, row in fdr.StockListing('KOSPI').head(150).iterrows(): tickers_dict[str(row['Code']).zfill(6) + '.KS'] = ('KR_KOSPI', row['Name'], str(row['Code']).zfill(6))
    except: pass
if target_market in ['KR_KOSDAQ', 'ALL']:
    try:
        for _, row in fdr.StockListing('KOSDAQ').head(150).iterrows(): tickers_dict[str(row['Code']).zfill(6) + '.KQ'] = ('KR_KOSDAQ', row['Name'], str(row['Code']).zfill(6))
    except: pass
if target_market in ['US', 'ALL']:
    us_tickers = ['SPLG', 'QQQ', 'SOXX']
    tickers_dict['SPLG'] = ('US', 'SPDR S&P 500 ETF', 'SPLG')
    tickers_dict['QQQ'] = ('US', 'Invesco QQQ Trust', 'QQQ')
    tickers_dict['SOXX'] = ('US', 'iShares Semiconductor ETF', 'SOXX')
    try:
        us_df = fdr.StockListing('SP500')
        col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
        for _, row in us_df.iterrows():
            sym = str(row[col_sym]).replace('.', '-').replace('/', '-')
            if sym not in ['BRK-B', 'BF-B']: tickers_dict[sym] = ('US', str(row['Name'] if 'Name' in us_df.columns else us_df.columns[1]), sym)
    except: pass

data_store, kr_candidates, us_candidates, prices_cache = {}, [], [], {}
fdr_start_date = (kr_time - timedelta(days=250)).strftime('%Y-%m-%d')

if kis_token:
    for ticker, (market, name, code) in tickers_dict.items():
        try:
            is_kr = market.startswith('KR')
            if is_kr:
                df = fdr.DataReader(code, start=fdr_start_date)
            else:
                df = yf.Ticker(ticker).history(period='1y')
                
            if df.empty or len(df) < 120: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=['Close'])
            
            curr_price = float(df['Close'].iloc[-1])
            prices_cache[ticker] = curr_price
            
            # 기술적 지표 계산 (MA10, MA20 추세선 포함)
            ma_10 = float(df['Close'].rolling(10).mean().iloc[-1])
            ma_20 = float(df['Close'].rolling(20).mean().iloc[-1])
            ma_120 = float(df['Close'].rolling(120).mean().iloc[-1])
            delta = df['Close'].diff()
            rs = (delta.where(delta > 0, 0)).rolling(2).mean() / (-delta.where(delta < 0, 0)).rolling(2).mean().replace(0, float('nan'))
            rsi_2 = float((100 - (100 / (1 + rs))).fillna(50).iloc[-1])
            recent_20_high = float(df['High'].iloc[-21:-1].max())
            
            # [A] 매도 로직 (고정 손절 + 추세 익절 + 무수익 타임스탑)
            if ticker in portfolio:
                pos = portfolio[ticker]
                sell_reason = None
                
                # 보유일수 계산
                buy_dt = datetime.strptime(pos.get('buy_date', kr_time.strftime('%Y-%m-%d')), '%Y-%m-%d')
                days_held = (kr_time.date() - buy_dt.date()).days
                
                if is_kr:
                    sl_price = pos['buy_price'] * (1.0 - FIXED_STOP_LOSS_KR)
                    if curr_price <= sl_price:
                        sell_reason = f"🔪 한국장 -{int(FIXED_STOP_LOSS_KR*100)}% 고정 손절"
                    elif curr_price > pos['buy_price'] and curr_price < ma_10:
                        sell_reason = "📈 한국장 10일선 추세 이탈 (익절)"
                    elif days_held >= MAX_HOLD_DAYS and curr_price <= pos['buy_price']:
                        sell_reason = f"⏳ 무수익 {MAX_HOLD_DAYS}일 타임스탑 (현금화)"
                else:
                    sl_price = pos['buy_price'] * (1.0 - FIXED_STOP_LOSS_US)
                    if curr_price <= sl_price:
                        sell_reason = f"🔪 미국장 -{int(FIXED_STOP_LOSS_US*100)}% 고정 손절"
                    elif curr_price > pos['buy_price'] and curr_price < ma_20:
                        sell_reason = "📈 미국장 20일선 추세 이탈 (익절)"
                    elif days_held >= MAX_HOLD_DAYS and curr_price <= pos['buy_price']:
                        sell_reason = f"⏳ 무수익 {MAX_HOLD_DAYS}일 타임스탑 (현금화)"
                    
                if sell_reason:
                    order_res = execute_order(ticker, pos['units'], side="SELL", price=curr_price)
                    sell_signals.append(f"- [{name}] {sell_reason} ({pos['units']}주) ➞ {order_res['msg']}")
                    if order_res['success']:
                        if is_kr: current_kr_positions -= 1
                        else: current_us_positions -= 1
                        del portfolio[ticker] 

            # [B] 매수 로직 (독립 마켓 방어막 연동)
            elif ticker not in portfolio:
                krw_price = curr_price if is_kr else curr_price * 1350.0
                if krw_price > POSITION_SIZE_KRW: continue
                unit_size = math.floor(POSITION_SIZE_KRW / krw_price)
                if unit_size == 0: continue
                
                # 1. 미국장 매수 (S&P500 상승장 + 신고가 돌파)
                if market == 'US' and target_market in ['US', 'ALL'] and is_us_bullish:
                    if curr_price > ma_120 and curr_price >= recent_20_high:
                        us_candidates.append({'ticker': ticker, 'name': name, 'market': 'US', 'price': curr_price, 'units': unit_size, 'score': (curr_price / ma_120)})
                
                # 2. 코스피 매수 (코스피 상승장 + RSI 패닉 줍기)
                elif market == 'KR_KOSPI' and target_market in ['KR_KOSPI', 'ALL'] and is_kospi_bullish:
                    if curr_price > ma_120 and rsi_2 < 10.0:
                        kr_candidates.append({'ticker': ticker, 'name': name, 'market': market, 'price': curr_price, 'units': unit_size, 'score': rsi_2})
                        
                # 3. 코스닥 매수 (코스닥 상승장 + RSI 패닉 줍기)
                elif market == 'KR_KOSDAQ' and target_market in ['KR_KOSDAQ', 'ALL'] and is_kosdaq_bullish:
                    if curr_price > ma_120 and rsi_2 < 10.0:
                        kr_candidates.append({'ticker': ticker, 'name': name, 'market': market, 'price': curr_price, 'units': unit_size, 'score': rsi_2})
        except: continue

    # [C] 랭킹 정렬 및 매수 체결
    us_candidates.sort(key=lambda x: x['score'], reverse=True)
    kr_candidates.sort(key=lambda x: x['score'])
    
    for cand in (us_candidates + kr_candidates):
        is_kr_cand = cand['market'].startswith('KR')
        if len(portfolio) >= MAX_POSITIONS: break
        if is_kr_cand and current_kr_positions >= MAX_KR_POSITIONS: continue
        if not is_kr_cand and current_us_positions >= MAX_US_POSITIONS: continue
            
        order_res = execute_order(cand['ticker'], cand['units'], side="BUY", price=cand['price'])
        
        if is_kr_cand: buy_signals.append(f"- 🥇 [{cand['name']}] 📉 RSI(2) 패닉 줍기 ➞ {order_res['msg']}")
        else: buy_signals.append(f"- 🥇 [{cand['name']}] ✨ 모멘텀 돌파 ➞ {order_res['msg']}")
            
        if order_res['success']:
            portfolio[cand['ticker']] = {
                'name': cand['name'], 'units': cand['units'], 'buy_price': cand['price'], 
                'market': cand['market'], 'buy_date': kr_time.strftime('%Y-%m-%d')
            }
            if is_kr_cand: current_kr_positions += 1
            else: current_us_positions += 1

for ticker, pos in portfolio.items():
    cp = prices_cache.get(ticker, pos['buy_price'])
    dashboard_list.append({"name": pos['name'], "units": pos['units'], "current_price": round(cp, 2), "buy_price": round(pos['buy_price'], 2)})

# ==========================================
# 🌟 5. 디스코드 브리핑 및 구글 DB 저장
# ==========================================
if not kis_token: final_content = "🚨 **시스템 경보** API 토큰 발급 실패"
else:
    b_sigs = [s for s in buy_signals if '진입' in s or '돌파' in s or '패닉' in s]
    buy_text = '\n'.join(b_sigs[:10]) if b_sigs else '신호 없음'
    sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '신호 없음'

    if buy_signals or sell_signals or skipped_signals:
        prompt = f"[매수] {buy_text}\n[청산] {sell_text}\n[보류] {skipped_signals}"
        response_text = ""
        for _ in range(3):
            try:
                response_text = client.models.generate_content(model='gemini-2.0-flash', contents=prompt).text 
                break 
            except: time.sleep(5)
        if not response_text: response_text = f"**매수**\n{buy_text}\n\n**청산**\n{sell_text}"
        final_content = f"🤖 **V35.0 트렌드 라이더 ({market_title})** 🤖\n{response_text}"
    else:
        final_content = f"🤖 **V35.0 트렌드 라이더 ({market_title} 관망)** 🤖\n독립 방어막 가동 중 / 잔고: 한국 {current_kr_positions}개, 미국 {current_us_positions}개."

try: requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content[:1900]}, timeout=10)
except: pass

if SHEET_WEBHOOK_URL:
    sheet_data = {"date": kr_time.strftime('%Y-%m-%d %H:%M:%S'), "message": f"[{market_title}] 진입 {len(b_sigs)}건, 청산 {len(sell_signals)}건", "dashboard": dashboard_list, "portfolio": portfolio}
    try: requests.post(SHEET_WEBHOOK_URL, json=sheet_data, timeout=30)
    except: pass
