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

export class BrowserSpeechOutput implements SpeechOutput {
  get available() {
    return typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window
  }

  speak(text: string, callbacks: SpeechOutputCallbacks) {
    if (!this.available) {
      callbacks.onError()
      return
    }

    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'zh-CN'
    utterance.rate = 1
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
