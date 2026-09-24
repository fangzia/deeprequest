"""条件路由函数集合：全部路由决策集中于此，供 builder.py 的边声明使用。

节点只负责状态更新（返回 dict），"下一步去哪" 统一由这些纯函数根据
图状态（与 config）决定，使整张图的拓扑在 builder.py 中一目了然。

路由信号（节点写入 state，路由函数读取）：
- ``plan_error``：planner 解析失败的信号（成功时置 None）；
- ``plan_retries``：planner 解析失败的累计重试次数（成功时清零）；
- ``feedback_decision``：human_feedback 对用户反馈的判定结果
  （accepted / edit_plan / invalid）。
"""

from typing import Literal

from langchain_core.runnables import RunnableConfig

from deepquest.graph.state import State
from deepquest.prompts.models import Plan, StepType


def route_after_coordinator(state: State) -> Literal["background_investigator", "planner"]:
    """coordinator 之后：按开关决定是否先做背景调查。"""
    if state.get("enable_background_investigation", False):
        return "background_investigator"
    return "planner"


def route_after_planner(
    state: State, config: RunnableConfig
) -> Literal["planner", "human_feedback", "reporter", "__end__"]:
    """planner 之后：带反馈重试、进入计划评审、直接产出报告，或终止。

    判定优先级：
    1. 研究轮次已达上限 → reporter（planner 已提前跳过 LLM 调用）；
    2. 计划解析失败 → 未超重试上限则回 planner 自环重试（planner 会把
       ``plan_error`` 回注到 prompt 让模型修正）；超限则已有既定研究轮次时
       reporter 兜底产出，否则终止；
    3. planner 判断背景已充分（has_enough_context）→ reporter；
    4. 其余 → human_feedback 计划评审。
    """
    research_rounds = state.get("research_rounds") or 0
    plan_retries = state.get("plan_retries") or 0
    configurable = (config or {}).get("configurable", {})
    max_research_rounds = configurable.get("max_research_rounds", 1)
    max_plan_retries = configurable.get("max_plan_retries", 1)

    if research_rounds >= max_research_rounds:
        return "reporter"

    if state.get("plan_error"):
        # plan_retries 在每次失败时已由 planner +1；未超上限则允许再试一次
        if plan_retries <= max_plan_retries:
            return "planner"
        return "reporter" if research_rounds > 0 else "__end__"

    plan = state.get("current_plan")
    if isinstance(plan, Plan) and plan.has_enough_context:
        return "reporter"

    return "human_feedback"


def route_after_feedback(
    state: State,
) -> Literal["planner", "research_team", "reporter", "__end__"]:
    """human_feedback 之后：按反馈判定结果分发。

    - edit_plan / invalid → 退回 planner 重新规划；
    - accepted 且计划有效 → research_team 执行研究；
    - accepted 但计划无效 → 已有既定研究轮次则 reporter 兜底，否则终止
      （与 route_after_planner 的 plan_error 超限分支口径一致：> 0）。
    """
    decision = state.get("feedback_decision")

    if decision in ("edit_plan", "invalid"):
        return "planner"

    # decision == "accepted"（或防御性缺省）：校验计划有效性
    plan = state.get("current_plan")
    research_rounds = state.get("research_rounds") or 0
    if not isinstance(plan, Plan) or not plan.steps:
        return "reporter" if research_rounds > 0 else "__end__"
    return "research_team"


def continue_to_running_research_team(
    state: State,
) -> Literal["planner", "researcher", "analyst", "coder"]:
    """根据当前计划中第一个未完成步骤的类型，分发到对应代理节点。

    Args:
        state: 当前图状态。

    Returns:
        下一节点名：planner / researcher / analyst / coder。
    """
    current_plan = state.get("current_plan")
    if isinstance(current_plan, str):
        # 防御：计划意外为字符串时不分发任何代理，交回 planner
        return "planner"
    if not isinstance(current_plan, Plan) or not current_plan.steps:
        return "planner"

    if all(step.execution_res for step in current_plan.steps):
        # 所有步骤已完成：回到 planner（由其决定补充计划或进入 reporter）
        return "planner"

    # 找到第一个未完成步骤
    incomplete_step = next((s for s in current_plan.steps if not s.execution_res), None)
    if incomplete_step is None:
        return "planner"

    if incomplete_step.step_type == StepType.RESEARCH:
        return "researcher"
    if incomplete_step.step_type == StepType.ANALYSIS:
        return "analyst"
    if incomplete_step.step_type == StepType.PROCESSING:
        return "coder"
    return "planner"
