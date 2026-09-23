"""可观测性子包：Langfuse 集成（可选组件）。

用法（server/app.py）：在构造图执行 config 后调用

    config = attach_langfuse_trace(config, thread_id)

未启用时 config 原样返回，主流程零侵入；应用关闭前调用 ``flush_langfuse``
确保缓冲区 trace 落库。
"""

from deepquest.observability.langfuse import (
    attach_langfuse_trace,
    flush_langfuse,
)

__all__ = ["attach_langfuse_trace", "flush_langfuse"]
