/**
 * 研究流程 Pinia store
 * 职责：
 * 1. 研究状态机：idle → planning → awaiting_approval → researching → reporting → done（任意状态可进入 error）
 * 2. planner 增量 JSON 的流式解析与截断修复
 * 3. 研究过程时间线（工具调用 / 步骤结果 / 智能体思考文本）
 * 4. 最终报告与引用来源（sources）收集
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import { streamResearch } from '../api/sse'
import type {
  AgentType,
  InterruptEvent,
  Plan,
  PlanStep,
  ResearchRequestBody,
  ResearchStatus,
  Source,
  TimelineItem,
  ToolCallChunksEvent,
  ToolCallResultEvent,
} from '../types'

/* ==================== planner 增量 JSON 解析与修复 ==================== */

/** 从 planner 累积文本中提取 JSON 对象主体（剥掉 markdown 围栏与前后杂文本） */
function extractJsonCandidate(raw: string): string {
  let text = raw.trim()
  // 去掉 ```json ... ``` 围栏
  if (text.startsWith('```')) {
    text = text.replace(/^```[a-zA-Z]*\s*/, '').replace(/```\s*$/, '')
  }
  const start = text.indexOf('{')
  if (start === -1) return ''
  return text.slice(start)
}

/**
 * 修复可能被截断的 JSON 文本（流式期间 planner 输出尚未结束）。
 * 思路：一次扫描找到最后一个"值完整"的安全截断点，丢弃其后内容，
 * 再按括号栈补齐缺失的闭合符。返回 null 表示无法修复。
 */
function repairTruncatedJson(text: string): string | null {
  const stack: string[] = []
  let inString = false
  let escaped = false
  let lastSafe = -1
  let lastSafeStack: string[] = []
  let i = 0
  while (i < text.length) {
    const ch = text[i]
    if (inString) {
      if (escaped) {
        escaped = false
      } else if (ch === '\\') {
        escaped = true
      } else if (ch === '"') {
        // 字符串完整闭合，此处可安全截断
        inString = false
        lastSafe = i + 1
        lastSafeStack = [...stack]
      }
      i++
      continue
    }
    if (ch === '"') {
      inString = true
      i++
      continue
    }
    if (ch === '{' || ch === '[') {
      stack.push(ch)
      // 空容器开头也可安全闭合
      lastSafe = i + 1
      lastSafeStack = [...stack]
      i++
      continue
    }
    if (ch === '}' || ch === ']') {
      stack.pop()
      lastSafe = i + 1
      lastSafeStack = [...stack]
      i++
      continue
    }
    // 数字 / true / false / null 字面量：需后随 , } ] 才视为完整（保守处理，避免数字被截半）
    if (/[0-9\-]/.test(ch) || /[a-z]/.test(ch)) {
      let j = i
      while (j < text.length && /[0-9a-zA-Z.\-+]/.test(text[j])) j++
      const after = text.slice(j).match(/^\s*([,\}\]])/)
      if (after) {
        lastSafe = j
        lastSafeStack = [...stack]
      }
      i = j
      continue
    }
    // 逗号、冒号、空白：不标记安全点
    i++
  }
  if (lastSafe <= 0) return null
  let repaired = text.slice(0, lastSafe)
  for (let k = lastSafeStack.length - 1; k >= 0; k--) {
    repaired += lastSafeStack[k] === '{' ? '}' : ']'
  }
  return repaired
}

