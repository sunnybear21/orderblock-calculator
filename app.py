# -*- coding: utf-8 -*-
"""
주식 분석 도구 - 단일 페이지 버전
v1.3 - 연기금/사모 상세 수급 추가 (KRX API)
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
def get_supply_data_naver(stock_code: str, days: int = 10) -> list:
    """네이버 금융에서 외국인/기관 수급 데이터 스크래핑"""
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={stock_code}"
        all_data = []
        page = 1

        while len(all_data) < days and page <= 3:
            page_url = f"{url}&page={page}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(page_url, headers=headers, timeout=10)
            response.encoding = 'euc-kr'

            soup = BeautifulSoup(response.text, 'html.parser')
            # 두 번째 type2 테이블 사용
            tables = soup.find_all('table', class_='type2')
            if len(tables) < 2:
                break
            table = tables[1]

            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 7:
                    date_text = cols[0].text.strip()
                    if not date_text or '.' not in date_text:
                        continue
                    try:
                        # 날짜
                        date = datetime.strptime(date_text, '%Y.%m.%d')

                        # 기관 순매매 (컬럼 5)
                        inst_text = cols[5].text.strip().replace(',', '').replace('+', '')
                        inst = int(inst_text) if inst_text and inst_text != '-' else 0

                        # 외국인 순매매 (컬럼 6)
                        foreign_text = cols[6].text.strip().replace(',', '').replace('+', '')
                        foreign = int(foreign_text) if foreign_text and foreign_text != '-' else 0

                        all_data.append({
                            'date': date,
                            'foreign': foreign,
                            'inst': inst
                        })
                    except:
                        continue
            page += 1

        return all_data[:days]
    except:
        return []


@st.cache_data(ttl=300)
def get_detailed_supply_pykrx(stock_code: str, days: int = 7) -> list:
    """pykrx로 투자자별 상세 수급 데이터 (연기금, 사모 포함)"""
    # 방법 1: pykrx 시도
    try:
        from pykrx import stock

        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days + 5)).strftime('%Y%m%d')

        df = stock.get_market_trading_volume_by_date(start_date, end_date, stock_code, detail=True)

        if df is not None and not df.empty:
            df = df.tail(days)
            all_data = []
            for idx, row in df.iterrows():
                all_data.append({
                    'date': idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx,
                    'financial': int(row.get('금융투자', 0)),
                    'insurance': int(row.get('보험', 0)),
                    'invest_trust': int(row.get('투신', 0)),
                    'private': int(row.get('사모', 0)),
                    'bank': int(row.get('은행', 0)),
                    'other_fin': int(row.get('기타금융', 0)),
                    'pension': int(row.get('연기금', 0)),
                    'corp': int(row.get('기타법인', 0)),
                    'retail': int(row.get('개인', 0)),
                    'foreign': int(row.get('외국인', 0)),
                    'other_foreign': int(row.get('기타외국인', 0)),
                })
            if all_data:
                return all_data
    except:
        pass

    # 방법 2: KRX API 직접 호출 (fallback)
    try:
        url = 'http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd'
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020302'
        }

        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days + 5)).strftime('%Y%m%d')

        # 여러 ISIN 형식 시도 (000~009)
        for suffix in ['003', '000', '001', '002', '004', '005', '006', '007', '008', '009']:
            krx_code = f'KR7{stock_code}{suffix}'

            data = {
                'bld': 'dbms/MDC/STAT/standard/MDCSTAT02303',
                'locale': 'ko_KR',
                'inqTpCd': '2',
                'trdVolVal': '1',
                'askBid': '3',
                'strtDd': start_date,
                'endDd': end_date,
                'isuCd': krx_code,
                'isuCd2': stock_code,
                'share': '1',
                'money': '1',
                'csvxls_is498': 'false'
            }

            response = requests.post(url, headers=headers, data=data, timeout=10)
            result = response.json()

            if 'output' in result and result['output']:
                all_data = []
                for row in result['output'][:days]:
                    def parse_val(v):
                        try:
                            return int(str(v).replace(',', '').replace('+', ''))
                        except:
                            return 0

                    all_data.append({
                        'date': datetime.strptime(row['TRD_DD'], '%Y/%m/%d'),
                        'financial': parse_val(row.get('TRDVAL1', '0')),
                        'insurance': parse_val(row.get('TRDVAL2', '0')),
                        'invest_trust': parse_val(row.get('TRDVAL3', '0')),
                        'private': parse_val(row.get('TRDVAL4', '0')),
                        'bank': parse_val(row.get('TRDVAL5', '0')),
                        'other_fin': parse_val(row.get('TRDVAL6', '0')),
                        'pension': parse_val(row.get('TRDVAL7', '0')),
                        'corp': parse_val(row.get('TRDVAL8', '0')),
                        'retail': parse_val(row.get('TRDVAL9', '0')),
                        'foreign': parse_val(row.get('TRDVAL10', '0')),
                        'other_foreign': parse_val(row.get('TRDVAL11', '0')),
                    })
                return all_data
    except:
        pass

    return []


def analyze_supply(data: list) -> dict:
    """수급 데이터 분석"""
    if not data:
        return {'daily_data': [], 'total_foreign': 0, 'total_inst': 0, 'buy_days': 0, 'sell_days': 0}

    daily_data = []
    for row in data:
        date_str = row['date'].strftime('%m/%d')
        foreign = row['foreign']
        inst = row['inst']
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
            supply_data = get_supply_data_naver(supply_code, days=7)

            if not supply_data:
                st.error("데이터 없음")
            else:
                analysis = analyze_supply(supply_data)

                st.markdown("---")
                st.subheader(f"{stock_info['name']} ({supply_code})")

                col1, col2, col3 = st.columns(3)
                col1.metric("현재가", f"{stock_info['price']:,}원", f"{stock_info['change_pct']:+.1f}%")
                col2.metric("순매수일", f"{analysis['buy_days']}일")
                col3.metric("순매도일", f"{analysis['sell_days']}일")

                st.markdown("---")

                col1, col2 = st.columns(2)
                # 주식수 기준이므로 억 단위로 변환하지 않음
                total_foreign = analysis['total_foreign']
                total_inst = analysis['total_inst']

                # 만주 단위로 표시
                if abs(total_foreign) >= 10000:
                    col1.metric("외국인 (7일)", f"{total_foreign/10000:+,.1f}만주")
                else:
                    col1.metric("외국인 (7일)", f"{total_foreign:+,}주")

                if abs(total_inst) >= 10000:
                    col2.metric("기관 (7일)", f"{total_inst/10000:+,.1f}만주")
                else:
                    col2.metric("기관 (7일)", f"{total_inst:+,}주")

                # 해석 요약
                st.markdown("---")
                total_smart = total_foreign + total_inst

                # 수급 판단
                if total_smart > 0 and analysis['buy_days'] >= 4:
                    signal = "accumulating"
                    signal_text = "매집 중"
                    signal_color = "#28a745"
                    signal_icon = "fa-arrow-up"
                elif total_smart < 0 and analysis['sell_days'] >= 4:
                    signal = "distributing"
                    signal_text = "물량 정리 중"
                    signal_color = "#dc3545"
                    signal_icon = "fa-arrow-down"
                elif total_foreign > 0 and total_inst < 0:
                    signal = "foreign_buy"
                    signal_text = "외국인 매집 (기관 매도)"
                    signal_color = "#17a2b8"
                    signal_icon = "fa-right-left"
                elif total_foreign < 0 and total_inst > 0:
                    signal = "inst_buy"
                    signal_text = "기관 매집 (외국인 매도)"
                    signal_color = "#fd7e14"
                    signal_icon = "fa-right-left"
                else:
                    signal = "neutral"
                    signal_text = "방향성 없음"
                    signal_color = "#6c757d"
                    signal_icon = "fa-minus"

                st.markdown(f'''
                <div style="background: linear-gradient(135deg, {signal_color}22, {signal_color}11);
                            border-left: 4px solid {signal_color};
                            padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <h4 style="margin:0; color:{signal_color};">
                        <i class="fa-solid {signal_icon}"></i> {signal_text}
                    </h4>
                    <p style="margin:8px 0 0 0; color:#ccc; font-size:14px;">
                        7일간 외국인+기관 합계: {total_smart/10000:+,.1f}만주 / 순매수 {analysis['buy_days']}일
                    </p>
                </div>
                ''', unsafe_allow_html=True)

                st.markdown("---")

                st.markdown('<h4><i class="fa-solid fa-calendar-days" style="color: #fd7e14;"></i> 일별 현황</h4>', unsafe_allow_html=True)

                table_data = []
                for d in analysis['daily_data']:
                    foreign = d['foreign']
                    inst = d['inst']
                    total = d['smart_net']

                    # 만주 단위 또는 주 단위
                    if abs(foreign) >= 10000:
                        f_str = f"{foreign/10000:+,.1f}만"
                    else:
                        f_str = f"{foreign:+,}"

                    if abs(inst) >= 10000:
                        i_str = f"{inst/10000:+,.1f}만"
                    else:
                        i_str = f"{inst:+,}"

                    if abs(total) >= 10000:
                        t_str = f"{total/10000:+,.1f}만"
                    else:
                        t_str = f"{total:+,}"

                    table_data.append({
                        '날짜': d['date'],
                        '외국인': f_str,
                        '기관': i_str,
                        '합계': t_str
                    })

                st.dataframe(table_data, use_container_width=True, hide_index=True)

                # 연기금/사모 상세 데이터 (KRX)
                st.markdown("---")
                st.markdown('<h4><i class="fa-solid fa-building-columns" style="color: #9b59b6;"></i> 연기금 / 사모 상세</h4>', unsafe_allow_html=True)

                detailed_data = get_detailed_supply_pykrx(supply_code, days=7)

                if detailed_data:
                    # 7일 합계 계산
                    total_pension = sum(d['pension'] for d in detailed_data)
                    total_private = sum(d['private'] for d in detailed_data)
                    total_invest_trust = sum(d['invest_trust'] for d in detailed_data)

                    def fmt_num(n):
                        if abs(n) >= 10000:
                            return f"{n/10000:+,.1f}만주"
                        return f"{n:+,}주"

                    col1, col2, col3 = st.columns(3)
                    col1.metric("연기금 (7일)", fmt_num(total_pension))
                    col2.metric("사모펀드 (7일)", fmt_num(total_private))
                    col3.metric("투신 (7일)", fmt_num(total_invest_trust))

                    # 상세 테이블
                    detail_table = []
                    for d in detailed_data:
                        def fmt_short(n):
                            if abs(n) >= 10000:
                                return f"{n/10000:+,.1f}만"
                            return f"{n:+,}"

                        detail_table.append({
                            '날짜': d['date'].strftime('%m/%d'),
                            '연기금': fmt_short(d['pension']),
                            '사모': fmt_short(d['private']),
                            '투신': fmt_short(d['invest_trust']),
                            '금융투자': fmt_short(d['financial']),
                        })

                    st.dataframe(detail_table, use_container_width=True, hide_index=True)

                    # 연기금 해석
                    if total_pension > 0:
                        st.success(f"연기금 7일 순매수 {fmt_num(total_pension)} - 국민연금 등 장기투자자 매집 신호")
                    elif total_pension < 0:
                        st.warning(f"연기금 7일 순매도 {fmt_num(total_pension)}")
                else:
                    st.info("연기금/사모 상세 데이터 없음 (해당 종목 미지원)")

    st.markdown("---")
    st.caption("네이버 금융 + KRX 데이터 기반 / 참고용")
