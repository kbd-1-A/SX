import { describe, expect, it, vi } from 'vitest'
import { AudioFocusManager } from './audioFocus'

describe('AudioFocusManager', () => {
  it('stops speech and any previous music session before a new music session starts', () => {
    const focus = new AudioFocusManager()
    const stopSpeech = vi.fn()
    const stopFirstTrack = vi.fn()
    const stopSecondTrack = vi.fn()
    focus.setSpeechStopper(stopSpeech)
    focus.registerMusicStopper('first', stopFirstTrack)
    focus.registerMusicStopper('second', stopSecondTrack)

    focus.claimMusic('second')

    expect(stopSpeech).toHaveBeenCalledTimes(1)
    expect(stopFirstTrack).toHaveBeenCalledTimes(1)
    expect(stopSecondTrack).not.toHaveBeenCalled()
  })

  it('stops every active music session before speech claims the audio focus', () => {
    const focus = new AudioFocusManager()
    const stopFirstTrack = vi.fn()
    const stopSecondTrack = vi.fn()
    focus.registerMusicStopper('first', stopFirstTrack)
    focus.registerMusicStopper('second', stopSecondTrack)

    focus.claimSpeech()

    expect(stopFirstTrack).toHaveBeenCalledTimes(1)
    expect(stopSecondTrack).toHaveBeenCalledTimes(1)
  })
})
