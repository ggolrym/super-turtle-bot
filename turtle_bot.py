# ==========================================
# 🐢 AI 하이브리드 터틀 봇 V21.0 (실전 라이브: RSI-2 & 모멘텀 성배 모드)
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

# [V21.0 패치] 시장 분리: 한국장은 종목 무관 'RSI(2) 평균회귀', 미국장은 '모멘텀'
if RUN_MARKET == 'KOSPI': target_market, market_title = 'KR_KOSPI', "🇰🇷 코스피 (RSI-2 투매 줍기)"
elif RUN_MARKET == 'KOSDAQ': target_market, market_title = 'KR_KOSDAQ', "🚀 코스닥 (RSI-2 투매 줍기)"
elif RUN_MARKET == 'US': target_market, market_title = 'US', "🇺🇸 미국장 (신고가 모멘텀)"
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
# 🌟 3. 자본 세팅 (50만 원 & 1/4 균등 분할)
# ==========================================
TOTAL_CAPITAL = 500000      
MIN_TURNOVER_KRW = 10000000000 # [V21.0] 거래대금 100억 이상 주도주만 타격
MIN_PRICE_KRW = 1000               

MAX_POSITIONS = 4          
MAX_KR_POSITIONS = 2        
MAX_US_POSITIONS = 2        
# 💡 [V21.0 패치] 변동성 몰빵 방지: 무조건 1슬롯당 12.5만원 고정 투입
POSITION_SIZE_KRW = TOTAL_CAPITAL * 0.25 

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
                    if isinstance(data, dict): 
                        portfolio = data.get('portfolio', data) 
                db_loaded = True
                break
            else: time.sleep(5)
        except: time.sleep(5)
            
    if not db_loaded:
        error_msg = f"🚨 **시스템 자동 정지** [{market_title}] 구글 DB 응답 없음."
        try: requests.post(DISCORD_WEBHOOK_URL, json={"content": error_msg}, timeout=10)
        except: pass
        exit() 

# 💡 기억상실 방지 로직 (실제 계좌 잔고 우선주의)
def sync_portfolio_with_kis_balance(current_portfolio):
    if not kis_token: return current_portfolio
    clean_account = KIS_ACCOUNT.replace("-", "").strip()
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
                qty = int(item.get('hldg_qty', 0))
                if qty > 0: kr_tickers[item.get('pdno')] = qty
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

    synced_portfolio = {}
    for t, p in current_portfolio.items():
        clean_t = t.split('.')[0]
        is_kr = t.endswith('.KS') or t.endswith('.KQ')
        
        if is_kr:
            if not kr_api_success: synced_portfolio[t] = p
            elif clean_t in kr_tickers or t in kr_tickers:
                p['units'] = kr_tickers.get(clean_t, kr_tickers.get(t, p['units']))
                synced_portfolio[t] = p
            else: skipped_signals.append(f"- 🔄 [{p['name']}] 계좌 잔고 없음 ➞ 장부 동기화 삭제")
        else:
            if not us_api_success: synced_portfolio[t] = p
            elif clean_t in us_tickers or t in us_tickers:
                p['units'] = us_tickers.get(clean_t, us_tickers.get(t, p['units']))
                synced_portfolio[t] = p
            else: skipped_signals.append(f"- 🔄 [{p['name']}] 계좌 잔고 없음 ➞ 장부 동기화 삭제")
                
    return synced_portfolio

portfolio = sync_portfolio_with_kis_balance(portfolio)

exchange_rate = 1350.0
try:
    ex_df = fdr.DataReader('USD/KRW')
    if not ex_df.empty: exchange_rate = float(ex_df['Close'].iloc[-1])
except: pass

# ==========================================
# 🌟 4. 사전 필터링 유니버스 (초고속 스캔)
# ==========================================
all_stocks = {}
print("⏳ 시장 유니버스 사전 필터링 중...")

