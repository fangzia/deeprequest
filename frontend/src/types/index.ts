/**
 * DeepQuest 前端全局类型定义
 * 覆盖：研究计划（Plan）、研究过程（时间线/来源）、SSE 事件协议、请求体
 */

/** 参与研究流程的智能体类型 */
export type AgentType =
  | 'coordinator'
  | 'planner'
  | 'researcher'
  | 'analyst'
  | 'coder'
  | 'reporter'

/** 研究步骤类型 */
export type StepType = 'research' | 'analysis' | 'processing'

/** 研究计划中的单个步骤 */
export interface PlanStep {
  /** 该步骤是否需要联网搜索 */
  need_search: boolean
  /** 步骤标题 */
  title: string
  /** 步骤描述 */
  description: string
  /** 步骤类型 */
  step_type: StepType
  /** 执行结果（后端回填，前端仅展示） */
  execution_res?: string
}

/** 研究计划（planner 产出的结构化 JSON） */
export interface Plan {
  locale: string
  has_enough_context: boolean
  thought: string
  title: string
  steps: PlanStep[]
}

/** 引用来源（报告中 [n] 引用对应的条目） */
export interface Source {
  url: string
  title: string
  snippet?: string
}

/** 研究状态机：空闲 → 规划中 → 等待确认 → 研究中 → 撰写报告 → 完成；任意状态可进入错误 */
export type ResearchStatus =
  | 'idle'
  | 'planning'
  | 'awaiting_approval'
  | 'researching'
  | 'reporting'
  | 'done'
  | 'error'

/** 对话消息（请求体中 messages 数组的元素） */
export interface ResearchMessage {
  role: 'user' | 'assistant'
  content: string
}

/** interrupt 后的续传指令 */
export type ResumePayload =
  | { type: 'accepted' }
  | { type: 'feedback'; content: string }

/** POST /api/research 请求体 */
export interface ResearchRequestBody {
  /** 首次请求必填；续传时可省略 */
  messages?: ResearchMessage[]
  /** 续传（interrupt 后）必填 */
  thread_id?: string
  auto_accepted_plan?: boolean
  /** 最大研究轮数（计划→执行的循环上限） */
  max_research_rounds?: number
  /** 计划解析失败时的最大重试次数 */
  max_plan_retries?: number
  max_step_num?: number
  enable_background_investigation?: boolean
  /** 仅续传请求携带 */
  resume?: ResumePayload
}

/* ---------- SSE 事件（event 名 + data JSON） ---------- */

/** start 事件：会话开始，返回 thread_id */
export interface StartEvent {
  thread_id: string
}

/** message_chunk 事件：某个智能体的增量文本（planner 为 Plan JSON 增量） */
export interface MessageChunkEvent {
  thread_id: string
  agent: AgentType
  content: string | null
}

/** 一次完整的工具调用（可能批量多条） */
export interface ToolCallItem {
  name: string
  args: string
  id: string
}

/** tool_calls 事件 */
export interface ToolCallsEvent {
  thread_id: string
  agent: AgentType
  tool_calls: ToolCallItem[]
}

/** tool_call_chunks 事件：工具调用流式分片 */
export interface ToolCallChunksEvent {
  thread_id: string
  agent: AgentType
  tool_call_chunk: {
    name?: string | null
    args?: string | null
    id?: string | null
    index: number
  }
}

/** tool_call_result 事件：工具执行结果 */
export interface ToolCallResultEvent {
  thread_id: string
  agent: AgentType
  tool_name: string
  content: string
  status: 'success' | 'error'
}

/** step_result 事件：一个研究步骤完成 */
export interface StepResultEvent {
  thread_id: string
  agent: AgentType
  topic: string
  content: string
}

/** interrupt 事件：流程中断等待人工确认（plan 为 Plan JSON 字符串） */
export interface InterruptEvent {
  thread_id: string
  type: 'plan_review'
  plan: string
}

/** error 事件：后端报错 */
export interface ErrorEvent {
  thread_id: string
  error: string
}

/** end 事件：流程结束，返回最终报告 */
export interface EndEvent {
  thread_id: string
  final_report: string
}

/** 所有 SSE 事件 data 的联合类型 */
export type SSEEventData =
  | StartEvent
  | MessageChunkEvent
  | ToolCallsEvent
  | ToolCallChunksEvent
  | ToolCallResultEvent
  | StepResultEvent
  | InterruptEvent
  | ErrorEvent
  | EndEvent

/* ---------- 研究过程时间线（活动流） ---------- */

/** 时间线条目类型 */
export type TimelineKind = 'tool' | 'step' | 'text'

/** 研究过程时间线条目（工具调用 / 步骤结果 / 智能体思考文本） */
export interface TimelineItem {
  id: number
  kind: TimelineKind
  agent: AgentType
  /** 记录时间（HH:mm:ss） */
  time: string
  /** kind=step：步骤标题 */
  topic?: string
  /** kind=step/text：正文内容 */
  content?: string
  /** kind=tool：工具名 */
  toolName?: string
  /** kind=tool：工具入参（JSON 字符串，可能不完整） */
  args?: string
  /** kind=tool：工具结果内容 */
  resultContent?: string
  /** kind=tool：执行状态 */
  status?: 'running' | 'success' | 'error'
  /** 工具调用 id（tool_call_chunks 去重用） */
  toolCallId?: string
}
