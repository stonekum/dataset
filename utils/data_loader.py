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
from typing import IO, Iterable

import numpy as np
import pandas as pd

from utils.logging import emit_warning as _emit_warning

logger = logging.getLogger(__name__)

# ============================================================
# 标准列字段语义表（Tier 2.4 文档化）
#
# 任何数据源（CSV / API / 手动录入）经过 _ensure_standard_shape 后都必须符合
# 这个列结构。每个字段的语义和各平台映射：
#
# | 字段名          | 类型     | 来源              | 平台差异说明                                            |
# |----------------|---------|-------------------|--------------------------------------------------------|
# | date           | date    | CSV/API           | 必填，统一为 datetime64[ns]                            |
# | platform       | str     | 文件名/识别       | 必填，小写：instagram/tiktok/youtube/x/facebook/linkedin|
# | followers      | int     | CSV/API           | 当日粉丝快照总数。YouTube/IG/TikTok 是 API 当日快照；     |
# |                |         |                   | LinkedIn 是 totalFollowersCount。                       |
# | impressions    | int     | CSV/API           | 日曝光。Meta=page_impressions；YouTube=views；           |
# |                |         |                   | TikTok=video views 聚合。                              |
# | reach          | int     | CSV               | 触达人数。仅 Instagram + Facebook + LinkedIn 提供。     |
# | likes          | int     | CSV/API           | 日点赞。⚠️ Meta 的 `likes` 实际来自                     |
# |                |         |                   | `page_post_engagements`（综合互动），不是纯赞数。       |
# | comments       | int     | CSV/API           | 日评论数。                                             |
# | shares         | int     | CSV/API           | 日分享/转发数。X 平台叫 Retweets，TikTok 叫 Shares。    |
# | saves          | int     | CSV               | 仅 Instagram 提供，其他平台为 NaN。                    |
# | posts_count    | int     | CSV/API           | 日发帖数。IG 来自 media 列表聚合。                      |
#
# 衍生字段（在 utils/metrics.enrich_dataframe 计算，不在这里）：
#   engagement_rate, follower_growth, follower_growth_rate
#
# 各平台的特殊聚合（请勿在 _ensure_standard_shape 之外的地方再调整）：
#   - LinkedIn follower_growth = organic + paid（两个 API 字段相加）
#   - TikTok 只有当日快照，没有历史每日时间序列
#   - Meta page_post_engagements 是 likes+comments+shares 综合值
# ============================================================
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




def _identify_source(columns: set[str]) -> tuple[str | None, dict[str, str] | None]:
    """根据列集合识别 CSV 来源。

    返回 (platform_or_metricool, column_map)。若无法识别则返回 (None, None)。
    Metricool 优先级最高，因为它有独占的 Account/Network 标记。
    "standard" 表示已经是标准列结构的 CSV（如本项目导出的合并文件），
    platform 列直接保留不覆盖。
    """
    # 已经是标准结构（小写 date + platform 列）→ 直接采纳，platform 不覆盖
    if {"date", "platform"}.issubset(columns):
        return "standard", None

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
    """对齐到标准列结构：补齐缺失列、转换类型、限定列顺序。

    可选透传列：若源数据已经提供 `follower_growth`（典型来自 YouTube /
    LinkedIn API 的"当日订阅净增"），会强制转 float64 后保留下来，
    供下游 `enrich_dataframe` 优先使用。不在白名单内的额外列仍然被丢弃，
    避免污染标准结构。
    """
    out = df.copy()

    # 日期列：缺失补 NaT；已有则转换为 datetime。
    # 优先按 ISO-8601 解析（GoogleSheetsSource.write 写出来就是这格式，
    # CSV 也大多是），失败的格子再走慢但通用的 dateutil 推断。这样
    # 标准路径不再触发 pandas 的 "Could not infer format" UserWarning。
    if "date" not in out.columns:
        out["date"] = pd.NaT
    else:
        iso_parsed = pd.to_datetime(out["date"], format="ISO8601", errors="coerce")
        if iso_parsed.isna().any():
            # 有未匹配 ISO 的格子（典型场景：手上传非标准格式 CSV）→ 对剩余
            # 行 fallback 到推断；用 mask 避免对已 parse 的格子再跑一次
            mask = iso_parsed.isna() & out["date"].notna()
            if mask.any():
                fallback = pd.to_datetime(out.loc[mask, "date"], errors="coerce")
                iso_parsed.loc[mask] = fallback
        out["date"] = iso_parsed

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

    # 透传 API 直接给出的 follower_growth（不进 STANDARD_COLS，避免污染 CSV 路径的契约）
    extras: list[str] = []
    if "follower_growth" in out.columns:
        out["follower_growth"] = pd.to_numeric(
            out["follower_growth"], errors="coerce"
        ).astype("float64")
        extras.append("follower_growth")

    return out[STANDARD_COLS + extras]


