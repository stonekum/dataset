"""F04 — 数据清洗。

职责：处理 `data_loader` 输出的标准 DataFrame 中的异常值和缺失值，为后续指标计算和可视化提供干净的输入。

清洗规则：
- 互动数（likes/comments/shares/saves/impressions/reach）的 NaN 视为 0.
- 负数（任何数值列出现负数）一律截断为 0；同时附带一列 `is_anomaly` 标记该行原始数据存在异常。
- followers 缺失或为负的行被标记为 anomaly；followers 自身不前向填充（保留 NaN 以便上游决定如何处理），但负值截断为 0.
- date 列必须非空；data_loader 已保证，这里再做一次 dropna 兜底。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_NUMERIC_COLS = [
    "followers",
    "impressions",
    "reach",
    "likes",
    "comments",
    "shares",
    "saves",
    "posts_count",
]
_INTERACTION_COLS = ["impressions", "reach", "likes", "comments", "shares", "saves", "posts_count"]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """清洗标准 DataFrame，返回新 DataFrame（不修改输入）。

    增加列：`is_anomaly`（bool）—— True 表示该行的原始数据中至少一个数值列为负数或 followers 为 NaN。
    """
    if df.empty:
        out = df.copy()
        out["is_anomaly"] = pd.Series(dtype="bool")
        return out

    out = df.copy()

    # 1) 标记异常：任何数值列 < 0，或 followers 缺失
    anomaly_mask = pd.Series(False, index=out.index)
    for col in _NUMERIC_COLS:
        if col in out.columns:
            anomaly_mask |= out[col].fillna(0) < 0
    if "followers" in out.columns:
        anomaly_mask |= out["followers"].isna()
    out["is_anomaly"] = anomaly_mask

    # 2) 修正：负数截断为 0
    for col in _NUMERIC_COLS:
        if col in out.columns:
            out[col] = out[col].where(out[col].isna() | (out[col] >= 0), 0)

    # 3) 互动相关列的 NaN 填 0（followers 保留 NaN）
    for col in _INTERACTION_COLS:
        if col in out.columns:
            out[col] = out[col].fillna(0)

    # 4) date 兜底：data_loader 已 dropna，这里再保护
    if "date" in out.columns:
        before = len(out)
        out = out.dropna(subset=["date"]).reset_index(drop=True)
        after = len(out)
        if before > 0 and after == 0:
            # 全部行的 date 都是 NaT 被 dropna 清空 —— 用户大概率不知道为啥
            # 数据没了，给一个明确警告（这条会出现在 Streamlit Cloud 页面顶部）
            try:
                import streamlit as st
                st.error(
                    f"❌ data_cleaner: 输入 {before} 行，但所有行的 date 列都是 NaT，"
                    "全部被 dropna 丢弃，最终返回 0 行。"
                    "源头数据的 date 列格式可能不是 YYYY-MM-DD —— "
                    "请检查 Google Sheet 的 date 列单元格格式（Format → Number → Plain text）。"
                )
            except Exception:  # noqa: BLE001
                pass

    return out
