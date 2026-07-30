# ==========================================
# 🐢 AI 멀티 에셋 터틀 봇 v9.6 (소액 50만 원 실전 최종본 + 무결점 픽스 통합)
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

# 🌟 2. 한국투자증권 API 통신 (타임아웃 방어)
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
        except: excg_cd = 'NYS'
            
        # 🌟 해외 주식 1% 버퍼 (슬리피지 극복 지정가)
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
# 🌟 3. 자본 및 포트폴리오 세팅 (50만 원 소액 실전)
# ==========================================
TOTAL_CAPITAL = 500000      # 💰 총 자본금 50만 원
RISK_PERCENT = 0.02        
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT

MIN_TURNOVER_KRW = 5000000000 # 거래대금 50억 이상 (우량주 필터 복구)
MAX_POSITION_KRW = 100000     # 🚨 [소액 특화] 한 종목당 최대 10만 원 제한

PORTFOLIO_FILE = 'portfolio.json' 
MAX_POSITIONS = 10          # 최대 10개 종목 (포지션 기준)
MAX_SECTOR_POSITIONS = 5       

# 🌟 정상적인 포트폴리오 로드 (강제 리셋 제거)
if os.path.exists(PORTFOLIO_FILE):
    with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f: portfolio = json.load(f)
else: portfolio = {}

exchange_rate = 1350
try:
    exchange_rate = float(fdr.DataReader('USD/KRW')['Close'].iloc[-1])
except: pass

buy_signals, sell_signals, skipped_signals = [], [], []

def get_sector(ticker):
    if ticker == 'GLDM': return 'Gold'
    elif ticker == 'DBC': return 'Commodity'
    elif ticker in ['SH', 'PSQ']: return 'Inverse' 
    return 'Stock'

# 🌟 소액 특화 미니 ETF 유지
all_stocks = {
    'SPLG': 'SPDR Portfolio S&P 500 (미니 S&P500)', 
    'GLDM': 'SPDR Gold MiniShares (미니 금 실물)', 
    'DBC': 'Invesco DB Commodity Index (원자재)', 
    'SH': 'ProShares Short S&P500 (🔥 S&P500 인버스)', 
    'PSQ': 'ProShares Short QQQ (🔥 나스닥 인버스)' 
}
try:
    kr_df = pd.read_csv('kospi_list.csv')
    for _, row in kr_df.iterrows(): all_stocks[str(row.iloc[0]).replace('.0', '').strip().zfill(6) + '.KS'] = str(row.iloc[1])
except: pass
try:
    us_df = fdr.StockListing('SP500')
    col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
    col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
    for _, row in us_df.iterrows(): all_stocks[str(row[col_sym])] = str(row[col_name])
except: pass

# 🌟 유닛(수량)이 아닌 포지션(종목 수) 기준으로 정확한 카운팅
current_positions = len(portfolio)
current_sector_positions = {'Stock': 0, 'Gold': 0, 'Commodity': 0, 'Inverse': 0}
for t in portfolio.keys(): 
    sec = get_sector(t)
    if sec in current_sector_positions: current_sector_positions[sec] += 1

print(f"\n🤖 총 {len(all_stocks)}개 자산 실전 스캔 시작 (v9.6 최종본)!\n")

