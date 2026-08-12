<script setup lang="ts">
/**
 * 陪伴模式核心视觉体：语音粒子球。
 *
 * - three.js Points + GLSL simplex noise 顶点扰动 + 加色混合发光；
 * - 律动靠「合成语音包络」：浏览器 SpeechSynthesis 不过 Web Audio，
 *   拿不到真实音量，所以说话状态用复合正弦模拟人声的强弱起伏，
 *   由父组件根据流式回复状态切换 state 即可；
 * - 颜色/运动参数变化走逐帧 lerp，切换面具/情绪时平滑过渡。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import type { OrbState, OrbStyle } from '../lib/orbStyle'
import { DEFAULT_ORB_STYLE } from '../lib/orbStyle'

const props = withDefaults(
  defineProps<{ style?: OrbStyle; state?: OrbState; particleCount?: number }>(),
  { style: () => DEFAULT_ORB_STYLE, state: 'idle', particleCount: 15000 },
)

const containerRef = ref<HTMLDivElement>()

const NOISE_GLSL = `
vec3 mod289(vec3 x){return x - floor(x * (1.0/289.0)) * 289.0;}
vec4 mod289(vec4 x){return x - floor(x * (1.0/289.0)) * 289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}
float snoise(vec3 v){
  const vec2 C = vec2(1.0/6.0, 1.0/3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(
      i.z + vec4(0.0, i1.z, i2.z, 1.0))
      + i.y + vec4(0.0, i1.y, i2.y, 1.0))
      + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}
`

const VERTEX_SHADER = `
uniform float uTime;
uniform float uAmp;
uniform float uNoiseAmp;
uniform float uNoiseSpeed;
uniform float uBreathe;
uniform float uSize;
uniform float uScaleFactor;
attribute float aScale;
varying float vDisp;
varying float vCore;
${NOISE_GLSL}
void main() {
  vec3 dir = normalize(position);
  float baseR = length(position);
  float t = uTime * uNoiseSpeed;
  float n = snoise(dir * 2.2 + vec3(0.0, t, t * 0.7));
  float breathe = sin(uTime * 0.8) * 0.025 * uBreathe;
  // 说话：高频抖动 + 整球随声脉冲膨胀
  float speech = snoise(dir * 5.0 + vec3(t * 3.0)) * uAmp * 0.3;
  float pulse = uAmp * 0.08;
  float r = baseR * (1.0 + n * uNoiseAmp + breathe + speech) + pulse;
  vec3 pos = dir * r;
  vDisp = clamp(n * 0.5 + 0.5 + uAmp * 0.4, 0.0, 1.0);
  vCore = 1.0 - baseR;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_Position = projectionMatrix * mv;
  // aScale 是「世界尺寸」，乘投影系数换算成像素，保证全屏下粒子肉眼可见
  gl_PointSize = uSize * aScale * uScaleFactor / -mv.z;
}
`

const FRAGMENT_SHADER = `
uniform vec3 uColorCore;
uniform vec3 uColorGlow;
uniform float uAmp;
varying float vDisp;
varying float vCore;
void main() {
  vec2 uv = gl_PointCoord - 0.5;
  float d = length(uv);
  if (d > 0.5) discard;
  float alpha = smoothstep(0.5, 0.05, d);
  vec3 color = mix(uColorCore, uColorGlow, vDisp);
  // 球心略亮体现层次，但克制——加色混合下球心粒子堆叠极易过曝成白团
  color += uColorCore * vCore * 0.25;
  // 说话时整体提亮
  color += uColorGlow * uAmp * 0.4;
  color *= 0.85;
  gl_FragColor = vec4(color, alpha * 0.55);
}
`

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let points: THREE.Points | null = null
let material: THREE.ShaderMaterial | null = null
let raf = 0
let resizeObserver: ResizeObserver | null = null
let clock: THREE.Clock | null = null

// 语音包络与颜色过渡的逐帧状态
let amp = 0
let elapsed = 0
const colorCore = new THREE.Color(DEFAULT_ORB_STYLE.core)
const colorGlow = new THREE.Color(DEFAULT_ORB_STYLE.glow)
const targetCore = colorCore.clone()
const targetGlow = colorGlow.clone()
const motion = { noiseAmp: 0, noiseSpeed: 0, breathe: 0, size: 0, speed: 1 }
const motionTarget = { ...motion }

function applyStyle(style: OrbStyle) {
  targetCore.set(style.core)
  targetGlow.set(style.glow)
  motionTarget.noiseAmp = style.noiseAmp
  motionTarget.noiseSpeed = style.noiseSpeed
  motionTarget.breathe = style.breathe
  motionTarget.size = style.size
  motionTarget.speed = style.speed
}

/** 合成语音包络：模拟人声说话的强弱节奏（复合正弦 + 快慢两档） */
function speechEnvelope(t: number): number {
  const fast = Math.abs(Math.sin(t * 6.3) * Math.sin(t * 2.7))
  const slow = Math.abs(Math.sin(t * 9.1) * 0.5 + Math.sin(t * 3.3) * 0.5)
  return Math.min(1, (fast * 0.7 + slow * 0.5))
}

function envelopeTarget(state: OrbState, t: number): number {
  switch (state) {
    case 'speaking':
      return 0.2 + 0.8 * speechEnvelope(t)
    case 'thinking':
      return 0.1 + 0.08 * Math.abs(Math.sin(t * 13))
    case 'listening':
      return 0.12 + 0.08 * Math.sin(t * 1.8)
    default:
      return 0
  }
}

