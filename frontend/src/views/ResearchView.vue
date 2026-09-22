<template>
  <div class="research-view">
    <!-- 输入区：主题 + 开始/停止 + 自动接受计划开关 -->
    <div class="input-panel">
      <el-input
        v-model="topicInput"
        size="large"
        :disabled="busy"
        placeholder="输入研究主题，例如：2025 年大模型智能体的发展趋势"
        clearable
        @keyup.enter="onStart"
      />
      <el-button size="large" type="primary" :disabled="!canSubmit" @click="onStart">
        开始研究
      </el-button>
      <el-button v-if="busy" size="large" @click="onStop">停止</el-button>
      <el-tooltip content="开启后跳过计划确认环节，自动按计划开始研究" placement="bottom">
        <el-switch v-model="autoAcceptedPlan" :disabled="busy" active-text="自动接受计划" />
      </el-tooltip>
    </div>

    <!-- 状态条 -->
    <div v-if="status !== 'idle'" class="status-bar">
      <el-tag :type="statusTagType" effect="light">{{ statusText }}</el-tag>
      <span v-if="topic" class="status-topic">主题：{{ topic }}</span>
    </div>

    <!-- 错误提示 -->
    <el-alert
      v-if="status === 'error'"
      class="error-alert"
      type="error"
      :title="errorMessage || '研究过程中出现错误'"
      description="请确认后端服务已启动，调整主题后可重新开始研究。"
      show-icon
      :closable="false"
    />

    <!-- 过程区：研究计划 + 研究过程时间线 -->
    <div v-if="showPlan || timeline.length" class="process-section">
      <PlanCard
        v-if="showPlan"
        :plan="plan"
        :plan-complete="planComplete"
        :awaiting-approval="status === 'awaiting_approval'"
        :submitting="submitting"
        @accept="onAccept"
        @feedback="onFeedback"
      />
      <ActivityTimeline v-if="timeline.length" class="timeline-block" :items="timeline" />
    </div>

    <!-- 报告区：最终报告 + 引用来源 -->
    <div v-if="displayReport" class="report-section">
      <ReportView :report="displayReport" :streaming="status === 'reporting'" />
      <SourceList v-if="sources.length" :sources="sources" />
    </div>

    <!-- 空状态引导 -->
    <div v-if="status === 'idle' && !displayReport && !timeline.length" class="empty-hint">
      <h2 class="empty-title">多智能体深度研究</h2>
      <p class="empty-desc">输入一个主题，系统将自动完成「规划 → 研究 → 分析 → 成稿」全流程。</p>
      <p class="empty-desc">默认需要你确认研究计划后才正式开始（human-in-the-loop），也可开启自动接受。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useResearchStore } from '../stores/research'
import PlanCard from '../components/PlanCard.vue'
import ActivityTimeline from '../components/ActivityTimeline.vue'
import ReportView from '../components/ReportView.vue'
import SourceList from '../components/SourceList.vue'
import type { ResearchStatus } from '../types'

const store = useResearchStore()
const {
  status,
  topic,
  autoAcceptedPlan,
  plan,
  planComplete,
  timeline,
  sources,
  errorMessage,
  submitting,
  busy,
  displayReport,
} = storeToRefs(store)

/** 主题输入框内容 */
const topicInput = ref('')

/** 各状态对应的中文文案 */
const STATUS_TEXT: Record<ResearchStatus, string> = {
  idle: '空闲',
  planning: '正在规划研究方案…',
  awaiting_approval: '等待确认研究计划',
  researching: '正在研究中…',
  reporting: '正在撰写报告…',
  done: '研究完成',
  error: '出现错误',
}

const statusText = computed(() => STATUS_TEXT[status.value])

/** 状态条标签颜色 */
const statusTagType = computed(() => {
  switch (status.value) {
    case 'awaiting_approval':
      return 'warning' as const
    case 'done':
      return 'success' as const
    case 'error':
      return 'danger' as const
    default:
      return 'primary' as const
  }
})

/** 是否可提交新研究 */
const canSubmit = computed(() => !busy.value && topicInput.value.trim().length > 0)

/** 是否展示计划卡片（规划中或已有计划） */
const showPlan = computed(() => plan.value !== null || status.value === 'planning')

function onStart() {
  if (!canSubmit.value) return
  store.startResearch(topicInput.value)
}

function onStop() {
  store.stopResearch()
}

function onAccept() {
  store.acceptPlan()
}

function onFeedback(content: string) {
  store.submitFeedback(content)
}
</script>

<style scoped>
.research-view {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 20px 48px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 输入区 */
.input-panel {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  background: #fff;
  padding: 16px;
  border-radius: 10px;
  border: 1px solid #e4e7ed;
}

.input-panel .el-input {
  flex: 1;
  min-width: 320px;
}

/* 状态条 */
.status-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-topic {
  color: #909399;
  font-size: 13px;
}

.error-alert {
  border-radius: 8px;
}

/* 过程区 */
.process-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 报告区 */
.report-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 空状态引导 */
.empty-hint {
  margin-top: 10vh;
  text-align: center;
  color: #909399;
}

.empty-title {
  margin: 0 0 12px;
  font-size: 26px;
  font-weight: 600;
  background: linear-gradient(74deg, #409eff 0%, #9b72cb 35%, #d96570 56%, #409eff 100%);
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.empty-desc {
  margin: 6px 0;
  font-size: 14px;
  line-height: 1.8;
}
</style>
