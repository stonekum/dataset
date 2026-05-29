"""一次性回填 Meta（Facebook + Instagram）历史数据到 Google Sheets。

调用方式：
    python scripts/backfill.py [--since YYYY-MM-DD] [--until YYYY-MM-DD] \
                               [--chunk-days N] [--platforms fb,ig]

- 默认窗口：until=今天，since=今天-365 天
- 默认 chunk：60 天（Meta API 单次返回 ~93 行上限以下安全）
- 默认平台：fb,ig 都拉

仅最后一个 chunk（即包含 until 的那段）会调用 ?fields=followers_count 取当前粉丝
总数快照填到末日；早期 chunk 不取，避免把"今天的总数"打到历史某天。

由 .github/workflows/backfill.yml 触发，secrets 从环境变量构造，复用
scripts.scheduled_pull._write_secrets_from_env 的逻辑。
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent.parent


def _parse_date(s: str | None, default: date) -> date:
    if not s:
        return default
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def _iter_chunks(since: date, until: date, chunk_days: int):
    """按 chunk_days 步长生成 (chunk_since, chunk_until) 对，闭区间。"""
    cur = since
    while cur <= until:
        chunk_until = min(cur + timedelta(days=chunk_days - 1), until)
        yield cur, chunk_until
        cur = chunk_until + timedelta(days=1)


def _safe_fetch(name: str, fetch_callable, *args, **kwargs) -> pd.DataFrame | None:
    """安全调单个 fetch，失败时 traceback 但不中断。"""
    try:
        df = fetch_callable(*args, **kwargs)
        if df is None or df.empty:
            print(f"    [{name}] 0 rows")
            return None
        print(f"    [{name}] {len(df)} rows")
        return df
    except Exception as exc:  # noqa: BLE001
        print(f"    [{name}] FAILED: {exc}")
        traceback.print_exc()
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Meta historical data to Google Sheets")
    parser.add_argument("--since", help="回填起始日 YYYY-MM-DD（默认：365 天前）")
    parser.add_argument("--until", help="回填结束日 YYYY-MM-DD（默认：今天）")
    parser.add_argument("--chunk-days", type=int, default=60,
                        help="每个 chunk 的天数（默认 60，Meta API 上限约 93 天）")
    parser.add_argument("--platforms", default="fb,ig",
                        help="逗号分隔，可选 fb / ig（默认全部）")
    args = parser.parse_args()

    today = date.today()
    until = _parse_date(args.until, today)
    since = _parse_date(args.since, until - timedelta(days=365))
    if since > until:
        print(f"[fatal] since ({since}) 晚于 until ({until})")
        return 1

    enabled = {p.strip().lower() for p in args.platforms.split(",") if p.strip()}
    print(f"[setup] window: {since} → {until} ({(until - since).days + 1} days)")
    print(f"[setup] chunk_days={args.chunk_days}")
    print(f"[setup] platforms: {sorted(enabled)}")

    # 复用 scheduled_pull 的 secrets-from-env 写入逻辑
    from scripts.scheduled_pull import _write_secrets_from_env
    _write_secrets_from_env()

    # 必须在 secrets.toml 落盘之后再导入
    from utils.meta_graph import MetaGraphSource
    from utils.data_sources import GoogleSheetsSource, is_gsheets_configured

    if not MetaGraphSource.is_configured():
        print("[fatal] meta_graph 未配置（META_ACCESS_TOKEN / META_PAGE_ID 缺失）")
        return 1
    if not is_gsheets_configured():
        print("[fatal] gsheets 未配置；回填没地方落盘")
        return 1

    meta = MetaGraphSource.from_streamlit_secrets()

    chunks = list(_iter_chunks(since, until, args.chunk_days))
    print(f"[setup] split into {len(chunks)} chunk(s)")

    all_frames: list[pd.DataFrame] = []
    for idx, (chunk_since, chunk_until) in enumerate(chunks):
        is_last = idx == len(chunks) - 1
        print(f"[chunk {idx + 1}/{len(chunks)}] {chunk_since} → {chunk_until}"
              f"  (snapshot={'YES' if is_last else 'no'})")

        if "fb" in enabled:
            fb_df = _safe_fetch(
                "facebook", meta.fetch_facebook,
                chunk_since, chunk_until,
                include_total_snapshot=is_last,
            )
            if fb_df is not None:
                all_frames.append(fb_df)

        if "ig" in enabled:
            ig_df = _safe_fetch(
                "instagram", meta.fetch_instagram,
                chunk_since, chunk_until,
                include_total_snapshot=is_last,
            )
            if ig_df is not None:
                all_frames.append(ig_df)

    if not all_frames:
        print("[summary] no data fetched; nothing to write")
        return 0

    combined = pd.concat(all_frames, ignore_index=True, sort=False)
    # 同一 (platform, date) 可能在 chunk 边界重复出现一次，去重保留最后
    combined = combined.sort_values(["platform", "date"]).drop_duplicates(
        subset=["platform", "date"], keep="last"
    ).reset_index(drop=True)
    print(f"[combine] total rows after dedup: {len(combined)}")

    try:
        result = GoogleSheetsSource().write(combined, mode="merge")
        print(f"[sheets] write result: {result}")
    except Exception as exc:  # noqa: BLE001
        print(f"[sheets] write FAILED: {exc}")
        traceback.print_exc()
        return 2

    print("[summary] backfill complete ✓")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[fatal] {exc}")
        traceback.print_exc()
        sys.exit(1)
