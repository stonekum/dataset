"""运营视图 — 面向日常运营团队的数据页（F05）。

数据流：data_loader.load_all_data → data_cleaner.clean → metrics.enrich_dataframe（结果用 st.cache_data 缓存）。
主区域：六平台 KPI 卡片、互动率趋势折线图、平台表现排行表。
侧边栏：平台多选 + 日期范围。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data_cleaner import clean
from utils.data_loader import load_all_data
from utils.metrics import enrich_dataframe

st.set_page_config(page_title="运营视图 - 海外社媒数据面板", page_icon="📊", layout="wide")

# 平台显示名映射
PLATFORM_LABELS = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "x": "X",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
}


@st.cache_data(show_spinner="加载数据中…")
def _load() -> pd.DataFrame:
    """加载、清洗、衍生指标，单次缓存。"""
    raw = load_all_data("data/samples")
    if raw.empty:
        return raw
    return enrich_dataframe(clean(raw))


def _empty_state() -> None:
    st.warning(
        "暂无可用数据。请运行 `python generate_sample_data.py` 生成示例数据，"
        "或将真实运营 CSV 放入 `data/` 目录。"
    )
    st.stop()


def _format_delta(value: float, unit: str = "") -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.0f}{unit}"


# ----------------- 主体 -----------------

st.title("📊 运营视图")
st.caption("六平台日常运营核心指标、趋势与排行")

df = _load()
if df.empty:
    _empty_state()

# --- 侧边栏筛选器 ---
with st.sidebar:
    st.header("筛选器")

    all_platforms = sorted(df["platform"].dropna().unique().tolist())
    selected_platforms = st.multiselect(
        "平台",
        options=all_platforms,
        default=all_platforms,
        format_func=lambda p: PLATFORM_LABELS.get(p, p),
    )

    min_date = df["date"].min().date()
    max_date = df["date"].max().date()
    date_range = st.date_input(
        "日期范围",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = min_date, max_date

    st.caption(f"数据时段：{min_date} → {max_date}")

# --- 应用筛选 ---
mask = (
    df["platform"].isin(selected_platforms)
    & (df["date"] >= pd.Timestamp(start_date))
    & (df["date"] <= pd.Timestamp(end_date))
)
view = df.loc[mask].copy()

if view.empty:
    st.warning("当前筛选条件下没有数据，请放宽平台或日期范围。")
    st.stop()

# --- KPI 卡片：每个被选中的平台一张 ---
st.subheader("📌 平台 KPI（基于当前筛选范围）")

# 计算每个平台的关键指标
kpi_rows = []
for platform in selected_platforms:
    sub = view[view["platform"] == platform].sort_values("date")
    if sub.empty:
        continue
    last_followers = float(sub["followers"].iloc[-1]) if pd.notna(sub["followers"].iloc[-1]) else 0
    avg_er = float(sub["engagement_rate"].mean())
    total_growth = float(sub["follower_growth"].sum())
    total_posts = float(sub["posts_count"].fillna(0).sum())
    kpi_rows.append(
        {
            "platform": platform,
            "followers": last_followers,
            "engagement_rate": avg_er,
            "follower_growth": total_growth,
            "posts_count": total_posts,
        }
    )

cols = st.columns(min(3, len(kpi_rows)) or 1)
for idx, row in enumerate(kpi_rows):
    with cols[idx % len(cols)]:
        st.markdown(f"**{PLATFORM_LABELS.get(row['platform'], row['platform'])}**")
        c1, c2 = st.columns(2)
        c1.metric("粉丝数（最新）", f"{row['followers']:,.0f}", _format_delta(row["follower_growth"]))
        c2.metric("平均互动率", f"{row['engagement_rate']:.2f}%")
        c3, c4 = st.columns(2)
        c3.metric("时段粉丝净增", _format_delta(row["follower_growth"]))
        c4.metric("时段发帖数", f"{row['posts_count']:,.0f}")
        st.divider()

# --- 互动率趋势折线图 ---
st.subheader("📈 互动率趋势")

chart_df = view.assign(
    platform_label=view["platform"].map(PLATFORM_LABELS).fillna(view["platform"])
)
fig = px.line(
    chart_df,
    x="date",
    y="engagement_rate",
    color="platform_label",
    labels={"date": "日期", "engagement_rate": "互动率 (%)", "platform_label": "平台"},
    markers=False,
)
fig.update_layout(legend_title_text="平台", height=420, margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(fig, width="stretch")

# --- 平台表现排行表 ---
st.subheader("🏆 平台表现排行（按时段总互动量）")

ranking = (
    view.assign(
        total_interactions=lambda x: x[["likes", "comments", "shares", "saves"]].fillna(0).sum(axis=1)
    )
    .groupby("platform", as_index=False)
    .agg(
        总互动量=("total_interactions", "sum"),
        总曝光=("impressions", "sum"),
        平均互动率=("engagement_rate", "mean"),
        粉丝净增=("follower_growth", "sum"),
    )
    .sort_values("总互动量", ascending=False)
    .reset_index(drop=True)
)
ranking["平台"] = ranking["platform"].map(PLATFORM_LABELS).fillna(ranking["platform"])
ranking = ranking[["平台", "总互动量", "总曝光", "平均互动率", "粉丝净增"]]

st.dataframe(
    ranking,
    width="stretch",
    hide_index=True,
    column_config={
        "总互动量": st.column_config.NumberColumn(format="%d"),
        "总曝光": st.column_config.NumberColumn(format="%d"),
        "平均互动率": st.column_config.NumberColumn(format="%.2f%%"),
        "粉丝净增": st.column_config.NumberColumn(format="%+d"),
    },
)

st.caption(
    f"数据来源：data/samples/ — 当前显示 {len(view):,} 行，"
    f"{len(selected_platforms)} 个平台，{start_date} → {end_date}"
)
