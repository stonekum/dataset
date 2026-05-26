"""把本地 CSV 数据清空 Google Sheets 后整表写入（replace 模式）。

用法：
    cd <项目根目录>
    python scripts/push_to_sheets.py [CSV路径]

默认 CSV 路径：data/samples/april_may_2026_all_platforms.csv

前提条件：
    .streamlit/secrets.toml 中已配置 [gsheets] 区段（spreadsheet_url + service_account）

执行流程：
    1. 读取 CSV（仅保留 STANDARD_COLS）
    2. 清空 Sheet（replace 模式，旧数据全部删除）
    3. 写入新数据 + 打印写入结果
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

STANDARD_COLS = [
    "date", "platform", "followers", "impressions", "reach",
    "likes", "comments", "shares", "saves", "posts_count",
]


def main() -> int:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "data/samples/april_may_2026_all_platforms.csv"

    if not csv_path.exists():
        print(f"[error] CSV 文件不存在：{csv_path}")
        return 1

    df = pd.read_csv(csv_path)
    # 只保留标准列，缺失列补 NaN
    for col in STANDARD_COLS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[STANDARD_COLS]
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["date"]).sort_values(["platform", "date"]).reset_index(drop=True)

    print(f"[load] 读取 {csv_path.name}：{len(df)} 行，{df['platform'].nunique()} 个平台")
    print(f"[load] 平台分布：{df['platform'].value_counts().to_dict()}")
    print(f"[load] 日期范围：{df['date'].min()} ~ {df['date'].max()}")

    from utils.data_sources import GoogleSheetsSource, is_gsheets_configured

    if not is_gsheets_configured():
        print("[error] Google Sheets 未配置，请检查 .streamlit/secrets.toml 中的 [gsheets] 区段")
        return 1

    print("[sheets] 正在清空旧数据并写入新数据（replace 模式）…")
    result = GoogleSheetsSource().write(df, mode="replace")
    print(f"[sheets] 完成：写入 {result['written']} 行（新增 {result['added']}，更新 {result['updated']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
