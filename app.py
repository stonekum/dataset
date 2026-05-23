"""Home page for the overseas social media data dashboard."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from utils.data_sources import get_active_dataframe

st.set_page_config(
    page_title="Pulse · 海外社媒数据面板",
    page_icon="P",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    :root {
        --canvas: #F7F8F6;
        --surface: #FFFFFF;
        --ink: #1F2933;
        --muted: #667085;
        --line: rgba(31, 41, 51, 0.10);
        --accent: #0F766E;
        --accent-dark: #115E59;
    }
    header[data-testid="stHeader"] { background: transparent; }
    .stApp { background: var(--canvas); }
    .block-container {
        max-width: 1280px;
        padding-top: 1.35rem;
        padding-bottom: 3.5rem;
    }
    html, body, [class*="css"] {
        font-family: "Geist", "SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: var(--ink);
    }
    .topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid var(--line);
    }
    .brand {
        display: inline-flex;
        align-items: center;
        gap: 0.65rem;
        color: var(--ink);
        font-size: 1rem;
        font-weight: 780;
        letter-spacing: 0;
    }
    .brand-mark {
        width: 2rem;
        height: 2rem;
        border-radius: 8px;
        background:
            linear-gradient(135deg, rgba(255,255,255,0.42), rgba(255,255,255,0) 42%),
            var(--ink);
        box-shadow: inset 0 0 0 1px rgba(255,255,255,0.12);
    }
    .navlinks {
        display: flex;
        align-items: center;
        gap: 1.25rem;
        color: var(--muted);
        font-size: 0.9rem;
        font-weight: 600;
    }
    .navlinks a {
        color: inherit;
        text-decoration: none;
    }
    .navlinks a:hover { color: var(--ink); }
    .nav-cta {
        display: inline-flex;
        align-items: center;
        padding: 0.52rem 0.82rem;
        border-radius: 8px;
        background: var(--ink);
        color: #fff !important;
        text-decoration: none;
        font-size: 0.86rem;
        font-weight: 680;
        transition: transform 160ms cubic-bezier(.16,1,.3,1), background 160ms ease;
    }
    .nav-cta:hover {
        background: #344054;
        transform: translateY(-1px);
    }
    .hero {
        display: grid;
        grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.8fr);
        gap: 2.6rem;
        align-items: end;
        min-height: 62dvh;
        padding: 3.8rem 0 2.2rem;
        border-bottom: 1px solid var(--line);
    }
    .eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.85rem;
        color: var(--accent-dark);
        font-size: 0.74rem;
        font-weight: 780;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }
    .eyebrow::before,
    .section-label::before,
    .status-dot {
        content: "";
        width: 0.52rem;
        height: 0.52rem;
        border-radius: 999px;
        background: var(--accent);
        box-shadow: inset 0 0 0 1px rgba(255,255,255,0.35);
    }
    .hero h1 {
        max-width: 820px;
        margin: 0;
        color: var(--ink);
        font-size: clamp(2.55rem, 5vw, 4.8rem);
        line-height: 0.98;
        letter-spacing: 0;
        font-weight: 810;
    }
    .hero h1 span { color: var(--accent-dark); }
    .hero-copy {
        max-width: 680px;
        margin: 1.2rem 0 0;
        color: var(--muted);
        font-size: 1.05rem;
        line-height: 1.72;
    }
    .hero-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin-top: 1.7rem;
    }
    .btn-primary,
    .btn-ghost {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 2.75rem;
        padding: 0.72rem 1rem;
        border-radius: 8px;
        text-decoration: none;
        font-weight: 700;
        font-size: 0.94rem;
        transition: transform 160ms cubic-bezier(.16,1,.3,1), background 160ms ease, border-color 160ms ease;
    }
    .btn-primary {
        background: var(--ink);
        color: #fff !important;
    }
    .btn-ghost {
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.58);
        color: var(--ink) !important;
    }
    .btn-primary:hover,
    .btn-ghost:hover { transform: translateY(-1px); }
    .btn-primary:hover { background: #344054; }
    .btn-ghost:hover { border-color: rgba(15,118,110,0.45); }
    .signal-panel {
        border: 1px solid var(--line);
        border-radius: 8px;
        background: rgba(255,255,255,0.72);
        box-shadow: 0 24px 50px -38px rgba(31,41,51,0.34);
        overflow: hidden;
    }
    .signal-head {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 1rem 1.05rem;
        border-bottom: 1px solid var(--line);
    }
    .signal-title {
        font-size: 0.85rem;
        color: var(--ink);
        font-weight: 760;
    }
    .signal-source {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        color: var(--muted);
        font-size: 0.78rem;
        font-weight: 620;
        text-align: right;
    }
    .metric-list { padding: 0.2rem 1.05rem 0.4rem; }
    .metric-row {
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 1rem;
        padding: 0.95rem 0;
        border-bottom: 1px solid rgba(31,41,51,0.08);
    }
    .metric-row:last-child { border-bottom: 0; }
    .metric-label {
        color: var(--muted);
        font-size: 0.82rem;
        font-weight: 640;
    }
    .metric-value {
        color: var(--ink);
        font-size: 1.18rem;
        font-weight: 790;
        font-variant-numeric: tabular-nums;
    }
    .platform-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
        padding: 1rem 1.05rem 1.1rem;
        background: rgba(247,248,246,0.72);
        border-top: 1px solid var(--line);
    }
    .platform-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.38rem 0.55rem;
        border: 1px solid var(--line);
        border-radius: 999px;
        background: #fff;
        color: #344054;
        font-size: 0.78rem;
        font-weight: 660;
    }
    .platform-chip span {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.15rem;
        height: 1.15rem;
        border-radius: 50%;
        background: var(--canvas);
        color: var(--accent-dark);
        font-size: 0.62rem;
        font-weight: 800;
    }
    .section {
        padding: 2.4rem 0 0;
    }
    .section-label {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        color: var(--accent-dark);
        font-size: 0.72rem;
        font-weight: 780;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }
    .section h2 {
        max-width: 760px;
        margin: 0.65rem 0 0.7rem;
        color: var(--ink);
        font-size: clamp(1.75rem, 3vw, 2.7rem);
        line-height: 1.08;
        letter-spacing: 0;
        font-weight: 790;
    }
    .section p {
        max-width: 700px;
        margin: 0;
        color: var(--muted);
        line-height: 1.68;
    }
    .workflow-grid {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
        gap: 0;
        margin-top: 1.55rem;
        border-top: 1px solid var(--line);
        border-bottom: 1px solid var(--line);
    }
    .workflow-item {
        min-height: 12rem;
        padding: 1.35rem 1.25rem;
        border-right: 1px solid var(--line);
        border-bottom: 1px solid var(--line);
    }
    .workflow-item:nth-child(2n) { border-right: 0; }
    .workflow-item:nth-last-child(-n+2) { border-bottom: 0; }
    .workflow-kicker {
        color: var(--accent-dark);
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .workflow-item h3 {
        margin: 0.65rem 0 0.45rem;
        color: var(--ink);
        font-size: 1.08rem;
        font-weight: 760;
    }
    .workflow-item p {
        color: var(--muted);
        font-size: 0.92rem;
        line-height: 1.62;
    }
    .views-grid {
        display: grid;
        grid-template-columns: minmax(0, 1.35fr) minmax(260px, 0.65fr);
        gap: 1rem;
        margin-top: 1.5rem;
    }
    .view-panel {
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        min-height: 16rem;
        padding: 1.35rem;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: #fff;
    }
    .view-panel h3 {
        margin: 0;
        color: var(--ink);
        font-size: 1.35rem;
        font-weight: 780;
    }
    .view-panel p {
        margin-top: 0.75rem;
        max-width: 620px;
        font-size: 0.95rem;
    }
    .view-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-top: 1.2rem;
    }
    .view-meta span {
        padding: 0.28rem 0.52rem;
        border: 1px solid var(--line);
        border-radius: 999px;
        color: var(--muted);
        font-size: 0.76rem;
        font-weight: 650;
    }
    .view-panel .btn-primary,
    .view-panel .btn-ghost { margin-top: 1.25rem; align-self: flex-start; }
    .footer {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        margin-top: 3rem;
        padding-top: 1.2rem;
        border-top: 1px solid var(--line);
        color: var(--muted);
        font-size: 0.82rem;
    }
    code {
        border: 1px solid rgba(31,41,51,0.10);
        border-radius: 5px;
        background: rgba(255,255,255,0.75);
        padding: 0.08rem 0.32rem;
    }
    @media (max-width: 860px) {
        .navlinks { display: none; }
        .hero,
        .views-grid,
        .workflow-grid {
            grid-template-columns: 1fr;
        }
        .hero { min-height: auto; padding-top: 2.4rem; }
        .workflow-item,
        .workflow-item:nth-child(2n) {
            border-right: 0;
            border-bottom: 1px solid var(--line);
        }
        .workflow-item:last-child { border-bottom: 0; }
        .footer { flex-direction: column; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _fmt_int(value: int | float) -> str:
    return f"{int(value):,}"


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
    platform_count = df["platform"].nunique() if "platform" in df.columns else 0
    date_span_days = (
        int((df["date"].max() - df["date"].min()).days) + 1
        if "date" in df.columns and not df["date"].isna().all()
        else 0
    )
    total_followers = int(df.groupby("platform")["followers"].last().sum()) if "followers" in df.columns else 0
else:
    total_rows = 0
    platform_count = 0
    date_span_days = 0
    total_followers = 0

source_dot_label = source_label if source_label and source_label != "未连接" else "等待数据接入"

st.markdown(
    """
    <div class="topbar">
      <div class="brand">
        <span class="brand-mark"></span>
        <span>Pulse · 海外社媒数据面板</span>
      </div>
      <div class="navlinks">
        <a href="#workflow">工作流</a>
        <a href="#views">视图</a>
        <a href="#status">数据状态</a>
        <a class="nav-cta" href="/数据导入" target="_self">接入数据</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <section class="hero">
      <div>
        <div class="eyebrow">SOCIAL OPERATIONS CONTROL</div>
        <h1>把六个平台的社媒数据，收束成一个<span>可行动的运营台</span></h1>
        <p class="hero-copy">
          面向日常运营和管理汇报的统一面板。接入 Instagram、TikTok、YouTube、X、Facebook、LinkedIn，
          自动清洗字段、计算指标、沉淀周期摘要，让团队少拼表，多判断。
        </p>
        <div class="hero-actions">
          <a class="btn-primary" href="/运营视图" target="_self">进入运营视图</a>
          <a class="btn-ghost" href="/汇报视图" target="_self">查看汇报视图</a>
        </div>
      </div>
      <aside class="signal-panel" id="status">
        <div class="signal-head">
          <div class="signal-title">当前数据状态</div>
          <div class="signal-source"><span class="status-dot"></span>{source_dot_label}</div>
        </div>
        <div class="metric-list">
          <div class="metric-row"><div class="metric-label">已接入平台</div><div class="metric-value">{platform_count}</div></div>
          <div class="metric-row"><div class="metric-label">数据记录</div><div class="metric-value">{_fmt_int(total_rows)}</div></div>
          <div class="metric-row"><div class="metric-label">覆盖天数</div><div class="metric-value">{date_span_days}</div></div>
          <div class="metric-row"><div class="metric-label">最新总粉丝</div><div class="metric-value">{_fmt_int(total_followers)}</div></div>
        </div>
        <div class="platform-strip">
          <div class="platform-chip"><span>IG</span>Instagram</div>
          <div class="platform-chip"><span>TT</span>TikTok</div>
          <div class="platform-chip"><span>YT</span>YouTube</div>
          <div class="platform-chip"><span>X</span>X</div>
          <div class="platform-chip"><span>FB</span>Facebook</div>
          <div class="platform-chip"><span>IN</span>LinkedIn</div>
        </div>
      </aside>
    </section>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <section class="section" id="workflow">
      <div class="section-label">WORKFLOW</div>
      <h2>从数据进入到汇报产出，保持同一套口径</h2>
      <p>
        面板不把每个功能拆成孤立卡片，而是围绕运营团队每天会重复执行的链路组织：
        接入、校验、分析、汇报。这样新人能跟着流程走，老手也能快速扫描异常。
      </p>
      <div class="workflow-grid">
        <div class="workflow-item">
          <div class="workflow-kicker">01 Intake</div>
          <h3>CSV、API、Google Sheets 汇入</h3>
          <p>支持平台原生导出、Metricool 统一导出、手动录入和 API 拉取，上传后优先进入当前 session。</p>
        </div>
        <div class="workflow-item">
          <div class="workflow-kicker">02 Normalize</div>
          <h3>字段识别与人工映射</h3>
          <p>已知格式自动映射；未知表头进入手动映射区，避免因为列名变化打断运营节奏。</p>
        </div>
        <div class="workflow-item">
          <div class="workflow-kicker">03 Operate</div>
          <h3>日常 KPI 与趋势监控</h3>
          <p>运营视图聚焦平台 KPI、互动率趋势、表现排行，配合侧边栏筛选完成日常复盘。</p>
        </div>
        <div class="workflow-item">
          <div class="workflow-kicker">04 Report</div>
          <h3>周期摘要与导出</h3>
          <p>汇报视图按月度或季度聚合，生成可复制的中文摘要，并提供 CSV 与 Markdown 下载。</p>
        </div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <section class="section" id="views">
      <div class="section-label">TEAM VIEWS</div>
      <h2>同一份数据，两种工作节奏</h2>
      <p>运营团队需要细颗粒度与可筛选性，管理层需要周期结论与可导出的材料。两个视图共用数据源，但界面密度和判断路径不同。</p>
      <div class="views-grid">
        <div class="view-panel">
          <div>
            <h3>运营视图</h3>
            <p>面向每日使用：平台筛选、日期筛选、KPI、互动率趋势、平台表现排行集中在一个工作台中。</p>
            <div class="view-meta">
              <span>平台多选</span><span>日期范围</span><span>互动率趋势</span><span>排行榜</span>
            </div>
          </div>
          <a class="btn-primary" href="/运营视图" target="_self">打开运营视图</a>
        </div>
        <div class="view-panel">
          <div>
            <h3>汇报视图</h3>
            <p>面向周期复盘：月度、季度聚合，自动生成摘要，图表和下载内容都服务于汇报材料。</p>
            <div class="view-meta">
              <span>月度</span><span>季度</span><span>摘要</span>
            </div>
          </div>
          <a class="btn-ghost" href="/汇报视图" target="_self">查看汇报视图</a>
        </div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

if df.empty:
    cta_title = "当前还没有数据，先接入一份 CSV"
    cta_desc = "上传任意平台导出的 CSV，或运行 python generate_sample_data.py 查看示例数据。"
    cta_href = "/数据导入"
    cta_label = "去接入数据"
else:
    cta_title = "数据已经就位，可以开始分析"
    cta_desc = f"当前数据源：{source_label}，共 {_fmt_int(total_rows)} 行、{platform_count} 个平台、{date_span_days} 天。"
    cta_href = "/运营视图"
    cta_label = "查看运营视图"

st.markdown(
    f"""
    <section class="section">
      <div class="section-label">NEXT STEP</div>
      <h2>{cta_title}</h2>
      <p>{cta_desc}</p>
      <div class="hero-actions">
        <a class="btn-primary" href="{cta_href}" target="_self">{cta_label}</a>
        <a class="btn-ghost" href="/数据导入" target="_self">管理数据源</a>
      </div>
    </section>
    <div class="footer">
      <div>Pulse · 海外社媒数据面板</div>
      <div>示例 CSV {len(sample_csvs)} 个 · 运营 CSV {len(real_csvs)} 个 · 启动前运行 <code>bash init.sh</code></div>
    </div>
    """,
    unsafe_allow_html=True,
)