/**
 * 体积撒点：75% 粒子按 pow 分布向球心聚集（中心密集），25% 落在表面勾勒轮廓。
 * aScale 存粒子的世界尺寸（配合 uScaleFactor 换算像素）。
 */
function buildGeometry(count: number) {
  const positions = new Float32Array(count * 3)
  const scales = new Float32Array(count)
  for (let i = 0; i < count; i += 1) {
    // 均匀随机方向
    const u = Math.random() * 2 - 1
    const theta = Math.random() * Math.PI * 2
    const ring = Math.sqrt(1 - u * u)
    // 中心密集：pow > 1 把半径压向球心；表面层粒子 r=1
    const inner = i % 4 !== 0
    const r = inner ? Math.pow(Math.random(), 2.2) : 1
    positions[i * 3] = Math.cos(theta) * ring * r
    positions[i * 3 + 1] = u * r
    positions[i * 3 + 2] = Math.sin(theta) * ring * r
    // 中心粒子略小更亮，表面粒子略大更透
    scales[i] = inner ? 0.006 + Math.random() * 0.008 : 0.009 + Math.random() * 0.011
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('aScale', new THREE.BufferAttribute(scales, 1))
  return geometry
}

function init() {
  const el = containerRef.value
  if (!el) return
  const w = el.clientWidth || 600
  const h = el.clientHeight || 600

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100)
  camera.position.set(0, 0, 3.0)

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setSize(w, h)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  el.appendChild(renderer.domElement)

  // 投影系数：把粒子的世界尺寸换算成像素（随视口高度与 fov 变化）
  const scaleFactor = () => {
    const vh = el.clientHeight || 600
    return (vh * Math.min(window.devicePixelRatio, 2)) / (2 * Math.tan((45 * Math.PI) / 360))
  }

  material = new THREE.ShaderMaterial({
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    uniforms: {
      uTime: { value: 0 },
      uAmp: { value: 0 },
      uNoiseAmp: { value: props.style.noiseAmp },
      uNoiseSpeed: { value: props.style.noiseSpeed },
      uBreathe: { value: props.style.breathe },
      uSize: { value: props.style.size },
      uScaleFactor: { value: scaleFactor() },
      uColorCore: { value: colorCore },
      uColorGlow: { value: colorGlow },
    },
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })

  points = new THREE.Points(buildGeometry(props.particleCount), material)
  scene.add(points)

  applyStyle(props.style)
  // 初始即落在目标参数上，避免首帧从默认值「飞」过来
  colorCore.copy(targetCore)
  colorGlow.copy(targetGlow)
  Object.assign(motion, motionTarget)

  clock = new THREE.Clock()
  animate()

  resizeObserver = new ResizeObserver(() => {
    if (!renderer || !camera || !el) return
    const rw = el.clientWidth || 600
    const rh = el.clientHeight || 600
    renderer.setSize(rw, rh)
    camera.aspect = rw / rh
    camera.updateProjectionMatrix()
    if (material) material.uniforms.uScaleFactor.value = scaleFactor()
  })
  resizeObserver.observe(el)
}

function animate() {
  raf = requestAnimationFrame(animate)
  if (!renderer || !scene || !camera || !material || !points || !clock) return

  const dt = Math.min(clock.getDelta(), 0.05)
  elapsed += dt * motion.speed

  // 包络：攻击快、释放慢，听感上更贴人声
  const target = envelopeTarget(props.state, elapsed)
  amp += (target - amp) * (target > amp ? 0.4 : 0.06)

  // 颜色与运动参数平滑过渡
  colorCore.lerp(targetCore, 0.06)
  colorGlow.lerp(targetGlow, 0.06)
  motion.noiseAmp += (motionTarget.noiseAmp - motion.noiseAmp) * 0.05
  motion.noiseSpeed += (motionTarget.noiseSpeed - motion.noiseSpeed) * 0.05
  motion.breathe += (motionTarget.breathe - motion.breathe) * 0.05
  motion.size += (motionTarget.size - motion.size) * 0.05
  motion.speed += (motionTarget.speed - motion.speed) * 0.05

  material.uniforms.uTime.value = elapsed
  material.uniforms.uAmp.value = amp
  material.uniforms.uNoiseAmp.value = motion.noiseAmp
  material.uniforms.uNoiseSpeed.value = motion.noiseSpeed
  material.uniforms.uBreathe.value = motion.breathe
  material.uniforms.uSize.value = motion.size

  points.rotation.y += dt * 0.12
  points.rotation.x = Math.sin(elapsed * 0.15) * 0.08

  renderer.render(scene, camera)
}

watch(
  () => props.style,
  (style) => applyStyle(style ?? DEFAULT_ORB_STYLE),
  { deep: true },
)

onMounted(init)
onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  resizeObserver?.disconnect()
  points?.geometry.dispose()
  material?.dispose()
  renderer?.dispose()
  if (renderer?.domElement && containerRef.value?.contains(renderer.domElement)) {
    containerRef.value.removeChild(renderer.domElement)
  }
})
</script>

<template>
  <div ref="containerRef" class="particle-orb" />
</template>

<style scoped>
.particle-orb {
  width: 100%;
  height: 100%;
}
.particle-orb :deep(canvas) {
  display: block;
}
</style>
