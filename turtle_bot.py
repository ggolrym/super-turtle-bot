# ==========================================
# 🐢 AI 멀티 에셋 터틀 봇 (삼성전자 1주 강제 매수 치트키 버전)
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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
KIS_APP_KEY = os.environ.get("KIS_APP_KEY")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")
KIS_ACCOUNT = os.environ.get("KIS_ACCOUNT")

if not all([GEMINI_API_KEY, DISCORD_WEBHOOK_URL, KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT]):
    print("🚨 API 키 또는 깃허브 시크릿 누락!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)
KIS_URL = "https://openapivts.koreainvestment.com:29443" 

def get_kis_token():
    url = f"{KIS_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    res = requests.post(url, headers=headers, data=json.dumps(body))
    return res.json().get("access_token") if res.status_code == 200 else None

kis_token = get_kis_token()
print("✅ KIS 토큰 발급 완료!" if kis_token else "❌ 토큰 발급 실패.")

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
            "CANO": cano, "ACNT_PRDT_CD": prdt_cd, 
            "OVRS_EXCG_CD": excg_cd, 
            "PDNO": clean_ticker, "ORD_QTY": str(int(qty)), 
            "OVRS_ORD_UNPR": str(round(price, 2)), 
            "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"
        }
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body))
        data = res.json()
        if data.get("rt_cd") == "0": return "✅ 주문 성공"
        else: return f"❌ 실패({data.get('msg1')})"
    except Exception: return f"❌ 네트워크 에러"

# ==========================================
# 장부 세팅
# ==========================================
PORTFOLIO_FILE = 'portfolio.json' 
if os.path.exists(PORTFOLIO_FILE):
    with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f: portfolio = json.load(f)
else: portfolio = {}

buy_signals, sell_signals, skipped_signals = [], [], []

# ==========================================
# 4. 검사 및 주문 집행 (🚨 절대 무적 치트키 발동)
# ==========================================
print("\n🤖 [치트키 모드] 차트 분석을 생략하고 삼성전자 매수를 시도합니다!\n")

ticker = '005930.KS'
name = '삼성전자'

try:
    # 1. 삼성전자 현재가 불러오기
    stock_data = yf.download(ticker, period='5d', progress=False)
    current_price = stock_data['Close'].iloc[-1].item()
    
    # 2. 거래소로 '시장가 매수 1주' 주문 발사
    order_res = execute_order(ticker, 1, side="BUY", price=current_price) 
    
    # 3. 장부에 기록
    portfolio[ticker] = {
        'name': name, 'units': 1, 
        'last_buy_price': current_price, 'stop_loss': current_price * 0.8
    }
    buy_signals.append(f"- [{name}] 🚨 강제 테스트 진입 (1주) ➞ {order_res}")
    
except Exception as e:
    buy_signals.append(f"- [{name}] 🚨 치트키 실행 중 에러 발생: {e}")

# 장부 저장
with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f: json.dump(portfolio, f, indent=4, ensure_ascii=False)

# ==========================================
# 5. 브리핑 작성 및 전송
# ==========================================
buy_text = '\n'.join(buy_signals) if buy_signals else '신호 없음'

prompt = f"""
아래는 모의투자 자동매매 테스트 결과입니다. 감정을 배제하고 짧게 요약하세요.
[신규 매수]
{buy_text}
"""

response_text = ""
for _ in range(3):
    try:
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        response_text = response.text 
        break 
    except Exception: time.sleep(5)
        
if not response_text: response_text = f"**매수**\n{buy_text}"

final_content = f"🤖 **무인 퀀트 시스템 API 테스트** 🤖\n{response_text}"
requests.post(DISCORD_WEBHOOK_URL, json={"content": final_content})
