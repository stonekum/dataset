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

from utils.data_cleaner import clean
from utils.data_loader import (
    STANDARD_COLS,
    _ensure_standard_shape,
    _identify_source,
)
from utils.metrics import (
    aggregate_by_period,
    calculate_engagement_rate,
    calculate_follower_growth,
    calculate_follower_growth_rate,
    calculate_period_change,
    enrich_dataframe,
    weighted_engagement_rate,
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
        # exposure_base = COALESCE(reach, impressions) = reach（reach 有值，优先）
        assert out["exposure_base"].iloc[0] == 9000.0
        # row 0: (100+20+5+3)/9000 * 100 ≈ 1.4222（分母用 exposure_base=reach，非 impressions）
        assert out["engagement_rate"].iloc[0] == pytest.approx(128 / 9000 * 100)
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
# exposure_base + 互动率 NaN 范式（H1 / H2）
# ============================================================

class TestExposureBaseAndEngagementRate:
    """A1/A2 + H1/H2：exposure_base = COALESCE(reach, impressions)（reach 优先）；
    互动率改用 exposure_base 当分母，分母 NaN/0 → 互动率 NaN（不再塌成 0）。"""

    def _df(self, reach, impressions, likes=10.0):
        n = len(reach)
        return pd.DataFrame({
            "date": pd.to_datetime([f"2026-05-{i + 1:02d}" for i in range(n)]),
            "platform": ["facebook"] * n,
            "followers": [1000.0] * n,
            "impressions": impressions,
            "reach": reach,
            "likes": [likes] * n,
            "comments": [0.0] * n,
            "shares": [0.0] * n,
            "saves": [0.0] * n,
            "posts_count": [1.0] * n,
        })

    # ---- H1：exposure_base COALESCE ----
    def test_exposure_base_prefers_reach(self):
        """reach 有值 → exposure_base=reach（FB/IG 落点）。"""
        out = enrich_dataframe(self._df(reach=[5000.0], impressions=[8000.0]))
        assert out["exposure_base"].iloc[0] == 5000.0

    def test_exposure_base_falls_back_to_impressions_when_reach_nan(self):
        """reach 为 NaN → 回落 impressions（YT/TikTok/LinkedIn 落点）。"""
        out = enrich_dataframe(self._df(reach=[np.nan], impressions=[8000.0]))
        assert out["exposure_base"].iloc[0] == 8000.0

    def test_exposure_base_nan_when_both_nan(self):
        """reach 和 impressions 都 NaN → exposure_base=NaN。"""
        out = enrich_dataframe(self._df(reach=[np.nan], impressions=[np.nan]))
        assert pd.isna(out["exposure_base"].iloc[0])

    def test_impressions_column_not_mutated(self):
        """A2：删掉 reach→impressions 回落后，impressions 原值不被改（NaN 仍是 NaN）。"""
        out = enrich_dataframe(self._df(reach=[5000.0], impressions=[np.nan]))
        assert pd.isna(out["impressions"].iloc[0])      # 不再被 reach 回填
        assert out["exposure_base"].iloc[0] == 5000.0   # 回落只发生在 exposure_base

    # ---- H2：互动率用 exposure_base，分母无效 → NaN ----
    def test_engagement_rate_uses_exposure_base(self):
        """互动率 = Σ互动 / exposure_base × 100，分母用 reach（=exposure_base）。"""
        out = enrich_dataframe(self._df(reach=[5000.0], impressions=[8000.0]))
        # interactions=10, exposure_base=5000 → 0.2%
        assert out["engagement_rate"].iloc[0] == pytest.approx(0.2)

    def test_engagement_rate_nan_when_base_nan(self):
        """H2：exposure_base 为 NaN → 互动率 NaN（不再 fillna(0)）。"""
        out = enrich_dataframe(self._df(reach=[np.nan], impressions=[np.nan]))
        assert pd.isna(out["engagement_rate"].iloc[0])

    def test_engagement_rate_nan_when_base_zero(self):
        """H2：exposure_base 为 0 → 分母无效 → 互动率 NaN（不塌成 0）。"""
        out = enrich_dataframe(self._df(reach=[0.0], impressions=[np.nan]))
        assert pd.isna(out["engagement_rate"].iloc[0])


# ============================================================
# 周期聚合 exposure_base（A3 / H5）
# ============================================================

class TestAggregateExposureBase:
    """A3 + H5：aggregate_by_period 把 reach / exposure_base 加入求和；exposure_base
    在**日级**算好后再 sum（Σexposure_base，而非 Σreach.fillna(Σimpressions)）；周期
    互动率 = Σ互动 / Σexposure_base（"先聚合再相除"，曝光加权）。"""

    def _enriched_two_days(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-05-01", "2026-05-02"]),
            "platform": ["facebook", "facebook"],
            "followers": [1000.0, 1010.0],
            # day1: reach 缺失 → exposure_base=impressions=1000；day2: reach=500（优先）
            "impressions": [1000.0, 2000.0],
            "reach": [np.nan, 500.0],
            "likes": [10.0, 20.0],
            "comments": [0.0, 0.0],
            "shares": [0.0, 0.0],
            "saves": [0.0, 0.0],
            "posts_count": [1.0, 1.0],
        })
        return enrich_dataframe(df)

    def test_reach_and_exposure_base_summed(self):
        agg = aggregate_by_period(self._enriched_two_days(), period="M")
        assert "exposure_base" in agg.columns
        assert "reach" in agg.columns
        # Σexposure_base = 1000(day1, 用 impressions) + 500(day2, reach 优先) = 1500
        assert agg.iloc[0]["exposure_base"] == 1500.0

    def test_exposure_base_sum_is_daylevel_not_naive_coalesce(self):
        """钉死"日级算好再 sum"：朴素 Σreach.fillna(Σimpressions)=Σreach=500 会算错。"""
        agg = aggregate_by_period(self._enriched_two_days(), period="M")
        assert agg.iloc[0]["exposure_base"] != 500.0   # 朴素跨天 COALESCE 的错值
        assert agg.iloc[0]["exposure_base"] == 1500.0  # 正确的日级 Σ

    def test_period_engagement_rate_aggregate_then_divide(self):
        """周期互动率 = Σ互动 / Σexposure_base × 100（先聚合再相除）。"""
        row = aggregate_by_period(self._enriched_two_days(), period="M").iloc[0]
        interactions = row["likes"] + row["comments"] + row["shares"] + row["saves"]
        er = interactions / row["exposure_base"] * 100
        # Σ互动=30, Σexposure_base=1500 → 2.0%
        assert er == pytest.approx(2.0)

    def test_period_engagement_rate_zero_exposure_is_nan_not_crash(self):
        """回归（code review BLOCKER）：某周期 Σexposure_base==0（整段 reach=0、无
        impressions）时，汇报视图的周期 ER 表达式必须产出 NaN，而不是抛 TypeError
        ——之前 .replace(0, pd.NA) 流进 .astype(float) 会崩（demo 数据曝光恒>0 抓不到）。"""
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-05-01", "2026-05-02"]),
            "platform": ["x", "x"],
            "followers": [100.0, 101.0],
            "impressions": [np.nan, np.nan],   # 无曝光
            "reach": [0.0, 0.0],               # reach=0 → exposure_base=0
            "likes": [5.0, 6.0], "comments": [0.0, 0.0],
            "shares": [0.0, 0.0], "saves": [np.nan, np.nan],
            "posts_count": [1.0, 1.0],
        })
        agg = aggregate_by_period(enrich_dataframe(df), period="M")
        interactions = (
            agg["likes"].fillna(0) + agg["comments"].fillna(0)
            + agg["shares"].fillna(0) + agg["saves"].fillna(0)
        )
        # 复刻 pages/2 修复后的表达式：np.nan + astype(float) 不应抛错，结果为 NaN
        er = (interactions / agg["exposure_base"].replace(0, np.nan) * 100).astype(float)
        assert er.isna().all()


