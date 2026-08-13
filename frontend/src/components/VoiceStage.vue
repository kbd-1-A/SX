<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { History, Mic, MicOff, Settings2 } from 'lucide-vue-next'
import { NButton, NDrawer, NDrawerContent, NSelect, NTag } from 'naive-ui'
import { MicrophoneCapture } from '../audio/capture'
import { listAudioInputs, type AudioInputDevice } from '../audio/devices'
import { VoiceProtocolClient } from '../audio/voiceClient'
import { VoiceResponseController } from '../audio/voiceResponse'
import { shouldRestoreListening, shouldShowPresence, voicePresenceStatus } from '../audio/voicePresence'
import { renderAssistantMarkdown } from '../utils/chatMarkdown'
import { useAgentStateStore } from '../stores/agentState'
import { useChatStore, type ChatReplyEvent } from '../stores/chat'
import type { MicPermission, VoiceServerEvent } from '../types/agentEvents'
import VoiceOrb from './VoiceOrb.vue'

const agent = useAgentStateStore()
const chat = useChatStore()
const historyOpen = ref(false)
const settingsOpen = ref(false)
const starting = ref(false)
const error = ref('')
const transcript = ref('')
const audioInputs = ref<AudioInputDevice[]>([])
const selectedDeviceId = ref('')
let client: VoiceProtocolClient | null = null
let capture: MicrophoneCapture | null = null
let unsubscribeReply: (() => void) | null = null

const voiceResponse = new VoiceResponseController({
  onWaiting: (requestId) => agent.transitionLocal('thinking', requestId, 'neutral', true),
  onPlaybackStart: (requestId) => agent.transitionLocal('speaking', requestId, 'warm', true),
  onPlaybackComplete: (requestId) => {
    agent.transitionLocal('idle', requestId, 'neutral', true)
    transcript.value = ''
  },
})

const orbVisible = computed(() => shouldShowPresence(agent.state))
const statusLabel = computed(() => voicePresenceStatus(agent.state, agent.captureActive, starting.value))
const audioInputOptions = computed(() => [
  { label: '系统默认麦克风', value: '' },
  ...audioInputs.value.map((device) => ({ label: device.label, value: device.deviceId })),
])

function makeClient() {
  if (client) return client
  client = new VoiceProtocolClient(
    (event: VoiceServerEvent) => {
      agent.applyEvent(event, 'server')
      if (event.type === 'asr.final') deliverTranscript(event.text)
      if (event.type === 'turn.error') error.value = event.message
    },
    (connected) => agent.setProtocolConnected(connected),
  )
  return client
}

function makeCapture() {
  if (capture) return capture
  capture = new MicrophoneCapture({
    onLevel: (level) => agent.setAmplitude(level),
    onSpeechStart: (sampleRate) => {
      try {
        const turnId = makeClient().beginTurn(sampleRate)
        if (!turnId) return false
        voiceResponse.cancel()
        chat.interruptForSpeech()
        transcript.value = ''
        agent.transitionLocal('listening', turnId, 'neutral', true)
        return true
      } catch (cause) {
        error.value = cause instanceof Error ? cause.message : '语音轮次没有启动。'
        return false
      }
    },
    onAudio: (samples) => makeClient().sendAudio(samples),
    onSpeechEnd: (reason) => makeClient().endTurn(reason),
    onError: (message) => { error.value = message },
  })
  return capture
}

async function refreshDevices() {
  try { audioInputs.value = await listAudioInputs() } catch { audioInputs.value = [] }
}

function deliverTranscript(text: string) {
  const normalized = text.trim()
  if (!normalized) return
  transcript.value = normalized
  if (!chat.sendVoice(normalized)) error.value = chat.lastError || '识别到了声音，但这句话没有发送成功。'
}

