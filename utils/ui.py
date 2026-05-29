"""Shared UI primitives for the Streamlit social media dashboard.

视觉方向：编辑式报刊感（editorial briefing）。
- 字体：Fraunces 衬线显示 + Noto Serif SC 中文 + JetBrains Mono 数字
- 调色：暖米色纸面、深墨海军蓝、烧土红、森林绿、赭石、暖灰
- 装饰：纸面噪点、双线规则、印章序号、italic 强调
对外约定的 CSS class 名称（kpi-panel / kpi-grid / kpi-item / ki-label /
ki-value / ki-delta / soft-card / pill / title）保持不变，运营、汇报两页无需
改动模板，仅样式被改写。
"""

from __future__ import annotations

import html

import streamlit as st

# ---------- 颜色 / 设计 token ----------
PAPER = "#F2EBDC"
PAPER_DEEP = "#EAE0CB"
INK = "#14181F"
INK_SOFT = "#2B2F3A"
TERRACOTTA = "#B8412A"
FOREST = "#2E4A2B"
OCHRE = "#C58A2E"
WARM_GRAY = "#8B8378"
PLUM = "#6E3F8A"
RULE = "rgba(20, 24, 31, 0.14)"
RULE_STRONG = "rgba(20, 24, 31, 0.34)"

# 兼容旧引用（utils/ui 之前导出过这些常量）
ACCENT = TERRACOTTA
ACCENT_DARK = "#8E2F1F"
MUTED = WARM_GRAY
LINE = RULE
SURFACE = PAPER_DEEP
CANVAS = PAPER

# 全局共享：6 大平台显示名（运营/汇报/导入三页都用）
PLATFORM_LABELS = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "x": "X",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
}

# 与 mockup legend 对应：IG=terracotta、TikTok=ink、YT=ochre、X=warm-gray、FB=forest、LI=plum
CHART_COLOR_SEQUENCE = [
    TERRACOTTA,
    INK,
    OCHRE,
    WARM_GRAY,
    FOREST,
    PLUM,
]

# 字体堆栈
_SERIF_STACK = (
    '"Fraunces", "Noto Serif SC", "Songti SC", "STSong", "Source Han Serif SC", serif'
)
_MONO_STACK = (
    '"JetBrains Mono", "IBM Plex Mono", "SF Mono", Menlo, Consolas, monospace'
)


