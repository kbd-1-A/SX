<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { NAlert, NButton, NInput, NLayout, NLayoutHeader, NLayoutFooter, NTag } from 'naive-ui'
import { useChatStore } from '../stores/chat'
import { renderAssistantMarkdown } from '../utils/chatMarkdown'
import RealtimeFoundationPanel from './RealtimeFoundationPanel.vue'

const chat = useChatStore()
const input = ref('')
const listRef = ref<HTMLDivElement | null>(null)
const isFollowingLatest = ref(true)

const FOLLOW_THRESHOLD = 80

function isNearBottom() {
  const list = listRef.value
  if (!list) return true
  return list.scrollHeight - list.scrollTop - list.clientHeight <= FOLLOW_THRESHOLD
}

function onListScroll() {
  isFollowingLatest.value = isNearBottom()
}

function scrollToLatest(behavior: ScrollBehavior = 'auto') {
  const list = listRef.value
  if (!list) return
  list.scrollTo({ top: list.scrollHeight, behavior })
}

watch(
  () => {
    const latest = chat.messages[chat.messages.length - 1]
    return [
      chat.currentSessionId,
      chat.messages.length,
      latest?.content,
      latest?.streaming,
      latest?.research?.status,
      latest?.research?.source_count,
    ] as const
  },
  async ([sessionId], [previousSessionId]) => {
    if (sessionId !== previousSessionId) isFollowingLatest.value = true
    await nextTick()
    if (isFollowingLatest.value) scrollToLatest()
  },
  { flush: 'post' },
)

async function onSend() {
  const text = input.value.trim()
  if (!text) return
  if (chat.send(text)) {
    input.value = ''
    isFollowingLatest.value = true
    await nextTick()
    scrollToLatest('smooth')
  }
}

const statusNames: Record<string, string> = {
  connecting: '连接中',
  online: '在线',
  reconnecting: '重连中',
  offline: '离线',
}

function formatFileSize(sizeBytes: number) {
  if (sizeBytes < 1024) return `${sizeBytes} B`
  return `${(sizeBytes / 1024).toFixed(1)} KB`
}

function sourceTypeLabel(sourceType: string) {
  if (sourceType === 'official') return '官方/一手'
  if (sourceType === 'organization') return '组织/研究'
  return '二手来源'
}
</script>

<template>
  <n-layout class="chat-window" content-class="chat-window__content">
    <n-layout-header bordered class="chat-header">
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px">
        <div style="display: flex; align-items: center; gap: 12px; min-width: 0">
          <h2 style="margin: 0; font-size: 18px; white-space: nowrap">时叙 · 你的陪伴 Agent</h2>
          <n-tag
            :type="chat.connected ? 'success' : chat.status === 'reconnecting' ? 'warning' : 'error'"
            size="small"
            :bordered="false"
          >
            {{ statusNames[chat.status] || '离线' }}
          </n-tag>
        </div>
        <RealtimeFoundationPanel />
      </div>
    </n-layout-header>

    <div ref="listRef" class="message-list" @scroll="onListScroll">
      <div
        style="
          padding: 24px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          max-width: 860px;
          margin: 0 auto;
        "
      >
        <div
          v-for="(m, i) in chat.messages"
          :key="i"
          :style="{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '70%',
          }"
        >
          <div
            v-if="m.content || m.streaming"
            class="message-bubble"
            :style="{
              padding: '10px 14px',
              borderRadius: '12px',
              background: m.role === 'user' ? '#2080f0' : '#f2f3f5',
              color: m.role === 'user' ? '#fff' : '#18181c',
              wordBreak: 'break-word',
            }"
          >
            <template v-if="m.role === 'user'">
              <span class="user-message">{{ m.content }}</span>
              <span v-if="m.streaming" class="streaming-cursor">▌</span>
            </template>
            <div
              v-else
              class="message-markdown"
              :class="{ 'message-markdown--streaming': m.streaming }"
              v-html="renderAssistantMarkdown(m.content)"
            />
          </div>
          <div v-if="m.research" class="research-card">
            <div class="research-card__header">
              <span class="research-card__title">联网研究</span>
              <n-tag
                :type="m.research.status === 'completed' ? 'success' : m.research.status === 'failed' ? 'warning' : 'info'"
                size="small"
                :bordered="false"
              >
                {{ m.research.status === 'completed' ? '来源已读取' : m.research.status === 'failed' ? '检索未完成' : '正在检索' }}
              </n-tag>
            </div>
            <div class="research-card__query">{{ m.research.query }}</div>
            <div v-if="m.research.status === 'running'" class="research-card__status">
              正在搜索公开资料并读取来源正文…
            </div>
            <div v-else-if="m.research.status === 'failed'" class="research-card__status research-card__status--failed">
              {{ m.research.message }} 已改为生成不含实时结论的研究框架。
            </div>
            <template v-else>
              <div class="research-card__status">
                {{ m.research.retrieved_at }} · {{ m.research.source_count || 0 }} 个来源
              </div>
              <div class="research-card__sources">
                <a
                  v-for="source in m.research.sources"
                  :key="source.citation_id"
                  class="research-card__source"
                  :href="source.url"
                  target="_blank"
                  rel="noreferrer"
                >
                  <span>[S{{ source.citation_id }}] {{ source.title }}</span>
                  <small>{{ source.domain }} · {{ sourceTypeLabel(source.source_type) }}</small>
                </a>
              </div>
              <div v-if="m.research.warnings?.length" class="research-card__warning">
                另有 {{ m.research.warnings.length }} 个来源因无法读取或正文不足被跳过。
              </div>
            </template>
          </div>
          <div v-for="artifact in m.artifacts" :key="artifact.id" class="artifact-card">
            <div class="artifact-card__header">
              <span class="artifact-card__name">{{ artifact.display_name }}</span>
              <n-tag type="success" size="small" :bordered="false">已创建并校验</n-tag>
            </div>
            <div class="artifact-card__path">{{ artifact.path }}</div>
            <div class="artifact-card__meta">
              <span>{{ formatFileSize(artifact.size_bytes) }}</span>
              <span>Markdown</span>
              <span>SHA-256 {{ artifact.sha256.slice(0, 12) }}...</span>
            </div>
          </div>
          <div v-if="m.artifactFailure" class="artifact-card artifact-card--failed">
            <div class="artifact-card__header">
              <span class="artifact-card__name">文件未创建</span>
              <n-tag type="error" size="small" :bordered="false">未完成</n-tag>
            </div>
            <div class="artifact-card__path">{{ m.artifactFailure.message }}</div>
          </div>
        </div>
      </div>
    </div>

    <n-layout-footer bordered class="chat-footer">
      <div style="max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 10px">
        <n-alert v-if="chat.lastError" type="warning" :show-icon="false">
          {{ chat.lastError }}
        </n-alert>
        <div style="display: flex; gap: 12px">
        <n-input
          v-model:value="input"
          placeholder="想说什么就说…"
          size="large"
          :maxlength="4000"
          :disabled="chat.isStreaming"
          @keydown.enter.prevent="onSend"
        />
          <n-button v-if="chat.isStreaming" size="large" @click="chat.stop">停止</n-button>
          <n-button type="primary" size="large" :disabled="chat.isStreaming" @click="onSend">发送</n-button>
        </div>
      </div>
    </n-layout-footer>
  </n-layout>
