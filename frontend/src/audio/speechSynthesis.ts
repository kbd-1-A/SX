export interface SpeechOutputCallbacks {
  onStart: () => void
  onEnd: () => void
  onError: () => void
}

export interface SpeechOutput {
  readonly available: boolean
  speak(text: string, callbacks: SpeechOutputCallbacks): void
  cancel(): void
}

/** 运行时语音参数：由 voiceSettings store 注入，speak 时读取最新值 */
export interface VoiceRuntimeSettings {
  rate: number
  pitch: number
  voiceURI: string
  /** 静音时不实际播放，立即 onEnd，让队列正常流转（文字仍显示） */
  muted: boolean
}

const DEFAULT_RUNTIME: VoiceRuntimeSettings = {
  rate: 1,
  pitch: 1,
  voiceURI: '',
  muted: false,
}

export class BrowserSpeechOutput implements SpeechOutput {
  constructor(private readonly getSettings?: () => Partial<VoiceRuntimeSettings>) {}

  get available() {
    return typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window
  }

  private resolveVoice(uri: string): SpeechSynthesisVoice | null {
    if (!this.available || !uri) return null
    const voices = window.speechSynthesis.getVoices()
    return voices.find((v) => v.voiceURI === uri) ?? null
  }

  speak(text: string, callbacks: SpeechOutputCallbacks) {
    if (!this.available) {
      callbacks.onError()
      return
    }

    const settings = { ...DEFAULT_RUNTIME, ...(this.getSettings?.() ?? {}) }
    // 静音：不实际播放，立即收尾，让队列推进——文字仍由 chat 流式显示
    if (settings.muted) {
      callbacks.onStart()
      callbacks.onEnd()
      return
    }

    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'zh-CN'
    utterance.rate = settings.rate
    utterance.pitch = settings.pitch
    const voice = this.resolveVoice(settings.voiceURI)
    if (voice) utterance.voice = voice
    utterance.onstart = callbacks.onStart
    utterance.onend = callbacks.onEnd
    utterance.onerror = callbacks.onError
    window.speechSynthesis.speak(utterance)
  }

  cancel() {
    if (this.available) window.speechSynthesis.cancel()
  }
}

export interface SpeechQueueCallbacks {
  onStart: () => void
  onIdle: () => void
}

export class SpeechQueue {
  private queue: string[] = []
  private active = false
  private generation = 0

  constructor(
    private readonly output: SpeechOutput,
    private readonly callbacks: SpeechQueueCallbacks,
  ) {}

  get available() {
    return this.output.available
  }

  get busy() {
    return this.active || this.queue.length > 0
  }

  enqueue(text: string) {
    const normalized = text.trim()
    if (!normalized || !this.available) return false
    this.queue.push(normalized)
    this.playNext()
    return true
  }

  cancel() {
    this.generation += 1
    this.queue = []
    this.active = false
    this.output.cancel()
  }

  private playNext() {
    if (this.active) return
    const text = this.queue.shift()
    if (!text) {
      this.callbacks.onIdle()
      return
    }

    this.active = true
    const generation = this.generation
    this.output.speak(text, {
      onStart: () => {
        if (generation === this.generation) this.callbacks.onStart()
      },
      onEnd: () => this.finishItem(generation),
      onError: () => this.finishItem(generation),
    })
  }

  private finishItem(generation: number) {
    if (generation !== this.generation) return
    this.active = false
    this.playNext()
  }
}
