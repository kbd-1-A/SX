<script setup lang="ts">
/**
 * 陪伴模式：粒子球为视觉主体，对话退为字幕浮层。
 *
 * 只读复用 chat store（WS 链路、面具、情绪、流式消息全部不动），
 * 本视图是同一份状态的另一种渲染——聊天/陪伴两种模式随时互切。
 */
import { computed, ref } from 'vue'
import { NButton, NInput } from 'naive-ui'
import { useChatStore } from '../stores/chat'
import { getOrbStyle, type OrbState } from '../lib/orbStyle'
import { getMaskStyle } from '../lib/maskVrm'
import { useVoiceConversation } from '../composables/useVoiceConversation'
import ParticleOrb from '../components/ParticleOrb.vue'

const emit = defineEmits<{ (e: 'switch-to-chat'): void }>()

const chat = useChatStore()
const draft = ref('')
const voice = useVoiceConversation()

const orbStyle = computed(() =>
  getOrbStyle(chat.currentMask, chat.currentEmotion.emotion, chat.currentEmotion.intensity),
)

const orbState = computed<OrbState>(() => {
  if (chat.isStreaming) return 'speaking'
  if (chat.isReplyPending) return 'thinking'
  if (voice.capturing.value) return 'listening'
  return 'idle'
})

const voiceHint = computed(() => {
  if (voice.captureError.value) return voice.captureError.value
  switch (voice.transcriptionStatus.value) {
    case 'listening':
      return '正在听，直接说话…'
    case 'processing':
      return '转写中…'
    case 'error':
      return '语音出了点问题'
    default:
      return ''
  }
})

const lastUserMessage = computed(() => {
  for (let i = chat.messages.length - 1; i >= 0; i -= 1) {
    if (chat.messages[i].role === 'user') return chat.messages[i].content
  }
  return ''
})

const lastAssistantMessage = computed(() => {
  for (let i = chat.messages.length - 1; i >= 0; i -= 1) {
    if (chat.messages[i].role === 'assistant') return chat.messages[i]
  }
  return null
})

const maskLabel = computed(() => getMaskStyle(chat.currentMask).label)

const statusText = computed(() => {
  switch (chat.status) {
    case 'online':
      return '已连接'
    case 'connecting':
      return '连接中'
    case 'reconnecting':
      return '重连中'
    default:
      return '未连接'
  }
})

function send() {
  const text = draft.value.trim()
  if (!text) return
  if (chat.send(text)) draft.value = ''
}
</script>

<template>
  <div
    class="companion-view"
    :style="{ background: orbStyle.bg }"
  >
    <header class="top-bar">
      <button class="mode-switch" type="button" @click="emit('switch-to-chat')">‹ 聊天模式</button>
      <div class="status">
        <span class="mask-tag">{{ maskLabel }}</span>
        <span class="conn" :class="chat.status">{{ statusText }}</span>
      </div>
    </header>

    <div class="orb-stage">
      <ParticleOrb :style="orbStyle" :state="orbState" />
    </div>

    <section class="subtitle" :class="{ active: lastAssistantMessage }">
      <p v-if="lastUserMessage" class="user-line">{{ lastUserMessage }}</p>
      <p v-if="lastAssistantMessage" class="assistant-line">
        {{ lastAssistantMessage.content
        }}<span v-if="lastAssistantMessage.streaming" class="caret">▍</span>
      </p>
      <p v-else class="placeholder">说点什么，我一直都在。</p>
    </section>

    <footer class="control-bar">
      <button
        class="mic-button"
        :class="{ active: voice.capturing.value }"
        type="button"
        :title="voice.capturing.value ? '停止语音输入' : '开启语音输入'"
        :disabled="voice.captureTransitioning.value || voice.voiceTurnBusy.value"
        @click="voice.toggleCapture()"
      >
        <span class="mic-icon">{{ voice.capturing.value ? '■' : '🎙' }}</span>
      </button>
      <div class="input-column">
        <span
          v-if="voiceHint"
          class="voice-hint"
          :class="{ dismissible: voice.captureError.value }"
          :title="voice.captureError.value ? '点击关闭提示' : ''"
          @click="voice.captureError.value && (voice.captureError.value = '')"
          >{{ voiceHint }}</span
        >
        <n-input
          v-model:value="draft"
          class="input"
          round
          size="large"
          placeholder="和时叙说说话…"
          :disabled="!chat.connected"
          @keyup.enter="send"
        />
      </div>
      <n-button v-if="chat.isStreaming || chat.isReplyPending" round size="large" @click="chat.stop()">
        停止
      </n-button>
      <n-button v-else round size="large" type="primary" :disabled="!chat.connected" @click="send">
        发送
      </n-button>
    </footer>
  </div>
