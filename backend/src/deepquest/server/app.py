"""FastAPI 应用：SSE 流式研究接口。

端点：
- ``GET  /api/health``：健康检查；
- ``POST /api/research``：启动（或续传）一次深度研究，返回 SSE 事件流。
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Command
from sse_starlette.sse import EventSourceResponse

from deepquest.config.settings import get_settings
from deepquest.graph.builder import build_graph
from deepquest.prompts.models import Plan, Source, Step, StepType
from deepquest.server.schemas import ChatRequest, ResumeRequest
from deepquest.server.sse import make_event, process_message_chunk, process_updates

logger = logging.getLogger(__name__)

# 图执行的递归上限（覆盖全部节点 + 各代理内部 ReAct 循环）
_GRAPH_RECURSION_LIMIT = 150


def _make_checkpointer() -> MemorySaver:
    """构造 Phase 1 的内存检查点保存器。

    显式把 deepquest.prompts.models 注册进 msgpack 反序列化白名单，
    避免 checkpoint 恢复时 Plan/StepType 触发"unregistered type"警告
    （该行为在未来 langgraph 版本默认会被阻断）。
    """
    serializer = JsonPlusSerializer(
        allowed_msgpack_modules=[Plan, Step, StepType, Source]
    )
    return MemorySaver(serde=serializer)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时构建研究图（Phase 1 固定使用 MemorySaver）。"""
    settings = get_settings()
    if settings.persistence_type == "postgres":
        # Postgres 持久化在 Phase 3 交付，当前回退到内存模式
        logger.info("persistence_type=postgres 将在 Phase 3 支持，本次回退 MemorySaver")
    app.state.graph = build_graph(checkpointer=_make_checkpointer())
    logger.info("DeepQuest 研究图已初始化（MemorySaver）")
    yield


app = FastAPI(title="DeepQuest", lifespan=lifespan)


@app.get("/api/health")
async def health() -> dict:
    """健康检查。"""
    return {"status": "ok"}


def _build_workflow_input(request: ChatRequest) -> dict:
    """构造首次启动时的图输入。"""
    messages = [m.model_dump() for m in request.messages]
    latest_content = messages[-1]["content"] if messages else ""
    return {
        "messages": messages,
        "research_topic": latest_content,
        "locale": "zh-CN",
        "plan_iterations": 0,
        "final_report": "",
        "current_plan": None,
        "observations": [],
        "auto_accepted_plan": request.auto_accepted_plan,
        "enable_background_investigation": request.enable_background_investigation,
    }


async def _build_resume_command(
    graph, config: dict, resume: ResumeRequest
) -> Command:
    """根据恢复请求类型构造 ``Command(resume=...)``。"""
    if resume.type == "accepted":
        return Command(resume="[ACCEPTED]")
    if resume.type == "feedback":
        return Command(resume=f"[EDIT_PLAN] {resume.content or ''}")

    # edit_plan：直接采用前端编辑后的完整计划，计划轮次 +1
    if not resume.plan:
        raise HTTPException(status_code=422, detail="edit_plan 恢复类型必须携带 plan 字段")
    plan = Plan.model_validate(resume.plan)
    snapshot = await graph.aget_state(config)
    plan_iterations = (snapshot.values.get("plan_iterations") or 0) + 1
    return Command(
        resume="[ACCEPTED]",
        update={"current_plan": plan, "plan_iterations": plan_iterations},
    )


async def _event_generator(
    graph, workflow_input, config: dict, thread_id: str
) -> AsyncIterator[dict]:
    """驱动图执行并把事件转换为 SSE 格式。"""
    yield make_event("start", {"thread_id": thread_id})
    error_occurred = False
    try:
        async for namespace, mode, payload in graph.astream(
            workflow_input,
            config=config,
            stream_mode=["messages", "updates"],
            subgraphs=True,
        ):
            if mode == "updates":
                # payload: {node_name: update_dict} 或含 __interrupt__
                for event in process_updates(payload, thread_id):
                    yield event
            else:
                # payload: (message_chunk, metadata)
                message_chunk, metadata = payload
                for event in process_message_chunk(
                    message_chunk, metadata, thread_id, namespace
                ):
                    yield event
    except Exception as e:  # noqa: BLE001
        logger.exception("图执行出错（thread_id=%s）", thread_id)
        yield make_event("error", {"thread_id": thread_id, "error": str(e)})
        error_occurred = True

    # 结束事件：reporter 完成后 final_report 非空，否则为空串
    final_report = ""
    if not error_occurred:
        try:
            snapshot = await graph.aget_state(config)
            final_report = snapshot.values.get("final_report", "") or ""
        except Exception:  # noqa: BLE001
            logger.warning("读取最终状态失败（thread_id=%s）", thread_id)
    yield make_event("end", {"thread_id": thread_id, "final_report": final_report})


@app.post("/api/research")
async def research(request: ChatRequest, http_request: Request) -> EventSourceResponse:
    """启动或续传一次深度研究，返回 SSE 事件流。

    - 首次启动：body 携带 messages 等参数，thread_id 为空时自动生成；
    - 中断续传：body 携带 thread_id + resume 字段，通过 ``Command(resume=...)``
      恢复暂停中的图。
    """
    graph = http_request.app.state.graph
    thread_id = request.thread_id or str(uuid4())
    config = {
        "configurable": {
            "thread_id": thread_id,
            "max_plan_iterations": request.max_plan_iterations,
            "max_step_num": request.max_step_num,
        },
        "recursion_limit": _GRAPH_RECURSION_LIMIT,
    }

    if request.resume is not None:
        if not request.thread_id:
            raise HTTPException(status_code=422, detail="续传请求必须携带 thread_id")
        logger.info(
            "恢复中断的研究（thread_id=%s, resume.type=%s）", thread_id, request.resume.type
        )
        workflow_input = await _build_resume_command(graph, config, request.resume)
    else:
        logger.info("启动新的研究（thread_id=%s）", thread_id)
        workflow_input = _build_workflow_input(request)

    return EventSourceResponse(
        _event_generator(graph, workflow_input, config, thread_id)
    )
