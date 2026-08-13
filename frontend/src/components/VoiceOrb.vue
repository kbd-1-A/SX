<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import type { AgentMainState } from '../types/agentEvents'

const props = defineProps<{
  state: AgentMainState
  visible: boolean
  amplitude: number
}>()

const host = ref<HTMLDivElement | null>(null)
let renderer: THREE.WebGLRenderer | null = null
let camera: THREE.PerspectiveCamera | null = null
let scene: THREE.Scene | null = null
let points: THREE.Points | null = null
let geometry: THREE.BufferGeometry | null = null
let material: THREE.PointsMaterial | null = null
let animationFrame = 0
let resizeObserver: ResizeObserver | null = null
let targetVisibility = 0
let currentVisibility = 0
let targetEnergy = 0.12
let currentEnergy = 0.12
let targetColor = new THREE.Color('#e8b86b')
const currentColor = new THREE.Color('#e8b86b')
const PARTICLE_COUNT = 4200
const basePositions = new Float32Array(PARTICLE_COUNT * 3)
const offsets = new Float32Array(PARTICLE_COUNT)

function seedParticles() {
  for (let index = 0; index < PARTICLE_COUNT; index += 1) {
    const radius = Math.cbrt(Math.random())
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    const elongated = 0.82 + Math.random() * 0.3
    const baseIndex = index * 3
    basePositions[baseIndex] = radius * Math.sin(phi) * Math.cos(theta) * elongated
    basePositions[baseIndex + 1] = radius * Math.cos(phi) * (1.04 + Math.random() * 0.12)
    basePositions[baseIndex + 2] = radius * Math.sin(phi) * Math.sin(theta) * elongated
    offsets[index] = Math.random() * Math.PI * 2
  }
}

function targetForState(state: AgentMainState) {
  if (state === 'listening') return { energy: 0.34 + props.amplitude * 0.7, color: '#67d8c8' }
  if (state === 'thinking') return { energy: 0.48, color: '#e8b86b' }
  if (state === 'speaking') return { energy: 0.62, color: '#86bdf5' }
  return { energy: 0.12, color: '#c99b62' }
}

function syncTargets() {
  targetVisibility = props.visible ? 1 : 0
  const next = targetForState(props.state)
  targetEnergy = next.energy
  targetColor = new THREE.Color(next.color)
}

function resize() {
  if (!host.value || !renderer || !camera) return
  const width = Math.max(1, host.value.clientWidth)
  const height = Math.max(1, host.value.clientHeight)
  renderer.setSize(width, height, false)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75))
  camera.aspect = width / height
  camera.updateProjectionMatrix()
}

function animate(timestamp = 0) {
  if (!renderer || !scene || !camera || !geometry || !material || !points) return
  const time = timestamp * 0.001
  currentVisibility += (targetVisibility - currentVisibility) * 0.055
  currentEnergy += (targetEnergy - currentEnergy) * 0.05
  currentColor.lerp(targetColor, 0.045)
  material.color.copy(currentColor)
  material.opacity = Math.max(0, Math.min(0.92, currentVisibility * 0.9))

  const positions = geometry.attributes.position.array as Float32Array
  const breath = 1 + Math.sin(time * 1.25) * 0.025 + currentEnergy * 0.075
  const stateRate = props.state === 'speaking' ? 4.2 : props.state === 'listening' ? 2.5 : 1.4
  for (let index = 0; index < PARTICLE_COUNT; index += 1) {
    const baseIndex = index * 3
    const phase = offsets[index]
    const wave = Math.sin(time * stateRate + phase) * currentEnergy * 0.075
    const scale = breath + wave
    positions[baseIndex] = basePositions[baseIndex] * scale
    positions[baseIndex + 1] = basePositions[baseIndex + 1] * scale + Math.sin(time * 0.8 + phase) * 0.018
    positions[baseIndex + 2] = basePositions[baseIndex + 2] * scale
  }
  geometry.attributes.position.needsUpdate = true
  points.rotation.y = time * (0.08 + currentEnergy * 0.09)
  points.rotation.z = Math.sin(time * 0.22) * 0.08
  points.scale.setScalar(Math.max(0.001, currentVisibility * (0.86 + currentEnergy * 0.18)))
  renderer.render(scene, camera)
  animationFrame = requestAnimationFrame(animate)
}

onMounted(() => {
  if (!host.value) return
  seedParticles()
  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(44, 1, 0.1, 20)
  camera.position.set(0, 0, 4.2)
  camera.lookAt(0, 0, 0)
  geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(basePositions), 3))
  material = new THREE.PointsMaterial({
    color: currentColor,
    size: 0.018,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })
  points = new THREE.Points(geometry, material)
  scene.add(points)
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
  renderer.setClearColor(0x000000, 0)
  host.value.appendChild(renderer.domElement)
  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(host.value)
  syncTargets()
  resize()
  animationFrame = requestAnimationFrame(animate)
})

watch(() => [props.state, props.visible, props.amplitude] as const, syncTargets)

onBeforeUnmount(() => {
  cancelAnimationFrame(animationFrame)
  resizeObserver?.disconnect()
  geometry?.dispose()
  material?.dispose()
  renderer?.dispose()
  renderer?.domElement.remove()
})
</script>

<template>
  <div ref="host" class="voice-orb" aria-hidden="true" />
</template>

<style scoped>
.voice-orb { width: 100%; height: 100%; min-width: 0; min-height: 0; }
.voice-orb :deep(canvas) { display: block; width: 100%; height: 100%; }
</style>