/** 将任意解析结果归一化为 Plan 结构；无法归一化时返回 null */
function normalizePlan(data: unknown, depth = 0): Plan | null {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null
  let obj = data as Record<string, unknown>
  // 兼容 {'content': '<Plan JSON 字符串>'} 的包裹格式（planner 输出偶发包裹）
  if (
    depth < 2 &&
    typeof obj.content === 'string' &&
    obj.title === undefined &&
    obj.steps === undefined
  ) {
    const inner = extractJsonCandidate(obj.content)
    if (!inner) return null
    try {
      return normalizePlan(JSON.parse(inner), depth + 1)
    } catch {
      const repaired = repairTruncatedJson(inner)
      if (repaired === null) return null
      try {
        return normalizePlan(JSON.parse(repaired), depth + 1)
      } catch {
        return null
      }
    }
  }
  const rawSteps = Array.isArray(obj.steps) ? obj.steps : []
  const steps: PlanStep[] = []
  for (const s of rawSteps) {
    if (!s || typeof s !== 'object') continue
    const step = s as Record<string, unknown>
    steps.push({
      need_search: step.need_search === true,
      title: typeof step.title === 'string' ? step.title : '',
      description: typeof step.description === 'string' ? step.description : '',
      step_type:
        step.step_type === 'research' || step.step_type === 'analysis' || step.step_type === 'processing'
          ? step.step_type
          : 'research',
      execution_res: typeof step.execution_res === 'string' ? step.execution_res : undefined,
    })
  }
  return {
    locale: typeof obj.locale === 'string' ? obj.locale : 'zh-CN',
    has_enough_context: obj.has_enough_context === true,
    thought: typeof obj.thought === 'string' ? obj.thought : '',
    title: typeof obj.title === 'string' ? obj.title : '',
    steps,
  }
}

/**
 * 解析 planner 累积文本为 Plan。
 * - 文本完整时 JSON.parse 直接成功，complete=true；
 * - 流式期间文本被截断时做修复解析，complete=false（用于 UI 预览）。
 */
export function parsePlanText(raw: string): { plan: Plan | null; complete: boolean } {
  const text = extractJsonCandidate(raw)
  if (!text) return { plan: null, complete: false }
  try {
    return { plan: normalizePlan(JSON.parse(text)), complete: true }
  } catch {
    // 尚未输出完整，继续尝试修复
  }
  const repaired = repairTruncatedJson(text)
  if (repaired !== null) {
    try {
      return { plan: normalizePlan(JSON.parse(repaired)), complete: false }
    } catch {
      // 修复后仍不合法（如刚开始输出），忽略
    }
  }
  return { plan: null, complete: false }
}

/* ==================== Pinia store ==================== */

/** 各 agent 的中文名（用于时间线展示） */
export const AGENT_LABELS: Record<AgentType, string> = {
  coordinator: '协调者',
  planner: '规划师',
  researcher: '研究员',
  analyst: '分析师',
  coder: '程序员',
  reporter: '撰稿人',
}