# ==========================================
# 🌟 4. 데이터 검증 및 엄격한 실전 매매 집행
# ==========================================
if kis_token: 
    for ticker, name in all_stocks.items():
        try:
            # 🌟 실전용 2년 치 데이터 조회 복구
            stock_data = yf.download(ticker, period='2y', progress=False)
            
            # yfinance 버그 완벽 패치 (MultiIndex 평탄화 및 결측치 제거)
            if isinstance(stock_data.columns, pd.MultiIndex):
                stock_data.columns = stock_data.columns.get_level_values(0)
            stock_data = stock_data.dropna()
            
            # 데이터 200일 미만 신규 상장주 컷오프 복구
            if len(stock_data) < 200: continue
                
            current_price = float(stock_data['Close'].iloc[-1])
            is_krw = ticker.endswith('.KS')
            current_price_krw = current_price if is_krw else current_price * exchange_rate
            
            # 🚨 [소액 보호] 1주 가격이 10만 원을 넘어가면 분산 투자를 위해 스킵
            if current_price_krw > MAX_POSITION_KRW: continue
            
            high_low = stock_data['High'] - stock_data['Low']
            high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
            low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            N = float(tr.rolling(window=20).mean().iloc[-1])
            
            # 0으로 나누기 버그 원천 차단
            if pd.isna(N) or N <= 0: continue
            
            N_krw = N if is_krw else N * exchange_rate
            unit_size = math.floor(RISK_AMOUNT / N_krw)
            unit_size = 1 if unit_size == 0 else unit_size

            # 🚨 [오버사이징 방지] 구매 금액이 10만 원을 넘으면 강제로 수량 깎기
            if unit_size * current_price_krw > MAX_POSITION_KRW:
                unit_size = math.floor(MAX_POSITION_KRW / current_price_krw)
                if unit_size == 0: continue 

            chart_link = f"https://finance.naver.com/item/fchart.naver?code={ticker.replace('.KS', '')}" if is_krw else f"https://finance.yahoo.com/quote/{ticker}/chart"
            sector = get_sector(ticker)

            # 📂 A. 청산 및 불타기 로직
            if ticker in portfolio:
                pos = portfolio[ticker]
                low_10 = float(stock_data['Low'].iloc[-11:-1].min())
                
                # 익절/손절선 이탈 시 10일 저점 기준 철저한 청산
                if current_price <= pos['stop_loss'] or current_price <= low_10:
                    order_res = execute_order(ticker, pos['units'], side="SELL", price=current_price)
                    sell_signals.append(f"- [{name}] 전량 청산 ({pos['units']}주) ➞ {order_res['msg']} [📊 차트]({chart_link})")
                    
                    if order_res['success']:
                        current_positions -= 1
                        current_sector_positions[sector] -= 1
                        del portfolio[ticker] 
                    continue
                    
                # 신중한 불타기 (0.5N 상승 시, 청크 단위 관리)
                chunks = pos.get('chunks', 1)
                if chunks < 4 and current_price >= pos['last_buy_price'] + (0.5 * N):
                    order_res = execute_order(ticker, unit_size, side="BUY", price=current_price)
                    buy_signals.append(f"- [{name}] 🔥 {chunks+1}차 불타기 ({unit_size}주) ➞ {order_res['msg']}")
                    
                    if order_res['success']:
                        pos['units'] += unit_size
                        pos['chunks'] = chunks + 1
                        pos['last_buy_price'] = current_price
                        pos['stop_loss'] = current_price - (2 * N)

            # 📂 B. 신규 진입 로직 (실전 필터 복구)
            else:
                avg_volume = float(stock_data['Volume'].iloc[-21:-1].mean())
                turnover_krw = (current_price * avg_volume) * (1 if is_krw else exchange_rate)
                if turnover_krw < MIN_TURNOVER_KRW: continue
                
                volatility_ratio = (N / current_price) * 100
                is_above_200 = current_price >= float(stock_data['Close'].rolling(window=200).mean().iloc[-1])
                is_above_120 = current_price >= float(stock_data['Close'].rolling(window=120).mean().iloc[-1]) 
                is_above_60 = current_price >= float(stock_data['Close'].rolling(window=60).mean().iloc[-1])   
                
                # 🌟 3중 추세/변동성 필터 복구
                if sector == 'Stock':
                    if not is_above_120: continue      
                    if volatility_ratio < 1.0: continue 
                elif sector == 'Inverse':
                    if not is_above_60: continue       
                    if volatility_ratio < 0.5: continue
                else:
                    if not is_above_200: continue      
                    if volatility_ratio < 0.5: continue

                # 🌟 실전 방아쇠: 까다로운 최근 20일(한 달) 고점 돌파!
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

        except Exception as e: 
            continue
        time.sleep(0.3)

with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f: json.dump(portfolio, f, indent=4, ensure_ascii=False)

# ==========================================
# 🌟 5. 브리핑 전송
# ==========================================
buy_text = '\n'.join(buy_signals[:10]) if buy_signals else '신호 없음'
sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '신호 없음'
skip_text = '\n'.join(skipped_signals[:5]) if skipped_signals else '보류 없음'

if buy_signals or sell_signals or skipped_signals:
    prompt = f"""
    아래는 퀀트 봇 v9.6(소액 실전 최종 버전)의 체결 결과입니다. 
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
    final_content = f"🤖 **터틀 펀드 v9.6 (50만 원 실전 가동)** 🤖\n{response_text}"
else:
    final_content = f"🤖 **터틀 펀드 v9.6 가동 중** 🤖\n보유 종목 {current_positions}/{MAX_POSITIONS} 개. 현재 시장 상황 관망 중."

requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content})

if SHEET_WEBHOOK_URL:
    kr_time = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    buy_count = len(buy_signals)
    sell_count = len(sell_signals)
    summary_msg = f"매수 {buy_count}건, 청산 {sell_count}건" if (buy_count > 0 or sell_count > 0) else "특이사항 없음 (관망)"
    
    sheet_data = {
        "date": kr_time,
        "total_positions": f"{current_positions} / {MAX_POSITIONS}",
        "buys": buy_count,
        "sells": sell_count,
        "message": summary_msg
    }
    try:
        requests.post(SHEET_WEBHOOK_URL, json=sheet_data, timeout=5)
    except Exception as e:
        print(f"⚠️ 구글 시트 업데이트 실패: {e}")
