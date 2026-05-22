"""数据源统一入口（F09）。

抽象 `get_active_dataframe()` 屏蔽具体来源，让 pages 不需要知道数据从本地 CSV、用户上传、还是未来的
Google Sheets / 平台 API 来。优先级：

    上传数据（session 内存） > 本地示例/运营 CSV > （未来：Google Sheets）

数据流：原始 DataFrame → data_cleaner.clean → metrics.enrich_dataframe，结果在 session 内缓存。

为 F10（持久化存储）预留扩展点：
- `GoogleSheetsSource`、`SQLiteSource` 等只需实现 `DataSource.load()`，并在 `get_active_dataframe` 里
  按需注册到优先级链中。
- 上传数据当前仅在 session_state 内存里（刷新即丢），后续可在 GoogleSheetsSource 上实现 "上传后写回 Sheets"
  来获得跨 session 持久化。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import IO, Iterable, Protocol

import pandas as pd
import streamlit as st

from utils.data_cleaner import clean
from utils.data_loader import load_all_data, load_uploaded_files
from utils.metrics import enrich_dataframe

# session_state key
_UPLOADED_KEY = "uploaded_dataframe"
_UPLOADED_META_KEY = "uploaded_meta"

# 默认本地数据目录优先级（先真实运营数据，再示例数据）
_LOCAL_FALLBACK_DIRS = ("data", "data/samples")


class DataSource(Protocol):
    """统一数据源接口。"""

    name: str

    def load(self) -> pd.DataFrame:  # pragma: no cover - protocol
        ...


@dataclass
class LocalCSVSource:
    """从本地目录加载 CSV。"""

    directory: str
    name: str = "本地 CSV"

    def load(self) -> pd.DataFrame:
        return load_all_data(self.directory)


@dataclass
class UploadedFilesSource:
    """从 Streamlit file_uploader 上传的文件加载。"""

    files: list  # list[UploadedFile]
    name: str = "本次上传"

    def load(self) -> pd.DataFrame:
        return load_uploaded_files(self.files)


class GoogleSheetsSource:
    """占位 — F10 实现。

    预期签名：`GoogleSheetsSource(spreadsheet_id, worksheet_name, credentials)`，
    通过 gspread + service account 读取，输出符合 data_loader 标准列结构的 DataFrame。
    """

    name = "Google Sheets"

    def load(self) -> pd.DataFrame:  # pragma: no cover - 未实现
        raise NotImplementedError("GoogleSheetsSource 将在 F10 中实现")


# ---------- 公共入口 ----------

def store_uploaded_dataframe(df: pd.DataFrame, meta: dict | None = None) -> None:
    """把上传并已识别的 DataFrame 放入 session_state，供所有页面使用。"""
    st.session_state[_UPLOADED_KEY] = df
    st.session_state[_UPLOADED_META_KEY] = meta or {}


def clear_uploaded_dataframe() -> None:
    """清除会话内上传数据，使下游回落到本地 CSV。"""
    st.session_state.pop(_UPLOADED_KEY, None)
    st.session_state.pop(_UPLOADED_META_KEY, None)


def get_uploaded_meta() -> dict:
    """获取上传数据的元信息（行数、平台、时间范围等），无上传则空 dict。"""
    return st.session_state.get(_UPLOADED_META_KEY, {})


def has_uploaded_dataframe() -> bool:
    df = st.session_state.get(_UPLOADED_KEY)
    return isinstance(df, pd.DataFrame) and not df.empty


def _resolve_source() -> tuple[pd.DataFrame, str]:
    """按优先级解析当前活动数据源，返回 (raw_df, source_label)。"""
    if has_uploaded_dataframe():
        return st.session_state[_UPLOADED_KEY], "本次上传"

    for directory in _LOCAL_FALLBACK_DIRS:
        df = LocalCSVSource(directory).load()
        if not df.empty:
            return df, f"本地 CSV ({directory})"

    # 未来：GoogleSheetsSource（启用条件留给 F10）
    return load_all_data("data/samples"), "本地 CSV (data/samples, 空)"


@st.cache_data(show_spinner="加载数据中…")
def _enrich_cached(df: pd.DataFrame, _cache_key: str) -> pd.DataFrame:
    """对清洗 + 衍生做缓存。`_cache_key` 触发缓存失效（上传内容变化时切换 key）。"""
    if df.empty:
        return df
    return enrich_dataframe(clean(df))


def get_active_dataframe() -> tuple[pd.DataFrame, str]:
    """统一入口：返回 (已清洗并衍生过的 DataFrame, 来源标签)。

    pages 调用此函数即可，无需关心数据是上传还是本地。
    """
    raw, label = _resolve_source()
    # 用上传 meta 中的指纹做缓存键；本地走相同 label
    cache_key = label
    if label == "本次上传":
        meta = get_uploaded_meta()
        cache_key = f"upload::{meta.get('fingerprint', '')}"
    df = _enrich_cached(raw, cache_key)
    return df, label
