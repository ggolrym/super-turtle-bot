# ==========================================
# 🐢 AI 멀티 에셋 터틀 봇 v9.3 (거래대금 함정 돌파 및 데이터 안정화)
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

if not all([GEMINI_API_KEY, DISCORD_WEBHOOK_URL, KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT]):
    print("🚨 API 키 또는 깃허브 시크릿 누락!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)
KIS_URL = "https://openapivts.koreainvestment.com:29443" 

# 🌟 2. 한국투자증권 통신 모듈 (Timeout 방어막 탑재)
def get_kis_token():
    url = f"{KIS_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        return res.json().get("access_token") if res.status_code == 200 else None
    except requests.exceptions.Timeout:
        print("🚨 KIS 서버 응답 지연 (Timeout).")
        return None
    except Exception as e:
        print(f"🚨 KIS 토큰 에러: {e}")
        return None

kis_token = get_kis_token()
print("✅ KIS 토큰 발급 완료!" if kis_token else "❌ 토큰 발급 실패. 임무를 보류합니다.")

def execute_order(ticker, qty, side="BUY", price=0.0):
    if not kis_token: return "❌ 토큰 없음"
    
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
        except:
            excg_cd = 'NYS'
            
        body = {
            "CANO": cano, "ACNT_PRDT_CD": prdt_cd, "OVRS_EXCG_CD": excg_cd, 
            "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), 
            "OVRS_ORD_UNPR": str(round(price, 2)), "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"
        }
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        data = res.json()
        if data.get("rt_cd") == "0": return "✅ 체결"
        else: return f"❌ 실패({data.get('msg1')})"
    except Exception: return f"❌ 네트워크 에러"

# ==========================================
# 🌟 3. 자본, 리스크 및 포트폴리오 세팅
# ==========================================
TOTAL_CAPITAL = 5000000     
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
MIN_TURNOVER_KRW = 10000000000 
PORTFOLIO_FILE = 'portfolio.json' 
MAX_TOTAL_UNITS = 12       
MAX_SECTOR_UNITS = 6       

if os.path.exists(PORTFOLIO_FILE):
    with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f: portfolio = json.load(f)
else: portfolio = {}

exchange_rate = 1350
try:
    ex_df = fdr.DataReader('USD/KRW')
    exchange_rate = ex_df['Close'].iloc[-1].item()
except Exception: pass

buy_signals, sell_signals, skipped_signals = [], [], []

def get_sector(ticker):
    if ticker == 'GLD': return 'Gold'
    elif ticker == 'TLT': return 'Bond'
    elif ticker == 'DBC': return 'Commodity'
    elif ticker == 'VNQ': return 'Real_Estate'
    elif ticker in ['SH', 'PSQ']: return 'Inverse' 
    else: return 'Stock'

all_stocks = {
    'QQQ': 'Invesco QQQ (나스닥 대형주)', 'SPY': 'SPDR S&P 500 ETF (미국 대형주)',
    'GLD': 'SPDR Gold Shares (금 실물)', 'TLT': 'iShares 20+ Year Treasury Bond (미국 장기채)',
    'DBC': 'Invesco DB Commodity Index (원자재)', 'VNQ': 'Vanguard Real Estate ETF (미국 부동산)',
    'SH': 'ProShares Short S&P500 (🔥 S&P500 인버스)', 
    'PSQ': 'ProShares Short QQQ (🔥 나스닥 인버스)' 
}
try:
    kr_df = pd.read_csv('kospi_list.csv')
    for _, row in kr_df.iterrows(): all_stocks[str(row.iloc[0]).replace('.0', '').strip().zfill(6) + '.KS'] = str(row.iloc[1])
except Exception: pass
try:
    us_df = fdr.StockListing('SP500')
    col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
    col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
    for _, row in us_df.iterrows():
        sym = str(row[col_sym])
        if sym not in all_stocks: all_stocks[sym] = str(row[col_name])
except Exception: pass

current_total_units = sum(pos['units'] for pos in portfolio.values())
current_sector_units = {'Stock': 0, 'Gold': 0, 'Bond': 0, 'Commodity': 0, 'Real_Estate': 0, 'Inverse': 0}
for t, pos in portfolio.items(): current_sector_units[get_sector(t)] += pos['units']

print(f"\n🤖 총 {len(all_stocks)}개 자산 정밀 스캔 시작!\n")

# ==========================================
# 🌟 4. 데이터 검증 및 주문 집행
# ==========================================
if kis_token: 
    for ticker, name in all_stocks.items():
        try:
            # 🌟 [v9.3 패치] 2년치(2y) 데이터 조회로 200일선 계산 안정성 극대화
            stock_data = yf.download(ticker, period='2y', progress=False)
            if len(stock_data) < 200: continue
                
            current_price = stock_data['Close'].iloc[-1].item()
            
            high_low = stock_data['High'] - stock_data['Low']
            high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
            low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            N = tr.rolling(window=20).mean().iloc[-1].item()
            
            is_krw = ticker.endswith('.KS')
            N_krw = N if is_krw else N * exchange_rate
            unit_size = math.floor(RISK_AMOUNT / N_krw)
            unit_size = 1 if unit_size == 0 else unit_size

            chart_link = f"https://finance.naver.com/item/fchart.naver?code={ticker.replace('.KS', '')}" if is_krw else f"https://finance.yahoo.com/quote/{ticker}/chart"
            sector = get_sector(ticker)

            # 📂 A. 청산 및 불타기 로직
            if ticker in portfolio:
                pos = portfolio[ticker]
                low_10 = stock_data['Low'].iloc[-11:-1].min().item()
                
                if current_price <= pos['stop_loss'] or current_price <= low_10:
                    order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                    sell_signals.append(f"- [{name}] 전량 청산 ({pos['units']}주) ➞ {order_res} [📊 차트]({chart_link})")
                    current_total_units -= pos['units']
                    current_sector_units[sector] -= pos['units']
                    del portfolio[ticker] 
                    continue
                    
                if pos['units'] < 4 and current_price >= pos['last_buy_price'] + (0.5 * N):
                    if current_total_units + 1 > MAX_TOTAL_UNITS: skipped_signals.append(f"- [{name}] 총 Unit 초과로 보류")
                    elif current_sector_units[sector] + 1 > MAX_SECTOR_UNITS: skipped_signals.append(f"- [{name}] {sector} 한도 초과")
                    else:
                        order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                        pos['units'] += unit_size
                        pos['last_buy_price'] = current_price
                        pos['stop_loss'] = current_price - (2 * N)
                        current_total_units += 1
                        current_sector_units[sector] += 1
                        buy_signals.append(f"- [{name}] 🔥 {pos['units']}차 불타기 ➞ {order_res} [📊 차트]({chart_link})")

            # 📂 B. 신규 진입 로직
            else:
                # 🌟 [v9.3 패치] 장 초반 거래대금 0원 함정 돌파: '최근 20일 평균 거래량'으로 심사
                avg_volume = stock_data['Volume'].iloc[-21:-1].mean().item()
                turnover_krw = (current_price * avg_volume) * (1 if is_krw else exchange_rate)
                if turnover_krw < MIN_TURNOVER_KRW: continue
                
                # 2. 이동평균선 및 변동성 필터 분기
                volatility_ratio = (N / current_price) * 100
                is_above_200 = current_price >= stock_data['Close'].rolling(window=200).mean().iloc[-1].item()
                is_above_120 = current_price >= stock_data['Close'].rolling(window=120).mean().iloc[-1].item() 
                is_above_60 = current_price >= stock_data['Close'].rolling(window=60).mean().iloc[-1].item()   
                
                if sector == 'Stock':
                    if not is_above_120: continue      # 개별주: 120일선(6개월 반기)으로 완화
                    if volatility_ratio < 1.0: continue # 개별주: 1.0%로 완화 (우량주 포함)
                elif sector == 'Inverse':
                    if not is_above_60: continue       # 인버스: 60일선 적용
                    if volatility_ratio < 0.5: continue
                else:
                    if not is_above_200: continue      # 금, 채권, ETF: 200일선 방어막 유지
                    if volatility_ratio < 0.5: continue

                # 3. 방아쇠 (20일 고점 돌파)
                if current_price >= stock_data['High'].iloc[-21:-1].max().item():
                    if current_total_units + 1 > MAX_TOTAL_UNITS: skipped_signals.append(f"- [{name}] 총 Unit 초과로 보류")
                    elif current_sector_units[sector] + 1 > MAX_SECTOR_UNITS: skipped_signals.append(f"- [{name}] {sector} 한도 초과")
                    else:
                        order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                        stop_loss_price = current_price - (2 * N)
                        portfolio[ticker] = {'name': name, 'units': unit_size, 'last_buy_price': current_price, 'stop_loss': stop_loss_price}
                        current_total_units += 1
                        current_sector_units[sector] += 1
                        buy_signals.append(f"- [{name}] ✨ 신규 1차 진입 ({unit_size}주) ➞ {order_res} [📊 차트]({chart_link})")

        except Exception: pass
        time.sleep(0.3)

with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f: json.dump(portfolio, f, indent=4, ensure_ascii=False)

# ==========================================
# 🌟 5. 브리핑 전송 (디스코드 + 구글 시트)
# ==========================================
buy_text = '\n'.join(buy_signals[:10]) if buy_signals else '신호 없음'
sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '신호 없음'
skip_text = '\n'.join(skipped_signals[:5]) if skipped_signals else '보류 없음'

if buy_signals or sell_signals or skipped_signals:
    prompt = f"""
    아래는 퀀트 봇 v9.3의 체결 결과입니다. 짧고 건조한 전문가 톤으로 요약하세요.
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
    final_content = f"🤖 **터틀 펀드 v9.3 (모의투자)** 🤖\n{response_text}"
else:
    final_content = f"🤖 **터틀 펀드 v9.3 가동 중** 🤖\n계좌 리스크 {current_total_units}/{MAX_TOTAL_UNITS} Units. 현재 시장 상황 관망 중."

requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content})

if SHEET_WEBHOOK_URL:
    kr_time = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    buy_count = len(buy_signals)
    sell_count = len(sell_signals)
    summary_msg = f"매수 {buy_count}건, 청산 {sell_count}건" if (buy_count > 0 or sell_count > 0) else "특이사항 없음 (관망)"
    
    sheet_data = {
        "date": kr_time,
        "total_units": f"{current_total_units} / {MAX_TOTAL_UNITS}",
        "buys": buy_count,
        "sells": sell_count,
        "message": summary_msg
    }
    try:
        requests.post(SHEET_WEBHOOK_URL, json=sheet_data, timeout=5)
        print("📊 구글 시트 업데이트 완료!")
    except Exception as e:
        print(f"⚠️ 구글 시트 업데이트 실패: {e}")
