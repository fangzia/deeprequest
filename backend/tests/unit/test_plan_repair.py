"""validate_and_fix_plan 计划修复逻辑单测（从参考实现搬运并适配）。"""

from deepquest.graph.nodes import validate_and_fix_plan


def test_non_dict_plan_passthrough():
    """非 dict 输入直接原样返回。"""
    assert validate_and_fix_plan("not-a-dict") == "not-a-dict"
    assert validate_and_fix_plan(None) is None
    assert validate_and_fix_plan([1, 2]) == [1, 2]


def test_repairs_missing_step_type_research():
    """缺失 step_type 时依据 need_search=true 推断为 research。"""
    plan = {
        "title": "T",
        "steps": [{"need_search": True, "title": "s1", "description": "d"}],
    }
    fixed = validate_and_fix_plan(plan)
    assert fixed["steps"][0]["step_type"] == "research"


def test_repairs_missing_step_type_analysis():
    """缺失 step_type 且 need_search=false 时推断为 analysis。"""
    plan = {
        "title": "T",
        "steps": [{"need_search": False, "title": "s1", "description": "d"}],
    }
    fixed = validate_and_fix_plan(plan)
    assert fixed["steps"][0]["step_type"] == "analysis"


def test_keeps_existing_step_type():
    """已有 step_type 时不改动。"""
    plan = {
        "title": "T",
        "steps": [
            {"need_search": False, "title": "s1", "description": "d", "step_type": "processing"}
        ],
    }
    fixed = validate_and_fix_plan(plan)
    assert fixed["steps"][0]["step_type"] == "processing"


def test_enforce_web_search_enables_research_step():
    """enforce_web_search 且无搜索步骤时，强制第一个 research 步骤启用搜索。"""
    plan = {
        "title": "T",
        "steps": [
            {"need_search": False, "title": "s1", "description": "d", "step_type": "research"},
            {"need_search": False, "title": "s2", "description": "d", "step_type": "analysis"},
        ],
    }
    fixed = validate_and_fix_plan(plan, enforce_web_search=True)
    assert fixed["steps"][0]["need_search"] is True


def test_enforce_web_search_converts_first_step_when_no_research():
    """enforce_web_search 且无 research 步骤时，将首步转为 research 并启用搜索。"""
    plan = {
        "title": "T",
        "steps": [
            {"need_search": False, "title": "s1", "description": "d", "step_type": "analysis"},
        ],
    }
    fixed = validate_and_fix_plan(plan, enforce_web_search=True)
    assert fixed["steps"][0]["step_type"] == "research"
    assert fixed["steps"][0]["need_search"] is True


def test_enforce_web_search_adds_default_step_when_empty():
    """enforce_web_search 且计划无步骤时，追加默认研究步骤。"""
    plan = {"title": "T", "steps": []}
    fixed = validate_and_fix_plan(plan, enforce_web_search=True)
    assert len(fixed["steps"]) == 1
    assert fixed["steps"][0]["step_type"] == "research"
    assert fixed["steps"][0]["need_search"] is True


def test_enforce_web_search_noop_when_search_exists():
    """已有搜索步骤时 enforce_web_search 不做额外改动。"""
    plan = {
        "title": "T",
        "steps": [
            {"need_search": True, "title": "s1", "description": "d", "step_type": "research"},
        ],
    }
    fixed = validate_and_fix_plan(plan, enforce_web_search=True)
    assert fixed["steps"][0]["need_search"] is True
    assert len(fixed["steps"]) == 1


def test_no_enforce_keeps_plan_untouched():
    """不启用 enforce_web_search 时不做强制修改。"""
    plan = {
        "title": "T",
        "steps": [
            {"need_search": False, "title": "s1", "description": "d", "step_type": "research"},
        ],
    }
    fixed = validate_and_fix_plan(plan, enforce_web_search=False)
    assert fixed["steps"][0]["need_search"] is False
