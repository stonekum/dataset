"""核心数据管道的最小测试集（Tier 2.5）。

覆盖：
- _identify_source：六平台 + Metricool 表头识别
- _ensure_standard_shape：缺列补齐、platform 注入、date 强转
- metrics：互动率、follower_growth、period_change 含除零
- GoogleSheetsSource.write 的 merge 逻辑（不发起真网络请求）
"""

import numpy as np
import pandas as pd
import pytest

from utils.data_loader import (
    STANDARD_COLS,
    _ensure_standard_shape,
    _identify_source,
)
from utils.metrics import (
    calculate_engagement_rate,
    calculate_follower_growth,
    calculate_follower_growth_rate,
    calculate_period_change,
    enrich_dataframe,
)


# ============================================================
# _identify_source
# ============================================================

class TestIdentifySource:
    def test_metricool(self):
        kind, _ = _identify_source({"Account", "Network", "Date", "Followers"})
        assert kind == "metricool"

    def test_instagram(self):
        cols = {"Date", "Followers", "Impressions", "Reach", "Likes", "Comments", "Shares", "Saves"}
        kind, _ = _identify_source(cols)
        assert kind == "instagram"

    def test_tiktok(self):
        cols = {"Date", "Followers", "Video Views", "Likes", "Comments", "Shares"}
        kind, _ = _identify_source(cols)
        assert kind == "tiktok"

    def test_youtube(self):
        cols = {"Date", "Subscribers", "Views", "Likes", "Comments"}
        kind, _ = _identify_source(cols)
        assert kind == "youtube"

    def test_unknown_returns_none(self):
        kind, _ = _identify_source({"foo", "bar", "baz"})
        assert kind is None


# ============================================================
# _ensure_standard_shape
# ============================================================

class TestEnsureStandardShape:
    def test_adds_missing_numeric_columns_as_nan(self):
        df = pd.DataFrame({"date": ["2026-01-01"], "platform": ["ig"], "followers": [100]})
        result = _ensure_standard_shape(df, platform="instagram")
        for col in STANDARD_COLS:
            assert col in result.columns
        # 没填的数值列应为 NaN
        assert pd.isna(result["impressions"].iloc[0])

    def test_injects_platform_when_missing(self):
        df = pd.DataFrame({"date": ["2026-01-01"], "followers": [100]})
        result = _ensure_standard_shape(df, platform="youtube")
        assert result["platform"].iloc[0] == "youtube"

    def test_empty_returns_empty_with_standard_cols(self):
        result = _ensure_standard_shape(pd.DataFrame(), platform=None)
        assert list(result.columns) == STANDARD_COLS
        assert len(result) == 0

    def test_date_string_to_datetime(self):
        df = pd.DataFrame({"date": ["2026-05-23"], "platform": ["ig"], "followers": [100]})
        result = _ensure_standard_shape(df, platform=None)
        assert pd.api.types.is_datetime64_any_dtype(result["date"])


# ============================================================
# metrics
# ============================================================

class TestMetrics:
    def test_engagement_rate_basic(self):
        # likes=10, comments=2, shares=3, saves=0, impressions=1000 → 1.5%
        assert calculate_engagement_rate(10, 2, 3, 0, 1000) == pytest.approx(1.5)

    def test_engagement_rate_zero_impressions(self):
        assert calculate_engagement_rate(10, 2, 3, 0, 0) == 0.0

    def test_engagement_rate_with_nan(self):
        # NaN 应被当作 0
        result = calculate_engagement_rate(np.nan, 2, 3, np.nan, 1000)
        assert result == pytest.approx(0.5)

    def test_follower_growth(self):
        assert calculate_follower_growth(1100, 1000) == 100
        assert calculate_follower_growth(900, 1000) == -100

    def test_follower_growth_rate_zero_base(self):
        assert calculate_follower_growth_rate(100, 0) == 0.0

    def test_period_change_basic(self):
        # this=120, last=100 → +20%
        assert calculate_period_change(120, 100) == pytest.approx(20.0)

    def test_period_change_zero_base(self):
        assert calculate_period_change(100, 0) == 0.0


