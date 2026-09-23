"""lifespan 持久化选择单测：memory / postgres 分支与失败配置的快速报错。

不依赖真实 Postgres：postgres 分支通过替身 AsyncPostgresSaver 验证
"建表 → 挂图 → 关闭连接" 的生命周期顺序。
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

from langgraph.checkpoint.memory import MemorySaver

import deepquest.server.app as app_module
from deepquest.server.app import _make_serializer, lifespan


def _fake_settings(persistence_type: str, postgres_uri: str = ""):
    return SimpleNamespace(
        persistence_type=persistence_type,
        postgres_uri=postgres_uri,
        langfuse_enabled=False,
    )


class _FakePostgresSaver(MemorySaver):
    """记录 setup() 调用次数的检查点保存器替身（借 MemorySaver 通过类型校验）。"""

    def __init__(self) -> None:
        super().__init__()
        self.setup_called = 0

    async def setup(self) -> None:
        self.setup_called += 1


async def test_memory_mode_builds_memory_saver(monkeypatch):
    """persistence_type=memory 时图使用 MemorySaver。"""
    monkeypatch.setattr(
        app_module, "get_settings", lambda: _fake_settings("memory")
    )
    app_stub = SimpleNamespace(state=SimpleNamespace())
    async with lifespan(app_stub):
        graph = app_stub.state.graph
        assert type(graph.checkpointer) is MemorySaver


async def test_postgres_mode_setups_and_attaches_saver(monkeypatch):
    """persistence_type=postgres 时执行 setup() 并把 saver 挂到图上。"""
    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: _fake_settings("postgres", "postgresql://u:p@localhost:5432/d"),
    )
    fake_saver = _FakePostgresSaver()

    @asynccontextmanager
    async def fake_from_conn_string(conn_string, *, pipeline=False, serde=None):
        assert conn_string == "postgresql://u:p@localhost:5432/d"
        yield fake_saver

    monkeypatch.setattr(
        app_module.AsyncPostgresSaver,
        "from_conn_string",
        staticmethod(fake_from_conn_string),
    )

    app_stub = SimpleNamespace(state=SimpleNamespace())
    async with lifespan(app_stub):
        assert fake_saver.setup_called == 1
        assert app_stub.state.graph.checkpointer is fake_saver


async def test_postgres_mode_without_uri_fails_fast(monkeypatch):
    """postgres 模式缺 URI 时启动即报错，而不是静默回退内存。"""
    monkeypatch.setattr(
        app_module, "get_settings", lambda: _fake_settings("postgres", "")
    )
    app_stub = SimpleNamespace(state=SimpleNamespace())
    try:
        async with lifespan(app_stub):
            pass
    except RuntimeError as e:
        assert "DEEPQUEST_POSTGRES_URI" in str(e)
    else:
        raise AssertionError("postgres 模式缺 URI 应当抛出 RuntimeError")


def test_serializer_round_trips_plan():
    """序列化器可往返 Plan/Step/StepType（checkpoint 恢复的关键路径）。"""
    from deepquest.prompts.models import Plan, Step, StepType

    plan = Plan(
        locale="zh-CN",
        has_enough_context=False,
        thought="先搜索再分析",
        title="测试研究",
        steps=[
            Step(
                need_search=True,
                title="检索",
                description="搜索相关资料",
                step_type=StepType.RESEARCH,
            )
        ],
    )
    serializer = _make_serializer()
    typ, payload = serializer.dumps_typed(plan)
    restored = serializer.loads_typed((typ, payload))
    assert restored == plan
