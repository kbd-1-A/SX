export type VadEvent = 'speech_start' | 'speech_end' | null

export interface EnergyVadOptions {
  startThreshold?: number
  stopThreshold?: number
  minSpeechFrames?: number
  hangoverFrames?: number
  calibrationFrames?: number
  minimumStartThreshold?: number
  noiseMultiplier?: number
}

export function rms(samples: Float32Array): number {
  if (!samples.length) return 0
  let total = 0
  for (const sample of samples) total += sample * sample
  return Math.sqrt(total / samples.length)
}

export class EnergyVad {
  private readonly fixedStartThreshold?: number
  private readonly fixedStopThreshold?: number
  private readonly minSpeechFrames: number
  private readonly hangoverFrames: number
  private readonly calibrationFrames: number
  private readonly minimumStartThreshold: number
  private readonly noiseMultiplier: number
  private speechFrames = 0
  private silenceFrames = 0
  private calibratedFrames = 0
  private noiseFloor = 0.0006
  private active = false

  constructor(options: EnergyVadOptions = {}) {
    this.fixedStartThreshold = options.startThreshold
    this.fixedStopThreshold = options.stopThreshold
    this.minSpeechFrames = options.minSpeechFrames ?? 2
    this.hangoverFrames = options.hangoverFrames ?? 30
    this.calibrationFrames = options.calibrationFrames ?? (options.startThreshold ? 0 : 12)
    this.minimumStartThreshold = options.minimumStartThreshold ?? 0.0016
    this.noiseMultiplier = options.noiseMultiplier ?? 2.4
  }

  reset() {
    this.speechFrames = 0
    this.silenceFrames = 0
    this.calibratedFrames = 0
    this.noiseFloor = 0.0006
    this.active = false
  }

  isActive() {
    return this.active
  }

  thresholds() {
    const start =
      this.fixedStartThreshold ??
      Math.min(0.02, Math.max(this.minimumStartThreshold, this.noiseFloor * this.noiseMultiplier))
    const stop =
      this.fixedStopThreshold ??
      Math.min(start * 0.72, Math.max(0.0008, this.noiseFloor * 1.35))
    return { start, stop, noiseFloor: this.noiseFloor }
  }

  push(samples: Float32Array): VadEvent {
    const level = rms(samples)
    const { start, stop } = this.thresholds()

    if (!this.active) {
      if (this.calibratedFrames < this.calibrationFrames) {
        this.noiseFloor = this.noiseFloor * 0.82 + level * 0.18
        this.calibratedFrames += 1
        return null
      }

      if (level >= start) {
        this.speechFrames += 1
        if (this.speechFrames >= this.minSpeechFrames) {
          this.active = true
          this.silenceFrames = 0
          return 'speech_start'
        }
      } else {
        this.speechFrames = 0
        this.noiseFloor = this.noiseFloor * 0.96 + level * 0.04
      }
      return null
    }

    if (level < stop) {
      this.silenceFrames += 1
      if (this.silenceFrames >= this.hangoverFrames) {
        this.reset()
        return 'speech_end'
      }
      return null
    }

    this.silenceFrames = 0
    return null
  }
}
