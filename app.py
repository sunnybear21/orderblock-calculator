# -*- coding: utf-8 -*-
"""
주식 분석 도구 모음
- 오더블록 계산기
- 수급 추적기
"""

import streamlit as st

st.set_page_config(
    page_title="주식 분석 도구",
    page_icon="📈",
    layout="centered"
)

# Font Awesome CDN 추가
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    .tool-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 30px;
        border-radius: 15px;
        margin: 10px 0;
        color: white;
    }
    .tool-card h3 {
        margin: 0 0 10px 0;
        color: white;
    }
    .tool-card p {
        margin: 0;
        opacity: 0.9;
    }
    .tool-card-green {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
    }
    .tool-icon {
        font-size: 2.5rem;
        margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 주식 분석 도구")
st.caption("매매 판단을 위한 분석 도구 모음")

st.markdown("---")

# 도구 소개
col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    <div class="tool-card">
        <div class="tool-icon">📊</div>
        <h3>오더블록 계산기</h3>
        <p>손절가 / 익절구간 / 진입구간 자동 계산</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("**기능:**")
    st.markdown("- 상승/하락 오더블록 감지")
    st.markdown("- 지지/저항 구간 계산")
    st.markdown("- 손절가 자동 설정")

with col2:
    st.markdown("""
    <div class="tool-card tool-card-green">
        <div class="tool-icon">💰</div>
        <h3>수급 추적기</h3>
        <p>스마트머니(외국인+기관) 매매 추적</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("**기능:**")
    st.markdown("- 7일간 수급 추세 분석")
    st.markdown("- 매수/매도 전환 신호")
    st.markdown("- 일별 상세 내역")

st.markdown("---")

# 사용 가이드
st.subheader("📖 사용 가이드")

st.markdown("""
**1단계: 수급 추적기로 종목 선별**
- 스마트머니가 **누적 매수 중**인 종목 찾기
- DISTRIBUTING(분산 매도) 종목은 피하기

**2단계: 오더블록으로 진입가 확인**
- 상승 오더블록(지지선) 근처에서 매수
- 하락 오더블록(저항선)에서 익절

**3단계: 매매 실행**
- 손절가 반드시 설정
- 수급 매도 전환 시 청산 고려
""")

st.markdown("---")

st.info("👈 왼쪽 사이드바에서 도구를 선택하세요")

# 푸터
st.markdown("---")
st.caption("Made by sunnybear · 네이버 금융 + pykrx 데이터 기반")