# ============================================================
# 两视图互动率口径一致（H4）
# ============================================================

class TestTwoViewEngagementCaliber:
    """H4：运营视图 KPI（weighted_engagement_rate）与汇报视图周期互动率
    （先 aggregate 再 Σ互动/Σexposure_base）对同一份数据必须相等——曝光加权口径统一。"""

    def _daily(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03"]),
            "platform": ["facebook"] * 3,
            "followers": [1000.0, 1010.0, 1020.0],
            "impressions": [1000.0, 2000.0, 4000.0],
            "reach": [np.nan, 500.0, 1000.0],   # day1 用 impressions，day2/3 用 reach
            "likes": [10.0, 20.0, 40.0],
            "comments": [0.0, 0.0, 0.0],
            "shares": [0.0, 0.0, 0.0],
            "saves": [np.nan, np.nan, np.nan],  # FB 无 saves（全 NaN）
            "posts_count": [1.0, 1.0, 1.0],
        })
        return enrich_dataframe(df)

    def test_ops_kpi_equals_report_period_rate(self):
        daily = self._daily()
        ops_er = weighted_engagement_rate(daily)
        agg = aggregate_by_period(daily, period="M").iloc[0]
        inter = agg[["likes", "comments", "shares", "saves"]].fillna(0).sum()
        rep_er = inter / agg["exposure_base"] * 100
        assert ops_er == pytest.approx(rep_er)
        # 具体数值：Σ互动=70, Σexposure_base=1000+500+1000=2500 → 2.8%
        assert ops_er == pytest.approx(70 / 2500 * 100)

    def test_weighted_rate_nan_when_no_exposure(self):
        """全无 exposure_base（reach+impressions 皆 NaN）→ 加权互动率 NaN（呈现 N/A）。"""
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-05-01"]),
            "platform": ["x"],
            "followers": [100.0],
            "impressions": [np.nan], "reach": [np.nan],
            "likes": [5.0], "comments": [0.0], "shares": [0.0], "saves": [np.nan],
            "posts_count": [1.0],
        })
        assert pd.isna(weighted_engagement_rate(enrich_dataframe(df)))


