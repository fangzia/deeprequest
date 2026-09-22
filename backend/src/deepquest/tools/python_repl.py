"""Python REPL 工具：简单 exec 沙箱 + stdout 捕获。

仅供 coder 代理做数学计算与数据处理；沙箱是"防止误伤"级别的简单隔离，
不是安全边界（不要暴露给不可信输入）。
"""

import contextlib
import io
import logging
from typing import Annotated

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def python_repl_tool(
    code: Annotated[str, "要执行的 Python 代码。想查看某个值时必须用 print(...) 输出。"],
) -> str:
    """执行 Python 代码进行数据分析或计算。想查看输出时，必须用 print(...) 打印。"""
    if not isinstance(code, str):
        return f"Error: code 必须是字符串，收到 {type(code).__name__}"

    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            # 简单沙箱：独立的全局命名空间，不带入调用方变量
            exec(code, {"__builtins__": __builtins__}, {})  # noqa: S102
    except Exception as e:  # noqa: BLE001
        logger.warning("python_repl_tool 执行出错: %r", e)
        return f"Error executing code:\n```python\n{code}\n```\nError: {e!r}"

    stdout = buffer.getvalue()
    return f"Successfully executed:\n```python\n{code}\n```\nStdout: {stdout}"
