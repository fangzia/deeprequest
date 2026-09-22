"""可观测性子包（占位）。

Phase 2 将填充 Langfuse 集成：懒加载 + ``DEEPQUEST_LANGFUSE_ENABLED`` 开关、
全图 trace（``graph.astream(..., config={"callbacks": [handler]})``）、
``session_id=thread_id`` 与 shutdown flush。
"""
