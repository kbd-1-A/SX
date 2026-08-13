import { describe, expect, it } from 'vitest'
import { shouldRestoreListening, shouldShowPresence, voicePresenceStatus } from './voicePresence'

describe('voice presence state', () => {
  it('keeps the visual dormant until voice activity starts', () => {
    expect(shouldShowPresence('idle')).toBe(false)
    expect(shouldShowPresence('listening')).toBe(true)
    expect(shouldShowPresence('thinking')).toBe(true)
    expect(shouldShowPresence('speaking')).toBe(true)
  })

  it('restores continuous listening only after microphone permission was granted', () => {
    expect(shouldRestoreListening('granted')).toBe(true)
    expect(shouldRestoreListening('prompt')).toBe(false)
    expect(shouldRestoreListening('denied')).toBe(false)
  })

  it('uses short voice-state labels instead of chat instructions', () => {
    expect(voicePresenceStatus('listening', true)).toBe('听见你了')
    expect(voicePresenceStatus('thinking', true)).toBe('让我想一想')
    expect(voicePresenceStatus('speaking', true)).toBe('时叙正在说')
  })
})
