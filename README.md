# DeepQuest

> 可观测、可评测、可扩展 MCP 工具的中文 Deep Research 多智能体系统

基于 LangGraph 的「规划 → 研究 → 分析 → 成稿」深度研究流水线：

- **多智能体协作**：coordinator / planner / researcher / analyst / coder / reporter，基于 LangGraph 状态图
- **human-in-the-loop**：研究计划可审批、可编辑，支持中断恢复
- **可观测**：Langfuse 全链路 trace（每个节点、工具调用、token 消耗）
- **可评测**：内置量化 benchmark（计划质量 / 引用准确率 / 要点覆盖度）
- **引用可溯源**：报告中的 `[n]` 引用对应结构化来源列表

🚧 项目正在建设中，架构设计与路线图见 `docs/`。

## 快速开始（建设中）

```bash
cp backend/.env.example backend/.env  # 填入 LLM 与 Tavily API Key
make dev
```
