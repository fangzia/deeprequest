"""Langfuse 可观测性门控逻辑单测（不依赖真实 Langfuse 服务）。"""

import sys
from types import SimpleNamespace

from deepquest.observability.langfuse import (
    _langfuse_client,
    attach_langfuse_trace,
    flush_langfuse,
)


def _fake_settings(enabled: bool = False, public: str = "", secret: str = ""):
    """构造带 Langfuse 配置项的假 settings 对象。"""
    return SimpleNamespace(
        langfuse_enabled=enabled,
        langfuse_public_key=public,
        langfuse_secret_key=secret,
        langfuse_host="http://localhost:3000",
    )


def test_disabled_config_untouched(monkeypatch):
    """DEEPQUEST_LANGFUSE_ENABLED=false（默认）时 config 原样返回。"""
    monkeypatch.setattr(
        "deepquest.observability.langfuse.get_settings",
        lambda: _fake_settings(enabled=False, public="pk", secret="sk"),
    )
    config = {"configurable": {"thread_id": "t1"}}
    assert attach_langfuse_trace(config, "t1") is config
    assert "callbacks" not in config
    assert "metadata" not in config


def test_enabled_missing_keys_config_untouched(monkeypatch):
    """开启但缺少 public/secret key 时降级为原样返回，不抛异常。"""
    monkeypatch.setattr(
        "deepquest.observability.langfuse.get_settings",
        lambda: _fake_settings(enabled=True),
    )
    config = {"configurable": {"thread_id": "t1"}}
    assert attach_langfuse_trace(config, "t1") is config
    assert "callbacks" not in config


def test_import_failure_config_untouched(monkeypatch):
    """langfuse 未安装（import 失败）时降级为原样返回，不抛异常。"""
    monkeypatch.setattr(
        "deepquest.observability.langfuse.get_settings",
        lambda: _fake_settings(enabled=True, public="pk", secret="sk"),
    )
    # sys.modules 中置 None 可让 `from langfuse... import ...` 抛 ImportError
    monkeypatch.setitem(sys.modules, "langfuse", None)
    config = {"configurable": {"thread_id": "t1"}}
    assert attach_langfuse_trace(config, "t1") is config
    assert "callbacks" not in config


def test_enabled_attaches_callbacks_and_session_metadata(monkeypatch):
    """开关打开 + key 齐全 + langfuse 已安装时，挂载 handler 与 session 元数据。"""
    monkeypatch.setattr(
        "deepquest.observability.langfuse.get_settings",
        lambda: _fake_settings(enabled=True, public="pk-lf-test", secret="sk-lf-test"),
    )
    monkeypatch.setattr("deepquest.observability.langfuse._langfuse_client", None)
    try:
        config = {"configurable": {"thread_id": "t1"}}
        attach_langfuse_trace(config, "t1")
        assert len(config["callbacks"]) == 1
        assert type(config["callbacks"][0]).__name__ == "LangchainCallbackHandler"
        # Langfuse SDK 约定：根 run metadata 中的 langfuse_session_id 绑定 session
        assert config["metadata"]["langfuse_session_id"] == "t1"
        assert config["metadata"]["langfuse_tags"] == ["deepquest"]
    finally:
        # 还原进程级客户端缓存，避免影响其他测试
        import deepquest.observability.langfuse as m

        m._langfuse_client = _langfuse_client


def test_flush_is_safe_without_client():
    """未初始化 Langfuse 客户端时 flush 不抛异常。"""
    flush_langfuse()