</template>

<style scoped>
.chat-window {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

:deep(.chat-window__content) {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.chat-header {
  flex: 0 0 auto;
  padding: 12px 24px;
}

.message-list {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.chat-footer {
  flex: 0 0 auto;
  padding: 16px 24px;
}

.user-message {
  white-space: pre-wrap;
}

.streaming-cursor,
.message-markdown--streaming::after {
  opacity: 0.6;
}

.message-markdown--streaming::after {
  content: '▌';
}

.message-markdown {
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.message-markdown :deep(p),
.message-markdown :deep(ul),
.message-markdown :deep(ol),
.message-markdown :deep(blockquote),
.message-markdown :deep(pre) {
  margin: 0 0 8px;
}

.message-markdown :deep(:last-child) {
  margin-bottom: 0;
}

.message-markdown :deep(ul),
.message-markdown :deep(ol) {
  padding-left: 22px;
}

.message-markdown :deep(code) {
  padding: 1px 4px;
  border-radius: 3px;
  background: #e5e7eb;
  font-family: Consolas, "Courier New", monospace;
  font-size: 0.92em;
}

.message-markdown :deep(pre) {
  overflow-x: auto;
  padding: 10px 12px;
  border-radius: 5px;
  background: #20252b;
  color: #f4f5f6;
  white-space: pre;
}

.message-markdown :deep(pre code) {
  padding: 0;
  background: transparent;
  color: inherit;
}

.message-markdown :deep(blockquote) {
  padding-left: 10px;
  border-left: 3px solid #c7cbd1;
  color: #5d6269;
}

.message-markdown :deep(a) {
  color: #1672c4;
}

.artifact-card {
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px solid #b7dfc4;
  border-radius: 6px;
  background: #f5fbf6;
  color: #203126;
}

.research-card {
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px solid #c7d3df;
  border-radius: 6px;
  background: #f7f9fb;
  color: #27323b;
}

.research-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.research-card__title {
  font-size: 14px;
  font-weight: 600;
}

.research-card__query {
  margin-top: 6px;
  overflow-wrap: anywhere;
  font-size: 13px;
}

.research-card__status {
  margin-top: 5px;
  color: #68757f;
  font-size: 12px;
  line-height: 1.45;
}

.research-card__status--failed {
  color: #845b24;
}

.research-card__sources {
  display: grid;
  gap: 5px;
  margin-top: 8px;
}

.research-card__source {
  display: grid;
  gap: 1px;
  overflow-wrap: anywhere;
  color: #246095;
  font-size: 12px;
  line-height: 1.4;
  text-decoration: none;
}

.research-card__source:hover {
  text-decoration: underline;
}

.research-card__source small {
  color: #74808a;
  font-size: 11px;
}

.research-card__warning {
  margin-top: 7px;
  color: #845b24;
  font-size: 11px;
  line-height: 1.4;
}

.artifact-card--failed {
  border-color: #f0b7b7;
  background: #fff7f7;
  color: #572222;
}

.artifact-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.artifact-card__name {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 14px;
  font-weight: 600;
}

.artifact-card__path {
  margin-top: 6px;
  overflow-wrap: anywhere;
  color: #536057;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  line-height: 1.45;
}

.artifact-card--failed .artifact-card__path {
  color: #7e3636;
  font-family: inherit;
}

.artifact-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 7px;
  color: #647068;
  font-size: 12px;
}
</style>
