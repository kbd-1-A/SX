import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { FOUNDATION_REPLAY } from '../fixtures/foundationReplay'
import { useAgentStateStore } from './agentState'

describe('agentState', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('ignores stale events from a superseded turn', () => {
    const agent = useAgentStateStore()
    agent.applyEvent({
      type: 'agent.state',
      turn_id: 'turn_new',
      state: 'listening',
      emotion: 'neutral',
    })
    const applied = agent.applyEvent({
      type: 'agent.state',
      turn_id: 'turn_old',
      state: 'speaking',
      emotion: 'warm',
    })

    expect(applied).toBe(false)
    expect(agent.state).toBe('listening')
    expect(agent.activeTurnId).toBe('turn_new')
  })

  it('persists state transitions through the fixed foundation replay', async () => {
    const agent = useAgentStateStore()

    await agent.replay(FOUNDATION_REPLAY, 0)

    expect(agent.state).toBe('idle')
    expect(agent.emotion).toBe('neutral')
    expect(agent.replaying).toBe(false)
    expect(agent.eventLog.map((entry) => entry.event.type)).toEqual(
      FOUNDATION_REPLAY.map((event) => event.type),
    )
    expect(agent.eventLog.every((entry) => entry.applied)).toBe(true)
    expect(agent.protocolConnected).toBe(false)
  })

  it('keeps application activity disabled unless explicitly enabled', () => {
    const agent = useAgentStateStore()

    expect(agent.sources.app_activity).toBe(false)
    agent.configureSources({ app_activity: true })
    expect(agent.sources.app_activity).toBe(true)
  })
})
