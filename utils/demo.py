"""Public demo mode helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


_TRUTHY = {"1", "true", "yes", "y", "on"}
_FALSY = {"0", "false", "no", "n", "off", ""}


def _as_bool(value: Any) -> bool:
    """把环境变量 / secrets 里的常见布尔写法转成 bool。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    normalized = str(value).strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    return False


def is_demo_mode() -> bool:
    """公网 demo 模式是否启用。

    优先读取环境变量 `DEMO_MODE`；未设置时读取 Streamlit Secrets：

        [demo]
        enabled = true

    demo 模式只用于公开展示：强制合成数据、禁用真实数据源入口。
    """
    env_value = os.environ.get("DEMO_MODE")
    if env_value is not None:
        return _as_bool(env_value)

    try:
        import streamlit as st

        demo_section = st.secrets.get("demo", {})
        # 注意：st.secrets 的嵌套区段是 AttrDict（Mapping 子类，不是 dict 子类），
        # 用 isinstance(x, dict) 判断会漏掉真实 Secrets 路径
        if isinstance(demo_section, Mapping):
            return _as_bool(demo_section.get("enabled"))
        return _as_bool(demo_section)
    except Exception:  # noqa: BLE001 - 无 Streamlit runtime / 无 secrets 文件时均视为关闭
        return False
