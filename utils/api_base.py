"""所有平台 API 模块的共享基础设施。

提供：
- APIConfigError / APIError：每个平台的错误类继承自这两个基类
- APISourceBase：统一的 secrets 读取 + 字段校验 + 带退避重试的 HTTP 请求
"""

from __future__ import annotations

import time
from typing import ClassVar

import requests


class APIConfigError(Exception):
    """配置缺失或无效时抛出（各平台错误类继承此类）。"""


class APIError(Exception):
    """API 调用失败时抛出（各平台错误类继承此类）。"""

    def __init__(self, message: str, status_code: int = 0, extra: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.extra = extra or {}


_DEFAULT_TIMEOUT = 20
_RETRY_STATUS = (429, 500, 502, 503, 504)


class APISourceBase:
    """各平台 Source 类的基类。子类需覆盖 SECRETS_SECTION + REQUIRED_FIELDS。"""

    # 子类必须覆盖
    SECRETS_SECTION: ClassVar[str] = ""
    REQUIRED_FIELDS: ClassVar[tuple[str, ...]] = ()

    # 子类决定异常类型（让 except XxxConfigError 仍能精确捕获）
    CONFIG_ERROR_CLS: ClassVar[type[APIConfigError]] = APIConfigError
    API_ERROR_CLS: ClassVar[type[APIError]] = APIError

    # ------------------------------------------------------------------
    # 配置 / Secrets
    # ------------------------------------------------------------------

    @classmethod
    def is_configured(cls) -> bool:
        """secrets.toml 是否已配齐所有必填字段。不抛异常。"""
        try:
            import streamlit as st
            cfg = st.secrets.get(cls.SECRETS_SECTION, {})
            return all(cfg.get(f) for f in cls.REQUIRED_FIELDS)
        except Exception:  # noqa: BLE001
            return False

    @classmethod
    def _load_secrets(cls) -> dict:
        """读取并校验 secrets，返回字典。校验失败抛 cls.CONFIG_ERROR_CLS。"""
        import streamlit as st
        cfg = st.secrets.get(cls.SECRETS_SECTION)
        if not cfg:
            raise cls.CONFIG_ERROR_CLS(
                f"secrets.toml 缺少 [{cls.SECRETS_SECTION}] 区段，请参考 secrets.toml.example。"
            )
        missing = [f for f in cls.REQUIRED_FIELDS if not cfg.get(f)]
        if missing:
            raise cls.CONFIG_ERROR_CLS(
                f"[{cls.SECRETS_SECTION}] 缺少必要字段：{', '.join(missing)}。"
            )
        return dict(cfg)

    # ------------------------------------------------------------------
    # HTTP 请求（统一的退避重试）
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        params: dict | None = None,
        json: dict | None = None,
        retries: int = 3,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> requests.Response:
        """发起 HTTP 请求，对网络错误和 429/5xx 做指数退避重试。

        不解析响应体也不检查 status_code（保留给调用方处理 401 等业务逻辑）。
        """
        last_exc: Exception | None = None
        resp: requests.Response | None = None
        for attempt in range(retries):
            try:
                resp = requests.request(
                    method, url,
                    headers=headers, params=params, json=json,
                    timeout=timeout,
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise self.API_ERROR_CLS(f"网络请求失败：{exc}") from exc
            if resp.status_code in _RETRY_STATUS and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            return resp
        if resp is not None:
            return resp
        raise self.API_ERROR_CLS(f"超过重试次数，请求失败：{last_exc}")
