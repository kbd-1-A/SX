import { afterEach, describe, expect, it, vi } from 'vitest'
import { VoiceProtocolClient } from './voiceClient'

class FakeWebSocket {
  static OPEN = 1
  static instances: FakeWebSocket[] = []
  readyState = 0
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null

  constructor(_url: string) {
    FakeWebSocket.instances.push(this)
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  message(event: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(event) })
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = 3
    this.onclose?.()
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  FakeWebSocket.instances = []
})

describe('VoiceProtocolClient turn lifecycle', () => {
  it('suppresses tail audio and a second turn until turn.done', async () => {
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.stubGlobal('location', { protocol: 'http:', host: '127.0.0.1:5174' })
    const client = new VoiceProtocolClient(vi.fn(), vi.fn())
    const connecting = client.connect()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    socket.message({
      type: 'session.ready',
      session_id: 'voice_test',
      protocol_version: 1,
      state: 'idle',
      sources: {},
    })
    await connecting

    const turnId = client.beginTurn(48_000)
    expect(turnId).toBeTruthy()
    client.endTurn('vad_end')
    const sentAfterEnd = socket.sent.length

    client.sendAudio(new Int16Array([1, 2, 3]))
    expect(client.beginTurn(48_000)).toBeNull()
    expect(socket.sent).toHaveLength(sentAfterEnd)

    socket.message({ type: 'turn.done', turn_id: turnId, reason: 'vad_end' })
    expect(client.beginTurn(48_000)).toBeTruthy()
    expect(socket.sent).toHaveLength(sentAfterEnd + 1)
  })
})
