"""图状态定义。

相比参考实现（puffin-chat）的 State：
- 删除了所有业务字段（user_id/tenant_id/message_id/clarification 系列）；
- 新增 ``sources``：researcher 各步骤产出的引用来源聚合（去重），
  是报告 [n] 编号引用与引用评测（citation eval）的地基；
- 新增 ``plan_error`` / ``feedback_decision`` 两个路由信号字段：
  节点只写状态，路由函数（routing.py）读取这些信号决定下一跳。
"""

from langgraph.graph import MessagesState

from deepquest.prompts.models import Plan, Source


class State(MessagesState):
    """DeepQuest 研究图的全局状态。"""

    # 运行时变量
    locale: str = "zh-CN"
    research_topic: str = ""
    observations: list[str] = []
    current_step: str = ""
    # 已批准并派发执行的研究轮数：仅在 human_feedback 接受计划时自增。
    # 注意它不是"规划尝试次数"——planner 的解析重试由 plan_retries 单独计数。
    research_rounds: int = 0
    current_plan: Plan | str | None = None
    final_report: str = ""
    auto_accepted_plan: bool = False
    enable_background_investigation: bool = True
    background_investigation_results: str | None = None

    # 引用溯源：researcher 完成每步后解析 "- [标题](URL)" 聚合去重追加
    sources: list[Source] = []

    # 路由信号（节点写入、routing.py 的条件边函数读取）
    # planner 解析失败信号（含模型原始输出，重试时回注给 planner 修正）；成功时置 None
    plan_error: str | None = None
    # planner 解析失败的重试计数（每次失败 +1，成功清零）；
    # 超过 max_plan_retries 后不再重试，兜底进 reporter 或终止
    plan_retries: int = 0
    # human_feedback 对用户反馈的判定结果（accepted / edit_plan / invalid）
    feedback_decision: str | None = None
