"""MCP 工具接入（可选组件，未配置时零侵入）。

配置文件采用 MCP 官方多服务器格式（``mcp.json``）：

```json
{
  "mcpServers": {
    "fetch": {
      "transport": "stdio",
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    },
    "weather": {
      "transport": "streamable_http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

设计要点：
- ``DEEPQUEST_MCP_CONFIG`` 未设置 / 文件不存在 / 解析失败 → 返回空列表，
  主流程不受影响；
- 按服务器逐个加载：单个 MCP 服务器挂掉只跳过该服务器的工具，
  不拖垮其他服务器与内置工具（与"工具错误返回字符串而非异常"的项目约定一致）；
- MCP 工具仅注入 researcher 代理（围绕信息获取场景）；
- langchain-mcp-adapters 0.3.x 的工具每次调用自建临时会话，
  无需长连接生命周期管理。
"""

import json
import logging
from pathlib import Path

from langchain_core.tools import BaseTool

from deepquest.config.settings import get_settings

logger = logging.getLogger(__name__)


def _load_connections(path: Path) -> dict:
    """解析 mcp.json，返回 ``{服务器名: 连接配置}`` 字典。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    connections = data.get("mcpServers", {})
    if not isinstance(connections, dict):
        logger.warning("mcp.json 的 mcpServers 字段必须是对象，跳过 MCP 工具")
        return {}
    return connections


async def load_mcp_tools() -> list[BaseTool]:
    """加载 mcp.json 中所有 MCP 服务器的工具。

    Returns:
        LangChain 工具列表；未配置或加载失败时返回空列表。
    """
    settings = get_settings()
    if not settings.mcp_config:
        return []

    path = Path(settings.mcp_config)
    if not path.exists():
        logger.warning("DEEPQUEST_MCP_CONFIG=%s 不存在，跳过 MCP 工具", settings.mcp_config)
        return []

    try:
        connections = _load_connections(path)
    except (json.JSONDecodeError, OSError):
        logger.warning("mcp.json 解析失败，跳过 MCP 工具", exc_info=True)
        return []

    if not connections:
        return []

    # 懒导入：未启用 MCP 时完全不加载该依赖
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(connections)
    tools: list[BaseTool] = []
    for server_name in connections:
        try:
            server_tools = await client.get_tools(server_name=server_name)
            tools.extend(server_tools)
            logger.info(
                "MCP 服务器 %s 提供工具：%s",
                server_name,
                [t.name for t in server_tools] or "（无）",
            )
        except Exception:  # noqa: BLE001
            logger.warning("MCP 服务器 %s 工具加载失败，已跳过", server_name, exc_info=True)
    return tools