if target_market in ['KR_KOSPI', 'ALL']:
    try:
        kr_df = fdr.StockListing('KOSPI')
        for _, row in kr_df.iterrows(): 
            try:
                price = float(row.get('Close', 0))
                amount = float(row.get('Amount', 0)) 
                if price < MIN_PRICE_KRW or amount < MIN_TURNOVER_KRW: continue
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
                if price < MIN_PRICE_KRW or amount < MIN_TURNOVER_KRW: continue
                code = str(row.get('Code', row.get('Symbol', ''))).zfill(6) + '.KQ'
                all_stocks[code] = str(row.get('Name', ''))
            except: continue
    except: pass

if target_market in ['US', 'ALL']:
    us_tickers = ['SPLG', 'QQQ', 'SOXX']
    try:
        us_df = fdr.StockListing('SP500')
        col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
        col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
        special_tickers = {'BRKB': 'BRK-B', 'BFB': 'BF-B'}
        for _, row in us_df.iterrows(): 
            raw_sym = str(row[col_sym])
            clean_sym = special_tickers.get(raw_sym, raw_sym.replace('.', '-').replace('/', '-'))
            us_tickers.append(clean_sym)
            all_stocks[clean_sym] = str(row[col_name])
    except: pass

for t in portfolio.keys():
    t_mark = 'KR_KOSPI' if t.endswith('.KS') else 'KR_KOSDAQ' if t.endswith('.KQ') else 'US'
    if target_market in ['ALL', t_mark] and t not in all_stocks: all_stocks[t] = portfolio[t]['name']

current_positions = len(portfolio)
current_kr_positions = sum(1 for p in portfolio.values() if p.get('market', '').startswith('KR'))
current_us_positions = sum(1 for p in portfolio.values() if p.get('market') == 'US')

print(f"📊 동기화된 계좌: 한국장 {current_kr_positions}개 / 미국장 {current_us_positions}개")
print(f"⚡ 사전 필터링 완료! 정예 종목 정밀 스캔 시작!")

# ==========================================
# 🌟 5. [V21.0 엔진] 스캔 및 매매 로직
# ==========================================
kr_candidates = []      
us_candidates = []            
prices_cache = {}
# 지표 계산에 충분한 200일 전 데이터 요청
fdr_start_date = (kr_time - timedelta(days=200)).strftime('%Y-%m-%d')
scanned_tickers = set()

