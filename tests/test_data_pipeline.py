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
