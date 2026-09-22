"""图中断与恢复单测：MemorySaver + FakeChatModel 全流程跑图（零 API 成本）。

覆盖两条路径：
- ``auto_accepted_plan=true``：planner 后直达研究，最终产出报告与引用来源；
- ``auto_accepted_plan=false``：planner 后产生 interrupt（计划评审），
  ``Command(resume="[ACCEPTED]")`` 可恢复执行直至产出报告。
"""

import json

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from deepquest.graph.builder import build_graph
from deepquest.prompts.models import Plan

# 测试用研究计划：单个 research 步骤
PLAN_DICT = {
    "locale": "zh-CN",
    "has_enough_context": False,
    "thought": "需要收集信息",
    "title": "测试研究",
    "steps": [
        {
            "need_search": True,
            "title": "收集资料",
            "description": "收集相关资料",
            "step_type": "research",
        }
    ],
}


class SequenceFakeChatModel(BaseChatModel):
    """按调用顺序依次吐出预设消息的假模型。

    消息序列对应图的 LLM 调用时序：
    1. coordinator → handoff_to_planner 工具调用
    2. planner → Plan 结构化输出（以 tool_calls 形式）
    3. researcher 代理 → 最终文本（含引用来源）
    4. reporter → 最终报告
    """

    messages: list  # noqa: RUF012
    cursor: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake-sequence"

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self

    def _generate(self, messages, stop=None, run_id=None, **kwargs) -> ChatResult:  # noqa: ARG002
        if self.cursor >= len(self.messages):
            # 序列耗尽：返回空消息，避免测试卡死
            msg = AIMessage(content="")
        else:
            msg = self.messages[self.cursor]
            self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _default_message_sequence() -> list[BaseMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "handoff_to_planner",
                    "args": {"research_topic": "测试主题", "locale": "zh-CN"},
                    "id": "call_coordinator",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "Plan", "args": PLAN_DICT, "id": "call_planner"}],
        ),
        AIMessage(
            content=(
                "研究发现：相关资料已收集完毕。\n\n参考：\n- [示例来源](https://example.com/page)"
            ),
        ),
        AIMessage(content="# 测试研究报告\n\n结论摘要 [1]。"),
    ]


@tool
def _fake_web_search(query: str) -> str:
    """测试用 web_search 替身：返回固定 JSON 结果，不发真实网络请求。"""
    return json.dumps(
        [{"title": "背景调查结果", "url": "https://example.com", "content": "背景内容"}],
        ensure_ascii=False,
    )


@pytest.fixture
def fake_model(monkeypatch) -> SequenceFakeChatModel:
    """构造假模型并注入到图的全部 LLM 获取点（节点 + 代理工厂）。"""
    model = SequenceFakeChatModel(messages=_default_message_sequence())
    monkeypatch.setattr("deepquest.graph.nodes.get_llm", lambda *a, **k: model)
    monkeypatch.setattr("deepquest.agents.factory.get_llm", lambda *a, **k: model)
    # 搜索工具替换为假工具：背景调查与 researcher 均无网络请求
    monkeypatch.setattr(
        "deepquest.graph.nodes.get_web_search_tool", lambda *a, **k: _fake_web_search
    )
    return model


def _make_input(auto_accepted: bool) -> dict:
    return {
        "messages": [{"role": "user", "content": "测试主题"}],
        "research_topic": "测试主题",
        "locale": "zh-CN",
        "plan_iterations": 0,
        "final_report": "",
        "auto_accepted_plan": auto_accepted,
        "enable_background_investigation": True,
    }


def _config(thread_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
            "max_plan_iterations": 1,
            "max_step_num": 3,
        },
        "recursion_limit": 150,
    }


async def _collect_events(graph, workflow_input, config) -> list:
    """收集 (namespace, mode, payload) 三元组事件。"""
    events = []
    async for ns, mode, payload in graph.astream(
        workflow_input,
        config=config,
        stream_mode=["messages", "updates"],
        subgraphs=True,
    ):
        events.append((ns, mode, payload))
    return events


