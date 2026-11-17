import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The FastAPI backend serves the built app from `web/dist` at `/` with an SPA
// fallback to index.html, so assets use the absolute base `/`. (A relative base
// like './' would break deep links such as /jobs/J01 after a page refresh.)
// During development, `/api` is proxied to the backend (override with VITE_API_TARGET).
const apiTarget = process.env.VITE_API_TARGET || 'http://127.0.0.1:8010'

export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    proxy: { '/api': { target: apiTarget, changeOrigin: true } },
  },
  preview: {
    proxy: { '/api': { target: apiTarget, changeOrigin: true } },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
