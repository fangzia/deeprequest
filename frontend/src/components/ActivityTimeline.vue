<template>
  <el-card class="timeline-card" shadow="never">
    <template #header>
      <div class="timeline-header">
        <span class="timeline-header-title">研究过程</span>
        <span class="timeline-header-stats">{{ statsText }}</span>
      </div>
    </template>

    <!-- 顶部实时动态：当前正在执行的操作 -->
    <div v-if="latestActivity" class="live-bar">
      <span class="live-dot"></span>
      <span class="live-text">{{ latestActivity }}</span>
    </div>

    <div ref="scrollRef" class="timeline-scroll">
      <el-timeline v-if="items.length" class="activity-timeline">
        <el-timeline-item
          v-for="item in items"
          :key="item.id"
          :type="dotType(item)"
          :timestamp="item.time"
          placement="top"
        >
          <!-- 工具调用：友好名称 + 参数摘要，可展开查看参数与原始结果 -->
          <div v-if="item.kind === 'tool'" class="tl-item">
            <div class="tl-head clickable" @click="toggle(item.id)">
              <span class="tool-icon" :class="item.status">{{ toolMeta(item).icon }}</span>
              <span class="tool-name">{{ toolMeta(item).label }}</span>
              <span v-if="argSummary(item)" class="tool-arg">{{ argSummary(item) }}</span>
              <el-tag size="small" type="info" effect="plain">{{ agentLabel(item.agent) }}</el-tag>
              <span v-if="item.status === 'running'" class="tool-running">执行中…</span>
              <el-tag v-else-if="item.status === 'error'" size="small" type="danger">失败</el-tag>
              <el-tag v-else size="small" type="success">完成</el-tag>
              <span class="expand-hint">{{ expanded.includes(item.id) ? '收起' : '详情' }}</span>
            </div>
            <p v-if="resultSummary(item)" class="tool-result-summary" :class="{ 'is-error': item.status === 'error' }">
              {{ resultSummary(item) }}
            </p>
            <div v-show="expanded.includes(item.id)" class="tl-body">
              <pre v-if="item.args" class="tool-block"><span class="block-label">参数</span>{{ prettyJson(item.args) }}</pre>
              <pre v-if="item.resultContent" class="tool-block" :class="{ 'is-error': item.status === 'error' }"><span class="block-label">结果</span>{{ brief(prettyJson(item.resultContent)) }}</pre>
            </div>
          </div>

          <!-- 步骤结果：agent 标签 + 步骤标题 + 可折叠内容 -->
          <div v-else-if="item.kind === 'step'" class="tl-item">
            <div class="tl-head clickable" @click="toggle(item.id)">
              <span class="step-badge">✓ 步骤完成</span>
              <span class="step-topic">{{ item.topic }}</span>
              <el-tag size="small" type="info" effect="plain">{{ agentLabel(item.agent) }}</el-tag>
              <span class="expand-hint">{{ expanded.includes(item.id) ? '收起' : '查看结论' }}</span>
            </div>
            <p class="step-brief">{{ plainBrief(item.content) }}</p>
            <div v-show="expanded.includes(item.id)" class="tl-body">
              <div class="step-content" v-html="renderMarkdown(item.content)"></div>
            </div>
          </div>

          <!-- 智能体思考文本：默认两行截断，点击展开 -->
          <div v-else class="tl-item">
            <div class="tl-head clickable" @click="toggle(item.id)">
              <el-tag size="small" type="info" effect="plain">{{ agentLabel(item.agent) }}</el-tag>
              <span class="thinking-label">思考</span>
              <span class="expand-hint">{{ expanded.includes(item.id) ? '收起' : '展开' }}</span>
            </div>
            <p class="thinking-text" :class="{ expanded: expanded.includes(item.id) }">{{ item.content }}</p>
          </div>
        </el-timeline-item>
      </el-timeline>
      <p v-else class="timeline-empty">研究尚未开始，暂无过程记录。</p>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { AGENT_LABELS } from '../stores/research'
import type { AgentType, TimelineItem } from '../types'

const props = defineProps<{
  /** 时间线条目（由 store 维护） */
  items: TimelineItem[]
}>()

/** 步骤内容按 markdown 渲染 */
const md = new MarkdownIt({ linkify: true, breaks: true })

/** 当前展开的条目 id 列表 */
const expanded = ref<number[]>([])

/** 滚动容器（自动跟随最新条目） */
const scrollRef = ref<HTMLElement | null>(null)

