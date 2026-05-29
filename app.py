"""海外社媒数据面板 — 首页（编辑式 briefing 视觉方案）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from utils.data_sources import get_active_dataframe
from utils.ui import inject_page_styles

st.set_page_config(
    page_title="海外社媒 Briefing",
    page_icon="●",
    layout="wide",
    initial_sidebar_state="auto",
)

# 注入全局编辑式视觉（Fraunces / Noto Serif SC / JetBrains Mono + 纸面调色）
inject_page_styles()

# 首页专属 layout（不重复字体与配色 token，仅追加 home 专属类）
st.markdown(
    """
    <style>
    /* ---------- masthead 报头 ---------- */
    .home-masthead {
        display: grid;
        grid-template-columns: auto 1fr auto;
        align-items: end;
        gap: 2rem;
        padding-bottom: 1rem;
        border-bottom: 3px double var(--ink);
        position: relative;
    }
    .home-masthead .brand {
        display: flex;
        align-items: baseline;
        gap: 0.9rem;
    }
    .home-masthead .brand .glyph {
        width: 44px; height: 44px;
        border: 1.5px solid var(--ink);
        border-radius: 50%;
        display: inline-grid;
        place-items: center;
        font-family: "Fraunces", serif;
        font-variation-settings: "opsz" 144, "wght" 600, "SOFT" 0, "WONK" 1;
        font-style: italic;
        font-size: 22px;
        background: var(--paper-deep);
        color: var(--terracotta);
        position: relative;
        top: 4px;
    }
    .home-masthead .brand .glyph::after {
        content: "";
        position: absolute;
        width: 44px; height: 44px;
        border-radius: 50%;
        border: 1px solid var(--terracotta);
        transform: translate(3px, 3px);
        z-index: -1;
    }
    .home-masthead .brand h1 {
        font-family: "Noto Serif SC", "Fraunces", serif;
        font-weight: 900;
        font-size: 2rem;
        line-height: 1;
        letter-spacing: -0.015em;
        margin: 0;
        color: var(--ink);
    }
    .home-masthead .brand h1 em {
        font-family: "Fraunces", serif;
        font-style: italic;
        font-weight: 400;
        font-variation-settings: "opsz" 144, "SOFT" 100, "WONK" 1;
        color: var(--terracotta);
        margin-left: 0.35rem;
    }

    .home-masthead .issue-meta {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.25rem;
        font-family: var(--mono);
        font-size: 0.66rem;
        letter-spacing: 0.32em;
        text-transform: uppercase;
        color: var(--ink-soft);
    }
    .home-masthead .issue-meta .rule {
        width: 38px; height: 1px;
        background: var(--ink);
    }
    .home-masthead .issue-meta .label { font-size: 0.6rem; letter-spacing: 0.4em; color: var(--warm-gray); }
    .home-masthead .issue-meta .value { font-size: 0.8rem; letter-spacing: 0.08em; color: var(--ink); }

    .home-masthead .source-badge {
        justify-self: end;
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.55rem 0.85rem;
        border: 1px solid var(--ink);
        background: var(--paper-deep);
        font-family: var(--mono);
        font-size: 0.7rem;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: var(--ink);
    }
    .home-masthead .source-badge::before {
        content: "●";
        color: var(--forest);
        font-size: 0.55rem;
    }

    /* ---------- 报头下方栏标 ---------- */
    .home-stripe {
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        align-items: center;
        margin-top: 0.5rem;
        padding-bottom: 1.4rem;
        border-bottom: 1px solid var(--rule-strong);
        font-family: var(--mono);
        font-size: 0.66rem;
        letter-spacing: 0.34em;
        text-transform: uppercase;
        color: var(--warm-gray);
    }
    .home-stripe .center {
        color: var(--terracotta);
        letter-spacing: 0.45em;
    }
    .home-stripe .right { text-align: right; }

    /* ---------- lead 主标 + standfirst ---------- */
    .home-lead {
        display: grid;
        grid-template-columns: 1.18fr 1fr;
        gap: 3rem;
        padding: 2.4rem 0 2rem;
        border-bottom: 1px solid var(--rule);
    }
    .home-lead h2 {
        font-family: "Noto Serif SC", "Fraunces", serif;
        font-weight: 900;
        font-size: clamp(2.4rem, 4.6vw, 4rem);
        line-height: 1.04;
        margin: 0;
        letter-spacing: -0.02em;
        color: var(--ink);
        text-wrap: balance;
    }
    .home-lead h2 em {
        font-family: "Fraunces", serif;
        font-style: italic;
        font-weight: 400;
        font-variation-settings: "opsz" 144, "SOFT" 100, "WONK" 1;
        color: var(--terracotta);
    }
    .home-lead h2 .small-mark {
        display: inline-block;
        transform: translateY(-1.2rem);
        font-family: "Fraunces", serif;
        font-style: italic;
        font-size: 0.9rem;
        color: var(--warm-gray);
        margin-left: 0.2rem;
        font-variation-settings: "opsz" 14;
    }
    .home-lead .standfirst {
        font-family: var(--serif);
        font-variation-settings: "opsz" 14, "SOFT" 30;
        font-size: 1rem;
        line-height: 1.6;
        color: var(--ink-soft);
        align-self: end;
        max-width: 44ch;
    }
    .home-lead .standfirst .drop {
        font-family: "Fraunces", serif;
        font-style: italic;
        font-size: 3.5rem;
        line-height: 0.85;
        float: left;
        margin: 0.4rem 0.55rem 0 0;
        color: var(--terracotta);
        font-variation-settings: "opsz" 144, "SOFT" 100, "WONK" 1;
    }
    .home-lead .standfirst b {
        font-family: var(--mono);
        font-weight: 500;
        color: var(--ink);
        font-size: 0.9rem;
        padding: 0 0.15rem;
    }

    /* ---------- 数据状态条（编辑式 KPI grid） ---------- */
    .home-status {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 0;
        margin-top: 2rem;
        border-top: 1px solid var(--ink);
        border-bottom: 1px solid var(--ink);
    }
    .home-status .cell {
        padding: 1.05rem 0.9rem 1.1rem;
        border-right: 1px dashed var(--rule-strong);
        display: flex;
        flex-direction: column;
        gap: 0.3rem;
        position: relative;
    }
    .home-status .cell:last-child { border-right: 0; }
    .home-status .cell::after {
        content: attr(data-stamp);
        position: absolute;
        top: 0.5rem; right: 0.7rem;
        font-family: "Fraunces", serif;
        font-style: italic;
        font-variation-settings: "opsz" 144, "SOFT" 100, "WONK" 1;
        font-size: 0.78rem;
        color: var(--terracotta);
        opacity: 0.5;
        transform: rotate(-6deg);
    }
    .home-status .cell .label {
        font-family: var(--mono);
        font-size: 0.6rem;
        letter-spacing: 0.28em;
        text-transform: uppercase;
        color: var(--warm-gray);
    }
    .home-status .cell .value {
        font-family: var(--mono);
        font-weight: 500;
        font-size: 1.6rem;
        line-height: 1;
        letter-spacing: -0.02em;
        color: var(--ink);
        font-feature-settings: "tnum" 1;
    }
    .home-status .cell .value .unit {
        font-family: "Fraunces", serif;
        font-style: italic;
        font-size: 0.8rem;
        color: var(--warm-gray);
        margin-left: 0.2rem;
        font-variation-settings: "opsz" 14, "SOFT" 60;
    }
    .home-status .cell .note {
        font-family: "Fraunces", serif;
        font-style: italic;
        font-size: 0.78rem;
        color: var(--ink-soft);
        margin-top: auto;
        padding-top: 0.4rem;
        font-variation-settings: "opsz" 14;
    }

    /* ---------- 工作流栏目 ---------- */
    .home-section {
        margin-top: 3.5rem;
        padding-top: 1.4rem;
        border-top: 3px double var(--ink);
    }
    .home-section .kicker {
        display: inline-block;
        font-family: var(--mono);
        font-size: 0.66rem;
        letter-spacing: 0.34em;
        text-transform: uppercase;
        color: var(--terracotta);
        margin-bottom: 0.5rem;
    }
    .home-section h2 {
        margin: 0 0 0.6rem;
        font-family: "Noto Serif SC", "Fraunces", serif;
        font-weight: 900;
        font-size: clamp(1.7rem, 2.8vw, 2.4rem);
        letter-spacing: -0.015em;
        color: var(--ink);
    }
    .home-section h2 em {
        font-family: "Fraunces", serif;
        font-style: italic;
        color: var(--terracotta);
        font-weight: 400;
        font-variation-settings: "opsz" 144, "SOFT" 100, "WONK" 1;
    }
    .home-section .lede {
        max-width: 64ch;
        margin: 0 0 1.4rem;
        font-family: var(--serif);
        font-variation-settings: "opsz" 14, "SOFT" 30;
        color: var(--ink-soft);
        line-height: 1.65;
    }

    .workflow-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 0;
        margin-top: 1.2rem;
        border-top: 1px solid var(--ink);
        border-bottom: 1px solid var(--ink);
    }
    .workflow-cell {
        padding: 1.4rem 1.2rem;
        border-right: 1px dashed var(--rule-strong);
        position: relative;
    }
    .workflow-cell:last-child { border-right: 0; }
    .workflow-cell .step {
        font-family: "Fraunces", serif;
        font-style: italic;
        font-variation-settings: "opsz" 144, "SOFT" 100, "WONK" 1;
        font-size: 1.4rem;
        color: var(--terracotta);
        margin-bottom: 0.5rem;
        display: block;
    }
    .workflow-cell h3 {
        margin: 0 0 0.5rem;
        font-family: "Noto Serif SC", "Fraunces", serif;
        font-weight: 600;
        font-size: 1.05rem;
        line-height: 1.3;
        color: var(--ink);
    }
    .workflow-cell p {
        margin: 0;
        font-family: var(--serif);
        font-variation-settings: "opsz" 14, "SOFT" 30;
        font-size: 0.9rem;
        line-height: 1.6;
        color: var(--ink-soft);
    }

    /* ---------- 两视图 panel ---------- */
    .views-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 1.4rem;
        margin-top: 1.6rem;
    }
    .view-panel {
        padding: 1.6rem 1.6rem 1.4rem;
        background: var(--paper-deep);
        border: 1px solid var(--ink);
        position: relative;
        display: flex;
        flex-direction: column;
    }
    .view-panel::before {
        content: "";
        position: absolute;
        inset: 6px;
        border: 1px solid var(--rule-strong);
        pointer-events: none;
    }
    .view-panel .tag {
        font-family: "Fraunces", serif;
        font-style: italic;
        font-variation-settings: "opsz" 144, "SOFT" 100, "WONK" 1;
        font-size: 1rem;
        color: var(--terracotta);
        margin-bottom: 0.4rem;
    }
    .view-panel h3 {
        margin: 0 0 0.6rem;
        font-family: "Noto Serif SC", "Fraunces", serif;
        font-weight: 900;
        font-size: 1.55rem;
        letter-spacing: -0.01em;
        color: var(--ink);
    }
    .view-panel p {
        margin: 0;
        font-family: var(--serif);
        font-variation-settings: "opsz" 14, "SOFT" 30;
        color: var(--ink-soft);
        line-height: 1.6;
        font-size: 0.94rem;
    }
    .view-panel .meta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        margin: 1rem 0 1.2rem;
    }
    .view-panel .meta span {
        padding: 0.25rem 0.55rem;
        border: 1px solid var(--rule-strong);
        background: var(--paper);
        font-family: var(--mono);
        font-size: 0.62rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--ink-soft);
    }
    .view-panel a.cta {
        display: inline-block;
        align-self: flex-start;
        margin-top: auto;
        padding: 0.55rem 0.95rem;
        border: 1px solid var(--ink);
        background: var(--ink);
        color: var(--paper) !important;
        text-decoration: none;
        font-family: var(--mono);
        font-size: 0.74rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        transition: transform 160ms cubic-bezier(.16,1,.3,1), box-shadow 160ms ease;
    }
    .view-panel a.cta.ghost {
        background: var(--paper);
        color: var(--ink) !important;
    }
    .view-panel a.cta:hover {
        transform: translate(-2px, -2px);
        box-shadow: 3px 3px 0 var(--ink);
    }

    /* ---------- 末段 CTA ---------- */
    .home-cta {
        margin-top: 3rem;
        padding: 1.8rem 0 0;
        border-top: 1px solid var(--rule-strong);
    }
    .home-cta-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.6rem;
        margin-top: 1rem;
    }
    .home-cta-actions a {
        padding: 0.6rem 1rem;
        border: 1px solid var(--ink);
        text-decoration: none;
        font-family: var(--mono);
        font-size: 0.76rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        transition: transform 160ms cubic-bezier(.16,1,.3,1), box-shadow 160ms ease;
    }
    .home-cta-actions a.primary { background: var(--ink); color: var(--paper) !important; }
    .home-cta-actions a.ghost   { background: var(--paper-deep); color: var(--ink) !important; }
    .home-cta-actions a:hover { transform: translate(-2px, -2px); box-shadow: 3px 3px 0 var(--ink); }

    /* ---------- colophon 页脚 ---------- */
    .colophon {
        margin-top: 4rem;
        padding-top: 1.4rem;
        border-top: 1px solid var(--rule-strong);
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        align-items: baseline;
        font-family: var(--mono);
        font-size: 0.65rem;
        letter-spacing: 0.24em;
        text-transform: uppercase;
        color: var(--warm-gray);
    }
    .colophon em {
        font-family: "Fraunces", serif;
        font-style: italic;
        font-variation-settings: "opsz" 14, "SOFT" 60;
        text-transform: none;
        letter-spacing: 0;
        font-size: 0.88rem;
        color: var(--ink-soft);
    }

    /* ---------- 入场动效 ---------- */
    @keyframes settle {
        from { opacity: 0; transform: translateY(8px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    .home-masthead, .home-lead, .home-status, .home-section, .home-cta, .colophon {
        animation: settle 0.9s cubic-bezier(.2,.7,.2,1) both;
    }
    .home-lead    { animation-delay: 0.08s; }
    .home-status  { animation-delay: 0.18s; }
    .home-section { animation-delay: 0.28s; }
    .home-cta     { animation-delay: 0.40s; }
    .colophon     { animation-delay: 0.52s; }

    @media (max-width: 980px) {
        .home-masthead { grid-template-columns: 1fr; }
        .home-masthead .issue-meta { align-items: flex-start; }
        .home-masthead .source-badge { justify-self: start; }
        .home-lead { grid-template-columns: 1fr; gap: 1.5rem; }
        .home-status { grid-template-columns: 1fr 1fr 1fr; }
        .home-status .cell:nth-child(3n) { border-right: 0; }
        .workflow-grid { grid-template-columns: 1fr 1fr; }
        .workflow-cell:nth-child(2n) { border-right: 0; }
        .views-grid { grid-template-columns: 1fr; }
        .colophon { flex-direction: column; align-items: flex-start; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _fmt_int(value: int | float) -> str:
    return f"{int(value):,}"


# ----------------- 数据加载（沉默掉 data_loader 的目录警告） -----------------
samples_dir = Path("data/samples")
data_dir = Path("data")
sample_csvs = sorted(samples_dir.glob("*.csv")) if samples_dir.exists() else []
real_csvs = sorted(p for p in data_dir.glob("*.csv") if p.is_file())

_orig_warning = st.warning
st.warning = lambda *a, **k: None
try:
    df, source_label = get_active_dataframe()
except Exception:
    df = pd.DataFrame()
    source_label = "未连接"
finally:
    st.warning = _orig_warning

if not df.empty:
    total_rows = len(df)
    platform_count = (
        int(df["platform"].nunique()) if "platform" in df.columns else 0
    )
    date_span_days = (
        int((df["date"].max() - df["date"].min()).days) + 1
        if "date" in df.columns and not df["date"].isna().all()
        else 0
    )
    total_followers = (
        int(df.groupby("platform")["followers"].last().sum())
        if "followers" in df.columns
        else 0
    )
else:
    total_rows = 0
    platform_count = 0
    date_span_days = 0
    total_followers = 0

source_dot_label = source_label if source_label and source_label != "未连接" else "等待数据接入"
today = datetime.now()
weekday_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][today.weekday()]

# ============================ MASTHEAD ============================
st.markdown(
    f"""
    <div class="home-masthead">
      <div class="brand">
        <span class="glyph">M</span>
        <h1>海外社媒 <em>Briefing</em></h1>
      </div>
      <div class="issue-meta">
        <span class="label">Vol. 02 · No. 137</span>
        <span class="rule"></span>
        <span class="value">{today.strftime("%Y · %m · %d")}  {weekday_en}</span>
        <span class="label">日常运营 · 月度汇报</span>
      </div>
      <div class="source-badge">{source_dot_label}</div>
    </div>
    <div class="home-stripe">
      <span class="left">Section / Operations</span>
      <span class="center">— Six Platforms, One Pulse —</span>
      <span class="right">Compiled by Ops Desk</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================ LEAD ============================
st.markdown(
    """
    <div class="home-lead">
      <h2>
        把六个平台的<em>风向</em>，<br>
        收束成一张可行动的运营台
        <span class="small-mark">↑ daily</span>
      </h2>
      <div class="standfirst">
        <span class="drop">面</span>向运营与管理汇报的统一面板。接入
        <b>Instagram · TikTok · YouTube · X · Facebook · LinkedIn</b>
        六个平台的导出与 API 数据，自动清洗字段、计算指标、沉淀周期摘要——
        让团队少拼表，多判断。
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================ STATUS（6 cell 编辑式状态条） ============================
status_value_platforms = str(platform_count) if platform_count else "—"
status_value_rows = _fmt_int(total_rows) if total_rows else "—"
status_value_days = str(date_span_days) if date_span_days else "—"
status_value_followers = _fmt_int(total_followers) if total_followers else "—"

date_range_note = (
    f"{df['date'].min().date()} → {df['date'].max().date()}"
    if not df.empty and "date" in df.columns and not df["date"].isna().all()
    else "等待接入"
)

st.markdown(
    f"""
    <div class="home-status">
      <div class="cell" data-stamp="N°01">
        <span class="label">Source</span>
        <span class="value">{source_dot_label}</span>
        <span class="note">数据源</span>
      </div>
      <div class="cell" data-stamp="N°02">
        <span class="label">Platforms</span>
        <span class="value">{status_value_platforms}<span class="unit">/ 6</span></span>
        <span class="note">已接入平台</span>
      </div>
      <div class="cell" data-stamp="N°03">
        <span class="label">Records</span>
        <span class="value">{status_value_rows}<span class="unit">行</span></span>
        <span class="note">数据记录</span>
      </div>
      <div class="cell" data-stamp="N°04">
        <span class="label">Span</span>
        <span class="value">{status_value_days}<span class="unit">天</span></span>
        <span class="note">{date_range_note}</span>
      </div>
      <div class="cell" data-stamp="N°05">
        <span class="label">Followers</span>
        <span class="value">{status_value_followers}</span>
        <span class="note">最新总粉丝</span>
      </div>
      <div class="cell" data-stamp="N°06">
        <span class="label">CSV</span>
        <span class="value">{len(sample_csvs)}<span class="unit">+ {len(real_csvs)}</span></span>
        <span class="note">示例 · 运营</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================ WORKFLOW ============================
st.markdown(
    """
    <div class="home-section">
      <span class="kicker">Workflow / 工作流</span>
      <h2>从数据进入到汇报产出，<em>保持同一套口径</em></h2>
      <p class="lede">
        面板不把每个功能拆成孤立卡片，而是围绕运营团队每天会重复执行的链路组织：
        接入、校验、分析、汇报。新人能跟着流程走，老手也能快速扫描异常。
      </p>
      <div class="workflow-grid">
        <div class="workflow-cell">
          <span class="step">i.  Intake</span>
          <h3>CSV、API、Sheets 汇入</h3>
          <p>支持平台原生导出、Metricool 统一导出、手动录入和 API 拉取，上传后优先进入当前 session。</p>
        </div>
        <div class="workflow-cell">
          <span class="step">ii.  Normalize</span>
          <h3>字段识别与人工映射</h3>
          <p>已知格式自动映射；未知表头进入手动映射区，避免因为列名变化打断运营节奏。</p>
        </div>
        <div class="workflow-cell">
          <span class="step">iii.  Operate</span>
          <h3>日常 KPI 与趋势</h3>
          <p>运营视图聚焦平台 KPI、互动率趋势、表现排行，配合侧边栏筛选完成日常复盘。</p>
        </div>
        <div class="workflow-cell">
          <span class="step">iv.  Report</span>
          <h3>周期摘要与导出</h3>
          <p>汇报视图按月度或季度聚合，自动生成可复制的中文摘要，并提供 CSV 与 Markdown 下载。</p>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================ TEAM VIEWS ============================
st.markdown(
    """
    <div class="home-section">
      <span class="kicker">Team Views / 视图</span>
      <h2>同一份数据，<em>两种工作节奏</em></h2>
      <p class="lede">运营团队需要细颗粒度与可筛选性；管理层需要周期结论与可导出的材料。两个视图共用数据源，但密度与判断路径不同。</p>
      <div class="views-grid">
        <div class="view-panel">
          <span class="tag">A.  Daily</span>
          <h3>运营视图</h3>
          <p>面向每日使用：平台筛选、日期筛选、KPI、互动率趋势、平台表现排行集中在一个工作台中。</p>
          <div class="meta">
            <span>平台多选</span><span>日期范围</span><span>互动率</span><span>排行榜</span>
          </div>
          <a class="cta" href="/运营视图" target="_self">打开运营视图 →</a>
        </div>
        <div class="view-panel">
          <span class="tag">B.  Periodic</span>
          <h3>汇报视图</h3>
          <p>面向周期复盘：月度、季度聚合，自动生成摘要，图表与下载内容都服务于汇报材料。</p>
          <div class="meta">
            <span>月度</span><span>季度</span><span>摘要</span><span>CSV · Markdown</span>
          </div>
          <a class="cta ghost" href="/汇报视图" target="_self">查看汇报视图 →</a>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================ NEXT STEP CTA ============================
if df.empty:
    cta_title = "当前还没有数据，先<em>接入</em>一份 CSV"
    cta_desc = "上传任意平台导出的 CSV，或运行 <b>python generate_sample_data.py</b> 查看示例数据。"
    cta_href = "/数据导入"
    cta_label = "去接入数据"
else:
    cta_title = "数据已经就位，<em>开始分析</em>"
    cta_desc = (
        f"当前数据源：<b>{source_label}</b>，共 <b>{_fmt_int(total_rows)}</b> 行、"
        f"<b>{platform_count}</b> 个平台、<b>{date_span_days}</b> 天。"
    )
    cta_href = "/运营视图"
    cta_label = "查看运营视图"

st.markdown(
    f"""
    <div class="home-cta home-section">
      <span class="kicker">Next Step / 下一步</span>
      <h2>{cta_title}</h2>
      <p class="lede">{cta_desc}</p>
      <div class="home-cta-actions">
        <a class="primary" href="{cta_href}" target="_self">{cta_label} →</a>
        <a class="ghost"   href="/数据导入" target="_self">管理数据源</a>
      </div>
    </div>

    <div class="colophon">
      <span>Set in Fraunces · Noto Serif SC · JetBrains Mono</span>
      <em>Compiled at {today.strftime("%Y-%m-%d %H:%M")} · 示例 CSV {len(sample_csvs)} · 运营 CSV {len(real_csvs)} · bash init.sh</em>
      <span>P. 01 / 03</span>
    </div>
    """,
    unsafe_allow_html=True,
)
