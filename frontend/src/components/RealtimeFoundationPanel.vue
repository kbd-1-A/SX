<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NDivider,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NSelect,
  NSpace,
  NSwitch,
  NTag,
} from 'naive-ui'
import { MicrophoneCapture } from '../audio/capture'
import { listAudioInputs, type AudioInputDevice } from '../audio/devices'
import { VoiceProtocolClient } from '../audio/voiceClient'
import { VoiceResponseController } from '../audio/voiceResponse'
import { useAgentStateStore } from '../stores/agentState'
import { useChatStore } from '../stores/chat'
import type { DataSourceSettings, MicPermission, VoiceServerEvent } from '../types/agentEvents'
import DeviceSimulator from './DeviceSimulator.vue'

const agent = useAgentStateStore()
const chat = useChatStore()
const open = ref(false)
const captureTransitioning = ref(false)
const captureError = ref('')
const lastTranscript = ref('')
const transcriptionStatus = ref<'idle' | 'listening' | 'processing' | 'error'>('idle')
const audioInputs = ref<AudioInputDevice[]>([])
const selectedDeviceId = ref('')
let client: VoiceProtocolClient | null = null
let capture: MicrophoneCapture | null = null
let unsubscribeReply: (() => void) | null = null
const voiceResponse = new VoiceResponseController({
  onWaiting: (requestId) => agent.transitionLocal('thinking', requestId, 'neutral', true),
  onPlaybackStart: (requestId) => agent.transitionLocal('speaking', requestId, 'warm', true),
  onPlaybackComplete: (requestId) => agent.transitionLocal('idle', requestId, 'neutral', true),
})

const sourceItems: Array<{
  key: keyof DataSourceSettings
  label: string
  description: string
  locked?: boolean
}> = [
  {
    key: 'microphone',
    label: '麦克风与转写',
    description: '原始音频仅在内存中交给本机 Faster-Whisper，转写完成后立即释放。',
  },
  { key: 'conversation_memory', label: '对话记忆', description: '允许本轮检索已确认的对话和长期记忆。' },
  { key: 'time_context', label: '时间上下文', description: '允许使用当前时间和会话时长。' },
  { key: 'app_activity', label: '应用活动', description: '默认关闭；本阶段只保留授权开关，不采集窗口内容。' },
]

const connectionLabel = computed(() => (agent.protocolConnected ? '协议已连接' : '协议未连接'))
const inputLevel = computed(() => Math.round(agent.amplitude * 100))
const voiceTurnBusy = computed(() => transcriptionStatus.value === 'processing')
const audioInputOptions = computed(() => [
  { label: '系统默认麦克风', value: '' },
  ...audioInputs.value.map((device) => ({ label: device.label, value: device.deviceId })),
])

const transcriptionLabel = computed(
  () =>
    ({
      idle: '等待语音',
      listening: '正在收音',
      processing: '本地转写中',
      error: '转写异常',
    })[transcriptionStatus.value],
)

function permissionLabel(permission: MicPermission) {
  return {
    unknown: '未检查',
    prompt: '待授权',
    granted: '已授权',
    denied: '已拒绝',
    unavailable: '不可用',
  }[permission]
}

function makeClient() {
  if (client) return client
  client = new VoiceProtocolClient(
    (event: VoiceServerEvent) => {
      agent.applyEvent(event, 'server')
      if (event.type === 'asr.final') {
        transcriptionStatus.value = 'listening'
        deliverTranscript(event.text)
      } else if (event.type === 'turn.error' && event.code.startsWith('asr')) {
        transcriptionStatus.value = 'error'
      } else if (event.type === 'turn.error' && event.code === 'no_speech') {
        transcriptionStatus.value = 'listening'
      } else if (event.type === 'turn.done') {
        transcriptionStatus.value = agent.captureActive ? 'listening' : 'idle'
      }
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
        if (voiceResponse.activeRequestId || chat.isReplyPending) {
          voiceResponse.cancel()
          chat.interruptForSpeech()
        }
        agent.transitionLocal('listening', turnId, 'neutral', true)
        if (turnId) transcriptionStatus.value = 'listening'
        return true
      } catch (error) {
        captureError.value = error instanceof Error ? error.message : '语音轮次没有启动。'
        return false
      }
    },
    onAudio: (samples) => makeClient().sendAudio(samples),
    onSpeechEnd: (reason) => {
      transcriptionStatus.value = 'processing'
      makeClient().endTurn(reason)
    },
    onError: (message) => {
      captureError.value = message
    },
  })
  return capture
}

