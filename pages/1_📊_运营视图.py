"""运营视图 — 面向日常运营团队的数据页（骨架，待 F05 实现）。"""

import streamlit as st

st.set_page_config(page_title="运营视图 - 海外社媒数据面板", page_icon="📊", layout="wide")

st.title("📊 运营视图")
st.caption("六平台核心 KPI、互动趋势、内容排行")

st.info(
    "⚠️ 这是 F01 阶段的页面骨架。完整功能（KPI 卡片、趋势折线图、"
    "内容排行表、平台筛选器、日期范围选择器）将在 F05 中实现。"
)

with st.sidebar:
    st.header("筛选器（待 F05 实现）")
    st.selectbox(
        "平台",
        ["全部", "Instagram", "TikTok", "YouTube", "X", "Facebook", "LinkedIn"],
        disabled=True,
    )
    st.date_input("日期范围", value=[], disabled=True)
