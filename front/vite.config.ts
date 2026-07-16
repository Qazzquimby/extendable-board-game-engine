import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/heroes': 'http://localhost:8000',
      '/run-game': 'http://localhost:8000',
    },
  },
})