def load_csv(source: "str | Path | IO[bytes] | IO[str]", label: str | None = None) -> pd.DataFrame:
    """读取单个 CSV 并映射到标准字段。

    `source` 可以是文件路径（str/Path）或 file-like 对象（如 Streamlit 的 UploadedFile）。
    `label` 用于警告信息中标识来源；省略时用 path 名或 file-like 的 .name。

    无法识别来源、空文件、解析失败时，发出警告并返回空 DataFrame（保持标准列结构）。
    """
    # 解析显示标签
    if label is None:
        if isinstance(source, (str, Path)):
            label = str(source)
        else:
            label = getattr(source, "name", "<uploaded>")

    empty = _ensure_standard_shape(pd.DataFrame(), platform=None)

    # 对 file-like 对象做读前重置（Streamlit UploadedFile 多次读取需要 seek(0)）
    if not isinstance(source, (str, Path)):
        try:
            source.seek(0)
        except (AttributeError, OSError):
            pass

    read_target: str | Path | IO = Path(source) if isinstance(source, (str, Path)) else source

    try:
        raw = pd.read_csv(read_target)
    except pd.errors.EmptyDataError:
        _emit_warning(f"文件为空，已跳过：{label}")
        return empty
    except Exception as exc:  # noqa: BLE001 - 把 pandas 抛的各种解析错误统一降级为警告
        _emit_warning(f"读取失败，已跳过：{label}（{type(exc).__name__}: {exc}）")
        return empty

    if raw.empty:
        _emit_warning(f"文件无数据行，已跳过：{label}")
        return empty

    source_kind, column_map = _identify_source(set(raw.columns))
    if source_kind is None:
        _emit_warning(
            f"无法识别 CSV 来源，已跳过：{label}\n  实际表头：{list(raw.columns)}"
        )
        return empty

    if source_kind == "standard":
        # 已经是标准结构（含 platform 列），保留原 platform 不覆盖
        df = _ensure_standard_shape(raw, platform=None)
    elif source_kind == "metricool":
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
        df = _ensure_standard_shape(renamed, platform=source_kind)

    if df["date"].isna().all():
        _emit_warning(f"所有日期解析失败，已跳过：{label}")
        return empty

    # 丢弃日期无效的行
    df = df.dropna(subset=["date"]).reset_index(drop=True)
    return df


def identify_csv_source(source: "str | Path | IO[bytes] | IO[str]") -> tuple[str | None, list[str]]:
    """轻量检测 CSV 来源，不做完整加载。

    Returns:
        (source_kind, columns)：source_kind 为 "metricool" / 平台名（小写）/ None；
        columns 为实际表头（识别失败时仍返回，供 UI 展示）
    """
    cols = peek_csv_columns(source)
    if not cols:
        return None, []
    kind, _ = _identify_source(set(cols))
    return kind, cols


def peek_csv_columns(source: "str | Path | IO[bytes] | IO[str]") -> list[str]:
    """读取 CSV 表头列表（仅第一行），不做完整加载。失败返回空列表。

    用于 UI 在识别失败时给用户展示原始列名以做手动映射。
    """
    if not isinstance(source, (str, Path)):
        try:
            source.seek(0)
        except (AttributeError, OSError):
            pass
    try:
        head = pd.read_csv(source, nrows=0)
        return list(head.columns)
    except Exception:  # noqa: BLE001
        return []
    finally:
        if not isinstance(source, (str, Path)):
            try:
                source.seek(0)
            except (AttributeError, OSError):
                pass


def load_csv_with_mapping(
    source: "str | Path | IO[bytes] | IO[str]",
    platform: str,
    column_map: dict[str, str],
    label: str | None = None,
) -> pd.DataFrame:
    """以用户指定的 platform + column_map 加载 CSV，绕过自动指纹识别。

    Args:
        source: 文件路径或 file-like
        platform: 标准平台名（instagram/tiktok/youtube/x/facebook/linkedin）
        column_map: {原始列名: 标准列名}；标准列名须在 STANDARD_COLS 内
        label: 警告信息中的显示名

    Returns:
        符合标准列结构的 DataFrame；解析失败返回空 DataFrame。
    """
    if label is None:
        label = str(source) if isinstance(source, (str, Path)) else getattr(source, "name", "<uploaded>")

    empty = _ensure_standard_shape(pd.DataFrame(), platform=None)

    if not isinstance(source, (str, Path)):
        try:
            source.seek(0)
        except (AttributeError, OSError):
            pass

    try:
        raw = pd.read_csv(source)
    except Exception as exc:  # noqa: BLE001
        _emit_warning(f"读取失败，已跳过：{label}（{type(exc).__name__}: {exc}）")
        return empty

    if raw.empty:
        _emit_warning(f"文件无数据行，已跳过：{label}")
        return empty

    # 只保留映射中存在的列
    effective = {src: dst for src, dst in column_map.items() if src in raw.columns and dst}
    if not effective:
        _emit_warning(f"映射中无有效列，已跳过：{label}")
        return empty

    renamed = raw.rename(columns=effective)
    df = _ensure_standard_shape(renamed, platform=platform)

    if df["date"].isna().all():
        _emit_warning(f"映射后所有日期解析失败，已跳过：{label}")
        return empty

    df = df.dropna(subset=["date"]).reset_index(drop=True)
    return df


def load_uploaded_files(files: "Iterable[IO[bytes] | IO[str]]") -> pd.DataFrame:
    """读取一组 file-like 对象（典型场景：Streamlit st.file_uploader 返回的列表）并合并。

    与 load_all_data 行为对齐：合并后按 (platform, date) 去重，保持标准列结构。
    """
    empty = _ensure_standard_shape(pd.DataFrame(), platform=None)
    frames = [load_csv(f, label=getattr(f, "name", None)) for f in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return empty
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined = combined.sort_values(["platform", "date"]).drop_duplicates(
        subset=["platform", "date"], keep="last"
    ).reset_index(drop=True)
    return combined


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
