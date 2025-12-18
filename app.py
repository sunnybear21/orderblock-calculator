# -*- coding: utf-8 -*-
"""
주식 분석 도구 - 단일 페이지 버전
v1.4 - 주도 테마 분석기 추가
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
    """KRX API로 투자자별 상세 수급 데이터 (연기금, 사모 포함)"""
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
tab1, tab2, tab3 = st.tabs([
    "오더블록 계산기",
    "수급 추적기",
    "주도 테마 분석"
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

                # 연기금/사모/투신 상세 데이터 미리 가져오기 (종합 해석용)
                detailed_data = get_detailed_supply_pykrx(supply_code, days=7)

                # 상세 데이터 합계
                if detailed_data:
                    total_pension = sum(d['pension'] for d in detailed_data)
                    total_private = sum(d['private'] for d in detailed_data)
                    total_invest_trust = sum(d['invest_trust'] for d in detailed_data)
                    total_financial = sum(d['financial'] for d in detailed_data)
                else:
                    total_pension = 0
                    total_private = 0
                    total_invest_trust = 0
                    total_financial = 0

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
                st.markdown('<h4><i class="fa-solid fa-lightbulb" style="color: #ffc107;"></i> 종합 수급 해석</h4>', unsafe_allow_html=True)

                total_smart = total_foreign + total_inst

                # 종합 스마트머니 (연기금+사모+투신 포함)
                total_all_smart = total_foreign + total_inst + total_pension + total_private + total_invest_trust

                # 최근 추세 분석 (최근 3일 vs 이전 4일)
                daily = analysis['daily_data']
                if len(daily) >= 5:
                    recent_3 = sum(d['smart_net'] for d in daily[:3])
                    prev_4 = sum(d['smart_net'] for d in daily[3:])
                    trend_turning = (recent_3 > 0 and prev_4 < 0) or (recent_3 < 0 and prev_4 > 0)
                else:
                    recent_3 = 0
                    prev_4 = 0
                    trend_turning = False

                # 투자자별 방향 체크
                foreign_buy = total_foreign > 0
                inst_buy = total_inst > 0
                pension_buy = total_pension > 0
                private_buy = total_private > 0
                trust_buy = total_invest_trust > 0

                # 방향 일치 수 (매수 방향)
                buy_count = sum([foreign_buy, inst_buy, pension_buy, private_buy, trust_buy])
                sell_count = 5 - buy_count

                # 종합 수급 판단 (연기금, 사모 등 포함)
                if detailed_data and total_all_smart > 0 and buy_count >= 4:
                    signal_text = "전방위 매집"
                    signal_color = "#28a745"
                    signal_icon = "fa-arrows-up-to-line"
                    tip = "외국인+기관+연기금+사모 모두 매수 중! 강력한 상승 신호"
                elif detailed_data and total_pension > 0 and total_smart > 0:
                    signal_text = "장기 스마트머니 매집"
                    signal_color = "#28a745"
                    signal_icon = "fa-landmark"
                    tip = "연기금(국민연금 등) + 외국인/기관 동반 매수. 장기 상승 기대"
                elif detailed_data and total_pension > 0 and total_smart < 0:
                    signal_text = "연기금 단독 매집"
                    signal_color = "#17a2b8"
                    signal_icon = "fa-landmark"
                    tip = "연기금 매수 vs 외국인/기관 매도. 장기 관점에서 긍정적"
                elif total_smart > 0 and analysis['buy_days'] >= 5:
                    signal_text = "강한 매집"
                    signal_color = "#28a745"
                    signal_icon = "fa-arrow-up"
                    tip = "스마트머니가 적극 매수 중. 단기 상승 가능성 높음"
                elif total_smart > 0 and analysis['buy_days'] >= 4:
                    signal_text = "매집 중"
                    signal_color = "#28a745"
                    signal_icon = "fa-arrow-up"
                    tip = "외국인+기관 순매수 우위. 상승 추세 지속 가능"
                elif detailed_data and total_all_smart < 0 and sell_count >= 4:
                    signal_text = "전방위 매도"
                    signal_color = "#dc3545"
                    signal_icon = "fa-arrows-down-to-line"
                    tip = "외국인+기관+연기금+사모 모두 매도! 강력한 하락 신호"
                elif detailed_data and total_pension < 0 and total_smart < 0:
                    signal_text = "장기 자금 이탈"
                    signal_color = "#dc3545"
                    signal_icon = "fa-landmark"
                    tip = "연기금까지 매도 중. 장기 하락 주의"
                elif total_smart < 0 and analysis['sell_days'] >= 5:
                    signal_text = "강한 매도"
                    signal_color = "#dc3545"
                    signal_icon = "fa-arrow-down"
                    tip = "스마트머니 대량 이탈 중. 하락 주의"
                elif total_smart < 0 and analysis['sell_days'] >= 4:
                    signal_text = "물량 정리"
                    signal_color = "#dc3545"
                    signal_icon = "fa-arrow-down"
                    tip = "외국인+기관 순매도 우위. 추가 하락 가능성"
                elif trend_turning and recent_3 > 0:
                    signal_text = "매수 전환"
                    signal_color = "#17a2b8"
                    signal_icon = "fa-rotate"
                    tip = "최근 3일 매수로 전환! 추세 변화 가능성"
                elif trend_turning and recent_3 < 0:
                    signal_text = "매도 전환"
                    signal_color = "#fd7e14"
                    signal_icon = "fa-rotate"
                    tip = "최근 3일 매도로 전환. 차익실현 또는 하락 전조"
                elif total_foreign > 0 and total_inst < 0:
                    signal_text = "외국인 주도"
                    signal_color = "#17a2b8"
                    signal_icon = "fa-globe"
                    tip = "외국인 매수 vs 기관 매도. 외국인 방향 주시"
                elif total_foreign < 0 and total_inst > 0:
                    signal_text = "기관 주도"
                    signal_color = "#fd7e14"
                    signal_icon = "fa-building"
                    tip = "기관 매수 vs 외국인 매도. 기관 방향 주시"
                else:
                    signal_text = "관망"
                    signal_color = "#6c757d"
                    signal_icon = "fa-minus"
                    tip = "뚜렷한 방향 없음. 추가 관찰 필요"

                # 메인 신호 박스
                st.markdown(f'''
                <div style="background: linear-gradient(135deg, {signal_color}22, {signal_color}11);
                            border-left: 4px solid {signal_color};
                            padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <h4 style="margin:0; color:{signal_color};">
                        <i class="fa-solid {signal_icon}"></i> {signal_text}
                    </h4>
                    <p style="margin:8px 0 0 0; color:#aaa; font-size:14px;">
                        {tip}
                    </p>
                    <p style="margin:8px 0 0 0; color:#888; font-size:12px;">
                        외국인+기관: {total_smart/10000:+,.1f}만주 | 순매수 {analysis['buy_days']}일 / 순매도 {analysis['sell_days']}일
                    </p>
                </div>
                ''', unsafe_allow_html=True)

                # 투자자별 방향 요약 (상세 데이터 있을 때만)
                if detailed_data:
                    def get_direction_badge(is_buy, amount):
                        if amount == 0:
                            return '<span style="color:#6c757d;">중립</span>'
                        color = "#28a745" if is_buy else "#dc3545"
                        icon = "▲" if is_buy else "▼"
                        return f'<span style="color:{color};">{icon}</span>'

                    st.markdown(f'''
                    <div style="background:#1a1a2e; padding:12px; border-radius:8px; margin:10px 0;">
                        <div style="font-size:13px; color:#888; margin-bottom:8px;">투자자별 방향 (7일 합계)</div>
                        <div style="display:flex; justify-content:space-around; flex-wrap:wrap; gap:8px;">
                            <div style="text-align:center;">
                                <div style="color:#aaa; font-size:11px;">외국인</div>
                                <div>{get_direction_badge(foreign_buy, total_foreign)}</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="color:#aaa; font-size:11px;">기관</div>
                                <div>{get_direction_badge(inst_buy, total_inst)}</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="color:#aaa; font-size:11px;">연기금</div>
                                <div>{get_direction_badge(pension_buy, total_pension)}</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="color:#aaa; font-size:11px;">사모</div>
                                <div>{get_direction_badge(private_buy, total_private)}</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="color:#aaa; font-size:11px;">투신</div>
                                <div>{get_direction_badge(trust_buy, total_invest_trust)}</div>
                            </div>
                        </div>
                        <div style="text-align:center; margin-top:10px; font-size:12px; color:#888;">
                            매수 {buy_count}곳 / 매도 {sell_count}곳
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)

                # 외국인 vs 기관 비교
                st.markdown("---")
                col1, col2 = st.columns(2)

                with col1:
                    if total_foreign > 0:
                        st.markdown(f'''
                        <div style="background:#1a472a; padding:10px; border-radius:8px; text-align:center;">
                            <div style="color:#28a745; font-size:12px;">외국인</div>
                            <div style="color:#28a745; font-size:18px; font-weight:bold;">매수 우위</div>
                            <div style="color:#888; font-size:11px;">{total_foreign/10000:+,.1f}만주</div>
                        </div>
                        ''', unsafe_allow_html=True)
                    else:
                        st.markdown(f'''
                        <div style="background:#4a1a1a; padding:10px; border-radius:8px; text-align:center;">
                            <div style="color:#dc3545; font-size:12px;">외국인</div>
                            <div style="color:#dc3545; font-size:18px; font-weight:bold;">매도 우위</div>
                            <div style="color:#888; font-size:11px;">{total_foreign/10000:+,.1f}만주</div>
                        </div>
                        ''', unsafe_allow_html=True)

                with col2:
                    if total_inst > 0:
                        st.markdown(f'''
                        <div style="background:#1a472a; padding:10px; border-radius:8px; text-align:center;">
                            <div style="color:#28a745; font-size:12px;">기관</div>
                            <div style="color:#28a745; font-size:18px; font-weight:bold;">매수 우위</div>
                            <div style="color:#888; font-size:11px;">{total_inst/10000:+,.1f}만주</div>
                        </div>
                        ''', unsafe_allow_html=True)
                    else:
                        st.markdown(f'''
                        <div style="background:#4a1a1a; padding:10px; border-radius:8px; text-align:center;">
                            <div style="color:#dc3545; font-size:12px;">기관</div>
                            <div style="color:#dc3545; font-size:18px; font-weight:bold;">매도 우위</div>
                            <div style="color:#888; font-size:11px;">{total_inst/10000:+,.1f}만주</div>
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

                if detailed_data:
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

                    # 투자자별 특성 해석
                    st.markdown("##### 투자자별 해석")

                    interpretations = []

                    # 연기금 해석
                    if total_pension > 0:
                        interpretations.append(f"✅ **연기금** 순매수 {fmt_num(total_pension)} - 국민연금 등 장기 투자자 매집 (장기 상승 기대)")
                    elif total_pension < 0:
                        interpretations.append(f"⚠️ **연기금** 순매도 {fmt_num(total_pension)} - 장기 투자자 비중 축소")

                    # 사모펀드 해석
                    if total_private > 0:
                        interpretations.append(f"✅ **사모펀드** 순매수 {fmt_num(total_private)} - 단기/중기 수익 기대하는 자금 유입")
                    elif total_private < 0:
                        interpretations.append(f"⚠️ **사모펀드** 순매도 {fmt_num(total_private)} - 차익실현 또는 리스크 회피")

                    # 투신 해석
                    if total_invest_trust > 0:
                        interpretations.append(f"✅ **투신(펀드)** 순매수 {fmt_num(total_invest_trust)} - 펀드 자금 유입 중")
                    elif total_invest_trust < 0:
                        interpretations.append(f"⚠️ **투신(펀드)** 순매도 {fmt_num(total_invest_trust)} - 펀드 환매 또는 비중 축소")

                    # 금융투자 해석
                    if total_financial > 0:
                        interpretations.append(f"✅ **금융투자** 순매수 {fmt_num(total_financial)} - 증권사 자기매매 매수")
                    elif total_financial < 0:
                        interpretations.append(f"⚠️ **금융투자** 순매도 {fmt_num(total_financial)} - 증권사 물량 정리")

                    if interpretations:
                        for interp in interpretations:
                            st.markdown(interp)
                    else:
                        st.info("특이 동향 없음")

                else:
                    st.info("연기금/사모 상세 데이터 없음 (해당 종목 미지원)")

    st.markdown("---")
    st.caption("네이버 금융 + KRX 데이터 기반 / 참고용")


# ============================================================
# 탭3: 주도 테마 분석
# ============================================================

# Google Sheets 자동 로드 함수
@st.cache_data(ttl=300)  # 5분 캐시
def load_theme_data_from_sheets():
    """Google Sheets에서 주도테마 데이터 자동 로드"""
    try:
        # 시트 ID
        sheet_id = "1BG_oNWSJtIgN3cYeNb5AZPsIgP__Ty-4eDgvjJwKg04"
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"

        # requests로 직접 다운로드 (리다이렉트 따라감)
        import io
        response = requests.get(csv_url, timeout=15)
        response.raise_for_status()

        # CSV 파싱
        df = pd.read_csv(io.StringIO(response.text))

        if df.empty:
            return None, "시트에 데이터가 없습니다"

        # 컬럼명 정리
        df.columns = df.columns.str.strip()

        # 필수 컬럼 확인 (영어 컬럼명)
        required_cols = ['theme', 'days']
        if not all(col in df.columns for col in required_cols):
            return None, f"필수 컬럼 없음. 현재 컬럼: {list(df.columns)}"

        # 컬럼명 한글로 변환 (표시용)
        df = df.rename(columns={
            'theme': '테마',
            'days': '출현일수',
            'max_streak': '연속일(최대)',
            'current_streak': '현재연속',
            'stocks': '총 종목수',
            'volume': '거래대금(억)',
            'leading': '주도일수',
            'avg_change': '평균상승률'
        })

        return df, None
    except Exception as e:
        return None, str(e)

with tab3:
    st.markdown('<h3><i class="fa-solid fa-fire" style="color: #ff6b6b;"></i> 주도 테마 분석</h3>', unsafe_allow_html=True)
    st.caption("테마별 출현 빈도, 모멘텀, 다음 주도 테마 예측")

    # 데이터 소스 선택
    data_source = st.radio(
        "데이터 소스",
        ["Google Sheets (자동)", "CSV 업로드 (수동)"],
        horizontal=True,
        label_visibility="collapsed"
    )

    df_theme = None

    if data_source == "Google Sheets (자동)":
        with st.spinner("Google Sheets에서 데이터 로드 중..."):
            df_theme, error = load_theme_data_from_sheets()

        if error:
            st.warning(f"시트 로드 실패: {error}")
            st.info("시트에 데이터가 없거나 공유 설정을 확인해주세요.")
        elif df_theme is not None and len(df_theme) > 0:
            st.success(f"✅ {len(df_theme)}개 테마 데이터 로드 완료!")
    else:
        # CSV 파일 업로드
        uploaded_file = st.file_uploader("테마 데이터 CSV 업로드", type=['csv'], key="theme_csv")
        if uploaded_file is not None:
            try:
                df_theme = pd.read_csv(uploaded_file, encoding='utf-8-sig')
                df_theme.columns = df_theme.columns.str.strip()
            except Exception as e:
                st.error(f"파일 읽기 오류: {e}")

    if df_theme is not None and len(df_theme) > 0:
        try:
            # 필수 컬럼 확인 (일부만 있어도 동작)
            has_all_cols = all(col in df_theme.columns for col in ['테마', '출현일수', '연속일(최대)', '현재연속', '거래대금(억)', '주도일수', '평균상승률'])

            if has_all_cols:
                # 데이터 타입 변환
                df_theme['출현일수'] = pd.to_numeric(df_theme['출현일수'], errors='coerce').fillna(0).astype(int)
                df_theme['현재연속'] = pd.to_numeric(df_theme['현재연속'], errors='coerce').fillna(0).astype(int)
                df_theme['거래대금(억)'] = pd.to_numeric(df_theme['거래대금(억)'], errors='coerce').fillna(0)
                df_theme['주도일수'] = pd.to_numeric(df_theme['주도일수'], errors='coerce').fillna(0).astype(int)
                df_theme['평균상승률'] = pd.to_numeric(df_theme['평균상승률'], errors='coerce').fillna(0)

                # 주도력 계산 (주도일수 / 출현일수)
                df_theme['주도력'] = df_theme.apply(
                    lambda x: (x['주도일수'] / x['출현일수'] * 100) if x['출현일수'] > 0 else 0, axis=1
                )

                # 종합 점수 계산 (다음 주도 테마 예측용)
                # 가중치: 현재연속(40%) + 거래대금정규화(30%) + 주도력(20%) + 평균상승률(10%)
                max_volume = df_theme['거래대금(억)'].max() if df_theme['거래대금(억)'].max() > 0 else 1
                max_consecutive = df_theme['현재연속'].max() if df_theme['현재연속'].max() > 0 else 1

                df_theme['종합점수'] = (
                    (df_theme['현재연속'] / max_consecutive * 40) +
                    (df_theme['거래대금(억)'] / max_volume * 30) +
                    (df_theme['주도력'] / 100 * 20) +
                    (df_theme['평균상승률'] / 100 * 10)
                )

                st.markdown("---")

                # 요약 통계
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("총 테마 수", f"{len(df_theme)}개")
                col2.metric("현재 연속 중", f"{len(df_theme[df_theme['현재연속'] > 0])}개")
                col3.metric("주도 테마", f"{len(df_theme[df_theme['주도일수'] > 0])}개")
                col4.metric("총 거래대금", f"{df_theme['거래대금(억)'].sum():,.0f}억")

                st.markdown("---")

                # 1. 다음 주도 테마 예측 (종합점수 TOP 10)
                st.markdown('<h4><i class="fa-solid fa-crystal-ball" style="color: #9b59b6;"></i> 다음 주도 테마 예측</h4>', unsafe_allow_html=True)
                st.caption("현재연속 + 거래대금 + 주도력 + 상승률 종합 분석")

                top_predicted = df_theme.nlargest(10, '종합점수')[['테마', '현재연속', '거래대금(억)', '주도력', '평균상승률', '종합점수']]

                # 1위 강조
                if len(top_predicted) > 0:
                    top1 = top_predicted.iloc[0]
                    st.markdown(f'''
                    <div style="background: linear-gradient(135deg, #9b59b622, #9b59b611);
                                border-left: 4px solid #9b59b6;
                                padding: 15px; border-radius: 8px; margin: 10px 0;">
                        <h4 style="margin:0; color:#9b59b6;">
                            <i class="fa-solid fa-crown"></i> 1위: {top1['테마']}
                        </h4>
                        <p style="margin:8px 0 0 0; color:#aaa; font-size:14px;">
                            연속 {top1['현재연속']}일 | 거래대금 {top1['거래대금(억)']:,.0f}억 | 주도력 {top1['주도력']:.1f}% | 상승률 {top1['평균상승률']:.1f}%
                        </p>
                    </div>
                    ''', unsafe_allow_html=True)

                # 테이블
                st.dataframe(
                    top_predicted.style.format({
                        '거래대금(억)': '{:,.0f}',
                        '주도력': '{:.1f}%',
                        '평균상승률': '{:.1f}%',
                        '종합점수': '{:.1f}'
                    }),
                    use_container_width=True,
                    hide_index=True
                )

                st.markdown("---")

                # 2. 현재 모멘텀 (연속일 TOP 10)
                st.markdown('<h4><i class="fa-solid fa-bolt" style="color: #f39c12;"></i> 현재 모멘텀 TOP 10</h4>', unsafe_allow_html=True)
                st.caption("현재 연속으로 출현 중인 테마")

                top_momentum = df_theme[df_theme['현재연속'] > 0].nlargest(10, '현재연속')

                if len(top_momentum) > 0:
                    # 막대 차트
                    chart_data = top_momentum.set_index('테마')['현재연속']
                    st.bar_chart(chart_data, color='#f39c12')

                    # 상세 테이블
                    with st.expander("상세 보기"):
                        st.dataframe(
                            top_momentum[['테마', '현재연속', '출현일수', '거래대금(억)', '평균상승률']],
                            use_container_width=True,
                            hide_index=True
                        )
                else:
                    st.info("현재 연속 출현 중인 테마가 없습니다.")

                st.markdown("---")

                # 3. 거래대금 TOP 10
                st.markdown('<h4><i class="fa-solid fa-coins" style="color: #27ae60;"></i> 거래대금 TOP 10</h4>', unsafe_allow_html=True)
                st.caption("돈이 몰리는 테마")

                top_volume = df_theme.nlargest(10, '거래대금(억)')

                # 막대 차트
                chart_data_vol = top_volume.set_index('테마')['거래대금(억)']
                st.bar_chart(chart_data_vol, color='#27ae60')

                # 상세 테이블
                with st.expander("상세 보기"):
                    st.dataframe(
                        top_volume[['테마', '거래대금(억)', '출현일수', '현재연속', '평균상승률']].style.format({
                            '거래대금(억)': '{:,.0f}',
                            '평균상승률': '{:.1f}%'
                        }),
                        use_container_width=True,
                        hide_index=True
                    )

                st.markdown("---")

                # 4. 출현 빈도 TOP 10
                st.markdown('<h4><i class="fa-solid fa-calendar-check" style="color: #3498db;"></i> 출현 빈도 TOP 10</h4>', unsafe_allow_html=True)
                st.caption("자주 등장하는 테마")

                top_frequency = df_theme.nlargest(10, '출현일수')

                # 막대 차트
                chart_data_freq = top_frequency.set_index('테마')['출현일수']
                st.bar_chart(chart_data_freq, color='#3498db')

                # 상세 테이블
                with st.expander("상세 보기"):
                    st.dataframe(
                        top_frequency[['테마', '출현일수', '연속일(최대)', '주도일수', '평균상승률']],
                        use_container_width=True,
                        hide_index=True
                    )

                st.markdown("---")

                # 5. 주도력 TOP 10 (출현 2일 이상)
                st.markdown('<h4><i class="fa-solid fa-crown" style="color: #e74c3c;"></i> 주도력 TOP 10</h4>', unsafe_allow_html=True)
                st.caption("출현 시 주도주가 되는 비율 (출현 2일 이상)")

                top_leading = df_theme[df_theme['출현일수'] >= 2].nlargest(10, '주도력')

                if len(top_leading) > 0:
                    # 막대 차트
                    chart_data_lead = top_leading.set_index('테마')['주도력']
                    st.bar_chart(chart_data_lead, color='#e74c3c')

                    # 상세 테이블
                    with st.expander("상세 보기"):
                        st.dataframe(
                            top_leading[['테마', '주도력', '주도일수', '출현일수', '평균상승률']].style.format({
                                '주도력': '{:.1f}%',
                                '평균상승률': '{:.1f}%'
                            }),
                            use_container_width=True,
                            hide_index=True
                        )
                else:
                    st.info("출현 2일 이상인 테마가 없습니다.")

                st.markdown("---")

                # 6. 평균상승률 TOP 10 (수익성)
                st.markdown('<h4><i class="fa-solid fa-arrow-trend-up" style="color: #1abc9c;"></i> 평균상승률 TOP 10</h4>', unsafe_allow_html=True)
                st.caption("수익성 높은 테마 (출현 2일 이상)")

                top_return = df_theme[(df_theme['출현일수'] >= 2) & (df_theme['평균상승률'] > 0)].nlargest(10, '평균상승률')

                if len(top_return) > 0:
                    # 막대 차트
                    chart_data_ret = top_return.set_index('테마')['평균상승률']
                    st.bar_chart(chart_data_ret, color='#1abc9c')

                    # 상세 테이블
                    with st.expander("상세 보기"):
                        st.dataframe(
                            top_return[['테마', '평균상승률', '출현일수', '거래대금(억)']].style.format({
                                '평균상승률': '{:.1f}%',
                                '거래대금(억)': '{:,.0f}'
                            }),
                            use_container_width=True,
                            hide_index=True
                        )
                else:
                    st.info("해당 조건의 테마가 없습니다.")

                st.markdown("---")

                # 7. 전체 데이터 보기
                with st.expander("전체 데이터 보기"):
                    st.dataframe(
                        df_theme.sort_values('종합점수', ascending=False).style.format({
                            '거래대금(억)': '{:,.0f}',
                            '주도력': '{:.1f}%',
                            '평균상승률': '{:.1f}%',
                            '종합점수': '{:.1f}'
                        }),
                        use_container_width=True,
                        hide_index=True
                    )

        except Exception as e:
            st.error(f"파일 읽기 오류: {e}")

    else:
        st.info("데이터가 없습니다. Google Sheets에 데이터를 입력하거나 CSV를 업로드해주세요.")

        st.markdown("""
        **데이터 형식:**
        ```
        테마,출현일수,연속일(최대),현재연속,총 종목수,거래대금(억),주도일수,평균상승률
        로봇,8,5,5,33,68402,5,14.3
        바이오,10,10,10,27,67375,5,14.2
        ...
        ```

        💡 **루시봇 연동 시** 매일 자동으로 데이터가 업데이트됩니다!
        """)

    st.markdown("---")
    st.caption("주도주 테마 데이터 기반 분석 / 참고용")
