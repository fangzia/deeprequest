<template>
  <el-card class="timeline-card" shadow="never">
    <template #header>
      <div class="timeline-header">
        <span class="timeline-header-title">研究过程</span>
        <span class="timeline-header-count">共 {{ items.length }} 条记录</span>
      </div>
    </template>

    <el-timeline v-if="items.length" class="activity-timeline">
      <el-timeline-item
        v-for="item in items"
        :key="item.id"
        :type="dotType(item)"
        :timestamp="item.time"
        placement="top"
      >
        <!-- 工具调用：图标 + 工具名 + 状态，可展开查看参数与结果 -->
        <div v-if="item.kind === 'tool'" class="tl-item">
          <div class="tl-head clickable" @click="toggle(item.id)">
            <svg class="tool-icon" :class="item.status" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M14.7 6.3a4.5 4.5 0 0 0-6.03 5.36L3.7 16.63a2 2 0 1 0 2.83 2.83l4.97-4.97a4.5 4.5 0 0 0 5.36-6.03l-2.4 2.4-2.83-2.83 2.4-2.4z"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <span class="tool-name">{{ item.toolName || '工具调用' }}</span>
            <el-tag size="small" type="info" effect="plain">{{ agentLabel(item.agent) }}</el-tag>
            <span v-if="item.status === 'running'" class="tool-running">执行中…</span>
            <el-tag v-else-if="item.status === 'error'" size="small" type="danger">失败</el-tag>
            <el-tag v-else size="small" type="success">完成</el-tag>
            <span class="expand-hint">{{ expanded.includes(item.id) ? '收起' : '展开' }}</span>
          </div>
          <div v-show="expanded.includes(item.id)" class="tl-body">
            <pre v-if="item.args" class="tool-block"><span class="block-label">参数</span>{{ prettyJson(item.args) }}</pre>
            <pre v-if="item.resultContent" class="tool-block" :class="{ 'is-error': item.status === 'error' }"><span class="block-label">结果</span>{{ brief(prettyJson(item.resultContent)) }}</pre>
          </div>
        </div>

        <!-- 步骤结果：agent 标签 + 步骤标题 + 可折叠内容 -->
        <div v-else-if="item.kind === 'step'" class="tl-item">
          <div class="tl-head clickable" @click="toggle(item.id)">
            <span class="step-badge">步骤</span>
            <span class="step-topic">{{ item.topic }}</span>
            <el-tag size="small" type="info" effect="plain">{{ agentLabel(item.agent) }}</el-tag>
            <span class="expand-hint">{{ expanded.includes(item.id) ? '收起' : '展开' }}</span>
          </div>
          <div v-show="expanded.includes(item.id)" class="tl-body">
            <div class="step-content" v-html="renderMarkdown(item.content)"></div>
          </div>
        </div>

        <!-- 智能体思考文本 -->
        <div v-else class="tl-item">
          <div class="tl-head">
            <el-tag size="small" type="info" effect="plain">{{ agentLabel(item.agent) }}</el-tag>
            <span class="thinking-label">思考</span>
          </div>
          <p class="thinking-text">{{ item.content }}</p>
        </div>
      </el-timeline-item>
    </el-timeline>
    <p v-else class="timeline-empty">研究尚未开始，暂无过程记录。</p>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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

.timeline-header-count {
  font-size: 12px;
  color: #909399;
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
  width: 16px;
  height: 16px;
  color: #909399;
  flex-shrink: 0;
}

.tool-icon.running {
  color: #409eff;
}

.tool-icon.success {
  color: #67c23a;
}

.tool-icon.error {
  color: #f56c6c;
}

.tool-name {
  font-weight: 600;
  font-size: 14px;
}

.tool-running {
  font-size: 12px;
  color: #409eff;
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