# ============================================================
# data_cleaner.clean —— NaN 保留范式（H3）
# ============================================================

class TestCleanPreservesNaN:
    """B1/B2/B3：clean() 不再把数值列 NaN 填 0（范式转变核心），保留 NaN；
    负值仍截断为 0；reach/impressions 的 NaN 绝不被填 0（否则 exposure_base 永不
    为 NaN，互动率会塌成 0）。"""

    def _row(self, **over):
        base = {
            "date": pd.to_datetime(["2026-05-01"]),
            "platform": ["instagram"],
            "followers": [1000.0],
            "impressions": [np.nan],
            "reach": [np.nan],
            "likes": [np.nan],
            "comments": [np.nan],
            "shares": [np.nan],
            "saves": [np.nan],
            "posts_count": [np.nan],
        }
        base.update({k: [v] for k, v in over.items()})
        return pd.DataFrame(base)

    def test_numeric_nan_preserved_not_filled_zero(self):
        """H3：互动/曝光数值列的 NaN 保留，不再被 fillna(0) 抹平。"""
        out = clean(self._row())
        for col in ["impressions", "reach", "likes", "comments", "shares", "saves", "posts_count"]:
            assert pd.isna(out[col].iloc[0]), f"{col} 的 NaN 被填成了 {out[col].iloc[0]}，应保留 NaN"

    def test_reach_and_impressions_nan_never_zero(self):
        """B3：reach / impressions 的 NaN 是 exposure_base 的根基，绝不能被填 0。"""
        out = clean(self._row(impressions=np.nan, reach=np.nan))
        assert pd.isna(out["reach"].iloc[0])
        assert pd.isna(out["impressions"].iloc[0])

    def test_negative_truncated_to_zero_and_flagged(self):
        """B2：负值仍截断为 0，并标记 is_anomaly（这条不变）。"""
        out = clean(self._row(likes=-5.0, impressions=2000.0))
        assert out["likes"].iloc[0] == 0
        assert bool(out["is_anomaly"].iloc[0]) is True

    def test_real_values_untouched(self):
        """有真实值时原样保留，不受 NaN 保留改动影响。"""
        out = clean(self._row(impressions=2000.0, reach=1500.0, likes=10.0))
        assert out["impressions"].iloc[0] == 2000.0
        assert out["reach"].iloc[0] == 1500.0
        assert out["likes"].iloc[0] == 10.0


# ============================================================
# 汇报 PDF 导出（utils.pdf_report）
# ============================================================

