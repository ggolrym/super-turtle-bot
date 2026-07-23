# ==========================================
# 🐢 AI 터틀 트레이딩 v6.0 (완전체 시스템)
# 1. 자금 관리, 2. 시스템1/2, 3. 거래대금 필터, 4. 피라미딩
# ==========================================
import os
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import requests
from google import genai
import time
import math

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
    print("🚨 금고에 API 키나 웹훅 URL이 없습니다!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 💰 1. 퀀트 트레이더의 자금 및 필터 설정
# ==========================================
TOTAL_CAPITAL = 1000000 # 총 투자금: 100만 원
RISK_PERCENT = 0.01      # 1회 매수 시 허용 리스크 (총 자산의 1%)
RISK_AMOUNT = TOTAL_CAPITAL * RISK_PERCENT # 잃을 수 있는 최대 금액 (10만 원)
MIN_TRADED_VALUE = 10000000000 # 최소 거래대금: 100억 원 (작전주 차단)

print(f"💰 총 투자금: {TOTAL_CAPITAL:,}원 / 1회 최대 리스크: {RISK_AMOUNT:,.0f}원")
print(f"🛡️ 거래대금 100억 미만 잡주 필터링 가동 중...")

exchange_rate = 1350 
try:
    ex_df = fdr.DataReader('USD/KRW')
    exchange_rate = ex_df['Close'].iloc[-1].item()
except:
    pass

buy_signals_sys2 = [] # 시스템 2 (장기 돌파)
buy_signals_sys1 = [] # 시스템 1 (단기 돌파)
pyramid_signals = []  # 피라미딩 (불타기)
sell_signals = []     # 매도/손절

# ==========================================
# 2. 방탄(Crash-proof) 명단 수집 
# ==========================================
korea_stocks = {}
try:
    kr_df = pd.read_csv('kospi_list.csv')
    col_sym, col_name = kr_df.columns[0], kr_df.columns[1]
    for _, row in kr_df.iterrows():
        korea_stocks[str(row[col_sym]).replace('.0', '').strip().zfill(6) + '.KS'] = str(row[col_name])
except:
    pass

us_stocks = {}
try:
    us_df = fdr.StockListing('SP500')
    col_sym = 'Symbol' if 'Symbol' in us_df.columns else 'Ticker'
    col_name = 'Name' if 'Name' in us_df.columns else us_df.columns[1]
    for _, row in us_df.iterrows():
        us_stocks[str(row[col_sym])] = str(row[col_name])
except:
    pass

all_stocks = {**korea_stocks, **us_stocks}
print(f"\n🤖 총 {len(all_stocks)}개 대장주 정밀 검사 시작!\n")

# ==========================================
# 3. 1,400개 컨베이어 벨트 (오리지널 터틀 로직)
# ==========================================
for ticker, name in all_stocks.items():
    try:
        stock_data = yf.download(ticker, period='1y', progress=False)
        
        if len(stock_data) >= 200:
            current_price = stock_data['Close'].iloc[-1].item()
            today_volume = stock_data['Volume'].iloc[-1].item()
            ma_200 = stock_data['Close'].rolling(window=200).mean().iloc[-1].item()
            
            # 🌟 [요소 3] 거래대금 계산 및 필터링 (100억 원)
            if ticker.endswith('.KS'):
                traded_value_krw = current_price * today_volume
                currency_mark = "원"
            else:
                traded_value_krw = current_price * today_volume * exchange_rate
                currency_mark = "달러"
                
            if traded_value_krw < MIN_TRADED_VALUE:
                continue # 거래대금 100억 미만은 가차 없이 버립니다.

            # 돌파 기준가 계산 (오늘을 제외한 과거 데이터 기준)
            high_55 = stock_data['High'].iloc[-56:-1].max().item()
            high_20 = stock_data['High'].iloc[-21:-1].max().item()
            low_20 = stock_data['Low'].iloc[-21:-1].min().item()
            low_10 = stock_data['Low'].iloc[-11:-1].min().item()
            
            # N값(ATR) 계산
            high_low = stock_data['High'] - stock_data['Low']
            high_close = (stock_data['High'] - stock_data['Close'].shift(1)).abs()
            low_close = (stock_data['Low'] - stock_data['Close'].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            current_n = tr.rolling(window=20).mean().iloc[-1].item()
            
            # 🌟 [요소 2] 자금 관리 (1 Unit 매수 수량 계산)
            n_krw = current_n if ticker.endswith('.KS') else current_n * exchange_rate
            unit_size = max(1, math.floor(RISK_AMOUNT / n_krw))
            req_money_krw = (unit_size * current_price) if ticker.endswith('.KS') else (unit_size * current_price * exchange_rate)
            
            buy_info = f"- **{name}**: 🎯 **{unit_size}주 매수 요망** (현재가: {current_price:,.2f}{currency_mark}, N값: {current_n:,.2f}, 투자금: 약 {req_money_krw:,.0f}원)"

            # 🌟 [요소 1 & 4] 진입 및 피라미딩 로직
            # 200일선 위에 있는 상승장만 거래합니다.
            if current_price > ma_200:
                # 1. 피라미딩 (불타기): 20일 돌파가보다 0.5N 이상 추가 상승했을 때
                if current_price >= high_20 + (0.5 * current_n):
                    pyramid_signals.append(f"- **{name}** (현재가: {current_price:,.2f}{currency_mark} / 이전에 샀다면 추가 매수 타점!)")
                
                # 2. 시스템 2 (55일 장기 돌파) - 속임수 방어
                elif current_price >= high_55:
                    buy_signals_sys2.append(buy_info)
                
                # 3. 시스템 1 (20일 단기 돌파)
                elif current_price >= high_20:
                    buy_signals_sys1.append(buy_info)
                
            # 매도/손절 조건: 시스템1(10일 저점 이탈) 또는 시스템2(20일 저점 이탈)
            if current_price <= low_10:
                sell_signals.append(f"- {name} (10일 저점 붕괴 - 시스템1 매도)")
            elif current_price <= low_20:
                sell_signals.append(f"- {name} (20일 저점 붕괴 - 시스템2 매도)")
                
    except Exception as e:
        pass 
        
    time.sleep(0.6)

# ==========================================
# 4. 브리핑 작성 및 전송 
# ==========================================
has_signals = bool(buy_signals_sys2 or buy_signals_sys1 or pyramid_signals or sell_signals)

if has_signals:
    buy_sys2_text = '\n'.join(buy_signals_sys2[:10]) if buy_signals_sys2 else '없음'
    buy_sys1_text = '\n'.join(buy_signals_sys1[:10]) if buy_signals_sys1 else '없음'
    pyramid_text = '\n'.join(pyramid_signals[:10]) if pyramid_signals else '없음'
    sell_text = '\n'.join(sell_signals[:10]) if sell_signals else '없음'

    prompt = f"""
    너는 오리지널 터틀 트레이딩 원칙을 철저히 지키는 퀀트 비서야.
    총 투자금 {TOTAL_CAPITAL:,}원 기준, 거래대금 100억 이상 종목만 필터링했어.
    
    - 🟣 시스템 2 매수 (55일 장기돌파, 신뢰도 높음):\n{buy_sys2_text}
    - 🟢 시스템 1 매수 (20일 단기돌파):\n{buy_sys1_text}
    - 🚀 피라미딩 타점 (0.5N 추가 상승, 불타기 구간):\n{pyramid_text}
    - 🔴 매도/손절 신호:\n{sell_text}
    
    이 결과를 바탕으로 디스코드 브리핑 메시지를 전문가답게 작성해줘. 숫자는 그대로 살려줘.
    """
    
    response_text = ""
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=prompt,
            )
            response_text = response.text 
            break 
        except:
            time.sleep(5)
            
    if not response_text:
        response_text = f"⚠️ **AI 비서 휴식 중! (원본 데이터 전송)**\n\n🟣 **시스템 2 매수:**\n{buy_sys2_text}\n\n🟢 **시스템 1 매수:**\n{buy_sys1_text}\n\n🚀 **피라미딩:**\n{pyramid_text}\n\n🔴 **매도:**\n{sell_text}"
    
    message_data = {"content": f"🐢 **터틀 시스템 완전체 리포트 (총자산 1,000만 원)** 🐢\n{response_text}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
    
else:
    message_data = {"content": "🐢 **터틀 시스템 완전체 리포트** 🐢\n조건에 부합하는 타점이 없습니다. 거래대금 100억 이상 대형 우량주 중 상승 추세를 시작한 종목이 없습니다. 관망하십시오."}
    requests.post(DISCORD_WEBHOOK_URL, data=message_data)
