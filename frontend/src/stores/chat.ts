import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const connected = ref(false)
  const currentMask = ref('daily_companion')
  let ws: WebSocket | null = null

  function wsUrl() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    return `${proto}://${location.host}/ws/chat`
  }

  function connect() {
    ws = new WebSocket(wsUrl())
    ws.onopen = () => {
      connected.value = true
    }
    ws.onclose = () => {
      connected.value = false
    }
    ws.onerror = () => {
      connected.value = false
    }
    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data)
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
        if (last) last.streaming = false
        if (data.mask) currentMask.value = data.mask
      } else if (data.type === 'error') {
        messages.value.push({
          id: -1,
          role: 'assistant',
          content: data.message,
          streaming: false,
        })
      }
    }
  }

  async function loadHistory() {
    const res = await fetch('/api/messages?limit=50')
    if (res.ok) {
      const data = await res.json()
      messages.value = data.map((m: any) => ({
        id: m.id,
        role: m.role,
        content: m.content,
      }))
    }
  }

  function send(content: string) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    messages.value.push({ id: -1, role: 'user', content })
    ws.send(JSON.stringify({ type: 'message', content }))
  }

  function init() {
    connect()
    loadHistory()
  }

  return { messages, connected, currentMask, init, send }
})