class TestPdfReport:
    def _sample(self):
        return dict(
            title="2026-05 月度汇报",
            date_range="2026-05-01 → 2026-05-31",
            kpi=[
                ("总曝光", "1,234,567", "+12.3% 环比"),
                ("总互动", "89,012", "-3.1% 环比"),
                ("净增粉丝", "+4,560", None),
                ("平均互动率", "7.21%", None),
            ],
            summary_lines=[
                "**2026-05 月度 汇报摘要**",
                "- 总曝光 **1,234,567**，环比 +12.3%。",
                "- Instagram 互动率最高。",
            ],
            platform_rows=[
                {"平台": "Instagram", "曝光（基准）": "500,000", "总互动": "40,000",
                 "粉丝净增": "+2,000", "期末粉丝": "90,942", "互动率": "8.00%"},
                {"平台": "Facebook", "曝光（基准）": "N/A", "总互动": "12,000",
                 "粉丝净增": "+0", "期末粉丝": "132,641", "互动率": "N/A"},
            ],
        )

    def test_returns_valid_pdf_bytes(self):
        """中文 + 数字混排能正常生成有效 PDF。"""
        from utils.pdf_report import build_period_report_pdf

        pdf = build_period_report_pdf(**self._sample())
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 2000  # 不是空壳

    def test_embedded_truetype_font_is_used(self):
        """应优先用仓库内置 TrueType 字体（保证所有查看器渲染中文），而非 CID 兜底。"""
        from utils.pdf_report import _ensure_font

        assert _ensure_font() == "CJKReport"

    def test_md_bold_and_escaping(self):
        """`**x**` → `<b>x</b>`；裸 & < > 被转义，避免 reportlab 解析异常。"""
        from utils.pdf_report import _md_to_rl

        assert _md_to_rl("总曝光 **1,234**") == "总曝光 <b>1,234</b>"
        assert _md_to_rl("a & b < c > d") == "a &amp; b &lt; c &gt; d"


# ============================================================
# 访问门禁（utils.auth.require_auth）
# ============================================================

