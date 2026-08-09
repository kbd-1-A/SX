export const VOICE_PROTOCOL_VERSION = 1 as const

export type AgentMainState = 'idle' | 'listening' | 'thinking' | 'speaking'
export type AgentEmotion = 'neutral' | 'warm' | 'happy' | 'concerned' | 'tired'
export type MicPermission = 'unknown' | 'prompt' | 'granted' | 'denied' | 'unavailable'

export interface DataSourceSettings {
  microphone: boolean
  conversation_memory: boolean
  time_context: boolean
  app_activity: boolean
}

export interface SessionReadyEvent {
  type: 'session.ready'
  session_id: string
  protocol_version: number
  state: AgentMainState
  sources: DataSourceSettings
  asr?: { provider: string; location: string; language: string }
}

export interface SessionConfiguredEvent {
  type: 'session.configured'
  sources: DataSourceSettings
}

export interface AgentStateEvent {
  type: 'agent.state'
  turn_id: string
  state: AgentMainState
  emotion?: AgentEmotion
}

export interface AudioAckEvent {
  type: 'audio.ack'
  turn_id: string
  seq: number
}

export interface AsrFinalEvent {
  type: 'asr.final'
  turn_id: string
  text: string
  language: string
  confidence: number
  duration_ms: number
}

export interface TurnDoneEvent {
  type: 'turn.done'
  turn_id: string
  reason: 'vad_end' | 'manual' | 'interrupted' | 'cancelled' | 'capture_complete' | string
  received_chunks?: number
}

export interface TurnErrorEvent {
  type: 'turn.error'
  turn_id?: string
  code: string
  message: string
}

export type VoiceServerEvent =
  | SessionReadyEvent
  | SessionConfiguredEvent
  | AgentStateEvent
  | AudioAckEvent
  | AsrFinalEvent
  | TurnDoneEvent
  | TurnErrorEvent

export type VoiceClientEvent =
  | { type: 'session.configure'; sources: DataSourceSettings }
  | {
      type: 'audio.start'
      turn_id: string
      sample_rate: number
      channels: 1
      format: 'pcm_s16le'
    }
  | { type: 'audio.chunk'; turn_id: string; seq: number; pcm_s16le_base64: string }
  | { type: 'audio.end'; turn_id: string; reason: 'vad_end' | 'manual' }
  | { type: 'turn.interrupt'; turn_id: string; played_ms: number }
  | { type: 'session.cancel'; turn_id?: string }

export interface AgentEventLogEntry {
  id: number
  receivedAt: number
  source: 'server' | 'local' | 'replay'
  applied: boolean
  event: VoiceServerEvent
}
