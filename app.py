# -*- coding: utf-8 -*-
"""
주식 분석 도구
"""

import streamlit as st

st.set_page_config(
    page_title="주식 분석 도구",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Font Awesome
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
""", unsafe_allow_html=True)

st.markdown('<h1><i class="fa-solid fa-chart-line" style="color: #1f77b4;"></i> 주식 분석 도구</h1>', unsafe_allow_html=True)

st.markdown("---")

st.markdown("""
<h3><i class="fa-solid fa-cube" style="color: #667eea;"></i> 오더블록 계산기</h3>
<p>손절가 / 익절구간 / 진입구간 계산</p>

<h3><i class="fa-solid fa-coins" style="color: #28a745;"></i> 수급 추적기</h3>
<p>외국인/기관 매매 현황 조회</p>
""", unsafe_allow_html=True)

st.markdown("---")

st.markdown('<p><i class="fa-solid fa-arrow-left"></i> 왼쪽 사이드바에서 도구 선택</p>', unsafe_allow_html=True)

st.caption("네이버 금융 + pykrx 데이터 기반")
