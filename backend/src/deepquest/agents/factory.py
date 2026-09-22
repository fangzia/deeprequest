"""代理工厂：统一封装研究团队各代理的创建逻辑。

适配说明：``langgraph.prebuilt.create_react_agent`` 在已安装的 langgraph 1.x 中已
标记废弃（V2.0 移除），迁移至 ``langchain.agents.create_agent``。新 API 的
``system_prompt`` 仅接受静态字符串，但本项目中代理是**每个研究步骤动态创建**的，
locale 在创建时已从图状态获得，因此将 locale 渲染进模板即可保留原有
"locale closure" 语义，无需 callable prompt。
"""

import logging

from langchain.agents import create_agent as _lc_create_agent
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from deepquest.llm.provider import get_llm
from deepquest.prompts import get_prompt_template

logger = logging.getLogger(__name__)


def create_agent(
    agent_name: str,
    tools: list[BaseTool],
    locale: str = "zh-CN",
) -> CompiledStateGraph:
    """创建一个具备指定工具与角色 prompt 的 ReAct 代理。

    Args:
        agent_name: 代理名（researcher/analyst/coder），同时是 prompt 模板名与 SSE 的 agent 名。
        tools: 代理可用的工具列表。
        locale: 语言区域，渲染进 system prompt。

    Returns:
        已编译的代理图（CompiledStateGraph）。
    """
    system_prompt = get_prompt_template(agent_name, locale=locale)
    agent = _lc_create_agent(
        get_llm(),
        tools,
        system_prompt=system_prompt,
        name=agent_name,
    )
    logger.info(
        "已创建代理 %s（工具数=%d, locale=%s）", agent_name, len(tools), locale
    )
    return agent
