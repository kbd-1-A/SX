<script setup lang="ts">
import { computed } from 'vue'
import { useAgentStateStore } from '../stores/agentState'

const agent = useAgentStateStore()

const gaze = computed(() => {
  if (agent.state === 'thinking') return { x: '-9px', y: '-4px' }
  if (agent.state === 'listening') return { x: '0px', y: '-5px' }
  if (agent.state === 'speaking') return { x: '3px', y: '0px' }
  return { x: '0px', y: '0px' }
})

const pulse = computed(() => {
  if (agent.state !== 'speaking') return 0
  return Math.max(0.12, agent.amplitude)
})
</script>

<template>
  <section
    class="device-simulator"
    :class="[`is-${agent.state}`, `is-${agent.emotion}`, { 'is-offline': !agent.deviceConnected }]"
  >
    <div class="device-head" aria-label="桌宠双眼设备模拟器">
      <div class="eye">
        <span class="pupil" :style="{ transform: `translate(${gaze.x}, ${gaze.y}) scale(${1 + pulse * 0.08})` }" />
        <span class="lid" />
      </div>
      <div class="eye">
        <span class="pupil" :style="{ transform: `translate(${gaze.x}, ${gaze.y}) scale(${1 + pulse * 0.08})` }" />
        <span class="lid" />
      </div>
    </div>
    <div class="device-readout">
      <span>{{ agent.deviceConnected ? '设备已连接' : '设备模拟离线' }}</span>
      <strong>{{ agent.stateLabel }}</strong>
    </div>
  </section>
</template>

<style scoped>
.device-simulator {
  border: 1px solid #d9e1e5;
  border-radius: 8px;
  background: #172126;
  overflow: hidden;
}

.device-head {
  min-height: 142px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: center;
  padding: 20px 28px;
}

.eye {
  aspect-ratio: 1;
  position: relative;
  overflow: hidden;
  border-radius: 50%;
  border: 4px solid #415159;
  background: #eaf7f5;
  box-shadow: inset 0 0 26px rgba(68, 212, 193, 0.3);
}

.pupil {
  position: absolute;
  width: 36%;
  aspect-ratio: 1;
  left: 32%;
  top: 34%;
  border-radius: 50%;
  background: #1c2d35;
  box-shadow: 0 0 0 10px rgba(69, 205, 188, 0.18);
  transition: transform 180ms ease-out, background 180ms ease-out;
}

.lid {
  position: absolute;
  inset: -54% 0 auto;
  height: 58%;
  background: #172126;
  border-radius: 0 0 50% 50%;
  animation: blink 5.5s infinite;
}

.is-thinking .pupil {
  background: #9d7924;
  box-shadow: 0 0 0 10px rgba(214, 174, 58, 0.2);
}

.is-speaking .pupil {
  background: #c86c5f;
  box-shadow: 0 0 0 10px rgba(220, 117, 100, 0.24);
}

.is-concerned .lid {
  top: -36%;
  animation: none;
}

.is-offline .device-head {
  filter: grayscale(1) brightness(0.58);
}

.device-readout {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  color: #b7c7cc;
  border-top: 1px solid #2f3f46;
  font-size: 12px;
}

.device-readout strong {
  color: #f2f6f7;
}

@keyframes blink {
  0%, 44%, 48%, 100% { transform: translateY(0); }
  46% { transform: translateY(92%); }
}
</style>
