import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from './chat'

class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 3
  static instances: FakeWebSocket[] = []
  readyState = FakeWebSocket.CONNECTING
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
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.()
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
  vi.stubGlobal('location', { protocol: 'http:', host: '127.0.0.1:5174' })
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, json: async () => [] })),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('chat voice replies', () => {
  it('keeps an ASR transcript until the chat connection opens and labels its reply as voice', async () => {
    const chat = useChatStore()
    const events: Array<{ type: string; origin: string; content?: string }> = []
    chat.subscribeReply((event) => events.push(event))

    await chat.init()
    const socket = FakeWebSocket.instances[0]
    const requestId = chat.sendVoice('今天有点累')

    expect(requestId).toBeTruthy()
    expect(chat.messages).toEqual([{ id: -1, role: 'user', content: '今天有点累' }])
    expect(events).toHaveLength(0)

    socket.open()

    expect(JSON.parse(socket.sent[0])).toEqual({ type: 'message', content: '今天有点累' })
    expect(events).toEqual([{ type: 'start', requestId, origin: 'voice' }])

    socket.message({ type: 'chunk', content: '我在，先缓一缓。' })
    socket.message({ type: 'done' })

    expect(events).toEqual([
      { type: 'start', requestId, origin: 'voice' },
      { type: 'chunk', requestId, origin: 'voice', content: '我在，先缓一缓。' },
      { type: 'done', requestId, origin: 'voice' },
    ])
    expect(chat.isReplyPending).toBe(false)
    expect(chat.userInteractionSequence).toBe(1)
  })

  it('counts typed messages as user interactions without treating assistant chunks as new input', async () => {
    const chat = useChatStore()
    await chat.init()
    const socket = FakeWebSocket.instances[0]
    socket.open()

    expect(chat.send('你好')).toBe(true)
    socket.message({ type: 'chunk', content: '你好。' })
    socket.message({ type: 'done' })

    expect(chat.userInteractionSequence).toBe(1)
  })
})
