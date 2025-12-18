# -*- coding: utf-8 -*-
"""
주식 분석 도구 - 단일 페이지 버전
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import urllib.parse
import re

st.set_page_config(
    page_title="주식 분석 도구",
    page_icon="📈",
    layout="centered"
)

# Font Awesome
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
""", unsafe_allow_html=True)

try:
    from pykrx import stock
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False


# ============================================================
# 공통 함수
# ============================================================

@st.cache_data(ttl=300)
def search_stock_code(keyword: str) -> list:
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
    try:
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'html.parser')

        price_tag = soup.select_one('p.no_today span.blind')
        current_price = int(price_tag.text.replace(',', '')) if price_tag else 0

        name_tag = soup.select_one('div.wrap_company h2 a')
        name = name_tag.text.strip() if name_tag else stock_code

        change_tag = soup.select_one('p.no_exday em span.blind')
        change_text = change_tag.text if change_tag else "0"

        is_down = soup.select_one('p.no_exday em.no_down')
        change_pct = float(change_text.replace('%', '').replace(',', ''))
        if is_down:
            change_pct = -change_pct

        return {'name': name, 'price': current_price, 'change_pct': change_pct}
    except:
        return {'name': stock_code, 'price': 0, 'change_pct': 0}


@st.cache_data(ttl=60)
def get_daily_candle_naver(stock_code: str, days: int = 60) -> pd.DataFrame:
    try:
        url = f"https://finance.naver.com/item/sise_day.naver?code={stock_code}"
        all_data = []
        page = 1

        while len(all_data) < days and page <= 10:
            page_url = f"{url}&page={page}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(page_url, headers=headers, timeout=10)
            response.encoding = 'euc-kr'

            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', class_='type2')
            if not table:
                break

            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 7:
                    date_text = cols[0].text.strip()
                    if not date_text:
                        continue
                    try:
                        date = datetime.strptime(date_text, '%Y.%m.%d')
                        all_data.append({
                            'date': date,
                            'open': int(cols[3].text.strip().replace(',', '')),
                            'high': int(cols[4].text.strip().replace(',', '')),
                            'low': int(cols[5].text.strip().replace(',', '')),
                            'close': int(cols[1].text.strip().replace(',', '')),
                            'volume': int(cols[6].text.strip().replace(',', ''))
                        })
                    except:
                        continue
            page += 1

        if not all_data:
            return pd.DataFrame()

        df = pd.DataFrame(all_data)
        df = df.set_index('date').sort_index(ascending=True)
        return df.tail(days)
    except:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_supply_data(stock_code: str, days: int = 10) -> pd.DataFrame:
    if not PYKRX_AVAILABLE:
        return pd.DataFrame()

    try:
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days + 10)).strftime('%Y%m%d')

        df = stock.get_market_trading_value_by_date(start_date, end_date, stock_code)

        if df is None or df.empty:
            return pd.DataFrame()

        return df.tail(days)
    except:
        return pd.DataFrame()


# ============================================================
# 오더블록 함수
# ============================================================

def detect_order_blocks(df: pd.DataFrame, lookback: int = 50, body_multiplier: float = 1.5) -> list:
    if df is None or len(df) < 15:
        return []

    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    order_blocks = []

    for i in range(len(df) - 2, max(len(df) - lookback, 10), -1):
        try:
            curr_open = opens[i + 1]
            curr_close = closes[i + 1]
            curr_body = abs(curr_close - curr_open)

            prev_open = opens[i]
            prev_close = closes[i]
            prev_high = highs[i]
            prev_low = lows[i]

            avg_body = np.mean([abs(closes[k] - opens[k]) for k in range(max(0, i - 10), i)])
            if avg_body == 0:
                continue

            ob_date = df.index[i].strftime('%Y-%m-%d')

            if (prev_close < prev_open) and (curr_close > curr_open) and \
               (curr_close > prev_high) and (curr_body > avg_body * body_multiplier):
                order_blocks.append({
                    'type': 'bullish', 'type_kr': '상승',
                    'date': ob_date, 'top': prev_high, 'bottom': prev_low,
                    'strength': curr_body / avg_body
                })

            if (prev_close > prev_open) and (curr_close < curr_open) and \
               (curr_close < prev_low) and (curr_body > avg_body * body_multiplier):
                order_blocks.append({
                    'type': 'bearish', 'type_kr': '하락',
                    'date': ob_date, 'top': prev_high, 'bottom': prev_low,
                    'strength': curr_body / avg_body
                })
        except:
            continue

    order_blocks.sort(key=lambda x: x['strength'], reverse=True)
    return order_blocks


