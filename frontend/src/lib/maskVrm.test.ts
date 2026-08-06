import { describe, expect, it, vi } from 'vitest'
import {
  MASK_STYLES,
  applyMaskExpression,
  getMaskStyle,
} from './maskVrm'

const KNOWN_MASKS = ['daily_companion', 'love_guide', 'old_bestie', 'work_advisor']

describe('MASK_STYLES', () => {
  it('覆盖所有已知面具', () => {
    for (const mask of KNOWN_MASKS) {
      expect(MASK_STYLES[mask]).toBeTruthy()
    }
  })

  it('每个面具都有中文名和一句话', () => {
    for (const mask of KNOWN_MASKS) {
      expect(MASK_STYLES[mask].label.length).toBeGreaterThan(0)
      expect(MASK_STYLES[mask].tagline.length).toBeGreaterThan(0)
    }
  })

  it('表情权重都在 0-1 之间', () => {
    for (const mask of KNOWN_MASKS) {
      for (const w of Object.values(MASK_STYLES[mask].expressions)) {
        expect(w).toBeGreaterThanOrEqual(0)
        expect(w).toBeLessThanOrEqual(1)
      }
    }
  })

  it('背景色是合法 hex', () => {
    for (const mask of KNOWN_MASKS) {
      expect(MASK_STYLES[mask].bg).toMatch(/^#[0-9a-fA-F]{6}$/)
    }
  })
})

describe('getMaskStyle', () => {
  it('未知面具回退默认（同行者）', () => {
    expect(getMaskStyle('not_a_mask')).toEqual(MASK_STYLES.daily_companion)
  })
})

describe('applyMaskExpression', () => {
  it('先清空再应用目标面具的表情', () => {
    const setValue = vi.fn()
    const vrm = { expressionManager: { setValue } }
    applyMaskExpression(vrm, 'old_bestie')
    // 先全部复位，再设置目标表情
    const resetCalls = setValue.mock.calls.filter(([, v]) => v === 0).length
    expect(resetCalls).toBeGreaterThan(0)
    expect(setValue).toHaveBeenCalledWith('happy', 0.8)
    expect(setValue).toHaveBeenCalledWith('aa', 0.25)
  })

  it('模型无表情管理器时静默跳过', () => {
    expect(() => applyMaskExpression({}, 'old_bestie')).not.toThrow()
  })
})
