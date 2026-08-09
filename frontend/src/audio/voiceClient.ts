import type {
  DataSourceSettings,
  VoiceClientEvent,
  VoiceServerEvent,
} from '../types/agentEvents'

function makeTurnId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `turn_${crypto.randomUUID().replaceAll('-', '').slice(0, 16)}`
  }
  return `turn_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

function pcmToBase64(samples: Int16Array) {
  const bytes = new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength)
  let binary = ''
  const chunkSize = 8192
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize))
  }
  return btoa(binary)
}

function voiceWsUrl() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${location.host}/ws/voice`
}

export class VoiceProtocolClient {
  private socket: WebSocket | null = null
  private readyPromise: Promise<void> | null = null
  private resolveReady: (() => void) | null = null
  private rejectReady: ((reason?: unknown) => void) | null = null
  private currentTurnId: string | null = null
  private turnClosing = false

  constructor(
    private readonly onEvent: (event: VoiceServerEvent) => void,
    private readonly onConnectionChange: (connected: boolean) => void,
  ) {}

  get connected() {
    return this.socket?.readyState === WebSocket.OPEN
  }

  get awaitingTurnCompletion() {
    return this.currentTurnId !== null
  }

  async connect() {
    if (this.connected) return
    if (this.readyPromise) return this.readyPromise

    this.readyPromise = new Promise<void>((resolve, reject) => {
      this.resolveReady = resolve
      this.rejectReady = reject
      const socket = new WebSocket(voiceWsUrl())
      this.socket = socket

      socket.onmessage = (message) => {
        let event: VoiceServerEvent
        try {
          event = JSON.parse(message.data) as VoiceServerEvent
        } catch {
          return
        }
        if (event.type === 'turn.done' && event.turn_id === this.currentTurnId) {
          this.currentTurnId = null
          this.turnClosing = false
        }
        this.onEvent(event)
        if (event.type === 'session.ready') {
          this.resolveReady?.()
          this.resolveReady = null
          this.rejectReady = null
          this.readyPromise = null
        }
      }

      socket.onerror = () => {
        if (this.socket !== socket) return
        this.rejectReady?.(new Error('语音协议连接失败。'))
        this.resolveReady = null
        this.rejectReady = null
        this.readyPromise = null
      }

      socket.onclose = () => {
        if (this.socket !== socket) return
        this.socket = null
        this.currentTurnId = null
        this.turnClosing = false
        this.onConnectionChange(false)
        this.rejectReady?.(new Error('语音协议连接已关闭。'))
        this.resolveReady = null
        this.rejectReady = null
        this.readyPromise = null
      }

      socket.onopen = () => this.onConnectionChange(true)
    })

    return this.readyPromise
  }

  close() {
    this.socket?.close()
    this.socket = null
    this.currentTurnId = null
    this.turnClosing = false
    this.onConnectionChange(false)
  }

  configureSources(sources: DataSourceSettings) {
    this.send({ type: 'session.configure', sources })
  }

  beginTurn(sampleRate: number) {
    if (!this.connected) throw new Error('语音协议尚未连接。')
    if (this.turnClosing) return null
    if (this.currentTurnId) return this.currentTurnId

    this.currentTurnId = makeTurnId()
    this.turnClosing = false
    this.send({
      type: 'audio.start',
      turn_id: this.currentTurnId,
      sample_rate: sampleRate,
      channels: 1,
      format: 'pcm_s16le',
    })
    return this.currentTurnId
  }

  sendAudio(samples: Int16Array) {
    if (!this.currentTurnId || this.turnClosing) return
    const seq = this.nextSequence()
    this.send({
      type: 'audio.chunk',
      turn_id: this.currentTurnId,
      seq,
      pcm_s16le_base64: pcmToBase64(samples),
    })
  }

  endTurn(reason: 'vad_end' | 'manual') {
    if (!this.currentTurnId || this.turnClosing) return
    const turnId = this.currentTurnId
    this.turnClosing = true
    this.send({ type: 'audio.end', turn_id: turnId, reason })
  }

  interrupt() {
    if (!this.currentTurnId) return
    this.send({ type: 'turn.interrupt', turn_id: this.currentTurnId, played_ms: 0 })
    this.turnClosing = true
  }

  private sequence = -1

  private nextSequence() {
    this.sequence += 1
    return this.sequence
  }

  private send(event: VoiceClientEvent) {
    if (!this.connected) return
    if (event.type === 'audio.start') this.sequence = -1
    this.socket?.send(JSON.stringify(event))
  }
}
