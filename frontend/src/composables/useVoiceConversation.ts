/**
 * 语音对话装配（composable）：把「麦克风采集 → /ws/voice 转写 →
 * 送进对话 → TTS 播报回复 → 插话打断」整条链路封装成可复用单元。
 *
 * 从 RealtimeFoundationPanel 提炼，供陪伴模式等视图直接使用；
 * 面板侧的高级设置（选麦克风/数据源开关/回放/日志）仍保留在原处。
 *
 * 注意：同一时刻只应有一个视图挂载本 composable（聊天/陪伴互斥渲染），
 * 否则 TTS 会因重复订阅 reply 事件而播报两遍。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { MicrophoneCapture } from '../audio/capture'
import { VoiceProtocolClient } from '../audio/voiceClient'
import { VoiceResponseController } from '../audio/voiceResponse'
import { useAgentStateStore } from '../stores/agentState'
import { useChatStore } from '../stores/chat'
import type { VoiceServerEvent } from '../types/agentEvents'

export type TranscriptionStatus = 'idle' | 'listening' | 'processing' | 'error'

export function useVoiceConversation() {
  const agent = useAgentStateStore()
  const chat = useChatStore()

  const captureError = ref('')
  const lastTranscript = ref('')
  const transcriptionStatus = ref<TranscriptionStatus>('idle')
  const captureTransitioning = ref(false)

  let client: VoiceProtocolClient | null = null
  let capture: MicrophoneCapture | null = null
  let unsubscribeReply: (() => void) | null = null

  const voiceResponse = new VoiceResponseController({
    onWaiting: (requestId) => agent.transitionLocal('thinking', requestId, 'neutral', true),
    onPlaybackStart: (requestId) => agent.transitionLocal('speaking', requestId, 'warm', true),
    onPlaybackComplete: (requestId) => agent.transitionLocal('idle', requestId, 'neutral', true),
  })

  const capturing = computed(() => agent.captureActive)
  /** 转写处理中（此时不能开始新采集） */
  const voiceTurnBusy = computed(() => transcriptionStatus.value === 'processing')

  function makeClient() {
    if (client) return client
    client = new VoiceProtocolClient(
      (event: VoiceServerEvent) => {
        agent.applyEvent(event, 'server')
        if (event.type === 'asr.final') {
          transcriptionStatus.value = 'listening'
          deliverTranscript(event.text)
        } else if (event.type === 'turn.error' && event.code.startsWith('asr')) {
          transcriptionStatus.value = 'error'
        } else if (event.type === 'turn.error' && event.code === 'no_speech') {
          transcriptionStatus.value = 'listening'
        } else if (event.type === 'turn.done') {
          transcriptionStatus.value = agent.captureActive ? 'listening' : 'idle'
        }
      },
      (connected) => agent.setProtocolConnected(connected),
    )
    return client
  }

  function makeCapture() {
    if (capture) return capture
    capture = new MicrophoneCapture({
      onLevel: (level) => agent.setAmplitude(level),
      onSpeechStart: (sampleRate) => {
        try {
          const turnId = makeClient().beginTurn(sampleRate)
          if (!turnId) return false
          // 插话打断：正在播报/生成回复时，用户一开口就停掉
          if (voiceResponse.activeRequestId || chat.isReplyPending) {
            voiceResponse.cancel()
            chat.interruptForSpeech()
          }
          agent.transitionLocal('listening', turnId, 'neutral', true)
          transcriptionStatus.value = 'listening'
          return true
        } catch (error) {
          captureError.value = error instanceof Error ? error.message : '语音轮次没有启动。'
          return false
        }
      },
      onAudio: (samples) => makeClient().sendAudio(samples),
      onSpeechEnd: (reason) => {
        transcriptionStatus.value = 'processing'
        makeClient().endTurn(reason)
      },
      onError: (message) => {
        captureError.value = message
      },
    })
    return capture
  }

  function deliverTranscript(text: string) {
    const normalized = text.trim()
    if (!normalized) return
    lastTranscript.value = normalized
    if (chat.sendVoice(normalized)) {
      captureError.value = ''
      return
    }
    captureError.value = chat.lastError || '已经识别到语音，但没有发送进当前对话。'
  }

  async function startCapture() {
    if (captureTransitioning.value || agent.captureActive || voiceTurnBusy.value) return
    captureTransitioning.value = true
    captureError.value = ''
    agent.clearError()
    if (!agent.sources.microphone) {
      captureError.value = '麦克风数据来源被关闭了，请到聊天模式「实时基础」里开启。'
      captureTransitioning.value = false
      return
    }
    try {
      await makeClient().connect()
      makeClient().configureSources(agent.sources)
      await makeCapture().start()
      agent.setMicPermission('granted')
      agent.setCaptureActive(true)
      transcriptionStatus.value = 'listening'
    } catch (error) {
      const name = error instanceof DOMException ? error.name : ''
      if (name === 'NotAllowedError') {
        agent.setMicPermission('denied')
        // 浏览器拒绝后不会再弹授权框，必须引导用户手动改权限
        captureError.value =
          '麦克风权限被拒绝了：点地址栏左侧的小锁图标，把「麦克风」改成允许，再点一次麦克风按钮。'
      } else if (name === 'NotFoundError') {
        captureError.value = '没有找到可用的麦克风设备。'
      } else {
        captureError.value = error instanceof Error ? error.message : '麦克风启动失败。'
      }
      await capture?.stop('manual')
      capture = null
      // 回到 idle 而不是卡在 error：错误文案已由 captureError 展示，按钮保持可重试
      transcriptionStatus.value = 'idle'
      agent.setCaptureActive(false)
    } finally {
      captureTransitioning.value = false
    }
  }

  async function stopCapture() {
    if (captureTransitioning.value) return
    captureTransitioning.value = true
    const activeCapture = capture
    capture = null
    try {
      await activeCapture?.stop('manual')
    } finally {
      agent.setCaptureActive(false)
      agent.setAmplitude(0)
      agent.clearError()
      captureError.value = ''
      transcriptionStatus.value = client?.awaitingTurnCompletion ? 'processing' : 'idle'
      captureTransitioning.value = false
    }
  }

  async function toggleCapture() {
    if (agent.captureActive) {
      await stopCapture()
    } else {
      await startCapture()
    }
  }

  onMounted(() => {
    unsubscribeReply = chat.subscribeReply((event) => voiceResponse.handle(event))
  })

  onBeforeUnmount(async () => {
    unsubscribeReply?.()
    voiceResponse.cancel()
    await stopCapture()
    client?.close()
    client = null
  })

  return {
    captureError,
    lastTranscript,
    transcriptionStatus,
    captureTransitioning,
    capturing,
    voiceTurnBusy,
    startCapture,
    stopCapture,
    toggleCapture,
  }
}
