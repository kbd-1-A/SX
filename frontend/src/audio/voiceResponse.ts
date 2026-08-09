import type { ChatReplyEvent } from '../stores/chat'
import { BrowserSpeechOutput, SpeechQueue, type SpeechOutput } from './speechSynthesis'

const MAX_SEGMENT_CHARS = 90
const SENTENCE_ENDINGS = /[。！？!?；;\n]/
const SOFT_BREAKS = ['，', '、', ',', ' ']

export interface VoiceResponseCallbacks {
  onWaiting: (requestId: string) => void
  onPlaybackStart: (requestId: string) => void
  onPlaybackComplete: (requestId: string) => void
}

export function splitSpeakableText(text: string, flush = false) {
  const segments: string[] = []
  let remaining = text

  while (remaining) {
    const sentenceEnd = remaining.search(SENTENCE_ENDINGS)
    if (sentenceEnd >= 0) {
      segments.push(remaining.slice(0, sentenceEnd + 1))
      remaining = remaining.slice(sentenceEnd + 1)
      continue
    }

    if (remaining.length >= MAX_SEGMENT_CHARS) {
      const preview = remaining.slice(0, MAX_SEGMENT_CHARS)
      const softBreak = Math.max(...SOFT_BREAKS.map((separator) => preview.lastIndexOf(separator)))
      const end = softBreak >= 45 ? softBreak + 1 : MAX_SEGMENT_CHARS
      segments.push(remaining.slice(0, end))
      remaining = remaining.slice(end)
      continue
    }

    break
  }

  if (flush && remaining.trim()) {
    segments.push(remaining)
    remaining = ''
  }

  return { segments, remaining }
}

export class VoiceResponseController {
  private requestId: string | null = null
  private pendingText = ''
  private replyFinished = false
  private readonly queue: SpeechQueue

  constructor(
    private readonly callbacks: VoiceResponseCallbacks,
    output: SpeechOutput = new BrowserSpeechOutput(),
  ) {
    this.queue = new SpeechQueue(output, {
      onStart: () => {
        if (this.requestId) this.callbacks.onPlaybackStart(this.requestId)
      },
      onIdle: () => {
        if (!this.requestId) return
        if (this.replyFinished) {
          this.complete()
        } else {
          this.callbacks.onWaiting(this.requestId)
        }
      },
    })
  }

  get available() {
    return this.queue.available
  }

  get activeRequestId() {
    return this.requestId
  }

  handle(event: ChatReplyEvent) {
    if (event.origin !== 'voice') return

    if (event.type === 'start') {
      this.cancel()
      this.requestId = event.requestId
      this.replyFinished = false
      this.callbacks.onWaiting(event.requestId)
      return
    }

    if (event.requestId !== this.requestId) return

    if (event.type === 'chunk') {
      this.append(event.content || '', false)
      return
    }

    if (event.type === 'done') {
      this.append('', true)
      this.replyFinished = true
      if (!this.queue.available || !this.queue.busy) this.complete()
      return
    }

    this.complete()
  }

  cancel() {
    this.queue.cancel()
    this.clear()
  }

  private append(text: string, flush: boolean) {
    this.pendingText += text
    const split = splitSpeakableText(this.pendingText, flush)
    this.pendingText = split.remaining
    for (const segment of split.segments) this.queue.enqueue(segment)
  }

  private complete() {
    if (!this.requestId) return
    const requestId = this.requestId
    this.queue.cancel()
    this.clear()
    this.callbacks.onPlaybackComplete(requestId)
  }

  private clear() {
    this.requestId = null
    this.pendingText = ''
    this.replyFinished = false
  }
}
