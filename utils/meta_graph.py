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


def _day_from_end_time(end_time: str) -> str | None:
    """把 Meta insights 返回的 `end_time` 换算成实际数据所属的那一天。

    Meta 对 period=day 的 `end_time` 是「周期结束的瞬间」，即下一天的 00:00（按
    Page 时区或 PT 表达）。例如 2026-05-29 的数据，end_time = '2026-05-30T08:00:00+0000'。
    旧代码直接 `end_time[:10]` 就会把 05-29 的数据写成 05-30。

    这里取出 ISO 字符串的日期部分再减 1 天，保证 date 列对齐到实际数据日。
    """
    if not end_time or not isinstance(end_time, str) or len(end_time) < 10:
        return None
    try:
        dt = datetime.strptime(end_time[:10], "%Y-%m-%d") - timedelta(days=1)
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d")
_TIMEOUT = 20  # 秒（仅 _get_all_pages 翻页时还在用）

# Facebook Page Insights 需要的指标
#
# 重要：Meta 在 2024-2025 把 Page Insights 大批指标废弃，截至 v21+ 实测仍可用：
#   - page_impressions_unique  （= reach 去重触达）
#   - page_post_engagements    （帖子互动综合：likes+comments+shares 之类聚合）
#   - page_views_total         （Page 页面被访问次数，与帖子曝光不同）
# 已废弃（不能再请求）：
#   - page_impressions, page_fans, page_fan_adds, page_engaged_users
# 应对：
#   - "impressions" 字段在此层无对应来源（page_views_total 语义是 Page 访问，
#     不是内容曝光，不映射），保留 None；UI 端的「曝光」请改用 reach
#   - "followers" 不再有时序快照；改用 `?fields=followers_count` 一次性快照，
#     仅填到时间窗最后一天（与 YouTube 行为一致）
_FB_METRICS = [
    "page_impressions_unique",  # 日触达（去重 reach）
    "page_post_engagements",    # 日帖互动综合
]