function deliverTranscript(text: string) {
  const normalized = text.trim()
  if (!normalized) return
  lastTranscript.value = normalized
  if (chat.sendVoice(normalized)) {
    captureError.value = ''
    return
  }
  captureError.value = chat.lastError || '已经识别到语音，但没有发送进当前对话。'
}

async function refreshAudioInputs() {
  try {
    audioInputs.value = await listAudioInputs()
    if (
      selectedDeviceId.value &&
      !audioInputs.value.some((device) => device.deviceId === selectedDeviceId.value)
    ) {
      selectedDeviceId.value = ''
    }
  } catch {
    audioInputs.value = []
  }
}

async function syncPermission() {
  if (!navigator.mediaDevices?.getUserMedia) {
    agent.setMicPermission('unavailable')
    return
  }
  if (!navigator.permissions?.query) {
    agent.setMicPermission('prompt')
    return
  }
  try {
    const result = await navigator.permissions.query({ name: 'microphone' as PermissionName })
    const update = () => {
      agent.setMicPermission(result.state as MicPermission)
      if (result.state === 'granted') refreshAudioInputs()
    }
    update()
    result.onchange = update
  } catch {
    agent.setMicPermission('prompt')
  }
}

async function startCapture() {
  if (captureTransitioning.value || agent.captureActive || voiceTurnBusy.value) return
  captureTransitioning.value = true
  captureError.value = ''
  agent.clearError()
  if (!agent.sources.microphone) {
    captureError.value = '请先启用麦克风数据来源。'
    captureTransitioning.value = false
    return
  }
  try {
    await makeClient().connect()
    makeClient().configureSources(agent.sources)
    await makeCapture().start(selectedDeviceId.value || undefined)
    agent.setMicPermission('granted')
    agent.setCaptureActive(true)
    transcriptionStatus.value = 'listening'
    await refreshAudioInputs()
  } catch (error) {
    const name = error instanceof DOMException ? error.name : ''
    if (name === 'NotAllowedError') agent.setMicPermission('denied')
    captureError.value = error instanceof Error ? error.message : '麦克风启动失败。'
    await capture?.stop('manual')
    capture = null
    transcriptionStatus.value = 'error'
    agent.setCaptureActive(false)
  } finally {
    captureTransitioning.value = false
  }
}

async function connectProtocol() {
  captureError.value = ''
  try {
    await makeClient().connect()
    makeClient().configureSources(agent.sources)
  } catch (error) {
    captureError.value = error instanceof Error ? error.message : '语音协议连接失败。'
  }
}

async function stopCapture() {
  if (captureTransitioning.value) return
  captureTransitioning.value = true
  const activeCapture = capture
  capture = null
  try {
    await activeCapture?.stop('manual')
  } finally {
    agent.setCaptureActive(false)
    agent.setAmplitude(0)
    agent.clearError()
    captureError.value = ''
    transcriptionStatus.value = client?.awaitingTurnCompletion ? 'processing' : 'idle'
    captureTransitioning.value = false
  }
}

async function updateSource(key: keyof DataSourceSettings, value: boolean) {
  agent.configureSources({ [key]: value })
  if (key === 'microphone' && !value) await stopCapture()
  if (client?.connected) client.configureSources(agent.sources)
}

