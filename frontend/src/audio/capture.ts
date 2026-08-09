import { EnergyVad, rms } from './vad'

export type CaptureEndReason = 'vad_end' | 'manual'

export interface MicrophoneCaptureCallbacks {
  onLevel: (level: number) => void
  onSpeechStart: (sampleRate: number) => boolean | void
  onAudio: (samples: Int16Array) => void
  onSpeechEnd: (reason: CaptureEndReason) => void
  onError: (message: string) => void
}

function toInt16(samples: Float32Array): Int16Array {
  const pcm = new Int16Array(samples.length)
  for (let index = 0; index < samples.length; index += 1) {
    const value = Math.max(-1, Math.min(1, samples[index]))
    pcm[index] = value < 0 ? value * 0x8000 : value * 0x7fff
  }
  return pcm
}

export class MicrophoneCapture {
  private stream: MediaStream | null = null
  private context: AudioContext | null = null
  private worklet: AudioWorkletNode | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private silenceGain: GainNode | null = null
  private pending: number[] = []
  private utteranceActive = false
  private sampleRate = 0
  private maximumSignal = 0
  private signalTimer: ReturnType<typeof setTimeout> | null = null
  private sessionToken = 0
  private readonly vad = new EnergyVad()
  private readonly frameDurationMs = 20

  constructor(private readonly callbacks: MicrophoneCaptureCallbacks) {}

  get active() {
    return this.stream !== null
  }

  async start(deviceId?: string) {
    if (this.active) return
    const sessionToken = ++this.sessionToken
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('当前浏览器不支持麦克风采集。')
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        deviceId: deviceId ? { exact: deviceId } : undefined,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    })

    const context = new AudioContext({ latencyHint: 'interactive' })
    if (!context.audioWorklet) {
      stream.getTracks().forEach((track) => track.stop())
      await context.close()
      throw new Error('当前浏览器不支持 AudioWorklet。')
    }

    try {
      await context.audioWorklet.addModule('/worklets/pcm-capture-processor.js')
      const source = context.createMediaStreamSource(stream)
      const worklet = new AudioWorkletNode(context, 'pcm-capture-processor', { numberOfInputs: 1, numberOfOutputs: 1 })
      const silenceGain = context.createGain()
      silenceGain.gain.value = 0
      source.connect(worklet).connect(silenceGain).connect(context.destination)

      this.stream = stream
      this.context = context
      this.source = source
      this.worklet = worklet
      this.silenceGain = silenceGain
      this.sampleRate = context.sampleRate
      this.maximumSignal = 0
      this.pending = []
      this.utteranceActive = false
      this.vad.reset()
      worklet.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        if (sessionToken !== this.sessionToken || !this.stream) return
        this.receiveFrame(event.data)
      }
      await context.resume()
      this.signalTimer = setTimeout(() => {
        if (this.active && this.maximumSignal < 0.00012) {
          this.callbacks.onError('麦克风已经打开，但没有音频信号。请在下方切换输入设备。')
        }
      }, 2200)
    } catch (error) {
      stream.getTracks().forEach((track) => track.stop())
      await context.close()
      throw error
    }
  }

  async stop(reason: CaptureEndReason = 'manual') {
    if (!this.active) return

    if (this.utteranceActive) this.callbacks.onSpeechEnd(reason)
    this.sessionToken += 1
    this.utteranceActive = false
    this.pending = []
    this.vad.reset()
    if (this.signalTimer) clearTimeout(this.signalTimer)
    this.signalTimer = null

    const worklet = this.worklet
    const source = this.source
    const silenceGain = this.silenceGain
    const stream = this.stream
    const context = this.context
    this.stream = null
    this.context = null
    this.source = null
    this.worklet = null
    this.silenceGain = null
    this.sampleRate = 0
    this.maximumSignal = 0

    if (worklet) worklet.port.onmessage = null
    worklet?.disconnect()
    source?.disconnect()
    silenceGain?.disconnect()
    stream?.getTracks().forEach((track) => track.stop())
    if (context && context.state !== 'closed') await context.close()
    this.callbacks.onLevel(0)
  }

  private receiveFrame(buffer: ArrayBuffer) {
    const samples = new Float32Array(buffer)
    const rawLevel = rms(samples)
    this.maximumSignal = Math.max(this.maximumSignal, rawLevel)
    const level = Math.min(1, rawLevel * 8)
    this.callbacks.onLevel(level)
    for (const sample of samples) this.pending.push(sample)

    const frameSamples = Math.max(1, Math.round((this.sampleRate * this.frameDurationMs) / 1000))
    while (this.pending.length >= frameSamples) {
      const frame = Float32Array.from(this.pending.splice(0, frameSamples))
      this.processVadFrame(frame)
    }
  }

  private processVadFrame(frame: Float32Array) {
    const event = this.vad.push(frame)
    if (event === 'speech_start') {
      this.utteranceActive = this.callbacks.onSpeechStart(this.sampleRate) !== false
    }

    if (this.utteranceActive) this.callbacks.onAudio(toInt16(frame))

    if (event === 'speech_end' && this.utteranceActive) {
      this.utteranceActive = false
      this.callbacks.onSpeechEnd('vad_end')
    }
  }
}
