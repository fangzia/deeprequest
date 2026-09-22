<template>
  <el-card class="source-card" shadow="never">
    <template #header>
      <div class="source-header">
        <span class="source-header-title">引用来源</span>
        <span class="source-header-count">共 {{ sources.length }} 条</span>
      </div>
    </template>

    <ol class="source-items">
      <li
        v-for="(source, i) in sources"
        :id="`source-${i + 1}`"
        :key="source.url"
        class="source-item"
      >
        <div class="source-line">
          <span class="source-index">[{{ i + 1 }}]</span>
          <a
            :href="source.url"
            target="_blank"
            rel="noopener noreferrer"
            class="source-link"
            :title="source.url"
          >
            {{ source.title }}
          </a>
        </div>
        <p v-if="source.snippet" class="source-snippet">{{ source.snippet }}</p>
      </li>
    </ol>
  </el-card>
</template>

<script setup lang="ts">
import type { Source } from '../types'

defineProps<{
  /** 引用来源列表（报告 [n] 引用的跳转目标，锚点为 #source-n） */
  sources: Source[]
}>()
</script>

<style scoped>
.source-card {
  border-radius: 8px;
}

.source-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.source-header-title {
  font-weight: 600;
}

.source-header-count {
  font-size: 12px;
  color: #909399;
}

.source-items {
  margin: 0;
  padding: 0;
  list-style: none;
}

.source-item {
  padding: 10px 8px;
  border-bottom: 1px dashed #ebeef5;
  /* 锚点跳转时留出头部空间 */
  scroll-margin-top: 80px;
}

.source-item:last-child {
  border-bottom: none;
}

.source-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.source-index {
  flex-shrink: 0;
  color: #409eff;
  font-size: 13px;
  font-weight: 600;
}

.source-link {
  color: #303133;
  font-size: 14px;
  text-decoration: none;
  word-break: break-all;
}

.source-link:hover {
  color: #409eff;
  text-decoration: underline;
}

.source-snippet {
  margin: 6px 0 0 24px;
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}
</style>
