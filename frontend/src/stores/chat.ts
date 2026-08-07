import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

export interface ChatTask {
  id: number
  created_at: string
  last_message_at: string
  message_count: number
  preview: string
}

export type ConnectionStatus = 'connecting' | 'online' | 'reconnecting' | 'offline'

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const tasks = ref<ChatTask[]>([])
  const currentSessionId = ref<number | null>(null)
  const status = ref<ConnectionStatus>('offline')
  const connected = computed(() => status.value === 'online')
  const currentMask = ref('daily_companion')
  const currentReplyMode = ref('catch_up')
  const lastError = ref('')
  const isStreaming = computed(() => messages.value.some((m) => m.streaming))
  let ws: WebSocket | null = null
  let reconnectTimer: number | null = null
  let reconnectAttempts = 0
  let stopRequested = false

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
        const last = messages.value[messages.value.length - 1]
        if (last && last.streaming) {
          last.content += data.content
        } else {
          messages.value.push({
            id: -1,
            role: 'assistant',
            content: data.content,
            streaming: true,
          })
        }
      } else if (data.type === 'done') {
        const last = messages.value[messages.value.length - 1]
        if (last?.streaming) last.streaming = false
        if (data.mask) currentMask.value = data.mask
        if (data.reply_mode) currentReplyMode.value = data.reply_mode
        loadTasks()
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
      }
    } catch {
      lastError.value = '历史消息暂时没加载出来，重连后会再试。'
    }
  }

  async function switchTask(sessionId: number) {
    if (currentSessionId.value === sessionId) return
    currentSessionId.value = sessionId
    currentMask.value = 'daily_companion'
    currentReplyMode.value = 'catch_up'
    lastError.value = ''
    messages.value = []
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
    currentMask.value = 'daily_companion'
    currentReplyMode.value = 'catch_up'
    lastError.value = ''
    messages.value = []
    closeSocket()
    connect()
  }

  function send(content: string): boolean {
    const text = content.trim()
    if (!text) return false
    if (text.length > 4000) {
      lastError.value = '这条消息有点长，请控制在 4000 个字符以内。'
      return false
    }
    if (isStreaming.value) {
      lastError.value = '时叙正在回复，等这句话结束或先点停止。'
      return false
    }
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      lastError.value = '时叙暂时没连上，这句话先留在输入框里。'
      if (!ws || ws.readyState === WebSocket.CLOSED) scheduleReconnect()
      return false
    }
    lastError.value = ''
    messages.value.push({ id: -1, role: 'user', content: text })
    ws.send(JSON.stringify({ type: 'message', content: text }))
    loadTasks()
    return true
  }

  function stop() {
    const last = messages.value[messages.value.length - 1]
    if (last && last.streaming) last.streaming = false
    if (ws && ws.readyState === WebSocket.OPEN) {
      stopRequested = true
      ws.close()
    } else {
      scheduleReconnect()
    }
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
    lastError,
    isStreaming,
    init,
    loadTasks,
    loadHistory,
    switchTask,
    newTask,
    send,
    stop,
  }
})