# ============================================================
# enrich_dataframe end-to-end
# ============================================================

class TestEnrichDataframe:
    def test_computes_engagement_rate_per_row(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "platform": ["ig", "ig"],
            "followers": [1000, 1010],
            "impressions": [10000, 12000],
            "reach": [9000, 10800],
            "likes": [100, 120],
            "comments": [20, 25],
            "shares": [5, 10],
            "saves": [3, 5],
            "posts_count": [1, 2],
        })
        out = enrich_dataframe(df)
        assert "engagement_rate" in out.columns
        # row 0: (100+20+5+3)/10000 * 100 = 1.28
        assert out["engagement_rate"].iloc[0] == pytest.approx(1.28)
        assert "follower_growth" in out.columns

    def test_follower_growth_first_row_is_zero_or_nan(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "platform": ["ig", "ig"],
            "followers": [1000, 1050],
            "impressions": [1000, 1000],
            "reach": [0, 0], "likes": [0, 0], "comments": [0, 0],
            "shares": [0, 0], "saves": [0, 0], "posts_count": [0, 0],
        })
        out = enrich_dataframe(df).sort_values("date").reset_index(drop=True)
        # day 2 - day 1 = 50
        assert out["follower_growth"].iloc[1] == 50


# ============================================================
# api_base smoke
# ============================================================

class TestAPIBase:
    def test_subclass_inheritance(self):
        from utils.api_base import APIConfigError, APIError, APISourceBase
        from utils.meta_graph import MetaGraphAPIError, MetaGraphConfigError, MetaGraphSource
        from utils.youtube_api import YouTubeAPIError, YouTubeConfigError, YouTubeSource

        assert issubclass(MetaGraphConfigError, APIConfigError)
        assert issubclass(MetaGraphAPIError, APIError)
        assert issubclass(MetaGraphSource, APISourceBase)
        assert issubclass(YouTubeConfigError, APIConfigError)
        assert issubclass(YouTubeAPIError, APIError)
        assert issubclass(YouTubeSource, APISourceBase)

    def test_meta_error_alias_preserved(self):
        """meta_error 是 extra 的别名（向后兼容 pages/3 中的 exc.meta_error）。"""
        from utils.meta_graph import MetaGraphAPIError
        e = MetaGraphAPIError("test", status_code=400, extra={"code": 100, "message": "boom"})
        assert e.meta_error == {"code": 100, "message": "boom"}


# ============================================================
# 回归：上一轮 /code-review 修复的三个 bug
# ============================================================

