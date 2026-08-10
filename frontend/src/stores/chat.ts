import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  proactiveEventId?: number
  artifacts?: ChatArtifact[]
  artifactFailure?: ArtifactFailure
  research?: ResearchState
}

export interface ChatArtifact {
  id: string
  path: string
  display_name: string
  target: 'desktop' | 'output'
  mime_type: 'text/markdown'
  size_bytes: number
  sha256: string
}

export interface ArtifactFailure {
  code: string
  message: string
}

export interface ResearchSource {
  citation_id: number
  title: string
  url: string
  domain: string
  source_type: 'official' | 'organization' | 'secondary'
}

export interface ResearchState {
  status: 'running' | 'completed' | 'failed'
  query: string
  retrieved_at?: string
  source_count?: number
  sources?: ResearchSource[]
  warnings?: string[]
  code?: string
  message?: string
}

export interface ChatTask {
  id: number
  created_at: string
  last_message_at: string
  message_count: number
  preview: string
}

export interface EmotionState {
  emotion: string
  emotion_label: string
  intensity: number
  confidence: number
  user_need: string
  user_need_label: string
  strategy: string
  strategy_label: string
  risk_level: string
  sensitive_scene: string
  emotion_scores?: Record<string, number>
  strategy_scores?: Record<string, number>
}

export type ConnectionStatus = 'connecting' | 'online' | 'reconnecting' | 'offline'
export type ChatReplyOrigin = 'text' | 'voice'

export interface ChatReplyEvent {
  type: 'start' | 'chunk' | 'done' | 'error' | 'interrupted'
  requestId: string
  origin: ChatReplyOrigin
  content?: string
}

interface ActiveReply {
  requestId: string
  origin: ChatReplyOrigin
}

interface PendingVoiceMessage {
  content: string
  requestId: string
}

