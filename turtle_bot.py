# ==========================================
# 🐢 AI 하이브리드 터틀 봇 V12.0 (스마트 랭킹 엔진 & 3중 방어막 탑재판) - 오류 수정 완료
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

# 🌟 1. 환경 변수 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
KIS_APP_KEY = os.environ.get("KIS_APP_KEY")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")
KIS_ACCOUNT = os.environ.get("KIS_ACCOUNT")
SHEET_WEBHOOK_URL = os.environ.get("SHEET_WEBHOOK_URL") 

if not all([GEMINI_API_KEY, DISCORD_WEBHOOK_URL, KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT, SHEET_WEBHOOK_URL]):
    print("🚨 API 키 또는 깃허브 시크릿 누락!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)
KIS_URL = "https://openapivts.koreainvestment.com:29443" 

# 🌟 2. 시간 감지 및 타겟 시장 설정 (오류 수정 완료)
kr_time = datetime.now(pytz.timezone('Asia/Seoul'))
kr_hour = kr_time.hour

# 👇 깃허브 시간 지연(2시간 조기 예약)을 반영하여 로봇의 인식 시간대를 대폭 확장!
if 12 <= kr_hour <= 17:
    target_market = 'KR'
    market_title = "🇰🇷 한국장(낙폭과대 우량주 스윙)"
elif 2 <= kr_hour <= 8:
    target_market = 'US'
    market_title = "🇺🇸 미국장(터틀 추세추종)"
else:
    target_market = 'ALL'
    market_title = "🌐 통합 테스트"

print(f"⏰ 현재 한국시간: {kr_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"🎯 타겟 스캔 시장: {market_title}\n")

# 🌟 3. KIS API 통신 모듈
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
    is_krw = ticker.endswith('.KS') or ticker.endswith('.KQ')
    clean_ticker = ticker.split('.')[0]
    clean_account = KIS_ACCOUNT.replace("-", "").strip()
    cano = clean_account[:8]
    prdt_cd = clean_account[8:10] if len(clean_account) >= 10 else "01"
    
    headers = {"Content-Type": "application/json; charset=utf-8", "authorization": f"Bearer {kis_token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    
    if is_krw:
        url = f"{KIS_URL}/uapi/domestic-stock/v1/trading/order-cash"
        headers["tr_id"] = "VTTC0802U" if side == "BUY" else "VTTC0801U"
        body = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), "ORD_DVSN": "01", "ORD_UNPR": "0"}
    else:
        url = f"{KIS_URL}/uapi/overseas-stock/v1/trading/order"
        headers["tr_id"] = "VTTT1002U" if side == "BUY" else "VTTT1006U"
        excg_cd = 'AMS' if clean_ticker in ['SPLG', 'SPY', 'GLDM', 'GLD', 'TLT', 'DBC', 'VNQ', 'SH', 'PSQ', 'QQQM'] else 'NAS'
        target_price = price * 1.01 if side == "BUY" else price * 0.99
        body = {"CANO": cano, "ACNT_PRDT_CD": prdt_cd, "OVRS_EXCG_CD": excg_cd, "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), "OVRS_ORD_UNPR": str(round(target_price, 2)), "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"}
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        data = res.json()
        if data.get("rt_cd") == "0": return {"success": True, "msg": "✅ 체결"}
        else: return {"success": False, "msg": f"❌ 거절({data.get('msg1')})"}
    except Exception as e: return {"success": False, "msg": f"❌ 에러({e})"}

# ==========================================
# 🌟 4. 자본 세팅 및 구글 DB '강제 보호' 장부 연동
# ==========================================
TOTAL_CAPITAL = 500000      
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
MIN_TURNOVER_KRW = 5000000000 
MIN_MARKET_CAP_KRW = 150000000000 
MIN_PRICE_KRW = 2000 

MAX_POSITION_KRW = 150000     
MAX_POSITIONS = 4          
MAX_SECTOR_POSITIONS = 2       

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
                        portfolio = data
                db_loaded = True
                break
            else:
                print(f"⚠️ 구글 DB 상태 코드 오류: {res.status_code}")
                time.sleep(5)
        except Exception as e:
            print(f"⚠️ 구글 DB 통 지연 (시도 {attempt+1}/3): {e}")
            time.sleep(5)
            
    if not db_loaded:
        error_msg = "🚨 **시스템 자동 정지** 구글 DB(장부) 응답 없음. 기존 보유 종목 데이터 소멸 및 덮어쓰기 위험을 감지하여 오늘 스캔 임무를 강제로 종료합니다."
        print(error_msg)
        try: requests.post(DISCORD_WEBHOOK_URL, json={"content": error_msg}, timeout=10)
        except: pass
        exit() 

exchange_rate = 1350.0
try:
    ex_df = fdr.DataReader('USD/KRW')
    if not ex_df.empty: exchange_rate = float(ex_df['Close'].iloc[-1])
except: pass

buy_signals, sell_signals, skipped_signals = [], [], []
dashboard_list = [] 

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
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ==========================================
# 🌟 5. 타겟 시장 유니버스 생성 
# ==========================================
all_stocks = {}

if target_market in ['KR', 'ALL']:
    try:
        if os.path.exists('kospi_list.csv'):
            kr_df = pd.read_csv('kospi_list.csv')
            for _, row in kr_df.iterrows(): 
                all_stocks[str(row.iloc[0]).replace('.0', '').strip().zfill(6) + '.KS'] = str(row.iloc[1])
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
            if raw_sym in special_tickers: clean_sym = special_tickers[raw_sym]
            else: clean_sym = raw_sym.replace('.', '-').replace('/', '-')
            all_stocks[clean_sym] = str(row[col_name])
    except: pass

for t in portfolio.keys():
    if t not in all_stocks: all_stocks[t] = portfolio[t]['name']

current_positions = len(portfolio)
current_sector_positions = {'Stock': 0, 'Gold': 0, 'Commodity': 0, 'Bond': 0, 'RealEstate': 0, 'Inverse': 0}
for t in portfolio.keys(): 
    sec = get_sector(t)
    if sec in current_sector_positions: current_sector_positions[sec] += 1

print(f"🤖 총 {len(all_stocks)}개 종목 정밀 스캔 및 랭킹 분석 시작!")

# ==========================================
# 🌟 6. [지능형 랭킹 엔진] 매매 스캔 및 실행
# ==========================================
# 장바구니 준비 및 실시간 가격 저장소
kr_candidates = []
us_candidates = []
prices_cache = {}

if kis_token: 
    # 1단계: 전체 스캔 (기존 종목 관리 및 신규 타점 수집)
    for ticker, name in all_stocks.items():
        try:
            stock_data = pd.DataFrame()
            ticker_obj = yf.Ticker(ticker)
            for attempt in range(3):
                temp_data = ticker_obj.history(period='2y')
                if not temp_data.empty and len(temp_data) >= 200:
                    stock_data = temp_data
                    break
                time.sleep(1) 
                
            if stock_data.empty: continue 
            
            if isinstance(stock_data.columns, pd.MultiIndex): stock_data.columns = stock_data.columns.get_level_values(0)
            stock_data = stock_data.dropna()
                
            current_price = float(stock_data['Close'].iloc[-1])
            prices_cache[ticker] = current_price # 대시보드용 가격 저장
            
            is_krw = ticker.endswith('.KS') or ticker.endswith('.KQ')
            ticker_market = 'KR' if is_krw else 'US'
            
            if target_market != 'ALL' and ticker_market != target_market:
                continue 
            
            current_price_krw = current_price if is_krw else current_price * exchange_rate
            sector = get_sector(ticker)
            chart_link = f"https://finance.naver.com/item/fchart.naver?code={ticker.split('.')[0]}" if is_krw else f"https://finance.yahoo.com/quote/{ticker}/chart"

            # ------------------------------------
            # 🇺🇸 미국장 로직 (터틀 추세추종)
            # ------------------------------------
            if ticker_market == 'US':
                low_10 = float(stock_data['Low'].iloc[-11:-1].min())
                high_low = stock_data['High'] - stock_data['Low']
                high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
                low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
                tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                N = float(tr.rolling(window=20).mean().iloc[-1])
                ma_120 = float(stock_data['Close'].rolling(window=120).mean().iloc[-1])
                
                if pd.isna(N) or N <= 0 or current_price_krw > MAX_POSITION_KRW: continue
                N_krw = N * exchange_rate
                unit_size = math.floor(RISK_AMOUNT / N_krw)
                unit_size = 1 if unit_size == 0 else unit_size
                if unit_size * current_price_krw > MAX_POSITION_KRW:
                    unit_size = math.floor(MAX_POSITION_KRW / current_price_krw)
                    if unit_size == 0: continue 

                # 기존 보유 종목 즉시 관리 (매도 / 불타기)
                if ticker in portfolio:
                    pos = portfolio[ticker]
                    pos['trailing_stop'] = low_10
                    if current_price <= pos['stop_loss'] or current_price <= low_10:
                        order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                        sell_signals.append(f"- [{name}] 전량 청산 ({pos['units']}주) ➞ {order_res['msg']}")
                        if order_res['success']:
                            current_positions -= 1; current_sector_positions[sector] -= 1
                            del portfolio[ticker] 
                    else:
                        chunks = pos.get('chunks', 1)
                        if chunks < 4 and current_price >= pos['last_buy_price'] + (0.5 * N):
                            order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                            buy_signals.append(f"- [{name}] 🔥 {chunks+1}차 불타기 ➞ {order_res['msg']}")
                            if order_res['success']:
                                pos['units'] += unit_size; pos['chunks'] = chunks + 1
                                pos['last_buy_price'] = current_price; pos['stop_loss'] = current_price - (2 * N)

                # 신규 타점 발견 시 장바구니에 담기
                elif ticker not in portfolio:
                    turnover_krw = (current_price * float(stock_data['Volume'].iloc[-21:-1].mean())) * exchange_rate
                    if turnover_krw < MIN_TURNOVER_KRW: continue
                    if sector == 'Stock' and current_price < ma_120: continue      

                    recent_20_high = float(stock_data['High'].iloc[-21:-1].max())
                    if current_price >= recent_20_high:
                        momentum = current_price / ma_120 # 랭킹 기준 1: 120일선 대비 강도
                        us_candidates.append({
                            'ticker': ticker, 'name': name, 'unit_size': unit_size, 'price': current_price,
                            'N': N, 'low_10': low_10, 'momentum': momentum, 'sector': sector, 'chart_link': chart_link
                        })

            # ------------------------------------
            # 🇰🇷 한국장 로직 (낙폭과대 스윙)
            # ------------------------------------
            elif ticker_market == 'KR':
                if current_price < MIN_PRICE_KRW or current_price_krw > MAX_POSITION_KRW: continue
                
                avg_volume = float(stock_data['Volume'].iloc[-21:-1].mean())
                turnover_krw = current_price * avg_volume
                if turnover_krw < MIN_TURNOVER_KRW: continue
                try:
                    market_cap = ticker_obj.info.get('marketCap', 0)
                    if market_cap and market_cap < MIN_MARKET_CAP_KRW: continue
                except: continue
                
                rsi_14 = float(calculate_rsi(stock_data['Close'], 14).iloc[-1])
                ma_20 = float(stock_data['Close'].rolling(window=20).mean().iloc[-1])
                std_20 = float(stock_data['Close'].rolling(window=20).std().iloc[-1])
                bb_lower = ma_20 - (2 * std_20)
                
                unit_size = math.floor(MAX_POSITION_KRW / current_price_krw)
                if unit_size == 0: continue

                # 기존 보유 종목 즉시 관리 (매도)
                if ticker in portfolio:
                    pos = portfolio[ticker]
                    profit_pct = (current_price - pos['last_buy_price']) / pos['last_buy_price'] * 100
                    if profit_pct >= 7.0 or profit_pct <= -5.0:
                        reason = "🎯 5% 익절" if profit_pct > 0 else "🔪 -5% 손절"
                        order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                        sell_signals.append(f"- [{name}] {reason} ({pos['units']}주) ➞ {order_res['msg']}")
                        if order_res['success']:
                            current_positions -= 1; current_sector_positions[sector] -= 1
                            del portfolio[ticker] 

                # 신규 타점 발견 시 장바구니에 담기
                elif ticker not in portfolio:
                    if rsi_14 <= 30.0 and current_price <= bb_lower:
                        kr_candidates.append({
                            'ticker': ticker, 'name': name, 'unit_size': unit_size, 'price': current_price,
                            'rsi': rsi_14, 'ma_20': ma_20, 'sector': sector, 'chart_link': chart_link
                        })

        except Exception: continue
        time.sleep(0.15) 

    # ==================================================
    # 2단계: 랭킹 정렬 및 1등부터 실제 매수 실행 (Rank & Execution)
    # ==================================================
    # 🇺🇸 미국장: 모멘텀(추세강도)이 높은 순서로 정렬 (내림차순)
    us_candidates.sort(key=lambda x: x['momentum'], reverse=True)
    # 🇰🇷 한국장: RSI(투매강도)가 가장 낮은 순서로 정렬 (오름차순)
    kr_candidates.sort(key=lambda x: x['rsi'])
    
    all_candidates = us_candidates + kr_candidates
    
    for cand in all_candidates:
        if current_positions >= MAX_POSITIONS: 
            skipped_signals.append(f"- [{cand['name']}] 한도 꽉참 (보류)")
            continue
        if current_sector_positions[cand['sector']] >= MAX_SECTOR_POSITIONS: 
            skipped_signals.append(f"- [{cand['name']}] 섹터 제한 (보류)")
            continue
            
        order_res = execute_order(cand['ticker'], cand['unit_size'], side="BUY", price=cand['price'])
        
        # 한국장 후보였을 경우
        if cand in kr_candidates:
            buy_signals.append(f"- 🥇 [{cand['name']}] 📉 랭킹 픽(RSI: {cand['rsi']:.1f}) ➞ {order_res['msg']} [차트]({cand['chart_link']})")
            if order_res['success']:
                portfolio[cand['ticker']] = {'name': cand['name'], 'units': cand['unit_size'], 'chunks': 1, 'last_buy_price': cand['price'], 'stop_loss': cand['price'] * 0.95, 'trailing_stop': cand['ma_20'], 'strategy': 'KR_SWING'}
                current_positions += 1; current_sector_positions[cand['sector']] += 1
        # 미국장 후보였을 경우
        else:
            buy_signals.append(f"- 🥇 [{cand['name']}] ✨ 랭킹 픽(모멘텀: {cand['momentum']:.2f}) ➞ {order_res['msg']} [차트]({cand['chart_link']})")
            if order_res['success']:
                portfolio[cand['ticker']] = {'name': cand['name'], 'units': cand['unit_size'], 'chunks': 1, 'last_buy_price': cand['price'], 'stop_loss': cand['price'] - (2 * cand['N']), 'trailing_stop': cand['low_10'], 'strategy': 'US_TURTLE'}
                current_positions += 1; current_sector_positions[cand['sector']] += 1

# 대시보드 리스트 생성 (최종 업데이트된 포트폴리오 기준)
for ticker, pos in portfolio.items():
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
        final_content = f"🤖 **하이브리드 터틀 V12.0 ({market_title})** 🤖\n{response_text}"
    else:
        final_content = f"🤖 **하이브리드 터틀 V12.0 ({market_title} 관망)** 🤖\n감시 종목 {len(all_stocks)}개 / 보유 종목 {current_positions}/{MAX_POSITIONS} 개."

if len(final_content) > 1900: final_content = final_content[:1900] + "\n\n... (⚠️ 요약됨)"

try:
    requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content}, timeout=10)
except Exception as e:
    print(f"⚠️ 디스코드 발송 실패: {e}")

if SHEET_WEBHOOK_URL:
    kr_time = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    buy_count = len([s for s in buy_signals if '신규 진입' in s or '랭킹 픽' in s])
    sell_count = len(sell_signals)
    summary_msg = f"매수 {buy_count}건, 청산 {sell_count}건" if (buy_count > 0 or sell_count > 0) else "관망 중"
    
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
