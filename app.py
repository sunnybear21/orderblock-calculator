# -*- coding: utf-8 -*-
"""
오더블록 계산기 (Order Block Calculator)
- 손절가 / 익절구간 / 진입구간 자동 계산
- 네이버 금융 크롤링 (API 키 불필요)
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from datetime import datetime
import re


# ============================================================
# 네이버 금융 크롤링 함수들
# ============================================================

@st.cache_data(ttl=300)
def search_stock_code(keyword: str) -> list:
    """종목명으로 종목코드 검색 (네이버 금융 검색 페이지 크롤링)"""
    import urllib.parse
    try:
        # 한글 URL 인코딩 (euc-kr)
        encoded_keyword = urllib.parse.quote(keyword, encoding='euc-kr')
        url = f"https://finance.naver.com/search/searchList.naver?query={encoded_keyword}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'euc-kr'

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        # 검색 결과 테이블에서 종목 추출
        links = soup.select('a.tltle')
        for link in links[:10]:  # 상위 10개만
            href = link.get('href', '')
            name = link.text.strip()

            # 종목코드 추출 (code=XXXXXX)
            if 'code=' in href:
                code = href.split('code=')[1].split('&')[0]
                if len(code) == 6 and code.isdigit():
                    results.append({'code': code, 'name': name})

        return results
    except Exception as e:
        return []


@st.cache_data(ttl=60)
def get_daily_candle_naver(stock_code: str, days: int = 60) -> pd.DataFrame:
    """네이버 금융에서 일봉 데이터 크롤링"""
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


@st.cache_data(ttl=30)
def get_current_price_naver(stock_code: str) -> dict:
    """네이버 금융에서 현재가 조회"""
    try:
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'  # 메인 페이지는 utf-8

        soup = BeautifulSoup(response.text, 'html.parser')
        price_tag = soup.select_one('p.no_today span.blind')
        current_price = int(price_tag.text.replace(',', '')) if price_tag else 0

        name_tag = soup.select_one('div.wrap_company h2 a')
        name = name_tag.text.strip() if name_tag else stock_code

        return {'name': name, 'price': current_price}
    except:
        return {'name': stock_code, 'price': 0}


def detect_order_blocks(df: pd.DataFrame, lookback: int = 50, body_multiplier: float = 1.5) -> list:
    """오더블록 감지"""
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

            # 상승 오더블록
            if (prev_close < prev_open) and (curr_close > curr_open) and \
               (curr_close > prev_high) and (curr_body > avg_body * body_multiplier):
                order_blocks.append({
                    'type': 'bullish', 'type_kr': '상승 (매수)',
                    'date': ob_date, 'top': prev_high, 'bottom': prev_low,
                    'strength': curr_body / avg_body
                })

            # 하락 오더블록
            if (prev_close > prev_open) and (curr_close < curr_open) and \
               (curr_close < prev_low) and (curr_body > avg_body * body_multiplier):
                order_blocks.append({
                    'type': 'bearish', 'type_kr': '하락 (매도)',
                    'date': ob_date, 'top': prev_high, 'bottom': prev_low,
                    'strength': curr_body / avg_body
                })
        except:
            continue

    order_blocks.sort(key=lambda x: x['strength'], reverse=True)
    return order_blocks


def calculate_levels(current_price: float, order_blocks: list) -> dict:
    """손절가, 익절구간, 진입구간 계산"""
    result = {
        'entry_zones': [], 'take_profit_zones': [],
        'stop_loss': None, 'nearest_support': None, 'nearest_resistance': None
    }

    bullish_obs = [ob for ob in order_blocks if ob['type'] == 'bullish']
    bearish_obs = [ob for ob in order_blocks if ob['type'] == 'bearish']

    # 진입 구간
    for ob in bullish_obs:
        mid = (ob['top'] + ob['bottom']) / 2
        if mid <= current_price * 1.05:
            result['entry_zones'].append(ob)

    # 익절 구간
    for ob in bearish_obs:
        mid = (ob['top'] + ob['bottom']) / 2
        if mid >= current_price * 0.95:
            result['take_profit_zones'].append(ob)

    # 가장 가까운 지지선
    supports = [ob for ob in bullish_obs if (ob['top'] + ob['bottom'])/2 < current_price]
    if supports:
        nearest = min(supports, key=lambda x: current_price - (x['top'] + x['bottom'])/2)
        result['nearest_support'] = nearest
        result['stop_loss'] = nearest['bottom'] * 0.998

    # 가장 가까운 저항선
    resistances = [ob for ob in bearish_obs if (ob['top'] + ob['bottom'])/2 > current_price]
    if resistances:
        nearest = min(resistances, key=lambda x: (x['top'] + x['bottom'])/2 - current_price)
        result['nearest_resistance'] = nearest

    return result


# ============================================================
# Streamlit 웹 앱
# ============================================================

def main():
    st.set_page_config(
        page_title="오더블록 계산기",
        page_icon="📊",
        layout="centered"
    )

    # Font Awesome CDN 추가
    st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .title-icon { font-size: 1.8rem; color: #1f77b4; }
        .section-icon { font-size: 1.2rem; margin-right: 8px; }
        .green { color: #28a745; }
        .red { color: #dc3545; }
        .blue { color: #1f77b4; }
        .orange { color: #fd7e14; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<h1><i class="fa-solid fa-chart-line title-icon"></i> 오더블록 계산기</h1>', unsafe_allow_html=True)
    st.caption("손절가 / 익절구간 / 진입구간 자동 계산")

    # 종목 코드 입력
    col1, col2 = st.columns([4, 1])
    with col1:
        stock_code = st.text_input("종목코드 6자리", placeholder="005930", label_visibility="collapsed", max_chars=6)
    with col2:
        search_btn = st.button("분석", use_container_width=True)

    st.caption("예: 005930(삼성전자), 000660(SK하이닉스), 035720(카카오)")

    if stock_code and search_btn:
        # 종목코드 유효성 체크
        if not re.match(r'^\d{6}$', stock_code):
            st.error("종목코드는 6자리 숫자입니다. (예: 005930)")
            return

        with st.spinner("분석 중..."):
            # 데이터 조회
            price_info = get_current_price_naver(stock_code)
            df = get_daily_candle_naver(stock_code, 60)

            if df.empty or price_info['price'] == 0:
                st.error("데이터를 가져올 수 없습니다.")
                return

            current_price = price_info['price']
            order_blocks = detect_order_blocks(df)
            levels = calculate_levels(current_price, order_blocks)

        # 결과 표시
        st.markdown("---")

        # 종목 정보
        st.subheader(f"{price_info['name']} ({stock_code})")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("현재가", f"{current_price:,}원")
        with col2:
            st.metric("오더블록", f"{len(order_blocks)}개")
        with col3:
            if levels['stop_loss']:
                loss_pct = (levels['stop_loss'] - current_price) / current_price * 100
                st.metric("손절가", f"{levels['stop_loss']:,.0f}원", f"{loss_pct:+.1f}%")
            else:
                st.metric("손절가", "없음")

        # 현재 위치 판단
        st.markdown("---")
        in_resistance = False
        in_support = False

        if levels['nearest_resistance']:
            res = levels['nearest_resistance']
            if res['bottom'] * 0.98 <= current_price <= res['top'] * 1.02:
                in_resistance = True

        if levels['nearest_support']:
            sup = levels['nearest_support']
            if sup['bottom'] * 0.98 <= current_price <= sup['top'] * 1.02:
                in_support = True

        if in_resistance:
            st.warning("**저항 구간 진입!** 신규 매수 비추천, 보유 중이면 익절 고려")
        elif in_support:
            st.success("**지지 구간!** 매수 타점, 손절가 설정 필수")
        else:
            st.info("**중립 구간** 아래 오더블록 참고하여 매매 계획 수립")

        # 진입 구간
        st.markdown("---")
        st.markdown('<h3><i class="fa-solid fa-arrow-trend-up section-icon green"></i>진입 구간 (상승 OB = 지지선)</h3>', unsafe_allow_html=True)
        if levels['entry_zones']:
            for ob in levels['entry_zones'][:5]:
                dist = ((ob['top'] + ob['bottom'])/2 - current_price) / current_price * 100
                st.markdown(f"""
                **{ob['bottom']:,.0f} ~ {ob['top']:,.0f}원** (거리: {dist:+.1f}%)
                - 생성일: {ob['date']} | 강도: {ob['strength']:.1f}배
                """)
        else:
            st.write("진입 구간 없음")

        # 익절 구간
        st.markdown("---")
        st.markdown('<h3><i class="fa-solid fa-arrow-trend-down section-icon red"></i>익절 구간 (하락 OB = 저항선)</h3>', unsafe_allow_html=True)
        if levels['take_profit_zones']:
            for ob in levels['take_profit_zones'][:5]:
                dist = ((ob['top'] + ob['bottom'])/2 - current_price) / current_price * 100
                st.markdown(f"""
                **{ob['bottom']:,.0f} ~ {ob['top']:,.0f}원** (거리: {dist:+.1f}%)
                - 생성일: {ob['date']} | 강도: {ob['strength']:.1f}배
                """)
        else:
            st.write("익절 구간 없음 (저항선 없음 = 상승 여력)")

        # 매매 전략
        st.markdown("---")
        st.markdown('<h3><i class="fa-solid fa-lightbulb section-icon orange"></i>매매 전략</h3>', unsafe_allow_html=True)

        strategy = []
        if levels['entry_zones']:
            entry = levels['entry_zones'][0]
            strategy.append(f"• **매수 대기**: {entry['bottom']:,.0f} ~ {entry['top']:,.0f}원 도달 시 진입")
        if levels['stop_loss']:
            strategy.append(f"• **손절 설정**: {levels['stop_loss']:,.0f}원 이탈 시 손절")
        if levels['take_profit_zones']:
            tp = levels['take_profit_zones'][0]
            strategy.append(f"• **익절 목표**: {tp['bottom']:,.0f} ~ {tp['top']:,.0f}원 도달 시 익절")

        if strategy:
            for s in strategy:
                st.markdown(s)
        else:
            st.write("오더블록 기반 전략 수립 불가 - 다른 분석 방법 활용 권장")

    # 푸터
    st.markdown("---")
    st.caption("네이버 금융 데이터 기반 · API 키 불필요")


if __name__ == "__main__":
    main()
