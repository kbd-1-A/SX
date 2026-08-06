<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { NButton, NInput, NLayout, NLayoutHeader, NLayoutFooter, NTag } from 'naive-ui'
import { useChatStore } from '../stores/chat'

const chat = useChatStore()
const input = ref('')
const listRef = ref<HTMLDivElement | null>(null)

// 新消息进来时滚到底部
watch(
  () => chat.messages.length,
  async () => {
    await nextTick()
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  },
  { deep: true },
)

function onSend() {
  const text = input.value.trim()
  if (!text) return
  chat.send(text)
  input.value = ''
}
</script>

<template>
  <n-layout style="height: 100%; display: flex; flex-direction: column">
    <n-layout-header bordered style="padding: 12px 24px">
      <div style="display: flex; align-items: center; gap: 12px">
        <h2 style="margin: 0; font-size: 18px">时叙 · 你的陪伴 Agent</h2>
        <n-tag :type="chat.connected ? 'success' : 'error'" size="small" :bordered="false">
          {{ chat.connected ? '在线' : '离线' }}
        </n-tag>
      </div>
    </n-layout-header>

    <div ref="listRef" style="flex: 1; overflow-y: auto">
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

    <n-layout-footer bordered style="padding: 16px 24px">
      <div style="max-width: 860px; margin: 0 auto; display: flex; gap: 12px">
        <n-input
          v-model:value="input"
          placeholder="想说什么就说…"
          size="large"
          @keydown.enter.prevent="onSend"
        />
        <n-button type="primary" size="large" @click="onSend">发送</n-button>
      </div>
    </n-layout-footer>
  </n-layout>
</template>
