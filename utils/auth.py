"""应用级访问门禁（纵深防御）。

部署到 Streamlit Community Cloud 时，安全本来只靠"手动把 app 设为 Private"
这一步人工操作——一旦忘记，公网任何人拿到 URL 就能看全部数据、烧 API 配额。
本模块把这层防护从"靠人记得"变成"代码强制"：

- secrets 配了 `[auth] password` → 进入任何页面前必须输入口令，否则 st.stop()。
- 没配口令 → 不阻断（本地开发、示例数据体验照常），但在页面顶部常驻一条
  醒目告警，提醒"当前无口令保护，请配置或在 Streamlit Cloud 设为 Private"。

口令以明文存在 secrets（与其他凭据同级，本就只有部署者可见），比较用
hmac.compare_digest 做常量时间比较，避免计时侧信道。

需要更强的身份认证（按人区分、可审计）时，可换成 Streamlit 原生
`st.login()`（OIDC），但那需要额外配置身份提供方，对小团队偏重。
"""

from __future__ import annotations

import hmac

import streamlit as st

_AUTH_SECTION = "auth"
_OK_KEY = "_auth_ok"


def _configured_password() -> str | None:
    """从 secrets 读取访问口令；未配置（或无 secrets 文件）时返回 None。"""
    try:
        section = st.secrets[_AUTH_SECTION]
    except Exception:  # noqa: BLE001 - secrets 文件可能整体不存在
        return None
    pw = section.get("password")
    if pw is None:
        return None
    pw = str(pw)
    return pw if pw else None


def require_auth() -> None:
    """页面入口处调用：未通过口令校验则阻断渲染。

    在每个页面脚本（app.py / pages/*.py）注入样式之后、渲染正文之前调用。
    `session_state` 跨页面共享，所以一次解锁后切换页面不会再次要求输入。
    """
    password = _configured_password()

    # 未配置口令：不阻断，但常驻告警，避免"裸奔"被默默忽略。
    if password is None:
        st.warning(
            "⚠️ 当前未设置访问口令，任何拿到链接的人都能访问本面板。"
            "请在 Streamlit Secrets 配置 `[auth] password`，"
            "并在 Streamlit Cloud 把 app 设为 Private。",
            icon="⚠️",
        )
        return

    # 已解锁
    if st.session_state.get(_OK_KEY):
        return

    # 未解锁：显示口令输入，阻断后续渲染
    st.markdown("### 🔒 请输入访问口令")
    entered = st.text_input(
        "访问口令",
        type="password",
        key="_auth_input",
        label_visibility="collapsed",
        placeholder="访问口令",
    )
    if entered:
        if hmac.compare_digest(entered, password):
            st.session_state[_OK_KEY] = True
            # 清掉输入框里的明文口令再重渲染
            st.session_state.pop("_auth_input", None)
            st.rerun()
        else:
            st.error("口令错误，请重试。")
    st.stop()
