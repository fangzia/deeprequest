"""图构建：节点注册、边连接与编译。

整张图的全部拓扑在此集中声明，不使用节点内 ``Command(goto=...)`` 跳转：

```text
START → coordinator ──(背景调查开关)──→ background_investigator → planner
                │                                              ↑ │
                └──────────────(跳过背景调查)───────────────────┘ │
                                                  (解析失败且未超重试上限：自环重试)
planner ──(研究轮次上限/重试超限/背景足够)──→ reporter 或 __end__
       └──(默认)──→ human_feedback ──(edit_plan/invalid)──→ planner
                            │
                            └──(accepted)──→ research_team ⇄ researcher/analyst/coder
                                                 │
                                                 └──(全部完成)──→ planner
reporter → END
```
"""

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from deepquest.graph.nodes import (
    analyst_node,
    background_investigation_node,
    coder_node,
    coordinator_node,
    human_feedback_node,
    planner_node,
    reporter_node,
    research_team_node,
    researcher_node,
)
from deepquest.graph.routing import (
    continue_to_running_research_team,
    route_after_coordinator,
    route_after_feedback,
    route_after_planner,
)
from deepquest.graph.state import State

logger = logging.getLogger(__name__)


def _build_base_graph() -> StateGraph:
    """构建并返回包含所有节点与边的基础状态图。"""
    builder = StateGraph(State)

    # ── 节点注册 ──────────────────────────────────────────────
    builder.add_node("coordinator", coordinator_node)
    builder.add_node("background_investigator", background_investigation_node)
    builder.add_node("planner", planner_node)
    builder.add_node("human_feedback", human_feedback_node)
    builder.add_node("research_team", research_team_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("analyst", analyst_node)
    builder.add_node("coder", coder_node)
    builder.add_node("reporter", reporter_node)

    # ── 入口与规划阶段 ────────────────────────────────────────
    builder.add_edge(START, "coordinator")
    builder.add_conditional_edges(
        "coordinator",
        route_after_coordinator,
        ["background_investigator", "planner"],
    )
    builder.add_edge("background_investigator", "planner")
    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        ["planner", "human_feedback", "reporter", END],
    )

    # ── 计划评审（human-in-the-loop）──────────────────────────
    builder.add_conditional_edges(
        "human_feedback",
        route_after_feedback,
        ["planner", "research_team", "reporter", END],
    )

    # ── 研究团队循环 ──────────────────────────────────────────
    builder.add_conditional_edges(
        "research_team",
        continue_to_running_research_team,
        ["planner", "researcher", "analyst", "coder"],
    )
    builder.add_edge("researcher", "research_team")
    builder.add_edge("analyst", "research_team")
    builder.add_edge("coder", "research_team")

    # ── 汇报与终止 ────────────────────────────────────────────
    builder.add_edge("reporter", END)
    return builder


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """构建并编译研究图。

    Args:
        checkpointer: 检查点保存器（MemorySaver / AsyncPostgresSaver 等）。
            传入 None 则编译为无持久化图（仅适合单次执行）。

    Returns:
        编译后的可执行图。
    """
    builder = _build_base_graph()
    graph = builder.compile(checkpointer=checkpointer)
    logger.info("研究图构建完成（checkpointer=%s）", type(checkpointer).__name__)
    return graph