def calculate_levels(current_price: float, order_blocks: list) -> dict:
    result = {
        'entry_zones': [], 'take_profit_zones': [],
        'stop_loss': None, 'nearest_support': None, 'nearest_resistance': None
    }

    bullish_obs = [ob for ob in order_blocks if ob['type'] == 'bullish']
    bearish_obs = [ob for ob in order_blocks if ob['type'] == 'bearish']

    for ob in bullish_obs:
        mid = (ob['top'] + ob['bottom']) / 2
        if mid <= current_price * 1.05:
            result['entry_zones'].append(ob)

    for ob in bearish_obs:
        mid = (ob['top'] + ob['bottom']) / 2
        if mid >= current_price * 0.95:
            result['take_profit_zones'].append(ob)

    supports = [ob for ob in bullish_obs if (ob['top'] + ob['bottom'])/2 < current_price]
    if supports:
        nearest = min(supports, key=lambda x: current_price - (x['top'] + x['bottom'])/2)
        result['nearest_support'] = nearest
        result['stop_loss'] = nearest['bottom'] * 0.998

    resistances = [ob for ob in bearish_obs if (ob['top'] + ob['bottom'])/2 > current_price]
    if resistances:
        nearest = min(resistances, key=lambda x: (x['top'] + x['bottom'])/2 - current_price)
        result['nearest_resistance'] = nearest

    return result


# ============================================================
# 수급 함수
# ============================================================

