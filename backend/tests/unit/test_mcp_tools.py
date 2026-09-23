"""MCP 工具加载门控单测（不依赖真实 MCP 服务器）。"""

import json
from pathlib import Path
from types import SimpleNamespace

from deepquest.tools.mcp import _load_connections, load_mcp_tools


def _fake_settings(mcp_config: str = ""):
    return SimpleNamespace(mcp_config=mcp_config)


async def test_not_configured_returns_empty(monkeypatch):
    """DEEPQUEST_MCP_CONFIG 未设置时返回空列表。"""
    monkeypatch.setattr(
        "deepquest.tools.mcp.get_settings", lambda: _fake_settings("")
    )
    assert await load_mcp_tools() == []


async def test_config_file_missing_returns_empty(monkeypatch):
    """配置文件不存在时返回空列表并告警，不抛异常。"""
    monkeypatch.setattr(
        "deepquest.tools.mcp.get_settings",
        lambda: _fake_settings(str(Path("no-such-mcp.json"))),
    )
    assert await load_mcp_tools() == []


async def test_invalid_json_returns_empty(monkeypatch, tmp_path):
    """JSON 解析失败时返回空列表，不抛异常。"""
    bad = tmp_path / "mcp.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(
        "deepquest.tools.mcp.get_settings", lambda: _fake_settings(str(bad))
    )
    assert await load_mcp_tools() == []


async def test_empty_servers_returns_empty(monkeypatch, tmp_path):
    """mcpServers 为空对象时返回空列表。"""
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    monkeypatch.setattr(
        "deepquest.tools.mcp.get_settings", lambda: _fake_settings(str(cfg))
    )
    assert await load_mcp_tools() == []


async def test_unreachable_server_skipped_gracefully(monkeypatch, tmp_path):
    """单个 MCP 服务器不可达时跳过该服务器，返回空列表且不抛异常。"""
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "broken": {
                        "transport": "stdio",
                        "command": "definitely-not-exist-cmd-xyz",
                        "args": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "deepquest.tools.mcp.get_settings", lambda: _fake_settings(str(cfg))
    )
    tools = await load_mcp_tools()
    assert tools == []


def test_load_connections_parses_official_format(tmp_path):
    """_load_connections 解析 MCP 官方多服务器格式。"""
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "a": {"transport": "stdio", "command": "uvx", "args": ["x"]},
                    "b": {"transport": "streamable_http", "url": "http://x/mcp"},
                }
            }
        ),
        encoding="utf-8",
    )
    connections = _load_connections(cfg)
    assert set(connections) == {"a", "b"}
    assert connections["a"]["command"] == "uvx"


def test_load_connections_invalid_servers_field(tmp_path):
    """mcpServers 非对象时返回空 dict。"""
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": ["not", "a", "dict"]}), encoding="utf-8")
    assert _load_connections(cfg) == {}
