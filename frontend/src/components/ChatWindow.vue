<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { NAlert, NButton, NInput, NLayout, NLayoutHeader, NLayoutFooter, NTag } from 'naive-ui'
import { useChatStore } from '../stores/chat'
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
    return [chat.currentSessionId, chat.messages.length, latest?.content, latest?.streaming] as const
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
            :style="{
              padding: '10px 14px',
              borderRadius: '12px',
              background: m.role === 'user' ? '#2080f0' : '#f2f3f5',
              color: m.role === 'user' ? '#fff' : '#18181c',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }"
          >
            {{ m.content }}<span v-if="m.streaming" style="opacity: 0.6">▌</span>
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
</style>