class TestAccessGate:
    def test_no_password_does_not_block_but_warns(self):
        """未配置 [auth] password 时不阻断（本地/示例可用），但常驻告警。"""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=30).run()
        assert not at.exception
        assert any("访问口令" in str(w.value) for w in at.warning)

    def test_password_blocks_until_correct(self):
        """配置口令后：未输入被阻断 → 输错报错 → 输对解锁。"""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=30)
        at.secrets["auth"] = {"password": "s3cret"}
        at.run()
        # 阻断态：出现口令输入框，尚未解锁
        assert len(at.text_input) > 0
        assert "_auth_ok" not in at.session_state or at.session_state["_auth_ok"] is not True

        # 输错
        at.text_input[0].set_value("nope").run()
        assert any("口令错误" in str(e.value) for e in at.error)

        # 输对 → 解锁，输入框消失
        at.text_input[0].set_value("s3cret").run()
        assert at.session_state["_auth_ok"] is True
        assert len(at.text_input) == 0
        assert not at.exception


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

    def test_backfill_chunks_cover_window_no_overlap(self):
        """回填脚本按 chunk_days 切窗口：所有 chunk 拼起来覆盖完整 [since, until]，
        相邻 chunk 边界不重叠不漏天。"""
        from scripts.backfill import _iter_chunks
        from datetime import date as _date

        since = _date(2025, 1, 1)
        until = _date(2025, 6, 30)
        chunks = list(_iter_chunks(since, until, 30))

        # 第一个 chunk 从 since 开始
        assert chunks[0][0] == since
        # 最后一个 chunk 到 until 结束
        assert chunks[-1][1] == until
        # 相邻边界连贯（前 chunk_until + 1 day == 后 chunk_since），无重叠
        for a, b in zip(chunks, chunks[1:]):
            assert (b[0] - a[1]).days == 1
        # 总天数加起来等于窗口长度
        total = sum((c[1] - c[0]).days + 1 for c in chunks)
        assert total == (until - since).days + 1

    def test_backfill_chunks_handle_single_day_window(self):
        """单日窗口（since == until）应当生成恰好 1 个 chunk 包含那一天。"""
        from scripts.backfill import _iter_chunks
        from datetime import date as _date

        day = _date(2025, 5, 15)
        chunks = list(_iter_chunks(day, day, 30))
        assert chunks == [(day, day)]

    def test_sheet_schema_includes_follower_growth(self):
        """Sheet 必须把 follower_growth 也持久化下来 —— IG 和 YouTube 的 API
        给出的当日净增数据，若在 write() 这一步被 df[STANDARD_COLS] 选列丢掉，
        Sheet 中只剩 followers（一个最后一天的总数快照），其他天的增长信息全失。"""
        from utils.data_sources import _SHEET_ALL_COLS, _SHEET_EXTRA_COLS

        assert "follower_growth" in _SHEET_ALL_COLS
        assert "follower_growth" in _SHEET_EXTRA_COLS
        # 不可破坏 STANDARD_COLS 原有契约
        from utils.data_loader import STANDARD_COLS
        assert _SHEET_ALL_COLS[: len(STANDARD_COLS)] == STANDARD_COLS

    def test_cell_merge_preserves_existing_when_new_is_nan(self):
        """cell_merge：手动收集的真实 followers 不应被 API 拉取的 NaN followers 清掉。
        （之前 _merge_into_session 用整行替换会丢这个值。）"""
        import numpy as _np
        from utils.data_sources import cell_merge

        # 手动收集（已有）：followers 完整
        existing = pd.DataFrame({
            "platform": ["facebook"],
            "date": pd.to_datetime(["2026-04-01"]),
            "followers": [111712.0],
            "impressions": [16751.0],
            "reach": [_np.nan],
            "likes": [128.0],
        })
        # API 新拉：followers/impressions=NaN（Meta 给不了），reach/likes 有值
        new = pd.DataFrame({
            "platform": ["facebook"],
            "date": pd.to_datetime(["2026-04-01"]),
            "followers": [_np.nan],
            "impressions": [_np.nan],
            "reach": [12724.0],
            "likes": [245.0],
        })
        out = cell_merge(new, existing).set_index(["platform", "date"]).loc[("facebook", pd.Timestamp("2026-04-01"))]
        assert out["followers"] == 111712.0     # 手动值保留
        assert out["impressions"] == 16751.0    # 手动值保留
        assert out["reach"] == 12724.0          # API 值填入空格
        assert out["likes"] == 245.0            # API 值覆盖旧值

    def test_cell_merge_adds_new_rows_and_keeps_orphan_existing(self):
        """cell_merge：existing 独有的行保留，new 独有的行加入。"""
        from utils.data_sources import cell_merge
        existing = pd.DataFrame({
            "platform": ["facebook"], "date": pd.to_datetime(["2026-04-01"]), "followers": [100.0],
        })
        new = pd.DataFrame({
            "platform": ["facebook"], "date": pd.to_datetime(["2026-04-02"]), "reach": [50.0],
        })
        out = cell_merge(new, existing)
        keys = set(zip(out["platform"], out["date"].astype(str)))
        assert ("facebook", "2026-04-01") in keys   # 旧行保留
        assert ("facebook", "2026-04-02") in keys   # 新行加入

    def test_sheets_merge_self_heals_column_swapped_dirty_rows(self):
        """端到端：Sheet 里残留列错位的脏数据（date 列装着 'facebook'），
        merge 写入时应自动丢弃这些 NaT 行，并把新数据按正确列序写回，
        最终 Sheet 表头/数据对齐，不再污染。"""
        import pandas as _pd
        from unittest.mock import MagicMock, patch
        from utils.data_sources import GoogleSheetsSource, _SHEET_ALL_COLS

        # 模拟 get_all_records 读到列错位的脏数据：
        # 表头是正确的 [date, platform, ...]，但数据行是 [facebook, 2026-04-01, ...]
        dirty = [
            {"date": "facebook", "platform": "2026-04-01", "followers": 111712,
             "impressions": 16751, "reach": "", "likes": 128, "comments": "",
             "shares": "", "saves": "", "posts_count": "", "follower_growth": ""},
        ]
        new_df = _pd.DataFrame({
            "date": _pd.to_datetime(["2026-04-01"]),
            "platform": ["facebook"],
            "reach": [12724],
            "likes": [245],
        })

        captured = {}
        fake_ws = MagicMock()
        fake_ws.get_all_records.return_value = dirty
        fake_ws.update.side_effect = lambda values, *a, **k: captured.__setitem__("values", values)

        src = GoogleSheetsSource.__new__(GoogleSheetsSource)
        with patch.object(GoogleSheetsSource, "_open_worksheet", return_value=fake_ws):
            src.write(new_df, mode="merge")

        hdr, rows = captured["values"][0], captured["values"][1:]
        # 表头正确
        assert hdr == _SHEET_ALL_COLS
        # 脏行被丢弃，只剩 1 行新数据，且列对齐
        assert len(rows) == 1
        assert rows[0][0] == "2026-04-01"   # date 列
        assert rows[0][1] == "facebook"     # platform 列
        assert rows[0][hdr.index("reach")] == 12724
        assert rows[0][hdr.index("likes")] == 245.0

    def test_sheets_merge_keeps_standard_column_order(self):
        """combine_first 走 set_index(['platform','date']) + reset_index() 会把
        platform/date 挪到最前，列序变成 [platform, date, ...]。写入时表头用的
        是 _SHEET_ALL_COLS（date 在前），不对齐就会表头/数据错位（Sheet 里
        date 列底下显示 platform 值）。这里钉死合并后必须重排回标准列序。"""
        import numpy as _np
        from utils.data_sources import _SHEET_ALL_COLS

        existing = pd.DataFrame({
            "date": pd.to_datetime(["2026-04-01"]),
            "platform": ["facebook"],
            "followers": [111712.0],
        })
        new_df = pd.DataFrame({
            "date": pd.to_datetime(["2026-04-02"]),
            "platform": ["facebook"],
            "followers": [112101.0],
        })
        # 复刻 write 里的合并 + 强制列序
        for d in (existing, new_df):
            for col in _SHEET_ALL_COLS:
                if col not in d.columns:
                    d[col] = _np.nan
        new_indexed = new_df[_SHEET_ALL_COLS].set_index(["platform", "date"])
        existing_indexed = existing[_SHEET_ALL_COLS].set_index(["platform", "date"])
        merged = new_indexed.combine_first(existing_indexed).reset_index()
        merged = merged.sort_values(["platform", "date"]).reset_index(drop=True)
        merged = merged[_SHEET_ALL_COLS]  # ← 被测的关键修复

        assert list(merged.columns) == _SHEET_ALL_COLS
        assert merged.columns[0] == "date"
        assert merged.columns[1] == "platform"

    def test_sheets_merge_preserves_existing_cells_when_new_is_nan(self):
        """merge 模式必须是 cell-level：新数据某列是 NaN 时不能清掉旧数据同列。
        场景：sample CSV 已同步 followers=111712 / impressions=16751；新 Meta
        回填 followers=NaN / impressions=NaN（Meta 砍了对应指标）/ reach=12724。
        合并后 followers 和 impressions 应保留 111712 / 16751，reach 取新值。"""
        import numpy as _np
        existing = pd.DataFrame({
            "date": pd.to_datetime(["2026-04-01"]),
            "platform": ["facebook"],
            "followers": [111712.0],
            "impressions": [16751.0],
            "reach": [_np.nan],
            "likes": [128.0],
        })
        new_df = pd.DataFrame({
            "date": pd.to_datetime(["2026-04-01"]),
            "platform": ["facebook"],
            "followers": [_np.nan],
            "impressions": [_np.nan],
            "reach": [12724.0],
            "likes": [245.0],
        })
        # 复刻 GoogleSheetsSource.write 里的 combine_first 流程
        new_indexed = new_df.set_index(["platform", "date"])
        existing_indexed = existing.set_index(["platform", "date"])
        merged = new_indexed.combine_first(existing_indexed).reset_index()
        row = merged.iloc[0]
        assert row["followers"] == 111712.0     # 保留旧值
        assert row["impressions"] == 16751.0    # 保留旧值
        assert row["reach"] == 12724.0          # 取新值（旧的为 NaN）
        assert row["likes"] == 245.0            # 新值覆盖旧值（都非空时新赢）

    def test_ig_follower_count_gated_by_30day_window(self):
        """Meta 拒绝 IG follower_count 在 30 天以外的查询，否则连带 reach 也
        一起被毙。fetch_instagram 必须在 since < today-30d 时把这个 metric
        从请求里剔除。"""
        from datetime import date as _date, timedelta as _td
        from unittest.mock import patch

        from utils.meta_graph import MetaGraphSource

        captured = {}

        def fake_get(self, endpoint, **params):
            captured.setdefault("calls", []).append({"endpoint": endpoint, "params": params})
            # 返回空 data 让 fetch_instagram 短路退出（不需要走完整路径）
            if "insights" in endpoint:
                return {"data": []}
            return {"followers_count": 0}

        src = MetaGraphSource(access_token="dummy", page_id="1", ig_user_id="2")

        # 1) since 在 30 天内 → 应包含 follower_count
        with patch.object(MetaGraphSource, "_get", fake_get), \
             patch.object(MetaGraphSource, "_fetch_ig_media_in_range", lambda self, *a, **kw: []):
            captured.clear()
            src.fetch_instagram(_date.today() - _td(days=5), _date.today(), include_total_snapshot=False)
            insights_call = next(c for c in captured["calls"] if "insights" in c["endpoint"])
            assert "follower_count" in insights_call["params"]["metric"]

        # 2) since 在 30 天外 → 应剔除 follower_count（仅保留 reach）
        with patch.object(MetaGraphSource, "_get", fake_get), \
             patch.object(MetaGraphSource, "_fetch_ig_media_in_range", lambda self, *a, **kw: []):
            captured.clear()
            src.fetch_instagram(_date.today() - _td(days=60), _date.today() - _td(days=45),
                                include_total_snapshot=False)
            insights_call = next(c for c in captured["calls"] if "insights" in c["endpoint"])
            assert "follower_count" not in insights_call["params"]["metric"]
            assert "reach" in insights_call["params"]["metric"]

    def test_meta_day_from_end_time_subtracts_one_day(self):
        """Meta insights end_time 是周期结束（次日 00:00），实际数据日要减 1。
        旧代码用 entry['end_time'][:10] 直接拿日期，导致 Sheet 中所有 FB/IG 行
        都晚一天（窗口结束 2026-05-29 会出现 2026-05-30 行）。"""
        from utils.meta_graph import _day_from_end_time

        assert _day_from_end_time("2026-05-30T08:00:00+0000") == "2026-05-29"
        assert _day_from_end_time("2026-01-01T00:00:00+0000") == "2025-12-31"
        # 边界 / 异常输入不应抛异常
        assert _day_from_end_time("") is None
        assert _day_from_end_time("not-a-date") is None
        assert _day_from_end_time(None) is None  # type: ignore[arg-type]

    def test_instagram_insights_day_aligns_with_media_day(self):
        """IG insights（reach / follower_count）必须和媒体聚合（likes/comments）
        落在同一真实数据日。insights 的 end_time 比数据日晚 1 天，媒体用帖子
        timestamp（真实当天）—— 若 insights 不减 1 天，会被拆成错位的两行：
        reach 落到 day+1、互动落到 day。"""
        from datetime import date
        from utils.meta_graph import MetaGraphSource

        src = MetaGraphSource(access_token="x", page_id="1", ig_user_id="42")

        # insights：2026-05-20 的数据，end_time = 次日 00:00（晚 1 天）
        def _fake_get(path, **params):
            assert path == "42/insights"
            return {
                "data": [
                    {"name": "reach", "values": [
                        {"end_time": "2026-05-21T07:00:00+0000", "value": 500},
                    ]},
                    {"name": "follower_count", "values": [
                        {"end_time": "2026-05-21T07:00:00+0000", "value": 12},
                    ]},
                ]
            }

        # 媒体：同一真实日 2026-05-20 发的帖
        def _fake_media(since, until):
            return [
                {"timestamp": "2026-05-20T15:00:00+0000",
                 "like_count": 30, "comments_count": 4},
            ]

        src._get = _fake_get  # type: ignore[method-assign]
        src._fetch_ig_media_in_range = _fake_media  # type: ignore[method-assign]

        df = src.fetch_instagram(
            date(2026, 5, 20), date(2026, 5, 20), include_total_snapshot=False
        )

        # 只应有 1 行，且日期是真实数据日 2026-05-20（不是 end_time 的 05-21）
        assert len(df) == 1
        row = df.iloc[0]
        assert row["date"].strftime("%Y-%m-%d") == "2026-05-20"
        # insights 与媒体聚合落在同一行
        assert row["reach"] == 500
        assert row["follower_growth"] == 12
        assert row["likes"] == 30
        assert row["comments"] == 4

    def test_backfill_iter_chunks_rejects_nonpositive(self):
        """chunk_days<=0 会让窗口指针不前进 → 死循环；必须早抛 ValueError。"""
        from scripts.backfill import _iter_chunks
        from datetime import date as _date

        with pytest.raises(ValueError):
            list(_iter_chunks(_date(2025, 1, 1), _date(2025, 2, 1), 0))

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


