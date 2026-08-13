<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton, NSlider, NTag } from 'naive-ui'
import { audioFocus } from '../audio/audioFocus'
import type { ChatMedia, MediaCommand } from '../stores/chat'

const props = defineProps<{
  media: ChatMedia
  command?: MediaCommand | null
}>()

const emit = defineEmits<{
  status: [status: 'playing' | 'paused' | 'stopped' | 'autoplay_blocked' | 'failed', message?: string]
  command: [command: 'play' | 'pause' | 'stop']
}>()

const audio = ref<HTMLAudioElement | null>(null)
const currentTime = ref(0)
const duration = ref(0)
const volume = ref(0.75)
const isPlaying = ref(false)
let unregisterFocus: (() => void) | null = null

const statusLabel = computed(() => {
  if (props.media.status === 'autoplay_blocked') return '等待点击播放'
  if (props.media.status === 'failed') return '播放失败'
  if (props.media.status === 'playing' || isPlaying.value) return '正在播放'
  if (props.media.status === 'paused') return '已暂停'
  if (props.media.status === 'stopped') return '已停止'
  return '准备播放'
})

function formatTime(value: number) {
  if (!Number.isFinite(value) || value < 0) return '0:00'
  const seconds = Math.floor(value)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function report(status: 'playing' | 'paused' | 'stopped' | 'autoplay_blocked' | 'failed', message?: string) {
  isPlaying.value = status === 'playing'
  emit('status', status, message)
}

async function play() {
  if (!audio.value) return
  audioFocus.claimMusic(props.media.playback_id)
  try {
    await audio.value.play()
    report('playing')
  } catch (error) {
    const name = error instanceof DOMException ? error.name : ''
    if (name === 'NotAllowedError') report('autoplay_blocked', '浏览器需要你点击一次播放。')
    else report('failed', '音频播放失败，请检查文件格式或输出设备。')
  }
}

function pause() {
  audio.value?.pause()
  report('paused')
}

function stop() {
  if (audio.value) {
    audio.value.pause()
    audio.value.currentTime = 0
  }
  report('stopped')
}

function toggle() {
  emit('command', isPlaying.value ? 'pause' : 'play')
}

function onTimeUpdate() {
  currentTime.value = audio.value?.currentTime || 0
}

function onLoadedMetadata() {
  duration.value = audio.value?.duration || 0
}

function onEnded() {
  report('stopped')
}

function onError() {
  report('failed', '音频文件无法播放。')
}

function seek(value: number | [number, number]) {
  if (audio.value && typeof value === 'number') audio.value.currentTime = value
}

function setupAudio() {
  const element = new Audio()
  element.preload = 'metadata'
  element.volume = volume.value
  element.addEventListener('timeupdate', onTimeUpdate)
  element.addEventListener('loadedmetadata', onLoadedMetadata)
  element.addEventListener('ended', onEnded)
  element.addEventListener('error', onError)
  audio.value = element
  unregisterFocus = audioFocus.registerMusicStopper(props.media.playback_id, () => {
    if (element.paused) return
    element.pause()
    report('paused')
  })
}

function loadTrack() {
  if (!audio.value) return
  audio.value.src = props.media.stream_url
  audio.value.load()
  currentTime.value = 0
  duration.value = 0
  void play()
}

watch(() => props.media.stream_url, loadTrack, { immediate: true })
watch(volume, (value) => {
  if (audio.value) audio.value.volume = value
})
watch(
  () => props.command,
  (command) => {
    if (!command || command.playback_id !== props.media.playback_id) return
    if (command.command === 'play') void play()
    else if (command.command === 'pause') pause()
    else stop()
  },
)

onMounted(() => {
  setupAudio()
  loadTrack()
})
onBeforeUnmount(() => {
  unregisterFocus?.()
  audio.value?.pause()
  audio.value?.removeAttribute('src')
  audio.value?.load()
})
</script>

<template>
  <div class="music-player">
    <div class="music-player__topline">
      <div class="music-player__identity">
        <span class="music-player__icon" aria-hidden="true">♫</span>
        <div>
          <strong>{{ media.title }}</strong>
          <span>{{ media.artist }}</span>
        </div>
      </div>
      <n-tag size="small" :type="media.status === 'failed' ? 'error' : media.status === 'playing' ? 'success' : 'default'" :bordered="false">
        {{ statusLabel }}
      </n-tag>
    </div>
    <div class="music-player__progress">
      <span>{{ formatTime(currentTime) }}</span>
      <n-slider :value="currentTime" :max="Math.max(duration, 1)" :step="0.1" :disabled="!duration" @update:value="seek" />
      <span>{{ formatTime(duration) }}</span>
    </div>
    <div class="music-player__controls">
      <n-button size="small" type="primary" :disabled="media.status === 'failed'" @click="toggle">
        {{ isPlaying ? '暂停' : '播放' }}
      </n-button>
      <n-button size="small" secondary :disabled="media.status === 'failed'" @click="emit('command', 'stop')">停止</n-button>
      <label class="music-player__volume">
        <span>音量</span>
        <n-slider v-model:value="volume" :min="0" :max="1" :step="0.05" />
      </label>
    </div>
    <p v-if="media.status === 'autoplay_blocked'" class="music-player__hint">浏览器没有自动开始有声播放，点击“播放”即可继续。</p>
    <p v-if="media.status === 'failed'" class="music-player__hint music-player__hint--error">{{ media.message || '音频没有播放成功。' }}</p>
  </div>
</template>

<style scoped>
.music-player { margin-top: 8px; padding: 12px; border: 1px solid #c8dce7; border-radius: 6px; background: #f5fafc; color: #243943; }
.music-player__topline, .music-player__controls, .music-player__progress { display: flex; align-items: center; gap: 10px; }
.music-player__topline { justify-content: space-between; }
.music-player__identity { display: flex; align-items: center; gap: 9px; min-width: 0; }
.music-player__identity strong, .music-player__identity span { display: block; overflow-wrap: anywhere; }
.music-player__identity strong { font-size: 14px; }
.music-player__identity span { margin-top: 2px; color: #6a7c84; font-size: 12px; }
.music-player__icon { width: 28px; height: 28px; border-radius: 50%; background: #d7edf2; color: #276779 !important; font-size: 18px !important; line-height: 28px; text-align: center; }
.music-player__progress { margin-top: 10px; color: #71818a; font-size: 11px; }
.music-player__progress :deep(.n-slider) { flex: 1; }
.music-player__controls { margin-top: 8px; flex-wrap: wrap; }
.music-player__volume { display: flex; align-items: center; gap: 7px; min-width: 140px; color: #71818a; font-size: 11px; }
.music-player__volume :deep(.n-slider) { width: 80px; }
.music-player__hint { margin: 8px 0 0; color: #6b7b82; font-size: 12px; line-height: 1.45; }
.music-player__hint--error { color: #a13a3a; }
</style>
