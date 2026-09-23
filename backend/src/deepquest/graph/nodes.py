"""研究图节点实现。

8 个节点：coordinator / background_investigation / planner / human_feedback /
researcher / analyst / coder / reporter（外加空的 research_team 汇聚节点）。

节点只负责**状态更新**（返回 dict），全部路由决策集中在 routing.py 的
纯函数中、由 builder.py 的边声明统一表达。节点与路由之间的信号约定：
- planner 解析失败 → 写入 ``plan_error``（成功时置 None）；
- human_feedback 判定用户反馈 → 写入 ``feedback_decision``
  （accepted / edit_plan / invalid）。

相比参考实现（puffin-chat node.py）的主要简化与升级：
- 删除 DB 写入、clarification、RAG 工具、ContextManager 压缩、web_search 强制校验；
- planner 优先 ``llm.with_structured_output(Plan)``，失败时回退 json-repair 文本解析；
- researcher 完成后解析结果中的 "- [标题](URL)" 引用，聚合去重追加到 state["sources"]；
- reporter 注入编号来源列表，要求正文使用 [n] 编号引用。
"""

import json
import logging
import re
from typing import Annotated

import json_repair
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from langgraph.types import interrupt

from deepquest.agents.factory import create_agent
from deepquest.graph.state import State
from deepquest.llm.provider import get_llm
from deepquest.prompts import apply_prompt_template
from deepquest.prompts.models import Plan, Source
from deepquest.tools import crawl_tool, get_web_search_tool, python_repl_tool
from deepquest.tools.mcp import load_mcp_tools

logger = logging.getLogger(__name__)

# 代理单步执行的递归上限（内部 ReAct 循环轮数）
_AGENT_RECURSION_LIMIT = 25

# 引用来源格式：- [标题](URL) 或 [标题](URL)
_CITATION_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")


@tool
def handoff_to_planner(
    research_topic: Annotated[str, "要转交给规划器的研究主题。"],
    locale: Annotated[str, "用户语言区域，如 zh-CN。"],
):
    """将研究任务转交给规划器（planner）制定研究计划。"""
    # 该工具不返回任何内容：仅作为 LLM 发出"转交给规划器"信号的方式
    return