# ============================================================
# 数据源治理（C2 / C3）
# ============================================================

class TestDataSourceGovernance:
    """C2：示例兜底只读单份标准化 demo（不再全量拼接 data/samples）。
    C3：exposure_base 是派生列，不持久化到 Sheet。"""

    def test_fallback_reads_single_demo_not_full_samples(self, monkeypatch):
        """C2：无上传 + 无 Sheet + data/ 空 → 只读 demo_all_platforms.csv，
        不把 data/samples 下手动真实数据也拼进来。"""
        import utils.data_sources as ds
        from utils.data_loader import load_csv

        monkeypatch.setattr(ds, "has_uploaded_dataframe", lambda: False)
        monkeypatch.setattr(ds, "_try_load_gsheets", lambda: None)
        # data/ 真实目录指向不存在的路径 → 空 → 落到 demo 分支
        monkeypatch.setattr(ds, "_REAL_LOCAL_DIR", "data/__does_not_exist__")

        raw, label = ds._resolve_source()
        # 走单份 demo 分支（而非全量 glob 的 "本地 CSV (data/samples)"）
        assert label == "示例数据 (demo)"
        # 行数 == 直接读 demo 文件，证明没把别的 samples 文件（含手动真实数据）拼进来
        assert len(raw) == len(load_csv(ds._DEMO_FILE))
        assert sorted(raw["platform"].dropna().unique().tolist()) == [
            "facebook", "instagram", "linkedin", "tiktok", "x", "youtube",
        ]

    def test_exposure_base_not_persisted_to_sheet(self):
        """C3：即便传入带 exposure_base 的 df，写 Sheet 也只落 _SHEET_ALL_COLS。"""
        from unittest.mock import MagicMock, patch
        from utils.data_sources import GoogleSheetsSource, _SHEET_ALL_COLS

        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-04-01"]),
            "platform": ["facebook"],
            "followers": [111712.0],
            "reach": [12724.0],
            "exposure_base": [12724.0],  # 派生列，混进来也必须被丢弃
        })
        captured = {}
        fake_ws = MagicMock()
        fake_ws.update.side_effect = lambda values, *a, **k: captured.__setitem__("values", values)

        src = GoogleSheetsSource.__new__(GoogleSheetsSource)
        with patch.object(GoogleSheetsSource, "_open_worksheet", return_value=fake_ws):
            src.write(df, mode="replace")

        header = captured["values"][0]
        assert "exposure_base" not in header
        assert header == _SHEET_ALL_COLS
        assert "exposure_base" not in _SHEET_ALL_COLS  # 钉死常量本身不含派生列


# ============================================================
# 呈现层 N/A（H6）
# ============================================================

class TestNAFormatting:
    """H6：呈现层把 NaN 渲染成 N/A 而非 0（决策 #4）。两视图共用 utils.ui.fmt_or_na。"""

    def test_nan_like_renders_na(self):
        from utils.ui import fmt_or_na
        assert fmt_or_na(np.nan) == "N/A"
        assert fmt_or_na(None) == "N/A"
        assert fmt_or_na(pd.NA) == "N/A"
        assert fmt_or_na(pd.NaT) == "N/A"

    def test_value_renders_formatted(self):
        from utils.ui import fmt_or_na
        assert fmt_or_na(1234567) == "1,234,567"
        assert fmt_or_na(7.214, "{:.2f}", "%") == "7.21%"
        assert fmt_or_na(50, "{:+,.0f}") == "+50"

    def test_zero_is_real_value_not_na(self):
        """0 是真实值，照常显示——只有 NaN 才 N/A（正是范式转变要区分的）。"""
        from utils.ui import fmt_or_na
        assert fmt_or_na(0) == "0"
        assert fmt_or_na(0.0, "{:.2f}", "%") == "0.00%"
