"""YouTube Data API v3 + YouTube Analytics API v2 数据拉取模块。

使用 OAuth 2.0 refresh_token 鉴权（一次授权，永久有效直到撤销）。
输出符合项目标准列结构的 DataFrame（platform='youtube'）。

覆盖字段：followers(subscribers), impressions(views), likes, comments,
          shares, follower_growth(subscribersGained - subscribersLost)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from utils.api_base import APIConfigError, APIError, APISourceBase
from utils.data_loader import _ensure_standard_shape
from utils.logging import emit_warning

logger = logging.getLogger(__name__)

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_ANALYTICS_BASE = "https://youtubeanalytics.googleapis.com/v2"
_DATA_BASE = "https://www.googleapis.com/youtube/v3"

# YouTube Analytics API 每日指标
_DAILY_METRICS = "views,likes,comments,shares,subscribersGained,subscribersLost"


class YouTubeConfigError(APIConfigError):
    pass


class YouTubeAPIError(APIError):
    pass


def _is_configured() -> bool:
    return YouTubeSource.is_configured()


class YouTubeSource(APISourceBase):
    """YouTube Analytics 数据拉取客户端。"""

    SECRETS_SECTION = "youtube"
    REQUIRED_FIELDS = ("client_id", "client_secret", "refresh_token")
    CONFIG_ERROR_CLS = YouTubeConfigError
    API_ERROR_CLS = YouTubeAPIError

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._access_token: str | None = None

    @classmethod
    def from_streamlit_secrets(cls) -> "YouTubeSource":
        cfg = cls._load_secrets()
        return cls(cfg["client_id"], cfg["client_secret"], cfg["refresh_token"])

    # ------------------------------------------------------------------
    # OAuth token 管理
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """用 refresh_token 换取 access_token（OAuth 端点用 form-encoded，绕过统一 _request）。"""
        import requests
        resp = requests.post(
            _TOKEN_URI,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        if resp.status_code != 200:
            raise YouTubeAPIError(
                f"Token 刷新失败 (HTTP {resp.status_code}): {resp.text[:300]}\n"
                "请确认 client_id / client_secret / refresh_token 正确，"
                "且 OAuth 凭证未被撤销。"
            )
        data = resp.json()
        if "error" in data:
            raise YouTubeAPIError(
                f"Token 刷新错误：{data.get('error')} — {data.get('error_description')}"
            )
        return data["access_token"]

    def _headers(self) -> dict:
        if not self._access_token:
            self._access_token = self._get_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _get(self, base: str, path: str, **params) -> dict[str, Any]:
        url = f"{base}/{path.lstrip('/')}"
        resp = self._request("GET", url, headers=self._headers(), params=params)
        if resp.status_code == 401:
            # token 过期，强制刷新后再试
            self._access_token = self._get_access_token()
            resp = self._request("GET", url, headers=self._headers(), params=params)
        if resp.status_code != 200:
            raise YouTubeAPIError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if "error" in data:
            err = data["error"]
            code = err.get("code") or err.get("errors", [{}])[0].get("reason", "")
            raise YouTubeAPIError(f"API 错误 {code}: {err.get('message')}")
        return data

    # ------------------------------------------------------------------
    # 数据拉取
    # ------------------------------------------------------------------

    def fetch(self, since: date, until: date) -> pd.DataFrame:
        """拉取 YouTube 频道每日分析数据，返回标准列 DataFrame。"""
        # 1. 每日指标（Analytics API）
        analytics = self._get(
            _ANALYTICS_BASE, "reports",
            ids="channel==MINE",
            startDate=since.isoformat(),
            endDate=until.isoformat(),
            metrics=_DAILY_METRICS,
            dimensions="day",
        )

        if not analytics.get("rows"):
            return _ensure_standard_shape(pd.DataFrame(), platform=None)

        # 构建列名映射
        col_names = [h["name"] for h in analytics["columnHeaders"]]
        df_raw = pd.DataFrame(analytics["rows"], columns=col_names)
        df_raw = df_raw.rename(columns={
            "day": "date",
            "views": "impressions",
            "likes": "likes",
            "comments": "comments",
            "shares": "shares",
            "subscribersGained": "_subs_gained",
            "subscribersLost": "_subs_lost",
        })
        df_raw["follower_growth"] = (
            df_raw.get("_subs_gained", 0).fillna(0).astype(int)
            - df_raw.get("_subs_lost", 0).fillna(0).astype(int)
        )
        df_raw["platform"] = "youtube"

        # 2. 频道总订阅数（每次取当前快照，Analytics API 不直接给历史绝对值）
        try:
            channel_data = self._get(
                _DATA_BASE, "channels",
                part="statistics",
                mine="true",
            )
            items = channel_data.get("items", [])
            if items:
                subs = int(items[0]["statistics"].get("subscriberCount", 0))
                # 将总量填到最后一天（其余天只有增量）
                last_day = df_raw["date"].max()
                df_raw.loc[df_raw["date"] == last_day, "followers"] = subs
        except YouTubeAPIError as exc:
            emit_warning(f"无法拉取频道订阅数：{exc}")

        return _ensure_standard_shape(df_raw, platform="youtube")

    def check_token(self) -> dict[str, Any]:
        """验证 refresh_token 是否能正常换 access_token。"""
        try:
            token = self._get_access_token()
            return {"valid": bool(token), "error": None}
        except YouTubeAPIError as exc:
            return {"valid": False, "error": str(exc)}
