"""LLM 提供者工厂。

统一通过 ``get_llm()`` 获取 OpenAI 兼容的 ChatOpenAI 实例（settings 驱动，进程内缓存）。
默认配置指向 DeepSeek，也可切换到任何 OpenAI 兼容服务（如 vLLM、Ollama、通义千问等）。
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from deepquest.config.settings import get_settings

logger = logging.getLogger(__name__)

# 进程内模型实例缓存：避免重复构造 HTTP 客户端
_LLM_CACHE: dict[str, BaseChatModel] = {}


def get_llm(llm_type: str = "basic") -> BaseChatModel:
    """按类型获取 LLM 实例（带缓存）。

    Args:
        llm_type: 模型类型。当前 ``basic`` 与 ``reasoning`` 共用同一配置
            （简化版），后续可通过 settings 扩展独立配置。

    Returns:
        OpenAI 兼容的聊天模型实例。
    """
    if llm_type in _LLM_CACHE:
        return _LLM_CACHE[llm_type]

    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        max_retries=settings.llm_max_retries,
    )
    _LLM_CACHE[llm_type] = llm
    logger.info("已创建 LLM 实例：type=%s, model=%s, base_url=%s",
                llm_type, settings.llm_model, settings.llm_base_url)
    return llm
