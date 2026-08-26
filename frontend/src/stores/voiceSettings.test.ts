import { describe, expect, it } from 'vitest'
import { VOICE_PRESETS, isQuietTime } from './voiceSettings'

function at(hour: number, minute = 0): Date {
  const d = new Date()
  d.setHours(hour, minute, 0, 0)
  return d
}

describe('isQuietTime', () => {
  it('同日时段：时段内为真，段外为假', () => {
    expect(isQuietTime('10:00', '12:00', at(11))).toBe(true)
    expect(isQuietTime('10:00', '12:00', at(9))).toBe(false)
    expect(isQuietTime('10:00', '12:00', at(13))).toBe(false)
  })

  it('边界：起始点算在内，结束点算在外', () => {
    expect(isQuietTime('10:00', '12:00', at(10, 0))).toBe(true)
    expect(isQuietTime('10:00', '12:00', at(12, 0))).toBe(false)
  })

  it('跨夜时段：23:00-08:00', () => {
    expect(isQuietTime('23:00', '08:00', at(2))).toBe(true)
    expect(isQuietTime('23:00', '08:00', at(23, 30))).toBe(true)
    expect(isQuietTime('23:00', '08:00', at(10))).toBe(false)
    expect(isQuietTime('23:00', '08:00', at(8, 0))).toBe(false)
  })

  it('起止相同返回 false（空区间）', () => {
    expect(isQuietTime('10:00', '10:00', at(10))).toBe(false)
  })
})

describe('VOICE_PRESETS', () => {
  it('每个预设都有合法的 rate 和 pitch', () => {
    for (const key of Object.keys(VOICE_PRESETS) as (keyof typeof VOICE_PRESETS)[]) {
      const spec = VOICE_PRESETS[key]
      expect(spec.rate).toBeGreaterThan(0)
      expect(spec.rate).toBeLessThanOrEqual(2)
      expect(spec.pitch).toBeGreaterThan(0)
      expect(spec.pitch).toBeLessThanOrEqual(2)
      expect(spec.label.length).toBeGreaterThan(0)
    }
  })

  it('gentle 比 daily 慢，lively 比 daily 快', () => {
    expect(VOICE_PRESETS.gentle.rate).toBeLessThan(VOICE_PRESETS.daily.rate)
    expect(VOICE_PRESETS.lively.rate).toBeGreaterThan(VOICE_PRESETS.daily.rate)
  })
})
