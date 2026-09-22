"""SSE 事件转换：LangGraph astream 事件 → SSE 事件 dict 的纯函数集合。

本模块不依赖 FastAPI/Starlette，可独立单测。
SSE 事件协议（event 名 + JSON data 字段）见 ``deepquest/server/schemas.py``。
"""

import json
import logging
from typing import Any

from langchain_core.messages import AIMessageChunk, BaseMessage, ToolMessage

logger = logging.getLogger(__name__)


def make_event(event: str, data: dict) -> dict:
    """构造 sse-starlette 可消费的事件 dict。

    注意：sse-starlette 3.x 不再自动把 dict data 序列化为 JSON（会 str() 化），
    因此这里显式 ``json.dumps``，保证 data 是合法 JSON 字符串。
    """
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def _get_agent_name(namespace: tuple, metadata: dict) -> str:
    """从事件命名空间或元数据中提取代理名。

    优先取 namespace 首元素（形如 "researcher:uuid"），否则回退到
    metadata["langgraph_node"]（节点内代理调用时为外层节点名）。
    """
    if namespace and isinstance(namespace[0], str) and namespace[0]:
        return namespace[0].split(":")[0]
    return metadata.get("langgraph_node", "unknown")


def _content_to_str(content: Any) -> str:
    """把消息 content 统一转为字符串（非字符串时 JSON 序列化）。"""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(content)


def process_message_chunk(
    message_chunk: BaseMessage,
    metadata: dict,
    thread_id: str,
    namespace: tuple = (),
) -> list[dict]:
    """将 messages 流式模式的单个消息 chunk 转换为 SSE 事件列表。

    转换规则：
    - ``ToolMessage`` → ``tool_call_result``；
    - ``AIMessageChunk`` 且带完整 ``tool_calls`` → ``tool_calls``（args 序列化为字符串）；
    - ``AIMessageChunk`` 且仅带 ``tool_call_chunks`` → 逐个产出 ``tool_call_chunks``；
    - 其余 → ``message_chunk``（增量文本）。
    """
    agent = _get_agent_name(namespace, metadata)
    events: list[dict] = []

    if isinstance(message_chunk, ToolMessage):
        events.append(
            make_event(
                "tool_call_result",
                {
                    "thread_id": thread_id,
                    "agent": agent,
                    "tool_name": message_chunk.name or "",
                    "content": _content_to_str(message_chunk.content),
                    "status": getattr(message_chunk, "status", "success") or "success",
                },
            )
        )
    elif isinstance(message_chunk, AIMessageChunk):
        if message_chunk.tool_calls:
            # 完整工具调用（流式聚合完成）
            tool_calls = [
                {
                    "name": tc.get("name", ""),
                    "args": (
                        tc.get("args", "")
                        if isinstance(tc.get("args"), str)
                        else json.dumps(tc.get("args", {}), ensure_ascii=False)
                    ),
                    "id": tc.get("id", ""),
                }
                for tc in message_chunk.tool_calls
            ]
            events.append(
                make_event(
                    "tool_calls",
                    {"thread_id": thread_id, "agent": agent, "tool_calls": tool_calls},
                )
            )
        elif message_chunk.tool_call_chunks:
            # 流式工具调用分片：逐个产出（不同 index 表示不同工具调用的边界）
            for chunk in message_chunk.tool_call_chunks:
                events.append(
                    make_event(
                        "tool_call_chunks",
                        {
                            "thread_id": thread_id,
                            "agent": agent,
                            "tool_call_chunk": {
                                "name": chunk.get("name") or "",
                                "args": chunk.get("args") or "",
                                "id": chunk.get("id") or "",
                                "index": chunk.get("index", 0),
                            },
                        },
                    )
                )
        else:
            content = _content_to_str(message_chunk.content)
            if content:
                events.append(
                    make_event(
                        "message_chunk",
                        {"thread_id": thread_id, "agent": agent, "content": content},
                    )
                )
    else:
        # 其他消息类型（HumanMessage 等）：有内容时按增量文本透传
        content = _content_to_str(getattr(message_chunk, "content", ""))
        if content:
            events.append(
                make_event(
                    "message_chunk",
                    {"thread_id": thread_id, "agent": agent, "content": content},
                )
            )

    return events


def process_updates(updates: dict, thread_id: str) -> list[dict]:
    """将 updates 流式模式的节点状态更新转换为 SSE 事件列表。

    转换规则：
    - 含 ``__interrupt__`` → ``interrupt``（计划评审）；
    - 某节点 update 中追加了 ``observations`` → ``step_result``（该步执行结果）。
    """
    events: list[dict] = []

    # 人工中断事件
    if "__interrupt__" in updates:
        interrupt_obj = updates["__interrupt__"][0]
        value = getattr(interrupt_obj, "value", None)
        if isinstance(value, dict):
            events.append(
                make_event(
                    "interrupt",
                    {
                        "thread_id": thread_id,
                        "type": value.get("type", "plan_review"),
                        "plan": value.get("plan", ""),
                    },
                )
            )
        else:
            # 防御：interrupt 值不是预期的 dict 时原样透传
            events.append(
                make_event(
                    "interrupt",
                    {"thread_id": thread_id, "type": "plan_review", "plan": str(value)},
                )
            )

    # 节点执行完毕的状态更新：observations 追加即步骤完成
    for node_name, state_update in updates.items():
        if node_name == "__interrupt__" or not isinstance(state_update, dict):
            continue
        observations = state_update.get("observations")
        if observations:
            events.append(
                make_event(
                    "step_result",
                    {
                        "thread_id": thread_id,
                        "agent": node_name,
                        "topic": state_update.get("current_step", ""),
                        "content": observations[-1],
                    },
                )
            )

    return events
