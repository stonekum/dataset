"""共享日志工具：在 Streamlit 运行时显示 st.warning，否则走标准 logger。

替换之前散落在 data_loader.py 里的私有 _emit_warning，让 4 个 API 模块
也能用统一的方式给用户报错（Cloud 上 logger.warning 用户看不到）。
"""

from __future__ import annotations

import logging

_logger = logging.getLogger("dashboard")


def emit_warning(message: str) -> None:
    """在 Streamlit 运行时中用 st.warning，否则记到标准 logger。"""
    try:
        import streamlit as st
        from streamlit.runtime import exists as _runtime_exists

        if _runtime_exists():
            st.warning(message)
            return
    except Exception:  # noqa: BLE001
        pass
    _logger.warning(message)


def emit_error(message: str) -> None:
    """同 emit_warning，但用 st.error。"""
    try:
        import streamlit as st
        from streamlit.runtime import exists as _runtime_exists

        if _runtime_exists():
            st.error(message)
            return
    except Exception:  # noqa: BLE001
        pass
    _logger.error(message)
