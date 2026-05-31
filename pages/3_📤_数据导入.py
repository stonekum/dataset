"""数据导入 — 拖拽上传各平台导出 CSV / 手动录入 / 调用官方 API（F09–F15）。

整页 Tab 化（Tier 1.1）：
- 状态卡（顶部，常驻）
- 📤 上传 CSV：自动识别 + 手动列映射
- ✍️ 手动录入：data_editor 多行录入
- 🔌 API 拉取：嵌套 tabs 分平台（Meta / YouTube / LinkedIn / TikTok）
- ☁️ Sheets 同步：写回 / 拉取
- 底部：数据源优先级说明
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from utils.data_loader import (
    STANDARD_COLS,
    identify_csv_source,
    load_csv,
    load_csv_with_mapping,
)
from utils.data_sources import (
    GoogleSheetsConfigError,
    GoogleSheetsSource,
    cell_merge,
    clear_uploaded_dataframe,
    get_uploaded_meta,
    has_uploaded_dataframe,
    is_gsheets_configured,
    load_sheets_into_session,
    store_uploaded_dataframe,
)
from utils.linkedin_api import (
    LinkedInAPIError,
    LinkedInConfigError,
    LinkedInSource,
    _is_configured as _li_configured,
)
from utils.meta_graph import (
    MetaGraphAPIError,
    MetaGraphConfigError,
    MetaGraphSource,
    _is_configured as _meta_configured,
)
from utils.tiktok_api import (
    TikTokAPIError,
    TikTokConfigError,
    TikTokSource,
    _is_configured as _tt_configured,
)
from utils.youtube_api import (
    YouTubeAPIError,
    YouTubeConfigError,
    YouTubeSource,
    _is_configured as _yt_configured,
)
from utils.ui import PLATFORM_LABELS, inject_page_styles, render_hero, render_metric_availability, section
from utils.auth import require_auth

STANDARD_FIELD_LABELS = {
    "date": "日期 (date)",
    "platform": "平台 (platform)",
    "followers": "粉丝 (followers)",
    "impressions": "曝光 (impressions)",
    "reach": "触达 (reach)",
    "likes": "点赞 (likes)",
    "comments": "评论 (comments)",
    "shares": "转发 (shares)",
    "saves": "收藏 (saves)",
    "posts_count": "发帖数 (posts_count)",
}
_PLATFORM_OPTIONS = ["instagram", "tiktok", "youtube", "x", "facebook", "linkedin"]
_MANUAL_BUFFER_KEY = "manual_entries_buffer"

st.set_page_config(page_title="数据导入 - 海外社媒数据面板", page_icon="📤", layout="wide")
inject_page_styles()
require_auth()

render_hero(
    eyebrow="DATA INTAKE · 数据导入",
    title_main="多源数据，",
    title_grad="一处汇入",
    subtitle="把各平台导出的 CSV 拖进来，或直接调用官方 API；系统自动识别来源、清洗、合并。无需碰仓库，无需 GitHub。",
    meta="支持 CSV · 手动录入 · Meta / YouTube / LinkedIn / TikTok API · Google Sheets",
)

# 平台指标口径与可用性（G1/G2/G3/G4）：导入前先让用户理解各平台有哪些指标、空值=N/A
render_metric_availability()


# ============================================================
# 通用工具
# ============================================================

def _merge_into_session(fetched: pd.DataFrame, source_label: str, fingerprint_extra: str = "") -> tuple[int, int]:
    """把新拉取的 DataFrame 合并进 session uploaded_dataframe，返回 (本次行数, 合并后总行数)。"""
    current = st.session_state.get("uploaded_dataframe")
    if isinstance(current, pd.DataFrame) and not current.empty:
        # cell-level merge：新拉取的非空值覆盖旧值，新数据为 NaN 的格子保留旧值。
        # 之前用 concat + drop_duplicates(keep="last") 是整行替换，会让 API 拉取
        # 行里的 NaN（如 Meta 给不了的 followers/impressions）把手动收集的真实值
        # 清空。改用与 Sheet 写入一致的 cell_merge 语义。
        merged = cell_merge(fetched, current)
    else:
        merged = fetched.copy()
    merged = merged.sort_values(["platform", "date"]).reset_index(drop=True)
    platforms = sorted(merged["platform"].dropna().unique().tolist())
    store_uploaded_dataframe(merged, {
        "rows": len(merged),
        "platforms": [PLATFORM_LABELS.get(p, p) for p in platforms],
        "platform_count": len(platforms),
        "date_start": merged["date"].min().date() if not merged.empty else None,
        "date_end": merged["date"].max().date() if not merged.empty else None,
        "files": [f"（{source_label}）"],
        "fingerprint": hashlib.sha1(
            f"{source_label}:{fingerprint_extra}:{len(merged)}".encode()
        ).hexdigest()[:12],
    })
    return len(fetched), len(merged)


def _empty_manual_buffer() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.Series(dtype="datetime64[ns]"),
            "platform": pd.Series(dtype="object"),
            **{c: pd.Series(dtype="float64") for c in STANDARD_COLS if c not in ("date", "platform")},
        }
    )


# ============================================================
# 状态卡（常驻顶部）
# ============================================================

if has_uploaded_dataframe():
    meta = get_uploaded_meta()
    section("当前会话数据", icon="🟢", color="emerald", hint="存在 session 内存中，刷新页面会丢失")
    with st.container(border=True):
        st.markdown("**当前已加载的上传数据**")
        c1, c2, c3 = st.columns([1, 1, 3])
        c1.metric("行数", f"{meta.get('rows', 0):,}")
        c2.metric("平台数", meta.get("platform_count", 0))
        start = meta.get("date_start", "—")
        end = meta.get("date_end", "—")
        c3.metric("日期范围", f"{start} → {end}")
        st.caption(f"覆盖平台：{', '.join(meta.get('platforms', [])) or '—'}")
        if st.button("🗑️ 清除上传数据，回落到示例", type="secondary"):
            clear_uploaded_dataframe()
            st.rerun()


# ============================================================
# Tab 1：📤 上传 CSV
# ============================================================

def render_csv_tab() -> None:
    with st.expander("支持的导出格式", expanded=False):
        st.markdown(
            """
            | 来源 | 必含列（用于自动识别） |
            |---|---|
            | **Metricool** | `Account` + `Network` + `Date` |
            | **Instagram (Meta Business Suite)** | `Date`、`Followers`、`Impressions`、`Reach`、`Likes`、`Comments`、`Shares`、`Saves` |
            | **TikTok Analytics** | `Date`、`Followers`、`Video Views`、`Likes`、`Comments`、`Shares` |
            | **YouTube Studio** | `Date`、`Subscribers`、`Views`、`Likes`、`Comments` |
            | **X Analytics** | `Date`、`Followers`、`Impressions`、`Likes`、`Replies`、`Retweets` |
            | **Facebook (Meta Business Suite)** | `Date`、`Page Followers`、`Impressions`、`Reach`、`Reactions`、`Comments`、`Shares` |
            | **LinkedIn Page Analytics** | `Date`、`Total followers`、`Impressions`、`Reactions`、`Comments`、`Shares` |

            系统按表头列集合作为指纹自动判别来源；未匹配的文件会进入下方手动映射。
            """
        )

    uploaded = st.file_uploader(
        "拖拽或选择 CSV 文件（可多选）",
        type=["csv"],
        accept_multiple_files=True,
        help="文件不会被上传到服务器以外的地方；当前实现存在 session 内存，刷新页面后失效。",
    )

    if not uploaded:
        if not has_uploaded_dataframe():
            st.caption("尚未上传任何文件。视图页将使用 `data/samples/` 下的示例数据。")
        return

    fingerprint_src = "|".join(sorted(f"{f.name}:{f.size}" for f in uploaded))
    fingerprint = hashlib.sha1(fingerprint_src.encode("utf-8")).hexdigest()[:12]

    # 第一遍：识别自动 vs 手动
    auto_frames: list[pd.DataFrame] = []
    needs_mapping: list[tuple] = []
    for f in uploaded:
        kind, cols = identify_csv_source(f)
        if kind is not None:
            auto_frames.append(load_csv(f, label=f.name))
        else:
            needs_mapping.append((f, cols))

    # 已保存的手动映射
    saved_mappings: dict = st.session_state.setdefault("manual_mappings", {})
    mapped_frames: list[pd.DataFrame] = []
    still_unmapped: list[tuple] = []
    for f, cols in needs_mapping:
        key = f"{f.name}:{f.size}"
        if key in saved_mappings:
            cfg = saved_mappings[key]
            mapped_frames.append(load_csv_with_mapping(f, cfg["platform"], cfg["column_map"], label=f.name))
        else:
            still_unmapped.append((f, cols, key))

    all_frames = [df for df in (auto_frames + mapped_frames) if not df.empty]
    if all_frames:
        df = pd.concat(all_frames, ignore_index=True, sort=False)
        df = df.sort_values(["platform", "date"]).drop_duplicates(
            subset=["platform", "date"], keep="last"
        ).reset_index(drop=True)
        platforms = sorted(df["platform"].dropna().unique().tolist())
        store_uploaded_dataframe(df, {
            "rows": len(df),
            "platforms": [PLATFORM_LABELS.get(p, p) for p in platforms],
            "platform_count": len(platforms),
            "date_start": df["date"].min().date() if not df.empty else None,
            "date_end": df["date"].max().date() if not df.empty else None,
            "files": [f.name for f in uploaded],
            "fingerprint": fingerprint,
        })
        st.success(
            f"✅ 已加载 {len(uploaded) - len(still_unmapped)} 个文件，共 {len(df):,} 行，"
            f"覆盖 {len(platforms)} 个平台。"
        )
        st.markdown("**数据预览（每平台前 2 行）**")
        st.dataframe(df.groupby("platform", group_keys=False).head(2), width="stretch", hide_index=True)
    elif not still_unmapped:
        st.error("没有任何文件被成功识别。请检查上方「支持的导出格式」。")

    if still_unmapped:
        st.divider()
        section("手动映射未识别的列", icon="🛠️", color="amber")
        st.caption("以下文件表头不匹配任何已知格式。请选择平台并把列名映射到标准字段；提交后并入上传数据。")
        for f, cols, key in still_unmapped:
            with st.expander(f"📄 {f.name}（{len(cols)} 列待映射）", expanded=True):
                st.caption(f"原始表头：{', '.join(cols)}")
                with st.form(f"mapping_form_{key}", clear_on_submit=False):
                    platform = st.selectbox(
                        "平台", options=_PLATFORM_OPTIONS,
                        format_func=lambda p: PLATFORM_LABELS.get(p, p),
                        key=f"plat_{key}",
                    )
                    st.markdown("**列映射**")
                    field_options = ["", *STANDARD_COLS]
                    field_labels = {"": "（忽略）", **{c: STANDARD_FIELD_LABELS.get(c, c) for c in STANDARD_COLS}}

                    def _guess(col: str) -> str:
                        low = col.strip().lower().replace(" ", "_")
                        return low if low in STANDARD_COLS else ""

                    column_map: dict[str, str] = {}
                    cols_pairs = [cols[i:i + 2] for i in range(0, len(cols), 2)]
                    for pair in cols_pairs:
                        ui_cols = st.columns(len(pair))
                        for ui_col, raw_col in zip(ui_cols, pair):
                            guess = _guess(raw_col)
                            with ui_col:
                                choice = st.selectbox(
                                    raw_col, options=field_options,
                                    format_func=lambda x: field_labels[x],
                                    index=field_options.index(guess),
                                    key=f"map_{key}_{raw_col}",
                                )
                                column_map[raw_col] = choice
                    if st.form_submit_button("✅ 应用映射"):
                        if "date" not in column_map.values():
                            st.error("必须至少把一列映射为「日期 (date)」。")
                        else:
                            saved_mappings[key] = {"platform": platform, "column_map": column_map}
                            st.rerun()

        if saved_mappings:
            if st.button("🗑️ 清除所有手动映射", type="secondary"):
                st.session_state["manual_mappings"] = {}
                st.rerun()


# ============================================================
# Tab 2：✍️ 手动录入
# ============================================================

def render_manual_tab() -> None:
    st.caption("适合没有 CSV 导出功能的平台。直接在表格里填一行或多行，提交后会并入上传数据。")

    if _MANUAL_BUFFER_KEY not in st.session_state:
        st.session_state[_MANUAL_BUFFER_KEY] = _empty_manual_buffer()

    edited = st.data_editor(
        st.session_state[_MANUAL_BUFFER_KEY],
        num_rows="dynamic",
        width="stretch",
        key="manual_entry_editor",
        column_config={
            "date": st.column_config.DateColumn("日期", required=True, format="YYYY-MM-DD"),
            "platform": st.column_config.SelectboxColumn("平台", options=_PLATFORM_OPTIONS, required=True),
            "followers": st.column_config.NumberColumn("粉丝", min_value=0, step=1),
            "impressions": st.column_config.NumberColumn("曝光", min_value=0, step=1),
            "reach": st.column_config.NumberColumn("触达", min_value=0, step=1),
            "likes": st.column_config.NumberColumn("点赞", min_value=0, step=1),
            "comments": st.column_config.NumberColumn("评论", min_value=0, step=1),
            "shares": st.column_config.NumberColumn("转发", min_value=0, step=1),
            "saves": st.column_config.NumberColumn("收藏", min_value=0, step=1),
            "posts_count": st.column_config.NumberColumn("发帖数", min_value=0, step=1),
        },
    )

    col_m1, col_m2 = st.columns([1, 1])
    with col_m1:
        if st.button("✅ 提交录入数据", disabled=edited.empty):
            valid = edited.dropna(subset=["date", "platform"]).copy()
            if valid.empty:
                st.error("每行必须填日期和平台。")
            else:
                valid["date"] = pd.to_datetime(valid["date"], errors="coerce")
                valid = valid.dropna(subset=["date"])
                added, total = _merge_into_session(valid[STANDARD_COLS], "手动录入", str(valid["date"].max()))
                st.session_state[_MANUAL_BUFFER_KEY] = _empty_manual_buffer()
                st.success(f"✅ 已并入 {added:,} 行手动数据，当前上传数据共 {total:,} 行。")
                st.rerun()
    with col_m2:
        if st.button("🗑️ 清空录入表格", type="secondary"):
            st.session_state[_MANUAL_BUFFER_KEY] = _empty_manual_buffer()
            st.rerun()


# ============================================================
# Tab 3：🔌 API 拉取（嵌套 tabs 分平台）
# ============================================================

def _render_meta_tab() -> None:
    if not _meta_configured():
        st.info("尚未配置 Meta API 凭证。请在 secrets 中添加 `[meta_graph]` 区段。")
        with st.expander("查看配置格式"):
            st.code(
                "[meta_graph]\n"
                'page_access_token = "EAAxxxxxx..."\n'
                'page_id           = "123456789"\n'
                'ig_user_id        = "987654321"   # 可选\n'
                'app_id            = "111111111"   # 可选\n',
                language="toml",
            )
        return

    st.caption("已检测到 `[meta_graph]` 配置。Page Access Token 60 天有效。")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        api_since = st.date_input("开始日期", value=date.today() - timedelta(days=29), key="meta_since")
    with col_m2:
        api_until = st.date_input("结束日期", value=date.today() - timedelta(days=1), key="meta_until")

    want_fb = st.checkbox("Facebook Page", value=True)
    want_ig = st.checkbox("Instagram Business Account", value=True)

    if st.button("📡 拉取 Meta API 数据", type="primary", key="meta_fetch"):
        if api_since > api_until:
            st.error("开始日期不能晚于结束日期。")
        elif not (want_fb or want_ig):
            st.error("请至少勾选一个平台。")
        else:
            try:
                if load_sheets_into_session():
                    st.info("已从 Google Sheets 恢复已有数据，正在合并新拉取内容…")
                source = MetaGraphSource.from_streamlit_secrets()
                with st.spinner(f"拉取 {api_since} → {api_until} 数据中…"):
                    fetched = source.fetch_all(api_since, api_until, fb=want_fb, ig=want_ig)
                if fetched.empty:
                    st.warning("API 返回了空数据，请确认时间范围内有发帖或活动。")
                else:
                    added, total = _merge_into_session(fetched, "Meta API 拉取", f"{api_since}:{api_until}")
                    fb_rows = len(fetched[fetched["platform"] == "facebook"]) if want_fb else 0
                    ig_rows = len(fetched[fetched["platform"] == "instagram"]) if want_ig else 0
                    parts = []
                    if want_fb: parts.append(f"Facebook {fb_rows} 行")
                    if want_ig: parts.append(f"Instagram {ig_rows} 行")
                    st.success(f"✅ 拉取完成：{' + '.join(parts)}，当前 session 共 {total:,} 行。")
            except MetaGraphConfigError as exc:
                st.error(f"配置错误：{exc}")
            except MetaGraphAPIError as exc:
                st.error(f"API 调用失败：{exc}")
                if exc.meta_error:
                    err = exc.meta_error
                    st.caption(
                        f"Meta 错误码 {err.get('code')} / 子码 {err.get('error_subcode')}："
                        f" {err.get('error_user_msg') or err.get('message', '')}"
                    )
            except Exception as exc:  # noqa: BLE001
                st.error(f"未知错误：{type(exc).__name__}: {exc}")

    with st.expander("🔍 验证 Token 是否有效"):
        if st.button("检查 Token 状态", key="meta_token_check"):
            try:
                source = MetaGraphSource.from_streamlit_secrets()
                info = source.check_token()
                if info["valid"]:
                    expires = info["expires_at"]
                    if expires:
                        days_left = (expires - date.today()).days
                        color = "🟢" if days_left > 14 else "🟡" if days_left > 3 else "🔴"
                        st.success(f"{color} Token 有效，到期 {expires}（还剩 {days_left} 天）")
                    else:
                        st.success("🟢 Token 有效（无过期时间）")
                    st.caption(f"权限：{', '.join(info['scopes'])}")
                    st.caption(f"类型：{info['type']}  App ID：{info['app_id']}")
                else:
                    st.error("🔴 Token 无效或已过期，请重新在 Graph API Explorer 生成。")
            except (MetaGraphConfigError, MetaGraphAPIError) as exc:
                st.error(str(exc))


def _render_simple_api_tab(
    *, config_key: str, source_cls, config_error_cls, api_error_cls,
    config_example: str, token_hint: str = "", data_note: str = "",
    is_configured_fn=None,
) -> None:
    """YouTube / LinkedIn / TikTok 共用模板。"""
    if data_note:
        st.caption(data_note)
    if not is_configured_fn():
        st.info(f"尚未配置凭证。请在 secrets 中添加 `[{config_key}]` 区段。")
        with st.expander("查看配置格式"):
            st.code(config_example, language="toml")
        return

    st.caption(f"已检测到 `[{config_key}]` 配置。" + (f" {token_hint}" if token_hint else ""))
    col1, col2 = st.columns(2)
    with col1:
        _since = st.date_input("开始日期", value=date.today() - timedelta(days=29), key=f"{config_key}_since")
    with col2:
        _until = st.date_input("结束日期", value=date.today() - timedelta(days=1), key=f"{config_key}_until")

    if st.button("📡 拉取数据", type="primary", key=f"{config_key}_fetch"):
        if _since > _until:
            st.error("开始日期不能晚于结束日期。")
        else:
            try:
                if load_sheets_into_session():
                    st.info("已从 Google Sheets 恢复已有数据，正在合并新拉取内容…")
                src = source_cls.from_streamlit_secrets()
                with st.spinner(f"拉取 {_since} → {_until} 数据中…"):
                    fetched = src.fetch(_since, _until)
                if fetched.empty:
                    st.warning("API 返回空数据，请确认时间段内有活动或发帖。")
                else:
                    added, total = _merge_into_session(fetched, f"{config_key} API 拉取", f"{_since}:{_until}")
                    st.success(f"✅ 拉取完成，{added:,} 行，当前 session 共 {total:,} 行。")
            except (config_error_cls, api_error_cls) as exc:
                st.error(str(exc))
            except Exception as exc:  # noqa: BLE001
                st.error(f"未知错误：{type(exc).__name__}: {exc}")

    with st.expander("🔍 验证 Token 是否有效"):
        if st.button("检查 Token 状态", key=f"{config_key}_token_check"):
            try:
                src = source_cls.from_streamlit_secrets()
                info = src.check_token()
                if info.get("valid"):
                    st.success(f"🟢 Token 有效。{info.get('name', '') or ''}")
                else:
                    st.error(f"🔴 Token 无效：{info.get('error', '未知原因')}")
            except (config_error_cls, api_error_cls) as exc:
                st.error(str(exc))


def render_api_tab() -> None:
    sub_meta, sub_yt, sub_li, sub_tt = st.tabs([
        "📘 Meta (FB + IG)", "📺 YouTube", "💼 LinkedIn", "🎵 TikTok",
    ])
    with sub_meta:
        _render_meta_tab()
    with sub_yt:
        _render_simple_api_tab(
            config_key="youtube",
            source_cls=YouTubeSource,
            config_error_cls=YouTubeConfigError,
            api_error_cls=YouTubeAPIError,
            is_configured_fn=_yt_configured,
            config_example=(
                "[youtube]\n"
                'client_id     = "...apps.googleusercontent.com"\n'
                'client_secret = "GOCSPX-..."\n'
                'refresh_token = "1//..."\n'
                "# 运行 scripts/youtube_auth.py 可自动生成 refresh_token"
            ),
            token_hint="refresh_token 永久有效，无需定期更换。",
        )
    with sub_li:
        _render_simple_api_tab(
            config_key="linkedin",
            source_cls=LinkedInSource,
            config_error_cls=LinkedInConfigError,
            api_error_cls=LinkedInAPIError,
            is_configured_fn=_li_configured,
            config_example=(
                "[linkedin]\n"
                'access_token    = "AQV..."\n'
                'organization_id = "12345678"   # 纯数字 或 urn:li:organization:12345678\n'
            ),
            token_hint="access_token 有效期约 60 天，过期后需重新授权。",
            data_note="⚠️ 需要 LinkedIn App 审核通过（r_organization_social 权限），审核约 1–5 个工作日。",
        )
    with sub_tt:
        _render_simple_api_tab(
            config_key="tiktok",
            source_cls=TikTokSource,
            config_error_cls=TikTokConfigError,
            api_error_cls=TikTokAPIError,
            is_configured_fn=_tt_configured,
            config_example=(
                "[tiktok]\n"
                'access_token  = "act.xxx..."   # 24 小时有效\n'
                'refresh_token = "rft.xxx..."   # 30 天有效\n'
                'app_id        = "7xxx"\n'
                'app_secret    = "xxx"\n'
            ),
            token_hint="⚠️ access_token 仅 24 小时有效，系统会自动用 refresh_token 续期。",
            data_note="⚠️ TikTok 有机内容日粒度 API 支持有限：仅返回当日快照 + 视频互动聚合，历史粉丝变化建议用 CSV 补充。",
        )


# ============================================================
# Tab 4：☁️ Google Sheets 同步
# ============================================================

def render_sheets_tab() -> None:
    if not is_gsheets_configured():
        st.info("尚未配置 Google Sheets 凭据，云端同步功能未启用。当前数据源回落顺序：上传 → 本地 CSV。")
        with st.expander("如何启用 Google Sheets 持久化", expanded=False):
            st.markdown(
                """
                **一次性设置（约 10 分钟）**：

                1. 创建一个 Google Sheet，第一行用标准列名作为表头：
                   `date | platform | followers | impressions | reach | likes | comments | shares | saves | posts_count`
                2. 到 [Google Cloud Console](https://console.cloud.google.com/) 新建项目 →
                   启用 **Google Sheets API** + **Google Drive API** → 创建 Service Account →
                   生成 JSON 密钥
                3. 把 Sheet **共享**给 Service Account 邮箱，权限选「编辑者」
                4. 在 Streamlit Cloud Settings → Secrets 里粘贴 `[gsheets]` 配置（见 secrets.toml.example）

                完整模板见 `.streamlit/secrets.toml.example`。
                """
            )
        return

    st.caption("已检测到 `[gsheets]` 配置。可把当前上传数据写回云端，实现跨 session 持久化。")

    write_mode = st.radio(
        "写入模式",
        options=["merge", "replace"],
        format_func=lambda m: {
            "merge": "🔀 增量合并（推荐）— 按平台+日期合并，新值覆盖旧值，未涉及行保留",
            "replace": "⚠️ 整表替换 — 清空 Sheet 后写入当前数据（会丢失之前积累的数据）",
        }[m],
        index=0,
    )

    # 整表替换是破坏性操作，强制确认（防误点 + 防公开应用被恶意访问者清空）
    replace_confirmed = True
    if write_mode == "replace":
        st.warning(
            "⚠️ 这会**清空 Sheet 里所有历史数据**并替换为本次上传内容。"
            "如果只想新增/更新某些日期，请用「增量合并」。"
        )
        confirm_text = st.text_input(
            '若确认执行整表替换，请输入 "REPLACE"',
            key="sheets_replace_confirm",
        )
        replace_confirmed = confirm_text.strip() == "REPLACE"
        if not replace_confirmed:
            st.caption("未输入确认文本，「写回」按钮已禁用。")

    col_a, col_b = st.columns(2)
    with col_a:
        write_disabled = (
            not has_uploaded_dataframe()
            or (write_mode == "replace" and not replace_confirmed)
        )
        if st.button("⬆️ 把当前上传数据写回 Google Sheets", disabled=write_disabled):
            try:
                source = GoogleSheetsSource()
                df_to_write = st.session_state.get("uploaded_dataframe")
                with st.spinner("写入 Google Sheets 中…"):
                    result = source.write(df_to_write, mode=write_mode)
                if result["mode"] == "merge":
                    st.success(
                        f"✅ 合并写入完成：新增 {result['added']:,} 行，更新 {result['updated']:,} 行，"
                        f"Sheet 现共 {result['total']:,} 行。"
                    )
                else:
                    st.success(f"✅ 整表替换完成：写入 {result['written']:,} 行。")
                    # 重置确认文本，避免下次进来仍然处于可执行状态
                    st.session_state.pop("sheets_replace_confirm", None)
            except GoogleSheetsConfigError as exc:
                st.error(f"配置错误：{exc}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"写入失败：{type(exc).__name__}: {exc}")
    with col_b:
        if st.button("🔄 从 Google Sheets 拉取最新数据"):
            try:
                with st.spinner("读取 Google Sheets 中…"):
                    df = GoogleSheetsSource().load()
                if df.empty:
                    st.warning("Google Sheets 为空。请先写回一次上传数据。")
                else:
                    st.success(f"✅ 已读到 {len(df):,} 行。视图页会优先使用本次上传；清除上传后将自动展示 Sheets 数据。")
                    st.dataframe(df.head(10), width="stretch", hide_index=True)
            except GoogleSheetsConfigError as exc:
                st.error(f"配置错误：{exc}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"读取失败：{type(exc).__name__}: {exc}")
    if not has_uploaded_dataframe():
        st.caption("💡 未上传数据时无法写回。请先在上方上传 CSV。")


# ============================================================
# 主入口：4 个 Tab
# ============================================================

tab_csv, tab_manual, tab_api, tab_sheets = st.tabs([
    "📤 上传 CSV", "✍️ 手动录入", "🔌 API 拉取", "☁️ Sheets 同步",
])

with tab_csv:
    render_csv_tab()
with tab_manual:
    render_manual_tab()
with tab_api:
    render_api_tab()
with tab_sheets:
    render_sheets_tab()

# ============================================================
# 底部：数据源优先级说明
# ============================================================

st.divider()
with st.expander("数据源优先级", expanded=False):
    st.markdown(
        """
        当前数据源解析顺序（先命中先用）：

        1. **本次上传**（session 内存，刷新失效）
        2. **Google Sheets**（若已配置 `[gsheets]` Secrets）— 跨 session 持久化
        3. **本地 CSV**：先读 `data/`（gitignore 的真实运营数据），再回落 `data/samples/`（示例）

        运营流程建议：在本页上传 → 点「写回 Google Sheets」→ 之后任何浏览器/设备打开仪表盘都能看到。
        """
    )
