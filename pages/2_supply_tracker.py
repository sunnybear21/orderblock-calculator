# -*- coding: utf-8 -*-
"""
수급 추적기 - 외국인/기관 매매 현황 조회
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

        return df.tail(days)
    except:
        return pd.DataFrame()


def analyze_supply(df: pd.DataFrame) -> dict:
    """수급 분석"""
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
# Streamlit UI
# ============================================================

st.set_page_config(page_title="수급 추적기", page_icon="💰", layout="centered")

st.title("💰 수급 추적기")
st.caption("외국인/기관 매매 현황 조회")

if not PYKRX_AVAILABLE:
    st.error("pykrx 모듈 필요: `pip install pykrx`")
    st.stop()

# 입력
col1, col2 = st.columns([4, 1])
with col1:
    stock_input = st.text_input("종목코드 또는 종목명", placeholder="005930 또는 삼성전자", label_visibility="collapsed")
with col2:
    search_btn = st.button("조회", use_container_width=True)

# 검색
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
    with st.spinner("조회 중..."):
        stock_info = get_stock_info_naver(stock_code)
        supply_df = get_supply_data(stock_code, days=7)

        if supply_df.empty:
            st.error("데이터 없음")
            st.stop()

        analysis = analyze_supply(supply_df)

    st.markdown("---")
    st.subheader(f"{stock_info['name']} ({stock_code})")

    # 현재가
    col1, col2, col3 = st.columns(3)
    col1.metric("현재가", f"{stock_info['price']:,}원", f"{stock_info['change_pct']:+.1f}%")
    col2.metric("순매수일", f"{analysis['buy_days']}일")
    col3.metric("순매도일", f"{analysis['sell_days']}일")

    st.markdown("---")

    # 누적
    col1, col2 = st.columns(2)
    foreign_bil = analysis['total_foreign'] / 1e8
    inst_bil = analysis['total_inst'] / 1e8

    col1.metric("외국인 (7일)", f"{foreign_bil:+,.1f}억")
    col2.metric("기관 (7일)", f"{inst_bil:+,.1f}억")

    st.markdown("---")

    # 일별 테이블
    st.subheader("일별 현황")

    table_data = []
    for d in reversed(analysis['daily_data']):
        f_bil = d['foreign'] / 1e8
        i_bil = d['inst'] / 1e8
        total = d['smart_net'] / 1e8
        signal = "🔴" if d['is_buy'] else "🔵"
        table_data.append({
            '날짜': d['date'],
            '외국인': f"{f_bil:+,.1f}억",
            '기관': f"{i_bil:+,.1f}억",
            '합계': f"{total:+,.1f}억",
            '': signal
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("pykrx 데이터 기반 · 참고용")
