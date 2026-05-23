"""数据导入 — 拖拽上传各平台导出 CSV（F09）。

支持 Metricool 统一导出 + 六个平台原生 Analytics 导出，自动识别表头并合并。
上传数据存储在 session 内存中（刷新页面会丢失），所有视图页会优先使用上传数据。
"""

from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from utils.data_loader import load_uploaded_files
from utils.data_sources import (
    GoogleSheetsConfigError,
    GoogleSheetsSource,
    clear_uploaded_dataframe,
    get_uploaded_meta,
    has_uploaded_dataframe,
    is_gsheets_configured,
    store_uploaded_dataframe,
)

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
    # 计算指纹用于缓存失效（同一组文件不重复处理）
    fingerprint_src = "|".join(sorted(f"{f.name}:{f.size}" for f in uploaded))
    fingerprint = hashlib.sha1(fingerprint_src.encode("utf-8")).hexdigest()[:12]

    with st.spinner("识别并合并文件中…"):
        df = load_uploaded_files(uploaded)

    if df.empty:
        st.error(
            "没有任何文件被成功识别。请检查上方「支持的导出格式」，或确认 CSV 表头未被改名。"
        )
    else:
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
            f"✅ 成功加载 {len(uploaded)} 个文件，共 {len(df):,} 行，"
            f"覆盖 {len(platforms)} 个平台（{df['date'].min().date()} → {df['date'].max().date()}）。"
        )

        # 预览：按平台分组首尾各两行
        st.markdown("**数据预览（每平台前 2 行）**")
        preview = df.groupby("platform", group_keys=False).head(2)
        st.dataframe(preview, width="stretch", hide_index=True)

        st.info("已切换为上传数据。请到「📊 运营视图」或「📈 汇报视图」查看效果。")
else:
    if not has_uploaded_dataframe():
        st.caption("尚未上传任何文件。视图页将使用 `data/samples/` 下的示例数据。")

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
