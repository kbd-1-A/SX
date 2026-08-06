import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端默认 8000；若后端换了端口，改这里
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
