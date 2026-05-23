"""TikTok Business API 数据拉取模块。

⚠️  重要说明：TikTok 官方 API 对有机（organic）内容的日粒度数据支持有限。
  - Business API 主要面向付费广告主，有机数据接口较少
  - 账号概览接口（/business/get/）返回粉丝/点赞等累计快照，无日级时间序列
  - 如需日粒度运营数据，目前更可靠的方式仍是从 TikTok Creator Center 手动导出 CSV

本模块实现：
  1. 账号基础指标快照（拉取当天快照写入 today 这一行）
  2. 视频列表（最近 20 条）的 likes/comments/shares 按发布日期聚合
  3. 如 TikTok Research API 开通，可扩展支持更多历史数据

覆盖字段：followers(snapshot), likes, comments, shares（帖子聚合）
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import pandas as pd

from utils.api_base import APIConfigError, APIError, APISourceBase
from utils.data_loader import _ensure_standard_shape
from utils.logging import emit_warning

logger = logging.getLogger(__name__)

_API_BASE = "https://business-api.tiktok.com/open_api/v1.3"


class TikTokConfigError(APIConfigError):
    pass


class TikTokAPIError(APIError):
    pass


def _is_configured() -> bool:
    return TikTokSource.is_configured()


class TikTokSource(APISourceBase):
    """TikTok Business API 数据拉取客户端。

    Setup 步骤（详见 .streamlit/secrets.toml.example）：
      1. 前往 https://business.tiktok.com/  → 确认账号是 Business Account
      2. 前往 https://developers.tiktok.com/ → Create App
      3. 添加产品 TikTok Business API → 申请权限 business.info.get + video.list
      4. 通过 OAuth 授权流程获取 access_token（有效期 24h）+ refresh_token（30 天）
      5. 填入 secrets.toml

    TikTok access_token 有效期只有 24 小时，需要用 refresh_token 定期刷新。
    本模块在调用前自动尝试刷新。
    """

    SECRETS_SECTION = "tiktok"
    REQUIRED_FIELDS = ("access_token",)
    CONFIG_ERROR_CLS = TikTokConfigError
    API_ERROR_CLS = TikTokAPIError

    def __init__(
        self,
        access_token: str,
        refresh_token: str | None = None,
        app_id: str | None = None,
        app_secret: str | None = None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.app_id = app_id
        self.app_secret = app_secret

    @classmethod
    def from_streamlit_secrets(cls) -> "TikTokSource":
        cfg = cls._load_secrets()
        return cls(
            access_token=cfg["access_token"],
            refresh_token=cfg.get("refresh_token"),
            app_id=cfg.get("app_id"),
            app_secret=cfg.get("app_secret"),
        )

    def _headers(self) -> dict:
        return {"Access-Token": self.access_token}

    def _post(self, path: str, body: dict | None = None) -> dict[str, Any]:
        url = f"{_API_BASE}/{path.lstrip('/')}"
        resp = self._request("POST", url, headers=self._headers(), json=body or {})
        if resp.status_code != 200:
            raise TikTokAPIError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        code = data.get("code", 0)
        if code != 0:
            msg = data.get("message", str(data))
            if code == 40001:
                raise TikTokAPIError(
                    f"access_token 无效或已过期（code {code}）。"
                    "TikTok token 有效期仅 24 小时，请重新授权并更新 secrets.toml。"
                )
            raise TikTokAPIError(f"TikTok API 错误 {code}: {msg}")
        return data.get("data", {})

    def _try_refresh_token(self) -> bool:
        """尝试用 refresh_token 换取新的 access_token。返回是否成功。"""
        if not all([self.refresh_token, self.app_id, self.app_secret]):
            return False
        try:
            resp = self._request(
                "POST",
                f"{_API_BASE}/oauth2/refresh_token/",
                json={
                    "app_id": self.app_id,
                    "secret": self.app_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        except TikTokAPIError:
            return False
        if resp.status_code != 200:
            return False
        data = resp.json()
        if data.get("code") != 0:
            return False
        new_token = data.get("data", {}).get("access_token")
        if new_token:
            self.access_token = new_token
            return True
        return False

    # ------------------------------------------------------------------
    # 数据拉取
    # ------------------------------------------------------------------

    def fetch(self, since: date, until: date) -> pd.DataFrame:
        """拉取 TikTok 账号数据。

        由于 TikTok 有机内容 API 限制，返回：
        - 当日账号粉丝/点赞快照（写入 today 这一行）
        - 时间段内发布的视频互动汇总（按发布日期聚合）

        ⚠️  日粒度历史数据（历史每天的粉丝曝光变化）暂不支持，需手动 CSV 补充。
        """
        rows = []

        # 1. 账号基础信息快照
        try:
            info = self._fetch_account_info()
            today = date.today().isoformat()
            rows.append({
                "date": today,
                "platform": "tiktok",
                "followers": info.get("followers_count"),
                "likes": info.get("likes_count"),
            })
        except TikTokAPIError as exc:
            # token 可能过期，尝试刷新
            if "过期" in str(exc) and self._try_refresh_token():
                try:
                    info = self._fetch_account_info()
                    rows.append({
                        "date": date.today().isoformat(),
                        "platform": "tiktok",
                        "followers": info.get("followers_count"),
                        "likes": info.get("likes_count"),
                    })
                except TikTokAPIError as exc2:
                    raise TikTokAPIError(f"刷新 token 后仍然失败：{exc2}") from exc2
            else:
                raise

        # 2. 视频列表 → 按发布日期聚合互动
        try:
            video_rows = self._fetch_video_engagement(since, until)
            rows.extend(video_rows)
        except TikTokAPIError as exc:
            emit_warning(f"拉取视频互动数据失败，跳过：{exc}")

        if not rows:
            return _ensure_standard_shape(pd.DataFrame(), platform=None)

        df = pd.DataFrame(rows)

        # 合并同一天的多条（账号快照 + 视频聚合可能有同一天的数据）
        df = df.groupby(["date", "platform"], as_index=False).sum(numeric_only=True, min_count=1)
        return _ensure_standard_shape(df, platform="tiktok")

    def _fetch_account_info(self) -> dict[str, Any]:
        """拉取账号基础信息（粉丝数、获赞数等）。"""
        data = self._post(
            "business/get/",
            {
                "fields": [
                    "username", "display_name", "followers_count",
                    "likes_count", "video_views", "comments_count", "shares_count",
                ],
            },
        )
        return data

    def _fetch_video_engagement(self, since: date, until: date) -> list[dict]:
        """拉取时间段内发布的视频，按日聚合互动数据。"""
        resp = self._post(
            "business/video/list/",
            {
                "fields": [
                    "item_id", "create_time", "like_count",
                    "comment_count", "share_count", "view_count",
                ],
                "max_count": 20,
            },
        )
        videos = resp.get("videos", [])
        if not videos:
            return []

        day_agg: dict[str, dict] = {}
        for v in videos:
            create_time = v.get("create_time")
            if not create_time:
                continue
            # create_time 是 Unix timestamp（秒）
            if isinstance(create_time, int):
                v_date = datetime.fromtimestamp(create_time).date()
            else:
                try:
                    v_date = date.fromisoformat(str(create_time)[:10])
                except ValueError:
                    continue
            if not (since <= v_date <= until):
                continue
            day_str = v_date.isoformat()
            if day_str not in day_agg:
                day_agg[day_str] = {"likes": 0, "comments": 0, "shares": 0, "impressions": 0}
            day_agg[day_str]["likes"] += v.get("like_count", 0) or 0
            day_agg[day_str]["comments"] += v.get("comment_count", 0) or 0
            day_agg[day_str]["shares"] += v.get("share_count", 0) or 0
            day_agg[day_str]["impressions"] += v.get("view_count", 0) or 0

        return [{"date": d, "platform": "tiktok", **v} for d, v in day_agg.items()]

    def check_token(self) -> dict[str, Any]:
        """验证 access_token 是否有效。"""
        try:
            self._fetch_account_info()
            return {"valid": True, "error": None}
        except TikTokAPIError as exc:
            return {"valid": False, "error": str(exc)}
