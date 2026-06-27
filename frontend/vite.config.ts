import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file from the current directory
  const env = loadEnv(mode, process.cwd(), '');
  const backendUrl = env.VITE_API_BASE_URL || 'http://localhost:8000';

  return {
    // Absolute asset paths are required for React Router to work
    // correctly when loading deep links like /login
    base: '/',
    plugins: [react()],
    server: {
      port: 5173,
      host: true,
      proxy: {
        '/health': {
          target: backendUrl,
          changeOrigin: true,
        },
        '/analysis': {
          target: backendUrl,
          changeOrigin: true,
        },
        '/quota': {
          target: backendUrl,
          changeOrigin: true,
        },
        '/debug': {
          target: backendUrl,
          changeOrigin: true,
        },
        '/api': {
          target: backendUrl,
          changeOrigin: true,
        },
      }
    }
  }
})

