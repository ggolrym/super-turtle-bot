# ==========================================
# 🐢 AI 멀티 에셋 터틀 봇 v10.1 (전 종목 무차별 스캔 + 구글 DB 통합판)
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

# 🌟 2. KIS API 통신 모듈
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
print("✅ KIS 토큰 발급 완료!" if kis_token else "❌ KIS 토큰 발급 실패. 임무를 보류합니다.")

def execute_order(ticker, qty, side="BUY", price=0.0):
    if not kis_token: return {"success": False, "msg": "토큰 없음"}
    
    is_krw = ticker.endswith('.KS') or ticker.endswith('.KQ')
    clean_ticker = ticker.split('.')[0]
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
        
        if clean_ticker in ['SPLG', 'SPY', 'GLDM', 'GLD', 'TLT', 'DBC', 'VNQ', 'SH', 'PSQ', 'QQQM']:
            excg_cd = 'AMS' 
        else:
            excg_cd = 'NAS' 
            
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
# 🌟 3. 자본 세팅 및 구글 DB 장부 연동
# ==========================================
TOTAL_CAPITAL = 500000      
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT

MIN_TURNOVER_KRW = 5000000000 
MAX_POSITION_KRW = 100000     
MAX_POSITIONS = 10          
MAX_SECTOR_POSITIONS = 5       

portfolio = {}
print("구글 시트(DB)에서 포트폴리오를 불러옵니다...")
if SHEET_WEBHOOK_URL:
    try:
        res = requests.get(SHEET_WEBHOOK_URL, timeout=30)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict):
                portfolio = data
            else:
                print("DB 데이터 형식 오류. 빈 장부로 시작합니다.")
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
    if ticker in ['GLDM', 'GLD']: return 'Gold'
    elif ticker == 'DBC': return 'Commodity'
    elif ticker == 'TLT': return 'Bond'
    elif ticker == 'VNQ': return 'RealEstate'
    elif ticker in ['SH', 'PSQ']: return 'Inverse' 
    return 'Stock'

# ==========================================
# 🌟 4. 전 종목 거대 유니버스 복원 (v9.6.2 오리지널 방식)
# ==========================================
all_stocks = {
    'SPLG': 'SPDR Portfolio S&P 500', 'GLDM': 'SPDR Gold MiniShares', 
    'DBC': 'Invesco DB Commodity', 'SH': 'ProShares Short S&P500', 'PSQ': 'ProShares Short QQQ' 
}

print("🌐 코스피 전체 리스트 및 S&P500 전체 리스트 수집 중...")
# 코스피 리스트 복원 (로컬에 kospi_list.csv 파일이 있어야 함)
try:
    if os.path.exists('kospi_list.csv'):
        kr_df = pd.read_csv('kospi_list.csv')
        for _, row in kr_df.iterrows(): 
            all_stocks[str(row.iloc[0]).replace('.0', '').strip().zfill(6) + '.KS'] = str(row.iloc[1])
    else:
        print("⚠️ kospi_list.csv 파일이 없어 코스피 리스트 로드 생략.")
except Exception as e: print(f"⚠️ 코스피 리스트 로드 에러: {e}")

# S&P500 전 종목 자동 수집 복원
try:
    us_df = fdr.StockListing('SP500')
    col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
    col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
    for _, row in us_df.iterrows(): 
        all_stocks[str(row[col_sym]).replace('.', '-')] = str(row[col_name])
except Exception as e: print(f"⚠️ S&P500 리스트 로드 에러: {e}")

current_positions = len(portfolio)
current_sector_positions = {'Stock': 0, 'Gold': 0, 'Commodity': 0, 'Bond': 0, 'RealEstate': 0, 'Inverse': 0}
for t in portfolio.keys(): 
    sec = get_sector(t)
    if sec in current_sector_positions: current_sector_positions[sec] += 1

print(f"\n🤖 총 {len(all_stocks)}개 전 종목 정밀 스캔 시작 (v10.1 무차별 스캔판)!\n")