async function replayFoundation() {
  await stopCapture()
  await agent.replay(undefined, 360)
}

async function resetRuntime() {
  agent.cancelReplay()
  voiceResponse.cancel()
  chat.interruptForSpeech()
  await stopCapture()
  lastTranscript.value = ''
  agent.resetRuntime()
}

onMounted(async () => {
  unsubscribeReply = chat.subscribeReply((event) => voiceResponse.handle(event))
  await syncPermission()
  await refreshAudioInputs()
})
onBeforeUnmount(async () => {
  unsubscribeReply?.()
  voiceResponse.cancel()
  await capture?.stop('manual')
  client?.close()
})
</script>

<template>
  <n-button secondary size="small" @click="open = true">实时基础</n-button>

  <n-drawer v-model:show="open" width="min(440px, 100vw)" placement="right">
    <n-drawer-content title="实时语音基础" closable>
      <n-space vertical :size="16">
        <section class="summary">
          <div>
            <span>Agent 状态</span>
            <strong>{{ agent.stateLabel }}</strong>
          </div>
          <div>
            <span>语音协议</span>
            <n-tag size="small" :type="agent.protocolConnected ? 'success' : 'default'" :bordered="false">
              {{ connectionLabel }}
            </n-tag>
          </div>
          <div>
            <span>麦克风</span>
            <n-tag size="small" :type="agent.micPermission === 'granted' ? 'success' : 'warning'" :bordered="false">
              {{ permissionLabel(agent.micPermission) }}
            </n-tag>
          </div>
        </section>

        <n-alert v-if="captureError || agent.lastError" type="warning" :show-icon="false">
          {{ captureError || agent.lastError }}
        </n-alert>

        <section class="transcript-panel">
          <div class="section-heading">
            <span>实时转写</span>
            <n-tag
              size="small"
              :bordered="false"
              :type="transcriptionStatus === 'listening' ? 'success' : transcriptionStatus === 'error' ? 'error' : 'default'"
            >
              {{ transcriptionLabel }}
            </n-tag>
          </div>
          <p :class="{ placeholder: !lastTranscript }">
            {{ lastTranscript || '选择正确的麦克风，开启后直接说话；停顿后由本机模型转写并发送。' }}
          </p>
        </section>

        <section>
          <div class="section-heading">
            <span>音频采集</span>
            <n-tag size="small" :bordered="false" :type="agent.captureActive ? 'success' : 'default'">
              {{ agent.captureActive ? '采集中' : '未采集' }}
            </n-tag>
          </div>
          <n-select
            v-model:value="selectedDeviceId"
            :options="audioInputOptions"
            :disabled="agent.captureActive || captureTransitioning"
            size="small"
            style="margin-top: 10px"
            placeholder="选择麦克风"
          />
          <div class="level-track" aria-label="麦克风输入强度">
            <span :style="{ transform: `scaleX(${agent.captureActive ? agent.amplitude : 0})` }" />
          </div>
          <div class="level-copy">输入电平 {{ inputLevel }}% · 说话时将自动进入“正在听”</div>
          <n-space style="margin-top: 10px">
            <n-button
              v-if="agent.captureActive"
              type="warning"
              :loading="captureTransitioning"
              @click="stopCapture"
            >停止采集</n-button>
            <n-button
              v-else
              type="primary"
              :loading="captureTransitioning"
              :disabled="voiceTurnBusy"
              @click="startCapture"
            >{{ voiceTurnBusy ? '等待转写完成' : '开启语音输入' }}</n-button>
            <n-button
              v-if="!agent.protocolConnected"
              :disabled="captureTransitioning"
              @click="connectProtocol"
            >连接协议</n-button>
            <n-button
              :disabled="agent.replaying || captureTransitioning"
              @click="replayFoundation"
            >回放固定日志</n-button>
            <n-button text :disabled="captureTransitioning" @click="resetRuntime">重置</n-button>
          </n-space>
        </section>

        <n-divider />

        <section>
          <div class="section-heading">数据来源</div>
          <div class="source-list">
            <div v-for="item in sourceItems" :key="item.key" class="source-row">
              <div>
                <strong>{{ item.label }}</strong>
                <p>{{ item.description }}</p>
              </div>
              <n-switch
                :value="agent.sources[item.key]"
                :disabled="item.locked"
                @update:value="(value) => updateSource(item.key, value)"
              />
            </div>
          </div>
        </section>

        <n-divider />

        <section>
          <div class="section-heading">设备模拟器</div>
          <DeviceSimulator />
          <n-button
            size="small"
            style="margin-top: 10px"
            @click="agent.setDeviceConnected(!agent.deviceConnected)"
          >
            {{ agent.deviceConnected ? '断开模拟设备' : '连接模拟设备' }}
          </n-button>
        </section>

        <n-divider />

        <section>
          <div class="section-heading">事件日志</div>
          <div v-if="agent.eventLog.length" class="event-log">
            <div v-for="entry in [...agent.eventLog].reverse()" :key="entry.id" class="event-row">
              <n-tag size="small" :bordered="false" :type="entry.applied ? 'info' : 'warning'">
                {{ entry.source }}
              </n-tag>
              <code>{{ entry.event.type }}</code>
              <span v-if="'state' in entry.event">{{ entry.event.state }}</span>
              <span v-else-if="'reason' in entry.event">{{ entry.event.reason }}</span>
              <span v-else-if="'code' in entry.event">{{ entry.event.code }}</span>
              <span v-else-if="'text' in entry.event">{{ entry.event.text }}</span>
            </div>
          </div>
          <n-empty v-else size="small" description="尚无协议事件" />
        </section>
      </n-space>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.summary > div {
  min-width: 0;
  padding: 10px;
  border: 1px solid #e2e8eb;
  border-radius: 6px;
  background: #f8fafb;
}

