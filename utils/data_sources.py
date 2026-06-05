"""数据源统一入口（F09 + F10）。

抽象 `get_active_dataframe()` 屏蔽具体来源，让 pages 不需要知道数据从本地 CSV、用户上传、还是
Google Sheets 来。优先级：

    上传数据（session 内存） > Google Sheets（唯一可信源，若已配置）
        > 本地真实 CSV (data/) > 单份标准化示例 demo (data/samples/demo_all_platforms.csv)

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
from pathlib import Path
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
    load_csv,
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


def cell_merge(
    new_df: pd.DataFrame,
    existing_df: pd.DataFrame,
    keys: tuple[str, ...] = ("platform", "date"),
) -> pd.DataFrame:
    """按 keys 做 cell-level upsert（而非整行替换）。

    语义：对每个 (platform, date)：
      - new_df 里非空的格子覆盖 existing 的同位置；
      - new_df 里是 NaN 的格子，保留 existing 的旧值；
      - 只在 existing 里有、new 里没有的行，原样保留（不丢历史）。

    这是 backfill 写 Sheet、API 拉取并入 session、手动数据叠加 三处统一使用的
    合并语义。用整行替换（concat + drop_duplicates）会让一行里的 NaN 把旧的
    非空值清掉——例如 Meta 回填的 followers=NaN 覆盖掉手动收集的真实 followers。

    返回结果列顺序不保证（combine_first 会把 keys 提到前面），调用方自行 reindex。
    """
    if existing_df is None or existing_df.empty:
        return new_df.copy()
    if new_df is None or new_df.empty:
        return existing_df.copy()
    new_idx = new_df.set_index(list(keys))
    old_idx = existing_df.set_index(list(keys))
    return new_idx.combine_first(old_idx).reset_index()

# 本地兜底（仅在「无上传 + 无 Sheet」时用）：
# - 先读真实运营数据目录 data/（gitignore，本地无 Sheet 时手动放 CSV 的地方，通常为空）
# - 再读**单份**标准化 demo（不再全量拼接 data/samples 下所有 CSV——原生格式、分月、
#   手动真实数据混在一起语义互相矛盾，正是整顿要根治的污染源；见决策 #2）
_REAL_LOCAL_DIR = "data"
_DEMO_FILE = Path("data/samples/demo_all_platforms.csv")

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

            # 自愈：丢弃 existing 中 date 无法解析成日期（NaT）的脏行。
            # 典型来源是历史上某次列错位 bug 把 platform 值（如 "facebook"）写进了
            # date 列，get_all_records 按表头读回来后 date 列就是 "facebook" → NaT。
            # 这种行无法按 (platform, date) 合并，留着只会污染结果；既然下面要
            # ws.clear() 整表重写，这里 drop 掉等于顺手把 Sheet 里的脏数据清理干净。
            if not existing.empty:
                n_before = len(existing)
                existing = existing[existing["date"].notna()].copy()
                n_dropped = n_before - len(existing)
                if n_dropped:
                    logger.warning(
                        "merge: 丢弃 %d 行 date 无法解析的脏数据（疑似历史列错位残留）",
                        n_dropped,
                    )

            # 计算 added / updated
            existing_keys = set(
                zip(existing["platform"].astype(str), existing["date"].dt.strftime("%Y-%m-%d"))
            ) if not existing.empty else set()
            new_keys = set(
                zip(new_df["platform"].astype(str), new_df["date"].dt.strftime("%Y-%m-%d"))
            )
            added = len(new_keys - existing_keys)
            updated = len(new_keys & existing_keys)

            # Cell-level merge（见模块级 cell_merge）：新非空覆盖旧，新 NaN 保留旧
            merged = cell_merge(new_df, existing)
            merged = merged.sort_values(["platform", "date"]).reset_index(drop=True)

        # 关键：reset_index() 会把 index 列（platform, date）按 index 顺序插到最前，
        # 导致列序变成 [platform, date, ...]，而写入用的表头是 _SHEET_ALL_COLS
        # （date 在前）。不强制对齐回标准列顺序，Sheet 表头就会和数据错位
        # （date 表头底下显示 platform 值）。
        merged = merged[_SHEET_ALL_COLS]

        # 序列化：date → ISO 字符串；NaN → 空字符串
        merged["date"] = pd.to_datetime(merged["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        for col in STANDARD_NUMERIC_COLS + _SHEET_EXTRA_COLS:
            if col in merged.columns:
                merged[col] = merged[col].replace({np.nan: ""})
        merged = merged.fillna("")
        # 表头从 merged.columns 取（而非常量 _SHEET_ALL_COLS），保证表头与数据
        # 物理同源：表头行和每条数据行都来自同一个 merged，列顺序天然一致。
        # 哪怕上游某个改动意外打乱了 merged 的列顺序，表头也会跟着一起变，
        # date 表头底下永远是 date 值，绝不会再出现"date 列显示 facebook"的错位。
        # （上面的 merged[_SHEET_ALL_COLS] 仍负责把顺序固定成标准顺序。）
        values = [merged.columns.tolist()] + merged.astype(object).values.tolist()
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
        # 区分"完全没配"和"配了一半"：如果 [gsheets] section 存在但
        # is_configured 返回 False，那是字段缺失/嵌套错；说出来用户才能修
        try:
            section_present = _GSHEETS_SECTION in st.secrets
        except Exception:  # noqa: BLE001
            section_present = False
        if section_present:
            try:
                cfg = dict(st.secrets[_GSHEETS_SECTION])
                missing = []
                if not cfg.get("service_account"):
                    missing.append("[gsheets.service_account] 子 table（必须是嵌套 table，不是扁平字段）")
                if not (cfg.get("spreadsheet_url") or cfg.get("spreadsheet_id")):
                    missing.append("spreadsheet_url 或 spreadsheet_id")
                if missing:
                    st.warning(
                        "⚠️ Streamlit Secrets 里的 [gsheets] 配置不完整，"
                        f"缺：{'; '.join(missing)}。参见 .streamlit/secrets.toml.example。"
                    )
            except BaseException:  # noqa: BLE001
                pass
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

    # 临时诊断（"配上 gsheets 就看不到任何数据"问题排查用）：
    # 看 GSheets 读到的 df 是否被下游 clean() 因 NaT 日期 dropna 清空
    try:
        nat_count = int(df["date"].isna().sum()) if "date" in df.columns else len(df)
        if nat_count == len(df) and len(df) > 0:
            # 全部 date 是 NaT —— clean() 会把它们全 drop，最终页面看空
            sample_dates = df["date"].head(3).tolist() if "date" in df.columns else []
            sample_raw = (
                df["date"].astype(str).head(3).tolist() if "date" in df.columns else []
            )
            st.warning(
                f"⚠️ GSheets 读到 {len(df)} 行，但 date 列**全部解析为 NaT**，"
                f"会被 clean() 全部丢弃 → 最终页面空。"
                f"raw date 前 3 个：{sample_raw}。"
                f"如果不是 'YYYY-MM-DD' 格式，请去 Sheet 选中 date 列 → "
                f"Format → Number → Plain text，再手动改回 ISO 格式。"
            )
        elif nat_count > 0:
            st.info(
                f"🔍 GSheets 读到 {len(df)} 行；{nat_count} 行的 date 解析失败"
                f"（不影响其他行）。"
            )
    except BaseException:  # noqa: BLE001
        pass

    return df


def _resolve_source() -> tuple[pd.DataFrame, str]:
    """按优先级解析当前活动数据源，返回 (raw_df, source_label)。

    优先级：上传 session > Google Sheet（唯一可信源）> 本地真实 CSV (data/) >
    单份示例 demo (data/samples/demo_all_platforms.csv)。
    """
    if has_uploaded_dataframe():
        return st.session_state[_UPLOADED_KEY], "本次上传"

    gs_df = _try_load_gsheets()
    if gs_df is not None:
        return gs_df, "Google Sheets"

    # 本地真实运营数据（data/，gitignore，通常为空）
    real = LocalCSVSource(_REAL_LOCAL_DIR).load()
    if not real.empty:
        return real, f"本地 CSV ({_REAL_LOCAL_DIR})"

    # 示例兜底：仅读一份标准化 demo，不再全量拼接 data/samples
    if _DEMO_FILE.exists():
        demo = load_csv(_DEMO_FILE)
        if not demo.empty:
            return demo, "示例数据 (demo)"

    # demo 尚未生成时的兼容兜底（保持旧行为，避免完全空白）：
    # 运行 `python generate_sample_data.py` 可生成 demo 文件。
    return load_all_data("data/samples"), "本地 CSV (data/samples)"


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
