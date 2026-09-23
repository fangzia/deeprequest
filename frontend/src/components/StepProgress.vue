<template>
  <el-card class="step-progress-card" shadow="never">
    <template #header>
      <div class="progress-header">
        <span class="progress-title">研究进度</span>
        <span class="progress-summary">{{ summaryText }}</span>
      </div>
    </template>

    <el-steps
      v-if="steps.length"
      :active="activeIndex"
      finish-status="success"
      align-center
      class="progress-steps"
    >
      <el-step
        v-for="(step, i) in steps"
        :key="i"
        :title="step.title"
        :description="STEP_LABEL[step.step_type]"
      />
    </el-steps>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PlanStep, StepType } from '../types'

const props = defineProps<{
  /** 研究计划的步骤列表 */
  steps: PlanStep[]
  /** 各步骤执行状态（key 为步骤标题） */
  stepStatuses: Record<string, 'pending' | 'running' | 'done'>
}>()

/** 步骤类型的中文标签 */
const STEP_LABEL: Record<StepType, string> = {
  research: '调研',
  analysis: '分析',
  processing: '处理',
}

/** el-steps 的 active 游标：优先取 running 步骤下标，否则为已完成数量 */
const activeIndex = computed(() => {
  const idx = props.steps.findIndex(s => props.stepStatuses[s.title] === 'running')
  if (idx !== -1) return idx
  return props.steps.filter(s => props.stepStatuses[s.title] === 'done').length
})

const summaryText = computed(() => {
  const done = props.steps.filter(s => props.stepStatuses[s.title] === 'done').length
  const total = props.steps.length
  if (done >= total) return `全部 ${total} 个步骤已完成`
  const running = props.steps.find(s => props.stepStatuses[s.title] === 'running')
  return running ? `正在执行第 ${props.steps.indexOf(running) + 1}/${total} 步：${running.title}` : `已完成 ${done}/${total} 个步骤`
})
</script>

<style scoped>
.step-progress-card {
  border-radius: 8px;
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.progress-title {
  font-weight: 600;
}

.progress-summary {
  font-size: 13px;
  color: #606266;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-steps :deep(.el-step__title) {
  font-size: 13px;
  line-height: 1.4;
}

.progress-steps :deep(.el-step__description) {
  font-size: 12px;
}
</style>
