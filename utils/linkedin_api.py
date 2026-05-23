"""LinkedIn Marketing API 数据拉取模块。

通过 LinkedIn OAuth 2.0 access_token 拉取公司主页（Organization Page）每日统计数据。
输出符合项目标准列结构的 DataFrame（platform='linkedin'）。

覆盖字段：impressions, followers, likes(reactions), comments, shares

注意：
  - 仅支持 Company / Organization Page，不支持个人主页
  - LinkedIn access_token 有效期约 60 天，需要定期刷新
  - 需要权限：r_organization_social（主页数据读取）
  - 申请 LinkedIn App 后需 App Review 才能获得 r_organization_social
    审核通常 1-5 个工作日
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from utils.api_base import APIConfigError, APIError, APISourceBase
from utils.data_loader import _ensure_standard_shape

logger = logging.getLogger(__name__)

_API_BASE = "https://api.linkedin.com/v2"


class LinkedInConfigError(APIConfigError):
    pass


class LinkedInAPIError(APIError):
    pass


def _is_configured() -> bool:
    return LinkedInSource.is_configured()


class LinkedInSource(APISourceBase):
    """LinkedIn Organization Page 数据拉取客户端。"""

    SECRETS_SECTION = "linkedin"
    REQUIRED_FIELDS = ("access_token", "organization_id")
    CONFIG_ERROR_CLS = LinkedInConfigError
    API_ERROR_CLS = LinkedInAPIError

    def __init__(self, access_token: str, organization_id: str):
        self.token = access_token
        # organization_id 可以是纯数字或 urn:li:organization:{id} 两种格式
        org_id = str(organization_id).strip()
        if org_id.startswith("urn:"):
            self.org_urn = org_id
        else:
            self.org_urn = f"urn:li:organization:{org_id}"

    @classmethod
    def from_streamlit_secrets(cls) -> "LinkedInSource":
        cfg = cls._load_secrets()
        return cls(access_token=cfg["access_token"], organization_id=cfg["organization_id"])

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def _get(self, path: str, **params) -> dict[str, Any]:
        url = f"{_API_BASE}/{path.lstrip('/')}"
        resp = self._request("GET", url, headers=self._headers(), params=params)
        if resp.status_code == 401:
            raise LinkedInAPIError(
                "Token 无效或已过期（HTTP 401）。"
                "LinkedIn access_token 有效期约 60 天，请重新授权并更新 secrets.toml。"
            )
        if resp.status_code == 403:
            raise LinkedInAPIError(
                "权限不足（HTTP 403）。"
                "请确认 LinkedIn App 已获得 r_organization_social 权限，且 App 已通过审核。"
            )
        if resp.status_code != 200:
            raise LinkedInAPIError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if "status" in data and data["status"] >= 400:
            raise LinkedInAPIError(
                f"API 错误 {data.get('status')}: {data.get('message', data)}"
            )
        return data

    # ------------------------------------------------------------------
    # 数据拉取
    # ------------------------------------------------------------------

    def fetch(self, since: date, until: date) -> pd.DataFrame:
        """拉取公司主页每日统计，返回标准列 DataFrame。"""
        # LinkedIn 时间范围用 Unix 毫秒
        since_ms = int(datetime(since.year, since.month, since.day, tzinfo=timezone.utc).timestamp() * 1000)
        until_ms = int(datetime(until.year, until.month, until.day, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

        raw = self._get(
            "organizationPageStatistics",
            q="organization",
            organization=self.org_urn,
            **{
                "timeIntervals.timeGranularityType": "DAY",
                "timeIntervals.timeRange.start": since_ms,
                "timeIntervals.timeRange.end": until_ms,
            },
        )

        elements = raw.get("elements", [])
        if not elements:
            return _ensure_standard_shape(pd.DataFrame(), platform=None)

        rows = []
        for el in elements:
            time_range = el.get("timeRange", {})
            start_ms = time_range.get("start")
            if not start_ms:
                continue
            day = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).date().isoformat()

            page_stats = el.get("totalPageStatistics", {})
            views = page_stats.get("views", {})
            clicks = page_stats.get("clicks", {})

            # 互动数据（reactions/comments/shares）来自 followerGains + organic ugcPosts
            # LinkedIn 把帖子互动放在不同字段，取 all channel 汇总
            impressions = (views.get("allPageViews", {}).get("pageViews")
                           or views.get("mobilePageViews", {}).get("pageViews", 0)
                           + views.get("desktopPageViews", {}).get("pageViews", 0))

            # follower stats (每日 follower 快照 / 增量)
            follower_stats = el.get("followerGains", {})
            follower_gained = follower_stats.get("organicFollowerGains", 0) or 0
            follower_paid = follower_stats.get("paidFollowerGains", 0) or 0

            rows.append({
                "date": day,
                "platform": "linkedin",
                "impressions": impressions,
                "follower_growth": follower_gained + follower_paid,
                # 互动数据需要调用 ugcPosts API，先留 None，后续分批补充
                "likes": None,
                "comments": None,
                "shares": None,
            })

        if not rows:
            return _ensure_standard_shape(pd.DataFrame(), platform=None)

        df = pd.DataFrame(rows)

        # 拉取帖子互动汇总（按日聚合 reactions + comments + shares）
        try:
            posts_df = self._fetch_post_engagement(since, until)
            if not posts_df.empty:
                df = df.merge(
                    posts_df.rename(columns={
                        "likes": "_post_likes",
                        "comments": "_post_comments",
                        "shares": "_post_shares",
                    }),
                    on="date", how="left",
                )
                df["likes"] = df["_post_likes"].where(df["_post_likes"].notna(), df["likes"])
                df["comments"] = df["_post_comments"].where(df["_post_comments"].notna(), df["comments"])
                df["shares"] = df["_post_shares"].where(df["_post_shares"].notna(), df["shares"])
                df = df.drop(columns=["_post_likes", "_post_comments", "_post_shares"], errors="ignore")
        except LinkedInAPIError as exc:
            logger.warning("拉取 LinkedIn 帖子互动失败，likes/comments/shares 将为空：%s", exc)

        # 拉取当前 follower 总数（snapshot）
        try:
            total = self._fetch_total_followers()
            if total is not None:
                last_day = df["date"].max()
                df.loc[df["date"] == last_day, "followers"] = total
        except LinkedInAPIError as exc:
            logger.warning("拉取 LinkedIn follower 总数失败：%s", exc)

        return _ensure_standard_shape(df, platform="linkedin")

    def _fetch_post_engagement(self, since: date, until: date) -> pd.DataFrame:
        """拉取时间段内的 UGC Posts 互动，按日聚合 reactions/comments/shares。"""
        since_ms = int(datetime(since.year, since.month, since.day, tzinfo=timezone.utc).timestamp() * 1000)
        until_ms = int(datetime(until.year, until.month, until.day, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

        # 获取该时间段发布的帖子
        posts_raw = self._get(
            "ugcPosts",
            q="authors",
            authors=f"List({self.org_urn})",
            **{
                "createdAfter": since_ms,
                "createdBefore": until_ms,
                "count": 50,
            },
        )
        elements = posts_raw.get("elements", [])
        if not elements:
            return pd.DataFrame()

        day_agg: dict[str, dict] = {}
        for post in elements:
            created_ms = post.get("created", {}).get("time", 0)
            if not created_ms:
                continue
            day = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).date().isoformat()
            stats = post.get("statistics", {})
            if day not in day_agg:
                day_agg[day] = {"likes": 0, "comments": 0, "shares": 0}
            day_agg[day]["likes"] += stats.get("likeCount", 0) or 0
            day_agg[day]["comments"] += stats.get("commentCount", 0) or 0
            day_agg[day]["shares"] += stats.get("shareCount", 0) or 0

        if not day_agg:
            return pd.DataFrame()
        return pd.DataFrame([{"date": d, **v} for d, v in day_agg.items()])

    def _fetch_total_followers(self) -> int | None:
        """拉取公司主页当前 follower 总数。"""
        data = self._get(
            "networkSizes",
            **{"edgeType": "CompanyFollowedByMember"},
            q="urn",
            urn=self.org_urn,
        )
        return data.get("firstDegreeSize")

    def check_token(self) -> dict[str, Any]:
        """验证 access_token 有效性（拉取 profile 做探针）。"""
        try:
            data = self._get("me")
            return {"valid": True, "name": data.get("localizedFirstName", "") + " " + data.get("localizedLastName", ""), "error": None}
        except LinkedInAPIError as exc:
            return {"valid": False, "name": None, "error": str(exc)}
