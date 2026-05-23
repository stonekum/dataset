"""数据导入 — 拖拽上传各平台导出 CSV（F09）。

支持 Metricool 统一导出 + 六个平台原生 Analytics 导出，自动识别表头并合并。
上传数据存储在 session 内存中（刷新页面会丢失），所有视图页会优先使用上传数据。
"""

from __future__ import annotations

import hashlib

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
    clear_uploaded_dataframe,
    get_uploaded_meta,
    has_uploaded_dataframe,
    is_gsheets_configured,
    store_uploaded_dataframe,
)

import pandas as pd

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

st.set_page_config(page_title="数据导入 - 海外社媒数据面板", page_icon="📤", layout="wide")

PLATFORM_LABELS = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "x": "X",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
}

st.title("📤 数据导入")
st.caption("把各平台导出的 CSV 拖进来，系统自动识别来源、清洗、合并。无需碰仓库，无需 GitHub。")

# ---------- 已有上传：状态卡 ----------
if has_uploaded_dataframe():
    meta = get_uploaded_meta()
    with st.container(border=True):
        st.markdown("**当前已加载的上传数据**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("行数", f"{meta.get('rows', 0):,}")
        c2.metric("平台数", meta.get("platform_count", 0))
        c3.metric("起始日期", str(meta.get("date_start", "—")))
        c4.metric("结束日期", str(meta.get("date_end", "—")))
        st.caption(f"覆盖平台：{', '.join(meta.get('platforms', [])) or '—'}")
        if st.button("🗑️ 清除上传数据，回落到示例", type="secondary"):
            clear_uploaded_dataframe()
            st.rerun()

# ---------- 上传入口 ----------
st.subheader("📥 上传 CSV")

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

        系统按表头列集合作为指纹自动判别来源；未匹配的文件会被跳过并提示。
        """
    )

uploaded = st.file_uploader(
    "拖拽或选择 CSV 文件（可多选）",
    type=["csv"],
    accept_multiple_files=True,
    help="文件不会被上传到服务器以外的地方；当前实现存在 session 内存，刷新页面后失效。",
)

if uploaded:
    fingerprint_src = "|".join(sorted(f"{f.name}:{f.size}" for f in uploaded))
    fingerprint = hashlib.sha1(fingerprint_src.encode("utf-8")).hexdigest()[:12]

    # 第一遍：识别哪些自动 OK、哪些需要手动映射
    auto_frames: list[pd.DataFrame] = []
    needs_mapping: list[tuple] = []  # (file, columns)
    for f in uploaded:
        kind, cols = identify_csv_source(f)
        if kind is not None:
            auto_frames.append(load_csv(f, label=f.name))
        else:
            needs_mapping.append((f, cols))

    # 已保存的手动映射（F12）
    saved_mappings: dict = st.session_state.setdefault("manual_mappings", {})
    mapped_frames: list[pd.DataFrame] = []
    still_unmapped: list[tuple] = []
    for f, cols in needs_mapping:
        key = f"{f.name}:{f.size}"
        if key in saved_mappings:
            cfg = saved_mappings[key]
            mapped_frames.append(
                load_csv_with_mapping(f, cfg["platform"], cfg["column_map"], label=f.name)
            )
        else:
            still_unmapped.append((f, cols, key))

    # 合并已识别 + 已映射
    all_frames = [df for df in (auto_frames + mapped_frames) if not df.empty]
    if all_frames:
        df = pd.concat(all_frames, ignore_index=True, sort=False)
        df = df.sort_values(["platform", "date"]).drop_duplicates(
            subset=["platform", "date"], keep="last"
        ).reset_index(drop=True)
        platforms = sorted(df["platform"].dropna().unique().tolist())
        meta = {
            "rows": len(df),
            "platforms": [PLATFORM_LABELS.get(p, p) for p in platforms],
            "platform_count": len(platforms),
            "date_start": df["date"].min().date() if not df.empty else None,
            "date_end": df["date"].max().date() if not df.empty else None,
            "files": [f.name for f in uploaded],
            "fingerprint": fingerprint,
        }
        store_uploaded_dataframe(df, meta)
        st.success(
            f"✅ 已加载 {len(uploaded) - len(still_unmapped)} 个文件，共 {len(df):,} 行，"
            f"覆盖 {len(platforms)} 个平台。"
        )
        st.markdown("**数据预览（每平台前 2 行）**")
        st.dataframe(df.groupby("platform", group_keys=False).head(2), width="stretch", hide_index=True)
    elif not still_unmapped:
        st.error("没有任何文件被成功识别。请检查上方「支持的导出格式」。")

    # 手动映射 UI（F12）
    if still_unmapped:
        st.divider()
        st.subheader("🛠️ 手动映射未识别的列")
        st.caption(
            "以下文件的表头与已知格式不匹配。请为每个文件选择平台，并把原始列名映射到标准字段；"
            "不需要的列选「（忽略）」。提交后会被合并进上传数据。"
        )
        for f, cols, key in still_unmapped:
            with st.expander(f"📄 {f.name}（{len(cols)} 列待映射）", expanded=True):
                st.caption(f"原始表头：{', '.join(cols)}")
                with st.form(f"mapping_form_{key}", clear_on_submit=False):
                    platform = st.selectbox(
                        "平台",
                        options=_PLATFORM_OPTIONS,
                        format_func=lambda p: PLATFORM_LABELS.get(p, p),
                        key=f"plat_{key}",
                    )
                    st.markdown("**列映射**（每个原始列对应一个标准字段，或忽略）")
                    field_options = ["", *STANDARD_COLS]
                    field_labels = {"": "（忽略）", **{c: STANDARD_FIELD_LABELS.get(c, c) for c in STANDARD_COLS}}

                    # 自动猜：若原始列名小写后等于某个标准列名，预选上
                    def _guess(col: str) -> str:
                        low = col.strip().lower().replace(" ", "_")
                        return low if low in STANDARD_COLS else ""

                    column_map: dict[str, str] = {}
                    cols_pairs = [cols[i:i+2] for i in range(0, len(cols), 2)]
                    for pair in cols_pairs:
                        ui_cols = st.columns(len(pair))
                        for ui_col, raw_col in zip(ui_cols, pair):
                            guess = _guess(raw_col)
                            with ui_col:
                                choice = st.selectbox(
                                    raw_col,
                                    options=field_options,
                                    format_func=lambda x: field_labels[x],
                                    index=field_options.index(guess),
                                    key=f"map_{key}_{raw_col}",
                                )
                                column_map[raw_col] = choice
                    submitted = st.form_submit_button("✅ 应用映射")
                    if submitted:
                        if "date" not in column_map.values():
                            st.error("必须至少把一列映射为「日期 (date)」。")
                        else:
                            saved_mappings[key] = {
                                "platform": platform,
                                "column_map": column_map,
                            }
                            st.rerun()

        if saved_mappings:
            if st.button("🗑️ 清除所有手动映射", type="secondary"):
                st.session_state["manual_mappings"] = {}
                st.rerun()

    if all_frames or saved_mappings:
        st.info("已切换为上传数据。请到「📊 运营视图」或「📈 汇报视图」查看效果。")
else:
    if not has_uploaded_dataframe():
        st.caption("尚未上传任何文件。视图页将使用 `data/samples/` 下的示例数据。")

# ---------- 手动录入（F13） ----------
st.divider()
st.subheader("✍️ 手动录入数据")
st.caption(
    "适合没有 CSV 导出功能的平台。直接在表格里填一行或多行，提交后会并入上传数据；"
    "可继续在「☁️ Google Sheets 同步」里写回云端做持久化。"
)

_MANUAL_BUFFER_KEY = "manual_entries_buffer"


def _empty_manual_buffer() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.Series(dtype="datetime64[ns]"),
            "platform": pd.Series(dtype="object"),
            **{c: pd.Series(dtype="float64") for c in STANDARD_COLS if c not in ("date", "platform")},
        }
    )


if _MANUAL_BUFFER_KEY not in st.session_state:
    st.session_state[_MANUAL_BUFFER_KEY] = _empty_manual_buffer()

edited = st.data_editor(
    st.session_state[_MANUAL_BUFFER_KEY],
    num_rows="dynamic",
    width="stretch",
    key="manual_entry_editor",
    column_config={
        "date": st.column_config.DateColumn("日期", required=True, format="YYYY-MM-DD"),
        "platform": st.column_config.SelectboxColumn(
            "平台", options=_PLATFORM_OPTIONS, required=True
        ),
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
        # 过滤：必须有 date 和 platform
        valid = edited.dropna(subset=["date", "platform"]).copy()
        if valid.empty:
            st.error("每行必须填日期和平台。")
        else:
            valid["date"] = pd.to_datetime(valid["date"], errors="coerce")
            valid = valid.dropna(subset=["date"])

            # 合并到 uploaded_dataframe（若有），按 (platform, date) 去重，新值覆盖
            current = st.session_state.get("uploaded_dataframe")
            if isinstance(current, pd.DataFrame) and not current.empty:
                merged = pd.concat([current, valid[STANDARD_COLS]], ignore_index=True, sort=False)
            else:
                merged = valid[STANDARD_COLS].copy()
            merged = merged.sort_values(["platform", "date"]).drop_duplicates(
                subset=["platform", "date"], keep="last"
            ).reset_index(drop=True)

            platforms = sorted(merged["platform"].dropna().unique().tolist())
            meta = {
                "rows": len(merged),
                "platforms": [PLATFORM_LABELS.get(p, p) for p in platforms],
                "platform_count": len(platforms),
                "date_start": merged["date"].min().date() if not merged.empty else None,
                "date_end": merged["date"].max().date() if not merged.empty else None,
                "files": ["（手动录入）"],
                "fingerprint": hashlib.sha1(
                    f"manual:{len(merged)}:{merged['date'].max()}".encode("utf-8")
                ).hexdigest()[:12],
            }
            store_uploaded_dataframe(merged, meta)
            st.session_state[_MANUAL_BUFFER_KEY] = _empty_manual_buffer()
            st.success(f"✅ 已并入 {len(valid):,} 行手动数据，当前上传数据共 {len(merged):,} 行。")
            st.rerun()
with col_m2:
    if st.button("🗑️ 清空录入表格", type="secondary"):
        st.session_state[_MANUAL_BUFFER_KEY] = _empty_manual_buffer()
        st.rerun()

# ---------- Meta Graph API 拉取（F14） ----------
st.divider()
st.subheader("🔌 Meta API 拉取（Facebook & Instagram）")

from utils.meta_graph import MetaGraphConfigError, MetaGraphAPIError, MetaGraphSource, _is_configured as _meta_configured  # noqa: E402

if not _meta_configured():
    st.info(
        "尚未配置 Meta API 凭证。"
        "请在 `.streamlit/secrets.toml` 中添加 `[meta_graph]` 区段（见 secrets.toml.example），"
        "或在 Streamlit Cloud → App Settings → Secrets 填入。"
    )
    with st.expander("查看配置格式"):
        st.code(
            "[meta_graph]\n"
            'page_access_token = "EAAxxxxxx..."\n'
            'page_id           = "123456789"\n'
            'ig_user_id        = "987654321"   # 可选，需要 IG 数据时填写\n'
            'app_id            = "111111111"   # 可选，仅用于续期参考\n',
            language="toml",
        )
else:
    st.caption(
        "已检测到 `[meta_graph]` 配置。选择时间范围和平台后点击「拉取」，"
        "数据会并入当前 session 数据（可再配合 Google Sheets 同步写回云端）。"
    )

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        api_since = st.date_input(
            "开始日期",
            value=date.today() - timedelta(days=29),
            key="meta_since",
        )
    with col_m2:
        api_until = st.date_input(
            "结束日期",
            value=date.today() - timedelta(days=1),
            key="meta_until",
        )

    from datetime import date, timedelta  # noqa: E402 (already imported via pd but explicit)

    want_fb = st.checkbox("Facebook Page", value=True)
    want_ig = st.checkbox("Instagram Business Account", value=True)

    if st.button("📡 拉取 Meta API 数据", type="primary"):
        if api_since > api_until:
            st.error("开始日期不能晚于结束日期。")
        elif not (want_fb or want_ig):
            st.error("请至少勾选一个平台。")
        else:
            try:
                source = MetaGraphSource.from_streamlit_secrets()
                with st.spinner(f"拉取 {api_since} → {api_until} 数据中…"):
                    fetched = source.fetch_all(api_since, api_until, fb=want_fb, ig=want_ig)

                if fetched.empty:
                    st.warning("API 返回了空数据，请确认时间范围内有发帖或活动。")
                else:
                    # 并入 session 数据
                    current = st.session_state.get("uploaded_dataframe")
                    if isinstance(current, pd.DataFrame) and not current.empty:
                        merged = pd.concat([current, fetched], ignore_index=True, sort=False)
                    else:
                        merged = fetched.copy()
                    merged = merged.sort_values(["platform", "date"]).drop_duplicates(
                        subset=["platform", "date"], keep="last"
                    ).reset_index(drop=True)

                    platforms = sorted(merged["platform"].dropna().unique().tolist())
                    meta_info = {
                        "rows": len(merged),
                        "platforms": [PLATFORM_LABELS.get(p, p) for p in platforms],
                        "platform_count": len(platforms),
                        "date_start": merged["date"].min().date() if not merged.empty else None,
                        "date_end": merged["date"].max().date() if not merged.empty else None,
                        "files": ["（Meta API 拉取）"],
                        "fingerprint": hashlib.sha1(
                            f"meta:{api_since}:{api_until}:{len(merged)}".encode()
                        ).hexdigest()[:12],
                    }
                    store_uploaded_dataframe(merged, meta_info)

                    fb_rows = len(fetched[fetched["platform"] == "facebook"]) if want_fb else 0
                    ig_rows = len(fetched[fetched["platform"] == "instagram"]) if want_ig else 0
                    msg_parts = []
                    if want_fb:
                        msg_parts.append(f"Facebook {fb_rows} 行")
                    if want_ig:
                        msg_parts.append(f"Instagram {ig_rows} 行")
                    st.success(f"✅ 拉取完成：{' + '.join(msg_parts)}，当前 session 共 {len(merged):,} 行。")
                    st.info("可到「📊 运营视图」查看效果，或在下方「Google Sheets 同步」写回云端。")

            except MetaGraphConfigError as exc:
                st.error(f"配置错误：{exc}")
            except MetaGraphAPIError as exc:
                st.error(f"API 调用失败：{exc}")
                if hasattr(exc, "meta_error") and exc.meta_error:
                    err = exc.meta_error
                    st.caption(
                        f"Meta 错误码 {err.get('code')} / 子码 {err.get('error_subcode')}："
                        f" {err.get('error_user_msg') or err.get('message', '')}"
                    )
            except Exception as exc:  # noqa: BLE001
                st.error(f"未知错误：{type(exc).__name__}: {exc}")

    with st.expander("🔍 验证 Token 是否有效"):
        if st.button("检查 Token 状态"):
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
                        st.success("🟢 Token 有效（无过期时间，可能是长期 System User Token）")
                    st.caption(f"权限：{', '.join(info['scopes'])}")
                    st.caption(f"类型：{info['type']}  App ID：{info['app_id']}")
                else:
                    st.error("🔴 Token 无效或已过期，请重新在 Graph API Explorer 生成。")
            except (MetaGraphConfigError, MetaGraphAPIError) as exc:
                st.error(str(exc))


def _api_fetch_section(
    section_title: str,
    config_key: str,
    is_configured_fn,
    source_cls,
    config_error_cls,
    api_error_cls,
    config_example: str,
    token_check_fn,
    token_hint: str = "",
    data_note: str = "",
):
    """通用 API 拉取区块渲染（YouTube / LinkedIn / TikTok 共用）。"""
    st.divider()
    st.subheader(section_title)
    if data_note:
        st.caption(data_note)

    if not is_configured_fn():
        st.info(
            f"尚未配置凭证。请在 `.streamlit/secrets.toml` 中添加 `[{config_key}]` 区段，"
            "或在 Streamlit Cloud → App Settings → Secrets 填入。"
        )
        with st.expander("查看配置格式"):
            st.code(config_example, language="toml")
        return

    st.caption(f"已检测到 `[{config_key}]` 配置。" + (f" {token_hint}" if token_hint else ""))
    col1, col2 = st.columns(2)
    with col1:
        _since = st.date_input("开始日期", value=date.today() - timedelta(days=29), key=f"{config_key}_since")
    with col2:
        _until = st.date_input("结束日期", value=date.today() - timedelta(days=1), key=f"{config_key}_until")

    if st.button(f"📡 拉取 {section_title.split('（')[0].replace('🔌 ', '')} 数据", type="primary", key=f"{config_key}_fetch"):
        if _since > _until:
            st.error("开始日期不能晚于结束日期。")
        else:
            try:
                src = source_cls.from_streamlit_secrets()
                with st.spinner(f"拉取 {_since} → {_until} 数据中…"):
                    fetched = src.fetch(_since, _until)
                if fetched.empty:
                    st.warning("API 返回空数据，请确认时间段内有活动或发帖。")
                else:
                    current = st.session_state.get("uploaded_dataframe")
                    if isinstance(current, pd.DataFrame) and not current.empty:
                        merged = pd.concat([current, fetched], ignore_index=True, sort=False)
                    else:
                        merged = fetched.copy()
                    merged = merged.sort_values(["platform", "date"]).drop_duplicates(
                        subset=["platform", "date"], keep="last"
                    ).reset_index(drop=True)
                    platforms = sorted(merged["platform"].dropna().unique().tolist())
                    store_uploaded_dataframe(merged, {
                        "rows": len(merged),
                        "platforms": [PLATFORM_LABELS.get(p, p) for p in platforms],
                        "platform_count": len(platforms),
                        "date_start": merged["date"].min().date() if not merged.empty else None,
                        "date_end": merged["date"].max().date() if not merged.empty else None,
                        "files": [f"（{config_key} API 拉取）"],
                        "fingerprint": hashlib.sha1(
                            f"{config_key}:{_since}:{_until}:{len(merged)}".encode()
                        ).hexdigest()[:12],
                    })
                    st.success(f"✅ 拉取完成，{len(fetched):,} 行，当前 session 共 {len(merged):,} 行。")
                    st.info("可到「📊 运营视图」查看，或用下方「Google Sheets 同步」写回云端。")
            except (config_error_cls, api_error_cls) as exc:
                st.error(str(exc))
            except Exception as exc:  # noqa: BLE001
                st.error(f"未知错误：{type(exc).__name__}: {exc}")

    with st.expander("🔍 验证 Token 是否有效"):
        if st.button("检查 Token 状态", key=f"{config_key}_token_check"):
            try:
                src = source_cls.from_streamlit_secrets()
                info = token_check_fn(src)
                if info.get("valid"):
                    st.success(f"🟢 Token 有效。{info.get('name', '') or ''}")
                else:
                    st.error(f"🔴 Token 无效：{info.get('error', '未知原因')}")
            except (config_error_cls, api_error_cls) as exc:
                st.error(str(exc))


# ---------- YouTube ----------
from utils.youtube_api import YouTubeSource, YouTubeConfigError, YouTubeAPIError, _is_configured as _yt_configured  # noqa: E402

_api_fetch_section(
    section_title="🔌 YouTube Analytics API",
    config_key="youtube",
    is_configured_fn=_yt_configured,
    source_cls=YouTubeSource,
    config_error_cls=YouTubeConfigError,
    api_error_cls=YouTubeAPIError,
    config_example=(
        "[youtube]\n"
        'client_id     = "...apps.googleusercontent.com"\n'
        'client_secret = "GOCSPX-..."\n'
        'refresh_token = "1//..."\n'
        "# 运行 scripts/youtube_auth.py 可自动生成 refresh_token"
    ),
    token_check_fn=lambda s: s.check_token(),
    token_hint="refresh_token 永久有效，无需定期更换。",
)

# ---------- LinkedIn ----------
from utils.linkedin_api import LinkedInSource, LinkedInConfigError, LinkedInAPIError, _is_configured as _li_configured  # noqa: E402

_api_fetch_section(
    section_title="🔌 LinkedIn Company Page API",
    config_key="linkedin",
    is_configured_fn=_li_configured,
    source_cls=LinkedInSource,
    config_error_cls=LinkedInConfigError,
    api_error_cls=LinkedInAPIError,
    config_example=(
        "[linkedin]\n"
        'access_token    = "AQV..."\n'
        'organization_id = "12345678"   # 纯数字，或 urn:li:organization:12345678\n'
        "# access_token 有效期约 60 天，需要定期在 LinkedIn Developer Portal 刷新"
    ),
    token_check_fn=lambda s: s.check_token(),
    token_hint="access_token 有效期约 60 天，过期后需重新授权。",
    data_note="⚠️ 需要 LinkedIn App 审核通过（r_organization_social 权限）才可使用，审核约 1–5 个工作日。",
)

# ---------- TikTok ----------
from utils.tiktok_api import TikTokSource, TikTokConfigError, TikTokAPIError, _is_configured as _tt_configured  # noqa: E402

_api_fetch_section(
    section_title="🔌 TikTok Business API",
    config_key="tiktok",
    is_configured_fn=_tt_configured,
    source_cls=TikTokSource,
    config_error_cls=TikTokConfigError,
    api_error_cls=TikTokAPIError,
    config_example=(
        "[tiktok]\n"
        'access_token  = "act.xxx..."   # 有效期 24 小时\n'
        'refresh_token = "rft.xxx..."   # 有效期 30 天\n'
        'app_id        = "7xxx"\n'
        'app_secret    = "xxx"\n'
        "# 通过 TikTok for Developers OAuth 2.0 流程获取"
    ),
    token_check_fn=lambda s: s.check_token(),
    token_hint="⚠️ access_token 仅 24 小时有效，系统会自动用 refresh_token 换取新 token。",
    data_note="⚠️ TikTok 有机内容日粒度 API 支持有限：仅返回账号当日快照 + 时间段内视频互动聚合，历史每日粉丝/曝光变化建议用 CSV 导出补充。",
)

# ---------- Google Sheets 同步（F10） ----------
st.divider()
st.subheader("☁️ Google Sheets 同步")

if is_gsheets_configured():
    st.caption("已检测到 `.streamlit/secrets.toml` 中的 `[gsheets]` 配置。可把当前上传数据写回云端，实现跨 session 持久化。")

    write_mode = st.radio(
        "写入模式",
        options=["merge", "replace"],
        format_func=lambda m: {
            "merge": "🔀 增量合并（推荐）— 按平台+日期合并，新值覆盖旧值，未涉及行保留",
            "replace": "⚠️ 整表替换 — 清空 Sheet 后写入当前数据（会丢失之前积累的数据）",
        }[m],
        horizontal=False,
        index=0,
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("⬆️ 把当前上传数据写回 Google Sheets", disabled=not has_uploaded_dataframe()):
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
else:
    st.info(
        "尚未配置 Google Sheets 凭据，云端同步功能未启用。当前数据源回落顺序：上传 → 本地 CSV。"
    )
    with st.expander("如何启用 Google Sheets 持久化", expanded=False):
        st.markdown(
            """
            **一次性设置（约 10 分钟）**：

            1. 创建一个 Google Sheet，第一行用标准列名作为表头：
               `date | platform | followers | impressions | reach | likes | comments | shares | saves | posts_count`
            2. 到 [Google Cloud Console](https://console.cloud.google.com/) 新建项目 →
               启用 **Google Sheets API** + **Google Drive API** → 创建 Service Account →
               生成 JSON 密钥
            3. 把 Sheet **共享**给 Service Account 邮箱（`xxx@xxx.iam.gserviceaccount.com`），权限选「编辑者」
            4. 在 Streamlit Cloud Settings → Secrets 里粘贴：
               ```toml
               [gsheets]
               spreadsheet_url = "https://docs.google.com/spreadsheets/d/.../edit"
               worksheet_name = "data"   # 可选

               [gsheets.service_account]
               type = "service_account"
               project_id = "..."
               private_key_id = "..."
               private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
               client_email = "...@...iam.gserviceaccount.com"
               client_id = "..."
               token_uri = "https://oauth2.googleapis.com/token"
               ```
            5. 本地开发时把同样内容写到 `.streamlit/secrets.toml`（已 gitignore）

            完整模板见 `.streamlit/secrets.toml.example`。
            """
        )

# ---------- 数据源说明 ----------
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
