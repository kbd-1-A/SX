import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// 默认连接 8000；并行开发时可用 VITE_BACKEND_TARGET 指向其他后端实例。
export default defineConfig(({ mode }) => {
  const backendTarget = loadEnv(mode, '.', '').VITE_BACKEND_TARGET || 'http://127.0.0.1:8000'
  const websocketTarget = backendTarget.replace(/^http/, 'ws')

  return {
    plugins: [vue()],
    server: {
      port: 5173,
      proxy: {
        '/api': backendTarget,
        '/ws': { target: websocketTarget, ws: true },
      },
    },
  }
})
