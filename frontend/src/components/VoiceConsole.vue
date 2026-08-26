<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton, NSelect, NSlider, NSwitch, NTag } from 'naive-ui'
import {
  PRESET_OPTIONS,
  useVoiceSettingsStore,
  type VoicePreset,
} from '../stores/voiceSettings'

const props = defineProps<{
  replayLastReply: () => boolean
  previewVoice: () => void
}>()

const voice = useVoiceSettingsStore()
const open = ref(false)

interface VoiceOption {
  label: string
  value: string
  lang: string
}
const voiceOptions = ref<VoiceOption[]>([])

function refreshVoices() {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
  const voices = window.speechSynthesis.getVoices()
  voiceOptions.value = voices
    .filter((v) => v.lang.toLowerCase().startsWith('zh'))
    .map((v) => ({
      label: `${v.name}（${v.lang}）`,
      value: v.voiceURI,
      lang: v.lang,
    }))
  if (!voiceOptions.value.length) {
    voiceOptions.value = voices.map((v) => ({
      label: `${v.name}（${v.lang}）`,
      value: v.voiceURI,
      lang: v.lang,
    }))
  }
}

function onVoicesChanged() {
  refreshVoices()
}

onMounted(() => {
  refreshVoices()
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.addEventListener('voiceschanged', onVoicesChanged)
  }
})
onBeforeUnmount(() => {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.removeEventListener('voiceschanged', onVoicesChanged)
  }
})

watch(
  () => voiceOptions.value.length,
  (n) => {
    if (n && voice.voiceURI && !voiceOptions.value.some((o) => o.value === voice.voiceURI)) {
      voice.setVoiceURI('')
    }
  },
)

function onPresetChange(v: string | number | null) {
  if (v === 'daily' || v === 'gentle' || v === 'lively' || v === 'calm') {
    voice.applyPreset(v as VoicePreset)
  }
}

function onVoiceChange(v: string | number | null) {
  voice.setVoiceURI(typeof v === 'string' ? v : '')
}

function onReplay() {
  if (!props.replayLastReply()) {
    // 没有可重播的内容时，退而用试听示例
    props.previewVoice()
  }
}

const rateMarks = { 0.5: '慢', 1: '常', 1.5: '快', 2: '极速' }
const pitchMarks = { 0: '低', 1: '常', 2: '高' }
const sizeMarks = { 12: '小', 17: '中', 28: '大' }
</script>