</template>

<style scoped>
.companion-view {
  position: relative;
  height: 100dvh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: background 1.2s ease;
}

.top-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 3;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
}

.mode-switch {
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.82);
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  backdrop-filter: blur(6px);
}
.mode-switch:hover {
  background: rgba(255, 255, 255, 0.12);
}

.status {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
}
.mask-tag {
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}
.conn::before {
  content: '●';
  margin-right: 4px;
  color: #e5534b;
}
.conn.online::before {
  color: #3fb950;
}
.conn.connecting::before,
.conn.reconnecting::before {
  color: #d29922;
}

.orb-stage {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.subtitle {
  position: relative;
  z-index: 2;
  margin-top: auto;
  padding: 0 24px 18px;
  text-align: center;
  pointer-events: none;
}
.user-line {
  color: rgba(255, 255, 255, 0.45);
  font-size: 13px;
  margin: 0 0 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.assistant-line {
  margin: 0 auto;
  max-width: 720px;
  color: rgba(255, 255, 255, 0.94);
  font-size: 17px;
  line-height: 1.75;
  text-shadow: 0 1px 12px rgba(0, 0, 0, 0.7);
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.caret {
  animation: blink 0.9s steps(2) infinite;
  color: rgba(255, 255, 255, 0.7);
}
.placeholder {
  color: rgba(255, 255, 255, 0.35);
  font-size: 15px;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}

.control-bar {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 0 24px 22px;
  max-width: 720px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}
.input-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.voice-hint {
  padding-left: 14px;
  color: rgba(255, 255, 255, 0.55);
  font-size: 12px;
}
.voice-hint.dismissible {
  color: rgba(255, 200, 120, 0.85);
  cursor: pointer;
}
.mic-button {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.07);
  color: rgba(255, 255, 255, 0.85);
  font-size: 15px;
  cursor: pointer;
  backdrop-filter: blur(6px);
  transition: all 0.25s ease;
}
.mic-button:hover {
  background: rgba(255, 255, 255, 0.14);
}
.mic-button.active {
  border-color: rgba(255, 184, 48, 0.7);
  background: rgba(255, 184, 48, 0.16);
  color: #ffb830;
  box-shadow: 0 0 14px rgba(255, 184, 48, 0.35);
  animation: mic-pulse 1.6s ease-in-out infinite;
}
.mic-button:disabled {
  opacity: 0.45;
  cursor: default;
}
@keyframes mic-pulse {
  50% {
    box-shadow: 0 0 22px rgba(255, 184, 48, 0.55);
  }
}
.input {
  flex: 1;
  --n-color: rgba(255, 255, 255, 0.08) !important;
  --n-color-focus: rgba(255, 255, 255, 0.12) !important;
  --n-text-color: rgba(255, 255, 255, 0.92) !important;
  --n-placeholder-color: rgba(255, 255, 255, 0.35) !important;
  --n-border: 1px solid rgba(255, 255, 255, 0.16) !important;
  --n-border-hover: 1px solid rgba(255, 255, 255, 0.3) !important;
  --n-border-focus: 1px solid rgba(255, 255, 255, 0.4) !important;
  --n-box-shadow-focus: none !important;
}
</style>
