"""首页 — 海外社媒数据面板 SaaS 风格落地页。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from utils.data_sources import get_active_dataframe

st.set_page_config(
    page_title="Pulse · 海外社媒数据面板",
    page_icon="🌏",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ----------------- 全局样式 -----------------

st.markdown(
    """
    <style>
    /* 隐藏 Streamlit 默认页眉，让落地页更干净 */
    header[data-testid="stHeader"] { background: transparent; }
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 3rem;
        max-width: 1180px;
    }

    /* 全局字体回退到 Inter / 系统字体 */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    /* 顶部导航条 */
    .pulse-nav {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.75rem 0 1.25rem 0;
        border-bottom: 1px solid rgba(15, 23, 42, 0.06);
        margin-bottom: 2.5rem;
    }
    .pulse-logo {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        font-weight: 700;
        font-size: 1.05rem;
        color: #0F172A;
        letter-spacing: -0.01em;
    }
    .pulse-logo-mark {
        width: 28px; height: 28px;
        border-radius: 8px;
        background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 50%, #EC4899 100%);
        box-shadow: 0 6px 18px -6px rgba(99, 102, 241, 0.55);
    }
    .pulse-nav-links {
        display: flex; gap: 1.8rem;
        font-size: 0.9rem; color: #475569;
    }
    .pulse-nav-links a { color: #475569; text-decoration: none; }
    .pulse-nav-links a:hover { color: #0F172A; }
    .pulse-nav-cta {
        font-size: 0.85rem;
        padding: 0.45rem 0.95rem;
        border-radius: 8px;
        background: #0F172A;
        color: #fff !important;
        text-decoration: none;
        font-weight: 500;
    }

    /* Hero */
    .hero-wrap {
        position: relative;
        padding: 3.5rem 0 2.5rem 0;
        text-align: center;
        overflow: hidden;
    }
    .hero-eyebrow {
        display: inline-flex; align-items: center; gap: 0.5rem;
        padding: 0.35rem 0.85rem;
        border-radius: 999px;
        background: rgba(99, 102, 241, 0.08);
        color: #4F46E5;
        font-size: 0.78rem; font-weight: 500;
        margin-bottom: 1.5rem;
        border: 1px solid rgba(99, 102, 241, 0.15);
    }
    .hero-eyebrow .dot {
        width: 6px; height: 6px; border-radius: 50%;
        background: #22C55E; box-shadow: 0 0 0 3px rgba(34,197,94,0.15);
    }
    .hero-title {
        font-size: clamp(2.4rem, 5vw, 3.6rem);
        font-weight: 700;
        letter-spacing: -0.035em;
        line-height: 1.05;
        color: #0F172A;
        margin: 0 0 1.1rem 0;
    }
    .hero-title .grad {
        background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 50%, #EC4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .hero-sub {
        font-size: 1.1rem;
        color: #475569;
        max-width: 640px;
        margin: 0 auto 2rem auto;
        line-height: 1.6;
    }
    .hero-cta-row {
        display: flex; justify-content: center; gap: 0.8rem;
        margin-bottom: 2.5rem;
    }
    .btn-primary, .btn-ghost {
        display: inline-flex; align-items: center; gap: 0.45rem;
        padding: 0.7rem 1.3rem;
        border-radius: 10px;
        font-weight: 500; font-size: 0.95rem;
        text-decoration: none;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .btn-primary {
        background: #0F172A; color: #fff !important;
        box-shadow: 0 10px 24px -10px rgba(15,23,42,0.4);
    }
    .btn-primary:hover { transform: translateY(-1px); }
    .btn-ghost {
        background: transparent; color: #0F172A !important;
        border: 1px solid rgba(15,23,42,0.12);
    }
    .btn-ghost:hover { background: rgba(15,23,42,0.04); }

    /* 平台 logo row */
    .platform-row {
        display: flex; justify-content: center; align-items: center;
        flex-wrap: wrap; gap: 2.2rem;
        padding: 1.5rem 0;
        opacity: 0.85;
    }
    .platform-pill {
        display: inline-flex; align-items: center; gap: 0.55rem;
        font-size: 0.92rem; font-weight: 500;
        color: #64748B;
    }
    .platform-pill .ico {
        width: 26px; height: 26px;
        border-radius: 7px;
        display: inline-flex; align-items: center; justify-content: center;
        background: #F1F5F9; color: #0F172A;
        font-size: 0.9rem;
    }

    /* Stats 条 */
    .stats-strip {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
        padding: 1.5rem 0 0.5rem 0;
        margin: 1rem 0 3rem 0;
        border-top: 1px solid rgba(15,23,42,0.06);
        border-bottom: 1px solid rgba(15,23,42,0.06);
    }
    .stat-cell { padding: 1rem 0.4rem; text-align: center; }
    .stat-val {
        font-size: 1.9rem; font-weight: 700;
        background: linear-gradient(135deg, #6366F1, #EC4899);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        letter-spacing: -0.02em;
    }
    .stat-label {
        font-size: 0.82rem; color: #64748B;
        margin-top: 0.25rem; letter-spacing: 0.02em;
    }

    /* Section heading */
    .section-eyebrow {
        text-align: center; font-size: 0.78rem; font-weight: 600;
        letter-spacing: 0.12em; text-transform: uppercase;
        color: #6366F1; margin-bottom: 0.6rem;
    }
    .section-title {
        text-align: center; font-size: 2rem; font-weight: 700;
        color: #0F172A; letter-spacing: -0.02em;
        margin-bottom: 0.6rem;
    }
    .section-sub {
        text-align: center; color: #64748B;
        max-width: 580px; margin: 0 auto 2.5rem auto;
        font-size: 1rem; line-height: 1.6;
    }

    /* Feature cards */
    .feature-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.1rem; }
    .feature-card {
        background: #fff;
        border: 1px solid rgba(15,23,42,0.07);
        border-radius: 16px;
        padding: 1.6rem 1.4rem;
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
        height: 100%;
    }
    .feature-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 18px 40px -22px rgba(15,23,42,0.18);
        border-color: rgba(99,102,241,0.25);
    }
    .feature-ico {
        width: 42px; height: 42px;
        border-radius: 11px;
        display: inline-flex; align-items: center; justify-content: center;
        font-size: 1.2rem;
        margin-bottom: 1rem;
    }
    .ico-indigo { background: rgba(99,102,241,0.12); color: #4F46E5; }
    .ico-rose   { background: rgba(236,72,153,0.12);  color: #DB2777; }
    .ico-amber  { background: rgba(245,158,11,0.12);  color: #B45309; }
    .ico-emerald{ background: rgba(16,185,129,0.12);  color: #047857; }
    .ico-sky    { background: rgba(14,165,233,0.12);  color: #0369A1; }
    .ico-violet { background: rgba(139,92,246,0.12);  color: #6D28D9; }

    .feature-title {
        font-size: 1.05rem; font-weight: 600; color: #0F172A;
        margin-bottom: 0.5rem;
    }
    .feature-desc { font-size: 0.92rem; color: #64748B; line-height: 1.55; }

    /* CTA 大卡片 */
    .cta-banner {
        margin-top: 3.5rem;
        background:
          radial-gradient(circle at 20% 20%, rgba(139,92,246,0.45), transparent 45%),
          radial-gradient(circle at 80% 80%, rgba(236,72,153,0.4), transparent 45%),
          linear-gradient(135deg, #1E1B4B 0%, #0F172A 100%);
        border-radius: 24px;
        padding: 3rem 2.5rem;
        color: #fff;
        text-align: center;
        position: relative;
        overflow: hidden;
    }
    .cta-banner h2 {
        font-size: 1.9rem; font-weight: 700;
        letter-spacing: -0.02em;
        margin: 0 0 0.75rem 0;
    }
    .cta-banner p {
        color: rgba(255,255,255,0.75);
        max-width: 520px; margin: 0 auto 1.75rem auto;
        line-height: 1.55;
    }
    .cta-banner .btn-primary {
        background: #fff; color: #0F172A !important;
    }
    .cta-banner .btn-ghost {
        color: #fff !important;
        border: 1px solid rgba(255,255,255,0.25);
    }

    /* Footer */
    .pulse-footer {
        margin-top: 4rem;
        padding: 1.75rem 0 0 0;
        border-top: 1px solid rgba(15,23,42,0.06);
        display: flex; justify-content: space-between; align-items: center;
        flex-wrap: wrap; gap: 1rem;
        font-size: 0.82rem; color: #94A3B8;
    }

    @media (max-width: 860px) {
        .feature-grid { grid-template-columns: 1fr; }
        .stats-strip { grid-template-columns: repeat(2, 1fr); }
        .pulse-nav-links { display: none; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------- 数据态势（用于 stats 条） -----------------

samples_dir = Path("data/samples")
data_dir = Path("data")
sample_csvs = sorted(samples_dir.glob("*.csv")) if samples_dir.exists() else []
real_csvs = sorted(p for p in data_dir.glob("*.csv") if p.is_file())

# 抑制数据加载过程中可能弹出的 st.warning（落地页用 stats strip 表达数据状态，
# 不希望页面顶部跳出黄色横条破坏视觉）
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

# ----------------- 顶部导航 -----------------

st.markdown(
    """
    <div class="pulse-nav">
      <div class="pulse-logo">
        <span class="pulse-logo-mark"></span>
        Pulse <span style="color:#94A3B8;font-weight:400;">· 海外社媒数据面板</span>
      </div>
      <div class="pulse-nav-links">
        <a href="#features">功能</a>
        <a href="#platforms">支持平台</a>
        <a href="#views">视图</a>
        <a href="#status">数据状态</a>
      </div>
      <a class="pulse-nav-cta" href="/数据导入" target="_self">开始接入 →</a>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------- Hero -----------------

source_dot_label = source_label if source_label and source_label != "未连接" else "等待数据接入"

st.markdown(
    f"""
    <div class="hero-wrap">
      <div class="hero-eyebrow">
        <span class="dot"></span>
        实时数据源：{source_dot_label}
      </div>
      <h1 class="hero-title">
        一个面板，看清 <span class="grad">六大海外社媒</span><br/>
        的运营全貌
      </h1>
      <p class="hero-sub">
        聚合 Instagram、TikTok、YouTube、X、Facebook、LinkedIn 的核心运营指标，
        为日常团队提供细颗粒度洞察，为管理层生成简洁汇报。无需切换平台，无需手工拼表。
      </p>
      <div class="hero-cta-row">
        <a class="btn-primary" href="/运营视图" target="_self">进入运营视图 →</a>
        <a class="btn-ghost" href="/汇报视图" target="_self">查看汇报视图</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------- 平台 pills -----------------

st.markdown(
    """
    <div id="platforms" class="platform-row">
      <div class="platform-pill"><span class="ico">📷</span> Instagram</div>
      <div class="platform-pill"><span class="ico">🎵</span> TikTok</div>
      <div class="platform-pill"><span class="ico">▶️</span> YouTube</div>
      <div class="platform-pill"><span class="ico">𝕏</span> X / Twitter</div>
      <div class="platform-pill"><span class="ico">👍</span> Facebook</div>
      <div class="platform-pill"><span class="ico">💼</span> LinkedIn</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------- Stats strip -----------------

st.markdown(
    f"""
    <div id="status" class="stats-strip">
      <div class="stat-cell">
        <div class="stat-val">{platform_count}</div>
        <div class="stat-label">已接入平台</div>
      </div>
      <div class="stat-cell">
        <div class="stat-val">{total_rows:,}</div>
        <div class="stat-label">数据记录条数</div>
      </div>
      <div class="stat-cell">
        <div class="stat-val">{date_span_days}</div>
        <div class="stat-label">数据时间跨度（天）</div>
      </div>
      <div class="stat-cell">
        <div class="stat-val">{total_followers:,}</div>
        <div class="stat-label">总粉丝数（最新）</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------- 特性卡片 -----------------

st.markdown(
    """
    <div id="features">
      <div class="section-eyebrow">CORE FEATURES</div>
      <div class="section-title">把碎片化的运营数据收拢成决策</div>
      <p class="section-sub">
        从原始 CSV / API 拉取，到清洗、计算、可视化，再到自动文字摘要 —
        覆盖每一位运营和管理者的关键工作流。
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="feature-grid">
      <div class="feature-card">
        <div class="feature-ico ico-indigo">📊</div>
        <div class="feature-title">运营视图</div>
        <div class="feature-desc">每日互动率、内容表现、平台对比 — 细颗粒度数据让运营动作有据可依。</div>
      </div>
      <div class="feature-card">
        <div class="feature-ico ico-rose">📈</div>
        <div class="feature-title">汇报视图</div>
        <div class="feature-desc">月度/季度聚合关键指标，自动生成中文文字摘要，5 分钟产出周期报告。</div>
      </div>
      <div class="feature-card">
        <div class="feature-ico ico-amber">⚡</div>
        <div class="feature-title">多源数据接入</div>
        <div class="feature-desc">支持 Metricool 统一导出、各平台原生 Analytics、Google Sheets 与官方 API。</div>
      </div>
      <div class="feature-card">
        <div class="feature-ico ico-emerald">🧮</div>
        <div class="feature-title">指标自动计算</div>
        <div class="feature-desc">互动率、粉丝增长率、周/月环比 — 标准化公式开箱即用，跨平台口径统一。</div>
      </div>
      <div class="feature-card">
        <div class="feature-ico ico-sky">🧭</div>
        <div class="feature-title">字段智能映射</div>
        <div class="feature-desc">未知表头自动识别来源，并提供可视化映射 UI，让历史导出也能即上即用。</div>
      </div>
      <div class="feature-card">
        <div class="feature-ico ico-violet">🔐</div>
        <div class="feature-title">本地优先</div>
        <div class="feature-desc">真实运营数据默认保留在本地或私有 Google Sheets，不上传任何第三方服务。</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------- 视图入口 -----------------

st.markdown(
    """
    <div id="views" style="margin-top:4rem;">
      <div class="section-eyebrow">FOR YOUR TEAM</div>
      <div class="section-title">为不同角色，准备好不同的画布</div>
      <p class="section-sub">两套视图共用同一份数据源，但用不同的颗粒度服务不同的人。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_a, col_b = st.columns(2, gap="medium")
with col_a:
    st.markdown(
        """
        <div class="feature-card" style="padding:1.8rem 1.6rem;">
          <div class="feature-ico ico-indigo">📊</div>
          <div class="feature-title" style="font-size:1.2rem;">运营视图</div>
          <div class="feature-desc" style="margin-bottom:1.2rem;">
            面向日常运营团队。提供平台 KPI 卡片、互动率趋势曲线、平台表现排行，
            支持平台与日期范围筛选。
          </div>
          <a class="btn-primary" href="/运营视图" target="_self" style="font-size:0.88rem;padding:0.55rem 1rem;">打开运营视图 →</a>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        """
        <div class="feature-card" style="padding:1.8rem 1.6rem;">
          <div class="feature-ico ico-rose">📈</div>
          <div class="feature-title" style="font-size:1.2rem;">汇报视图</div>
          <div class="feature-desc" style="margin-bottom:1.2rem;">
            面向管理层。按月/季度聚合，自动生成环比文字摘要、跨平台对比柱状图、
            粉丝增长曲线，可一键复制进 PPT。
          </div>
          <a class="btn-primary" href="/汇报视图" target="_self" style="font-size:0.88rem;padding:0.55rem 1rem;">打开汇报视图 →</a>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ----------------- CTA 横幅 -----------------

if df.empty:
    cta_title = "现在还没数据，先从一个 CSV 开始"
    cta_desc = "上传任意一个平台导出的 CSV，或运行 <code style='background:rgba(255,255,255,0.12);padding:2px 6px;border-radius:4px;'>python generate_sample_data.py</code> 体验示例数据。"
    cta_btn = "去上传数据 →"
else:
    cta_title = "数据已经就位，直接开始分析"
    cta_desc = f"当前数据源 <strong>{source_label}</strong>，共 {total_rows:,} 行 / {platform_count} 个平台 / {date_span_days} 天。"
    cta_btn = "查看运营视图 →"

st.markdown(
    f"""
    <div class="cta-banner">
      <h2>{cta_title}</h2>
      <p>{cta_desc}</p>
      <div class="hero-cta-row" style="margin-bottom:0;">
        <a class="btn-primary" href="/数据导入" target="_self">{cta_btn}</a>
        <a class="btn-ghost" href="/运营视图" target="_self">直接体验视图</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------- Footer -----------------

st.markdown(
    f"""
    <div class="pulse-footer">
      <div>© {pd.Timestamp.now().year} Pulse · 海外社媒数据面板</div>
      <div>示例数据 {len(sample_csvs)} 个 · 运营数据 {len(real_csvs)} 个 · 启动前请 <code style="background:#F1F5F9;padding:1px 6px;border-radius:4px;">bash init.sh</code></div>
    </div>
    """,
    unsafe_allow_html=True,
)
