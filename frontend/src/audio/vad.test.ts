import { describe, expect, it } from 'vitest'
import { EnergyVad, rms } from './vad'

function frame(level: number, length = 320) {
  return new Float32Array(length).fill(level)
}

describe('EnergyVad', () => {
  it('uses a short speech confirmation before starting', () => {
    const vad = new EnergyVad({ minSpeechFrames: 2, hangoverFrames: 2, calibrationFrames: 0 })

    expect(vad.push(frame(0.02))).toBeNull()
    expect(vad.push(frame(0.02))).toBe('speech_start')
    expect(vad.isActive()).toBe(true)
  })

  it('uses hangover before ending an utterance', () => {
    const vad = new EnergyVad({ minSpeechFrames: 1, hangoverFrames: 3, calibrationFrames: 0 })

    expect(vad.push(frame(0.02))).toBe('speech_start')
    expect(vad.push(frame(0.0001))).toBeNull()
    expect(vad.push(frame(0.0001))).toBeNull()
    expect(vad.push(frame(0.0001))).toBe('speech_end')
    expect(vad.isActive()).toBe(false)
  })

  it('computes zero RMS for silence', () => {
    expect(rms(frame(0))).toBe(0)
  })

  it('detects low microphone levels after calibrating quiet background noise', () => {
    const vad = new EnergyVad({ calibrationFrames: 4, minSpeechFrames: 2, hangoverFrames: 2 })

    for (let index = 0; index < 4; index += 1) expect(vad.push(frame(0.00035))).toBeNull()
    expect(vad.push(frame(0.0022))).toBeNull()
    expect(vad.push(frame(0.0022))).toBe('speech_start')
    expect(vad.thresholds().start).toBeLessThan(0.0022)
  })

  it('adapts its start threshold above steady background noise', () => {
    const vad = new EnergyVad({ calibrationFrames: 8, minSpeechFrames: 2 })

    for (let index = 0; index < 8; index += 1) expect(vad.push(frame(0.0025))).toBeNull()
    expect(vad.thresholds().start).toBeGreaterThan(0.004)
    expect(vad.push(frame(0.0025))).toBeNull()
    expect(vad.isActive()).toBe(false)
  })
})