async function startListening() {
  if (starting.value || agent.captureActive) return
  starting.value = true
  error.value = ''
  try {
    agent.configureSources({ microphone: true })
    await makeClient().connect()
    makeClient().configureSources(agent.sources)
    await makeCapture().start(selectedDeviceId.value || undefined)
    agent.setCaptureActive(true)
    agent.setMicPermission('granted')
    await refreshDevices()
  } catch (cause) {
    const name = cause instanceof DOMException ? cause.name : ''
    if (name === 'NotAllowedError') agent.setMicPermission('denied')
    error.value = cause instanceof Error ? cause.message : '麦克风没有启动。'
    await capture?.stop('manual')
    capture = null
    agent.setCaptureActive(false)
  } finally { starting.value = false }
}

async function stopListening() {
  voiceResponse.cancel()
  chat.interruptForSpeech()
  await capture?.stop('manual')
  capture = null
  agent.setCaptureActive(false)
  agent.setAmplitude(0)
  agent.resetRuntime()
  transcript.value = ''
}

function handleReply(event: ChatReplyEvent) {
  voiceResponse.handle(event)
}

async function detectPermission(): Promise<MicPermission> {
  if (!navigator.mediaDevices?.getUserMedia) return 'unavailable'
  if (!navigator.permissions?.query) return 'prompt'
  try {
    const result = await navigator.permissions.query({ name: 'microphone' as PermissionName })
    return result.state as MicPermission
  } catch {
    return 'prompt'
  }
}

onMounted(async () => {
  unsubscribeReply = chat.subscribeReply(handleReply)
  await chat.init()
  await refreshDevices()
  const permission = await detectPermission()
  agent.setMicPermission(permission)
  if (shouldRestoreListening(permission)) await startListening()
})
onBeforeUnmount(async () => {
  unsubscribeReply?.()
  voiceResponse.cancel()
  await capture?.stop('manual')
  client?.close()
})
</script>

<template>
  <main class="voice-stage" :class="`voice-stage--${agent.state}`">
    <header class="stage-header">
      <div class="stage-brand">
        <span class="stage-brand__mark" />
        <div><strong>时叙</strong><small>SHIXU</small></div>
      </div>
      <div class="stage-actions">
        <n-button quaternary circle title="对话记录" aria-label="对话记录" @click="historyOpen = true"><History :size="18" /></n-button>
        <n-button quaternary circle title="语音设置" aria-label="语音设置" @click="settingsOpen = true"><Settings2 :size="18" /></n-button>
      </div>
    </header>

    <section class="stage-center">
      <div class="orb-field" :class="{ 'orb-field--visible': orbVisible }">
        <VoiceOrb :state="agent.state" :visible="orbVisible" :amplitude="agent.amplitude" />
      </div>
      <div class="stage-copy">
        <h1>{{ statusLabel }}</h1>
        <p v-if="!agent.captureActive" class="stage-copy__hint">授权后保持页面打开，直接说话即可。</p>
      </div>
    </section>

    <footer class="stage-footer">
      <n-button
        v-if="!agent.captureActive"
        class="wake-button"
        circle
        type="primary"
        :loading="starting"
        title="唤醒时叙"
        aria-label="唤醒时叙"
        @click="startListening"
      ><Mic :size="26" /></n-button>
      <n-button v-else class="wake-button wake-button--active" circle type="error" secondary title="停止监听" aria-label="停止监听" @click="stopListening"><MicOff :size="24" /></n-button>
      <span>{{ agent.captureActive ? '持续监听中' : '点击麦克风开始' }}</span>
      <div v-if="error || chat.lastError" class="stage-error">{{ error || chat.lastError }}</div>
    </footer>

    <n-drawer v-model:show="historyOpen" width="min(520px, 100vw)" placement="right">
      <n-drawer-content title="对话记录" closable>
        <div class="history-list">
          <div v-for="message in chat.messages" :key="message.id" class="history-item" :class="`history-item--${message.role}`">
            <span>{{ message.role === 'user' ? '你' : '时叙' }}</span>
            <div v-if="message.role === 'assistant'" v-html="renderAssistantMarkdown(message.content)" />
            <p v-else>{{ message.content }}</p>
          </div>
        </div>
      </n-drawer-content>
    </n-drawer>

    <n-drawer v-model:show="settingsOpen" width="min(380px, 100vw)" placement="right">
      <n-drawer-content title="语音设置" closable>
        <div class="settings-panel">
          <label>麦克风</label>
          <n-select v-model:value="selectedDeviceId" :options="audioInputOptions" :disabled="agent.captureActive" />
          <div class="settings-status"><span>语音识别</span><n-tag size="small" :bordered="false" type="success">本机 Faster-Whisper</n-tag></div>
          <div class="settings-status"><span>语音回复</span><n-tag size="small" :bordered="false" :type="voiceResponse.available ? 'success' : 'warning'">{{ voiceResponse.available ? '浏览器语音可用' : '当前不可用' }}</n-tag></div>
          <p>浏览器首次使用必须点击麦克风授权；授权后只要保持页面打开，就能直接说话。</p>
        </div>
      </n-drawer-content>
    </n-drawer>
  </main>
