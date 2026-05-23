"""共享 UI 组件 — Hero header、全局样式、Plotly 主题。

子页面通过 inject_page_styles() + render_hero() 获得与首页一致的视觉风格。
"""

from __future__ import annotations

import streamlit as st

# 与首页保持一致的色板
INDIGO = "#6366F1"
VIOLET = "#8B5CF6"
PINK = "#EC4899"
INK = "#0F172A"
MUTED = "#64748B"

# Plotly 配色（用于 px.line / px.bar 等）
CHART_COLOR_SEQUENCE = [
    "#6366F1",  # indigo
    "#EC4899",  # pink
    "#F59E0B",  # amber
    "#10B981",  # emerald
    "#0EA5E9",  # sky
    "#8B5CF6",  # violet
]


def inject_page_styles() -> None:
    """注入与首页一致的 SaaS 风格全局样式。子页面（layout=wide）调用一次。"""
    st.markdown(
        """
        <style>
        header[data-testid="stHeader"] { background: transparent; }
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 3rem;
            max-width: 1240px;
        }
        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }

        /* ===== Hero ===== */
        .page-hero {
            position: relative;
            margin: 0 0 1.75rem 0;
            padding: 1.8rem 1.9rem;
            border-radius: 20px;
            background:
              radial-gradient(circle at 0% 0%, rgba(99,102,241,0.18), transparent 55%),
              radial-gradient(circle at 100% 100%, rgba(236,72,153,0.16), transparent 55%),
              linear-gradient(135deg, #F8FAFC 0%, #FFFFFF 100%);
            border: 1px solid rgba(15,23,42,0.06);
            overflow: hidden;
        }
        .page-hero-eyebrow {
            display: inline-flex; align-items: center; gap: 0.45rem;
            font-size: 0.72rem; font-weight: 600;
            letter-spacing: 0.14em; text-transform: uppercase;
            color: #4F46E5;
            margin-bottom: 0.55rem;
        }
        .page-hero-eyebrow .badge-dot {
            width: 6px; height: 6px; border-radius: 50%;
            background: #22C55E;
            box-shadow: 0 0 0 3px rgba(34,197,94,0.18);
        }
        .page-hero-title {
            font-size: 1.85rem; font-weight: 700;
            color: #0F172A; letter-spacing: -0.025em;
            line-height: 1.15;
            margin: 0 0 0.45rem 0;
        }
        .page-hero-title .grad {
            background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 50%, #EC4899 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .page-hero-sub {
            font-size: 0.98rem; color: #475569;
            max-width: 720px; line-height: 1.55;
            margin: 0 0 0.85rem 0;
        }
        .page-hero-meta {
            display: inline-flex; align-items: center; gap: 0.5rem;
            padding: 0.32rem 0.75rem;
            font-size: 0.78rem; font-weight: 500;
            color: #334155;
            background: rgba(255,255,255,0.75);
            border: 1px solid rgba(15,23,42,0.08);
            border-radius: 999px;
            backdrop-filter: blur(6px);
        }
        .page-hero-meta .dot {
            width: 6px; height: 6px; border-radius: 50%;
            background: #6366F1;
        }

        /* ===== Section eyebrow ===== */
        .sec-eyebrow {
            display: inline-flex; align-items: center; gap: 0.55rem;
            margin-top: 2rem; margin-bottom: 0.35rem;
        }
        .sec-eyebrow .ico {
            width: 30px; height: 30px;
            border-radius: 9px;
            display: inline-flex; align-items: center; justify-content: center;
            font-size: 0.95rem;
            background: rgba(99,102,241,0.1); color: #4F46E5;
        }
        .sec-eyebrow .ico.rose    { background: rgba(236,72,153,0.1); color: #DB2777; }
        .sec-eyebrow .ico.amber   { background: rgba(245,158,11,0.1); color: #B45309; }
        .sec-eyebrow .ico.emerald { background: rgba(16,185,129,0.1); color: #047857; }
        .sec-eyebrow .ico.sky     { background: rgba(14,165,233,0.1); color: #0369A1; }
        .sec-eyebrow .ico.violet  { background: rgba(139,92,246,0.1); color: #6D28D9; }
        .sec-eyebrow .ico.slate   { background: rgba(15,23,42,0.07); color: #334155; }
        .sec-eyebrow h3 {
            margin: 0; font-size: 1.15rem; font-weight: 700;
            color: #0F172A; letter-spacing: -0.01em;
        }
        .sec-eyebrow .hint { font-size: 0.85rem; color: #64748B; margin-left: 0.4rem; }

        /* ===== KPI panel ===== */
        .kpi-panel {
            background: #fff;
            border: 1px solid rgba(15,23,42,0.07);
            border-radius: 16px;
            padding: 1.2rem 1.25rem 1rem 1.25rem;
            margin-bottom: 0.75rem;
            transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
        }
        .kpi-panel:hover {
            transform: translateY(-2px);
            box-shadow: 0 14px 32px -22px rgba(15,23,42,0.18);
            border-color: rgba(99,102,241,0.25);
        }
        .kpi-panel-head {
            display: flex; align-items: center; gap: 0.55rem;
            margin-bottom: 0.85rem;
        }
        .kpi-panel-head .pill {
            font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em;
            padding: 0.2rem 0.6rem; border-radius: 999px;
            background: rgba(99,102,241,0.1); color: #4F46E5;
        }
        .kpi-panel-head .title {
            font-weight: 600; font-size: 0.98rem; color: #0F172A;
        }

        /* ===== Soft card (用来包裹 summary / 数据预览) ===== */
        .soft-card {
            background: linear-gradient(180deg, #FFFFFF 0%, #FAFBFD 100%);
            border: 1px solid rgba(15,23,42,0.07);
            border-radius: 16px;
            padding: 1.3rem 1.4rem;
            margin: 0.4rem 0 0.6rem 0;
        }

        /* 让 Streamlit st.metric 在卡片内更克制 */
        [data-testid="stMetricValue"] {
            font-weight: 700; letter-spacing: -0.02em;
            background: linear-gradient(135deg, #6366F1, #EC4899);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        [data-testid="stMetricLabel"] { color: #64748B !important; font-weight: 500; }
        [data-testid="stMetricDelta"] svg { display: none; }

        /* 主按钮/下载按钮统一颜色 */
        button[kind="primary"], div[data-testid="stDownloadButton"] button {
            background: #0F172A !important;
            color: #fff !important;
            border: none !important;
            border-radius: 10px !important;
            font-weight: 500 !important;
        }
        button[kind="primary"]:hover, div[data-testid="stDownloadButton"] button:hover {
            background: #1E293B !important;
            transform: translateY(-1px);
        }

        /* 让 tab / radio 看起来更像现代 SaaS */
        div[role="radiogroup"] label { font-weight: 500; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(
    eyebrow: str,
    title_main: str,
    title_grad: str = "",
    subtitle: str = "",
    meta: str | None = None,
) -> None:
    """渲染子页面 hero header。

    - eyebrow：右上方 eyebrow tag 文字（不含 dot）
    - title_main：标题主体（黑色）
    - title_grad：标题中渐变高亮的部分（可空），会拼接在 title_main 后
    - subtitle：副标题
    - meta：右下角小 chip，例如数据源；为 None 时不显示
    """
    grad_html = f' <span class="grad">{title_grad}</span>' if title_grad else ""
    meta_html = (
        f'<div class="page-hero-meta"><span class="dot"></span>{meta}</div>'
        if meta
        else ""
    )
    st.markdown(
        f"""
        <div class="page-hero">
          <div class="page-hero-eyebrow"><span class="badge-dot"></span>{eyebrow}</div>
          <div class="page-hero-title">{title_main}{grad_html}</div>
          <p class="page-hero-sub">{subtitle}</p>
          {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, icon: str = "✦", color: str = "indigo", hint: str = "") -> None:
    """渲染带图标的 section heading（替代 st.subheader 提升设计感）。"""
    hint_html = f'<span class="hint">{hint}</span>' if hint else ""
    st.markdown(
        f"""
        <div class="sec-eyebrow">
          <span class="ico {color}">{icon}</span>
          <h3>{title}</h3>
          {hint_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def apply_plotly_theme(fig) -> None:
    """统一 Plotly 图表外观：透明背景 + 项目色板 + 现代字体。"""
    fig.update_layout(
        colorway=CHART_COLOR_SEQUENCE,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            color="#334155",
            size=12,
        ),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(
            bgcolor="rgba(255,255,255,0)",
            bordercolor="rgba(15,23,42,0.06)",
            borderwidth=1,
        ),
        xaxis=dict(
            gridcolor="rgba(15,23,42,0.06)",
            zerolinecolor="rgba(15,23,42,0.08)",
            linecolor="rgba(15,23,42,0.1)",
        ),
        yaxis=dict(
            gridcolor="rgba(15,23,42,0.06)",
            zerolinecolor="rgba(15,23,42,0.08)",
            linecolor="rgba(15,23,42,0.1)",
        ),
    )