if kis_token: 
    for ticker, name in all_stocks.items():
        try:
            stock_data = pd.DataFrame()
            is_kr_kospi = ticker.endswith('.KS')
            is_kr_kosdaq = ticker.endswith('.KQ')
            is_kr = is_kr_kospi or is_kr_kosdaq
            is_us = not is_kr
            clean_ticker = ticker.split('.')[0]
            
            if is_kr:
                for attempt in range(3):
                    temp_data = fdr.DataReader(clean_ticker, start=fdr_start_date)
                    min_len = 20 if ticker in portfolio else 120 
                    if not temp_data.empty and len(temp_data) >= min_len:
                        stock_data = temp_data
                        break
                    time.sleep(0.05) 
            else:
                ticker_obj = yf.Ticker(ticker)
                for attempt in range(3):
                    temp_data = ticker_obj.history(period='1y')
                    min_len = 20 if ticker in portfolio else 120
                    if not temp_data.empty and len(temp_data) >= min_len:
                        stock_data = temp_data
                        break
                    time.sleep(0.1)
                
            if stock_data.empty or len(stock_data) < 2: continue 
            scanned_tickers.add(ticker)
            if isinstance(stock_data.columns, pd.MultiIndex): stock_data.columns = stock_data.columns.get_level_values(0)
            stock_data = stock_data.dropna()
                
            current_price = float(stock_data['Close'].iloc[-1])
            prices_cache[ticker] = current_price 
            current_price_krw = current_price if is_kr else current_price * exchange_rate
            chart_link = f"https://finance.naver.com/item/fchart.naver?code={clean_ticker}" if is_kr else f"https://finance.yahoo.com/quote/{ticker}/chart"

            # 💡 [V21.0 기술적 지표 계산]
            ma_5 = float(stock_data['Close'].rolling(window=5).mean().iloc[-1])
            ma_20 = float(stock_data['Close'].rolling(window=20).mean().iloc[-1])
            ma_120 = float(stock_data['Close'].rolling(window=120).mean().iloc[-1])
            
            # RSI(2) 수식
            delta = stock_data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=2).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
            rs = gain / loss.replace(0, float('nan'))
            rsi_2 = float((100 - (100 / (1 + rs))).fillna(50).iloc[-1])
            
            recent_20_high = float(stock_data['High'].iloc[-21:-1].max())

            # ------------------------------------
            # [A] 종가 청산(매도) 심사
            # ------------------------------------
            if ticker in portfolio:
                pos = portfolio[ticker]
                sell_reason = None
                
                # 🇰🇷 한국장 청산
                if is_kr:
                    if current_price <= pos['buy_price'] * 0.92:
                        sell_reason = "🔪 -8% 하드스탑 방어"
                    elif current_price >= ma_5:
                        sell_reason = "🎯 5일선 평균회귀 익절"
                # 🇺🇸 미국장 청산
                else:
                    if current_price < ma_20:
                        sell_reason = "📉 20일선 추세 이탈"
                        
                if sell_reason:
                    order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                    sell_signals.append(f"- [{name}] {sell_reason} ({pos['units']}주) ➞ {order_res['msg']}")
                    if order_res['success']:
                        current_positions -= 1
                        if is_kr: current_kr_positions -= 1
                        else: current_us_positions -= 1
                        del portfolio[ticker] 

            # ------------------------------------
            # [B] 종가 진입(매수) 심사
            # ------------------------------------
            elif ticker not in portfolio:
                if current_price_krw > POSITION_SIZE_KRW: continue
                unit_size = math.floor(POSITION_SIZE_KRW / current_price_krw)
                if unit_size == 0: continue
                
                # 🇺🇸 미국 터틀 (모멘텀 돌파)
                if is_us and target_market in ['US', 'ALL']:
                    if current_price > ma_120 and current_price >= recent_20_high:
                        us_candidates.append({
                            'ticker': ticker, 'name': name, 'market': 'US', 'price': current_price, 
                            'units': unit_size, 'score': (current_price / ma_120), 'chart_link': chart_link
                        })
                
                # 🇰🇷 한국장 (RSI_2 < 10 단기 패닉 줍기)
                elif is_kr and target_market in ['KR_KOSPI', 'KR_KOSDAQ', 'ALL']:
                    # V21.0 핵심: 대세 우상향(MA120 이상) 중 단기 투매가 나왔을 때
                    if current_price > ma_120 and rsi_2 < 10.0:
                        kr_candidates.append({
                            'ticker': ticker, 'name': name, 'market': ('KR_KOSPI' if is_kr_kospi else 'KR_KOSDAQ'), 
                            'price': current_price, 'units': unit_size, 'score': rsi_2, 'chart_link': chart_link
                        })

        except Exception: continue
        
    # 데이터 조회 실패 종목 유지
    for t in list(portfolio.keys()):
        t_mark = 'KR_KOSPI' if t.endswith('.KS') else 'KR_KOSDAQ' if t.endswith('.KQ') else 'US'
        if target_market in ['ALL', t_mark] and t not in scanned_tickers:
            skipped_signals.append(f"- ⚠️ [{portfolio[t]['name']}] 데이터 일시 누락 (홀딩 유지)")

    # --------------------------------------------------
    # [C] 랭킹 정렬 및 매수 실행
    # --------------------------------------------------
    us_candidates.sort(key=lambda x: x['score'], reverse=True) # 미국은 모멘텀(돌파 강도) 높은 순
    kr_candidates.sort(key=lambda x: x['score'])               # 한국은 RSI_2가 가장 낮은(패닉이 큰) 순
    
    all_candidates = us_candidates + kr_candidates
    
    for cand in all_candidates:
        is_kr_cand = cand['market'].startswith('KR')
        
        # 슬롯 풀방 여부 확인 (강제 교체 삭제)
        if len(portfolio) >= MAX_POSITIONS: break
        if is_kr_cand and current_kr_positions >= MAX_KR_POSITIONS: continue
        if cand['market'] == 'US' and current_us_positions >= MAX_US_POSITIONS: continue
            
        order_res = execute_order(cand['ticker'], cand['units'], side="BUY", price=cand['price'])
        
        if is_kr_cand:
            buy_signals.append(f"- 🥇 [{cand['name']}] 📉 RSI(2) 패닉 줍기 ➞ {order_res['msg']} [차트]({cand['chart_link']})")
        else:
            buy_signals.append(f"- 🥇 [{cand['name']}] ✨ 모멘텀 신고가 돌파 ➞ {order_res['msg']} [차트]({cand['chart_link']})")
            
        if order_res['success']:
            # 스탑로스는 -8% 로 기록해두지만, 실제 청산은 당일 로직(MA5 등)에서 동적으로 평가함
            portfolio[cand['ticker']] = {
                'name': cand['name'], 'units': cand['units'], 'buy_price': cand['price'], 
                'stop_loss': cand['price'] * 0.92, 'strategy': 'V21_RSI2' if is_kr_cand else 'V21_MOMENTUM', 
                'market': cand['market'], 'buy_date': kr_time.strftime('%Y-%m-%d')
            }
            if is_kr_cand: current_kr_positions += 1
            else: current_us_positions += 1