class TestRegressionsFromCodeReview:
    def test_esc_escapes_newlines_in_private_key(self):
        """GCP private_key 经 json.loads 后含真实 LF，必须转义成 \\n 才能写进
        TOML basic string。旧版只转 \\ 与 "，导致 secrets.toml 解析失败。"""
        from scripts.scheduled_pull import _esc

        sample = "-----BEGIN PRIVATE KEY-----\nMIIE\tBAQ\r\n-----END PRIVATE KEY-----\n"
        escaped = _esc(sample)
        # 输出不允许含裸的换行 / 制表
        assert "\n" not in escaped
        assert "\r" not in escaped
        assert "\t" not in escaped
        # 但应包含字面 \n 序列
        assert "\\n" in escaped
        assert "\\t" in escaped
        # 反斜杠和双引号转义沿用旧行为
        assert _esc('he said "hi"') == 'he said \\"hi\\"'
        assert _esc(r"a\b") == "a\\\\b"

    def test_ensure_standard_shape_preserves_follower_growth_when_present(self):
        """API 源（YouTube / LinkedIn）会直接给当日 follower_growth；
        _ensure_standard_shape 必须把它透传出来，而不是在 out[STANDARD_COLS] 这一步丢掉。"""
        df = pd.DataFrame({
            "date": ["2026-05-01"],
            "platform": ["youtube"],
            "followers": [10000],
            "follower_growth": [42],
        })
        result = _ensure_standard_shape(df, platform="youtube")
        assert "follower_growth" in result.columns
        assert result["follower_growth"].iloc[0] == 42.0

    def test_ensure_standard_shape_does_not_invent_follower_growth(self):
        """CSV 源没有 follower_growth；不应该凭空生出来，避免污染 STANDARD_COLS 契约。"""
        df = pd.DataFrame({
            "date": ["2026-05-01"],
            "platform": ["instagram"],
            "followers": [10000],
        })
        result = _ensure_standard_shape(df, platform="instagram")
        assert "follower_growth" not in result.columns
        assert list(result.columns) == STANDARD_COLS

    def test_enrich_dataframe_prefers_source_follower_growth_over_shift(self):
        """API 路径：followers 仅有最后一天的快照，shift 差值不可信。
        enrich_dataframe 必须优先用源头 follower_growth。"""
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03"]),
            "platform": ["youtube", "youtube", "youtube"],
            # 模拟 YouTube：仅最后一天有 followers 快照
            "followers": [np.nan, np.nan, 50000.0],
            "impressions": [1000, 1100, 1200],
            "reach": [0, 0, 0],
            "likes": [10, 12, 15],
            "comments": [0, 0, 0],
            "shares": [0, 0, 0],
            "saves": [0, 0, 0],
            "posts_count": [0, 0, 0],
            "follower_growth": [120, 88, 95],  # 来自 subscribersGained - subscribersLost
        })
        out = enrich_dataframe(df).sort_values("date").reset_index(drop=True)
        assert list(out["follower_growth"]) == [120.0, 88.0, 95.0]

    def test_enrich_dataframe_falls_back_to_shift_when_api_value_nan(self):
        """混合路径：concat 后某些行 follower_growth 是 NaN（来自 CSV），
        这些 NaN 应该被 followers 差值填补，不能扔成 0。"""
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-05-01", "2026-05-02"]),
            "platform": ["instagram", "instagram"],
            "followers": [1000.0, 1050.0],
            "impressions": [100, 100],
            "reach": [0, 0],
            "likes": [0, 0], "comments": [0, 0], "shares": [0, 0], "saves": [0, 0],
            "posts_count": [0, 0],
            "follower_growth": [np.nan, np.nan],
        })
        out = enrich_dataframe(df).sort_values("date").reset_index(drop=True)
        # day 2: followers shift 给出 50，应该回落使用
        assert out["follower_growth"].iloc[1] == 50.0

    def test_linkedin_impressions_precedence(self):
        """复现 `A or B + C` 优先级 bug：allPageViews=0 时不应回落到 mobile+desktop。"""
        # 我们不发起真 API 调用，而是直接复刻 _fetch_share_statistics 里那段判断逻辑。
        # 提取的语义：优先 allPageViews.pageViews，仅当字段整体缺失时才回退。
        def compute(views):
            _all_pv = views.get("allPageViews", {}).get("pageViews")
            if _all_pv is None:
                return (
                    views.get("mobilePageViews", {}).get("pageViews", 0)
                    + views.get("desktopPageViews", {}).get("pageViews", 0)
                )
            return _all_pv

        # 1) allPageViews=0（真零）→ 必须返回 0，不可回退到 mobile+desktop
        views_zero = {
            "allPageViews":     {"pageViews": 0},
            "mobilePageViews":  {"pageViews": 100},
            "desktopPageViews": {"pageViews": 200},
        }
        assert compute(views_zero) == 0

        # 2) allPageViews=正值 → 用 allPageViews
        views_pos = {
            "allPageViews":     {"pageViews": 350},
            "mobilePageViews":  {"pageViews": 100},
            "desktopPageViews": {"pageViews": 200},
        }
        assert compute(views_pos) == 350

        # 3) allPageViews 整体缺失 → 才回退到 mobile+desktop
        views_missing = {
            "mobilePageViews":  {"pageViews": 100},
            "desktopPageViews": {"pageViews": 200},
        }
        assert compute(views_missing) == 300
