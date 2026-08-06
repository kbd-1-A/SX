/**
 * 面具 → VRM 表情/背景映射（纯数据 + 纯函数，可单测）。
 *
 * 数字人形象随面具切换：不同面具对应不同 blendShape 权重与背景氛围。
 * 映射用 VRM0/VRM1 通用的 preset 表情名（happy/relaxed/neutral/aa…）。
 */

export interface MaskStyle {
  /** blendShape 名 → 权重(0-1)。同一面具多表情叠加 */
  expressions: Record<string, number>
  /** 背景色（hex），随面具氛围变化 */
  bg: string
  /** 侧边栏中文名 */
  label: string
  /** 一句话口吻描述 */
  tagline: string
}

export const MASK_STYLES: Record<string, MaskStyle> = {
  daily_companion: {
    expressions: { neutral: 1 },
    bg: '#3b4a63',
    label: '同行者',
    tagline: '安静的同行者',
  },
  love_guide: {
    expressions: { happy: 0.5, relaxed: 0.6 },
    bg: '#6b4a7a',
    label: '感情向导',
    tagline: '慢慢说，我听着',
  },
  old_bestie: {
    expressions: { happy: 0.8, aa: 0.25 },
    bg: '#8a6a3a',
    label: '老闺蜜',
    tagline: '嗑着瓜子等你开麦',
  },
  work_advisor: {
    expressions: { neutral: 0.8, relaxed: 0.2 },
    bg: '#2e5a6a',
    label: '工作参谋',
    tagline: '直接说，我帮你拆',
  },
}

/** 表情复位时清一遍的 preset 名单（含 VRM0/VRM1 通用项） */
export const EXPRESSION_NAMES = [
  'neutral',
  'happy',
  'angry',
  'sad',
  'relaxed',
  'surprise',
  'aa',
  'ih',
  'ou',
  'ee',
  'oh',
  'blink',
  'blinkLeft',
  'blinkRight',
]

export const DEFAULT_MASK_STYLE = MASK_STYLES.daily_companion

export function getMaskStyle(mask: string): MaskStyle {
  return MASK_STYLES[mask] ?? DEFAULT_MASK_STYLE
}

/**
 * 把面具映射应用到一个已加载的 VRM 上。
 * vrm.expressionManager 可能不存在（模型无表情）——静默跳过。
 */
export function applyMaskExpression(vrm: any, mask: string): void {
  const manager = vrm?.expressionManager
  if (!manager) return
  const style = getMaskStyle(mask)
  for (const name of EXPRESSION_NAMES) {
    manager.setValue(name, 0)
  }
  for (const [name, weight] of Object.entries(style.expressions)) {
    manager.setValue(name, weight)
  }
}
