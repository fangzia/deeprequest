<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-header-inner">
        <h1 class="app-title">DeepQuest 深度研究</h1>
        <span class="app-subtitle">多智能体 · 规划 - 研究 - 分析 - 成稿</span>
      </div>
    </header>
    <main class="app-main">
      <ResearchView />
    </main>
  </div>
</template>

<script setup lang="ts">
import ResearchView from './views/ResearchView.vue'
</script>

<style>
/* 全局基础样式 */
html,
body,
#app {
  height: 100%;
  margin: 0;
}

body {
  font-family:
    'Helvetica Neue',
    Helvetica,
    'PingFang SC',
    'Hiragino Sans GB',
    'Microsoft YaHei',
    Arial,
    sans-serif;
  background-color: #f5f7fa;
  color: #303133;
}

.app-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.app-header {
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}

.app-header-inner {
  max-width: 1000px;
  margin: 0 auto;
  padding: 14px 20px;
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.app-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.app-subtitle {
  font-size: 13px;
  color: #909399;
}

.app-main {
  flex: 1;
  overflow-y: auto;
}
</style>
