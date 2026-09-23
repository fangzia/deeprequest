<template>
  <el-dialog
    v-model="visible"
    title="确认研究计划"
    width="680px"
    align-center
    :close-on-click-modal="false"
    class="plan-confirm-dialog"
  >
    <template #header>
      <div class="dialog-header">
        <span class="dialog-title">确认研究计划</span>
        <el-tag size="small" type="warning">等待人工确认</el-tag>
      </div>
    </template>

    <div v-if="plan" class="dialog-body">
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
      </div>

      <el-input
        v-model="feedback"
        type="textarea"
        :rows="3"
        maxlength="500"
        show-word-limit
        placeholder="修改意见（可选）：填写后规划师将按意见重新规划；留空请直接点击「接受计划」"
      />
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button type="primary" size="large" :loading="submitting" @click="emit('accept')">
          接受计划，开始研究
        </el-button>
        <el-button
          size="large"
          :disabled="!feedback.trim()"
          :loading="submitting"
          @click="emit('feedback', feedback.trim())"
        >
          提交修改意见
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Plan, StepType } from '../types'

/** 弹窗可见性（v-model:visible） */
const visible = defineModel<boolean>('visible', { default: false })

defineProps<{
  /** 待确认的研究计划 */
  plan: Plan | null
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

// 弹窗关闭（接受后进入研究）时清空上次的修改意见
watch(visible, v => {
  if (!v) feedback.value = ''
})
</script>

<style scoped>
.dialog-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dialog-title {
  font-size: 17px;
  font-weight: 600;
}

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plan-topic {
  margin: 0;
  font-size: 16px;
}

.plan-thought {
  margin: 0;
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
  gap: 10px;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
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
  font-size: 14px;
}

.plan-step-desc {
  margin: 8px 0 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
