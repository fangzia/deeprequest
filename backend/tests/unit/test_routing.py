"""条件路由函数的全分支单测（continue_to_running_research_team 及三个路由函数）。"""

from deepquest.graph.routing import (
    continue_to_running_research_team,
    route_after_coordinator,
    route_after_feedback,
    route_after_planner,
)
from deepquest.prompts.models import Plan, Step


def _make_plan(steps: list[Step], enough_context: bool = False) -> Plan:
    return Plan(
        has_enough_context=enough_context,
        thought="",
        title="测试计划",
        steps=steps,
    )


def _step(step_type: str, executed: bool = False, need_search: bool = False) -> Step:
    return Step(
        need_search=need_search,
        title=f"步骤-{step_type}",
        description="测试步骤",
        step_type=step_type,
        execution_res="已完成" if executed else None,
    )


# ── route_after_coordinator ────────────────────────────────────


def test_coordinator_background_enabled_routes_to_investigator():
    """开启背景调查开关时先进入 background_investigator。"""
    assert route_after_coordinator({"enable_background_investigation": True}) == (
        "background_investigator"
    )


def test_coordinator_background_disabled_routes_to_planner():
    """关闭背景调查开关时直达 planner。"""
    assert route_after_coordinator({"enable_background_investigation": False}) == "planner"


# ── route_after_planner ────────────────────────────────────────


def _planner_config(max_plan_iterations: int = 1) -> dict:
    return {"configurable": {"max_plan_iterations": max_plan_iterations}}


def test_planner_max_iterations_routes_to_reporter():
    """计划轮次已达上限时进入 reporter。"""
    state = {"plan_iterations": 1, "current_plan": _make_plan([_step("research")])}
    assert route_after_planner(state, _planner_config(1)) == "reporter"


def test_planner_parse_error_first_iteration_ends():
    """首轮解析失败且无既定轮次时终止图。"""
    assert route_after_planner({"plan_iterations": 0, "plan_error": "bad"}, _planner_config()) == (
        "__end__"
    )


def test_planner_parse_error_with_history_routes_to_reporter():
    """已有既定轮次时解析失败兜底进 reporter。"""
    state = {"plan_iterations": 1, "plan_error": "bad"}
    assert route_after_planner(state, _planner_config(2)) == "reporter"


def test_planner_enough_context_routes_to_reporter():
    """背景已充分（has_enough_context）时直达 reporter。"""
    state = {
        "plan_iterations": 0,
        "current_plan": _make_plan([], enough_context=True),
    }
    assert route_after_planner(state, _planner_config()) == "reporter"


def test_planner_default_routes_to_feedback():
    """常规产出计划后进入人工评审。"""
    state = {"plan_iterations": 0, "current_plan": _make_plan([_step("research")])}
    assert route_after_planner(state, _planner_config()) == "human_feedback"


# ── route_after_feedback ───────────────────────────────────────


def test_feedback_edit_plan_routes_to_planner():
    """修改计划反馈退回 planner。"""
    assert route_after_feedback({"feedback_decision": "edit_plan"}) == "planner"


def test_feedback_invalid_routes_to_planner():
    """无效反馈格式退回 planner。"""
    assert route_after_feedback({"feedback_decision": "invalid"}) == "planner"


def test_feedback_accepted_valid_plan_routes_to_research_team():
    """接受且计划有效时进入研究团队。"""
    state = {
        "feedback_decision": "accepted",
        "plan_iterations": 1,
        "current_plan": _make_plan([_step("research")]),
    }
    assert route_after_feedback(state) == "research_team"


def test_feedback_accepted_invalid_plan_routes_to_reporter():
    """接受但计划无效、已有既定轮次时兜底进 reporter（与 planner 口径一致：> 0）。"""
    state = {"feedback_decision": "accepted", "plan_iterations": 1, "current_plan": None}
    assert route_after_feedback(state) == "reporter"


def test_feedback_accepted_invalid_plan_without_iterations_ends():
    """防御分支：接受但计划无效且无任何既定轮次（plan_iterations=0）时终止图。"""
    state = {"feedback_decision": "accepted", "plan_iterations": 0, "current_plan": None}
    assert route_after_feedback(state) == "__end__"


# ── continue_to_running_research_team ──────────────────────────


def test_no_plan_returns_planner():
    """current_plan 缺失时应回到 planner。"""
    assert continue_to_running_research_team({"current_plan": None}) == "planner"


def test_plan_string_returns_planner():
    """current_plan 为字符串（防御分支）时应回到 planner。"""
    assert continue_to_running_research_team({"current_plan": "not-a-plan"}) == "planner"


def test_empty_steps_returns_planner():
    """计划无步骤时应回到 planner。"""
    plan = _make_plan([])
    assert continue_to_running_research_team({"current_plan": plan}) == "planner"


def test_all_steps_completed_returns_planner():
    """所有步骤都已执行时应回到 planner。"""
    plan = _make_plan([_step("research", executed=True), _step("analysis", executed=True)])
    assert continue_to_running_research_team({"current_plan": plan}) == "planner"


def test_first_incomplete_research_step_routes_to_researcher():
    """第一个未完成步骤为 research 时路由到 researcher（跳过已完成的 analysis）。"""
    plan = _make_plan([_step("analysis", executed=True), _step("research", need_search=True)])
    assert continue_to_running_research_team({"current_plan": plan}) == "researcher"


def test_first_incomplete_analysis_step_routes_to_analyst():
    """第一个未完成步骤为 analysis 时路由到 analyst。"""
    plan = _make_plan([_step("research", executed=True), _step("analysis")])
    assert continue_to_running_research_team({"current_plan": plan}) == "analyst"


def test_first_incomplete_processing_step_routes_to_coder():
    """第一个未完成步骤为 processing 时路由到 coder。"""
    plan = _make_plan([_step("processing")])
    assert continue_to_running_research_team({"current_plan": plan}) == "coder"


def test_unknown_step_type_falls_back_to_planner():
    """未知 step_type 时兜底回到 planner。"""
    plan = _make_plan([_step("research", executed=True)])
    # 直接构造异常类型的步骤
    plan.steps[0].step_type = "unknown"  # type: ignore[assignment]
    assert continue_to_running_research_team({"current_plan": plan}) == "planner"
