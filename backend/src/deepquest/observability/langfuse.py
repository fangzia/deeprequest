"""Langfuse 可观测性集成（可选组件，未启用时零侵入）。

设计要点：
- 运行时开关 ``DEEPQUEST_LANGFUSE_ENABLED``：关闭（默认）或 langfuse 未安装时，
  ``attach_langfuse_trace`` 原样返回 config，主流程完全不受影响；
- 懒导入：进程首次真正需要 trace 时才 import langfuse，加快冷启动；
- ``session_id=thread_id``：一次研究会话（含中断续传的多次请求）在 Langfuse
  UI 中聚合为同一条 session，便于按研究主题回放全链路。会话绑定通过
  LangChain 运行时 metadata 中的 ``langfuse_session_id`` 实现（Langfuse SDK
  约定的协议，v3/v4 通用）；
- Langfuse 客户端按进程单例注册（SDK 内部按 public_key 管理），避免每次
  请求重建导出器线程。
"""

import logging
from typing import Any

from deepquest.config.settings import get_settings

logger = logging.getLogger(__name__)

# 进程级 Langfuse 客户端缓存（None 表示尚未初始化）
_langfuse_client: Any | None = None


def _get_langfuse_client(settings) -> Any:
    """获取（或首次创建）进程级 Langfuse 客户端。"""
    global _langfuse_client
    if _langfuse_client is None:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_host,
        )
    return _langfuse_client


def attach_langfuse_trace(config: dict, session_id: str) -> dict:
    """把 Langfuse trace 挂载到图执行 config 上（原地修改并返回）。

    Args:
        config: LangGraph 执行配置（含 configurable/recursion_limit 等键）。
        session_id: 会话标识（生产接入中传 thread_id）。

    Returns:
        挂载了 ``callbacks`` 与 ``metadata`` 的 config；
        未启用 / 缺 key / langfuse 未安装时原样返回。
    """
    settings = get_settings()
    if not settings.langfuse_enabled:
        return config

    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.warning(
            "DEEPQUEST_LANGFUSE_ENABLED=true 但缺少 LANGFUSE_PUBLIC_KEY/SECRET_KEY，跳过 trace"
        )
        return config

    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        logger.warning("langfuse 未安装，跳过 trace（可选依赖：uv add langfuse）")
        return config

    _get_langfuse_client(settings)
    handler = CallbackHandler(public_key=settings.langfuse_public_key)

    # Langfuse SDK 约定：根 run 的 metadata 中 langfuse_session_id/langfuse_tags
    # 会被提升为 trace 属性（见 CallbackHandler._parse_langfuse_trace_attributes_from_metadata）
    config["callbacks"] = [*config.get("callbacks", []), handler]
    config["metadata"] = {
        **config.get("metadata", {}),
        "langfuse_session_id": session_id,
        "langfuse_tags": ["deepquest"],
    }
    logger.debug("Langfuse trace 已挂载（session_id=%s）", session_id)
    return config


def flush_langfuse() -> None:
    """把 Langfuse 客户端缓冲区的 trace 数据刷出到服务端（应用关闭前调用）。"""
    global _langfuse_client
    if _langfuse_client is None:
        return
    try:
        _langfuse_client.flush()
    except Exception:  # noqa: BLE001
        logger.warning("Langfuse flush 失败（忽略，不影响应用关闭）", exc_info=True)
