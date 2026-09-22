"""计划（Plan）与引用来源（Source）数据模型。"""

from enum import StrEnum

from pydantic import BaseModel, Field


class StepType(StrEnum):
    """研究步骤类型。"""

    RESEARCH = "research"
    ANALYSIS = "analysis"
    PROCESSING = "processing"


class Step(BaseModel):
    """单个研究步骤。"""

    need_search: bool = Field(..., description="该步骤是否需要联网搜索")
    title: str = Field(..., description="步骤标题")
    description: str = Field(..., description="指定要收集的确切数据或要执行的分析")
    step_type: StepType = Field(..., description="步骤性质：research/analysis/processing")
    execution_res: str | None = Field(default=None, description="该步骤的执行结果")


class Plan(BaseModel):
    """研究计划。"""

    locale: str = Field(default="zh-CN", description="基于用户语言，如 zh-CN/en-US")
    has_enough_context: bool = Field(..., description="已有背景是否足以直接产出报告")
    thought: str = Field(default="", description="规划思考过程")
    title: str = Field(..., description="研究任务标题")
    steps: list[Step] = Field(default_factory=list, description="研究/分析/处理步骤列表")


class Source(BaseModel):
    """引用来源，用于报告的 [n] 编号引用与引用评测。"""

    url: str = Field(..., description="来源 URL")
    title: str = Field(default="", description="来源标题")
    snippet: str = Field(default="", description="来源摘要片段")