/** 最新的步骤结果条目 id（用于自动展开） */
const latestStepId = computed(() => {
  for (let i = props.items.length - 1; i >= 0; i--) {
    if (props.items[i].kind === 'step') return props.items[i].id
  }
  return null
})

// 新步骤完成时自动展开
watch(
  latestStepId,
  id => {
    if (id !== null && !expanded.value.includes(id)) expanded.value.push(id)
  },
  { immediate: true },
)

// 新条目到达时自动滚动到底部（若用户没有向上翻阅）
watch(
  () => props.items.length,
  async () => {
    const el = scrollRef.value
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
    if (nearBottom) {
      await nextTick()
      el.scrollTop = el.scrollHeight
    }
  },
)

/** 顶部实时动态文案：取最后一条活动 */
const latestActivity = computed(() => {
  if (!props.items.length) return ''
  const last = props.items[props.items.length - 1]
  const agent = agentLabel(last.agent)
  if (last.kind === 'tool') {
    const label = toolMeta(last).label
    if (last.status === 'running') return `${agent}正在${label}（${argSummary(last) || '…'}）`
    return `${agent}${label}完成`
  }
  if (last.kind === 'step') return `步骤「${last.topic}」已完成`
  return `${agent}正在思考…`
})

/** 头部统计文案 */
const statsText = computed(() => {
  const tools = props.items.filter(t => t.kind === 'tool')
  const searches = tools.filter(t => t.toolName === 'web_search').length
  const reads = tools.filter(t => t.toolName === 'crawl_tool').length
  const parts = [`共 ${props.items.length} 条记录`]
  if (searches) parts.push(`搜索 ${searches} 次`)
  if (reads) parts.push(`阅读网页 ${reads} 篇`)
  return parts.join(' · ')
})

/* ---------- 工具的友好展示 ---------- */

const TOOL_META: Record<string, { label: string; icon: string }> = {
  web_search: { label: '联网搜索', icon: '🔍' },
  crawl_tool: { label: '阅读网页', icon: '📄' },
  python_repl_tool: { label: '执行代码', icon: '💻' },
}

function toolMeta(item: TimelineItem): { label: string; icon: string } {
  return TOOL_META[item.toolName ?? ''] ?? { label: item.toolName || '工具调用', icon: '🛠' }
}

