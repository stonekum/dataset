"""F04 — 衍生指标计算。

提供标量函数（单点计算）和 DataFrame 级别的批量函数（按平台分组、按日期排序后逐日推导）。

标量比率函数在分母为 0 时返回 0.0（不抛异常）。
DataFrame 级 enrich_dataframe 的 engagement_rate 例外：分母 exposure_base 为 0/NaN 时
结果为 NaN（不塌成 0），以便呈现层区分"无曝光数据"（N/A）与真实低互动。
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
        for col in ("exposure_base", "engagement_rate", "follower_growth", "follower_growth_rate"):
            out[col] = pd.Series(dtype="float64")
        return out

    out = df.copy().sort_values(["platform", "date"]).reset_index(drop=True)

    # 曝光基准 exposure_base = COALESCE(reach, impressions)（reach 优先）。
    # 各平台落点：FB/IG 有 reach（去重触达）→ 用 reach；YT/TikTok/LinkedIn 无 reach
    # → 回落 impressions（曝光/播放次数）。reach 与 impressions 皆 NaN → exposure_base
    # = NaN（呈现层显示 N/A，互动率不塌成 0）。
    # 关键：这是派生展示列，**不回写 impressions 原值**（impressions 的 NaN 仍保留），
    # 也不持久化到 Sheet（write 走原始 df，每次 enrich 重算）。
    reach = out["reach"] if "reach" in out.columns else pd.Series(np.nan, index=out.index)
    impressions = out["impressions"] if "impressions" in out.columns else pd.Series(np.nan, index=out.index)
    out["exposure_base"] = reach.fillna(impressions)

    # 互动率 = Σ互动 / exposure_base × 100（向量化）。
    # 分子用 skipna 求和（缺某个互动指标按 0 计入）；分母 exposure_base 为 0/NaN 时
    # 结果为 NaN（**不再 fillna(0)**）——区分"没有曝光数据"（NaN→N/A）与真实低互动。
    interactions = (
        out["likes"].fillna(0)
        + out["comments"].fillna(0)
        + out["shares"].fillna(0)
        + out["saves"].fillna(0)
    )
    base = out["exposure_base"].replace(0, np.nan)
    out["engagement_rate"] = interactions / base * 100

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
    metrics: Iterable[str] = (
        "impressions", "reach", "exposure_base",
        "likes", "comments", "shares", "saves", "follower_growth",
    ),
) -> pd.DataFrame:
    """按周期（W=周, M=月, Q=季）按平台聚合（求和），用于 wow/mom 计算和汇报视图。

    `followers` 取该周期的期末值（每周/每月最后一天的快照），其他指标求和。

    exposure_base 也在求和之列：它已由 enrich_dataframe 在**日级**算好（每天
    COALESCE(reach, impressions)），这里直接 Σexposure_base。**不要**用
    Σreach.fillna(Σimpressions)——跨天混合（某天有 reach、某天只有 impressions）会算错。
    周期互动率由调用方按 Σ互动 / Σexposure_base 重算（"先聚合再相除"，曝光加权）。
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
    # 只对实际存在的列求和：未 enrich 的 df 可能没有 exposure_base/reach，避免 KeyError
    present = [m for m in metrics if m in work.columns]
    sums = (
        work.groupby(["platform", grouper], observed=True)[present]
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


def weighted_engagement_rate(df: pd.DataFrame) -> float:
    """曝光加权互动率 = Σ(likes+comments+shares+saves) / Σexposure_base × 100。

    两视图统一口径（决策 #3）：对一组（已 enrich 的）日级行，先把互动与
    exposure_base 各自求和再相除（"先聚合再相除"），而非对逐日 engagement_rate
    取平均——后者会让低曝光日被过度加权。

    分子用 skipna 求和（某平台缺某个互动指标按 0 计入）；分母 Σexposure_base 为
    0 或全 NaN（没有任何曝光数据）时返回 NaN，呈现层显示 N/A（不塌成 0）。
    """
    if df is None or df.empty:
        return float("nan")
    interactions = 0.0
    for col in ("likes", "comments", "shares", "saves"):
        if col in df.columns:
            interactions += float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
    if "exposure_base" in df.columns:
        exposure = pd.to_numeric(df["exposure_base"], errors="coerce").sum(min_count=1)
    else:
        exposure = np.nan
    if pd.isna(exposure) or exposure == 0:
        return float("nan")
    return float(interactions / exposure * 100)