.summary span {
  display: block;
  margin-bottom: 5px;
  color: #69777f;
  font-size: 11px;
}

.summary strong {
  font-size: 13px;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #26343a;
  font-size: 14px;
  font-weight: 600;
}

.transcript-panel {
  padding: 12px 0;
  border-top: 1px solid #e7ecee;
  border-bottom: 1px solid #e7ecee;
}

.transcript-panel p {
  min-height: 42px;
  margin: 8px 0 0;
  color: #2d3c43;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

.transcript-panel p.placeholder,
.transcript-panel small {
  color: #76848b;
}

.level-track {
  height: 5px;
  margin-top: 10px;
  overflow: hidden;
  border-radius: 4px;
  background: #e3e9eb;
}

.level-track span {
  display: block;
  width: 100%;
  height: 100%;
  transform-origin: left center;
  border-radius: inherit;
  background: #2b8c82;
  transition: transform 80ms linear;
}

.level-copy {
  margin-top: 6px;
  color: #75828a;
  font-size: 11px;
}

.source-list {
  margin-top: 8px;
  border-top: 1px solid #e7ecee;
}

.source-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 11px 0;
  border-bottom: 1px solid #e7ecee;
}

.source-row strong {
  color: #34434a;
  font-size: 13px;
}

.source-row p {
  margin: 3px 0 0;
  color: #75828a;
  font-size: 12px;
  line-height: 1.45;
}

.event-log {
  max-height: 198px;
  margin-top: 8px;
  overflow: auto;
  border: 1px solid #e4eaed;
  border-radius: 6px;
}

.event-row {
  display: grid;
  grid-template-columns: 62px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 9px;
  border-bottom: 1px solid #edf1f3;
  color: #6a7880;
  font-size: 11px;
}

.event-row:last-child {
  border-bottom: 0;
}

.event-row code {
  overflow: hidden;
  color: #33434b;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 520px) {
  .summary {
    grid-template-columns: 1fr;
  }
}
</style>
