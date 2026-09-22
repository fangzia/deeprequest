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
    plan_iterations: int = 0
    current_plan: Plan | str | None = None
    final_report: str = ""
    auto_accepted_plan: bool = False
    enable_background_investigation: bool = True
    background_investigation_results: str | None = None

    # 引用溯源：researcher 完成每步后解析 "- [标题](URL)" 聚合去重追加
    sources: list[Source] = []

    # 路由信号（节点写入、routing.py 的条件边函数读取）
    plan_error: str | None = None  # planner 解析失败信号；成功时由节点置 None
    feedback_decision: str | None = None  # accepted / edit_plan / invalid
