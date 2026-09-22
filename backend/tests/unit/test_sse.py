"""SSE 事件转换单测：AIMessageChunk / ToolMessage / updates 各场景。

说明：``make_event`` 产出的 ``data`` 是 JSON 字符串（sse-starlette 3.x 不再自动
序列化 dict data），测试中统一先 ``json.loads`` 再断言。
"""

import json

from langchain_core.messages import AIMessageChunk, ToolMessage

from deepquest.server.sse import make_event, process_message_chunk, process_updates


def _decode(events: list[dict]) -> list[tuple[str, dict]]:
    """把事件列表解码为 (event 名, data dict) 便于断言。"""
    return [(e["event"], json.loads(e["data"])) for e in events]


def test_make_event_shape():
    """make_event 产出 sse-starlette 消费的事件 dict，data 为合法 JSON 字符串。"""
    ev = make_event("start", {"thread_id": "t1"})
    assert ev["event"] == "start"
    assert json.loads(ev["data"]) == {"thread_id": "t1"}


def test_text_chunk_emits_message_chunk():
    """纯文本 AIMessageChunk → message_chunk 事件。"""
    chunk = AIMessageChunk(content="你好")
    events = _decode(process_message_chunk(chunk, {"langgraph_node": "planner"}, "t1"))
    assert events == [
        ("message_chunk", {"thread_id": "t1", "agent": "planner", "content": "你好"})
    ]


def test_agent_name_from_namespace():
    """namespace 首元素形如 'researcher:uuid' 时优先取代理名。"""
    chunk = AIMessageChunk(content="数据")
    events = _decode(
        process_message_chunk(chunk, {"langgraph_node": "model"}, "t1", ("researcher:abc",))
    )
    assert events[0][1]["agent"] == "researcher"


def test_non_str_content_serialized_to_json():
    """content 为 list（多模态）时序列化为 JSON 字符串。"""
    chunk = AIMessageChunk(content=[{"type": "text", "text": "hi"}])
    events = _decode(process_message_chunk(chunk, {"langgraph_node": "reporter"}, "t1"))
    assert events[0][1]["content"].startswith("[")


def test_tool_calls_emits_tool_calls_event_with_str_args():
    """带完整 tool_calls 的 AIMessageChunk → tool_calls 事件，args 序列化为字符串。"""
    chunk = AIMessageChunk(
        content="",
        tool_calls=[{"name": "web_search", "args": {"query": "AI"}, "id": "call_1"}],
    )
    events = _decode(process_message_chunk(chunk, {"langgraph_node": "researcher"}, "t1"))
    assert len(events) == 1
    event, data = events[0]
    assert event == "tool_calls"
    assert data["tool_calls"] == [
        {"name": "web_search", "args": '{"query": "AI"}', "id": "call_1"}
    ]


def test_tool_call_chunks_emits_chunk_events():
    """args 增量分片（无 name/id，真实流式的后续分片形态）→ tool_call_chunks 事件。

    说明：带 name/id 的分片会被 langchain-core 聚合出 tool_calls，走 tool_calls 分支；
    仅无 name 的 args 增量分片不会聚合，走 tool_call_chunks 分支。
    """
    chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": None, "args": 'ry": "AI"}', "id": None, "index": 0}],
    )
    events = _decode(process_message_chunk(chunk, {"langgraph_node": "researcher"}, "t1"))
    assert len(events) == 1
    event, data = events[0]
    assert event == "tool_call_chunks"
    assert data["tool_call_chunk"] == {
        "name": "",
        "args": 'ry": "AI"}',
        "id": "",
        "index": 0,
    }


def test_multiple_tool_call_chunks_emit_multiple_events():
    """多个 args 增量分片（独立到达，真实流式形态）逐个产出事件。

    说明：args 为非 JSON 前缀的增量文本（字符串中部）时不会聚合出 tool_calls；
    合法 JSON 前缀（如 '{"url"'）会被 best-effort 聚合，走 tool_calls 分支。
    """
    chunk_1 = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": None, "args": 'ry": "AI"}', "id": None, "index": 0}],
    )
    chunk_2 = AIMessageChunk(
        content="",
        tool_call_chunks=[
            {"name": None, "args": 'rl": "https://example.com"}', "id": None, "index": 1},
        ],
    )
    events_1 = _decode(
        process_message_chunk(chunk_1, {"langgraph_node": "researcher"}, "t1")
    )
    events_2 = _decode(
        process_message_chunk(chunk_2, {"langgraph_node": "researcher"}, "t1")
    )
    assert len(events_1) == 1
    assert len(events_2) == 1
    assert events_1[0][1]["tool_call_chunk"]["index"] == 0
    assert events_2[0][1]["tool_call_chunk"]["index"] == 1


def test_tool_message_emits_tool_call_result():
    """ToolMessage → tool_call_result 事件。"""
    msg = ToolMessage(content="搜索结果", name="web_search", tool_call_id="call_1")
    events = _decode(process_message_chunk(msg, {"langgraph_node": "researcher"}, "t1"))
    assert events == [
        (
            "tool_call_result",
            {
                "thread_id": "t1",
                "agent": "researcher",
                "tool_name": "web_search",
                "content": "搜索结果",
                "status": "success",
            },
        )
    ]


def test_tool_message_error_status():
    """ToolMessage 带 error 状态时 status 为 error。"""
    msg = ToolMessage(
        content="工具出错", name="crawl_tool", tool_call_id="call_1", status="error"
    )
    events = _decode(process_message_chunk(msg, {"langgraph_node": "researcher"}, "t1"))
    assert events[0][1]["status"] == "error"


def test_empty_content_chunk_emits_nothing():
    """空 content 的 AIMessageChunk 不产出事件。"""
    chunk = AIMessageChunk(content="")
    assert process_message_chunk(chunk, {"langgraph_node": "planner"}, "t1") == []


def test_updates_interrupt_event():
    """updates 含 __interrupt__ → interrupt 事件（计划评审）。"""

    class FakeInterrupt:
        value = {"type": "plan_review", "plan": '{"title": "T"}'}

    events = _decode(process_updates({"__interrupt__": [FakeInterrupt()]}, "t1"))
    assert events == [
        (
            "interrupt",
            {
                "thread_id": "t1",
                "type": "plan_review",
                "plan": '{"title": "T"}',
            },
        )
    ]


def test_updates_interrupt_non_dict_value():
    """interrupt 值非 dict 时防御性透传。"""

    class FakeInterrupt:
        value = "plain text"

    events = _decode(process_updates({"__interrupt__": [FakeInterrupt()]}, "t1"))
    assert events[0][1]["plan"] == "plain text"


def test_updates_step_result_event():
    """节点 update 追加 observations → step_result 事件。"""
    updates = {
        "researcher": {
            "observations": ["已有观察", "新观察结果"],
            "current_step": "市场分析",
        }
    }
    events = _decode(process_updates(updates, "t1"))
    assert events == [
        (
            "step_result",
            {
                "thread_id": "t1",
                "agent": "researcher",
                "topic": "市场分析",
                "content": "新观察结果",
            },
        )
    ]


def test_updates_without_observations_emits_nothing():
    """普通节点 update（无 observations）不产出事件。"""
    updates = {"planner": {"current_plan": {"title": "T"}}}
    assert process_updates(updates, "t1") == []