def inject_page_styles() -> None:
    """注入编辑式视觉系统（被所有子页面共享）。"""
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT,WONK@0,9..144,300..900,0..100,0..1;1,9..144,300..900,0..100,0..1&family=JetBrains+Mono:wght@300;400;500;600&family=Noto+Serif+SC:wght@400;600;900&display=swap');
:root {
            --paper:       #F2EBDC;
            --paper-deep:  #EAE0CB;
            --ink:         #14181F;
            --ink-soft:    #2B2F3A;
            --terracotta:  #B8412A;
            --forest:      #2E4A2B;
            --ochre:       #C58A2E;
            --warm-gray:   #8B8378;
            --plum:        #6E3F8A;
            --rule:        rgba(20, 24, 31, 0.14);
            --rule-strong: rgba(20, 24, 31, 0.34);
            --serif:       "Fraunces", "Noto Serif SC", "Songti SC", "STSong", "Source Han Serif SC", serif;
            --mono:        "JetBrains Mono", "IBM Plex Mono", "SF Mono", Menlo, Consolas, monospace;
        }

        /* 纸面噪点纹理（SVG turbulence，base64 over inline url） */
        .stApp::before {
            content: "";
            position: fixed; inset: 0;
            background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.08  0 0 0 0 0.09  0 0 0 0 0.12  0 0 0 0.18 0'/></filter><rect width='160' height='160' filter='url(%23n)'/></svg>");
            background-size: 160px 160px;
            mix-blend-mode: multiply;
            opacity: 0.45;
            pointer-events: none;
            z-index: 0;
        }
        .stApp > * { position: relative; z-index: 1; }

        header[data-testid="stHeader"] { background: transparent; }
        .stApp { background: var(--paper); }
        .block-container {
            max-width: 1280px;
            padding-top: 1.5rem;
            padding-bottom: 4rem;
        }

        html, body, [class*="css"] {
            font-family: var(--serif);
            font-variation-settings: "opsz" 14, "SOFT" 30, "WONK" 0;
            color: var(--ink);
            -webkit-font-smoothing: antialiased;
        }

        /* ---------------- masthead / hero ---------------- */
        .page-hero {
            display: grid;
            grid-template-columns: minmax(0, 1.25fr) minmax(260px, 0.75fr);
            gap: 2.2rem;
            align-items: end;
            padding: 1.6rem 0 1.4rem;
            margin-bottom: 1.4rem;
            border-bottom: 3px double var(--ink);
            position: relative;
        }
        .page-hero::after {
            content: "";
            position: absolute;
            left: 0; right: 0; bottom: -7px;
            height: 1px;
            background: var(--rule-strong);
        }
        .page-hero-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            margin-bottom: 0.8rem;
            color: var(--terracotta);
            font-family: var(--mono);
            font-size: 0.7rem;
            font-weight: 500;
            letter-spacing: 0.34em;
            text-transform: uppercase;
        }
        .page-hero-eyebrow .badge-dot,
        .page-hero-meta .dot,
        .sec-eyebrow .ico {
            width: 0.55rem;
            height: 0.55rem;
            border-radius: 999px;
            background: var(--terracotta);
            box-shadow: 0 0 0 3px var(--paper), 0 0 0 4px var(--terracotta);
        }
        .page-hero-title {
            max-width: 880px;
            margin: 0 0 0.65rem;
            color: var(--ink);
            font-family: "Noto Serif SC", "Fraunces", serif;
            font-size: clamp(2.4rem, 4.6vw, 3.8rem);
            font-weight: 900;
            letter-spacing: -0.015em;
            line-height: 1.03;
            text-wrap: balance;
        }
        .page-hero-title .grad {
            font-family: "Fraunces", serif;
            font-style: italic;
            font-weight: 400;
            font-variation-settings: "opsz" 144, "SOFT" 100, "WONK" 1;
            color: var(--terracotta);
            -webkit-text-fill-color: currentColor;
            background: none;
            margin-left: 0.1em;
        }
        .page-hero-sub {
            max-width: 60ch;
            margin: 0;
            color: var(--ink-soft);
            font-family: var(--serif);
            font-variation-settings: "opsz" 14, "SOFT" 30;
            font-size: 1rem;
            line-height: 1.65;
        }
        .page-hero-meta {
            justify-self: end;
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            max-width: 100%;
            padding: 0.55rem 0.85rem;
            border: 1px solid var(--ink);
            background: var(--paper-deep);
            color: var(--ink);
            font-family: var(--mono);
            font-size: 0.72rem;
            line-height: 1.4;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }

        /* ---------------- section eyebrow ---------------- */
        .sec-eyebrow {
            display: flex;
            align-items: baseline;
            gap: 0.8rem;
            margin-top: 2.3rem;
            margin-bottom: 0.8rem;
            padding-top: 0.9rem;
            border-top: 1px solid var(--rule-strong);
            position: relative;
        }
        .sec-eyebrow::before {
            content: "";
            position: absolute;
            left: 0; top: 0;
            width: 56px; height: 3px;
            background: var(--ink);
        }
        .sec-eyebrow h3 {
            margin: 0;
            color: var(--ink);
            font-family: "Noto Serif SC", "Fraunces", serif;
            font-size: 1.4rem;
            font-weight: 900;
            letter-spacing: -0.01em;
        }
        .sec-eyebrow .hint {
            color: var(--warm-gray);
            font-family: "Fraunces", serif;
            font-style: italic;
            font-variation-settings: "opsz" 14, "SOFT" 60;
            font-size: 0.92rem;
        }

        /* ---------------- KPI panel（运营、汇报两页共用） ---------------- */
        .kpi-panel {
            padding: 0.6rem 0 0.4rem;
            margin-bottom: 0.4rem;
            border-top: 1px solid var(--ink);
            border-bottom: 1px solid var(--ink);
            background: transparent;
            position: relative;
        }
        .kpi-panel::before,
        .kpi-panel::after {
            content: "";
            position: absolute; left: 0; right: 0;
            height: 1px;
            background: var(--rule-strong);
        }
        .kpi-panel::before { top: -4px; }
        .kpi-panel::after  { bottom: -4px; }

        .kpi-panel-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            padding: 0.4rem 0.2rem 0.55rem;
            border-bottom: 1px dashed var(--rule-strong);
        }
        .kpi-panel-head .pill {
            padding: 0.22rem 0.6rem;
            border: 1px solid var(--ink);
            background: var(--ink);
            color: var(--paper) !important;
            font-family: var(--mono);
            font-size: 0.66rem;
            font-weight: 500;
            letter-spacing: 0.22em;
            text-transform: uppercase;
        }
        .kpi-panel-head .title {
            color: var(--warm-gray);
            font-family: "Fraunces", serif;
            font-style: italic;
            font-variation-settings: "opsz" 144, "SOFT" 80;
            font-size: 0.95rem;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0;
            margin-top: 0;
        }
        .kpi-item {
            position: relative;
            padding: 0.85rem 0.95rem 0.95rem;
            background: transparent;
            border-right: 1px dashed var(--rule-strong);
            border-bottom: 1px dashed var(--rule-strong);
        }
        .kpi-item:nth-child(2n) { border-right: 0; }
        .kpi-item:nth-last-child(-n+2) { border-bottom: 0; }
        /* 4 列网格（汇报页用 inline grid-template-columns 覆盖） */
        .kpi-grid[style*="1fr 1fr 1fr 1fr"] .kpi-item:nth-child(2n) { border-right: 1px dashed var(--rule-strong); }
        .kpi-grid[style*="1fr 1fr 1fr 1fr"] .kpi-item:nth-child(4n) { border-right: 0; }
        .kpi-grid[style*="1fr 1fr 1fr 1fr"] .kpi-item:nth-last-child(-n+4) { border-bottom: 0; }
        .kpi-grid[style*="1fr 1fr 1fr 1fr"] .kpi-item:nth-last-child(-n+2) { border-bottom: 1px dashed var(--rule-strong); }

        .kpi-item .ki-label {
            font-family: var(--mono);
            font-size: 0.66rem;
            font-weight: 500;
            color: var(--warm-gray);
            letter-spacing: 0.22em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }
        .kpi-item .ki-value {
            font-family: var(--mono);
            font-size: 1.7rem;
            font-weight: 500;
            color: var(--ink);
            letter-spacing: -0.02em;
            line-height: 1.05;
            font-feature-settings: "tnum" 1;
        }
        .kpi-item .ki-delta {
            font-family: var(--mono);
            font-size: 0.74rem;
            font-weight: 500;
            margin-top: 0.45rem;
            letter-spacing: 0.06em;
        }
        .kpi-item .ki-delta.pos { color: var(--forest); }
        .kpi-item .ki-delta.neg { color: var(--terracotta); }
        .kpi-item .ki-delta.neu { color: var(--warm-gray); }

        /* 印章风格平台名（如果 pill 是平台名而不是"本期总览"） */
        .kpi-item::before {
            content: "";
            position: absolute;
            top: 0.6rem; right: 0.7rem;
            width: 6px; height: 6px;
            background: var(--terracotta);
            opacity: 0.5;
            border-radius: 50%;
        }

        /* ---------------- 柔软卡片（摘要、说明区） ---------------- */
        .soft-card {
            position: relative;
            padding: 1.4rem 1.5rem 1.5rem;
            margin: 0.6rem 0 1rem;
            background: var(--paper-deep);
            border: 1px solid var(--ink);
            font-family: var(--serif);
            font-variation-settings: "opsz" 14, "SOFT" 30;
            font-size: 0.98rem;
            line-height: 1.7;
            color: var(--ink-soft);
        }
        .soft-card::before {
            content: "";
            position: absolute;
            inset: 6px;
            border: 1px solid var(--rule-strong);
            pointer-events: none;
        }
        .soft-card p:first-child { margin-top: 0; }
        .soft-card p:last-child  { margin-bottom: 0; }
        .soft-card strong {
            font-family: var(--mono);
            font-weight: 500;
            font-size: 0.95em;
            background: var(--paper);
            padding: 0 0.25rem;
            color: var(--ink);
        }

        /* ---------------- Streamlit 原生组件主题化 ---------------- */
        [data-testid="stMetric"] {
            padding: 0.4rem 0 0.6rem;
            border-bottom: 1px dashed var(--rule-strong);
        }
        [data-testid="stMetricValue"] {
            color: var(--ink);
            font-family: var(--mono);
            font-weight: 500;
            letter-spacing: -0.02em;
        }
        [data-testid="stMetricLabel"] {
            color: var(--warm-gray) !important;
            font-family: var(--mono);
            font-size: 0.7rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.22em !important;
            text-transform: uppercase;
        }
        [data-testid="stMetricDelta"] {
            color: var(--terracotta) !important;
            font-family: var(--mono);
            font-weight: 500;
        }
        [data-testid="stMetricDelta"] svg { display: none; }

        /* 按钮：油墨色印刷风 */
        button[kind="primary"],
        button[kind="secondary"],
        div[data-testid="stDownloadButton"] button {
            border: 1px solid var(--ink) !important;
            border-radius: 0 !important;
            background: var(--ink) !important;
            color: var(--paper) !important;
            font-family: var(--mono) !important;
            font-size: 0.78rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.18em !important;
            text-transform: uppercase !important;
            transition: transform 160ms cubic-bezier(.16,1,.3,1), box-shadow 160ms ease !important;
        }
        button[kind="secondary"],
        div[data-testid="stDownloadButton"] button {
            background: var(--paper-deep) !important;
            color: var(--ink) !important;
        }
        button[kind="primary"]:hover,
        button[kind="secondary"]:hover,
        div[data-testid="stDownloadButton"] button:hover {
            transform: translate(-2px, -2px);
            box-shadow: 3px 3px 0 var(--ink);
        }
        button:active { transform: translate(0, 0); box-shadow: none; }

        /* radio / multiselect / date label */
        div[role="radiogroup"] label,
        label[data-testid="stWidgetLabel"] {
            font-family: var(--mono);
            font-size: 0.72rem !important;
            font-weight: 500 !important;
            color: var(--ink) !important;
            letter-spacing: 0.22em !important;
            text-transform: uppercase;
        }

        /* tab nav（数据导入页 4 tab） */
        button[data-baseweb="tab"] {
            font-family: var(--mono) !important;
            font-size: 0.78rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.16em !important;
            text-transform: uppercase !important;
            color: var(--warm-gray) !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--ink) !important;
        }
        button[data-baseweb="tab"][aria-selected="true"]::after {
            background: var(--terracotta) !important;
        }
        div[data-baseweb="tab-list"] {
            border-bottom: 1px solid var(--rule-strong) !important;
        }

        /* sidebar */
        section[data-testid="stSidebar"] {
            background: var(--paper-deep);
            border-right: 1px solid var(--rule-strong);
        }
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            font-family: "Noto Serif SC", "Fraunces", serif;
            font-weight: 900;
            letter-spacing: -0.01em;
            color: var(--ink);
        }

        /* dataframe / table — 类报纸数表 */
        [data-testid="stDataFrame"] {
            border: 1px solid var(--ink);
            background: var(--paper-deep);
        }
        [data-testid="stDataFrame"] [role="columnheader"] {
            font-family: var(--mono) !important;
            font-size: 0.7rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.22em !important;
            text-transform: uppercase !important;
            color: var(--warm-gray) !important;
            background: var(--paper) !important;
        }
        [data-testid="stDataFrame"] [role="gridcell"] {
            font-family: var(--mono) !important;
            font-size: 0.84rem !important;
            color: var(--ink) !important;
        }

        /* caption */
        .stCaption, [data-testid="stCaption"] {
            font-family: "Fraunces", serif !important;
            font-style: italic !important;
            font-variation-settings: "opsz" 14, "SOFT" 60 !important;
            color: var(--warm-gray) !important;
            font-size: 0.85rem !important;
        }

        /* 普通正文 markdown */
        .stMarkdown p {
            font-family: var(--serif);
            font-variation-settings: "opsz" 14, "SOFT" 30;
            line-height: 1.65;
            color: var(--ink-soft);
        }
        .stMarkdown a { color: var(--terracotta); }

        /* warning / info / success / error — 印刷条而非圆角胶囊 */
        div[data-baseweb="notification"],
        div[data-testid="stAlert"] {
            border-radius: 0 !important;
            border: 1px solid var(--ink) !important;
            background: var(--paper-deep) !important;
            font-family: var(--serif) !important;
            font-variation-settings: "opsz" 14, "SOFT" 30 !important;
        }

        @media (max-width: 860px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; }
            .page-hero { grid-template-columns: 1fr; gap: 1rem; }
            .page-hero-meta { justify-self: stretch; }
            .kpi-grid { grid-template-columns: 1fr !important; }
            .kpi-item, .kpi-item:nth-child(2n) {
                border-right: 0;
                border-bottom: 1px dashed var(--rule-strong);
            }
            .kpi-item:last-child { border-bottom: 0; }
        }
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
    """编辑式 masthead：双线规则 + 印章 eyebrow + italic 强调副标题 + mono 数据源戳记。"""
    safe_eyebrow = html.escape(eyebrow)
    safe_title_main = html.escape(title_main)
    safe_title_grad = html.escape(title_grad)
    safe_subtitle = html.escape(subtitle)
    grad_html = f' <span class="grad">{safe_title_grad}</span>' if title_grad else ""
    meta_html = (
        f'<div class="page-hero-meta"><span class="dot"></span>{html.escape(meta)}</div>'
        if meta
        else ""
    )
    st.markdown(
        f"""
        <div class="page-hero">
          <div>
            <div class="page-hero-eyebrow"><span class="badge-dot"></span>{safe_eyebrow}</div>
            <div class="page-hero-title">{safe_title_main}{grad_html}</div>
            <p class="page-hero-sub">{safe_subtitle}</p>
          </div>
          {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, icon: str = "", color: str = "accent", hint: str = "") -> None:
    """编辑式段落规则：横向粗线 + Noto Serif SC 标题 + italic 提示。

    icon / color 参数保留兼容旧调用，已不再使用。
    """
    del icon, color
    hint_html = f'<span class="hint">{html.escape(hint)}</span>' if hint else ""
    st.markdown(
        f"""
        <div class="sec-eyebrow">
          <span class="ico"></span>
          <h3>{html.escape(title)}</h3>
          {hint_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def apply_plotly_theme(fig) -> None:
    """图表主题：纸面底、墨色坐标、衬线字体、editorial 配色序列。"""
    fig.update_layout(
        colorway=CHART_COLOR_SEQUENCE,
        paper_bgcolor="rgba(234, 224, 203, 0.55)",
        plot_bgcolor="rgba(0, 0, 0, 0)",
        font=dict(
            family='"Fraunces", "Noto Serif SC", "Songti SC", serif',
            color=INK_SOFT,
            size=12,
        ),
        margin=dict(l=14, r=14, t=36, b=14),
        legend=dict(
            bgcolor="rgba(0, 0, 0, 0)",
            bordercolor=RULE_STRONG,
            borderwidth=1,
            font=dict(
                family='"JetBrains Mono", "IBM Plex Mono", monospace',
                size=10,
                color=INK,
            ),
        ),
        xaxis=dict(
            gridcolor="rgba(20, 24, 31, 0.08)",
            zerolinecolor="rgba(20, 24, 31, 0.14)",
            linecolor=INK,
            linewidth=1,
            tickfont=dict(
                family='"JetBrains Mono", monospace',
                size=10,
                color=WARM_GRAY,
            ),
            title_font=dict(family='"Fraunces", serif', size=12, color=INK_SOFT),
        ),
        yaxis=dict(
            gridcolor="rgba(20, 24, 31, 0.08)",
            zerolinecolor="rgba(20, 24, 31, 0.14)",
            linecolor=INK,
            linewidth=1,
            tickfont=dict(
                family='"JetBrains Mono", monospace',
                size=10,
                color=WARM_GRAY,
            ),
            title_font=dict(family='"Fraunces", serif', size=12, color=INK_SOFT),
        ),
    )
