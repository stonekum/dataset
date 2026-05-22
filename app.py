"""首页 — 海外社媒数据面板入口。"""

from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="海外社媒数据面板",
    page_icon="🌏",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🌏 海外社媒数据面板")
st.caption("聚合 Instagram、TikTok、YouTube、X、Facebook、LinkedIn 六个平台的运营数据")

st.markdown(
    """
    本面板服务于两类受众：

    - **📊 运营视图**：面向日常运营团队，关注每日互动率、内容表现、平台对比。
    - **📈 汇报视图**：面向管理层，按月度/季度聚合关键指标，附自动文字摘要。

    使用左侧侧边栏切换不同视图。
    """
)

st.divider()

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📦 数据状态")
    samples_dir = Path("data/samples")
    data_dir = Path("data")
    sample_csvs = sorted(samples_dir.glob("*.csv")) if samples_dir.exists() else []
    real_csvs = sorted(p for p in data_dir.glob("*.csv") if p.is_file())

    st.metric("示例数据文件", f"{len(sample_csvs)} 个")
    st.metric("运营数据文件", f"{len(real_csvs)} 个")

    if not sample_csvs and not real_csvs:
        st.warning(
            "尚未检测到任何 CSV 数据。请在 `data/` 下放入运营导出文件，"
            "或等待 F02（示例数据生成器）完成后生成示例数据。"
        )
    else:
        st.success("数据目录已就绪。")

with col_right:
    st.subheader("🧭 平台覆盖")
    platforms = [
        ("Instagram", "📷"),
        ("TikTok", "🎵"),
        ("YouTube", "▶️"),
        ("X / Twitter", "🐦"),
        ("Facebook", "👍"),
        ("LinkedIn", "💼"),
    ]
    for name, icon in platforms:
        st.write(f"{icon} {name}")

st.divider()
st.caption("提示：使用前请先运行 `bash init.sh` 完成环境初始化。")
