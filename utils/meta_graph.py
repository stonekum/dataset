"""Meta Graph API 数据拉取模块。

负责从 Facebook Page Insights 和 Instagram Business Account Insights
拉取每日指标，输出符合项目标准列结构的 DataFrame。

依赖 secrets.toml 中的 [meta_graph] 区段（见 .streamlit/secrets.toml.example）。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import requests

from utils.api_base import APIConfigError, APIError, APISourceBase
from utils.data_loader import STANDARD_COLS, _ensure_standard_shape
from utils.logging import emit_warning

logger = logging.getLogger(__name__)

_API_BASE = "https://graph.facebook.com/v21.0"
_TIMEOUT = 20  # 秒（仅 _get_all_pages 翻页时还在用）

# Facebook Page Insights 需要的指标
_FB_METRICS = [
    "page_impressions",        # 日曝光
    "page_post_engagements",   # 日帖互动（likes+comments+shares 综合）
    "page_fans",               # 粉丝总数（每日快照）
]

# Instagram Business Account Insights 需要的指标
_IG_ACCOUNT_METRICS = [
    "impressions",    # 日曝光
    "reach",          # 日触达
    "follower_count", # 粉丝总数（每日快照）
]

# IG 媒体每条帖子可拿到的字段（聚合后得到 likes + comments）
_IG_MEDIA_FIELDS = "id,timestamp,like_count,comments_count"


class MetaGraphConfigError(APIConfigError):
    pass


class MetaGraphAPIError(APIError):
    """Graph API 错误。`meta_error` 是 `extra` 的别名（向后兼容）。"""

    @property
    def meta_error(self) -> dict:
        return self.extra


def _is_configured() -> bool:
    return MetaGraphSource.is_configured()


class MetaGraphSource(APISourceBase):
    """从 Meta Graph API 拉取 Facebook Page + Instagram 数据的客户端。"""

    SECRETS_SECTION = "meta_graph"
    REQUIRED_FIELDS = ("page_access_token", "page_id")
    CONFIG_ERROR_CLS = MetaGraphConfigError
    API_ERROR_CLS = MetaGraphAPIError

    def __init__(self, access_token: str, page_id: str, ig_user_id: str | None = None):
        self.token = access_token
        self.page_id = str(page_id)
        self.ig_user_id = str(ig_user_id) if ig_user_id else None

    @classmethod
    def from_streamlit_secrets(cls) -> "MetaGraphSource":
        cfg = cls._load_secrets()
        return cls(
            access_token=cfg["page_access_token"],
            page_id=cfg["page_id"],
            ig_user_id=cfg.get("ig_user_id") or None,
        )

    # ------------------------------------------------------------------
    # 底层 HTTP 工具
    # ------------------------------------------------------------------

    def _get(self, path: str, **params) -> dict[str, Any]:
        """对 Graph API 发出 GET 请求，自动加 access_token，复用 base 的重试机制。"""
        url = f"{_API_BASE}/{path.lstrip('/')}"
        params["access_token"] = self.token
        resp = self._request("GET", url, params=params)
        if resp.status_code == 200:
            data = resp.json()
            if "error" in data:
                err = data["error"]
                raise MetaGraphAPIError(
                    f"Meta API 错误 {err.get('code')}: {err.get('message')}",
                    status_code=resp.status_code,
                    extra=err,
                )
            return data
        try:
            err = resp.json().get("error", {})
        except Exception:  # noqa: BLE001
            err = {}
        raise MetaGraphAPIError(
            f"HTTP {resp.status_code}: {err.get('message', resp.text[:200])}",
            status_code=resp.status_code,
            extra=err,
        )

    def _get_all_pages(self, path: str, **params) -> list[dict]:
        """自动翻页，返回所有 data 列表元素。"""
        results = []
        data = self._get(path, **params)
        results.extend(data.get("data", []))
        while True:
            next_url = data.get("paging", {}).get("next")
            if not next_url:
                break
            resp = requests.get(next_url, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("data", []))
        return results

    # ------------------------------------------------------------------
    # Facebook Page
    # ------------------------------------------------------------------

    def fetch_facebook(self, since: date, until: date) -> pd.DataFrame:
        """拉取 Facebook Page 每日指标，返回标准列 DataFrame（platform=facebook）。

        覆盖字段：followers, impressions, likes（来自 page_post_engagements 综合值）
        """
        since_str = since.isoformat()
        until_str = (until + timedelta(days=1)).isoformat()  # API until 是开区间

        raw = self._get(
            f"{self.page_id}/insights",
            metric=",".join(_FB_METRICS),
            period="day",
            since=since_str,
            until=until_str,
        )

        # 把每个指标的 values 列表合并成 {date -> {metric: value}}
        day_map: dict[str, dict[str, Any]] = {}
        for metric_obj in raw.get("data", []):
            name = metric_obj["name"]
            for entry in metric_obj.get("values", []):
                # end_time 格式：'2024-01-02T08:00:00+0000'，取日期部分
                day = entry["end_time"][:10]
                if day not in day_map:
                    day_map[day] = {}
                day_map[day][name] = entry["value"]

        if not day_map:
            return _ensure_standard_shape(pd.DataFrame(), platform=None)

        rows = []
        for day_str, metrics in sorted(day_map.items()):
            rows.append({
                "date": day_str,
                "platform": "facebook",
                "followers": metrics.get("page_fans"),
                "impressions": metrics.get("page_impressions"),
                "likes": metrics.get("page_post_engagements"),  # 最接近 engagement 的 proxy
            })

        df = pd.DataFrame(rows)
        return _ensure_standard_shape(df, platform="facebook")

    # ------------------------------------------------------------------
    # Instagram Business Account
    # ------------------------------------------------------------------

    def fetch_instagram(self, since: date, until: date) -> pd.DataFrame:
        """拉取 Instagram Business Account 每日指标，返回标准列 DataFrame。

        覆盖字段：followers, impressions, reach, likes, comments（后两者来自帖子聚合）
        """
        if not self.ig_user_id:
            raise MetaGraphConfigError(
                "secrets.toml 缺少 ig_user_id，无法拉取 Instagram 数据。"
            )

        since_str = since.isoformat()
        until_str = (until + timedelta(days=1)).isoformat()

        # 1. 账号级别每日指标（曝光 / 触达 / 粉丝）
        raw = self._get(
            f"{self.ig_user_id}/insights",
            metric=",".join(_IG_ACCOUNT_METRICS),
            period="day",
            since=since_str,
            until=until_str,
        )

        day_map: dict[str, dict[str, Any]] = {}
        for metric_obj in raw.get("data", []):
            name = metric_obj["name"]
            for entry in metric_obj.get("values", []):
                day = entry["end_time"][:10]
                if day not in day_map:
                    day_map[day] = {}
                day_map[day][name] = entry["value"]

        # 2. 媒体列表 → 聚合每日 likes + comments
        media_items = self._fetch_ig_media_in_range(since, until)
        for item in media_items:
            ts = item.get("timestamp", "")
            day = ts[:10] if ts else None
            if not day:
                continue
            if day not in day_map:
                day_map[day] = {}
            day_map[day]["media_likes"] = (
                day_map[day].get("media_likes", 0) + (item.get("like_count") or 0)
            )
            day_map[day]["media_comments"] = (
                day_map[day].get("media_comments", 0) + (item.get("comments_count") or 0)
            )
            day_map[day]["posts_count"] = day_map[day].get("posts_count", 0) + 1

        if not day_map:
            return _ensure_standard_shape(pd.DataFrame(), platform=None)

        rows = []
        for day_str, m in sorted(day_map.items()):
            rows.append({
                "date": day_str,
                "platform": "instagram",
                "followers": m.get("follower_count"),
                "impressions": m.get("impressions"),
                "reach": m.get("reach"),
                "likes": m.get("media_likes"),
                "comments": m.get("media_comments"),
                "posts_count": m.get("posts_count"),
            })

        df = pd.DataFrame(rows)
        return _ensure_standard_shape(df, platform="instagram")

    def _fetch_ig_media_in_range(self, since: date, until: date) -> list[dict]:
        """拉取时间范围内发布的媒体列表（帖子），返回含 like_count / comments_count 的列表。"""
        try:
            items = self._get_all_pages(
                f"{self.ig_user_id}/media",
                fields=_IG_MEDIA_FIELDS,
                since=since.isoformat(),
                until=(until + timedelta(days=1)).isoformat(),
                limit=100,
            )
        except MetaGraphAPIError as exc:
            emit_warning(f"拉取 IG 媒体列表失败，likes/comments 将为空：{exc}")
            return []
        # 过滤时间范围（API 有时返回边界外数据）
        result = []
        for item in items:
            ts = item.get("timestamp", "")
            if not ts:
                continue
            try:
                item_date = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
            except ValueError:
                item_date = date.fromisoformat(ts[:10])
            if since <= item_date <= until:
                result.append(item)
        return result

    # ------------------------------------------------------------------
    # 一次性拉取 FB + IG
    # ------------------------------------------------------------------

    def fetch_all(self, since: date, until: date, *, fb: bool = True, ig: bool = True) -> pd.DataFrame:
        """拉取所选平台数据并合并，返回标准列 DataFrame。"""
        frames = []
        if fb:
            frames.append(self.fetch_facebook(since, until))
        if ig and self.ig_user_id:
            frames.append(self.fetch_instagram(since, until))
        if not frames:
            return _ensure_standard_shape(pd.DataFrame(), platform=None)
        return pd.concat(frames, ignore_index=True, sort=False)

    # ------------------------------------------------------------------
    # Token 健康检查
    # ------------------------------------------------------------------

    def check_token(self) -> dict[str, Any]:
        """验证 access_token 是否有效，返回 {valid, expires_at, scopes}。"""
        data = self._get("debug_token", input_token=self.token)
        info = data.get("data", {})
        expires_at = None
        if info.get("expires_at"):
            expires_at = datetime.fromtimestamp(info["expires_at"]).date()
        return {
            "valid": info.get("is_valid", False),
            "expires_at": expires_at,
            "scopes": info.get("scopes", []),
            "app_id": info.get("app_id"),
            "type": info.get("type"),
        }
