// vite.config.js
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd());

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api-remote': {
          target: env.VITE_CLOUDFLARE_LINK,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api-remote/, ''),
        },
        // Proxy to serve local images from your upload folder
        '/local-bills': {
          target: 'http://localhost:5173', // Points back to Vite
          bypass: (req, res, proxyOptions) => {
            // This is a trick to serve files from a specific local path
            // Note: In production, you'd use a proper static file server
          }
        }
      }
    }
  }
})