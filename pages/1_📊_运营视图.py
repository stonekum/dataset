"""运营视图 — 面向日常运营团队的数据页（F05）。

数据流：data_loader.load_all_data → data_cleaner.clean → metrics.enrich_dataframe（结果用 st.cache_data 缓存）。
主区域：六平台 KPI 卡片、互动率趋势折线图、平台表现排行表。
侧边栏：平台多选 + 日期范围。
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data_sources import get_active_dataframe
from utils.ui import apply_plotly_theme, inject_page_styles, render_hero, section

st.set_page_config(page_title="运营视图 - 海外社媒数据面板", page_icon="📊", layout="wide")
inject_page_styles()

# 平台显示名映射
PLATFORM_LABELS = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "x": "X",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
}


def _empty_state() -> None:
    render_hero(
        eyebrow="OPERATIONS · 运营视图",
        title_main="先接入数据，",
        title_grad="再看运营全貌",
        subtitle="目前没有可用数据。请到「📤 数据导入」上传 CSV，或运行 python generate_sample_data.py 生成示例数据。",
    )
    st.warning(
        "暂无可用数据。请到「📤 数据导入」上传 CSV，"
        "或运行 `python generate_sample_data.py` 生成示例数据。"
    )
    st.stop()


def _format_delta(value: float, unit: str = "") -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.0f}{unit}"


# ----------------- 数据加载 -----------------

# 抑制 data_loader 的"目录无 CSV"提示 —— hero 的 meta chip 已表达数据源
_orig_warning = st.warning
st.warning = lambda *a, **k: None
try:
    df, source_label = get_active_dataframe()
finally:
    st.warning = _orig_warning

if df.empty:
    _empty_state()

# ----------------- Hero -----------------

render_hero(
    eyebrow="OPERATIONS · 运营视图",
    title_main="六平台日常运营",
    title_grad="核心指标与趋势",
    subtitle="面向运营团队的细颗粒度看板：平台 KPI、互动率趋势、表现排行。通过左侧筛选器切换平台与日期范围。",
    meta=f"数据源：{source_label}",
)

# ----------------- 侧边栏筛选 -----------------

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

# ----------------- 应用筛选 -----------------

mask = (
    df["platform"].isin(selected_platforms)
    & (df["date"] >= pd.Timestamp(start_date))
    & (df["date"] <= pd.Timestamp(end_date))
)
view = df.loc[mask].copy()

if view.empty:
    st.warning("当前筛选条件下没有数据，请放宽平台或日期范围。")
    st.stop()

# ----------------- KPI 卡片 -----------------

section(
    "平台 KPI",
    icon="📌",
    color="indigo",
    hint=f"基于当前筛选范围 · {start_date} → {end_date}",
)

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

def _delta_html(value: float) -> str:
    cls = "pos" if value > 0 else "neg" if value < 0 else "neu"
    arrow = "▲ " if value > 0 else "▼ " if value < 0 else ""
    return f'<div class="ki-delta {cls}">{arrow}{abs(value):,.0f}</div>'


cols = st.columns(min(3, len(kpi_rows)) or 1)
for idx, row in enumerate(kpi_rows):
    label = PLATFORM_LABELS.get(row["platform"], row["platform"])
    with cols[idx % len(cols)]:
        st.markdown(
            f"""
            <div class="kpi-panel">
              <div class="kpi-panel-head">
                <span class="pill">{label}</span>
                <span class="title">平台核心指标</span>
              </div>
              <div class="kpi-grid">
                <div class="kpi-item">
                  <div class="ki-label">粉丝数（最新）</div>
                  <div class="ki-value">{row['followers']:,.0f}</div>
                  {_delta_html(row['follower_growth'])}
                </div>
                <div class="kpi-item">
                  <div class="ki-label">平均互动率</div>
                  <div class="ki-value">{row['engagement_rate']:.2f}%</div>
                </div>
                <div class="kpi-item">
                  <div class="ki-label">时段粉丝净增</div>
                  <div class="ki-value">{row['follower_growth']:+,.0f}</div>
                </div>
                <div class="kpi-item">
                  <div class="ki-label">时段发帖数</div>
                  <div class="ki-value">{row['posts_count']:,.0f}</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ----------------- 互动率趋势 -----------------

section(
    "互动率趋势",
    icon="📈",
    color="rose",
    hint="按平台分色，按日聚合",
)

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
fig.update_traces(line=dict(width=2.4))
apply_plotly_theme(fig)
fig.update_layout(height=420)
st.plotly_chart(fig, width="stretch")

# ----------------- 平台排行 -----------------

section(
    "平台表现排行",
    icon="🏆",
    color="amber",
    hint="按时段总互动量排序",
)

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
    f"当前显示 {len(view):,} 行，"
    f"{len(selected_platforms)} 个平台，{start_date} → {end_date}"
)