<template>
  <div class="voice-console">
    <button
      class="console-toggle"
      :class="{ active: open }"
      type="button"
      :title="open ? '收起控制台' : '语音控制台'"
      @click="open = !open"
    >
      <span class="toggle-icon">{{ open ? '✕' : '⚙' }}</span>
    </button>

    <transition name="vc-slide">
      <section v-if="open" class="console-panel">
        <header class="panel-head">
          <span class="panel-title">时叙控制台</span>
          <NTag
            v-if="voice.shouldMute"
            size="tiny"
            type="warning"
            :bordered="false"
            round
          >
            静音中
          </NTag>
        </header>

        <div class="ctrl-row">
          <span class="ctrl-label">语音风格</span>
          <NSelect
            :value="voice.preset"
            size="small"
            :options="PRESET_OPTIONS"
            :consistent-menu-width="false"
            @update:value="onPresetChange"
          />
        </div>

        <div class="ctrl-row">
          <span class="ctrl-label">语速 <em>{{ voice.rate.toFixed(2) }}×</em></span>
          <NSlider
            :value="voice.rate"
            :min="0.5"
            :max="2"
            :step="0.05"
            :marks="rateMarks"
            size="small"
            @update:value="(v: number) => voice.setRate(v)"
          />
        </div>

        <div class="ctrl-row">
          <span class="ctrl-label">音调 <em>{{ voice.pitch.toFixed(2) }}</em></span>
          <NSlider
            :value="voice.pitch"
            :min="0"
            :max="2"
            :step="0.05"
            :marks="pitchMarks"
            size="small"
            @update:value="(v: number) => voice.setPitch(v)"
          />
        </div>

        <div class="ctrl-row">
          <span class="ctrl-label">声音</span>
          <NSelect
            :value="voice.voiceURI || undefined"
            size="small"
            :options="voiceOptions"
            placeholder="系统默认"
            :consistent-menu-width="false"
            filterable
            @update:value="onVoiceChange"
          />
        </div>

        <div class="ctrl-row btn-row">
          <NButton size="small" secondary @click="onReplay">重播</NButton>
          <NButton size="small" tertiary @click="props.previewVoice()">试听</NButton>
          <div class="auto-read">
            <span class="ctrl-label small">自动朗读</span>
            <NSwitch :value="voice.autoRead" size="small" @update:value="(v: boolean) => voice.setAutoRead(v)" />
          </div>
        </div>

        <div class="divider" />

        <div class="ctrl-row">
          <span class="ctrl-label small">夜间静音</span>
          <NSwitch
            :value="voice.nightQuietEnabled"
            size="small"
            @update:value="(v: boolean) => voice.setNightQuiet(v)"
          />
        </div>
        <div v-if="voice.nightQuietEnabled" class="quiet-range">
          <input
            type="time"
            class="time-input"
            :value="voice.nightQuietStart"
            @change="(e) => voice.setNightQuietRange((e.target as HTMLInputElement).value, voice.nightQuietEnd)"
          />
          <span class="quiet-sep">至</span>
          <input
            type="time"
            class="time-input"
            :value="voice.nightQuietEnd"
            @change="(e) => voice.setNightQuietRange(voice.nightQuietStart, (e.target as HTMLInputElement).value)"
          />
        </div>

        <div class="divider" />

        <div class="ctrl-row">
          <span class="ctrl-label">字幕字号 <em>{{ voice.subtitleFontSize }}px</em></span>
          <NSlider
            :value="voice.subtitleFontSize"
            :min="12"
            :max="28"
            :step="1"
            :marks="sizeMarks"
            size="small"
            @update:value="(v: number) => voice.setSubtitleFontSize(v)"
          />
        </div>
      </section>
    </transition>
  </div>
</template>

<style scoped>
.voice-console {
  position: absolute;
  top: 52px;
  left: 18px;
  z-index: 5;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.console-toggle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(20, 20, 26, 0.72);
  color: rgba(255, 255, 255, 0.85);
  font-size: 15px;
  cursor: pointer;
  backdrop-filter: blur(10px);
  transition: all 0.25s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}
.console-toggle:hover {
  background: rgba(40, 40, 48, 0.85);
  border-color: rgba(255, 184, 48, 0.5);
}
.console-toggle.active {
  border-color: rgba(255, 184, 48, 0.7);
  background: rgba(255, 184, 48, 0.18);
  color: #ffb830;
}

.console-panel {
  margin-top: 10px;
  width: 268px;
  max-height: calc(100dvh - 120px);
  overflow-y: auto;
  padding: 14px 14px 16px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(12, 12, 16, 0.88);
  backdrop-filter: blur(16px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  letter-spacing: 0.04em;
}

.ctrl-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ctrl-label {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.62);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ctrl-label em {
  font-style: normal;
  color: rgba(255, 184, 48, 0.85);
  font-size: 11px;
}
.ctrl-label.small {
  font-size: 11px;
}

.btn-row {
  flex-direction: row;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.auto-read {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
}

.divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.08);
  margin: 2px 0;
}

.quiet-range {
  display: flex;
  align-items: center;
  gap: 8px;
}
.time-input {
  flex: 1;
  min-width: 0;
  padding: 4px 6px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.9);
  font-size: 12px;
  color-scheme: dark;
}
.quiet-sep {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
}

.vc-slide-enter-active,
.vc-slide-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
  transform-origin: top left;
}
.vc-slide-enter-from,
.vc-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.96);
}
</style>
