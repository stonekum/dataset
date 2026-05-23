"""Shared UI primitives for the Streamlit social media dashboard."""

from __future__ import annotations

import html

import streamlit as st

ACCENT = "#0F766E"
ACCENT_DARK = "#115E59"
INK = "#1F2933"
MUTED = "#667085"
LINE = "rgba(31, 41, 51, 0.10)"
SURFACE = "#FFFFFF"
CANVAS = "#F7F8F6"

# 全局共享：6 大平台显示名（运营/汇报/导入三页都用）
PLATFORM_LABELS = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "x": "X",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
}

CHART_COLOR_SEQUENCE = [
    "#0F766E",
    "#2563EB",
    "#B45309",
    "#BE123C",
    "#475569",
    "#15803D",
]


def inject_page_styles() -> None:
    """Inject the restrained dashboard visual system used by all subpages."""
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
            padding-bottom: 3.25rem;
        }

        html, body, [class*="css"] {
            font-family: "Geist", "SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: var(--ink);
        }

        .page-hero {
            display: grid;
            grid-template-columns: minmax(0, 1.45fr) minmax(260px, 0.75fr);
            gap: 2rem;
            align-items: end;
            padding: 2rem 0 1.7rem;
            margin-bottom: 1.6rem;
            border-bottom: 1px solid var(--line);
        }
        .page-hero-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.7rem;
            color: var(--accent-dark);
            font-size: 0.73rem;
            font-weight: 750;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }
        .page-hero-eyebrow .badge-dot,
        .page-hero-meta .dot,
        .sec-eyebrow .ico {
            width: 0.55rem;
            height: 0.55rem;
            border-radius: 999px;
            background: var(--accent);
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.35);
        }
        .page-hero-title {
            max-width: 820px;
            margin: 0 0 0.65rem;
            color: var(--ink);
            font-size: clamp(2rem, 4.2vw, 3.6rem);
            font-weight: 780;
            letter-spacing: 0;
            line-height: 1.04;
        }
        .page-hero-title .grad {
            color: var(--accent-dark);
            -webkit-text-fill-color: currentColor;
            background: none;
        }
        .page-hero-sub {
            max-width: 760px;
            margin: 0;
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.68;
        }
        .page-hero-meta {
            justify-self: end;
            display: inline-flex;
            align-items: center;
            gap: 0.58rem;
            max-width: 100%;
            padding: 0.7rem 0.85rem;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: rgba(255,255,255,0.72);
            color: #344054;
            font-size: 0.82rem;
            line-height: 1.45;
            box-shadow: 0 18px 40px -28px rgba(31,41,51,0.22);
        }

        .sec-eyebrow {
            display: flex;
            align-items: baseline;
            gap: 0.65rem;
            margin-top: 2.15rem;
            margin-bottom: 0.75rem;
            padding-top: 0.85rem;
            border-top: 1px solid var(--line);
        }
        .sec-eyebrow h3 {
            margin: 0;
            color: var(--ink);
            font-size: 1.08rem;
            font-weight: 760;
            letter-spacing: 0;
        }
        .sec-eyebrow .hint {
            color: var(--muted);
            font-size: 0.84rem;
        }

        .kpi-panel {
            padding: 1rem 0 0.65rem;
            margin-bottom: 0.4rem;
            border-top: 1px solid var(--line);
            background: transparent;
        }
        .kpi-panel-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.6rem;
        }
        .kpi-panel-head .pill {
            padding: 0.18rem 0.55rem;
            border: 1px solid var(--line);
            border-radius: 999px;
            background: rgba(255,255,255,0.68);
            color: var(--accent-dark) !important;
            font-size: 0.72rem;
            font-weight: 720;
            letter-spacing: 0.04em;
        }
        .kpi-panel-head .title {
            color: var(--muted);
            font-size: 0.82rem;
            font-weight: 620;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.45rem;
            margin-top: 0.45rem;
        }
        .kpi-item {
            padding: 0.55rem 0.65rem;
            background: var(--canvas);
            border: 1px solid var(--line);
            border-radius: 6px;
        }
        .kpi-item .ki-label {
            font-size: 0.72rem; font-weight: 600;
            color: var(--muted); letter-spacing: 0.02em;
            margin-bottom: 0.18rem;
        }
        .kpi-item .ki-value {
            font-size: 1.38rem; font-weight: 780;
            letter-spacing: -0.02em; color: var(--ink); line-height: 1.15;
        }
        .kpi-item .ki-delta { font-size: 0.76rem; font-weight: 650; margin-top: 0.08rem; }
        .kpi-item .ki-delta.pos { color: var(--accent); }
        .kpi-item .ki-delta.neg { color: #BE123C; }
        .kpi-item .ki-delta.neu { color: var(--muted); }

        .soft-card {
            padding: 1.2rem 1.25rem;
            margin: 0.45rem 0 0.7rem;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: var(--surface);
            box-shadow: 0 18px 42px -34px rgba(31,41,51,0.28);
        }

        [data-testid="stMetric"] {
            padding: 0.25rem 0 0.6rem;
            border-bottom: 1px solid rgba(31,41,51,0.07);
        }
        [data-testid="stMetricValue"] {
            color: var(--ink);
            font-weight: 780;
            letter-spacing: 0;
        }
        [data-testid="stMetricLabel"] {
            color: var(--muted) !important;
            font-weight: 600;
        }
        [data-testid="stMetricDelta"] {
            color: var(--accent-dark) !important;
            font-weight: 650;
        }
        [data-testid="stMetricDelta"] svg { display: none; }

        button[kind="primary"],
        div[data-testid="stDownloadButton"] button {
            border: 0 !important;
            border-radius: 8px !important;
            background: var(--ink) !important;
            color: #fff !important;
            font-weight: 650 !important;
            transition: transform 160ms cubic-bezier(.16,1,.3,1), background 160ms ease !important;
        }
        button[kind="primary"]:hover,
        div[data-testid="stDownloadButton"] button:hover {
            background: #344054 !important;
            transform: translateY(-1px);
        }
        button:active { transform: translateY(1px) scale(0.99); }

        div[role="radiogroup"] label,
        label[data-testid="stWidgetLabel"] {
            font-weight: 620;
            color: var(--ink);
        }

        @media (max-width: 760px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; }
            .page-hero { grid-template-columns: 1fr; gap: 1rem; padding-top: 1rem; }
            .page-hero-meta { justify-self: stretch; }
            .sec-eyebrow { align-items: flex-start; flex-direction: column; gap: 0.3rem; }
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
    """Render a left-aligned, work-focused page header."""
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
    """Render a compact section heading. The icon argument is kept for compatibility."""
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
    """Apply the dashboard chart style."""
    fig.update_layout(
        colorway=CHART_COLOR_SEQUENCE,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Geist, SF Pro Display, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
            color="#344054",
            size=12,
        ),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(
            bgcolor="rgba(255,255,255,0)",
            bordercolor="rgba(31,41,51,0.10)",
            borderwidth=1,
        ),
        xaxis=dict(
            gridcolor="rgba(31,41,51,0.07)",
            zerolinecolor="rgba(31,41,51,0.10)",
            linecolor="rgba(31,41,51,0.12)",
        ),
        yaxis=dict(
            gridcolor="rgba(31,41,51,0.07)",
            zerolinecolor="rgba(31,41,51,0.10)",
            linecolor="rgba(31,41,51,0.12)",
        ),
    )