def repair_json_output(content: str) -> str:
    """修复并规范化模型输出的 JSON 文本。

    处理 JSON 闭合括号后有多余 token、结构不完整等情况。
    """
    content = content.strip()
    if not content:
        return content
    try:
        repaired = json_repair.loads(content)
        if isinstance(repaired, dict | list):
            return json.dumps(repaired, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        logger.debug("JSON 修复失败，返回原始内容")
    return content


def validate_and_fix_plan(plan: dict, enforce_web_search: bool = False) -> dict:
    """校验并修复计划，确保其满足执行要求。

    Args:
        plan: 待校验的计划字典。
        enforce_web_search: 为 True 时确保至少一个步骤 need_search=true。

    Returns:
        校验/修复后的计划字典。
    """
    if not isinstance(plan, dict):
        return plan

    steps = plan.get("steps", [])

    # 第一部分：修复缺失的 step_type 字段
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        if "step_type" not in step or not step.get("step_type"):
            # 依据 need_search 推断；非搜索步骤默认为 analysis（并非所有处理都需要代码）
            inferred_type = "research" if step.get("need_search", False) else "analysis"
            step["step_type"] = inferred_type
            logger.info(
                "已修复步骤 %d（%s）缺失的 step_type：依据 need_search=%s 推断为 '%s'",
                idx, step.get("title", "未命名"), step.get("need_search", False), inferred_type,
            )

    # 第二部分：强制网络搜索要求
    if enforce_web_search:
        has_search_step = any(
            step.get("need_search", False) for step in steps if isinstance(step, dict)
        )

        if not has_search_step and steps:
            for idx, step in enumerate(steps):
                if isinstance(step, dict) and step.get("step_type") == "research":
                    step["need_search"] = True
                    logger.info("已强制步骤 %d（research）启用网络搜索", idx)
                    break
            else:
                # 兜底：无 research 步骤时，将首步转为 research 步骤
                if isinstance(steps[0], dict):
                    steps[0]["step_type"] = "research"
                    steps[0]["need_search"] = True
                    logger.info("已将首步转为 research 并启用网络搜索")
        elif not has_search_step and not steps:
            logger.warning("计划没有任何步骤，追加默认研究步骤")
            plan["steps"] = [
                {
                    "need_search": True,
                    "title": "初始研究",
                    "description": "收集关于研究主题的基础信息",
                    "step_type": "research",
                }
            ]

    return plan


def _extract_sources(text: str, existing_urls: set[str]) -> list[Source]:
    """从文本中解析 "- [标题](URL)" 形式的引用，返回未收录过的新来源。"""
    sources: list[Source] = []
    for match in _CITATION_RE.finditer(text):
        title, url = match.group(1).strip(), match.group(2).strip()
        if url in existing_urls:
            continue
        existing_urls.add(url)
        sources.append(Source(url=url, title=title, snippet=""))
    return sources


def _parse_plan_or_none(raw: str) -> Plan | None:
    """将模型输出的 JSON 文本修复并解析为 Plan；失败返回 None。"""
    try:
        plan_dict = json.loads(repair_json_output(raw))
        if not isinstance(plan_dict, dict):
            return None
        plan_dict = validate_and_fix_plan(plan_dict)
        return Plan.model_validate(plan_dict)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("计划解析失败：%s", e)
        return None


def coordinator_node(state: State, config: RunnableConfig) -> dict:  # noqa: ARG001
    """协调器节点：接收用户请求，解析研究主题与语言。"""
    logger.info("coordinator 节点运行中")
    locale = state.get("locale", "zh-CN")
    messages = apply_prompt_template("coordinator", state, locale=locale)

    response = get_llm().bind_tools([handoff_to_planner]).invoke(messages)

    research_topic = state.get("research_topic", "")
    new_locale = locale
    if response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call.get("name") == "handoff_to_planner":
                logger.info("coordinator 转交给 planner")
                args = tool_call.get("args", {})
                if args.get("research_topic"):
                    research_topic = args["research_topic"]
                if args.get("locale"):
                    new_locale = args["locale"]
                break
    else:
        # 模型未调用工具时兜底转交，保证研究流程不中断
        logger.warning("coordinator 未调用工具，兜底转交给 planner")

    update: dict = {"research_topic": research_topic, "locale": new_locale}
    if response.content:
        update["messages"] = [AIMessage(content=str(response.content), name="coordinator")]
    return update


def background_investigation_node(state: State, config: RunnableConfig) -> dict:
    """背景调查节点：在规划前对研究主题做一次快速搜索，为 planner 提供背景。"""
    logger.info("背景调查节点运行中")
    configurable = (config or {}).get("configurable", {})
    max_search_results = configurable.get("max_search_results", 3)

    query = state.get("research_topic", "")
    searched = get_web_search_tool(max_search_results).invoke({"query": query})

    results_text = ""
    if isinstance(searched, str):
        try:
            parsed = json.loads(searched)
            if isinstance(parsed, list):
                results_text = "\n\n".join(
                    f"## {elem.get('title', '无标题')}\n\n{elem.get('content', '无内容')}"
                    for elem in parsed
                    if isinstance(elem, dict)
                )
            elif isinstance(parsed, dict) and "error" in parsed:
                logger.error("背景调查搜索出错：%s", parsed["error"])
        except json.JSONDecodeError:
            # 占位工具的错误提示等非 JSON 内容，原样透传给 planner
            logger.warning("背景调查返回非 JSON 内容，原样透传")
            results_text = searched

    if not results_text:
        results_text = "（本次背景调查未获取到有效结果）"

    return {"background_investigation_results": results_text}


def planner_node(state: State, config: RunnableConfig) -> dict:
    """规划器节点：生成完整研究计划。

    优先使用 ``llm.with_structured_output(Plan)`` 结构化输出；
    失败（返回 None 或抛异常）时回退到"普通调用 + json-repair 文本解析"路径。

    路由信号：成功写入 ``current_plan`` 并清空 ``plan_error``；
    解析失败写入 ``plan_error``，由 ``route_after_planner`` 决定去向。
    轮次已达上限时提前返回（不调用 LLM），同样交由路由函数转 reporter。
    """
    logger.info("planner 生成研究计划，locale=%s", state.get("locale", "zh-CN"))
    configurable = (config or {}).get("configurable", {})
    max_plan_iterations = configurable.get("max_plan_iterations", 1)
    max_step_num = configurable.get("max_step_num", 3)
    plan_iterations = state.get("plan_iterations") or 0
    locale = state.get("locale", "zh-CN")

    # 计划轮次已达上限：跳过 LLM 调用，路由函数会直接转 reporter
    if plan_iterations >= max_plan_iterations:
        logger.info("计划轮次已达上限（%d），进入 reporter", max_plan_iterations)
        return {}

    messages = apply_prompt_template(
        "planner", state, locale=locale, max_step_num=max_step_num
    )
    if state.get("enable_background_investigation") and state.get(
        "background_investigation_results"
    ):
        messages.append(
            {
                "role": "user",
                "content": (
                    "用户查询的背景调查结果：\n"
                    + state["background_investigation_results"]
                    + "\n"
                ),
            },
        )

    llm = get_llm()
    curr_plan: Plan | None = None
    full_response = ""

    # 路径一：结构化输出（优先）
    try:
        structured_llm = llm.with_structured_output(Plan)
        result = structured_llm.invoke(messages)
        if isinstance(result, Plan):
            curr_plan = result
    except Exception as e:  # noqa: BLE001
        logger.warning("结构化输出计划失败，回退文本解析路径：%s", e)

    # 路径二：普通调用 + json-repair 解析（兜底）
    if curr_plan is None:
        logger.info("planner 使用文本解析路径")
        response = llm.invoke(messages)
        full_response = str(response.content or "")
        curr_plan = _parse_plan_or_none(full_response)

    if curr_plan is None:
        logger.warning("planner 输出无法解析为有效计划")
        return {"plan_error": "planner 输出无法解析为有效计划"}

    plan_text = full_response or curr_plan.model_dump_json()
    logger.info("planner 计划生成成功：%s（%d 个步骤）", curr_plan.title, len(curr_plan.steps))

    return {
        "messages": [AIMessage(content=plan_text, name="planner")],
        "current_plan": curr_plan,
        "plan_error": None,
    }


def human_feedback_node(state: State, config: RunnableConfig) -> dict:  # noqa: ARG001
    """人工反馈节点：human-in-the-loop 计划确认。

    ``auto_accepted_plan=false`` 时通过 ``interrupt()`` 暂停图执行，
    等待前端通过 ``Command(resume=...)`` 传入 "[ACCEPTED]" 或 "[EDIT_PLAN] ..."。

    节点只写入 ``feedback_decision`` 等状态更新，去向由
    ``route_after_feedback`` 决定。
    """
    current_plan = state.get("current_plan")
    auto_accepted_plan = state.get("auto_accepted_plan", False)

    if not auto_accepted_plan:
        # interrupt 会暂停图执行并将括号内的值作为中断信息返回；
        # 图恢复运行时，代码从下一行继续，interrupt 的返回值即 Command(resume=...) 传入的值
        plan_text = (
            current_plan.model_dump_json()
            if isinstance(current_plan, Plan)
            else str(current_plan or "")
        )
        feedback = interrupt({"type": "plan_review", "plan": plan_text})

        if not feedback:
            logger.warning("收到空的反馈（%r），返回 planner 重新规划", feedback)
            return {"feedback_decision": "invalid"}

        feedback_normalized = str(feedback).strip().upper()
        if feedback_normalized.startswith("[EDIT_PLAN]"):
            logger.info("用户请求修改计划：%s", feedback)
            return {
                "feedback_decision": "edit_plan",
                "messages": [HumanMessage(content=str(feedback), name="feedback")],
            }
        if not feedback_normalized.startswith("[ACCEPTED]"):
            logger.warning(
                "不支持的反馈格式（%r），请使用 '[ACCEPTED]' 或 '[EDIT_PLAN]'", feedback
            )
            return {"feedback_decision": "invalid"}
        logger.info("用户已接受计划")

    # 计划被接受（或自动接受）：解析并校验计划
    plan_iterations = (state.get("plan_iterations") or 0) + 1

    if isinstance(current_plan, str):
        current_plan = _parse_plan_or_none(current_plan)

    update: dict = {
        "plan_iterations": plan_iterations,
        "feedback_decision": "accepted",
    }
    if isinstance(current_plan, Plan) and current_plan.steps:
        update["current_plan"] = current_plan
        if current_plan.locale:
            update["locale"] = current_plan.locale
    else:
        logger.warning("计划无效或没有步骤")
    return update


async def _execute_agent_step(
    state: State,
    config: RunnableConfig,  # noqa: ARG001
    agent_name: str,
    tools: list,
) -> dict:
    """用指定代理执行当前步骤（第一个未执行步骤），并回写结果与来源。"""
    current_plan = state["current_plan"]
    if isinstance(current_plan, str):
        current_plan = _parse_plan_or_none(current_plan)
    if not isinstance(current_plan, Plan):
        logger.warning("当前计划无效，返回 research_team")
        return {}

    plan_title = current_plan.title
    observations = state.get("observations", [])

    # 找到第一个未执行的步骤
    current_step = None
    completed_steps = []
    for step in current_plan.steps:
        if not step.execution_res:
            current_step = step
            break
        completed_steps.append(step)

    if current_step is None:
        logger.warning("没有找到未执行的步骤")
        return {}

    logger.info("执行步骤「%s」，代理：%s", current_step.title, agent_name)

    # 组织已完成步骤信息
    completed_steps_info = ""
    if completed_steps:
        completed_steps_info = "# 已完成的研究步骤\n\n"
        for i, step in enumerate(completed_steps):
            completed_steps_info += (
                f"## 已完成步骤 {i + 1}：{step.title}\n\n"
                f"<finding>\n{step.execution_res}\n</finding>\n\n"
            )

    locale = state.get("locale", "zh-CN")
    agent_input = {
        "messages": [
            HumanMessage(
                content=(
                    f"# 研究主题\n\n{plan_title}\n\n{completed_steps_info}"
                    f"# 当前步骤\n\n## 标题\n\n{current_step.title}\n\n"
                    f"## 描述\n\n{current_step.description}\n\n## 语言\n\n{locale}"
                )
            )
        ]
    }

    # 研究员附加引用格式要求：来源以 "- [标题](URL)" 列出，供 sources 聚合解析
    if agent_name == "researcher":
        agent_input["messages"].append(
            HumanMessage(
                content=(
                    "重要：不要在正文中使用内联引用。请在结果末尾的「参考」部分，"
                    "用如下链接引用格式列出所有使用的来源，每条一行：\n"
                    "- [来源标题](URL)"
                ),
                name="system",
            )
        )

    agent = create_agent(agent_name, tools, locale=locale)

    result_state = None
    try:
        async for chunk in agent.astream(
            input=agent_input,
            config={"recursion_limit": _AGENT_RECURSION_LIMIT},
            stream_mode="values",
        ):
            # 每个 chunk 都是最新的完整 state，持续覆盖保存
            result_state = chunk
    except GraphRecursionError:
        logger.warning(
            "代理 %s 执行步骤「%s」时达到递归上限，提取部分结果", agent_name, current_step.title
        )
        partial_content = _extract_partial_result(result_state, current_step.title)
        current_step.execution_res = partial_content
        return {
            "messages": result_state.get("messages", [])
            if result_state
            else [HumanMessage(content=partial_content, name=agent_name)],
            "observations": observations + [partial_content],
            "current_step": current_step.title,
            "current_plan": current_plan,
        }
    except Exception as e:  # noqa: BLE001
        logger.exception("代理 %s 执行步骤「%s」出错", agent_name, current_step.title)
        detailed_error = (
            f"[ERROR] {agent_name} 代理执行错误\n\n步骤：{current_step.title}\n\n错误详情：{e}"
        )
        current_step.execution_res = detailed_error
        return {
            "messages": [HumanMessage(content=detailed_error, name=agent_name)],
            "observations": observations + [detailed_error],
            "current_step": current_step.title,
            "current_plan": current_plan,
        }

    if result_state is None or not result_state.get("messages"):
        logger.warning("代理 %s 未返回任何消息", agent_name)
        current_step.execution_res = "（代理未返回结果）"
        return {
            "observations": observations + ["（代理未返回结果）"],
            "current_step": current_step.title,
            "current_plan": current_plan,
        }

    response_content = str(result_state["messages"][-1].content)
    current_step.execution_res = response_content
    logger.info("步骤「%s」由 %s 执行完成", current_step.title, agent_name)

    update: dict = {
        "messages": result_state.get("messages", []),
        "observations": observations + [response_content],
        "current_step": current_step.title,
        "current_plan": current_plan,
    }

    # 研究员：解析本步结果中的引用来源，聚合去重追加到 state["sources"]
    if agent_name == "researcher":
        existing_urls = {s.url for s in state.get("sources", [])}
        new_sources = _extract_sources(response_content, existing_urls)
        if new_sources:
            update["sources"] = state.get("sources", []) + new_sources
            logger.info("本步骤新增 %d 个引用来源", len(new_sources))

    return update


def _extract_partial_result(result_state: dict | None, step_title: str) -> str:
    """递归超限后，从已流式收集的 state 中提取部分结果。"""
    if result_state is not None:
        collected_messages = result_state.get("messages", [])
        # 第一优先级：最后一条有内容的 AIMessage
        last_ai = next(
            (m for m in reversed(collected_messages) if isinstance(m, AIMessage) and m.content),
            None,
        )
        if last_ai is not None:
            return str(last_ai.content)
        # 第二优先级：拼接所有 ToolMessage 内容
        tool_contents = [
            f"[工具: {m.name}]\n{m.content}"
            for m in collected_messages
            if isinstance(m, ToolMessage) and m.content
        ]
        if tool_contents:
            return "\n\n---\n\n".join(tool_contents)
    # 第三优先级：无任何有效内容
    return (
        f"[研究说明] 由于执行轮次达到上限，步骤「{step_title}」未能完整完成，"
        "本步骤无法提取到有效研究结果，请参考其他步骤结果进行综合分析。"
    )


async def researcher_node(state: State, config: RunnableConfig) -> dict:
    """研究员节点：内置搜索/抓取工具，外加可选的 MCP 工具收集信息。"""
    logger.info("researcher 节点运行中")
    configurable = (config or {}).get("configurable", {})
    max_search_results = configurable.get("max_search_results", 3)
    tools = [get_web_search_tool(max_search_results), crawl_tool]
    # MCP 工具（可选）：未配置或加载失败时返回空列表，不影响内置工具
    tools.extend(await load_mcp_tools())
    return await _execute_agent_step(state, config, "researcher", tools)


async def analyst_node(state: State, config: RunnableConfig) -> dict:
    """分析师节点：纯 LLM 推理，交叉验证与综合分析。"""
    logger.info("analyst 节点运行中")
    return await _execute_agent_step(state, config, "analyst", [])


async def coder_node(state: State, config: RunnableConfig) -> dict:
    """编码节点：使用 Python REPL 进行计算与数据处理。"""
    logger.info("coder 节点运行中")
    return await _execute_agent_step(state, config, "coder", [python_repl_tool])


def research_team_node(state: State) -> None:  # noqa: ARG001
    """研究团队汇聚节点（空节点）：具体路由在 conditional_edges 中判断。"""
    logger.info("研究团队协作中")


def reporter_node(state: State, config: RunnableConfig) -> dict:  # noqa: ARG001
    """记者节点：汇总观察结果与编号来源列表，产出带 [n] 引用的最终报告。"""
    logger.info("reporter 撰写最终报告")
    current_plan = state.get("current_plan")
    locale = state.get("locale", "zh-CN")

    plan_title = current_plan.title if isinstance(current_plan, Plan) else "研究任务"
    plan_thought = current_plan.thought if isinstance(current_plan, Plan) else ""
    input_ = {
        "messages": [
            HumanMessage(
                f"# 研究需求\n\n## 任务\n\n{plan_title}\n\n## 描述\n\n{plan_thought}"
            )
        ],
        "locale": locale,
    }
    invoke_messages = apply_prompt_template("reporter", input_, locale=locale)

    # 注入各步骤的观察结果
    for observation in state.get("observations", []):
        invoke_messages.append(
            HumanMessage(
                content=f"以下是研究任务的一些观察结果：\n\n{observation}",
                name="observation",
            )
        )

    # 注入编号来源列表，供正文 [n] 引用
    sources = state.get("sources", [])
    if sources:
        sources_lines = "\n".join(
            f"[{i + 1}] {s.title}（{s.url}）" for i, s in enumerate(sources)
        )
        invoke_messages.append(
            HumanMessage(
                content=(
                    "可用引用来源列表（正文中引用信息时必须使用对应的 [n] 编号）：\n"
                    f"{sources_lines}"
                ),
                name="system",
            )
        )

    # 引用格式提醒
    invoke_messages.append(
        HumanMessage(
            content=(
                "重要：请按 prompt 中的格式组织报告。正文中的引用必须使用 [n] 编号格式"
                "（n 为可用引用来源列表中的编号），并在报告末尾的「参考来源」部分"
                "列出编号来源对应表。优先使用 Markdown 表格呈现比较数据。"
            ),
            name="system",
        )
    )

    response = get_llm().invoke(invoke_messages)
    response_content = str(response.content)
    logger.info("reporter 报告完成，长度 %d 字符", len(response_content))
    return {"final_report": response_content}
