import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const apiBaseUrl = loadEnv(mode, process.cwd(), 'VITE_').VITE_API_BASE_URL || 'http://127.0.0.1:8000'
  return {
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/health': apiBaseUrl,
      '/ready': apiBaseUrl,
      '/resolve': apiBaseUrl,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
  }
})
