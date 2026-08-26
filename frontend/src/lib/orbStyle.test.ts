import { describe, expect, it } from 'vitest'
import { DEFAULT_ORB_STYLE, MASK_ORB_STYLES, applyVoicePreset, getOrbStyle } from './orbStyle'

const HEX_RE = /^#[0-9a-f]{6}$/

describe('getOrbStyle', () => {
  it('每个面具都有合法样式：hex 颜色 + 正数运动参数', () => {
    for (const mask of Object.keys(MASK_ORB_STYLES)) {
      const style = getOrbStyle(mask)
      expect(style.core).toMatch(HEX_RE)
      expect(style.glow).toMatch(HEX_RE)
      expect(style.bg).toMatch(HEX_RE)
      expect(style.noiseAmp).toBeGreaterThan(0)
      expect(style.noiseSpeed).toBeGreaterThan(0)
      expect(style.breathe).toBeGreaterThan(0)
      expect(style.speed).toBeGreaterThan(0)
      expect(style.size).toBeGreaterThan(0)
    }
  })

  it('未知面具回退到同行者默认样式', () => {
    expect(getOrbStyle('nonexistent')).toEqual(DEFAULT_ORB_STYLE)
    expect(getOrbStyle('')).toEqual(DEFAULT_ORB_STYLE)
  })

  it('情绪不影响颜色，只影响运动参数（色相氛围由面具定）', () => {
    const neutral = getOrbStyle('daily_companion', 'neutral', 3)
    const sad = getOrbStyle('daily_companion', 'low', 3)
    expect(sad.core).toBe(neutral.core)
    expect(sad.glow).toBe(neutral.glow)
    expect(sad.bg).toBe(neutral.bg)
  })

  it('低落让球变慢收敛，焦虑让噪声更快更燥', () => {
    const mask = 'daily_companion'
    const neutral = getOrbStyle(mask, 'neutral', 3)
    const low = getOrbStyle(mask, 'low', 3)
    const anxious = getOrbStyle(mask, 'anxious', 3)
    expect(low.speed).toBeLessThan(neutral.speed)
    expect(low.noiseAmp).toBeLessThan(neutral.noiseAmp)
    expect(anxious.noiseSpeed).toBeGreaterThan(neutral.noiseSpeed)
    expect(anxious.noiseAmp).toBeGreaterThan(neutral.noiseAmp)
  })

  it('crisis 高压到最稳：比低落更慢更安静', () => {
    const mask = 'old_bestie'
    const crisis = getOrbStyle(mask, 'crisis', 3)
    const low = getOrbStyle(mask, 'low', 3)
    expect(crisis.speed).toBeLessThan(low.speed)
    expect(crisis.noiseAmp).toBeLessThan(low.noiseAmp)
  })

  it('intensity 线性缩放调制幅度：0 时等于面具基调', () => {
    const base = getOrbStyle('work_advisor')
    const mild = getOrbStyle('work_advisor', 'angry', 0)
    const full = getOrbStyle('work_advisor', 'angry', 3)
    expect(mild).toEqual(base)
    expect(full.noiseAmp).toBeGreaterThan(base.noiseAmp)
  })

  it('intensity 超出 0-3 范围时被钳制，不产生非法值', () => {
    const over = getOrbStyle('daily_companion', 'anxious', 99)
    const negative = getOrbStyle('daily_companion', 'anxious', -5)
    expect(over.noiseSpeed).toBeLessThanOrEqual(2)
    expect(over.noiseAmp).toBeLessThanOrEqual(0.5)
    expect(negative).toEqual(getOrbStyle('daily_companion', 'anxious', 0))
  })

  it('未知情绪按 neutral 处理', () => {
    expect(getOrbStyle('daily_companion', 'whatever', 3)).toEqual(
      getOrbStyle('daily_companion', 'neutral', 3),
    )
  })
})

describe('applyVoicePreset', () => {
  it('daily 预设不改变任何运动参数', () => {
    const base = getOrbStyle('daily_companion', 'happy', 2)
    const result = applyVoicePreset(base, 'daily')
    expect(result.speed).toBe(base.speed)
    expect(result.noiseAmp).toBe(base.noiseAmp)
    expect(result.breathe).toBe(base.breathe)
    expect(result.noiseSpeed).toBe(base.noiseSpeed)
  })

  it('gentle 预设让球变慢变柔', () => {
    const base = getOrbStyle('daily_companion', 'neutral', 0)
    const gentle = applyVoicePreset(base, 'gentle')
    expect(gentle.speed).toBeLessThan(base.speed)
    expect(gentle.breathe).toBeLessThan(base.breathe)
    expect(gentle.noiseAmp).toBeLessThan(base.noiseAmp)
  })

  it('lively 预设让球变快变活', () => {
    const base = getOrbStyle('daily_companion', 'neutral', 0)
    const lively = applyVoicePreset(base, 'lively')
    expect(lively.speed).toBeGreaterThan(base.speed)
    expect(lively.breathe).toBeGreaterThan(base.breathe)
    expect(lively.noiseAmp).toBeGreaterThan(base.noiseAmp)
  })

  it('calm 预设让球稍慢但不过度收敛', () => {
    const base = getOrbStyle('daily_companion', 'neutral', 0)
    const calm = applyVoicePreset(base, 'calm')
    expect(calm.speed).toBeLessThan(base.speed)
    expect(calm.speed).toBeGreaterThan(applyVoicePreset(base, 'gentle').speed)
  })

  it('预设不改变颜色，只改变运动', () => {
    const base = getOrbStyle('love_guide', 'happy', 3)
    const result = applyVoicePreset(base, 'lively')
    expect(result.core).toBe(base.core)
    expect(result.glow).toBe(base.glow)
    expect(result.bg).toBe(base.bg)
    expect(result.size).toBe(base.size)
  })

  it('未知预设按 daily 处理（不改变）', () => {
    const base = getOrbStyle('daily_companion')
    expect(applyVoicePreset(base, 'nonexistent')).toEqual(base)
  })

  it('预设叠加在情绪之上，结果仍被钳制到合法区间', () => {
    const extreme = applyVoicePreset(getOrbStyle('daily_companion', 'anxious', 3), 'lively')
    expect(extreme.noiseAmp).toBeLessThanOrEqual(0.5)
    expect(extreme.noiseSpeed).toBeLessThanOrEqual(2)
    expect(extreme.speed).toBeLessThanOrEqual(2)
    expect(extreme.breathe).toBeLessThanOrEqual(1)
  })
})
