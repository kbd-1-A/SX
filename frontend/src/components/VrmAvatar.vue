<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import type { VRM } from '@pixiv/three-vrm'
import { applyMaskExpression, getMaskStyle } from '../lib/maskVrm'

const props = defineProps<{ mask: string }>()

const containerRef = ref<HTMLDivElement>()
const currentStyle = ref(getMaskStyle(props.mask))

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let vrm: VRM | null = null
let raf = 0
let bgTarget = new THREE.Color(getMaskStyle(props.mask).bg)
let bgCurrent = bgTarget.clone()

function init() {
  const el = containerRef.value
  if (!el) return
  const w = el.clientWidth || 300
  const h = el.clientHeight || 360

  scene = new THREE.Scene()
  scene.background = bgCurrent.clone()

  // 窄条布局（aspect≈0.32）：fov 得够大、相机得对准数字人，
  // 否则数字人（position.y=-1.15 下移后）落在视野外被视锥剔除 → 画面空白
  camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 100)
  camera.position.set(0, 0.3, -3.7)
  camera.lookAt(0, -0.36, 0)

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setSize(w, h)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  el.appendChild(renderer.domElement)

  scene.add(new THREE.AmbientLight(0xffffff, 0.75))
  const dir = new THREE.DirectionalLight(0xffffff, 1.1)
  dir.position.set(1, 2, 1.5)
  scene.add(dir)
  const fill = new THREE.DirectionalLight(0xffffff, 0.4)
  fill.position.set(-1, 0.5, 1)
  scene.add(fill)

  loadModel()
  animate()

  const ro = new ResizeObserver(() => {
    if (!renderer || !camera || !el) return
    const rw = el.clientWidth || 300
    const rh = el.clientHeight || 360
    renderer.setSize(rw, rh)
    camera.aspect = rw / rh
    camera.updateProjectionMatrix()
  })
  ro.observe(el)
}

async function loadModel() {
  const loader = new GLTFLoader()
  loader.register((parser: any) => new VRMLoaderPlugin(parser))
  const gltf = await loader.loadAsync('/models/three-vrm-girl.vrm')
  vrm = gltf.userData.vrm as VRM
  VRMUtils.rotateVRM0(vrm)
  vrm.scene.position.y = -1.15
  // 窄条面板里模型原宽会超出水平视野被裁剪，缩放到适配宽度
  vrm.scene.scale.setScalar(0.85)
  scene?.add(vrm.scene)
  applyMaskExpression(vrm, props.mask)
}

function animate() {
  raf = requestAnimationFrame(animate)
  if (vrm) vrm.update(0.016)
  // 背景色向目标色过渡
  bgCurrent.lerp(bgTarget, 0.08)
  if (scene) scene.background = bgCurrent
  renderer?.render(scene as THREE.Scene, camera as THREE.PerspectiveCamera)
}

watch(
  () => props.mask,
  (m) => {
    currentStyle.value = getMaskStyle(m)
    bgTarget = new THREE.Color(currentStyle.value.bg)
    if (vrm) applyMaskExpression(vrm, m)
  },
)

onMounted(init)
onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  renderer?.dispose()
  if (renderer?.domElement && containerRef.value) {
    containerRef.value.removeChild(renderer.domElement)
  }
})
</script>

<template>
  <div style="height: 100%; position: relative; overflow: hidden">
    <div ref="containerRef" style="height: 100%; width: 100%" />
    <div
      style="
        position: absolute;
        left: 0;
        right: 0;
        bottom: 12px;
        text-align: center;
        color: rgba(255, 255, 255, 0.92);
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
      "
    >
      <div style="font-size: 15px; font-weight: 600">{{ currentStyle.label }}</div>
      <div style="font-size: 12px; opacity: 0.85; margin-top: 2px">
        {{ currentStyle.tagline }}
      </div>
    </div>
  </div>
</template>
