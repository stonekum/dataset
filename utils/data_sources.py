"""数据源统一入口（F09 + F10）。

抽象 `get_active_dataframe()` 屏蔽具体来源，让 pages 不需要知道数据从本地 CSV、用户上传、还是
Google Sheets 来。优先级：

    上传数据（session 内存） > Google Sheets（若已配置）> 本地真实 CSV (data/) > 本地示例 CSV (data/samples/)

数据流：原始 DataFrame → data_cleaner.clean → metrics.enrich_dataframe，结果用 st.cache_data 缓存。

F10 实现说明：
- 通过 Streamlit Secrets 注入凭据（不写入仓库）
- 表格约定：第一个 worksheet（或 secrets 指定的 worksheet_name）使用标准列结构
  date, platform, followers, impressions, reach, likes, comments, shares, saves, posts_count
- 上传入口可选「同步到 Google Sheets」：把 session_state 里的 DataFrame 写回云端
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd
import streamlit as st

from utils.data_cleaner import clean
from utils.data_loader import (
    STANDARD_COLS,
    STANDARD_NUMERIC_COLS,
    _ensure_standard_shape,
    load_all_data,
    load_uploaded_files,
)
from utils.metrics import enrich_dataframe

logger = logging.getLogger(__name__)

# session_state key
_UPLOADED_KEY = "uploaded_dataframe"
_UPLOADED_META_KEY = "uploaded_meta"

# 默认本地数据目录优先级（先真实运营数据，再示例数据）
_LOCAL_FALLBACK_DIRS = ("data", "data/samples")

# Streamlit Secrets 区段名
_GSHEETS_SECTION = "gsheets"


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


# ---------- Google Sheets (F10) ----------


class GoogleSheetsConfigError(RuntimeError):
    """Secrets 缺失或格式错误时抛出。"""


def _read_gsheets_config() -> dict | None:
    """从 Streamlit Secrets 读 [gsheets] 区段；缺失或读取异常时返回 None。

    期望结构：
        [gsheets]
        spreadsheet_url = "https://docs.google.com/spreadsheets/d/.../edit"
        worksheet_name = "data"   # 可选，默认取第一个 worksheet
        [gsheets.service_account]
        type = "service_account"
        project_id = "..."
        ...
    """
    try:
        if _GSHEETS_SECTION not in st.secrets:
            return None
        cfg = dict(st.secrets[_GSHEETS_SECTION])
    except Exception:  # noqa: BLE001 - secrets 文件可能不存在
        return None
    if not cfg.get("service_account"):
        return None
    if not (cfg.get("spreadsheet_url") or cfg.get("spreadsheet_id")):
        return None
    return cfg


def is_gsheets_configured() -> bool:
    """Secrets 是否已配置 Google Sheets 凭据。供 UI 判断是否显示同步入口。"""
    return _read_gsheets_config() is not None


@dataclass
class GoogleSheetsSource:
    """通过 gspread + service account 读取/写入一份共享 Google Sheet。

    使用 Streamlit Secrets 注入凭据：
        st.secrets["gsheets"]["service_account"]   → dict（service account JSON 内容）
        st.secrets["gsheets"]["spreadsheet_url"]   → str（或 spreadsheet_id）
        st.secrets["gsheets"]["worksheet_name"]    → str（可选）

    Sheet 表头必须使用标准列名（date / platform / followers / impressions / reach /
    likes / comments / shares / saves / posts_count）。
    """

    name: str = "Google Sheets"

    def _client(self):
        cfg = _read_gsheets_config()
        if cfg is None:
            raise GoogleSheetsConfigError(
                "未在 .streamlit/secrets.toml 中配置 [gsheets] 区段（spreadsheet_url + service_account）"
            )
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as exc:  # pragma: no cover - 依赖未装
            raise GoogleSheetsConfigError(
                "缺少依赖：pip install gspread google-auth"
            ) from exc

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(
            dict(cfg["service_account"]), scopes=scopes
        )
        return gspread.authorize(creds), cfg

    def _open_worksheet(self):
        gc, cfg = self._client()
        if cfg.get("spreadsheet_url"):
            sh = gc.open_by_url(cfg["spreadsheet_url"])
        else:
            sh = gc.open_by_key(cfg["spreadsheet_id"])
        ws_name = cfg.get("worksheet_name")
        if ws_name:
            return sh.worksheet(ws_name)
        return sh.sheet1

    def load(self) -> pd.DataFrame:
        """从 Sheet 读取并映射为标准列结构。失败抛 GoogleSheetsConfigError。"""
        ws = self._open_worksheet()
        records = ws.get_all_records()
        if not records:
            return _ensure_standard_shape(pd.DataFrame(), platform=None)
        raw = pd.DataFrame(records)
        # 若用户给的是 Metricool/原生导出表头，复用 load_csv 逻辑会更复杂；
        # F10 约定 Sheet 直接用标准列名（运营同事可从模板复制）
        return _ensure_standard_shape(raw, platform=None)

    def write(self, df: pd.DataFrame) -> int:
        """把 DataFrame 写回 Sheet（整表替换）。返回写入行数。"""
        ws = self._open_worksheet()
        if df.empty:
            ws.clear()
            ws.update([STANDARD_COLS])
            return 0
        out = df[STANDARD_COLS].copy()
        # date → ISO 字符串；NaN → 空字符串（Sheets 不接受 NaN）
        out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        for col in STANDARD_NUMERIC_COLS:
            out[col] = out[col].replace({np.nan: ""})
        out = out.fillna("")
        values = [STANDARD_COLS] + out.astype(object).values.tolist()
        ws.clear()
        ws.update(values)
        return len(out)


# ---------- 上传数据（session_state）----------

def store_uploaded_dataframe(df: pd.DataFrame, meta: dict | None = None) -> None:
    """把上传并已识别的 DataFrame 放入 session_state，供所有页面使用。"""
    st.session_state[_UPLOADED_KEY] = df
    st.session_state[_UPLOADED_META_KEY] = meta or {}


def clear_uploaded_dataframe() -> None:
    """清除会话内上传数据，使下游回落到本地 CSV / Google Sheets。"""
    st.session_state.pop(_UPLOADED_KEY, None)
    st.session_state.pop(_UPLOADED_META_KEY, None)


def get_uploaded_meta() -> dict:
    """获取上传数据的元信息（行数、平台、时间范围等），无上传则空 dict。"""
    return st.session_state.get(_UPLOADED_META_KEY, {})


def has_uploaded_dataframe() -> bool:
    df = st.session_state.get(_UPLOADED_KEY)
    return isinstance(df, pd.DataFrame) and not df.empty


# ---------- 公共入口 ----------


def _try_load_gsheets() -> pd.DataFrame | None:
    """尝试从 Google Sheets 加载；未配置或失败则返回 None（不打断 app）。

    用 BaseException 兜底是因为底层 cryptography 在某些环境里会以 Rust
    PanicException 形式抛出，那不属于 Exception。
    """
    if not is_gsheets_configured():
        return None
    try:
        df = GoogleSheetsSource().load()
    except GoogleSheetsConfigError as exc:
        logger.warning("Google Sheets 配置错误：%s", exc)
        return None
    except BaseException as exc:  # noqa: BLE001 - 含 PanicException 等非 Exception 类型
        logger.warning("Google Sheets 读取失败：%s: %s", type(exc).__name__, exc)
        try:
            st.warning(f"Google Sheets 读取失败，已回落到本地数据：{exc}")
        except BaseException:  # noqa: BLE001
            pass
        return None
    return df if not df.empty else None


def _resolve_source() -> tuple[pd.DataFrame, str]:
    """按优先级解析当前活动数据源，返回 (raw_df, source_label)。"""
    if has_uploaded_dataframe():
        return st.session_state[_UPLOADED_KEY], "本次上传"

    gs_df = _try_load_gsheets()
    if gs_df is not None:
        return gs_df, "Google Sheets"

    for directory in _LOCAL_FALLBACK_DIRS:
        df = LocalCSVSource(directory).load()
        if not df.empty:
            return df, f"本地 CSV ({directory})"

    return load_all_data("data/samples"), "本地 CSV (data/samples, 空)"


@st.cache_data(show_spinner="加载数据中…")
def _enrich_cached(df: pd.DataFrame, _cache_key: str) -> pd.DataFrame:
    """对清洗 + 衍生做缓存。`_cache_key` 触发缓存失效（上传内容变化时切换 key）。"""
    if df.empty:
        return df
    return enrich_dataframe(clean(df))


def get_active_dataframe() -> tuple[pd.DataFrame, str]:
    """统一入口：返回 (已清洗并衍生过的 DataFrame, 来源标签)。

    pages 调用此函数即可，无需关心数据是上传、Google Sheets 还是本地。
    """
    raw, label = _resolve_source()
    cache_key = label
    if label == "本次上传":
        meta = get_uploaded_meta()
        cache_key = f"upload::{meta.get('fingerprint', '')}"
    df = _enrich_cached(raw, cache_key)
    return df, label
