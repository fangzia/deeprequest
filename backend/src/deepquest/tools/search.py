"""网络搜索工具：基于官方 langchain-tavily 封装。

Tavily API key 缺失时返回一个同名占位工具，调用时给出清晰的错误提示
而不是让整个研究流程崩溃。
"""

import logging

from langchain_core.tools import BaseTool, tool
from langchain_tavily import TavilySearch

from deepquest.config.settings import get_settings

logger = logging.getLogger(__name__)

# 统一对外的工具名（SSE 协议与前端的 tool_call 事件依赖该名称）
SEARCH_TOOL_NAME = "web_search"


def _make_missing_key_tool() -> BaseTool:
    """构造一个缺少 API key 时使用的占位搜索工具。"""

    @tool(SEARCH_TOOL_NAME)
    def web_search(query: str) -> str:
        """执行网络搜索（当前不可用：缺少 Tavily API key）。"""
        return (
            "错误：未配置 TAVILY_API_KEY，web_search 工具不可用。"
            "请在 backend/.env 中设置 TAVILY_API_KEY（可在 https://tavily.com 免费注册获取），"
            "然后重启服务。"
        )

    return web_search


def get_web_search_tool(max_results: int = 3) -> BaseTool:
    """获取网络搜索工具。

    Args:
        max_results: 单次搜索返回的最大结果数。

    Returns:
        Tavily 搜索工具；若未配置 TAVILY_API_KEY，则返回带清晰错误提示的占位工具。
    """
    settings = get_settings()
    if not settings.tavily_api_key:
        logger.warning("TAVILY_API_KEY 未配置，web_search 将返回错误提示")
        return _make_missing_key_tool()

    return TavilySearch(
        name=SEARCH_TOOL_NAME,
        max_results=max_results,
        search_depth="advanced",
    )
