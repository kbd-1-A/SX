/**
 * 陪伴模式粒子球样式映射（纯数据 + 纯函数，可单测）。
 *
 * 输入：面具 + 情绪状态（emotion_state.emotion / intensity，强度 0-3）。
 * 输出：粒子球的颜色与运动参数。
 *
 * 设计原则：
 * - 面具定「色相氛围」（和 maskVrm 的 bg 同族但更亮，适配发光粒子）；
 * - 情绪定「运动节奏」——低落/疲惫变慢变小，焦虑/愤怒变快变燥，
 *   高风险（crisis）反而压到最稳，给的是一个安定在场的感觉；
 * - intensity（0-3）线性缩放情绪调制幅度，未识别情绪时不影响面具基调。
 */

export interface OrbStyle {
  /** 核心粒子色（hex） */
  core: string
  /** 辉光/边缘色（hex） */
  glow: string
  /** 背景氛围色（hex，用于容器渐变） */
  bg: string
  /** 噪声形变幅度（0-1，相对球半径） */
  noiseAmp: number
  /** 噪声流动速度（倍率） */
  noiseSpeed: number
  /** 呼吸幅度（0-1） */
  breathe: number
  /** 整体运动节奏（倍率，1 = 基准） */
  speed: number
  /** 粒子点大小（倍率） */
  size: number
}

/** 粒子球律动状态：idle 呼吸 / thinking 等待首块 / speaking 流式说话 / listening 聆听（预留给语音采集） */
export type OrbState = 'idle' | 'thinking' | 'speaking' | 'listening'

export const MASK_ORB_STYLES: Record<string, OrbStyle> = {
  // 默认金色粒子 + 纯黑底（对标参考视频的主视觉）
  daily_companion: {
    core: '#fff3d6',
    glow: '#ffb830',
    bg: '#000000',
    noiseAmp: 0.16,
    noiseSpeed: 0.5,
    breathe: 0.5,
    speed: 1,
    size: 1,
  },
  love_guide: {
    core: '#ffd1e0',
    glow: '#e05585',
    bg: '#020001',
    noiseAmp: 0.15,
    noiseSpeed: 0.45,
    breathe: 0.55,
    speed: 0.95,
    size: 1,
  },
  old_bestie: {
    core: '#ffe1a8',
    glow: '#ff8f1f',
    bg: '#020100',
    noiseAmp: 0.2,
    noiseSpeed: 0.6,
    breathe: 0.6,
    speed: 1.1,
    size: 1.05,
  },
  work_advisor: {
    core: '#b8f2e9',
    glow: '#2ec4b6',
    bg: '#000202',
    noiseAmp: 0.12,
    noiseSpeed: 0.4,
    breathe: 0.4,
    speed: 0.9,
    size: 0.95,
  },
}

export const DEFAULT_ORB_STYLE = MASK_ORB_STYLES.daily_companion

/** 情绪 → 运动参数调制（倍率，在 intensity=3 时达到满幅） */
interface MotionMod {
  noiseAmp?: number
  noiseSpeed?: number
  breathe?: number
  speed?: number
  size?: number
}

const EMOTION_MODS: Record<string, MotionMod> = {
  neutral: {},
  happy: { speed: 1.3, noiseAmp: 1.2, breathe: 1.25, noiseSpeed: 1.2 },
  low: { speed: 0.6, noiseAmp: 0.7, breathe: 0.7, size: 0.92 },
  anxious: { noiseSpeed: 1.9, noiseAmp: 1.45, speed: 1.15, breathe: 0.8 },
  tired: { speed: 0.5, breathe: 0.55, noiseSpeed: 0.6, noiseAmp: 0.8 },
  angry: { noiseAmp: 1.65, noiseSpeed: 1.6, speed: 1.25 },
  perfunctory: { speed: 0.85, breathe: 0.85 },
  mixed: { noiseAmp: 1.25, noiseSpeed: 1.3, speed: 0.9 },
  // 高风险：不做刺激性运动，压到最稳最慢，视觉上「稳住场子」
  crisis: { speed: 0.4, noiseAmp: 0.5, noiseSpeed: 0.5, breathe: 0.45 },
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/** 按 factor（0-1）把 base 朝 target 倍率插值：factor=0 保持 base，factor=1 达到 base*target */
function lerpMultiplier(base: number, target: number, factor: number): number {
  return base * (1 + (target - 1) * factor)
}

export function getOrbStyle(mask: string, emotion = 'neutral', intensity = 0): OrbStyle {
  const base = MASK_ORB_STYLES[mask] ?? DEFAULT_ORB_STYLE
  const mod = EMOTION_MODS[emotion] ?? EMOTION_MODS.neutral
  const factor = clamp(intensity / 3, 0, 1)
  return {
    core: base.core,
    glow: base.glow,
    bg: base.bg,
    noiseAmp: clamp(lerpMultiplier(base.noiseAmp, mod.noiseAmp ?? 1, factor), 0.02, 0.5),
    noiseSpeed: clamp(lerpMultiplier(base.noiseSpeed, mod.noiseSpeed ?? 1, factor), 0.1, 2),
    breathe: clamp(lerpMultiplier(base.breathe, mod.breathe ?? 1, factor), 0.1, 1),
    speed: clamp(lerpMultiplier(base.speed, mod.speed ?? 1, factor), 0.2, 2),
    size: clamp(lerpMultiplier(base.size, mod.size ?? 1, factor), 0.5, 1.5),
  }
}