def analyze_supply(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {'daily_data': [], 'total_foreign': 0, 'total_inst': 0, 'buy_days': 0, 'sell_days': 0}

    daily_data = []
    for idx, row in df.iterrows():
        date_str = idx.strftime('%m/%d') if hasattr(idx, 'strftime') else str(idx)

        foreign = row.get('외국인합계', row.get('외국인', 0))
        inst = row.get('기관합계', 0)
        smart_net = foreign + inst

        daily_data.append({
            'date': date_str,
            'foreign': foreign,
            'inst': inst,
            'smart_net': smart_net,
            'is_buy': smart_net > 0
        })

    total_foreign = sum(d['foreign'] for d in daily_data)
    total_inst = sum(d['inst'] for d in daily_data)
    buy_days = sum(1 for d in daily_data if d['is_buy'])
    sell_days = len(daily_data) - buy_days

    return {
        'daily_data': daily_data,
        'total_foreign': total_foreign,
        'total_inst': total_inst,
        'buy_days': buy_days,
        'sell_days': sell_days
    }


# ============================================================
# 메인 UI
# ============================================================

st.markdown('<h1><i class="fa-solid fa-chart-line" style="color: #1f77b4;"></i> 주식 분석 도구</h1>', unsafe_allow_html=True)

# 탭으로 메뉴 구성
tab1, tab2 = st.tabs([
    "오더블록 계산기",
    "수급 추적기"
])

# ============================================================
# 탭1: 오더블록 계산기
# ============================================================
with tab1:
    st.markdown('<h3><i class="fa-solid fa-cube" style="color: #667eea;"></i> 오더블록 계산기</h3>', unsafe_allow_html=True)
    st.caption("손절가 / 익절구간 / 진입구간 계산")

    col1, col2 = st.columns([4, 1])
    with col1:
        ob_stock_code = st.text_input("종목코드", placeholder="005930", label_visibility="collapsed", max_chars=6, key="ob_code")
    with col2:
        ob_search_btn = st.button("분석", use_container_width=True, key="ob_btn")

    if ob_stock_code and ob_search_btn:
        if not re.match(r'^\d{6}$', ob_stock_code):
            st.error("종목코드는 6자리 숫자")
        else:
            with st.spinner("분석 중..."):
                price_info = get_stock_info_naver(ob_stock_code)
                df = get_daily_candle_naver(ob_stock_code, 60)

                if df.empty or price_info['price'] == 0:
                    st.error("데이터 없음")
                else:
                    current_price = price_info['price']
                    order_blocks = detect_order_blocks(df)
                    levels = calculate_levels(current_price, order_blocks)

                    st.markdown("---")
                    st.subheader(f"{price_info['name']} ({ob_stock_code})")

                    col1, col2, col3 = st.columns(3)
                    col1.metric("현재가", f"{current_price:,}원")
                    col2.metric("오더블록", f"{len(order_blocks)}개")
                    if levels['stop_loss']:
                        loss_pct = (levels['stop_loss'] - current_price) / current_price * 100
                        col3.metric("손절가", f"{levels['stop_loss']:,.0f}원", f"{loss_pct:+.1f}%")
                    else:
                        col3.metric("손절가", "-")

                    st.markdown("---")

                    st.markdown('<h4><i class="fa-solid fa-arrow-trend-up" style="color: #28a745;"></i> 진입 구간 (상승 OB)</h4>', unsafe_allow_html=True)
                    if levels['entry_zones']:
                        for ob in levels['entry_zones'][:5]:
                            dist = ((ob['top'] + ob['bottom'])/2 - current_price) / current_price * 100
                            st.write(f"**{ob['bottom']:,.0f} ~ {ob['top']:,.0f}원** ({dist:+.1f}%) - {ob['date']}")
                    else:
                        st.write("없음")

                    st.markdown("---")

                    st.markdown('<h4><i class="fa-solid fa-arrow-trend-down" style="color: #dc3545;"></i> 익절 구간 (하락 OB)</h4>', unsafe_allow_html=True)
                    if levels['take_profit_zones']:
                        for ob in levels['take_profit_zones'][:5]:
                            dist = ((ob['top'] + ob['bottom'])/2 - current_price) / current_price * 100
                            st.write(f"**{ob['bottom']:,.0f} ~ {ob['top']:,.0f}원** ({dist:+.1f}%) - {ob['date']}")
                    else:
                        st.write("없음")

    st.markdown("---")
    st.caption("네이버 금융 데이터 기반 / 참고용")


# ============================================================
# 탭2: 수급 추적기
# ============================================================
with tab2:
    st.markdown('<h3><i class="fa-solid fa-coins" style="color: #28a745;"></i> 수급 추적기</h3>', unsafe_allow_html=True)
    st.caption("외국인/기관 매매 현황 조회")

    if not PYKRX_AVAILABLE:
        st.error("pykrx 모듈 필요: pip install pykrx")
    else:
        col1, col2 = st.columns([4, 1])
        with col1:
            supply_input = st.text_input("종목코드 또는 종목명", placeholder="005930 또는 삼성전자", label_visibility="collapsed", key="supply_input")
        with col2:
            supply_btn = st.button("조회", use_container_width=True, key="supply_btn")

        supply_code = None
        if supply_input and not supply_input.isdigit():
            results = search_stock_code(supply_input)
            if results:
                options = [f"{r['name']} ({r['code']})" for r in results]
                selected = st.selectbox("검색 결과", options, key="supply_select")
                if selected:
                    supply_code = selected.split('(')[1].replace(')', '')
        elif supply_input and len(supply_input) == 6:
            supply_code = supply_input

        if supply_code and supply_btn:
            with st.spinner("조회 중..."):
                stock_info = get_stock_info_naver(supply_code)
                supply_df = get_supply_data(supply_code, days=7)

                if supply_df.empty:
                    st.error("데이터 없음")
                else:
                    analysis = analyze_supply(supply_df)

                    st.markdown("---")
                    st.subheader(f"{stock_info['name']} ({supply_code})")

                    col1, col2, col3 = st.columns(3)
                    col1.metric("현재가", f"{stock_info['price']:,}원", f"{stock_info['change_pct']:+.1f}%")
                    col2.metric("순매수일", f"{analysis['buy_days']}일")
                    col3.metric("순매도일", f"{analysis['sell_days']}일")

                    st.markdown("---")

                    col1, col2 = st.columns(2)
                    foreign_bil = analysis['total_foreign'] / 1e8
                    inst_bil = analysis['total_inst'] / 1e8

                    col1.metric("외국인 (7일)", f"{foreign_bil:+,.1f}억")
                    col2.metric("기관 (7일)", f"{inst_bil:+,.1f}억")

                    st.markdown("---")

                    st.markdown('<h4><i class="fa-solid fa-calendar-days" style="color: #fd7e14;"></i> 일별 현황</h4>', unsafe_allow_html=True)

                    table_data = []
                    for d in reversed(analysis['daily_data']):
                        f_bil = d['foreign'] / 1e8
                        i_bil = d['inst'] / 1e8
                        total = d['smart_net'] / 1e8
                        table_data.append({
                            '날짜': d['date'],
                            '외국인': f"{f_bil:+,.1f}억",
                            '기관': f"{i_bil:+,.1f}억",
                            '합계': f"{total:+,.1f}억"
                        })

                    st.dataframe(table_data, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.caption("pykrx 데이터 기반 / 참고용")