/** 解析工具参数 JSON（流式期间可能不完整） */
function parseArgs(item: TimelineItem): Record<string, unknown> {
  try {
    const parsed = JSON.parse(item.args || '{}')
    return typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

/** 工具入参的一行摘要：搜索词 / URL / 代码首行 */
function argSummary(item: TimelineItem): string {
  const args = parseArgs(item)
  switch (item.toolName) {
    case 'web_search': {
      const q = args.query ?? args.q
      return typeof q === 'string' ? q : ''
    }
    case 'crawl_tool': {
      const url = args.url
      if (typeof url !== 'string') return ''
      return url.replace(/^https?:\/\//, '').replace(/\/$/, '')
    }
    case 'python_repl_tool': {
      const code = args.code
      if (typeof code !== 'string') return ''
      const firstLine = code.split('\n').find(l => l.trim()) ?? ''
      return firstLine.length > 60 ? `${firstLine.slice(0, 60)}…` : firstLine
    }
    default: {
      const values = Object.values(args).filter(v => typeof v === 'string') as string[]
      const joined = values.join(' ')
      return joined.length > 80 ? `${joined.slice(0, 80)}…` : joined
    }
  }
}

/** 工具结果的一行摘要（不展开也能看懂进展） */
function resultSummary(item: TimelineItem): string {
  if (item.status === 'running' || !item.resultContent) return ''
  if (item.status === 'error') return briefText(item.resultContent, 120)
  switch (item.toolName) {
    case 'web_search': {
      try {
        const data = JSON.parse(item.resultContent)
        const arr = Array.isArray(data) ? data : []
        if (arr.length) {
          const titles = arr
            .map(r => (r && typeof r === 'object' && typeof (r as Record<string, unknown>).title === 'string' ? (r as Record<string, unknown>).title as string : ''))
            .filter(Boolean)
            .slice(0, 2)
          return `找到 ${arr.length} 条结果${titles.length ? `：${titles.join('；')}` : ''}`
        }
      } catch {
        // 非结构化结果，走通用摘要
      }
      return briefText(item.resultContent, 120)
    }
    case 'crawl_tool': {
      if (/^error/i.test(item.resultContent)) return briefText(item.resultContent, 120)
      return `已抓取 ${item.resultContent.length.toLocaleString()} 字符`
    }
    default:
      return briefText(item.resultContent, 120)
  }
}

/* ---------- 通用 ---------- */

function toggle(id: number) {
  const idx = expanded.value.indexOf(id)
  if (idx === -1) expanded.value.push(id)
  else expanded.value.splice(idx, 1)
}

function agentLabel(agent: AgentType): string {
  return AGENT_LABELS[agent] ?? agent
}

/** 时间轴圆点颜色 */
function dotType(item: TimelineItem): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (item.kind === 'step') return 'warning'
  if (item.kind === 'text') return 'info'
  if (item.status === 'error') return 'danger'
  if (item.status === 'success') return 'success'
  return 'primary'
}

/** JSON 美化：工具参数/结果可能是 JSON 字符串（流式期间可能不完整），解析失败则原样展示 */
function prettyJson(text?: string): string {
  if (!text) return ''
  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch {
    return text
  }
}

/** 过长内容截断展示 */
function brief(text: string, limit = 800): string {
  return text.length > limit ? `${text.slice(0, limit)}\n…（内容过长，已截断）` : text
}

/** 去掉 markdown 标记后的一行纯文本摘要 */
function plainBrief(src?: string, limit = 100): string {
  if (!src) return ''
  const text = src
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*_`~\[\]()!-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

function briefText(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

function renderMarkdown(src?: string): string {
  return md.render(src ?? '')
}
</script>

<style scoped>
.timeline-card {
  border-radius: 8px;
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.timeline-header-title {
  font-weight: 600;
}

.timeline-header-stats {
  font-size: 12px;
  color: #909399;
}

/* 顶部实时动态 */
.live-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #ecf5ff;
  color: #409eff;
  font-size: 13px;
}

.live-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #409eff;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  50% {
    opacity: 0.25;
  }
}

.live-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 滚动容器：过程较长时保持固定高度，自动跟随最新活动 */
.timeline-scroll {
  max-height: 520px;
  overflow-y: auto;
  padding-right: 4px;
}

.timeline-empty {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.tl-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-height: 24px;
}

.tl-head.clickable {
  cursor: pointer;
  user-select: none;
}

.tl-head.clickable:hover .step-topic,
.tl-head.clickable:hover .tool-name {
  color: #409eff;
}

.tool-icon {
  flex-shrink: 0;
  font-size: 14px;
  line-height: 1;
}

.tool-icon.running {
  animation: spin 1.6s linear infinite;
}

@keyframes spin {
  100% {
    transform: rotate(360deg);
  }
}

.tool-name {
  font-weight: 600;
  font-size: 14px;
}

.tool-arg {
  color: #606266;
  font-size: 13px;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-running {
  font-size: 12px;
  color: #409eff;
}

/* 工具结果摘要行 */
.tool-result-summary {
  margin: 6px 0 0;
  font-size: 12px;
  color: #67c23a;
  line-height: 1.5;
}

.tool-result-summary.is-error {
  color: #f56c6c;
}

.step-badge {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: 4px;
  background: #e6a23c;
  color: #fff;
  font-size: 12px;
}

.step-topic {
  font-weight: 600;
  font-size: 14px;
}

.step-brief {
  margin: 4px 0 0;
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.expand-hint {
  margin-left: auto;
  font-size: 12px;
  color: #c0c4cc;
}

.thinking-label {
  font-size: 12px;
  color: #c0c4cc;
}

.thinking-text {
  margin: 6px 0 0;
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.thinking-text.expanded {
  display: block;
  -webkit-line-clamp: unset;
  overflow: visible;
}

.tl-body {
  margin-top: 8px;
}

.tool-block {
  margin: 0 0 8px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: #606266;
  max-height: 320px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.tool-block.is-error {
  background: #fef0f0;
  color: #f56c6c;
}

.block-label {
  display: inline-block;
  margin-right: 8px;
  padding: 0 6px;
  border-radius: 3px;
  background: #dcdfe6;
  color: #606266;
  font-weight: 600;
}

/* 步骤内容的 markdown 排版 */
.step-content :deep(p) {
  margin: 0 0 8px;
  line-height: 1.7;
}

.step-content :deep(p:last-child) {
  margin-bottom: 0;
}

.step-content :deep(ul),
.step-content :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}

.step-content :deep(code) {
  padding: 1px 4px;
  border-radius: 3px;
  background: #f0f2f5;
  font-size: 12px;
}

.step-content :deep(pre) {
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  overflow-x: auto;
}

.step-content :deep(a) {
  color: #409eff;
  text-decoration: none;
}
</style>
