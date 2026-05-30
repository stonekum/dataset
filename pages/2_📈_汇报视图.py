"""汇报视图 — 面向管理层的月度/季度汇报页（F06）。

主区域：
1. 周期摘要 KPI（最近完整周期的总曝光、总互动、净增粉丝、平均互动率）
2. 月度/季度环比文字摘要（自动生成，含关键数据点）
3. 跨平台横向对比柱状图（按周期聚合）
4. 粉丝增长曲线（按平台分色）
"""

from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.auth import require_auth
from utils.data_sources import get_active_dataframe
from utils.metrics import aggregate_by_period, calculate_period_change
from utils.pdf_report import build_period_report_pdf
from utils.ui import PLATFORM_LABELS, apply_plotly_theme, inject_page_styles, render_hero, section

st.set_page_config(page_title="汇报视图 - 海外社媒数据面板", page_icon="📈", layout="wide")
inject_page_styles()
require_auth()


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


# ----------------- 数据加载 -----------------

# 抑制 data_loader 的"目录无 CSV"提示 —— hero 的 meta chip 已表达数据源
_orig_warning = st.warning
st.warning = lambda *a, **k: None
try:
    df, source_label = get_active_dataframe()
finally:
    st.warning = _orig_warning

if df.empty:
    render_hero(
        eyebrow="EXECUTIVE · 汇报视图",
        title_main="先接入数据，",
        title_grad="再产出汇报",
        subtitle="目前没有可用数据。请到「📤 数据导入」上传 CSV，或运行 python generate_sample_data.py 生成示例数据。",
    )
    st.warning(
        "暂无可用数据。请到「📤 数据导入」上传 CSV，"
        "或运行 `python generate_sample_data.py` 生成示例数据。"
    )
    st.stop()

# ----------------- Hero -----------------

render_hero(
    eyebrow="EXECUTIVE · 汇报视图",
    title_main="月度 / 季度汇总，",
    title_grad="自动生成摘要",
    subtitle="按周期聚合关键指标，自动生成环比文字摘要、跨平台对比与粉丝增长曲线，方便直接复制进汇报材料。",
    meta=f"数据源：{source_label}",
)

# ----------------- 侧边栏 -----------------

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

# ----------------- 聚合 -----------------

periodic = aggregate_by_period(df, period=period_code)  # 每平台 × 周期
periodic["interactions"] = (
    periodic["likes"].fillna(0)
    + periodic["comments"].fillna(0)
    + periodic["shares"].fillna(0)
    + periodic["saves"].fillna(0)
)
periodic["engagement_rate"] = (
    periodic["interactions"] / periodic["impressions"].replace(0, pd.NA) * 100
).fillna(0.0).astype(float)

max_date = df["date"].max()
if exclude_partial and not periodic.empty:
    last_period_end = periodic["date"].max()
    if max_date < last_period_end:
        periodic = periodic[periodic["date"] < last_period_end]

if periodic.empty:
    st.warning("当前周期范围内无聚合数据，请取消排除当前周期或更新源数据。")
    st.stop()

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

# ----------------- 周期摘要 KPI -----------------

this_row = overall.iloc[-1]
last_row = overall.iloc[-2] if len(overall) >= 2 else None
this_label = this_row["date"].strftime("%Y-%m" if period_code == "M" else "%Y-Q") + (
    "" if period_code == "M" else f"{((this_row['date'].month - 1) // 3) + 1}"
)

section(
    f"{this_label} {period_choice}汇总",
    icon="📌",
    color="indigo",
    hint="基于最近一个完整周期",
)

def _delta_html(value: float | None) -> str:
    if value is None or pd.isna(value):
        return '<div class="ki-delta neu">—</div>'
    cls = "pos" if value > 0 else "neg" if value < 0 else "neu"
    arrow = "▲" if value > 0 else "▼" if value < 0 else "•"
    return f'<div class="ki-delta {cls}">{arrow} {abs(value):.1f}% 环比</div>'


_impr_delta = calculate_period_change(this_row["impressions"], last_row["impressions"]) if last_row is not None else None
_inter_delta = calculate_period_change(this_row["interactions"], last_row["interactions"]) if last_row is not None else None
_grow_delta = calculate_period_change(this_row["follower_growth"], last_row["follower_growth"]) if last_row is not None else None

