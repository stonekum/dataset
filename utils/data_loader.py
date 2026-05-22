"""F03 — CSV 读取与来源自动识别。

职责：扫描目录下所有 CSV 文件，按表头识别来源（Metricool 统一格式或各平台原生导出），
统一映射为 CLAUDE.md 中定义的标准字段命名，返回一个合并的 pandas DataFrame。

标准输出列：
    date(datetime64), platform(str), followers, impressions, reach, likes,
    comments, shares, saves, posts_count

缺失列会被填充为 NaN（数值类）或空字符串（字符串类），不会抛异常。
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# CLAUDE.md 标准字段命名表中的基础列（衍生字段在 F04 计算）
STANDARD_NUMERIC_COLS = [
    "followers",
    "impressions",
    "reach",
    "likes",
    "comments",
    "shares",
    "saves",
    "posts_count",
]
STANDARD_COLS = ["date", "platform", *STANDARD_NUMERIC_COLS]


# 各平台原生导出的指纹（必须出现的字段子集）→ (platform_name, column_map)
# column_map：原生列名 → 标准列名
_PLATFORM_FINGERPRINTS: list[tuple[str, set[str], dict[str, str]]] = [
    (
        "instagram",
        {"Date", "Followers", "Impressions", "Reach", "Likes", "Comments", "Shares", "Saves"},
        {
            "Date": "date",
            "Followers": "followers",
            "Impressions": "impressions",
            "Reach": "reach",
            "Likes": "likes",
            "Comments": "comments",
            "Shares": "shares",
            "Saves": "saves",
        },
    ),
    (
        "tiktok",
        {"Date", "Followers", "Video Views", "Likes", "Comments", "Shares"},
        {
            "Date": "date",
            "Followers": "followers",
            "Video Views": "impressions",
            "Likes": "likes",
            "Comments": "comments",
            "Shares": "shares",
        },
    ),
    (
        "youtube",
        {"Date", "Subscribers", "Views", "Likes", "Comments"},
        {
            "Date": "date",
            "Subscribers": "followers",
            "Views": "impressions",
            "Likes": "likes",
            "Comments": "comments",
        },
    ),
    (
        "x",
        {"Date", "Followers", "Impressions", "Likes", "Replies", "Retweets"},
        {
            "Date": "date",
            "Followers": "followers",
            "Impressions": "impressions",
            "Likes": "likes",
            "Replies": "comments",
            "Retweets": "shares",
        },
    ),
    (
        "facebook",
        {"Date", "Page Followers", "Impressions", "Reach", "Reactions", "Comments", "Shares"},
        {
            "Date": "date",
            "Page Followers": "followers",
            "Impressions": "impressions",
            "Reach": "reach",
            "Reactions": "likes",
            "Comments": "comments",
            "Shares": "shares",
        },
    ),
    (
        "linkedin",
        {"Date", "Total followers", "Impressions", "Reactions", "Comments", "Shares"},
        {
            "Date": "date",
            "Total followers": "followers",
            "Impressions": "impressions",
            "Reactions": "likes",
            "Comments": "comments",
            "Shares": "shares",
        },
    ),
]

# Metricool 统一导出的指纹
_METRICOOL_REQUIRED = {"Account", "Network", "Date"}
_METRICOOL_COLUMN_MAP = {
    "Date": "date",
    "Followers": "followers",
    "Impressions": "impressions",
    "Reach": "reach",
    "Likes": "likes",
    "Comments": "comments",
    "Shares": "shares",
    "Saves": "saves",
    "Posts": "posts_count",
}

# Metricool 的 Network 字段值 → 标准平台名
_METRICOOL_NETWORK_MAP = {
    "instagram": "instagram",
    "tiktok": "tiktok",
    "youtube": "youtube",
    "twitter": "x",
    "x": "x",
    "facebook": "facebook",
    "linkedin": "linkedin",
}


class LoaderWarning(UserWarning):
    """用于在 Streamlit 上下文之外做单元测试时捕获警告。"""


def _emit_warning(message: str) -> None:
    """在 Streamlit 运行时中用 st.warning，否则记到日志。

    通过 streamlit.runtime.exists() 判断是否在真实的 Streamlit 进程中，
    避免在 CLI/单元测试上下文里把警告丢进 Streamlit 内部 logger 而看不见。
    """
    try:
        import streamlit as st
        from streamlit.runtime import exists as _runtime_exists

        if _runtime_exists():
            st.warning(message)
            return
    except Exception:  # noqa: BLE001 - 任何导入或运行时检查失败都降级
        pass
    logger.warning(message)


def _identify_source(columns: set[str]) -> tuple[str | None, dict[str, str] | None]:
    """根据列集合识别 CSV 来源。

    返回 (platform_or_metricool, column_map)。若无法识别则返回 (None, None)。
    Metricool 优先级最高，因为它有独占的 Account/Network 标记。
    """
    if _METRICOOL_REQUIRED.issubset(columns):
        return "metricool", _METRICOOL_COLUMN_MAP

    # 找包含字段最多的匹配，按指纹列与实际列的交集大小排序
    best: tuple[str, dict[str, str], int] | None = None
    for name, required, mapping in _PLATFORM_FINGERPRINTS:
        if required.issubset(columns):
            score = len(required)
            if best is None or score > best[2]:
                best = (name, mapping, score)
    if best is None:
        return None, None
    return best[0], best[1]


def _ensure_standard_shape(df: pd.DataFrame, platform: str | None) -> pd.DataFrame:
    """对齐到标准列结构：补齐缺失列、转换类型、限定列顺序。"""
    out = df.copy()

    # 日期列：缺失补 NaT，已有则转换为 datetime
    if "date" not in out.columns:
        out["date"] = pd.NaT
    else:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")

    # 平台列
    if platform is not None:
        out["platform"] = platform
    elif "platform" not in out.columns:
        out["platform"] = ""

    # 数值列：缺失列补 float NaN，已有列强制为 float（统一 dtype，便于后续 concat）
    for col in STANDARD_NUMERIC_COLS:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")

    return out[STANDARD_COLS]


def load_csv(path: str | Path) -> pd.DataFrame:
    """读取单个 CSV 并映射到标准字段。

    无法识别来源、空文件、解析失败时，发出警告并返回空 DataFrame（保持标准列结构）。
    """
    path = Path(path)
    empty = _ensure_standard_shape(pd.DataFrame(), platform=None)

    try:
        raw = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        _emit_warning(f"文件为空，已跳过：{path}")
        return empty
    except Exception as exc:  # noqa: BLE001 - 把 pandas 抛的各种解析错误统一降级为警告
        _emit_warning(f"读取失败，已跳过：{path}（{type(exc).__name__}: {exc}）")
        return empty

    if raw.empty:
        _emit_warning(f"文件无数据行，已跳过：{path}")
        return empty

    source, column_map = _identify_source(set(raw.columns))
    if source is None:
        _emit_warning(
            f"无法识别 CSV 来源，已跳过：{path}\n  实际表头：{list(raw.columns)}"
        )
        return empty

    if source == "metricool":
        # Metricool：保留所有可映射列；platform 从 Network 列推断
        renamed = raw.rename(columns=column_map)
        if "Network" in raw.columns:
            renamed["platform"] = (
                raw["Network"].astype(str).str.strip().str.lower().map(_METRICOOL_NETWORK_MAP).fillna("")
            )
        # 标准化
        df = _ensure_standard_shape(renamed, platform=None)
    else:
        # 平台原生：按映射重命名，platform 由指纹决定
        renamed = raw.rename(columns=column_map)
        df = _ensure_standard_shape(renamed, platform=source)

    if df["date"].isna().all():
        _emit_warning(f"所有日期解析失败，已跳过：{path}")
        return empty

    # 丢弃日期无效的行
    df = df.dropna(subset=["date"]).reset_index(drop=True)
    return df


def load_all_data(directory: str | Path) -> pd.DataFrame:
    """读取目录下所有 .csv 文件并合并。返回标准列结构的 DataFrame。

    若目录不存在或无任何可识别文件，返回空 DataFrame（仍保持标准列结构）。
    """
    directory = Path(directory)
    empty = _ensure_standard_shape(pd.DataFrame(), platform=None)

    if not directory.exists():
        _emit_warning(f"数据目录不存在：{directory}")
        return empty

    files = sorted(p for p in directory.glob("*.csv") if p.is_file())
    if not files:
        _emit_warning(f"数据目录无 CSV 文件：{directory}")
        return empty

    frames = [load_csv(p) for p in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return empty

    combined = pd.concat(frames, ignore_index=True, sort=False)
    # 同一平台同一日期可能在多个文件中出现（例如 Metricool 与原生重叠），按 (platform, date) 取最后一条
    combined = combined.sort_values(["platform", "date"]).drop_duplicates(
        subset=["platform", "date"], keep="last"
    ).reset_index(drop=True)
    return combined
