"""F02 — 生成六平台 ~90 天模拟运营数据，合并为一份标准化 demo CSV。

输出 data/samples/demo_all_platforms.csv，使用**标准列名**（见 CLAUDE.md 标准字段表），
而非各平台原生格式——作为「无 Google Sheet、无上传」时的纯 demo 兜底
（数据管线整顿决策 #2：唯一可信源是 Google Sheet，data/samples 仅作 demo）。

平台指标可用性刻意贴近真实，用来演示 exposure_base 与 N/A：
- FB / IG 有 reach（exposure_base 用 reach）；YT / TikTok / X / LinkedIn 无 reach，
  留空（→ NaN），exposure_base 回落 impressions。
- 仅 IG 有 saves；其余平台 saves 留空（→ NaN），呈现层显示 N/A
  （演示"平台没这个指标" ≠ "真的是 0"）。
- YouTube 无 shares，留空（→ NaN）。

可重跑：固定随机种子，每次结果一致；旧文件直接覆盖。
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# 数据规格
DAYS = 90
END_DATE = date(2026, 5, 30)  # 截止到"昨天"（相对 CLAUDE.md 中的 currentDate 2026-05-31）
START_DATE = END_DATE - timedelta(days=DAYS - 1)
SAMPLES_DIR = Path("data/samples")
OUTPUT_FILE = SAMPLES_DIR / "demo_all_platforms.csv"
SEED = 20260531

# 标准列（与 utils.data_loader.STANDARD_COLS 一致）
STANDARD_COLUMNS = [
    "date", "platform", "followers", "impressions", "reach",
    "likes", "comments", "shares", "saves", "posts_count",
]


@dataclass
class PlatformSpec:
    """单个平台的合成参数。

    `reach_ratio_range` / `save_rate_range` / `share_rate_range` 为 None（或 share 上界为 0）
    表示该平台没有这个指标——demo 里对应单元格留空（→ NaN），演示 N/A。
    """

    name: str  # 平台标准名
    base_followers: int
    daily_follower_delta_range: tuple[int, int]  # 当日粉丝净增的均匀分布区间
    impressions_per_follower_range: tuple[float, float]  # 每粉丝当日曝光乘数
    like_rate_range: tuple[float, float]  # 点赞 / 曝光
    comment_rate_range: tuple[float, float]
    share_rate_range: tuple[float, float] | None  # None / (0,0) 表示无转发字段
    save_rate_range: tuple[float, float] | None  # None 表示该平台无收藏字段
    reach_ratio_range: tuple[float, float] | None  # 触达 / 曝光，None 表示无该字段


PLATFORMS: dict[str, PlatformSpec] = {
    "instagram": PlatformSpec(
        name="instagram",
        base_followers=82_000,
        daily_follower_delta_range=(30, 180),
        impressions_per_follower_range=(0.25, 0.55),
        like_rate_range=(0.03, 0.06),
        comment_rate_range=(0.002, 0.005),
        share_rate_range=(0.004, 0.010),
        save_rate_range=(0.005, 0.012),
        reach_ratio_range=(0.55, 0.80),
    ),
    "tiktok": PlatformSpec(
        name="tiktok",
        base_followers=215_000,
        daily_follower_delta_range=(120, 620),
        impressions_per_follower_range=(0.80, 2.20),
        like_rate_range=(0.04, 0.08),
        comment_rate_range=(0.002, 0.006),
        share_rate_range=(0.003, 0.008),
        save_rate_range=None,
        reach_ratio_range=None,
    ),
    "youtube": PlatformSpec(
        name="youtube",
        base_followers=48_500,
        daily_follower_delta_range=(15, 95),
        impressions_per_follower_range=(0.10, 0.35),
        like_rate_range=(0.020, 0.045),
        comment_rate_range=(0.001, 0.003),
        share_rate_range=(0.0, 0.0),  # YouTube 无 shares → 留空
        save_rate_range=None,
        reach_ratio_range=None,
    ),
    "x": PlatformSpec(
        name="x",
        base_followers=31_200,
        daily_follower_delta_range=(5, 60),
        impressions_per_follower_range=(0.40, 1.20),
        like_rate_range=(0.010, 0.030),
        comment_rate_range=(0.0008, 0.003),
        share_rate_range=(0.002, 0.008),
        save_rate_range=None,
        reach_ratio_range=None,
    ),
    "facebook": PlatformSpec(
        name="facebook",
        base_followers=128_000,
        daily_follower_delta_range=(10, 95),
        impressions_per_follower_range=(0.15, 0.40),
        like_rate_range=(0.008, 0.025),
        comment_rate_range=(0.0008, 0.003),
        share_rate_range=(0.001, 0.005),
        save_rate_range=None,
        reach_ratio_range=(0.50, 0.75),
    ),
    "linkedin": PlatformSpec(
        name="linkedin",
        base_followers=22_400,
        daily_follower_delta_range=(5, 45),
        impressions_per_follower_range=(0.20, 0.55),
        like_rate_range=(0.020, 0.050),
        comment_rate_range=(0.001, 0.004),
        share_rate_range=(0.002, 0.007),
        save_rate_range=None,
        reach_ratio_range=None,
    ),
}


def _daterange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _simulate_followers(spec: PlatformSpec, rng: random.Random) -> list[int]:
    """生成 90 天的粉丝时间序列：每日净增取均匀分布，保证递增（允许偶发小幅波动）。"""
    series = [spec.base_followers]
    lo, hi = spec.daily_follower_delta_range
    for _ in range(DAYS - 1):
        delta = rng.randint(lo, hi)
        # 5% 概率出现一次小幅取关（避免单调到失真）
        if rng.random() < 0.05:
            delta = -rng.randint(0, max(1, lo // 2))
        series.append(series[-1] + delta)
    return series


def _daily_row(spec: PlatformSpec, followers: int, rng: random.Random) -> dict[str, object]:
    """根据粉丝数和速率区间生成当日指标。

    平台没有的指标返回 None —— 写进 CSV 是空单元格，pandas 读回来即 NaN，
    交给下游 exposure_base COALESCE 与呈现层 N/A 处理（不再用 0 假装"有数据"）。
    """
    imp_mult = rng.uniform(*spec.impressions_per_follower_range)
    impressions = max(0, int(followers * imp_mult))
    likes = int(impressions * rng.uniform(*spec.like_rate_range))
    comments = int(impressions * rng.uniform(*spec.comment_rate_range))
    has_shares = spec.share_rate_range is not None and spec.share_rate_range[1] > 0
    shares = int(impressions * rng.uniform(*spec.share_rate_range)) if has_shares else None
    saves = int(impressions * rng.uniform(*spec.save_rate_range)) if spec.save_rate_range else None
    reach = int(impressions * rng.uniform(*spec.reach_ratio_range)) if spec.reach_ratio_range else None
    posts_count = rng.randint(0, 3)
    return {
        "impressions": impressions,
        "reach": reach,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "saves": saves,
        "posts_count": posts_count,
    }


def generate() -> Path:
    """生成所有平台的合并 demo CSV，返回输出路径。"""
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[list[object]] = []
    for platform, spec in PLATFORMS.items():
        rng = random.Random(f"{SEED}-{platform}")
        followers_series = _simulate_followers(spec, rng)
        for d, fol in zip(_daterange(START_DATE, END_DATE), followers_series):
            m = _daily_row(spec, fol, rng)
            rows.append([
                d.isoformat(), platform, fol,
                m["impressions"], m["reach"], m["likes"], m["comments"],
                m["shares"], m["saves"], m["posts_count"],
            ])
    # 按 (platform, date) 排序，与 load_all_data 的排序一致，便于人工对照
    rows.sort(key=lambda r: (r[1], r[0]))
    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(STANDARD_COLUMNS)
        w.writerows(rows)  # None → 空单元格
    return OUTPUT_FILE


if __name__ == "__main__":
    print(f"生成标准化 demo → {OUTPUT_FILE}")
    out = generate()
    with out.open(encoding="utf-8") as fh:
        n_rows = sum(1 for _ in fh) - 1
    print(f"完成：{out}（{n_rows} 行，{START_DATE} → {END_DATE}，{len(PLATFORMS)} 个平台）")
