# DeepQuest

> 可观测、可评测、可扩展 MCP 工具的中文 Deep Research 多智能体系统

基于 LangGraph 的「规划 → 研究 → 分析 → 成稿」深度研究流水线：输入一个研究主题，
多智能体团队自动拆解计划、联网检索、交叉分析，最终产出带 `[n]` 编号引用的结构化报告。

## 架构

```text
                          ┌─────────────────────────────────────────────────┐
                          │                LangGraph 研究图                  │
                          │                                                 │
 START ──→ coordinator ──(背景调查开关)──→ background_investigator           │
              │        └──(跳过背景调查)──→ planner ←──────┐                 │
              │                    │                      │                 │
              │        (轮次上限/解析失败/背景足够)          │ (edit_plan     │
              │            ┌───→ human_feedback ⛔中断     │  /invalid)     │
              │            │         │                    │                 │
              │            │    (accepted)                │                 │
              │            │         ↓                    │                 │
              │            │    research_team ⇄ researcher / analyst / coder
              │            │         │                    │                 │
              │            │    (全部完成)──→ reporter ──→ END               │
              │            └──(auto_accepted)──→ reporter                   │
                          └─────────────────────────────────────────────────┘
                                     │ checkpointer（memory / Postgres）
                                     ▼
                     SSE 事件流（计划卡片 / token 流 / 工具调用时间线 / 报告）
```

- **多智能体协作**：coordinator / planner / researcher / analyst / coder / reporter，全部拓扑集中声明在 [builder.py](backend/src/deepquest/graph/builder.py)，路由逻辑独立于 [routing.py](backend/src/deepquest/graph/routing.py)
- **human-in-the-loop**：研究计划通过 LangGraph `interrupt` 暂停，前端可审批 / 反馈 / 直接编辑计划后 `Command(resume=...)` 续传
- **可观测**：Langfuse 全链路 trace（按 `thread_id` 聚合 session，每个节点、工具调用、token 消耗）
- **可持久化**：checkpointer 插件化，内存模式零依赖，Postgres 模式跨重启续传
- **可评测**：内置 citation eval，量化报告引用的幻觉率 / 覆盖率 / 密度
- **可扩展**：MCP 协议工具热插拔（`mcp.json` 声明即接入 researcher）
- **引用可溯源**：报告中的 `[n]` 引用对应结构化来源列表，逐条可回查

## 快速开始

依赖：Python 3.12+、[uv](https://docs.astral.sh/uv/)、Node.js 18+。

```bash
# 1. 后端
cd backend
cp .env.example .env       # 填入 DEEPQUEST_LLM_API_KEY（DeepSeek 等任意 OpenAI 兼容接口）
uv sync
uv run uvicorn deepquest.server.app:app --reload --port 8598

# 2. 前端（另开终端）
cd frontend
npm install
npm run dev                # 默认 http://localhost:5173
```

`TAVILY_API_KEY`（[免费注册](https://tavily.com)）缺失时不会崩溃：搜索工具降级为
带清晰提示的占位工具，流程仍可走通。

## 可选组件

三个可选组件全部通过配置门控，默认关闭，不影响主流程：

| 组件                       | 开启方式                                                                                                                                               | 说明                                             |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| **Langfuse**（trace）      | `docker compose -f docker-compose.langfuse.yml up -d`，在 UI 创建项目拿 key，`.env` 设 `DEEPQUEST_LANGFUSE_ENABLED=true` + `LANGFUSE_PUBLIC_KEY/SECRET_KEY` | 自托管社区版免费；一次研究会话聚合为一条 session，回放全链路             |
| **Postgres**（checkpoint） | `docker compose up -d`，`.env` 设 `DEEPQUEST_PERSISTENCE_TYPE=postgres` + `DEEPQUEST_POSTGRES_URI`                                                   | 服务重启后中断的研究可续传；建表幂等（`setup()`）                  |
| **MCP 工具**               | `cp backend/mcp.json.example backend/mcp.json`，`.env` 设 `DEEPQUEST_MCP_CONFIG=./mcp.json`                                                          | MCP 官方多服务器格式，stdio / streamable\_http；按服务器独立降级 |

## 测试与评测

```bash
cd backend

# 单元测试（46+ 个，零 API 成本：FakeChatModel 跑通全图，含中断续传）
uv run pytest

# 静态检查
uv run ruff check src tests

# 引用一致性评测（对 {"report": ..., "sources": [...]} 格式的 JSON）
uv run python -m deepquest.evals.citation result.json
```

citation eval 输出四项指标：**越界引用**（`[n]` 指向不存在的来源，即幻觉引用）、
**来源覆盖率**（检索到且实际被引用的比例）、**幻觉引用率**、**引用密度**（次/千字）。

## 项目结构

```text
backend/
├── src/deepquest/
│   ├── graph/          # 图构建：builder（集中边）/ nodes / routing / state
│   ├── agents/         # 代理工厂：按步骤动态创建 ReAct 代理（langchain.agents）
│   ├── llm/            # LLM provider（OpenAI 兼容接口，进程内缓存）
│   ├── tools/          # 内置工具（Tavily 搜索 / Jina 抓取 / REPL）+ MCP 接入
│   ├── prompts/        # 提示词模板与 Plan/Source 领域模型
│   ├── server/         # FastAPI：SSE 端点、事件转换（纯函数）、schemas
│   ├── observability/  # Langfuse 集成（可选，attach_langfuse_trace）
│   ├── evals/          # citation eval（确定性校验，无 LLM 依赖）
│   └── config/         # pydantic-settings 统一配置（DEEPQUEST_ 前缀）
└── tests/unit/         # 图拓扑 / 中断续传 / SSE / 路由 / 评测 / 门控逻辑
frontend/               # Vue 3 + Element Plus：计划卡片、时间线、Markdown 报告渲染
```

## 设计取舍

- **集中式边声明**：不使用节点内 `Command(goto=...)` 跳转，全部拓扑在 `builder.py`
  一览无余；节点只返回 dict，通过 `plan_error` / `feedback_decision` 等 State 信号
  字段与路由函数通信——图的"读"与"写"分离，可测试性显著更好。
- **SSE 协议层纯函数化**：`server/sse.py` 不依赖 FastAPI 上下文，事件转换可单测，
  前后端协议演进有单一收敛点。
- **零成本测试**：`FakeChatModel` / `SequenceFakeChatModel` 替换 `get_llm()`，
  全图（含 interrupt/resume）测试不花一分钱 API 费。
- **可选组件零侵入**：Langfuse / Postgres / MCP 的门控都收敛在模块边界
  （`attach_langfuse_trace` / `load_mcp_tools` / lifespan 分支），关闭时主路径
  代码路径完全不变。
- **工具错误不抛异常**：缺 key 的搜索、挂掉的 MCP 服务器都返回错误字符串或
  降级空列表，让模型有机会自修复而不是整个研究流程崩溃。

## License

MIT
