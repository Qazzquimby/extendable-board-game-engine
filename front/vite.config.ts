import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 8425,
    proxy: {
      '/heroes': 'http://localhost:8000',
      '/run-game': 'http://localhost:8000',
    },
  },
})