async def test_auto_accepted_plan_runs_to_report(fake_model):
    """auto_accepted_plan=true：跳过人工确认直达研究，产出报告与引用来源。"""
    graph = build_graph(checkpointer=MemorySaver())
    config = _config("t-auto")

    events = await _collect_events(graph, _make_input(auto_accepted=True), config)

    # 无任何 interrupt 事件
    interrupt_events = [
        e for e in events if e[1] == "updates" and "__interrupt__" in e[2]
    ]
    assert interrupt_events == []

    # 步骤结果事件存在（researcher 完成一步）
    step_events = [
        e[2] for e in events if e[1] == "updates" and isinstance(e[2], dict)
        and "observations" in (e[2].get("researcher") or {})
    ]
    assert step_events, "应产生 researcher 的 step 更新"

    # 终态校验
    snapshot = await graph.aget_state(config)
    assert snapshot.values["final_report"] == "# 测试研究报告\n\n结论摘要 [1]。"
    assert snapshot.values["current_step"] == "收集资料"
    assert len(snapshot.values["observations"]) == 1
    # 引用来源聚合：researcher 结果中的 "- [示例来源](https://example.com/page)" 被解析
    sources = snapshot.values["sources"]
    assert len(sources) == 1
    assert sources[0].url == "https://example.com/page"
    assert sources[0].title == "示例来源"
    # 计划轮次推进
    assert snapshot.values["plan_iterations"] == 1


async def test_interrupt_and_resume_with_accepted(fake_model):
    """auto_accepted_plan=false：产生计划评审 interrupt，Command(resume) 可恢复。"""
    graph = build_graph(checkpointer=MemorySaver())
    config = _config("t-interrupt")

    # 第一轮：应停在 human_feedback 的 interrupt
    events = await _collect_events(graph, _make_input(auto_accepted=False), config)

    interrupts = [
        e[2]["__interrupt__"][0]
        for e in events
        if e[1] == "updates" and isinstance(e[2], dict) and "__interrupt__" in e[2]
    ]
    assert len(interrupts) == 1, "应产生且仅产生一次 interrupt"
    interrupt_value = interrupts[0].value
    assert interrupt_value["type"] == "plan_review"
    assert Plan.model_validate(json.loads(interrupt_value["plan"])).title == "测试研究"

    # 图状态：停在 human_feedback 节点，final_report 为空
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ("human_feedback",)
    assert snapshot.values["final_report"] == ""

    # 第二轮：以 [ACCEPTED] 恢复，流程直达报告
    resume_events = await _collect_events(graph, Command(resume="[ACCEPTED]"), config)
    # 恢复后不应再有 interrupt
    assert not [
        e for e in resume_events if e[1] == "updates" and "__interrupt__" in e[2]
    ]

    snapshot = await graph.aget_state(config)
    assert snapshot.values["final_report"] == "# 测试研究报告\n\n结论摘要 [1]。"
    assert len(snapshot.values["sources"]) == 1
    assert snapshot.values["plan_iterations"] == 1


async def test_interrupt_edit_plan_feedback_returns_to_planner(fake_model):
    """[EDIT_PLAN] 反馈：human_feedback 把流程退回 planner 重新规划。"""
    graph = build_graph(checkpointer=MemorySaver())
    config = _config("t-edit")

    # 第一轮：停在 interrupt
    await _collect_events(graph, _make_input(auto_accepted=False), config)
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ("human_feedback",)

    # 第二轮：以 [EDIT_PLAN] 意见恢复 → planner 重新规划（再次产出计划）
    # 重置模型序列：让下一处 LLM 调用（planner）拿到新的 Plan 结构化输出，
    # 计划产出后再次停在 human_feedback 的 interrupt
    fake_model.messages = _default_message_sequence()
    fake_model.cursor = 1  # 跳过 coordinator 的 handoff 消息

    await _collect_events(graph, Command(resume="[EDIT_PLAN] 请缩小研究范围"), config)

    # planner 重新规划后再次 interrupt（auto_accepted_plan 仍为 false）
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ("human_feedback",)
    # feedback 消息已写入会话
    assert any(
        getattr(m, "name", "") == "feedback" for m in snapshot.values["messages"]
    )
