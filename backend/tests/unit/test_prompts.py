"""prompt 模板渲染单测：locale 归一化与缺失模板的兜底回退。"""

import pytest

from deepquest.prompts import get_prompt_template


def test_known_agent_renders_with_variables():
    """已知角色模板渲染成功，且 jinja 变量被正确替换。"""
    prompt = get_prompt_template("planner", locale="zh-CN", max_step_num=3)
    assert "3" in prompt  # max_step_num 已渲染
    assert "{{" not in prompt  # 无残留未渲染变量


def test_locale_normalized_to_underscore():
    """zh-CN 与 zh_CN 归一化后命中同一模板。"""
    assert get_prompt_template("coordinator", locale="zh-CN") == get_prompt_template(
        "coordinator", locale="zh_CN"
    )


def test_missing_locale_falls_back_to_zh_cn():
    """缺失该 locale 的模板时兜底到中文基础模板，而非抛 ValueError。"""
    prompt = get_prompt_template("planner", locale="en-US")
    # 模板文本为中文兜底版，但 {{ locale }} 变量按请求渲染，指示英文输出
    assert "en-US" in prompt
    assert "深度研究者" in prompt
    # 任意未知 locale（含模型输出的异常字符串）同样兜底成功
    assert get_prompt_template("reporter", locale="fr-FR")


def test_unknown_agent_raises():
    """未知角色名仍应抛出 ValueError。"""
    with pytest.raises(ValueError, match="未找到角色"):
        get_prompt_template("nonexistent_agent", locale="zh-CN")
