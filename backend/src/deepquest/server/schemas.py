"""请求/响应与 SSE 事件的数据模型。"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# ===== 请求模型 =====


class ChatMessage(BaseModel):
    """单条会话消息。"""

    role: str = Field(..., description="消息角色：user / assistant")
    content: str = Field(..., description="消息文本内容")


class ResumeRequest(BaseModel):
    """中断恢复请求。

    - ``accepted``：接受当前计划，等价于 ``Command(resume="[ACCEPTED]")``；
    - ``feedback``：以文本修改意见回退到 planner 重新规划，等价于
      ``Command(resume="[EDIT_PLAN] " + content)``；
    - ``edit_plan``：直接提交编辑后的完整计划，等价于
      ``Command(resume="[ACCEPTED]", update={current_plan: Plan(...)})``；
      计划轮次由 human_feedback 节点统一计数。
    """

    type: Literal["accepted", "feedback", "edit_plan"] = Field(..., description="恢复类型")
    content: str | None = Field(default=None, description="feedback 类型的修改意见文本")
    plan: dict[str, Any] | None = Field(default=None, description="edit_plan 类型的完整 Plan JSON")


class ChatRequest(BaseModel):
    """POST /api/research 请求体。"""

    messages: list[ChatMessage] = Field(default_factory=list, description="用户会话消息")
    thread_id: str | None = Field(default=None, description="会话线程 ID；续传时必传")
    auto_accepted_plan: bool = Field(default=False, description="是否自动接受计划（跳过人工确认）")
    max_research_rounds: int = Field(
        default=1, description="最大研究轮数（计划→执行的循环上限，仅在计划被接受时计数）"
    )
    max_plan_retries: int = Field(default=1, description="计划解析失败时的最大重试次数")
    max_step_num: int = Field(default=3, description="计划的最大步骤数")
    enable_background_investigation: bool = Field(
        default=True, description="是否在规划前执行背景调查"
    )
    resume: ResumeRequest | None = Field(default=None, description="中断恢复参数（续传时使用）")


# ===== SSE 事件模型（与前端对接协议，字段名必须严格一致）=====


class StartEvent(BaseModel):
    """``start`` 事件：流开始。"""

    thread_id: str


class MessageChunkEvent(BaseModel):
    """``message_chunk`` 事件：LLM 增量文本。"""

    thread_id: str
    agent: str
    content: str


class ToolCallItem(BaseModel):
    """``tool_calls`` 事件中的单个完整工具调用。"""

    name: str
    args: str = Field(..., description="工具参数（JSON 字符串）")
    id: str


class ToolCallsEvent(BaseModel):
    """``tool_calls`` 事件：完整的工具调用列表。"""

    thread_id: str
    agent: str
    tool_calls: list[ToolCallItem]


class ToolCallChunkPayload(BaseModel):
    """``tool_call_chunks`` 事件中的单个流式工具调用分片。"""

    name: str | None = None
    args: str = ""
    id: str | None = None
    index: int = 0


class ToolCallChunksEvent(BaseModel):
    """``tool_call_chunks`` 事件：流式工具调用分片。"""

    thread_id: str
    agent: str
    tool_call_chunk: ToolCallChunkPayload


class ToolCallResultEvent(BaseModel):
    """``tool_call_result`` 事件：工具执行结果。"""

    thread_id: str
    agent: str
    tool_name: str
    content: str
    status: Literal["success", "error"] = "success"


class StepResultEvent(BaseModel):
    """``step_result`` 事件：单个研究步骤执行完成。"""

    thread_id: str
    agent: str
    topic: str = Field(..., description="当前步骤标题")
    content: str = Field(..., description="该步执行结果")


class InterruptEvent(BaseModel):
    """``interrupt`` 事件：图因等待人工确认而暂停。"""

    thread_id: str
    type: str = Field(default="plan_review", description="中断类型")
    plan: str = Field(..., description="Plan 的 JSON 字符串")


class ErrorEvent(BaseModel):
    """``error`` 事件：执行出错。"""

    thread_id: str
    error: str


class EndEvent(BaseModel):
    """``end`` 事件：流结束。"""

    thread_id: str
    final_report: str = Field(default="", description="报告 markdown（reporter 完成后才有）")
