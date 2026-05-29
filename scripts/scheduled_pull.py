"""定时任务：每日从各平台 API 拉取最近 7 天数据并写入 Google Sheets。

由 GitHub Actions 调度执行。运行流程：
  1. 从环境变量构建 .streamlit/secrets.toml（绕过 Streamlit 运行时的 st.secrets 依赖）
  2. 逐平台调用 fetch()，单个失败不影响其他平台
  3. 合并 DataFrame 后 merge 写入 Google Sheets（若已配置）
  4. 打印汇总；遇到未捕获异常以非零退出，让工作流可见失败
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent.parent


def _esc(value: str) -> str:
    """转义 TOML 基本字符串字面值中的特殊字符。

    GCP service-account JSON 经 json.loads 后，private_key 字段内的 \\n 会被
    解码成真实换行；TOML 基本字符串不允许出现裸 LF/CR/Tab，必须转义回去，
    否则 secrets.toml 解析失败，所有平台 is_configured() 会兜底返回 False，
    定时任务静默 no-op。
    """
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _write_secrets_from_env() -> None:
    """根据环境变量生成 .streamlit/secrets.toml。

    缺失的区段直接跳过，使 is_configured() 返回 False。
    """
    secrets_dir = REPO_ROOT / ".streamlit"
    secrets_dir.mkdir(exist_ok=True)
    secrets_path = secrets_dir / "secrets.toml"

    lines: list[str] = []

    # Meta Graph
    meta_token = os.environ.get("META_ACCESS_TOKEN", "").strip()
    meta_page = os.environ.get("META_PAGE_ID", "").strip()
    meta_ig = os.environ.get("META_IG_USER_ID", "").strip()
    if meta_token and meta_page:
        lines.append("[meta_graph]")
        lines.append(f'page_access_token = "{_esc(meta_token)}"')
        lines.append(f'page_id = "{_esc(meta_page)}"')
        if meta_ig:
            lines.append(f'ig_user_id = "{_esc(meta_ig)}"')
        lines.append("")

    # YouTube
    yt_cid = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    yt_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    yt_refresh = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    if yt_cid and yt_secret and yt_refresh:
        lines.append("[youtube]")
        lines.append(f'client_id = "{_esc(yt_cid)}"')
        lines.append(f'client_secret = "{_esc(yt_secret)}"')
        lines.append(f'refresh_token = "{_esc(yt_refresh)}"')
        lines.append("")

    # LinkedIn
    li_token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
    li_org = os.environ.get("LINKEDIN_ORGANIZATION_ID", "").strip()
    if li_token and li_org:
        lines.append("[linkedin]")
        lines.append(f'access_token = "{_esc(li_token)}"')
        lines.append(f'organization_id = "{_esc(li_org)}"')
        lines.append("")

    # TikTok
    tt_token = os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
    tt_refresh = os.environ.get("TIKTOK_REFRESH_TOKEN", "").strip()
    tt_app = os.environ.get("TIKTOK_APP_ID", "").strip()
    tt_app_secret = os.environ.get("TIKTOK_APP_SECRET", "").strip()
    if tt_token and tt_refresh and tt_app and tt_app_secret:
        lines.append("[tiktok]")
        lines.append(f'access_token = "{_esc(tt_token)}"')
        lines.append(f'refresh_token = "{_esc(tt_refresh)}"')
        lines.append(f'app_id = "{_esc(tt_app)}"')
        lines.append(f'app_secret = "{_esc(tt_app_secret)}"')
        lines.append("")

    # Google Sheets
    gs_sheet = os.environ.get("GSHEETS_SHEET_ID", "").strip()
    gs_ws = os.environ.get("GSHEETS_WORKSHEET", "").strip()
    gs_sa_json = os.environ.get("GSHEETS_SERVICE_ACCOUNT_JSON", "").strip()
    if gs_sheet and gs_sa_json:
        import json
        try:
            sa = json.loads(gs_sa_json)
        except json.JSONDecodeError as exc:
            print(f"[warn] GSHEETS_SERVICE_ACCOUNT_JSON 不是合法 JSON：{exc}")
            sa = None
        if sa:
            lines.append("[gsheets]")
            # 支持传入完整 URL 或裸 sheet id
            if gs_sheet.startswith("http"):
                lines.append(f'spreadsheet_url = "{_esc(gs_sheet)}"')
            else:
                lines.append(
                    f'spreadsheet_url = "https://docs.google.com/spreadsheets/d/{_esc(gs_sheet)}/edit"'
                )
            if gs_ws:
                lines.append(f'worksheet_name = "{_esc(gs_ws)}"')
            lines.append("")
            lines.append("[gsheets.service_account]")
            for key, value in sa.items():
                if isinstance(value, str):
                    lines.append(f'{key} = "{_esc(value)}"')
                elif isinstance(value, bool):
                    lines.append(f"{key} = {'true' if value else 'false'}")
                elif isinstance(value, (int, float)):
                    lines.append(f"{key} = {value}")
            lines.append("")

    secrets_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[setup] wrote {secrets_path} ({len(lines)} lines)")


def _fetch_platform(name: str, fetch_callable, since: date, until: date) -> pd.DataFrame | None:
    """安全执行单个平台的拉取，失败时打印 traceback 返回 None。"""
    try:
        df = fetch_callable(since, until)
        if df is None or df.empty:
            print(f"[{name}] fetched 0 rows")
            return None
        print(f"[{name}] fetched {len(df)} rows")
        return df
    except Exception as exc:  # noqa: BLE001 - 这里就是要兜底
        print(f"[{name}] FAILED: {exc}")
        traceback.print_exc()
        return None


def main() -> int:
    _write_secrets_from_env()

    # 必须在写完 secrets 之后再导入这些模块
    from utils.meta_graph import MetaGraphSource
    from utils.youtube_api import YouTubeSource
    from utils.linkedin_api import LinkedInSource
    from utils.tiktok_api import TikTokSource
    from utils.data_sources import GoogleSheetsSource, is_gsheets_configured

    until = date.today()
    since = until - timedelta(days=7)
    print(f"[setup] date window: {since} → {until}")

    frames: list[pd.DataFrame] = []
    succeeded: list[str] = []

    # Meta（Facebook + Instagram 走同一个 source 的两个方法）
    if MetaGraphSource.is_configured():
        try:
            meta = MetaGraphSource.from_streamlit_secrets()
            fb_df = _fetch_platform("facebook", meta.fetch_facebook, since, until)
            if fb_df is not None:
                frames.append(fb_df)
                succeeded.append("facebook")
            ig_df = _fetch_platform("instagram", meta.fetch_instagram, since, until)
            if ig_df is not None:
                frames.append(ig_df)
                succeeded.append("instagram")
        except Exception as exc:  # noqa: BLE001
            print(f"[meta] init FAILED: {exc}")
            traceback.print_exc()
    else:
        print("[meta] not configured, skipping")

    # YouTube
    if YouTubeSource.is_configured():
        try:
            yt = YouTubeSource.from_streamlit_secrets()
            df = _fetch_platform("youtube", yt.fetch, since, until)
            if df is not None:
                frames.append(df)
                succeeded.append("youtube")
        except Exception as exc:  # noqa: BLE001
            print(f"[youtube] init FAILED: {exc}")
            traceback.print_exc()
    else:
        print("[youtube] not configured, skipping")

    # LinkedIn
    if LinkedInSource.is_configured():
        try:
            li = LinkedInSource.from_streamlit_secrets()
            df = _fetch_platform("linkedin", li.fetch, since, until)
            if df is not None:
                frames.append(df)
                succeeded.append("linkedin")
        except Exception as exc:  # noqa: BLE001
            print(f"[linkedin] init FAILED: {exc}")
            traceback.print_exc()
    else:
        print("[linkedin] not configured, skipping")

    # TikTok
    if TikTokSource.is_configured():
        try:
            tt = TikTokSource.from_streamlit_secrets()
            df = _fetch_platform("tiktok", tt.fetch, since, until)
            if df is not None:
                frames.append(df)
                succeeded.append("tiktok")
        except Exception as exc:  # noqa: BLE001
            print(f"[tiktok] init FAILED: {exc}")
            traceback.print_exc()
    else:
        print("[tiktok] not configured, skipping")

    if not frames:
        print("[summary] no platforms produced data; nothing to write")
        print(f"[summary] succeeded platforms: {succeeded or 'none'}")
        return 0

    combined = pd.concat(frames, ignore_index=True)
    print(f"[combine] total rows: {len(combined)}")

    if is_gsheets_configured():
        try:
            result = GoogleSheetsSource().write(combined, mode="merge")
            print(f"[sheets] write result: {result}")
        except Exception as exc:  # noqa: BLE001
            print(f"[sheets] write FAILED: {exc}")
            traceback.print_exc()
            return 2
    else:
        print("[sheets] not configured, skipping write")

    print(f"[summary] succeeded platforms: {succeeded}")
    return 0


if __name__ == "__main__":
    # 让 `import utils.*` 能找到 utils 包
    sys.path.insert(0, str(REPO_ROOT))
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - 顶层兜底以非零退出
        print(f"[fatal] {exc}")
        traceback.print_exc()
        sys.exit(1)
