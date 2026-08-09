import type { VoiceServerEvent } from '../types/agentEvents'

export const FOUNDATION_REPLAY: VoiceServerEvent[] = [
  {
    type: 'session.ready',
    session_id: 'replay_session',
    protocol_version: 1,
    state: 'idle',
    sources: {
      microphone: true,
      conversation_memory: true,
      time_context: true,
      app_activity: false,
    },
  },
  {
    type: 'agent.state',
    turn_id: 'replay_turn',
    state: 'listening',
    emotion: 'neutral',
  },
  {
    type: 'agent.state',
    turn_id: 'replay_turn',
    state: 'thinking',
    emotion: 'neutral',
  },
  {
    type: 'agent.state',
    turn_id: 'replay_turn',
    state: 'speaking',
    emotion: 'warm',
  },
  {
    type: 'agent.state',
    turn_id: 'replay_turn',
    state: 'listening',
    emotion: 'neutral',
  },
  {
    type: 'turn.done',
    turn_id: 'replay_turn',
    reason: 'interrupted',
    received_chunks: 12,
  },
  {
    type: 'agent.state',
    turn_id: 'replay_turn',
    state: 'idle',
    emotion: 'neutral',
  },
]
