import { describe, expect, it, vi } from 'vitest'
import { VoiceResponseController, splitSpeakableText } from './voiceResponse'
import type { SpeechOutput } from './speechSynthesis'

class FakeSpeechOutput implements SpeechOutput {
  available = true
  spoken: string[] = []
  current: { onStart: () => void; onEnd: () => void; onError: () => void } | null = null

  speak(text: string, callbacks: { onStart: () => void; onEnd: () => void; onError: () => void }) {
    this.spoken.push(text)
    this.current = callbacks
    callbacks.onStart()
  }

  cancel() {
    this.current = null
  }

  endCurrent() {
    const callbacks = this.current
    this.current = null
    callbacks?.onEnd()
  }
}

describe('splitSpeakableText', () => {
  it('emits completed Chinese sentences and keeps an unfinished tail', () => {
    expect(splitSpeakableText('第一句。第二句还没有结束')).toEqual({
      segments: ['第一句。'],
      remaining: '第二句还没有结束',
    })
  })

  it('flushes the final tail when a reply is complete', () => {
    expect(splitSpeakableText('最后一句', true)).toEqual({ segments: ['最后一句'], remaining: '' })
  })
})

describe('VoiceResponseController', () => {
  it('speaks only voice-origin chunks and returns to idle after playback', () => {
    const output = new FakeSpeechOutput()
    const callbacks = {
      onWaiting: vi.fn(),
      onPlaybackStart: vi.fn(),
      onPlaybackComplete: vi.fn(),
    }
    const controller = new VoiceResponseController(callbacks, output)

    controller.handle({ type: 'start', requestId: 'voice_1', origin: 'voice' })
    controller.handle({ type: 'chunk', requestId: 'voice_1', origin: 'voice', content: '你好。' })
    controller.handle({ type: 'chunk', requestId: 'voice_1', origin: 'voice', content: '后半句' })
    controller.handle({ type: 'done', requestId: 'voice_1', origin: 'voice' })

    expect(output.spoken).toEqual(['你好。'])
    expect(callbacks.onPlaybackStart).toHaveBeenCalledWith('voice_1')
    output.endCurrent()
    expect(output.spoken).toEqual(['你好。', '后半句'])
    output.endCurrent()
    expect(callbacks.onPlaybackComplete).toHaveBeenCalledWith('voice_1')
  })

  it('clears queued speech on interruption', () => {
    const output = new FakeSpeechOutput()
    const controller = new VoiceResponseController(
      { onWaiting: vi.fn(), onPlaybackStart: vi.fn(), onPlaybackComplete: vi.fn() },
      output,
    )

    controller.handle({ type: 'start', requestId: 'voice_1', origin: 'voice' })
    controller.handle({ type: 'chunk', requestId: 'voice_1', origin: 'voice', content: '第一句。第二句。' })
    controller.handle({ type: 'interrupted', requestId: 'voice_1', origin: 'voice' })
    output.endCurrent()

    expect(controller.activeRequestId).toBeNull()
    expect(output.spoken).toEqual(['第一句。'])
  })
})
