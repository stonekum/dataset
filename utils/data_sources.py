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

# Sheet 写入额外保留的列（不在 STANDARD_COLS 里但有持久化价值）
# - follower_growth: API 源头给出的当日净增（YouTube subscribersGained-Lost、
#   IG insights.follower_count）。CSV 没有，但 API 持久化下来后 enrich_dataframe
#   会优先用它而不是 followers shift（见 utils/metrics.py 的 follower_growth 逻辑）
_SHEET_EXTRA_COLS = ["follower_growth"]
_SHEET_ALL_COLS = STANDARD_COLS + _SHEET_EXTRA_COLS

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

    def write(self, df: pd.DataFrame, mode: str = "merge") -> dict:
        """把 DataFrame 写回 Sheet。

        Args:
            df: 待写入数据（标准列结构）
            mode: "merge" — 与现有数据按 (platform, date) 合并，新值覆盖旧值（默认）；
                  "replace" — 清空 Sheet 后整表替换

        Returns:
            dict 含 mode/written/added/updated/total，便于 UI 展示明细
        """
        ws = self._open_worksheet()

        # 工具：把任意 df 对齐到 Sheet 的完整列结构（STANDARD_COLS + 额外列）
        def _align_to_sheet_cols(src: pd.DataFrame) -> pd.DataFrame:
            out = src.copy()
            for col in _SHEET_ALL_COLS:
                if col not in out.columns:
                    out[col] = np.nan
            return out[_SHEET_ALL_COLS]

        if mode == "replace":
            if df.empty:
                ws.clear()
                ws.update([_SHEET_ALL_COLS])
                return {"mode": "replace", "written": 0, "added": 0, "updated": 0, "total": 0}
            merged = _align_to_sheet_cols(df)
            added = len(merged)
            updated = 0
        else:
            # merge 模式：先读现有，再 upsert
            try:
                existing_records = ws.get_all_records()
            except Exception:  # noqa: BLE001
                existing_records = []
            existing = (
                _ensure_standard_shape(pd.DataFrame(existing_records), platform=None)
                if existing_records
                else _ensure_standard_shape(pd.DataFrame(), platform=None)
            )

            new_df = _align_to_sheet_cols(df)
            existing = _align_to_sheet_cols(existing)
            new_df["date"] = pd.to_datetime(new_df["date"], errors="coerce")
            existing["date"] = pd.to_datetime(existing["date"], errors="coerce")

            # 计算 added / updated
            existing_keys = set(
                zip(existing["platform"].astype(str), existing["date"].dt.strftime("%Y-%m-%d"))
            ) if not existing.empty else set()
            new_keys = set(
                zip(new_df["platform"].astype(str), new_df["date"].dt.strftime("%Y-%m-%d"))
            )
            added = len(new_keys - existing_keys)
            updated = len(new_keys & existing_keys)

            # Cell-level merge（不是整行替换）：
            # 新数据非空的格子覆盖旧值；新数据 NaN 的格子保留旧值。
            # 避免场景：旧行从 sample CSV 同步过来 followers=111712，新行从 Meta
            # 回填 followers=NaN（因为 Meta 把 page_fans 砍了），整行替换会把
            # 111712 清成空。combine_first 语义：caller 中非空的留，为空的用
            # other 同位置填。结果是 union of indexes，旧行如果新数据没覆盖也
            # 会出现在结果里（不丢历史）。
            if existing.empty:
                merged = new_df.copy()
            else:
                new_indexed = new_df.set_index(["platform", "date"])
                existing_indexed = existing.set_index(["platform", "date"])
                merged = new_indexed.combine_first(existing_indexed).reset_index()
            merged = merged.sort_values(["platform", "date"]).reset_index(drop=True)

        # 序列化：date → ISO 字符串；NaN → 空字符串
        merged["date"] = pd.to_datetime(merged["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        for col in STANDARD_NUMERIC_COLS + _SHEET_EXTRA_COLS:
            if col in merged.columns:
                merged[col] = merged[col].replace({np.nan: ""})
        merged = merged.fillna("")
        values = [_SHEET_ALL_COLS] + merged.astype(object).values.tolist()
        ws.clear()
        ws.update(values)
        return {
            "mode": mode,
            "written": len(merged),
            "added": added,
            "updated": updated,
            "total": len(merged),
        }


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


def load_sheets_into_session() -> bool:
    """如果 Sheets 已配置且 session 内无上传数据，从 Sheets 加载数据到 session_state。

    返回 True 表示成功加载了数据，False 表示未配置 / 加载失败 / 原本就有数据。
    用于 API 拉取时确保已有数据不因 session 重启而丢失。
    """
    if has_uploaded_dataframe():
        return False
    if not is_gsheets_configured():
        return False
    try:
        source = GoogleSheetsSource()
        df = source.load()
        if df.empty:
            return False
        store_uploaded_dataframe(df, {
            "rows": len(df),
            "platforms": sorted(df["platform"].dropna().unique().tolist()),
            "date_start": df["date"].min().date() if not df.empty else None,
            "date_end": df["date"].max().date() if not df.empty else None,
            "files": ["（从 Google Sheets 自动加载）"],
        })
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("从 Sheets 自动加载失败：%s", exc)
        return False



def _try_load_gsheets() -> pd.DataFrame | None:
    """尝试从 Google Sheets 加载；未配置或失败则返回 None（不打断 app）。

    用 BaseException 兜底是因为底层 cryptography 在某些环境里会以 Rust
    PanicException 形式抛出，那不属于 Exception。

    失败原因（含"读到空表"）会通过 st.warning 显示在页面顶部，方便快速排查
    "Sheet 已配置但 Cloud 看不到数据" 这类问题（之前只走 logger.warning，
    Cloud 默认级别下不显示，问题排查困难）。
    """
    if not is_gsheets_configured():
        return None
    try:
        df = GoogleSheetsSource().load()
    except GoogleSheetsConfigError as exc:
        logger.warning("Google Sheets 配置错误：%s", exc)
        try:
            st.warning(f"⚠️ Google Sheets 配置错误：{exc}")
        except BaseException:  # noqa: BLE001
            pass
        return None
    except BaseException as exc:  # noqa: BLE001 - 含 PanicException 等非 Exception 类型
        logger.warning("Google Sheets 读取失败：%s: %s", type(exc).__name__, exc)
        try:
            st.warning(
                f"⚠️ Google Sheets 读取失败（{type(exc).__name__}），"
                f"已回落到本地数据：{exc}"
            )
        except BaseException:  # noqa: BLE001
            pass
        return None
    if df.empty:
        # 配置正确但读到空 worksheet —— 经常是 worksheet_name 对不上、
        # 或共享给的 service account 看到的是另一个空 tab
        try:
            st.warning(
                "⚠️ Google Sheets 连上了但读到 0 行。检查："
                "(a) worksheet_name 是否就是 Sheet 底部那个 tab 名（区分大小写）；"
                "(b) spreadsheet_url 是否就是写入数据用的那个 Sheet；"
                "(c) service account 邮箱是否真的被 Share 进去了。"
            )
        except BaseException:  # noqa: BLE001
            pass
        return None
    return df


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
    """对清洗 + 衍生做缓存。`_cache_key` 触发缓存失效（内容变化时切换 key）。"""
    if df.empty:
        return df
    return enrich_dataframe(clean(df))


def _content_hash(df: pd.DataFrame) -> str:
    """对 DataFrame 内容做 hash，作为 cache key 的一部分。

    比起单纯用文件名/label，避免同名不同内容的 CSV 命中旧缓存（Tier 2.3）。
    """
    import hashlib
    if df.empty:
        return "empty"
    try:
        h = hashlib.md5(pd.util.hash_pandas_object(df, index=False).values.tobytes())
        return h.hexdigest()[:12]
    except Exception:  # noqa: BLE001
        # 万一 hash 失败（含不可哈希类型），退化到行数 + 列名签名
        return f"{len(df)}:{hash(tuple(df.columns))}"


def get_active_dataframe() -> tuple[pd.DataFrame, str]:
    """统一入口：返回 (已清洗并衍生过的 DataFrame, 来源标签)。

    pages 调用此函数即可，无需关心数据是上传、Google Sheets 还是本地。
    """
    raw, label = _resolve_source()
    # cache key 始终拼上内容 hash：上传 / Sheets / 本地 CSV 都能正确失效
    cache_key = f"{label}::{_content_hash(raw)}"
    df = _enrich_cached(raw, cache_key)
    return df, label