const DEFAULT_EMOTION: EmotionState = {
  emotion: 'neutral',
  emotion_label: '平稳',
  intensity: 0,
  confidence: 0,
  user_need: 'company',
  user_need_label: '想有人陪着',
  strategy: 'catch_up',
  strategy_label: '自然接话',
  risk_level: 'none',
  sensitive_scene: 'none',
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const tasks = ref<ChatTask[]>([])
  const currentSessionId = ref<number | null>(null)
  const status = ref<ConnectionStatus>('offline')
  const connected = computed(() => status.value === 'online')
  const currentMask = ref('daily_companion')
  const currentReplyMode = ref('catch_up')
  const currentEmotion = ref<EmotionState>({ ...DEFAULT_EMOTION })
  const lastError = ref('')
  const isStreaming = computed(() => messages.value.some((m) => m.streaming))
  const isReplyPending = ref(false)
  const userInteractionSequence = ref(0)
  let ws: WebSocket | null = null
  let reconnectTimer: number | null = null
  let reconnectAttempts = 0
  let stopRequested = false
  let pendingProactiveMessages: Array<{ id: number; content: string }> = []
  let activeReply: ActiveReply | null = null
  let pendingVoiceMessages: PendingVoiceMessage[] = []
  const replyListeners = new Set<(event: ChatReplyEvent) => void>()
  let requestSequence = 0

  function emitReply(event: ChatReplyEvent) {
    for (const listener of replyListeners) listener(event)
  }

  function completeActiveReply(type: Extract<ChatReplyEvent['type'], 'done' | 'error' | 'interrupted'>) {
    if (!activeReply) return
    const reply = activeReply
    activeReply = null
    isReplyPending.value = false
    emitReply({ type, ...reply })
  }

  function subscribeReply(listener: (event: ChatReplyEvent) => void) {
    replyListeners.add(listener)
    return () => replyListeners.delete(listener)
  }

  function makeRequestId() {
    requestSequence += 1
    return `chat_${Date.now().toString(36)}_${requestSequence.toString(36)}`
  }

  function flushPendingVoiceMessages() {
    if (activeReply || !ws || ws.readyState !== WebSocket.OPEN) return
    const next = pendingVoiceMessages.shift()
    if (!next) return
    if (!sendMessage(next.content, 'voice', next.requestId, false)) {
      pendingVoiceMessages.unshift(next)
    }
  }

  function flushProactiveMessages() {
    if (isStreaming.value || !pendingProactiveMessages.length) return
    const pending = pendingProactiveMessages
    pendingProactiveMessages = []
    for (const event of pending) {
      if (messages.value.some((message) => message.proactiveEventId === event.id)) continue
      messages.value.push({
        id: -event.id,
        role: 'assistant',
        content: event.content,
        proactiveEventId: event.id,
      })
    }
  }

  function receiveProactiveMessages(events: Array<{ id: number; content: string }>) {
    for (const event of events) {
      if (
        messages.value.some((message) => message.proactiveEventId === event.id) ||
        pendingProactiveMessages.some((pending) => pending.id === event.id)
      ) {
        continue
      }
      if (isStreaming.value) {
        pendingProactiveMessages.push(event)
      } else {
        messages.value.push({
          id: -event.id,
          role: 'assistant',
          content: event.content,
          proactiveEventId: event.id,
        })
      }
    }
  }

  function resetTurnState() {
    currentMask.value = 'daily_companion'
    currentReplyMode.value = 'catch_up'
    currentEmotion.value = { ...DEFAULT_EMOTION }
  }

  function ensureStreamingAssistantMessage() {
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'assistant' && last.streaming) return last
    const message: ChatMessage = {
      id: -1,
      role: 'assistant',
      content: '',
      streaming: true,
    }
    messages.value.push(message)
    return message
  }

  function wsUrl() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const query = currentSessionId.value ? `?session_id=${currentSessionId.value}` : ''
    return `${proto}://${location.host}/ws/chat${query}`
  }

  function connect(reconnecting = false) {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return

    status.value = reconnecting ? 'reconnecting' : 'connecting'
    const socket = new WebSocket(wsUrl())
    ws = socket

    socket.onopen = () => {
      if (ws !== socket) return
      status.value = 'online'
      reconnectAttempts = 0
      stopRequested = false
      lastError.value = ''
      flushPendingVoiceMessages()
    }

    socket.onclose = () => {
      if (ws !== socket) return
      const last = messages.value[messages.value.length - 1]
      if (last?.streaming) {
        last.streaming = false
        if (!stopRequested) {
          lastError.value = '回复中断了，我正在重新连接。'
        }
      }
      if (activeReply) completeActiveReply(stopRequested ? 'interrupted' : 'error')
      stopRequested = false
      status.value = 'offline'
      scheduleReconnect()
    }

    socket.onerror = () => {
      if (ws !== socket) return
      status.value = 'offline'
    }

    socket.onmessage = (ev) => {
      let data: any
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }
      if (data.type === 'chunk') {
        const last = ensureStreamingAssistantMessage()
        last.content += data.content
        if (activeReply) emitReply({ type: 'chunk', ...activeReply, content: data.content })
      } else if (data.type === 'artifact.created') {
        const artifact = data.artifact as ChatArtifact | undefined
        if (!artifact?.id) return
        const last = ensureStreamingAssistantMessage()
        const artifacts = last.artifacts || (last.artifacts = [])
        if (!artifacts.some((item) => item.id === artifact.id)) artifacts.push(artifact)
      } else if (data.type === 'artifact.failed') {
        const last = ensureStreamingAssistantMessage()
        last.artifactFailure = {
          code: data.code || 'file_create_failed',
          message: data.message || '文件没有创建成功。',
        }
      } else if (data.type === 'research.started') {
        const last = ensureStreamingAssistantMessage()
        last.research = {
          status: 'running',
          query: data.query || '当前主题',
        }
      } else if (data.type === 'research.completed') {
        const last = ensureStreamingAssistantMessage()
        const research = data.research || {}
        last.research = {
          status: 'completed',
          query: research.query || last.research?.query || '当前主题',
          retrieved_at: research.retrieved_at,
          source_count: research.source_count || 0,
          sources: research.sources || [],
          warnings: research.warnings || [],
        }
      } else if (data.type === 'research.failed') {
        const last = ensureStreamingAssistantMessage()
        last.research = {
          status: 'failed',
          query: last.research?.query || '当前主题',
          code: data.code || 'research_failed',
          message: data.message || '联网研究没有完成。',
        }
      } else if (data.type === 'done') {
        const last = messages.value[messages.value.length - 1]
        if (last?.streaming) last.streaming = false
        flushProactiveMessages()
        if (data.mask) currentMask.value = data.mask
        if (data.reply_mode) currentReplyMode.value = data.reply_mode
        if (data.emotion_state) currentEmotion.value = data.emotion_state
        completeActiveReply('done')
        loadTasks()
        flushPendingVoiceMessages()
      } else if (data.type === 'error') {
        const last = messages.value[messages.value.length - 1]
        const hadPartialReply = Boolean(last?.role === 'assistant' && last.streaming)
        if (last?.streaming) last.streaming = false
        lastError.value = data.message || '时叙暂时没接住这句话，请稍后再试。'
        if (!hadPartialReply) {
          messages.value.push({
            id: -1,
            role: 'assistant',
            content: lastError.value,
            streaming: false,
          })
        }
        flushProactiveMessages()
        completeActiveReply('error')
        flushPendingVoiceMessages()
      }
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer !== null) return
    const delay = Math.min(5000, 800 * 2 ** reconnectAttempts)
    reconnectAttempts += 1
    status.value = 'reconnecting'
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      connect(true)
    }, delay)
  }

  function closeSocket() {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    const socket = ws
    ws = null
    pendingVoiceMessages = []
    completeActiveReply('interrupted')
    if (socket && socket.readyState !== WebSocket.CLOSED) socket.close()
  }

  async function loadTasks() {
    try {
      const res = await fetch('/api/sessions?limit=30')
      if (!res.ok) return
      tasks.value = await res.json()
      if (!currentSessionId.value && tasks.value.length) {
        currentSessionId.value = tasks.value[0].id
      }
    } catch {
      // WebSocket 重连期间，任务列表失败不应影响当前会话。
    }
  }

  async function loadHistory() {
    try {
      const sessionQuery = currentSessionId.value ? `&session_id=${currentSessionId.value}` : ''
      const res = await fetch(`/api/messages?limit=50${sessionQuery}`)
      if (res.ok) {
        const data = await res.json()
        messages.value = data.map((m: any) => ({
          id: m.id,
          role: m.role,
          content: m.content,
        }))
        pendingProactiveMessages = []
      }
    } catch {
      lastError.value = '历史消息暂时没加载出来，重连后会再试。'
    }
  }

  async function switchTask(sessionId: number) {
    if (currentSessionId.value === sessionId) return
    currentSessionId.value = sessionId
    resetTurnState()
    lastError.value = ''
    messages.value = []
    pendingProactiveMessages = []
    closeSocket()
    await loadHistory()
    connect()
  }

  async function newTask() {
    const res = await fetch('/api/sessions', { method: 'POST' })
    if (!res.ok) {
      lastError.value = '新开任务失败，先别急，我这边没接住。'
      return
    }
    const task = await res.json()
    tasks.value = [task, ...tasks.value.filter((t) => t.id !== task.id)]
    currentSessionId.value = task.id
    resetTurnState()
    lastError.value = ''
    messages.value = []
    pendingProactiveMessages = []
    closeSocket()
    connect()
  }

  function sendMessage(
    content: string,
    origin: ChatReplyOrigin,
    requestId = makeRequestId(),
    appendUserMessage = true,
  ): boolean {
    const text = content.trim()
    if (!text) return false
    if (text.length > 4000) {
      lastError.value = '这条消息有点长，请控制在 4000 个字符以内。'
      return false
    }
    if (activeReply || isStreaming.value) {
      lastError.value = '时叙正在回复，等这句话结束或先点停止。'
      return false
    }
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      lastError.value = '时叙暂时没连上，这句话先留在输入框里。'
      if (!ws || ws.readyState === WebSocket.CLOSED) scheduleReconnect()
      return false
    }
    lastError.value = ''
    if (appendUserMessage) messages.value.push({ id: -1, role: 'user', content: text })
    if (origin === 'text') userInteractionSequence.value += 1
    activeReply = { requestId, origin }
    isReplyPending.value = true
    emitReply({ type: 'start', ...activeReply })
    ws.send(JSON.stringify({ type: 'message', content: text }))
    loadTasks()
    return true
  }

  function send(content: string): boolean {
    return sendMessage(content, 'text')
  }

  function sendVoice(content: string): string | null {
    const text = content.trim()
    if (!text || text.length > 4000) return null
    const requestId = makeRequestId()
    messages.value.push({ id: -1, role: 'user', content: text })
    userInteractionSequence.value += 1
    pendingVoiceMessages.push({ content: text, requestId })
    lastError.value = ''
    flushPendingVoiceMessages()
    if (!ws || ws.readyState === WebSocket.CLOSED) scheduleReconnect()
    return requestId
  }

  function stop() {
    const last = messages.value[messages.value.length - 1]
    if (last && last.streaming) last.streaming = false
    flushProactiveMessages()
    const hadActiveReply = activeReply !== null
    completeActiveReply('interrupted')
    if (ws && ws.readyState === WebSocket.OPEN) {
      stopRequested = true
      ws.close()
    } else {
      scheduleReconnect()
    }
    return hadActiveReply
  }

  function interruptForSpeech() {
    pendingVoiceMessages = []
    if (!activeReply && !isStreaming.value) return false
    return stop()
  }

  async function init() {
    await loadTasks()
    await loadHistory()
    connect()
  }

  return {
    messages,
    tasks,
    currentSessionId,
    status,
    connected,
    currentMask,
    currentReplyMode,
    currentEmotion,
    lastError,
    isStreaming,
    isReplyPending,
    userInteractionSequence,
    init,
    loadTasks,
    loadHistory,
    switchTask,
    newTask,
    send,
    sendVoice,
    stop,
    interruptForSpeech,
    receiveProactiveMessages,
    subscribeReply,
  }
})