# Instagram Business Account Insights 需要的指标
#
# 重要：Meta 从 2024-Q4 起把 IG 账号级 `impressions` 指标整个废弃
# （报错 "metric must be one of: reach, follower_count, views, ..."）。
# 当前选择是只保留 `reach` 和 `follower_count` —— 它们仍走最简单的
# period=day 时序接口，不需要 `metric_type=total_value`。
#
# `views` 在新 API 里是 impressions 的最接近替代，但它要求
# `metric_type=total_value` 且只返回单一聚合值（拿不到逐日时序），
# 接入需要单独一次请求 + 改 dataframe 装配逻辑，后续单独实现。
#
# 影响：IG 数据的 `impressions` 字段将一直是 NaN，下游若需要
# 「曝光」近似值可暂用 `reach`（去重触达，数量级与 impressions 接近）。
_IG_ACCOUNT_METRICS = [
    "reach",          # 日去重触达
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

    def _auth_headers(self) -> dict:
        """access_token 走 Authorization header，不放 URL 避免落进代理/Referer 日志。"""
        return {"Authorization": f"Bearer {self.token}"}

    def _get(self, path: str, **params) -> dict[str, Any]:
        """对 Graph API 发出 GET 请求，复用 base 的重试机制。"""
        url = f"{_API_BASE}/{path.lstrip('/')}"
        resp = self._request("GET", url, headers=self._auth_headers(), params=params)
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
        # 不把 resp.text 塞进异常给用户看（可能含 token 碎片或敏感字段）
        try:
            err = resp.json().get("error", {})
            user_msg = err.get("message", "请查看服务端日志")
        except Exception:  # noqa: BLE001
            err = {}
            user_msg = "服务返回非 JSON 响应"
            logger.warning("Meta API 非 JSON 响应 (status=%s)：%s", resp.status_code, resp.text[:500])
        raise MetaGraphAPIError(
            f"HTTP {resp.status_code}: {user_msg}",
            status_code=resp.status_code,
            extra=err,
        )

    def _get_all_pages(self, path: str, **params) -> list[dict]:
        """自动翻页，返回所有 data 列表元素。

        翻页 URL 由 Meta 返回；我们校验 host 后用统一的 _request 走重试，
        避免 SSRF（next_url 被篡改指向内网）和翻页时无重试问题。
        """
        results = []
        data = self._get(path, **params)
        results.extend(data.get("data", []))
        while True:
            next_url = data.get("paging", {}).get("next")
            if not next_url:
                break
            # 防御性校验：next_url 必须仍指向 Graph API 域
            if not next_url.startswith("https://graph.facebook.com/"):
                logger.warning("拒绝可疑的翻页 URL（非 graph.facebook.com）：%s", next_url[:120])
                break
            resp = self._request("GET", next_url, headers=self._auth_headers())
            if resp.status_code != 200:
                logger.warning("翻页请求失败 (status=%s)，停止翻页", resp.status_code)
                break
            data = resp.json()
            results.extend(data.get("data", []))
        return results

    # ------------------------------------------------------------------
    # Facebook Page
    # ------------------------------------------------------------------

    def fetch_facebook(self, since: date, until: date) -> pd.DataFrame:
        """拉取 Facebook Page 每日指标，返回标准列 DataFrame（platform=facebook）。

        覆盖字段：reach（page_impressions_unique）、likes（page_post_engagements，
        互动综合值）、followers（来自 followers_count 的当前快照，仅填到末日）。

        注意 Meta 在 2024-2025 大批废弃 Page Insights 指标，原 page_impressions /
        page_fans 都已 #100 报错，详见 _FB_METRICS 处注释。
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
                # 用 _day_from_end_time 反推实际数据日（Meta end_time 比数据日晚 1 天）
                day = _day_from_end_time(entry.get("end_time", ""))
                if day is None:
                    continue
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
                # page_impressions 已废弃；保留 None，UI 用 reach 替代曝光
                "impressions": None,
                "reach": metrics.get("page_impressions_unique"),
                "likes": metrics.get("page_post_engagements"),  # 最接近 engagement 的 proxy
            })

        # page_fans 已废弃；改用 ?fields=followers_count 取当前粉丝总数快照，
        # 仅填到时间窗最后一天（其他天保持 None），与 YouTube 行为一致。
        try:
            info = self._get(self.page_id, fields="followers_count")
            follower_count = info.get("followers_count")
            if follower_count is not None and rows:
                rows[-1]["followers"] = follower_count
        except MetaGraphAPIError as exc:
            emit_warning(f"拉取 Facebook Page followers_count 失败：{exc}")

        df = pd.DataFrame(rows)
        return _ensure_standard_shape(df, platform="facebook")

    # ------------------------------------------------------------------
    # Instagram Business Account
    # ------------------------------------------------------------------

    def fetch_instagram(self, since: date, until: date) -> pd.DataFrame:
        """拉取 Instagram Business Account 每日指标，返回标准列 DataFrame。

        覆盖字段：
          - `reach`           ← insights.reach
          - `follower_growth` ← insights.follower_count（**单数；当日净增**，不是总数）
          - `followers`       ← `?fields=followers_count` 当前快照，仅填到末日
          - `likes/comments`  ← 媒体级 like_count/comments_count 按日聚合
          - `posts_count`     ← 当日发布的媒体条数

        Meta 命名陷阱：
          - insights 的 `follower_count`（单数）= 当日净增粉丝（日度增量）
          - 账号字段 `followers_count`（复数）= 当前粉丝总数快照
        旧实现把单数当总数塞进 `followers` 列，导致 Sheet 中出现 100、138 等
        异常小的"粉丝数"。本版本拆分映射，与 YouTube 行为一致。
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
                # insights.follower_count（单数）= 当日净增；放进 follower_growth
                "follower_growth": m.get("follower_count"),
                # impressions 在 IG 已废弃；UI 用 reach 替代曝光
                "impressions": None,
                "reach": m.get("reach"),
                # 媒体级聚合：如果该日有 insights 数据但无新发帖，应记 0 而非 None
                # （0 帖 = 0 互动，是已知值；None 看着像"数据缺失"，会让 Sheet 视觉
                # 上空一片，也会让 enrich_dataframe 在 fillna 时多绕一步）
                "likes": m.get("media_likes", 0),
                "comments": m.get("media_comments", 0),
                "posts_count": m.get("posts_count", 0),
            })

        # 另起一次请求拿当前粉丝总数（账号字段 followers_count，复数），
        # 填到时间窗末日；其他天保持 None。与 FB / YouTube 路径一致。
        try:
            info = self._get(self.ig_user_id, fields="followers_count")
            followers_count = info.get("followers_count")
            if followers_count is not None and rows:
                rows[-1]["followers"] = followers_count
        except MetaGraphAPIError as exc:
            emit_warning(f"拉取 Instagram followers_count 失败：{exc}")

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