export const useResearchStore = defineStore('research', () => {
  /* ---------- 状态 ---------- */
  const status = ref<ResearchStatus>('idle')
  const threadId = ref('')
  const topic = ref('')
  const autoAcceptedPlan = ref(false)

  const plan = ref<Plan | null>(null)
  /** planner 累积的原始文本（Plan JSON 增量） */
  const planRaw = ref('')
  /** plan JSON 是否已完整解析（流式期间为 false，用于 UI 展示"生成中"） */
  const planComplete = ref(false)
  /** 各计划步骤的执行状态（key 为步骤标题：pending → running → done） */
  const stepStatuses = ref<Record<string, 'pending' | 'running' | 'done'>>({})

  const timeline = ref<TimelineItem[]>([])
  /** reporter 的报告草稿（流式） */
  const reportDraft = ref('')
  const finalReport = ref('')
  const sources = ref<Source[]>([])
  const errorMessage = ref('')
  /** interrupt 后提交反馈（接受/修改意见）的请求进行中 */
  const submitting = ref(false)

  /* ---------- 非响应式内部状态 ---------- */
  let abortController: AbortController | null = null
  let timelineSeq = 0
  const seenSourceUrls = new Set<string>()

  /* ---------- 计算属性 ---------- */
  /** 是否处于需要展示"进行中"状态的阶段 */
  const busy = computed(() =>
    ['planning', 'awaiting_approval', 'researching', 'reporting'].includes(status.value),
  )
  /** 是否允许开始新研究 */
  const canStart = computed(() => status.value === 'idle' || status.value === 'done' || status.value === 'error')
  /** 当前应展示的报告（最终报告优先，其次流式草稿） */
  const displayReport = computed(() => finalReport.value || reportDraft.value)

  /* ---------- 内部工具 ---------- */

  /** 时间线新增条目（自动记录时间） */
  function pushTimeline(item: Omit<TimelineItem, 'id' | 'time'>): TimelineItem {
    const full: TimelineItem = {
      id: ++timelineSeq,
      time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      ...item,
    }
    timeline.value.push(full)
    return full
  }

  /**
   * 在"当前步骤区间"内从后向前查找条目（最后一个 step_result 之后的范围）。
   * 用于把工具调用分片 / 执行结果聚合到同一条目，且不受上一轮同名工具干扰。
   */
  function findInCurrentRound(predicate: (t: TimelineItem) => boolean): TimelineItem | null {
    for (let i = timeline.value.length - 1; i >= 0; i--) {
      const t = timeline.value[i]
      if (t.kind === 'step') break
      if (predicate(t)) return t
    }
    return null
  }

  /** 收到执行类事件时推进状态 */
  function markResearching(agent: AgentType) {
    if (agent === 'coordinator' || agent === 'planner' || agent === 'reporter') return
    if (status.value === 'planning' || status.value === 'awaiting_approval' || status.value === 'researching') {
      status.value = 'researching'
    }
    advanceStepToRunning()
  }

  /** 将步骤状态表与当前 plan 同步（新步骤置为 pending，保留已有状态，移除废弃标题） */
  function syncStepStatuses() {
    if (!plan.value) return
    const next: Record<string, 'pending' | 'running' | 'done'> = {}
    for (const s of plan.value.steps) {
      next[s.title] = stepStatuses.value[s.title] ?? 'pending'
    }
    stepStatuses.value = next
  }

  /** 研究活动开始时：若当前没有 running 步骤，则将第一个 pending 步骤置为 running */
  function advanceStepToRunning() {
    const statuses = stepStatuses.value
    const titles = Object.keys(statuses)
    if (!titles.length) return
    if (titles.some(t => statuses[t] === 'running')) return
    const firstPending = titles.find(t => statuses[t] === 'pending')
    if (firstPending) statuses[firstPending] = 'running'
  }

  /** 从工具结果文本中尽力提取引用来源（搜索/爬虫结果为 JSON 结构时） */
  function collectSources(content: string) {
    let data: unknown
    try {
      data = JSON.parse(content)
    } catch {
      return
    }
    const items = Array.isArray(data) ? data : [data]
    for (const item of items) {
      if (!item || typeof item !== 'object') continue
      const obj = item as Record<string, unknown>
      const url = typeof obj.url === 'string' ? obj.url : ''
      if (!url || seenSourceUrls.has(url)) continue
      const title =
        typeof obj.title === 'string' && obj.title.trim() ? obj.title.trim() : url
      const snippet = typeof obj.snippet === 'string' ? obj.snippet : undefined
      seenSourceUrls.add(url)
      sources.value.push({ url, title, snippet })
    }
  }

  /* ---------- SSE 事件处理 ---------- */

  function handleMessageChunk(agent: AgentType, content: string | null) {
    if (content === null) return
    if (agent === 'planner') {
      status.value = 'planning'
      planRaw.value += content
      // 边收边解析：完整则直接解析，不完整则修复截断后预览
      const parsed = parsePlanText(planRaw.value)
      if (parsed.plan) {
        plan.value = parsed.plan
        planComplete.value = parsed.complete
        syncStepStatuses()
      }
      return
    }
    if (agent === 'reporter') {
      status.value = 'reporting'
      reportDraft.value += content
      return
    }
    if (agent === 'coordinator') return // 路由信息不展示
    // researcher / analyst / coder 的思考文本：聚合同一 agent 的连续文本
    const existing = findInCurrentRound(t => t.kind === 'text' && t.agent === agent)
    if (existing) {
      existing.content = (existing.content ?? '') + content
    } else {
      pushTimeline({ kind: 'text', agent, content })
      markResearching(agent)
    }
  }

  function handleToolCalls(agent: AgentType, toolCalls: { name: string; args: string; id: string }[]) {
    markResearching(agent)
    for (const call of toolCalls) {
      pushTimeline({
        kind: 'tool',
        agent,
        toolName: call.name,
        args: call.args,
        toolCallId: call.id || undefined,
        status: 'running',
      })
    }
  }

  function handleToolCallChunk(agent: AgentType, chunk: ToolCallChunksEvent['tool_call_chunk']) {
    markResearching(agent)
    // 聚合 key：优先用调用 id，否则用 index 兜底
    const key = chunk.id || (chunk.index !== undefined ? `idx-${agent}-${chunk.index}` : '')
    if (!key) return
    const existing = findInCurrentRound(t => t.toolCallId === key)
    if (existing) {
      if (chunk.args) existing.args = (existing.args ?? '') + chunk.args
      if (chunk.name && !existing.toolName) existing.toolName = chunk.name
    } else {
      pushTimeline({
        kind: 'tool',
        agent,
        toolName: chunk.name ?? '',
        args: chunk.args ?? '',
        toolCallId: key,
        status: 'running',
      })
    }
  }

  function handleToolCallResult(e: ToolCallResultEvent) {
    markResearching(e.agent)
    // 优先回填当前区间内同名的进行中条目
    const existing = findInCurrentRound(
      t => t.kind === 'tool' && t.toolName === e.tool_name && t.status === 'running',
    )
    if (existing) {
      existing.resultContent = e.content
      existing.status = e.status
    } else {
      pushTimeline({
        kind: 'tool',
        agent: e.agent,
        toolName: e.tool_name,
        resultContent: e.content,
        status: e.status,
      })
    }
    // researcher 的工具结果里通常带搜索/网页来源
    if (e.agent === 'researcher' && e.status === 'success') {
      collectSources(e.content)
    }
  }

  function handleStepResult(agent: AgentType, stepTopic: string, content: string) {
    markResearching(agent)
    // 步骤完成：标记 done，并把下一个 pending 步骤提前置为 running
    if (stepTopic && stepStatuses.value[stepTopic] !== undefined) {
      stepStatuses.value[stepTopic] = 'done'
      advanceStepToRunning()
    }
    pushTimeline({ kind: 'step', agent, topic: stepTopic, content })
  }

  function handleInterrupt(e: InterruptEvent) {
    const parsed = parsePlanText(e.plan)
    if (!parsed.plan) {
      status.value = 'error'
      errorMessage.value = '研究计划解析失败，请重试'
      ElMessage.error(errorMessage.value)
      return
    }
    plan.value = parsed.plan
    planComplete.value = true
    planRaw.value = e.plan
    // 重新规划时标题可能变化：以最新 plan 为准重建步骤状态（保留已完成）
    const prevStatuses = { ...stepStatuses.value }
    const next: Record<string, 'pending' | 'running' | 'done'> = {}
    for (const s of parsed.plan.steps) {
      next[s.title] = prevStatuses[s.title] ?? 'pending'
    }
    stepStatuses.value = next
    status.value = 'awaiting_approval'
  }

  function handleError(threadError: string) {
    status.value = 'error'
    errorMessage.value = threadError || '研究服务返回错误'
    ElMessage.error(errorMessage.value)
  }

  function handleEnd(finalReportText: string) {
    if (finalReportText) finalReport.value = finalReportText
    // interrupt 后后端仍会发 end（final_report 为空）：保持 awaiting_approval，等用户确认
    // error 后的 end 同理，不覆盖错误状态
    if (status.value === 'awaiting_approval' || status.value === 'error') return
    status.value = 'done'
  }

  function handleClosed() {
    // 连接关闭时若仍处于流式中间态，视为异常中断（awaiting_approval / done 为正常关闭）
    if (status.value === 'planning' || status.value === 'researching' || status.value === 'reporting') {
      status.value = 'error'
      errorMessage.value = '连接已中断，请重试'
      ElMessage.warning(errorMessage.value)
    }
  }

  /* ---------- 请求发起 ---------- */

  /** 统一的 SSE 请求入口：注册事件回调并处理网络层错误 */
  async function send(body: ResearchRequestBody) {
    abortController = new AbortController()
    try {
      await streamResearch(
        body,
        {
          onStart: e => {
            threadId.value = e.thread_id
          },
          onMessageChunk: e => handleMessageChunk(e.agent, e.content),
          onToolCalls: e => handleToolCalls(e.agent, e.tool_calls),
          onToolCallChunks: e => handleToolCallChunk(e.agent, e.tool_call_chunk),
          onToolCallResult: e => handleToolCallResult(e),
          onStepResult: e => handleStepResult(e.agent, e.topic, e.content),
          onInterrupt: e => handleInterrupt(e),
          onErrorEvent: e => handleError(e.error),
          onEnd: e => handleEnd(e.final_report),
          onClosed: handleClosed,
        },
        abortController.signal,
      )
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      status.value = 'error'
      errorMessage.value = err instanceof Error ? err.message : '网络请求失败'
      ElMessage.error(errorMessage.value)
    } finally {
      abortController = null
    }
  }

  /** 开始一项新研究 */
  async function startResearch(newTopic: string) {
    const trimmed = newTopic.trim()
    if (!trimmed || !canStart.value) return
    // 重置上一轮状态
    reset()
    topic.value = trimmed
    status.value = 'planning'
    await send({
      messages: [{ role: 'user', content: trimmed }],
      auto_accepted_plan: autoAcceptedPlan.value,
      max_research_rounds: 1,
      max_step_num: 3,
      enable_background_investigation: true,
    })
  }

  /** interrupt 后：接受计划，继续研究 */
  async function acceptPlan() {
    if (status.value !== 'awaiting_approval' || !threadId.value) return
    submitting.value = true
    status.value = 'researching'
    try {
      await send({
        thread_id: threadId.value,
        auto_accepted_plan: false,
        max_research_rounds: 1,
        max_step_num: 3,
        enable_background_investigation: true,
        resume: { type: 'accepted' },
      })
    } finally {
      submitting.value = false
    }
  }

  /** interrupt 后：提交文本修改意见，planner 将重新规划 */
  async function submitFeedback(text: string) {
    const trimmed = text.trim()
    if (status.value !== 'awaiting_approval' || !threadId.value || !trimmed) return
    submitting.value = true
    // 重新规划：清空累积文本，保留旧 plan 展示直到新内容覆盖
    planRaw.value = ''
    planComplete.value = false
    status.value = 'planning'
    try {
      await send({
        thread_id: threadId.value,
        auto_accepted_plan: false,
        max_research_rounds: 1,
        max_step_num: 3,
        enable_background_investigation: true,
        resume: { type: 'feedback', content: trimmed },
      })
    } finally {
      submitting.value = false
    }
  }

  /** 中断当前研究 */
  function stopResearch() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    if (busy.value) {
      status.value = 'idle'
      ElMessage.info('已停止本次研究')
    }
  }

  /** 重置全部状态 */
  function reset() {
    status.value = 'idle'
    threadId.value = ''
    plan.value = null
    planRaw.value = ''
    planComplete.value = false
    stepStatuses.value = {}
    timeline.value = []
    reportDraft.value = ''
    finalReport.value = ''
    sources.value = []
    errorMessage.value = ''
    submitting.value = false
    seenSourceUrls.clear()
  }

  return {
    // 状态
    status,
    threadId,
    topic,
    autoAcceptedPlan,
    plan,
    planComplete,
    stepStatuses,
    timeline,
    reportDraft,
    finalReport,
    sources,
    errorMessage,
    submitting,
    // 计算属性
    busy,
    canStart,
    displayReport,
    // 动作
    startResearch,
    acceptPlan,
    submitFeedback,
    stopResearch,
    reset,
  }
})
