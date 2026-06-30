import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // Per esporre il dev server via tunnel (cloudflared/ngrok) serve consentire
    // gli host esterni: altrimenti Vite risponde 403 "host not allowed".
    // `true` accetta qualunque host — ok per una demo temporanea via tunnel.
    allowedHosts: true,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
