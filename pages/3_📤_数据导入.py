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
    clear_uploaded_dataframe,
    get_uploaded_meta,
    has_uploaded_dataframe,
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

# ---------- 数据源说明 ----------
st.divider()
with st.expander("数据源优先级 & 未来扩展（F10 路线）", expanded=False):
    st.markdown(
        """
        当前数据源优先级：

        1. **本次上传**（session 内存，刷新失效）— 当前可用
        2. **本地 CSV**：先读 `data/`（gitignore 的真实运营数据），再回落 `data/samples/`（示例）
        3. **Google Sheets**（占位 — F10 实现）— 跨 session 持久化，运营团队可以共享同一份表

        想要持久化保存上传内容时，下一步是把 `utils/data_sources.py` 中的 `GoogleSheetsSource` 实现起来：
        通过 gspread + service account 读写一份共享表格，等于把上传入口"自动同步到云端"。
        """
    )
