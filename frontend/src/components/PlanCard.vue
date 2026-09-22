<template>
  <el-card class="plan-card" shadow="never">
    <template #header>
      <div class="plan-header">
        <span class="plan-header-title">研究计划</span>
        <el-tag v-if="!planComplete" size="small" type="info" effect="plain">生成中…</el-tag>
        <el-tag v-else-if="awaitingApproval" size="small" type="warning">待确认</el-tag>
        <el-tag v-else size="small" type="success">已确认</el-tag>
      </div>
    </template>

    <template v-if="plan">
      <h3 class="plan-topic">{{ plan.title || '（未命名研究主题）' }}</h3>
      <p v-if="plan.thought" class="plan-thought">{{ plan.thought }}</p>

      <div class="plan-steps">
        <div v-for="(step, i) in plan.steps" :key="i" class="plan-step">
          <div class="plan-step-head">
            <span class="plan-step-index">{{ i + 1 }}</span>
            <span class="plan-step-title">{{ step.title }}</span>
            <el-tag size="small" :type="STEP_TAG[step.step_type]" effect="light">
              {{ STEP_LABEL[step.step_type] }}
            </el-tag>
            <el-tag v-if="step.need_search" size="small" type="info" effect="plain">联网搜索</el-tag>
          </div>
          <p class="plan-step-desc">{{ step.description }}</p>
        </div>
        <p v-if="!plan.steps.length" class="plan-steps-empty">（步骤生成中…）</p>
      </div>
    </template>
    <p v-else class="plan-loading">正在生成研究计划…</p>

    <!-- 确认区：仅在等待人工确认时展示 -->
    <div v-if="awaitingApproval" class="plan-actions">
      <el-input
        v-model="feedback"
        type="textarea"
        :rows="2"
        maxlength="500"
        show-word-limit
        placeholder="修改意见（可选）：填写后规划师将按意见重新规划；留空请直接点击「接受计划」"
      />
      <div class="plan-action-buttons">
        <el-button type="primary" :loading="submitting" @click="emit('accept')">接受计划</el-button>
        <el-button
          :disabled="!feedback.trim()"
          :loading="submitting"
          @click="emit('feedback', feedback.trim())"
        >
          提交修改意见
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { Plan, StepType } from '../types'

defineProps<{
  /** 当前解析出的研究计划（流式期间可能为 null 或不完整） */
  plan: Plan | null
  /** plan JSON 是否已完整接收（流式期间 false，展示"生成中"） */
  planComplete: boolean
  /** 是否处于"等待确认"状态（展示操作按钮） */
  awaitingApproval: boolean
  /** 续传（接受/反馈）请求进行中 */
  submitting: boolean
}>()

const emit = defineEmits<{
  accept: []
  feedback: [content: string]
}>()

/** 步骤类型的中文标签 */
const STEP_LABEL: Record<StepType, string> = {
  research: '调研',
  analysis: '分析',
  processing: '处理',
}

/** 步骤类型对应的标签颜色 */
const STEP_TAG: Record<StepType, 'primary' | 'warning' | 'info'> = {
  research: 'primary',
  analysis: 'warning',
  processing: 'info',
}

/** 修改意见输入框 */
const feedback = ref('')
</script>

<style scoped>
.plan-card {
  border-radius: 8px;
}

.plan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.plan-header-title {
  font-weight: 600;
}

.plan-topic {
  margin: 0 0 8px;
  font-size: 17px;
}

.plan-thought {
  margin: 0 0 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}

.plan-steps {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plan-step {
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.plan-step-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.plan-step-index {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.plan-step-title {
  font-weight: 600;
}

.plan-step-desc {
  margin: 8px 0 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}

.plan-steps-empty {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.plan-loading {
  margin: 0;
  color: #909399;
}

.plan-actions {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed #dcdfe6;
}

.plan-action-buttons {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
