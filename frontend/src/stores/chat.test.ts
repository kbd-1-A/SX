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

  it('attaches a verified file artifact to the current assistant reply', async () => {
    const chat = useChatStore()
    await chat.init()
    const socket = FakeWebSocket.instances[0]
    socket.open()

    expect(chat.send('帮我创建一个 md 文件')).toBe(true)
    socket.message({
      type: 'artifact.created',
      artifact: {
        id: 'artifact-1',
        path: 'E:\\Kairos-output\\计划.md',
        display_name: '计划.md',
        target: 'output',
        mime_type: 'text/markdown',
        size_bytes: 42,
        sha256: 'a'.repeat(64),
      },
    })
    socket.message({ type: 'chunk', content: '已创建 Markdown 文件：计划.md' })
    socket.message({ type: 'done' })

    const reply = chat.messages[1]
    expect(reply.content).toContain('已创建 Markdown 文件')
    expect(reply.streaming).toBe(false)
    expect(reply.artifacts).toEqual([
      expect.objectContaining({ display_name: '计划.md', size_bytes: 42 }),
    ])
  })

  it('keeps the artifact failure visible with the assistant reply', async () => {
    const chat = useChatStore()
    await chat.init()
    const socket = FakeWebSocket.instances[0]
    socket.open()

    expect(chat.send('帮我创建一个 md 文件')).toBe(true)
    socket.message({
      type: 'artifact.failed',
      code: 'destination_unavailable',
      message: '目标文件夹无法使用。',
    })
    socket.message({ type: 'chunk', content: 'Markdown 文件没有创建成功。' })
    socket.message({ type: 'done' })

    expect(chat.messages[1].artifactFailure).toEqual({
      code: 'destination_unavailable',
      message: '目标文件夹无法使用。',
    })
  })

  it('tracks research progress and verified source summaries', async () => {
    const chat = useChatStore()
    await chat.init()
    const socket = FakeWebSocket.instances[0]
    socket.open()

    expect(chat.send('研究 agent 行业并创建 md')).toBe(true)
    socket.message({ type: 'research.started', query: 'agent 行业' })
    expect(chat.messages[1].research).toEqual({ status: 'running', query: 'agent 行业' })

    socket.message({
      type: 'research.completed',
      research: {
        query: 'agent 行业',
        retrieved_at: '2026-08-10 15:00:00 +0800',
        source_count: 2,
        sources: [
          { citation_id: 1, title: '官方资料', url: 'https://example.com/a', domain: 'example.com', source_type: 'official' },
          { citation_id: 2, title: '行业资料', url: 'https://example.org/b', domain: 'example.org', source_type: 'organization' },
        ],
        warnings: [],
      },
    })
    socket.message({ type: 'chunk', content: '研究文档已创建。' })
    socket.message({ type: 'done' })

    expect(chat.messages[1].research).toEqual(
      expect.objectContaining({
        status: 'completed',
        source_count: 2,
        sources: [expect.objectContaining({ domain: 'example.com' }), expect.any(Object)],
      }),
    )
  })

  it('shows research failure without converting it into a successful search state', async () => {
    const chat = useChatStore()
    await chat.init()
    const socket = FakeWebSocket.instances[0]
    socket.open()

    expect(chat.send('研究 agent 行业并创建 md')).toBe(true)
    socket.message({ type: 'research.started', query: 'agent 行业' })
    socket.message({
      type: 'research.failed',
      code: 'search_unavailable',
      message: '联网搜索暂时不可用。',
    })
    socket.message({ type: 'chunk', content: '已创建研究框架。' })
    socket.message({ type: 'done' })

    expect(chat.messages[1].research).toEqual({
      status: 'failed',
      query: 'agent 行业',
      code: 'search_unavailable',
      message: '联网搜索暂时不可用。',
    })
  })

  it('keeps media ready until the browser confirms actual playback', async () => {
    const chat = useChatStore()
    await chat.init()
    const socket = FakeWebSocket.instances[0]
    socket.open()

    expect(chat.send('放一首歌')).toBe(true)
    socket.message({
      type: 'media.ready',
      media: {
        playback_id: 'playback-1',
        track_id: 'track-1',
        title: '慢慢来',
        artist: '夜晚',
        provider_id: 'local_library',
        mime_type: 'audio/mpeg',
        stream_url: '/api/media/local/track-1',
      },
    })

    expect(chat.messages[1].media).toEqual(expect.objectContaining({ status: 'ready', title: '慢慢来' }))

    socket.message({ type: 'media.playing', playback_id: 'playback-1' })

    expect(chat.messages[1].media).toEqual(expect.objectContaining({ status: 'playing' }))
  })

  it('keeps browser autoplay blocking visible instead of claiming playback', async () => {
    const chat = useChatStore()
    await chat.init()
    const socket = FakeWebSocket.instances[0]
    socket.open()

    expect(chat.send('放一首歌')).toBe(true)
    socket.message({
      type: 'media.ready',
      media: {
        playback_id: 'playback-1',
        track_id: 'track-1',
        title: '慢慢来',
        artist: '夜晚',
        provider_id: 'local_library',
        mime_type: 'audio/mpeg',
        stream_url: '/api/media/local/track-1',
      },
    })
    socket.message({
      type: 'media.autoplay_blocked',
      playback_id: 'playback-1',
      message: '浏览器需要你点击一次播放。',
    })

    expect(chat.messages[1].media).toEqual(
      expect.objectContaining({ status: 'autoplay_blocked', message: '浏览器需要你点击一次播放。' }),
    )
  })
})
