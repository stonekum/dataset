"""汇报视图 — 面向管理层的月度/季度汇报页（F06）。

主区域：
1. 周期摘要 KPI（最近完整周期的总曝光、总互动、净增粉丝、平均互动率）
2. 月度/季度环比文字摘要（自动生成，含关键数据点）
3. 跨平台横向对比柱状图（按周期聚合）
4. 粉丝增长曲线（按平台分色）
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data_cleaner import clean
from utils.data_loader import load_all_data
from utils.metrics import aggregate_by_period, calculate_period_change, enrich_dataframe

st.set_page_config(page_title="汇报视图 - 海外社媒数据面板", page_icon="📈", layout="wide")

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
    raw = load_all_data("data/samples")
    if raw.empty:
        return raw
    return enrich_dataframe(clean(raw))


def _format_pct(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _format_int(value: float) -> str:
    return f"{value:,.0f}"


def _build_summary_text(
    period_label: str,
    this_row: pd.Series,
    last_row: pd.Series | None,
    by_platform_this: pd.DataFrame,
) -> str:
    """生成汇报文字摘要：本期总量 + 环比 + 单平台亮点。"""
    lines = [f"**{period_label} 汇报摘要**"]

    if last_row is not None:
        impr_change = calculate_period_change(this_row["impressions"], last_row["impressions"])
        inter_change = calculate_period_change(this_row["interactions"], last_row["interactions"])
        growth_change = calculate_period_change(
            this_row["follower_growth"], last_row["follower_growth"]
        )
        lines.append(
            f"- 总曝光 **{_format_int(this_row['impressions'])}**，环比 {_format_pct(impr_change)}；"
            f"总互动 **{_format_int(this_row['interactions'])}**，环比 {_format_pct(inter_change)}。"
        )
        lines.append(
            f"- 期内净增粉丝 **{_format_int(this_row['follower_growth'])}**，"
            f"环比 {_format_pct(growth_change)}；平均互动率 **{this_row['engagement_rate']:.2f}%**。"
        )
    else:
        lines.append(
            f"- 总曝光 **{_format_int(this_row['impressions'])}**；"
            f"总互动 **{_format_int(this_row['interactions'])}**；"
            f"净增粉丝 **{_format_int(this_row['follower_growth'])}**；"
            f"平均互动率 **{this_row['engagement_rate']:.2f}%**。"
        )
        lines.append("- 上一周期数据不足，未计算环比。")

    # 单平台亮点：互动率第一 / 净增第一
    if not by_platform_this.empty:
        top_er = by_platform_this.sort_values("engagement_rate", ascending=False).iloc[0]
        top_growth = by_platform_this.sort_values("follower_growth", ascending=False).iloc[0]
        lines.append(
            f"- 互动率最高：**{PLATFORM_LABELS.get(top_er['platform'], top_er['platform'])}** "
            f"({top_er['engagement_rate']:.2f}%)；"
            f"粉丝净增最多：**{PLATFORM_LABELS.get(top_growth['platform'], top_growth['platform'])}** "
            f"(+{_format_int(top_growth['follower_growth'])})。"
        )
    return "\n".join(lines)


# ----------------- 主体 -----------------

st.title("📈 汇报视图")
st.caption("月度 / 季度汇总、跨平台对比与文字摘要")

df = _load()
if df.empty:
    st.warning(
        "暂无可用数据。请运行 `python generate_sample_data.py` 生成示例数据，"
        "或将真实运营 CSV 放入 `data/` 目录。"
    )
    st.stop()

# --- 侧边栏 ---
with st.sidebar:
    st.header("汇报周期")
    period_choice = st.radio("周期粒度", ["月度", "季度"], horizontal=True)
    period_code = "M" if period_choice == "月度" else "Q"
    exclude_partial = st.checkbox(
        "排除未结束的当前周期",
        value=True,
        help="样本数据可能不覆盖完整周期，建议默认排除以避免环比失真。",
    )
    st.divider()
    st.caption(f"数据时段：{df['date'].min().date()} → {df['date'].max().date()}")

# --- 聚合 ---
periodic = aggregate_by_period(df, period=period_code)  # 每平台 × 周期
# 聚合后追加：interactions（总互动）和 engagement_rate（按聚合值重算）
periodic["interactions"] = (
    periodic["likes"].fillna(0)
    + periodic["comments"].fillna(0)
    + periodic["shares"].fillna(0)
    + periodic["saves"].fillna(0)
)
periodic["engagement_rate"] = (
    periodic["interactions"] / periodic["impressions"].replace(0, pd.NA) * 100
).fillna(0.0).astype(float)

# 排除最后一个未结束周期（按数据中的最大日期判定）
max_date = df["date"].max()
if exclude_partial and not periodic.empty:
    last_period_end = periodic["date"].max()
    if max_date < last_period_end:
        periodic = periodic[periodic["date"] < last_period_end]

if periodic.empty:
    st.warning("当前周期范围内无聚合数据，请取消排除当前周期或更新源数据。")
    st.stop()

# 全平台汇总（按周期）
overall = (
    periodic.groupby("date", as_index=False)
    .agg(
        impressions=("impressions", "sum"),
        interactions=("interactions", "sum"),
        follower_growth=("follower_growth", "sum"),
    )
    .sort_values("date")
    .reset_index(drop=True)
)
overall["engagement_rate"] = (
    overall["interactions"] / overall["impressions"].replace(0, pd.NA) * 100
).fillna(0.0).astype(float)

# --- KPI：最近一个完整周期 ---
this_row = overall.iloc[-1]
last_row = overall.iloc[-2] if len(overall) >= 2 else None
this_label = this_row["date"].strftime("%Y-%m" if period_code == "M" else "%Y-Q") + (
    "" if period_code == "M" else f"{((this_row['date'].month - 1) // 3) + 1}"
)

st.subheader(f"📌 {this_label} {period_choice}汇总")
k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "总曝光",
    _format_int(this_row["impressions"]),
    _format_pct(calculate_period_change(this_row["impressions"], last_row["impressions"])) if last_row is not None else None,
)
k2.metric(
    "总互动",
    _format_int(this_row["interactions"]),
    _format_pct(calculate_period_change(this_row["interactions"], last_row["interactions"])) if last_row is not None else None,
)
k3.metric(
    "净增粉丝",
    _format_int(this_row["follower_growth"]),
    _format_pct(calculate_period_change(this_row["follower_growth"], last_row["follower_growth"])) if last_row is not None else None,
)
k4.metric("平均互动率", f"{this_row['engagement_rate']:.2f}%")

# --- 文字摘要 ---
st.subheader("📝 自动摘要")
by_platform_this = periodic[periodic["date"] == this_row["date"]].copy()
st.markdown(_build_summary_text(this_label, this_row, last_row, by_platform_this))

# --- 跨平台对比柱状图 ---
st.subheader("📊 跨平台对比（按周期）")
metric_choice = st.selectbox(
    "对比指标",
    options=["impressions", "interactions", "follower_growth", "engagement_rate"],
    format_func=lambda m: {
        "impressions": "总曝光",
        "interactions": "总互动",
        "follower_growth": "净增粉丝",
        "engagement_rate": "平均互动率 (%)",
    }[m],
)
bar_df = periodic.assign(
    平台=periodic["platform"].map(PLATFORM_LABELS).fillna(periodic["platform"]),
    周期=periodic["date"].dt.strftime("%Y-%m" if period_code == "M" else "%Y-Q%q"),
)
fig_bar = px.bar(
    bar_df,
    x="周期",
    y=metric_choice,
    color="平台",
    barmode="group",
    labels={metric_choice: "数值"},
)
fig_bar.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(fig_bar, width="stretch")

# --- 粉丝增长曲线 ---
st.subheader("📈 粉丝增长曲线（按日）")
follower_df = df.assign(
    平台=df["platform"].map(PLATFORM_LABELS).fillna(df["platform"])
).sort_values(["平台", "date"])
fig_line = px.line(
    follower_df,
    x="date",
    y="followers",
    color="平台",
    labels={"date": "日期", "followers": "粉丝数"},
)
fig_line.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(fig_line, width="stretch")

st.caption(
    f"聚合粒度：{period_choice}；本期排除未结束周期：{'是' if exclude_partial else '否'}；"
    f"原始数据共 {len(df):,} 行（{df['date'].min().date()} → {df['date'].max().date()}）"
)
