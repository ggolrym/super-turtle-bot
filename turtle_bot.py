# ==========================================
# 🐢 AI 멀티 에셋 터틀 봇 v9.4.1 (모의투자 액션 극대화/조건 대폭 완화)
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
    except requests.exceptions.Timeout:
        print("🚨 KIS 서버 응답 지연 (Timeout).")
        return None
    except Exception as e:
        print(f"🚨 KIS 토큰 에러: {e}")
        return None

kis_token = get_kis_token()
print("✅ KIS 토큰 발급 완료!" if kis_token else "❌ 토큰 발급 실패. 임무를 보류합니다.")

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
        except:
            excg_cd = 'NYS'
            
        if side == "BUY": target_price = price * 1.01 
        else: target_price = price * 0.99
            
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
# 🌟 3. 자본, 리스크 및 포트폴리오 세팅 (조건 완화)
# ==========================================
TOTAL_CAPITAL = 5000000     
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT
# 🌟 [완화] 거래대금 필터 100억 ➞ 10억으로 대폭 하향
MIN_TURNOVER_KRW = 1000000000 
PORTFOLIO_FILE = 'portfolio.json' 
# 🌟 [완화] 포트폴리오 유닛 넉넉하게 확장
MAX_TOTAL_UNITS = 20       
MAX_SECTOR_UNITS = 10       

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
    'QQQ': 'Invesco QQQ', 'SPY': 'SPDR S&P 500',
    'GLD': 'SPDR Gold', 'TLT': 'iShares 20+ Bond',
    'DBC': 'Invesco Commodity', 'VNQ': 'Vanguard Real Estate',
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

print(f"\n🤖 총 {len(all_stocks)}개 자산 쾌속 스캔 시작 (v9.4.1)!\n")

# ==========================================
# 🌟 4. 데이터 검증 및 주문 집행 (액션형 기준 적용)
# ==========================================
if kis_token: 
    for ticker, name in all_stocks.items():
        try:
            stock_data = yf.download(ticker, period='2y', progress=False)
            # 🌟 [완화] 데이터 최소 필요 일수를 200일 ➞ 60일로 단축
            if len(stock_data) < 60: continue
                
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
                # 🌟 [완화] 10일 저점 ➞ 5일 저점 이탈 시 빠른 손절/익절 (잦은 청산)
                low_5 = stock_data['Low'].iloc[-6:-1].min().item()
                
                if current_price <= pos['stop_loss'] or current_price <= low_5:
                    order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                    sell_signals.append(f"- [{name}] 청산 ({pos['units']}주) ➞ {order_res['msg']} [📊 차트]({chart_link})")
                    
                    if order_res['success']:
                        current_total_units -= pos['units']
                        current_sector_units[sector] -= pos['units']
                        del portfolio[ticker] 
                    continue
                    
                # 🌟 [완화] 불타기 기준을 절반(0.25N)으로 낮춰서 더 공격적으로 비중 확대
                if pos['units'] < 4 and current_price >= pos['last_buy_price'] + (0.25 * N):
                    if current_total_units + 1 > MAX_TOTAL_UNITS: skipped_signals.append(f"- [{name}] 총 Unit 초과 보류")
                    elif current_sector_units[sector] + 1 > MAX_SECTOR_UNITS: skipped_signals.append(f"- [{name}] {sector} 한도 초과")
                    else:
                        order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                        buy_signals.append(f"- [{name}] 🔥 {pos['units']+1}차 불타기 ({unit_size}주) ➞ {order_res['msg']}")
                        
                        if order_res['success']:
                            pos['units'] += unit_size
                            pos['last_buy_price'] = current_price
                            pos['stop_loss'] = current_price - (2 * N)
                            current_total_units += 1
                            current_sector_units[sector] += 1

            # 📂 B. 신규 진입 로직
            else:
                avg_volume = stock_data['Volume'].iloc[-21:-1].mean().item()
                turnover_krw = (current_price * avg_volume) * (1 if is_krw else exchange_rate)
                if turnover_krw < MIN_TURNOVER_KRW: continue
                
                volatility_ratio = (N / current_price) * 100
                
                # 🌟 [완화] 추세 기준선을 1/3 토막으로 깎아서 진입 장벽 낮춤
                is_above_60 = current_price >= stock_data['Close'].rolling(window=60).mean().iloc[-1].item() 
                is_above_20 = current_price >= stock_data['Close'].rolling(window=20).mean().iloc[-1].item()   
                
                if sector == 'Stock':
                    if not is_above_60: continue      # 주식: 120일 ➞ 60일선(석 달) 통과 시
                    if volatility_ratio < 0.5: continue # 주식: 변동성 1.0% ➞ 0.5%
                elif sector == 'Inverse':
                    if not is_above_20: continue       # 인버스: 60일 ➞ 20일선(한 달) 통과 시
                    if volatility_ratio < 0.2: continue # 인버스: 변동성 0.5% ➞ 0.2%
                else:
                    if not is_above_60: continue      # ETF: 200일 ➞ 60일선 통과 시
                    if volatility_ratio < 0.2: continue # ETF: 변동성 0.5% ➞ 0.2%

                # 🌟 [완화] 방아쇠: 20일 고점 ➞ 10일 고점 돌파 시 즉각 발포!
                if current_price >= stock_data['High'].iloc[-11:-1].max().item():
                    if current_total_units + 1 > MAX_TOTAL_UNITS: skipped_signals.append(f"- [{name}] 총 Unit 초과로 보류")
                    elif current_sector_units[sector] + 1 > MAX_SECTOR_UNITS: skipped_signals.append(f"- [{name}] {sector} 한도 초과")
                    else:
                        order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                        buy_signals.append(f"- [{name}] ✨ 신규 진입 ({unit_size}주) ➞ {order_res['msg']} [📊 차트]({chart_link})")
                        
                        if order_res['success']:
                            stop_loss_price = current_price - (2 * N)
                            portfolio[ticker] = {'name': name, 'units': unit_size, 'last_buy_price': current_price, 'stop_loss': stop_loss_price}
                            current_total_units += 1
                            current_sector_units[sector] += 1

        except Exception: pass
        time.sleep(0.3)

with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f: json.dump(portfolio, f, indent=4, ensure_ascii=False)

# ==========================================
# 🌟 5. 브리핑 전송 (디스코드 + 구글 시트)
# ==========================================
buy_text = '\n'.join(buy_signals[:15]) if buy_signals else '신호 없음'
sell_text = '\n'.join(sell_signals[:15]) if sell_signals else '신호 없음'
skip_text = '\n'.join(skipped_signals[:5]) if skipped_signals else '보류 없음'

if buy_signals or sell_signals or skipped_signals:
    prompt = f"""
    아래는 퀀트 봇 v9.4.1(테스트 액션 모드)의 체결 결과입니다. 
    주의: "거절/에러"가 포함된 종목은 계좌에 매수되지 않았음을 명시하세요.
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
    final_content = f"🤖 **터틀 펀드 v9.4.1 (테스트 액션 모드)** 🤖\n{response_text}"
else:
    final_content = f"🤖 **터틀 펀드 v9.4.1 가동 중** 🤖\n계좌 리스크 {current_total_units}/{MAX_TOTAL_UNITS} Units. (허들을 대폭 낮췄음에도 오늘은 장이 고요합니다.)"

requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content})

if SHEET_WEBHOOK_URL:
    kr_time = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    buy_count = len(buy_signals)
    sell_count = len(sell_signals)
    summary_msg = f"매수/청산 활발 (디스코드 확인)" if (buy_count > 0 or sell_count > 0) else "특이사항 없음 (관망)"
    
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
