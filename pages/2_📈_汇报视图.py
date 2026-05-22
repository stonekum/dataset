"""汇报视图 — 面向管理层的月度/季度汇报页（骨架，待 F06 实现）。"""

import streamlit as st

st.set_page_config(page_title="汇报视图 - 海外社媒数据面板", page_icon="📈", layout="wide")

st.title("📈 汇报视图")
st.caption("月度/季度汇总、跨平台对比、自动文字摘要")

st.info(
    "⚠️ 这是 F01 阶段的页面骨架。完整功能（月度汇总、跨平台柱状图、"
    "粉丝增长曲线、自动文字摘要、PDF 导出）将在 F06 / F07 中实现。"
)

with st.sidebar:
    st.header("周期选择（待 F06 实现）")
    st.radio("汇报周期", ["月度", "季度"], disabled=True)
