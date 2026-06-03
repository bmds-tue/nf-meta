import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Proxy only used in development context, when vite is accessed directly
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/docs": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../frontend_dist',
    emptyOutDir: true,
  },
})