</template>

<style scoped>
.voice-stage { position: relative; width: 100%; height: 100dvh; overflow: hidden; color: #eef5f3; background: #080b0c; }
.stage-header { position: absolute; z-index: 3; top: 0; left: 0; right: 0; display: flex; align-items: center; justify-content: space-between; padding: 24px 28px; }
.stage-brand, .stage-brand__mark, .stage-actions, .stage-center, .stage-footer, .settings-status { display: flex; align-items: center; }
.stage-brand { gap: 10px; }
.stage-brand__mark { width: 9px; height: 9px; border-radius: 50%; background: #e2b268; box-shadow: 0 0 18px #e2b268; }
.stage-brand strong, .stage-brand small { display: block; letter-spacing: 0; }
.stage-brand strong { font-size: 15px; font-weight: 600; }
.stage-brand small { margin-top: 2px; color: #778583; font-size: 9px; }
.stage-actions { gap: 4px; color: #aebbb8; }
.stage-center { position: absolute; inset: 72px 20px 132px; flex-direction: column; justify-content: center; }
.orb-field { width: min(62vw, 560px); height: min(58vh, 560px); max-width: 100%; opacity: .2; transform: scale(.48); transition: opacity .8s ease, transform 1s cubic-bezier(.2,.8,.2,1); }
.orb-field--visible { opacity: 1; transform: scale(1); }
.stage-copy { position: relative; z-index: 2; width: min(620px, 92vw); min-height: 88px; margin-top: -68px; text-align: center; }
.stage-copy h1 { margin: 0; font-size: 22px; font-weight: 500; letter-spacing: 0; }
.stage-copy__hint { margin: 9px auto 0; color: #7f8d8a; font-size: 13px; line-height: 1.6; }
.stage-footer { position: absolute; z-index: 3; right: 0; bottom: 26px; left: 0; flex-direction: column; gap: 8px; color: #75827f; font-size: 11px; }
.wake-button { width: 58px; height: 58px; box-shadow: 0 0 0 8px rgba(73,139,128,.08), 0 8px 26px rgba(0,0,0,.28); }
.stage-error { max-width: min(520px, 88vw); color: #d98b83; text-align: center; }
.history-list { display: grid; gap: 16px; }
.history-item { padding-bottom: 14px; border-bottom: 1px solid #edf0f1; color: #2e3837; font-size: 13px; line-height: 1.6; }
.history-item > span { display: block; margin-bottom: 5px; color: #889390; font-size: 11px; }
.history-item p, .history-item :deep(p) { margin: 0; }
.settings-panel { display: grid; gap: 14px; }
.settings-panel label { color: #3a4644; font-size: 13px; font-weight: 600; }
.settings-panel p { margin: 0; color: #7a8684; font-size: 12px; line-height: 1.6; }
.settings-status { justify-content: space-between; gap: 12px; font-size: 13px; }
@media (max-width: 680px) { .stage-header { padding: 18px; } .stage-center { inset: 64px 12px 126px; } .orb-field { width: 90vw; height: 54vh; } .stage-copy { margin-top: -46px; } .stage-copy h1 { font-size: 19px; } }
</style>
