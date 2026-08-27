/**
 * 后端云语音合成输出（DashScope Qwen-TTS 指令控制）。
 *
 * 实现与 BrowserSpeechOutput 相同的 SpeechOutput 接口，供 VoiceResponseController
 * 无缝切换：speak(text) → POST /api/tts → 后端按 inner_world 当前情绪合成语气 →
 * 返回 WAV → Web Audio 播放。情绪/语气由后端决定，前端只传文本。
 */
import type { SpeechOutput, SpeechOutputCallbacks, VoiceRuntimeSettings } from './speechSynthesis'

const DEFAULT_RUNTIME: VoiceRuntimeSettings = {
  rate: 1,
  pitch: 1,
  voiceURI: '',
  muted: false,
}

let sharedContext: AudioContext | null = null

function getAudioContext(): AudioContext {
  if (!sharedContext) {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    sharedContext = new Ctx()
  }
  if (sharedContext.state === 'suspended') void sharedContext.resume()
  return sharedContext
}

export class BackendSpeechOutput implements SpeechOutput {
  private activeSource: AudioBufferSourceNode | null = null
  private generation = 0

  constructor(private readonly getSettings?: () => Partial<VoiceRuntimeSettings>) {}

  get available() {
    return typeof window !== 'undefined' && 'fetch' in window
  }

  speak(text: string, callbacks: SpeechOutputCallbacks) {
    const settings = { ...DEFAULT_RUNTIME, ...(this.getSettings?.() ?? {}) }
    if (settings.muted) {
      callbacks.onStart()
      callbacks.onEnd()
      return
    }
    if (!text.trim()) {
      callbacks.onError()
      return
    }
    this.synthesizeAndPlay(text, callbacks)
  }

  cancel() {
    this.generation += 1
    if (this.activeSource) {
      try {
        this.activeSource.onended = null
        this.activeSource.stop()
      } catch {
        // 已停止或未启动时忽略
      }
      this.activeSource = null
    }
  }

  private async synthesizeAndPlay(text: string, callbacks: SpeechOutputCallbacks) {
    const generation = this.generation
    try {
      const resp = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.trim() }),
      })
      if (!resp.ok) {
        const detail = await resp.text().catch(() => '')
        throw new Error(`TTS ${resp.status}: ${detail.slice(0, 200)}`)
      }
      if (generation !== this.generation) return
      const arrayBuffer = await resp.arrayBuffer()
      if (generation !== this.generation || arrayBuffer.byteLength === 0) return

      const ctx = getAudioContext()
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer)
      if (generation !== this.generation) return

      const source = ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(ctx.destination)
      this.activeSource = source
      source.onended = () => {
        if (this.activeSource === source) this.activeSource = null
        if (generation === this.generation) callbacks.onEnd()
      }
      source.start()
      if (generation === this.generation) callbacks.onStart()
    } catch (error) {
      if (generation !== this.generation) return
      callbacks.onError()
    }
  }
}