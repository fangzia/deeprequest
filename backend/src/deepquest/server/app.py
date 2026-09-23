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
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Command
from sse_starlette.sse import EventSourceResponse

from deepquest.config.settings import get_settings
from deepquest.graph.builder import build_graph
from deepquest.observability import attach_langfuse_trace, flush_langfuse
from deepquest.prompts.models import Plan, Source, Step, StepType
from deepquest.server.schemas import ChatRequest, ResumeRequest
from deepquest.server.sse import make_event, process_message_chunk, process_updates

logger = logging.getLogger(__name__)

# 图执行的递归上限（覆盖全部节点 + 各代理内部 ReAct 循环）
_GRAPH_RECURSION_LIMIT = 150


def _make_serializer() -> JsonPlusSerializer:
    """构造 checkpoint 序列化器。

    显式把 deepquest.prompts.models 注册进 msgpack 反序列化白名单，
    避免 checkpoint 恢复时 Plan/StepType 触发"unregistered type"警告
    （该行为在未来 langgraph 版本默认会被阻断）。
    """
    return JsonPlusSerializer(allowed_msgpack_modules=[Plan, Step, StepType, Source])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：按 persistence_type 构建研究图与检查点保存器。

    - ``memory``（默认）：MemorySaver，零依赖，进程重启即丢失；
    - ``postgres``：AsyncPostgresSaver，跨进程/重启持久化，启动时自动建表
      （``setup()`` 幂等，可安全重复执行）。
    """
    settings = get_settings()
    serializer = _make_serializer()

    if settings.persistence_type == "postgres":
        if not settings.postgres_uri:
            raise RuntimeError(
                "persistence_type=postgres 需要配置 DEEPQUEST_POSTGRES_URI"
                "（示例：postgresql://deepquest:deepquest@localhost:5432/deepquest）"
            )
        async with AsyncPostgresSaver.from_conn_string(
            settings.postgres_uri, serde=serializer
        ) as saver:
            await saver.setup()
            app.state.graph = build_graph(checkpointer=saver)
            logger.info("DeepQuest 研究图已初始化（AsyncPostgresSaver，持久化已就绪）")
            yield
    else:
        app.state.graph = build_graph(
            checkpointer=MemorySaver(serde=serializer)
        )
        logger.info("DeepQuest 研究图已初始化（MemorySaver）")
        yield

    flush_langfuse()


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

    # 可选 Langfuse trace：session 绑定 thread_id，一次研究会话聚合为一条 session
    config = attach_langfuse_trace(config, thread_id)

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
