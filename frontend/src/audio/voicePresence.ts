import type { AgentMainState, MicPermission } from '../types/agentEvents'

export function voicePresenceStatus(state: AgentMainState, captureActive: boolean, starting = false) {
  if (starting) return '正在连接'
  if (!captureActive) return '说话前，先唤醒时叙'
  return ({
    idle: '我在听',
    listening: '听见你了',
    thinking: '让我想一想',
    speaking: '时叙正在说',
  })[state]
}

export function shouldRestoreListening(permission: MicPermission) {
  return permission === 'granted'
}

export function shouldShowPresence(state: AgentMainState) {
  return state !== 'idle'
}
