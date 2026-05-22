"""F02 — 生成六个平台 90 天的模拟运营数据 CSV，写入 data/samples/。

每个平台一个 CSV，字段沿用各平台原生导出格式（见 CLAUDE.md 各平台字段映射表），
便于 F03 的 data_loader 通过表头识别来源。

可重跑：固定随机种子，每次运行结果一致；旧文件直接覆盖。
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# 数据规格
DAYS = 90
END_DATE = date(2026, 5, 21)  # 截止到"昨天"（相对 CLAUDE.md 中的 currentDate 2026-05-22）
START_DATE = END_DATE - timedelta(days=DAYS - 1)
SAMPLES_DIR = Path("data/samples")
SEED = 20260522


@dataclass
class PlatformSpec:
    """单个平台的合成参数。"""

    name: str  # 文件名前缀
    base_followers: int
    daily_follower_delta_range: tuple[int, int]  # 当日粉丝净增的均匀分布区间
    impressions_per_follower_range: tuple[float, float]  # 每粉丝当日曝光乘数
    like_rate_range: tuple[float, float]  # 点赞 / 曝光
    comment_rate_range: tuple[float, float]
    share_rate_range: tuple[float, float]
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
        share_rate_range=(0.0, 0.0),
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


def _daily_row(spec: PlatformSpec, followers: int, rng: random.Random) -> dict[str, int]:
    """根据粉丝数和速率区间生成当日互动数据。"""
    imp_mult = rng.uniform(*spec.impressions_per_follower_range)
    impressions = max(0, int(followers * imp_mult))
    likes = int(impressions * rng.uniform(*spec.like_rate_range))
    comments = int(impressions * rng.uniform(*spec.comment_rate_range))
    shares = int(impressions * rng.uniform(*spec.share_rate_range))
    saves = int(impressions * rng.uniform(*spec.save_rate_range)) if spec.save_rate_range else 0
    reach = int(impressions * rng.uniform(*spec.reach_ratio_range)) if spec.reach_ratio_range else 0
    return {
        "impressions": impressions,
        "reach": reach,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "saves": saves,
    }


# 各平台原生 CSV 表头与映射规则（与 CLAUDE.md 字段映射表一致）
def _write_instagram(path: Path, rows: list[tuple[date, int, dict[str, int]]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Followers", "Impressions", "Reach", "Likes", "Comments", "Shares", "Saves"])
        for d, fol, m in rows:
            w.writerow([d.isoformat(), fol, m["impressions"], m["reach"], m["likes"], m["comments"], m["shares"], m["saves"]])


def _write_tiktok(path: Path, rows: list[tuple[date, int, dict[str, int]]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Followers", "Video Views", "Likes", "Comments", "Shares"])
        for d, fol, m in rows:
            w.writerow([d.isoformat(), fol, m["impressions"], m["likes"], m["comments"], m["shares"]])


def _write_youtube(path: Path, rows: list[tuple[date, int, dict[str, int]]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Subscribers", "Views", "Likes", "Comments"])
        for d, fol, m in rows:
            w.writerow([d.isoformat(), fol, m["impressions"], m["likes"], m["comments"]])


def _write_x(path: Path, rows: list[tuple[date, int, dict[str, int]]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Followers", "Impressions", "Likes", "Replies", "Retweets"])
        for d, fol, m in rows:
            w.writerow([d.isoformat(), fol, m["impressions"], m["likes"], m["comments"], m["shares"]])


def _write_facebook(path: Path, rows: list[tuple[date, int, dict[str, int]]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Page Followers", "Impressions", "Reach", "Reactions", "Comments", "Shares"])
        for d, fol, m in rows:
            w.writerow([d.isoformat(), fol, m["impressions"], m["reach"], m["likes"], m["comments"], m["shares"]])


def _write_linkedin(path: Path, rows: list[tuple[date, int, dict[str, int]]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Total followers", "Impressions", "Reactions", "Comments", "Shares"])
        for d, fol, m in rows:
            w.writerow([d.isoformat(), fol, m["impressions"], m["likes"], m["comments"], m["shares"]])


WRITERS = {
    "instagram": _write_instagram,
    "tiktok": _write_tiktok,
    "youtube": _write_youtube,
    "x": _write_x,
    "facebook": _write_facebook,
    "linkedin": _write_linkedin,
}


def generate() -> list[Path]:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for platform, spec in PLATFORMS.items():
        rng = random.Random(f"{SEED}-{platform}")
        followers_series = _simulate_followers(spec, rng)
        rows = [
            (d, fol, _daily_row(spec, fol, rng))
            for d, fol in zip(_daterange(START_DATE, END_DATE), followers_series)
        ]
        out = SAMPLES_DIR / f"{platform}.csv"
        WRITERS[platform](out, rows)
        written.append(out)
        print(f"  生成 {out}（{len(rows)} 行，{rows[0][0]} → {rows[-1][0]}）")
    return written


if __name__ == "__main__":
    print(f"生成示例数据 → {SAMPLES_DIR}/")
    paths = generate()
    print(f"完成，共 {len(paths)} 个 CSV。")