st.markdown(
    f"""
    <div class="kpi-panel">
      <div class="kpi-panel-head">
        <span class="pill">本期总览</span>
        <span class="title">{this_label}</span>
      </div>
      <div class="kpi-grid" style="grid-template-columns: 1fr 1fr 1fr 1fr;">
        <div class="kpi-item">
          <div class="ki-label">总曝光</div>
          <div class="ki-value">{_format_int(this_row['impressions'])}</div>
          {_delta_html(_impr_delta)}
        </div>
        <div class="kpi-item">
          <div class="ki-label">总互动</div>
          <div class="ki-value">{_format_int(this_row['interactions'])}</div>
          {_delta_html(_inter_delta)}
        </div>
        <div class="kpi-item">
          <div class="ki-label">净增粉丝</div>
          <div class="ki-value">{_format_int(this_row['follower_growth'])}</div>
          {_delta_html(_grow_delta)}
        </div>
        <div class="kpi-item">
          <div class="ki-label">平均互动率</div>
          <div class="ki-value">{this_row['engagement_rate']:.2f}%</div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------- 文字摘要 -----------------

section("自动摘要", icon="📝", color="rose", hint="可直接复制粘贴")

by_platform_this = periodic[periodic["date"] == this_row["date"]].copy()
summary_md = _build_summary_text(this_label, this_row, last_row, by_platform_this)

st.markdown(f'<div class="soft-card">{summary_md}</div>', unsafe_allow_html=True)

# ----------------- 跨平台对比柱状图 -----------------

section("跨平台对比", icon="📊", color="amber", hint="按周期聚合")

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
if period_code == "M":
    period_str = periodic["date"].dt.strftime("%Y-%m")
else:
    period_str = (
        periodic["date"].dt.year.astype(str)
        + "-Q"
        + (((periodic["date"].dt.month - 1) // 3) + 1).astype(str)
    )
bar_df = periodic.assign(
    平台=periodic["platform"].map(PLATFORM_LABELS).fillna(periodic["platform"]),
    周期=period_str,
)
fig_bar = px.bar(
    bar_df,
    x="周期",
    y=metric_choice,
    color="平台",
    barmode="group",
    labels={metric_choice: "数值"},
)
apply_plotly_theme(fig_bar)
fig_bar.update_layout(height=420)
st.plotly_chart(fig_bar, width="stretch")

# ----------------- 粉丝增长曲线 -----------------

section("粉丝增长曲线", icon="📈", color="emerald", hint="按日 · 按平台分色")

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
fig_line.update_traces(line=dict(width=2.4))
apply_plotly_theme(fig_line)
fig_line.update_layout(height=420)
st.plotly_chart(fig_line, width="stretch")

st.caption(
    f"聚合粒度：{period_choice}；本期排除未结束周期：{'是' if exclude_partial else '否'}；"
    f"原始数据共 {len(df):,} 行（{df['date'].min().date()} → {df['date'].max().date()}）"
)

# ----------------- 报告导出 -----------------

section(
    "导出报告",
    icon="📥",
    color="violet",
    hint="CSV 表格 + Markdown 摘要",
)

st.caption("提供 PDF（适合直接汇报）、CSV（适合 Excel 二次分析）、Markdown（适合粘到飞书/Notion）三种格式。")

# CSV：周期 × 平台聚合（含衍生字段），适合 Excel
export_df = periodic.assign(
    平台=periodic["platform"].map(PLATFORM_LABELS).fillna(periodic["platform"]),
).rename(
    columns={
        "date": "周期截止日",
        "impressions": "曝光",
        "likes": "点赞",
        "comments": "评论",
        "shares": "转发",
        "saves": "收藏",
        "follower_growth": "粉丝净增",
        "followers": "期末粉丝",
        "interactions": "总互动",
        "engagement_rate": "互动率(%)",
    }
)[
    [
        "周期截止日",
        "平台",
        "曝光",
        "总互动",
        "点赞",
        "评论",
        "转发",
        "收藏",
        "粉丝净增",
        "期末粉丝",
        "互动率(%)",
    ]
]
csv_bytes = ("﻿" + export_df.to_csv(index=False)).encode("utf-8")  # BOM → Excel 正确识别中文

md_lines = [
    f"# 海外社媒数据面板 — {this_label} {period_choice}汇报",
    "",
    _build_summary_text(this_label, this_row, last_row, by_platform_this),
    "",
    "## 各平台数据",
    "",
    "| 平台 | 曝光 | 总互动 | 粉丝净增 | 期末粉丝 | 互动率 |",
    "|---|---:|---:|---:|---:|---:|",
]
for _, row in by_platform_this.iterrows():
    md_lines.append(
        f"| {PLATFORM_LABELS.get(row['platform'], row['platform'])} "
        f"| {row['impressions']:,.0f} "
        f"| {row['interactions']:,.0f} "
        f"| {row['follower_growth']:+,.0f} "
        f"| {row['followers']:,.0f} "
        f"| {row['engagement_rate']:.2f}% |"
    )
md_lines.extend(
    [
        "",
        f"_数据时段：{df['date'].min().date()} → {df['date'].max().date()}；"
        f"聚合粒度：{period_choice}；排除未结束周期：{'是' if exclude_partial else '否'}_",
    ]
)
md_bytes = "\n".join(md_lines).encode("utf-8")

if period_code == "M":
    period_slug = this_row["date"].strftime("%Y%m")
else:
    period_slug = f"{this_row['date'].year}Q{((this_row['date'].month - 1) // 3) + 1}"

# PDF：开箱即用的汇报成品（复用上面已算好的 KPI / 摘要 / 各平台数据）
def _fmt_int_safe(v) -> str:
    return "—" if pd.isna(v) else f"{v:,.0f}"


def _fmt_growth_safe(v) -> str:
    return "—" if pd.isna(v) else f"{v:+,.0f}"


def _fmt_pct_safe(v) -> str:
    return "—" if pd.isna(v) else f"{v:.2f}%"


_pdf_kpi = [
    ("总曝光", _format_int(this_row["impressions"]),
     f"{_format_pct(_impr_delta)} 环比" if _impr_delta is not None else None),
    ("总互动", _format_int(this_row["interactions"]),
     f"{_format_pct(_inter_delta)} 环比" if _inter_delta is not None else None),
    ("净增粉丝", _format_int(this_row["follower_growth"]),
     f"{_format_pct(_grow_delta)} 环比" if _grow_delta is not None else None),
    ("平均互动率", f"{this_row['engagement_rate']:.2f}%", None),
]
_pdf_platform_rows = [
    {
        "平台": PLATFORM_LABELS.get(r["platform"], r["platform"]),
        "曝光": _fmt_int_safe(r["impressions"]),
        "总互动": _fmt_int_safe(r["interactions"]),
        "粉丝净增": _fmt_growth_safe(r["follower_growth"]),
        "期末粉丝": _fmt_int_safe(r["followers"]),
        "互动率": _fmt_pct_safe(r["engagement_rate"]),
    }
    for _, r in by_platform_this.iterrows()
]
try:
    pdf_bytes = build_period_report_pdf(
        title=f"{this_label} {period_choice}汇报",
        date_range=f"{df['date'].min().date()} → {df['date'].max().date()}",
        kpi=_pdf_kpi,
        summary_lines=summary_md.split("\n"),
        platform_rows=_pdf_platform_rows,
    )
except Exception as exc:  # noqa: BLE001 - PDF 生成失败不应连累 CSV/MD 导出
    pdf_bytes = None
    st.warning(f"PDF 生成失败，可改用 CSV / Markdown：{exc}")

col_pdf, col_csv, col_md = st.columns(3)
col_pdf.download_button(
    "⬇️ 下载 PDF（汇报成品）",
    data=pdf_bytes if pdf_bytes is not None else b"",
    file_name=f"social_report_{period_slug}.pdf",
    mime="application/pdf",
    width="stretch",
    disabled=pdf_bytes is None,
)
col_csv.download_button(
    "⬇️ 下载 CSV（周期 × 平台聚合）",
    data=csv_bytes,
    file_name=f"social_report_{period_slug}.csv",
    mime="text/csv",
    width="stretch",
)
col_md.download_button(
    "⬇️ 下载 Markdown 摘要",
    data=md_bytes,
    file_name=f"social_report_{period_slug}.md",
    mime="text/markdown",
    width="stretch",
)

# 通用 CSV / Excel 导出：基于聚合后的 periodic DataFrame
if not periodic.empty:
    _today = datetime.now().strftime("%Y%m%d")
    _csv_bytes_p = periodic.to_csv(index=False).encode("utf-8-sig")
    _xlsx_buf_p = io.BytesIO()
    with pd.ExcelWriter(_xlsx_buf_p, engine="openpyxl") as _writer_p:
        periodic.to_excel(_writer_p, index=False)
    _xlsx_bytes_p = _xlsx_buf_p.getvalue()

    c1, c2 = st.columns(2)
    c1.download_button(
        "⬇️ 下载 CSV（周期聚合原始字段）",
        data=_csv_bytes_p,
        file_name=f"汇报视图_{_today}.csv",
        mime="text/csv",
        width="stretch",
    )
    c2.download_button(
        "⬇️ 下载 Excel（周期聚合原始字段）",
        data=_xlsx_bytes_p,
        file_name=f"汇报视图_{_today}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
