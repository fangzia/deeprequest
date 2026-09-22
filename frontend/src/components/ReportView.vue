<template>
  <el-card class="report-card" shadow="never">
    <template #header>
      <div class="report-header">
        <span class="report-header-title">研究报告</span>
        <el-tag v-if="streaming" size="small" type="info" effect="plain">撰写中…</el-tag>
        <el-tag v-else size="small" type="success">已完成</el-tag>
      </div>
    </template>

    <!-- 报告正文（[n] 引用已替换为指向底部来源列表的锚点链接） -->
    <div class="report-content" v-html="html"></div>
    <p v-if="streaming" class="report-cursor">▍</p>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'

const props = defineProps<{
  /** 报告 markdown 文本（最终报告或流式草稿） */
  report: string
  /** 是否流式撰写中 */
  streaming?: boolean
}>()

const md = new MarkdownIt({ linkify: true, breaks: true })

/**
 * 将报告中的 [n] 引用替换为 markdown 链接（渲染为指向 #source-n 的锚点）。
 * 用 [[n]](#source-n) 形式让链接文本保留 "[n]" 字样；(?!\() 跳过已是链接的文本。
 */
function preprocess(src: string): string {
  return src.replace(/\[(\d{1,3})\](?!\()/g, (_m, n: string) => `[[${n}]](#source-${n})`)
}

const html = computed(() => md.render(preprocess(props.report)))
</script>

<style scoped>
.report-card {
  border-radius: 8px;
}

.report-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.report-header-title {
  font-weight: 600;
}

/* 引用角标样式 */
.report-content :deep(a[href^='#source-']) {
  color: #409eff;
  text-decoration: none;
  font-size: 0.75em;
  vertical-align: super;
  margin: 0 1px;
}

.report-content :deep(a[href^='#source-']:hover) {
  text-decoration: underline;
}

/* 外部链接 */
.report-content :deep(a[href^='http']) {
  color: #409eff;
  text-decoration: none;
}

.report-content :deep(a[href^='http']:hover) {
  text-decoration: underline;
}

/* markdown 排版 */
.report-content :deep(h1),
.report-content :deep(h2),
.report-content :deep(h3),
.report-content :deep(h4) {
  margin: 18px 0 10px;
  line-height: 1.4;
}

.report-content :deep(h1) {
  font-size: 22px;
}

.report-content :deep(h2) {
  font-size: 18px;
  padding-bottom: 6px;
  border-bottom: 1px solid #ebeef5;
}

.report-content :deep(h3) {
  font-size: 16px;
}

.report-content :deep(p) {
  margin: 0 0 12px;
  line-height: 1.8;
}

.report-content :deep(ul),
.report-content :deep(ol) {
  margin: 0 0 12px;
  padding-left: 22px;
}

.report-content :deep(li) {
  margin: 4px 0;
  line-height: 1.7;
}

.report-content :deep(blockquote) {
  margin: 0 0 12px;
  padding: 4px 14px;
  border-left: 4px solid #dcdfe6;
  color: #909399;
  background: #fafafa;
}

.report-content :deep(code) {
  padding: 1px 5px;
  border-radius: 3px;
  background: #f0f2f5;
  font-size: 13px;
  font-family: Consolas, Monaco, 'Courier New', monospace;
}

.report-content :deep(pre) {
  margin: 0 0 12px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
  overflow-x: auto;
}

.report-content :deep(pre code) {
  padding: 0;
  background: none;
}

.report-content :deep(table) {
  width: 100%;
  margin: 0 0 12px;
  border-collapse: collapse;
}

.report-content :deep(th),
.report-content :deep(td) {
  padding: 8px 10px;
  border: 1px solid #ebeef5;
  text-align: left;
  line-height: 1.6;
}

.report-content :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
}

.report-content :deep(hr) {
  margin: 16px 0;
  border: none;
  border-top: 1px solid #ebeef5;
}

.report-content :deep(img) {
  max-width: 100%;
}

/* 流式撰写中的光标动画 */
.report-cursor {
  margin: 0;
  color: #409eff;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
