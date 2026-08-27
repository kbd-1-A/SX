/**
 * 语音设置 store：语速/音调/声音/预设/自动朗读/夜间静音/字幕字号。
 *
 * 全部持久化到 localStorage，刷新保留。陪伴模式与聊天模式共享同一份设置。
 * 预设（preset）是 rate+pitch 的一键组合，选预设会覆盖单独的 rate/pitch 值。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'shishu.voice-settings.v1'

export type VoicePreset = 'daily' | 'gentle' | 'lively' | 'calm'

/** TTS 引擎：browser=浏览器 SpeechSynthesis；cloud=后端 DashScope 云合成（情绪语气） */
export type TtsEngine = 'browser' | 'cloud'

export interface PresetSpec {
  rate: number
  pitch: number
  label: string
}

export const VOICE_PRESETS: Record<VoicePreset, PresetSpec> = {
  daily: { rate: 1.0, pitch: 1.0, label: '日常' },
  gentle: { rate: 0.85, pitch: 0.9, label: '温柔' },
  lively: { rate: 1.15, pitch: 1.15, label: '活泼' },
  calm: { rate: 0.95, pitch: 0.85, label: '沉稳' },
}

export const PRESET_OPTIONS = (Object.keys(VOICE_PRESETS) as VoicePreset[]).map((k) => ({
  value: k,
  label: VOICE_PRESETS[k].label,
}))

interface PersistedSettings {
  preset: VoicePreset
  rate: number
  pitch: number
  voiceURI: string
  ttsEngine: TtsEngine
  autoRead: boolean
  nightQuietEnabled: boolean
  nightQuietStart: string
  nightQuietEnd: string
  subtitleFontSize: number
}

const DEFAULTS: PersistedSettings = {
  preset: 'daily',
  rate: 1.0,
  pitch: 1.0,
  voiceURI: '',
  ttsEngine: 'browser',
  autoRead: true,
  nightQuietEnabled: false,
  nightQuietStart: '23:00',
  nightQuietEnd: '08:00',
  subtitleFontSize: 17,
}

function load(): PersistedSettings {
  if (typeof localStorage === 'undefined') return { ...DEFAULTS }
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    return {
      preset: (saved.preset as VoicePreset) in VOICE_PRESETS ? saved.preset : DEFAULTS.preset,
      rate: clampNum(saved.rate, 0.5, 2.0, DEFAULTS.rate),
      pitch: clampNum(saved.pitch, 0, 2.0, DEFAULTS.pitch),
      voiceURI: typeof saved.voiceURI === 'string' ? saved.voiceURI : DEFAULTS.voiceURI,
      ttsEngine: saved.ttsEngine === 'cloud' ? 'cloud' : 'browser',
      autoRead: saved.autoRead !== false,
      nightQuietEnabled: saved.nightQuietEnabled === true,
      nightQuietStart: isHHMM(saved.nightQuietStart) ? saved.nightQuietStart : DEFAULTS.nightQuietStart,
      nightQuietEnd: isHHMM(saved.nightQuietEnd) ? saved.nightQuietEnd : DEFAULTS.nightQuietEnd,
      subtitleFontSize: clampNum(saved.subtitleFontSize, 12, 28, DEFAULTS.subtitleFontSize),
    }
  } catch {
    return { ...DEFAULTS }
  }
}

function clampNum(v: unknown, min: number, max: number, fallback: number): number {
  const n = typeof v === 'number' && isFinite(v) ? v : fallback
  return Math.min(max, Math.max(min, n))
}

function isHHMM(v: unknown): v is string {
  if (typeof v !== 'string' || !/^\d{2}:\d{2}$/.test(v)) return false
  const [h, m] = v.split(':').map(Number)
  return h >= 0 && h < 24 && m >= 0 && m < 60
}

/** 把 "HH:MM" 转成当日分钟数 */
function hhmmToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

/** 当前是否处于静音时段。支持跨夜（如 23:00-08:00） */
export function isQuietTime(start: string, end: string, now = new Date()): boolean {
  const s = hhmmToMinutes(start)
  const e = hhmmToMinutes(end)
  const cur = now.getHours() * 60 + now.getMinutes()
  if (s === e) return false
  return s < e ? cur >= s && cur < e : cur >= s || cur < e
}

export const useVoiceSettingsStore = defineStore('voiceSettings', () => {
  const loaded = load()
  const preset = ref<VoicePreset>(loaded.preset)
  const rate = ref(loaded.rate)
  const pitch = ref(loaded.pitch)
  const voiceURI = ref(loaded.voiceURI)
  const ttsEngine = ref<TtsEngine>(loaded.ttsEngine)
  const autoRead = ref(loaded.autoRead)
  const nightQuietEnabled = ref(loaded.nightQuietEnabled)
  const nightQuietStart = ref(loaded.nightQuietStart)
  const nightQuietEnd = ref(loaded.nightQuietEnd)
  const subtitleFontSize = ref(loaded.subtitleFontSize)

  /** 选预设时同步覆盖 rate/pitch，并持久化 */
  function applyPreset(p: VoicePreset) {
    preset.value = p
    rate.value = VOICE_PRESETS[p].rate
    pitch.value = VOICE_PRESETS[p].pitch
    persist()
  }

  function setRate(v: number) {
    rate.value = clampNum(v, 0.5, 2.0, 1.0)
    preset.value = 'daily'
    persist()
  }

  function setPitch(v: number) {
    pitch.value = clampNum(v, 0, 2.0, 1.0)
    preset.value = 'daily'
    persist()
  }

  function setVoiceURI(v: string) {
    voiceURI.value = v
    persist()
  }

  function setTtsEngine(v: TtsEngine) {
    ttsEngine.value = v
    persist()
  }

  function setAutoRead(v: boolean) {
    autoRead.value = v
    persist()
  }

  function setNightQuiet(enabled: boolean) {
    nightQuietEnabled.value = enabled
    persist()
  }

  function setNightQuietRange(start: string, end: string) {
    if (isHHMM(start) && isHHMM(end)) {
      nightQuietStart.value = start
      nightQuietEnd.value = end
      persist()
    }
  }

  function setSubtitleFontSize(v: number) {
    subtitleFontSize.value = clampNum(v, 12, 28, 17)
    persist()
  }

  function persist() {
    if (typeof localStorage === 'undefined') return
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          preset: preset.value,
          rate: rate.value,
          pitch: pitch.value,
          voiceURI: voiceURI.value,
          ttsEngine: ttsEngine.value,
          autoRead: autoRead.value,
          nightQuietEnabled: nightQuietEnabled.value,
          nightQuietStart: nightQuietStart.value,
          nightQuietEnd: nightQuietEnd.value,
          subtitleFontSize: subtitleFontSize.value,
        } satisfies PersistedSettings),
      )
    } catch {
      // 隐私模式或配额异常不应阻断语音链路
    }
  }

  /** 当前时刻是否应静音（自动朗读关闭或处于夜间静音时段） */
  const shouldMute = computed(() => {
    if (!autoRead.value) return true
    if (nightQuietEnabled.value && isQuietTime(nightQuietStart.value, nightQuietEnd.value)) {
      return true
    }
    return false
  })

  return {
    preset,
    rate,
    pitch,
    voiceURI,
    ttsEngine,
    autoRead,
    nightQuietEnabled,
    nightQuietStart,
    nightQuietEnd,
    subtitleFontSize,
    shouldMute,
    applyPreset,
    setRate,
    setPitch,
    setVoiceURI,
    setTtsEngine,
    setAutoRead,
    setNightQuiet,
    setNightQuietRange,
    setSubtitleFontSize,
  }
})
