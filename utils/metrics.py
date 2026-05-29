"""F04 — 衍生指标计算。

提供标量函数（单点计算）和 DataFrame 级别的批量函数（按平台分组、按日期排序后逐日推导）。

所有比率字段在分母为 0 时返回 0.0（不抛异常）。
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


# ---------- 标量函数 ----------

def _safe_div(numerator: float, denominator: float) -> float:
    """除法安全封装：分母为 0、NaN 或负数时返回 0.0。"""
    if denominator is None or denominator == 0:
        return 0.0
    try:
        d = float(denominator)
        n = float(numerator) if numerator is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(d) or d == 0:
        return 0.0
    if math.isnan(n):
        return 0.0
    return n / d


def calculate_engagement_rate(
    likes: float,
    comments: float,
    shares: float,
    saves: float,
    impressions: float,
) -> float:
    """互动率 = (likes + comments + shares + saves) / impressions * 100。

    任一互动字段为 None/NaN 时按 0 处理；impressions 为 0/NaN 时返回 0.0。
    """
    parts = [likes, comments, shares, saves]
    cleaned = [0.0 if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v) for v in parts]
    total = sum(cleaned)
    return _safe_div(total, impressions) * 100


def calculate_follower_growth(today: float, yesterday: float) -> float:
    """当日粉丝净增 = followers_today - followers_yesterday。任一为 NaN 返回 0。"""
    if today is None or yesterday is None:
        return 0.0
    try:
        t, y = float(today), float(yesterday)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(t) or math.isnan(y):
        return 0.0
    return t - y


def calculate_follower_growth_rate(today: float, yesterday: float) -> float:
    """粉丝增长率 = (today - yesterday) / yesterday * 100。分母为 0 返回 0.0。"""
    return _safe_div(calculate_follower_growth(today, yesterday), yesterday) * 100


def calculate_period_change(this_value: float, last_value: float) -> float:
    """通用周/月环比 = (this - last) / last * 100。分母为 0 返回 0.0。

    既可用于周环比（wow），也可用于月环比（mom），调用方传聚合后的两个标量即可。
    """
    if this_value is None or last_value is None:
        return 0.0
    try:
        t, l = float(this_value), float(last_value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(t) or math.isnan(l):
        return 0.0
    return _safe_div(t - l, l) * 100


# ---------- DataFrame 级别 ----------

def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """给标准 DataFrame 追加衍生字段：engagement_rate / follower_growth / follower_growth_rate。

    输入要求：包含 `date`、`platform` 及标准数值列。
    返回新的 DataFrame（不修改输入）。
    """
    if df.empty:
        out = df.copy()
        for col in ("engagement_rate", "follower_growth", "follower_growth_rate"):
            out[col] = pd.Series(dtype="float64")
        return out

    out = df.copy().sort_values(["platform", "date"]).reset_index(drop=True)

    # 互动率（向量化 + 除零保护）
    interactions = (
        out["likes"].fillna(0)
        + out["comments"].fillna(0)
        + out["shares"].fillna(0)
        + out["saves"].fillna(0)
    )
    impressions = out["impressions"].replace(0, np.nan)
    out["engagement_rate"] = (interactions / impressions * 100).fillna(0.0)

    # 粉丝净增 / 增长率：
    # - CSV 路径只有 followers 快照，需按平台 shift 算差值
    # - API 路径（YouTube subscribersGained-Lost / LinkedIn followerGains）会
    #   直接给当日净增；followers 可能仅在最后一天有快照，差值不可信，所以
    #   优先用源头 follower_growth，仅在它为 NaN 时回落到 shift 差值
    prev_followers = out.groupby("platform")["followers"].shift(1)
    computed_growth = out["followers"] - prev_followers
    if "follower_growth" in out.columns:
        out["follower_growth"] = (
            out["follower_growth"].fillna(computed_growth).fillna(0.0).astype(float)
        )
    else:
        out["follower_growth"] = computed_growth.fillna(0.0)
    safe_prev = prev_followers.replace(0, np.nan)
    out["follower_growth_rate"] = (out["follower_growth"] / safe_prev * 100).fillna(0.0)

    return out


def aggregate_by_period(
    df: pd.DataFrame,
    period: str,
    metrics: Iterable[str] = ("impressions", "likes", "comments", "shares", "saves", "follower_growth"),
) -> pd.DataFrame:
    """按周期（W=周, M=月, Q=季）按平台聚合（求和），用于 wow/mom 计算和汇报视图。

    `followers` 取该周期的期末值（每周/每月最后一天的快照），其他指标求和。
    """
    if df.empty:
        return df.copy()

    work = df.copy().sort_values(["platform", "date"]).reset_index(drop=True)
    period = period.upper()
    # pandas >=2.2 将 'M'/'Q' 重命名为 'ME'/'QE'（月末/季末锚点），保持向后兼容的输入
    freq_map = {"W": "W", "M": "ME", "Q": "QE"}
    if period not in freq_map:
        raise ValueError(f"period 必须是 'W' / 'M' / 'Q'，收到 {period!r}")
    freq = freq_map[period]

    grouper = pd.Grouper(key="date", freq=freq)
    sums = (
        work.groupby(["platform", grouper], observed=True)[list(metrics)]
        .sum(min_count=1)
        .reset_index()
    )
    last_followers = (
        work.groupby(["platform", grouper], observed=True)["followers"]
        .last()
        .reset_index()
    )
    merged = sums.merge(last_followers, on=["platform", "date"], how="left")
    return merged