# ==========================================
# 🌟 5. 전 종목 스캔 및 매매 집행
# ==========================================
if kis_token: 
    for ticker, name in all_stocks.items():
        try:
            # 🌟 [방어 강화] 야후 다운로드 시 progress=False 유지 및 에러 시 즉시 다음 종목 패스
            stock_data = yf.download(ticker, period='2y', progress=False)
            if stock_data.empty: continue
            
            if isinstance(stock_data.columns, pd.MultiIndex):
                stock_data.columns = stock_data.columns.get_level_values(0)
            stock_data = stock_data.dropna()
            
            if len(stock_data) < 200: continue
                
            current_price = float(stock_data['Close'].iloc[-1])
            is_krw = ticker.endswith('.KS') or ticker.endswith('.KQ')
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

            if unit_size * current_price_krw > MAX_POSITION_KRW:
                unit_size = math.floor(MAX_POSITION_KRW / current_price_krw)
                if unit_size == 0: continue 

            chart_link = f"https://finance.naver.com/item/fchart.naver?code={ticker.split('.')[0]}" if is_krw else f"https://finance.yahoo.com/quote/{ticker}/chart"
            sector = get_sector(ticker)

            # 📂 A. 기존 포지션 관리
            if ticker in portfolio:
                pos = portfolio[ticker]
                if current_price <= pos['stop_loss'] or current_price <= low_10:
                    order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                    sell_signals.append(f"- [{name}] 전량 청산 ({pos['units']}주) ➞ {order_res['msg']} [📊 차트]({chart_link})")
                    
                    if order_res['success']:
                        current_positions -= 1
                        current_sector_positions[sector] -= 1
                        del portfolio[ticker] 
                else:
                    chunks = pos.get('chunks', 1)
                    if chunks < 4 and current_price >= pos['last_buy_price'] + (0.5 * N):
                        order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                        buy_signals.append(f"- [{name}] 🔥 {chunks+1}차 불타기 ({unit_size}주) ➞ {order_res['msg']}")
                        
                        if order_res['success']:
                            pos['units'] += unit_size
                            pos['chunks'] = chunks + 1
                            pos['last_buy_price'] = current_price
                            pos['stop_loss'] = current_price - (2 * N)

            # 📂 B. 신규 진입 로직
            elif ticker not in portfolio:
                avg_volume = float(stock_data['Volume'].iloc[-21:-1].mean())
                turnover_krw = (current_price * avg_volume) * (1 if is_krw else exchange_rate)
                # 🌟 거대 종목 풀에서는 유동성 필터가 생명줄 (잡주 완벽 필터링)
                if turnover_krw < MIN_TURNOVER_KRW: continue
                
                volatility_ratio = (N / current_price) * 100
                is_above_200 = current_price >= float(stock_data['Close'].rolling(window=200).mean().iloc[-1])
                is_above_120 = current_price >= float(stock_data['Close'].rolling(window=120).mean().iloc[-1]) 
                is_above_60 = current_price >= float(stock_data['Close'].rolling(window=60).mean().iloc[-1])   
                
                if sector == 'Stock':
                    if not is_above_120: continue      
                    if volatility_ratio < 1.0: continue 
                elif sector == 'Inverse':
                    if not is_above_60: continue       
                    if volatility_ratio < 0.5: continue
                else:
                    if not is_above_200: continue      
                    if volatility_ratio < 0.5: continue

                recent_20_high = float(stock_data['High'].iloc[-21:-1].max())
                
                if current_price >= recent_20_high:
                    if current_positions + 1 > MAX_POSITIONS: skipped_signals.append(f"- [{name}] 10종목 한도 초과 보류")
                    elif current_sector_positions[sector] + 1 > MAX_SECTOR_POSITIONS: skipped_signals.append(f"- [{name}] {sector} 섹터 초과")
                    else:
                        order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                        buy_signals.append(f"- [{name}] ✨ 신규 1차 진입 ({unit_size}주) ➞ {order_res['msg']} [📊 차트]({chart_link})")
                        
                        if order_res['success']:
                            stop_loss_price = current_price - (2 * N)
                            portfolio[ticker] = {'name': name, 'units': unit_size, 'chunks': 1, 'last_buy_price': current_price, 'stop_loss': stop_loss_price}
                            current_positions += 1
                            current_sector_positions[sector] += 1

            # 매매 처리 후 포트폴리오를 대시보드 리스트에 추가
            if ticker in portfolio:
                pos = portfolio[ticker]
                dashboard_list.append({
                    "name": pos['name'],
                    "units": pos['units'],
                    "current_price": round(current_price, 2),
                    "buy_price": round(pos['last_buy_price'], 2),
                    "stop_loss": round(pos['stop_loss'], 2),
                    "trailing_stop": round(low_10, 2)
                })

        except Exception: 
            continue
            
        # 🌟 수천 개 스캔 시 야후 IP 차단을 막는 필수 딜레이 (0.15초)
        time.sleep(0.15) 

# ==========================================
# 🌟 6. 브리핑 전송 및 구글 DB 저장
# ==========================================
if not kis_token:
    final_content = "🚨 **터틀 펀드 시스템 경보** 🚨\n한국투자증권 API 서버 응답 지연으로 금일 스캔을 보류합니다."
else:
    buy_text = '\n'.join(buy_signals[:10]) if buy_signals else '신호 없음'
    sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '신호 없음'
    skip_text = '\n'.join(skipped_signals[:5]) if skipped_signals else '보류 없음'

    if buy_signals or sell_signals or skipped_signals:
        prompt = f"""
        아래는 퀀트 봇 체결 결과입니다. 
        [매수] {buy_text}
        [청산] {sell_text}
        [보류] {skip_text}
        """
        response_text = ""
        for _ in range(3):
            try:
                response_text = client.models.generate_content(model='gemini-2.0-flash', contents=prompt).text 
                break 
            except Exception: time.sleep(5)
                
        if not response_text: response_text = f"**매수**\n{buy_text}\n\n**청산**\n{sell_text}"
        final_content = f"🤖 **터틀 펀드 v10.1 (전 종목 스캔)** 🤖\n{response_text}"
    else:
        final_content = f"🤖 **터틀 펀드 v10.1 가동 중** 🤖\n감시 종목 {len(all_stocks)}개 / 보유 종목 {current_positions}/{MAX_POSITIONS} 개. 현재 시장 상황 관망 중."

if len(final_content) > 1900: final_content = final_content[:1900] + "\n\n... (⚠️ 내용이 너무 길어 요약됨)"
requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content})

if SHEET_WEBHOOK_URL:
    kr_time = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    buy_count = len(buy_signals)
    sell_count = len(sell_signals)
    summary_msg = f"매수 {buy_count}건, 청산 {sell_count}건" if (buy_count > 0 or sell_count > 0) else ("API 서버 오류" if not kis_token else "특이사항 없음 (관망)")
    
    sheet_data = {
        "date": kr_time,
        "message": summary_msg,
        "dashboard": dashboard_list,
        "portfolio": portfolio 
    }
    try:
        requests.post(SHEET_WEBHOOK_URL, json=sheet_data, timeout=30)
    except Exception as e:
        print(f"⚠️ 구글 시트 업데이트 실패: {e}")
