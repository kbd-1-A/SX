import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { FOUNDATION_REPLAY } from '../fixtures/foundationReplay'
import { listAudioInputs } from '../audio/devices'
import type { AudioInputDevice } from '../audio/devices'
import type {
  AgentEmotion,
  AgentEventLogEntry,
  AgentMainState,
  DataSourceSettings,
  MicPermission,
  VoiceServerEvent,
} from '../types/agentEvents'

const SOURCE_STORAGE_KEY = 'shishu.data-sources.v1'
const SELECTED_DEVICE_STORAGE_KEY = 'shishu.selected-mic-device.v1'
const MAX_LOG_ENTRIES = 80

function loadSelectedDeviceId(): string {
  if (typeof localStorage === 'undefined') return ''
  try {
    return localStorage.getItem(SELECTED_DEVICE_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

export const DEFAULT_DATA_SOURCES: DataSourceSettings = {
  microphone: true,
  conversation_memory: true,
  time_context: true,
  app_activity: false,
}

function loadSources(): DataSourceSettings {
  if (typeof localStorage === 'undefined') return { ...DEFAULT_DATA_SOURCES }
  try {
    const saved = JSON.parse(localStorage.getItem(SOURCE_STORAGE_KEY) || '{}')
    return {
      microphone: saved.microphone !== false,
      conversation_memory: saved.conversation_memory !== false,
      time_context: saved.time_context !== false,
      app_activity: saved.app_activity === true,
    }
  } catch {
    return { ...DEFAULT_DATA_SOURCES }
  }
}

export const useAgentStateStore = defineStore('agentState', () => {
  const state = ref<AgentMainState>('idle')
  const emotion = ref<AgentEmotion>('neutral')
  const activeTurnId = ref<string | null>(null)
  const sessionId = ref<string | null>(null)
  const protocolConnected = ref(false)
  const micPermission = ref<MicPermission>('unknown')
  const captureActive = ref(false)
  const amplitude = ref(0)
  const sources = ref<DataSourceSettings>(loadSources())
  const deviceConnected = ref(true)
  const eventLog = ref<AgentEventLogEntry[]>([])
  const replaying = ref(false)
  const lastError = ref('')
  const selectedDeviceId = ref<string>(loadSelectedDeviceId())
  const audioInputs = ref<AudioInputDevice[]>([])
  let logSequence = 0
  let replayToken = 0

  const stateLabel = computed(
    () =>
      ({
        idle: '待机',
        listening: '正在听',
        thinking: '正在想',
        speaking: '正在说',
      })[state.value],
  )

  function persistSources() {
    if (typeof localStorage === 'undefined') return
    try {
      localStorage.setItem(SOURCE_STORAGE_KEY, JSON.stringify(sources.value))
    } catch {
      // 隐私模式或存储配额异常不应阻断实时链路。
    }
  }

  function configureSources(patch: Partial<DataSourceSettings>) {
    sources.value = { ...sources.value, ...patch }
    persistSources()
  }

  function record(event: VoiceServerEvent, source: AgentEventLogEntry['source'], applied: boolean) {
    eventLog.value.push({
      id: ++logSequence,
      receivedAt: Date.now(),
      source,
      applied,
      event,
    })
    if (eventLog.value.length > MAX_LOG_ENTRIES) {
      eventLog.value.splice(0, eventLog.value.length - MAX_LOG_ENTRIES)
    }
  }

  function applyEvent(
    event: VoiceServerEvent,
    source: AgentEventLogEntry['source'] = 'server',
    force = false,
  ) {
    let applied = true

    if (event.type === 'session.ready') {
      sessionId.value = event.session_id
      if (source === 'server') protocolConnected.value = true
      state.value = event.state
      lastError.value = ''
    } else if (event.type === 'session.configured') {
      sources.value = { ...event.sources }
      persistSources()
    } else if (event.type === 'agent.state') {
      const startsNewTurn = event.state === 'listening'
      if (!force && activeTurnId.value && event.turn_id !== activeTurnId.value && !startsNewTurn) {
        applied = false
      } else {
        activeTurnId.value = event.state === 'idle' ? null : event.turn_id
        state.value = event.state
        emotion.value = event.emotion || 'neutral'
        if (event.state === 'idle') amplitude.value = 0
      }
    } else if (event.type === 'turn.done') {
      if (activeTurnId.value && event.turn_id !== activeTurnId.value) applied = false
    } else if (event.type === 'asr.final') {
      lastError.value = ''
    } else if (event.type === 'turn.error') {
      if (event.turn_id && activeTurnId.value && event.turn_id !== activeTurnId.value) {
        applied = false
      } else {
        lastError.value = event.message
      }
    }

    record(event, source, applied)
    return applied
  }

  function transitionLocal(
    nextState: AgentMainState,
    turnId: string,
    nextEmotion: AgentEmotion = 'neutral',
    force = false,
  ) {
    applyEvent(
      {
        type: 'agent.state',
        turn_id: turnId,
        state: nextState,
        emotion: nextEmotion,
      },
      'local',
      force,
    )
  }

  function setProtocolConnected(connected: boolean) {
    protocolConnected.value = connected
    if (!connected && !captureActive.value) {
      state.value = 'idle'
      activeTurnId.value = null
    }
  }

  function setMicPermission(permission: MicPermission) {
    micPermission.value = permission
  }

  function setCaptureActive(active: boolean) {
    captureActive.value = active
  }

  function setAmplitude(value: number) {
    amplitude.value = Math.min(1, Math.max(0, value))
  }

  function setDeviceConnected(connected: boolean) {
    deviceConnected.value = connected
  }

  function setSelectedDeviceId(deviceId: string) {
    selectedDeviceId.value = deviceId
    if (typeof localStorage !== 'undefined') {
      try {
        if (deviceId) {
          localStorage.setItem(SELECTED_DEVICE_STORAGE_KEY, deviceId)
        } else {
          localStorage.removeItem(SELECTED_DEVICE_STORAGE_KEY)
        }
      } catch {
        // 隐私模式或存储配额异常不应阻断语音采集。
      }
    }
  }

  async function refreshAudioInputs() {
    try {
      const list = await listAudioInputs()
      audioInputs.value = list
      // 之前选过的设备如果已经离线（被拔/驱动掉了），就回退到系统默认，
      // 避免 getUserMedia({ exact }) 直接抛 NotFoundError。
      if (
        selectedDeviceId.value &&
        !list.some((device) => device.deviceId === selectedDeviceId.value)
      ) {
        setSelectedDeviceId('')
      }
    } catch {
      audioInputs.value = []
    }
  }

  function clearLog() {
    eventLog.value = []
  }

  function clearError() {
    lastError.value = ''
  }

  function resetRuntime() {
    state.value = 'idle'
    emotion.value = 'neutral'
    activeTurnId.value = null
    amplitude.value = 0
    lastError.value = ''
  }

  function cancelReplay() {
    replayToken += 1
    replaying.value = false
    resetRuntime()
  }

  async function replay(events: VoiceServerEvent[] = FOUNDATION_REPLAY, delayMs = 420) {
    cancelReplay()
    const token = replayToken
    replaying.value = true
    clearLog()
    try {
      for (const event of events) {
        if (token !== replayToken) break
        if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, delayMs))
        if (token !== replayToken) break
        applyEvent(event, 'replay')
      }
    } finally {
      if (token === replayToken) replaying.value = false
    }
  }

  return {
    state,
    emotion,
    activeTurnId,
    sessionId,
    protocolConnected,
    micPermission,
    captureActive,
    amplitude,
    sources,
    deviceConnected,
    eventLog,
    replaying,
    lastError,
    stateLabel,
    configureSources,
    applyEvent,
    transitionLocal,
    setProtocolConnected,
    setMicPermission,
    setCaptureActive,
    setAmplitude,
    setDeviceConnected,
    clearLog,
    clearError,
    resetRuntime,
    cancelReplay,
    replay,
    selectedDeviceId,
    audioInputs,
    setSelectedDeviceId,
    refreshAudioInputs,
  }
})
