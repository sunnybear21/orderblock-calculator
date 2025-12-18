# -*- coding: utf-8 -*-
"""
수급 머니 추적기 (Smart Money Tracker)
- 외국인/기관 매수매도 추적
- 주간 수급 추세 분석
- 매수/매도 타이밍 신호
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse

# pykrx 사용 (수급 데이터)
try:
    from pykrx import stock
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False


# ============================================================
# 네이버 금융 크롤링 함수들
# ============================================================

@st.cache_data(ttl=300)
def search_stock_code(keyword: str) -> list:
    """종목명으로 종목코드 검색"""
    try:
        encoded_keyword = urllib.parse.quote(keyword, encoding='euc-kr')
        url = f"https://finance.naver.com/search/searchList.naver?query={encoded_keyword}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'euc-kr'

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        links = soup.select('a.tltle')
        for link in links[:10]:
            href = link.get('href', '')
            name = link.text.strip()

            if 'code=' in href:
                code = href.split('code=')[1].split('&')[0]
                if len(code) == 6 and code.isdigit():
                    results.append({'code': code, 'name': name})

        return results
    except:
        return []


@st.cache_data(ttl=60)
def get_stock_info_naver(stock_code: str) -> dict:
    """네이버 금융에서 종목 정보 조회"""
    try:
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'html.parser')

        # 현재가
        price_tag = soup.select_one('p.no_today span.blind')
        current_price = int(price_tag.text.replace(',', '')) if price_tag else 0

        # 종목명
        name_tag = soup.select_one('div.wrap_company h2 a')
        name = name_tag.text.strip() if name_tag else stock_code

        # 등락률
        change_tag = soup.select_one('p.no_exday em span.blind')
        change_text = change_tag.text if change_tag else "0"

        # 부호 확인
        is_down = soup.select_one('p.no_exday em.no_down')
        change_pct = float(change_text.replace('%', '').replace(',', ''))
        if is_down:
            change_pct = -change_pct

        return {
            'name': name,
            'price': current_price,
            'change_pct': change_pct
        }
    except Exception as e:
        return {'name': stock_code, 'price': 0, 'change_pct': 0}


@st.cache_data(ttl=300)
def get_supply_data(stock_code: str, days: int = 10) -> pd.DataFrame:
    """pykrx로 수급 데이터 조회"""
    if not PYKRX_AVAILABLE:
        return pd.DataFrame()

    try:
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days + 10)).strftime('%Y%m%d')

        df = stock.get_market_trading_value_by_date(start_date, end_date, stock_code)

        if df is None or df.empty:
            return pd.DataFrame()

        # 최근 N일
        df = df.tail(days)

        return df
    except Exception as e:
        return pd.DataFrame()


def analyze_supply_trend(df: pd.DataFrame) -> dict:
    """수급 추세 분석"""
    if df is None or df.empty or len(df) < 3:
        return {
            'trend': 'UNKNOWN',
            'signal': '데이터 부족',
            'buy_days': 0,
            'sell_days': 0,
            'consecutive_buy': 0,
            'consecutive_sell': 0,
            'total_foreign': 0,
            'total_inst': 0,
            'daily_data': []
        }

    daily_data = []
    for idx, row in df.iterrows():
        date_str = idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)

        # 외국인
        foreign = 0
        if '외국인합계' in df.columns:
            foreign = row['외국인합계']
        elif '외국인' in df.columns:
            foreign = row['외국인']

        # 기관
        inst = 0
        if '기관합계' in df.columns:
            inst = row['기관합계']

        # 합산 (스마트머니)
        smart_net = foreign + inst

        daily_data.append({
            'date': date_str,
            'foreign': foreign,
            'inst': inst,
            'smart_net': smart_net,
            'is_buy': smart_net > 0
        })

    # 매수일/매도일 카운트
    buy_days = sum(1 for d in daily_data if d['is_buy'])
    sell_days = len(daily_data) - buy_days

    # 연속 매수/매도일 (최근부터 역순)
    consecutive_buy = 0
    consecutive_sell = 0
    for d in reversed(daily_data):
        if d['is_buy']:
            if consecutive_sell == 0:
                consecutive_buy += 1
            else:
                break
        else:
            if consecutive_buy == 0:
                consecutive_sell += 1
            else:
                break

    # 총 누적
    total_foreign = sum(d['foreign'] for d in daily_data)
    total_inst = sum(d['inst'] for d in daily_data)

    # 추세 판단
    trend = 'NEUTRAL'
    signal = ''

    # 1. 누적 매수 중 (3일 이상 연속)
    if consecutive_buy >= 3 and (total_foreign > 0 or total_inst > 0):
        trend = 'ACCUMULATING'
        signal = f"{consecutive_buy}일 연속 매수 중!"

    # 2. 분산 매도 중 (3일 이상 연속)
    elif consecutive_sell >= 3 and total_foreign < 0 and total_inst < 0:
        trend = 'DISTRIBUTING'
        signal = f"{consecutive_sell}일 연속 매도 중!"

    # 3. 매수 전환
    elif consecutive_buy >= 2 and consecutive_buy < len(daily_data):
        prev_idx = -(consecutive_buy + 1)
        if len(daily_data) > abs(prev_idx) and not daily_data[prev_idx]['is_buy']:
            if total_foreign > 0 or total_inst > 0:
                trend = 'TURNING_BUY'
                signal = f"매수 전환! ({consecutive_buy}일 연속)"

    # 4. 매도 전환
    elif consecutive_sell >= 1 and buy_days >= 3:
        trend = 'TURNING_SELL'
        signal = f"매도 전환! (매수 {buy_days}일 후 {consecutive_sell}일 매도)"

    # 5. 주간 5일 이상 매수
    elif buy_days >= 5:
        trend = 'ACCUMULATING'
        signal = f"주간 {buy_days}/{len(daily_data)}일 매수"

    # 6. 주간 5일 이상 매도
    elif sell_days >= 5:
        trend = 'DISTRIBUTING'
        signal = f"주간 {sell_days}/{len(daily_data)}일 매도"

    # 중립
    else:
        trend = 'NEUTRAL'
        signal = f"매수 {buy_days}일 / 매도 {sell_days}일"

    return {
        'trend': trend,
        'signal': signal,
        'buy_days': buy_days,
        'sell_days': sell_days,
        'consecutive_buy': consecutive_buy,
        'consecutive_sell': consecutive_sell,
        'total_foreign': total_foreign,
        'total_inst': total_inst,
        'daily_data': daily_data
    }


# ============================================================
# Streamlit 웹 앱
# ============================================================

st.set_page_config(
    page_title="수급 추적기",
    page_icon="💰",
    layout="centered"
)

# Font Awesome CDN 추가
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    .title-icon { font-size: 1.8rem; color: #28a745; }
    .section-icon { font-size: 1.2rem; margin-right: 8px; }
    .green { color: #28a745; }
    .red { color: #dc3545; }
    .blue { color: #1f77b4; }
    .orange { color: #fd7e14; }
    .buy-row { background-color: #d4edda; padding: 8px 12px; margin: 4px 0; border-radius: 6px; }
    .sell-row { background-color: #f8d7da; padding: 8px 12px; margin: 4px 0; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1><i class="fa-solid fa-money-bill-trend-up title-icon"></i> 수급 추적기</h1>', unsafe_allow_html=True)
st.caption("스마트머니(외국인+기관) 매수/매도 추적")

if not PYKRX_AVAILABLE:
    st.error("pykrx 모듈이 필요합니다. `pip install pykrx` 실행 후 재시작하세요.")
    st.stop()

# 종목 입력
col1, col2 = st.columns([4, 1])
with col1:
    stock_input = st.text_input("종목코드 또는 종목명", placeholder="005930 또는 삼성전자", label_visibility="collapsed")
with col2:
    search_btn = st.button("분석", use_container_width=True)

st.caption("예: 005930, 삼성전자, SK하이닉스")

# 종목 검색 결과
stock_code = None
if stock_input and not stock_input.isdigit():
    results = search_stock_code(stock_input)
    if results:
        options = [f"{r['name']} ({r['code']})" for r in results]
        selected = st.selectbox("검색 결과", options)
        if selected:
            stock_code = selected.split('(')[1].replace(')', '')
elif stock_input and len(stock_input) == 6:
    stock_code = stock_input

if stock_code and search_btn:
    with st.spinner("수급 데이터 분석 중..."):
        # 종목 정보
        stock_info = get_stock_info_naver(stock_code)

        # 수급 데이터 (7일)
        supply_df = get_supply_data(stock_code, days=7)

        if supply_df.empty:
            st.error("수급 데이터를 가져올 수 없습니다.")
            st.stop()

        # 분석
        analysis = analyze_supply_trend(supply_df)

    # 결과 표시
    st.markdown("---")

    # 종목 정보
    st.subheader(f"{stock_info['name']} ({stock_code})")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("현재가", f"{stock_info['price']:,}원", f"{stock_info['change_pct']:+.2f}%")
    with col2:
        st.metric("매수일", f"{analysis['buy_days']}일 / 7일")
    with col3:
        st.metric("매도일", f"{analysis['sell_days']}일 / 7일")

    # 추세 신호
    st.markdown("---")
    trend = analysis['trend']

    if trend == 'ACCUMULATING':
        st.success(f"**🟢 누적 매수 중** - {analysis['signal']}")
        st.info("스마트머니가 모으는 중! 매수 타이밍")
    elif trend == 'TURNING_BUY':
        st.success(f"**🔄 매수 전환** - {analysis['signal']}")
        st.info("매도에서 매수로 전환! 진입 고려")
    elif trend == 'DISTRIBUTING':
        st.error(f"**🔴 분산 매도 중** - {analysis['signal']}")
        st.warning("스마트머니가 던지는 중! 매수 금지, 보유 시 청산 고려")
    elif trend == 'TURNING_SELL':
        st.error(f"**⚠️ 매도 전환** - {analysis['signal']}")
        st.warning("매수에서 매도로 전환! 보유 시 청산 고려")
    else:
        st.info(f"**➖ 중립** - {analysis['signal']}")
        st.write("뚜렷한 방향 없음. 추가 분석 필요")

    # 누적 수급
    st.markdown("---")
    st.markdown('<h3><i class="fa-solid fa-chart-pie section-icon blue"></i>주간 누적 수급</h3>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        foreign_bil = analysis['total_foreign'] / 1e8
        color = "green" if foreign_bil >= 0 else "red"
        st.markdown(f"""
        <div style="text-align: center; padding: 20px; background: #f8f9fa; border-radius: 10px;">
            <div style="font-size: 0.9rem; color: #666;">외국인</div>
            <div style="font-size: 1.8rem; font-weight: bold; color: {color};">{foreign_bil:+,.1f}억</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        inst_bil = analysis['total_inst'] / 1e8
        color = "green" if inst_bil >= 0 else "red"
        st.markdown(f"""
        <div style="text-align: center; padding: 20px; background: #f8f9fa; border-radius: 10px;">
            <div style="font-size: 0.9rem; color: #666;">기관</div>
            <div style="font-size: 1.8rem; font-weight: bold; color: {color};">{inst_bil:+,.1f}억</div>
        </div>
        """, unsafe_allow_html=True)

    # 일별 상세
    st.markdown("---")
    st.markdown('<h3><i class="fa-solid fa-calendar-days section-icon orange"></i>일별 수급 내역</h3>', unsafe_allow_html=True)

    for d in reversed(analysis['daily_data']):
        foreign_bil = d['foreign'] / 1e8
        inst_bil = d['inst'] / 1e8
        smart_bil = d['smart_net'] / 1e8

        if d['is_buy']:
            st.markdown(f"""
            <div class="buy-row">
                <strong>{d['date']}</strong>
                <span style="float: right; color: green; font-weight: bold;">📈 매수</span>
                <br>
                <small>외국인: {foreign_bil:+,.1f}억 | 기관: {inst_bil:+,.1f}억 | 합계: {smart_bil:+,.1f}억</small>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="sell-row">
                <strong>{d['date']}</strong>
                <span style="float: right; color: red; font-weight: bold;">📉 매도</span>
                <br>
                <small>외국인: {foreign_bil:+,.1f}억 | 기관: {inst_bil:+,.1f}억 | 합계: {smart_bil:+,.1f}억</small>
            </div>
            """, unsafe_allow_html=True)

    # 매매 전략
    st.markdown("---")
    st.markdown('<h3><i class="fa-solid fa-lightbulb section-icon orange"></i>매매 전략</h3>', unsafe_allow_html=True)

    if trend in ('ACCUMULATING', 'TURNING_BUY'):
        st.markdown("""
        - ✅ **매수 고려** - 스마트머니가 매수 중
        - 📊 오더블록 계산기로 진입가/손절가 확인
        - ⏳ 연속 매수 지속 여부 모니터링
        """)
    elif trend in ('DISTRIBUTING', 'TURNING_SELL'):
        st.markdown("""
        - ❌ **매수 금지** - 스마트머니가 매도 중
        - 💨 보유 중이면 청산 고려
        - 👀 매수 전환 신호 대기
        """)
    else:
        st.markdown("""
        - ➖ **관망** - 뚜렷한 방향 없음
        - 📈 연속 매수 3일 이상 시 매수 신호
        - 📉 연속 매도 3일 이상 시 매도 신호
        """)

# 푸터
st.markdown("---")
st.caption("pykrx 데이터 기반 · 오더블록 계산기와 함께 사용 권장")
