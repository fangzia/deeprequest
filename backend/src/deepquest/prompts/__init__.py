"""提示词子包：jinja2 模板渲染 + 角色数据模型。

提供两个核心函数：
- ``get_prompt_template``：按角色与 locale 渲染 system prompt 字符串；
- ``apply_prompt_template``：在 system prompt 后拼接当前会话消息，供直接调用 LLM 的节点使用。
"""

import logging
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

logger = logging.getLogger(__name__)

# 初始化 jinja2 环境：模板与本文件同目录，均为 *.zh_CN.md
_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(),
    trim_blocks=True,
    lstrip_blocks=True,
)

# 支持的角色名（与 prompts/*.zh_CN.md 一一对应）
SUPPORTED_AGENTS = {"coordinator", "planner", "researcher", "analyst", "coder", "reporter"}


def _normalize_locale(locale: str | None) -> str:
    """将 ``zh-CN`` 归一化为模板文件名后缀 ``zh_CN``。"""
    if not locale or not locale.strip():
        return "zh_CN"
    return locale.strip().replace("-", "_")


def get_prompt_template(agent: str, locale: str = "zh-CN", **variables: object) -> str:
    """渲染指定角色的 system prompt 模板。

    Args:
        agent: 角色名（coordinator/planner/researcher/analyst/coder/reporter）。
        locale: 语言区域，默认 ``zh-CN``。
        **variables: 传入模板的额外变量（如 ``max_step_num``）。

    Returns:
        渲染后的 prompt 字符串。

    Raises:
        ValueError: 模板不存在或渲染失败。
    """
    now = datetime.now()
    render_vars = {
        "CURRENT_TIME": now.strftime("%a %b %d %Y %H:%M:%S"),
        "CURRENT_YEAR": now.strftime("%Y"),
        "locale": locale,
        **variables,
    }
    normalized = _normalize_locale(locale)
    try:
        template = _ENV.get_template(f"{agent}.{normalized}.md")
    except TemplateNotFound:
        try:
            # 该 locale 模板缺失时兜底到中文基础模板（项目目前仅提供 zh_CN 版本）。
            # 模板内通过 {{ locale }} 变量指示输出语言，因此非中文 locale
            # 仍能获得对应语言的输出，只是 system prompt 文本为中文。
            template = _ENV.get_template(f"{agent}.zh_CN.md")
        except TemplateNotFound as e:
            raise ValueError(f"未找到角色 {agent} 的 prompt 模板（locale={locale}）") from e
    try:
        return template.render(**render_vars)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"渲染模板 {agent}（locale={locale}）失败: {e}") from e


def apply_prompt_template(
    agent: str,
    state: Mapping,
    locale: str = "zh-CN",
    **variables: object,
) -> list:
    """构造传给 LLM 的完整消息列表：[system prompt] + 当前会话消息。

    Args:
        agent: 角色名。
        state: 图状态（需包含 ``messages`` 键）。
        locale: 语言区域。
        **variables: 传入模板的额外变量。

    Returns:
        消息列表，首条为 ``{"role": "system", ...}``，其后为 state 中的消息。
    """
    system_prompt = get_prompt_template(agent, locale=locale, **variables)
    messages = list(state.get("messages", []) or [])
    return [{"role": "system", "content": system_prompt}, *messages]
