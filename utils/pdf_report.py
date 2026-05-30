"""汇报视图 PDF 生成（F07）。

把周期汇报渲染成一份干净的 PDF：报头 + 本期 KPI 摘要 + 自动文字摘要 +
各平台数据表。中文嵌入仓库自带的 TrueType 字体
`assets/fonts/WenQuanYiZenHei.ttf`（含拉丁+中日韩字形，导出时只子集化用到的字形，文件很小），
保证本地与 Streamlit Cloud 上所有查看器都能正确显示中文；字体文件缺失时回落到
reportlab 内置 CID 字体兜底。reportlab 是纯 pip 依赖、无 API key，符合 CLAUDE.md。

本模块只依赖 reportlab + 标准库，不 import streamlit / pandas，便于单测：
调用方（pages/2）负责把 DataFrame/Series 拆成下面这些原生数据结构再传进来。
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# 纸面调色，与应用的编辑式视觉呼应（但 PDF 不强求像素级一致）
_INK = colors.HexColor("#14181F")
_TERRACOTTA = colors.HexColor("#B8412A")
_PAPER_DEEP = colors.HexColor("#EAE0CB")
_RULE = colors.HexColor("#C9Bfa6")

# 内置 TrueType 中文字体（嵌入子集，保证本地 / Streamlit Cloud 都正确渲染中文）
_FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "WenQuanYiZenHei.ttf"
_EMBEDDED_FONT = "CJKReport"
_font_name: str | None = None


def _ensure_font() -> str:
    """注册中文字体（只注册一次），返回可用的字体名。

    优先嵌入仓库自带的 TrueType 字体（字形真正进 PDF，所有查看器都能显示）；
    万一字体文件缺失，回落到 reportlab 内置 CID 字体 STSong-Light（依赖查看器
    自带 Adobe 中文字体包，仅作兜底）。
    """
    global _font_name
    if _font_name is not None:
        return _font_name
    try:
        if not _FONT_PATH.exists():
            raise FileNotFoundError(_FONT_PATH)
        pdfmetrics.registerFont(TTFont(_EMBEDDED_FONT, str(_FONT_PATH)))
        _font_name = _EMBEDDED_FONT
    except Exception:  # noqa: BLE001 - 字体文件异常时退化到 CID 字体
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        _font_name = "STSong-Light"
    return _font_name


def _md_to_rl(text: str) -> str:
    """把 `**x**` 粗体语法转成 reportlab 的 `<b>x</b>`，并转义裸 & < >。"""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def build_period_report_pdf(
    *,
    title: str,
    date_range: str,
    kpi: list[tuple[str, str, str | None]],
    summary_lines: list[str],
    platform_rows: list[dict],
) -> bytes:
    """生成周期汇报 PDF，返回 bytes（供 st.download_button）。

    Args:
        title: 报头标题，如 "2026-05 月度汇报"。
        date_range: 数据时段说明，如 "2026-05-01 → 2026-05-31"。
        kpi: 四个核心指标，每项 (标签, 值文本, 环比文本或 None)。
            如 [("总曝光", "1,234,567", "+12.3% 环比"), ...]。
        summary_lines: 自动文字摘要的每一行（可含 `**` 粗体、前导 "- "）。
        platform_rows: 各平台数据，每行 dict，键为
            平台 / 曝光 / 总互动 / 粉丝净增 / 期末粉丝 / 互动率（值均为已格式化字符串）。

    Returns:
        PDF 文件的字节内容。
    """
    font = _ensure_font()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=title,
    )

    base = getSampleStyleSheet()["Normal"]
    style_title = ParagraphStyle(
        "ReportTitle", parent=base, fontName=font, fontSize=20,
        leading=24, textColor=_INK, spaceAfter=2,
    )
    style_meta = ParagraphStyle(
        "ReportMeta", parent=base, fontName=font, fontSize=9,
        leading=12, textColor=_TERRACOTTA, spaceAfter=10,
    )
    style_h2 = ParagraphStyle(
        "ReportH2", parent=base, fontName=font, fontSize=12,
        leading=16, textColor=_INK, spaceBefore=12, spaceAfter=6,
    )
    style_body = ParagraphStyle(
        "ReportBody", parent=base, fontName=font, fontSize=10,
        leading=15, textColor=_INK,
    )
    style_kpi_label = ParagraphStyle(
        "KpiLabel", parent=base, fontName=font, fontSize=8,
        leading=10, textColor=_TERRACOTTA, alignment=1,
    )
    style_kpi_value = ParagraphStyle(
        "KpiValue", parent=base, fontName=font, fontSize=15,
        leading=18, textColor=_INK, alignment=1,
    )
    style_kpi_delta = ParagraphStyle(
        "KpiDelta", parent=base, fontName=font, fontSize=8,
        leading=10, textColor=colors.HexColor("#2B2F3A"), alignment=1,
    )

    elements: list = []

    # ---------- 报头 ----------
    elements.append(Paragraph(_md_to_rl(title), style_title))
    elements.append(Paragraph(f"数据时段：{date_range}", style_meta))

    # ---------- KPI 摘要（四列） ----------
    kpi_cells = []
    for label, value, delta in kpi:
        stack = [Paragraph(_md_to_rl(label), style_kpi_label),
                 Paragraph(_md_to_rl(value), style_kpi_value)]
        if delta:
            stack.append(Paragraph(_md_to_rl(delta), style_kpi_delta))
        kpi_cells.append(stack)
    kpi_table = Table([kpi_cells], colWidths=[doc.width / len(kpi_cells)] * len(kpi_cells))
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _PAPER_DEEP),
        ("BOX", (0, 0), (-1, -1), 0.75, _INK),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, _RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(kpi_table)

    # ---------- 文字摘要 ----------
    elements.append(Paragraph("汇报摘要", style_h2))
    for line in summary_lines:
        line = line.strip()
        if not line:
            continue
        # 摘要里以 "- " 开头的当作要点，缩进 + 项目符号
        bullet = line.startswith("- ")
        text = line[2:] if bullet else line
        # 跳过摘要里重复的标题行（如 "**xxx 汇报摘要**"），避免和上面的 H2 重复
        if re.fullmatch(r"\*\*.*汇报摘要\*\*", text):
            continue
        para_style = ParagraphStyle(
            "bullet", parent=style_body, leftIndent=12 if bullet else 0,
            bulletIndent=0,
        )
        prefix = "• " if bullet else ""
        elements.append(Paragraph(prefix + _md_to_rl(text), para_style))

    # ---------- 各平台数据表 ----------
    elements.append(Paragraph("各平台数据", style_h2))
    cols = ["平台", "曝光", "总互动", "粉丝净增", "期末粉丝", "互动率"]
    header_style = ParagraphStyle(
        "th", parent=style_body, fontSize=9, textColor=colors.white, alignment=1,
    )
    cell_l = ParagraphStyle("tdl", parent=style_body, fontSize=9, alignment=0)
    cell_r = ParagraphStyle("tdr", parent=style_body, fontSize=9, alignment=2)

    data = [[Paragraph(c, header_style) for c in cols]]
    for row in platform_rows:
        data.append([
            Paragraph(_md_to_rl(str(row.get("平台", ""))), cell_l),
            Paragraph(_md_to_rl(str(row.get("曝光", ""))), cell_r),
            Paragraph(_md_to_rl(str(row.get("总互动", ""))), cell_r),
            Paragraph(_md_to_rl(str(row.get("粉丝净增", ""))), cell_r),
            Paragraph(_md_to_rl(str(row.get("期末粉丝", ""))), cell_r),
            Paragraph(_md_to_rl(str(row.get("互动率", ""))), cell_r),
        ])
    table = Table(
        data,
        colWidths=[doc.width * w for w in (0.22, 0.17, 0.16, 0.16, 0.17, 0.12)],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _PAPER_DEEP]),
        ("BOX", (0, 0), (-1, -1), 0.75, _INK),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, _RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(table)

    # ---------- 页脚生成时间 ----------
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        f"由海外社媒数据面板生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        style_meta,
    ))

    doc.build(elements)
    return buf.getvalue()