# 대시보드 리스트 생성
for ticker, pos in portfolio.items():
    cp = prices_cache.get(ticker, pos['buy_price'])
    dashboard_list.append({
        "name": pos['name'], "units": pos['units'], "current_price": round(cp, 2), 
        "buy_price": round(pos['buy_price'], 2), "stop_loss": round(pos['stop_loss'], 2)
    })

# ==========================================
# 🌟 7. 브리핑 전송 및 구글 DB 저장
# ==========================================
if not kis_token:
    final_content = "🚨 **시스템 경보** API 토큰 발급 실패"
else:
    # 텔레그램/디스코드 문자수 제한 방지를 위해 요약 표시 
    b_sigs = [s for s in buy_signals if '신규 진입' in s or '픽' in s or '돌파' in s or '패닉' in s or '추세' in s]
    buy_text = '\n'.join(b_sigs[:10]) if b_sigs else '신호 없음'
    sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '신호 없음'
    skip_text = '\n'.join(list(set(skipped_signals))[:3]) if skipped_signals else '보류 없음'

    if buy_signals or sell_signals or skipped_signals:
        prompt = f"[매수] {buy_text}\n[청산/익절] {sell_text}\n[보류요약] {skip_text}"
        response_text = ""
        for _ in range(3):
            try:
                response_text = client.models.generate_content(model='gemini-2.0-flash', contents=prompt).text 
                break 
            except Exception: time.sleep(5)
                
        if not response_text: response_text = f"**매수**\n{buy_text}\n\n**청산**\n{sell_text}"
        final_content = f"🤖 **V21.0 성배 모드 ({market_title})** 🤖\n{response_text}"
    else:
        final_content = f"🤖 **V21.0 성배 모드 ({market_title} 관망)** 🤖\n감시 {len(all_stocks)}개 / 잔고: 한국 {current_kr_positions}/{MAX_KR_POSITIONS}개, 미국 {current_us_positions}/{MAX_US_POSITIONS}개."

if len(final_content) > 1900: final_content = final_content[:1900] + "\n\n... (⚠️ 요약됨)"

try:
    requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content}, timeout=10)
except Exception as e:
    print(f"⚠️ 디스코드 발송 실패: {e}")

if SHEET_WEBHOOK_URL:
    kr_time = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    buy_count = len(b_sigs)
    sell_count = len(sell_signals)
    summary_msg = f"진입 {buy_count}건, 청산/익절 {sell_count}건" if (buy_count > 0 or sell_count > 0) else "관망 중"
    
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
