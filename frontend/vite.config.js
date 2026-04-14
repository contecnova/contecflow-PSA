import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const apiTarget = process.env.VITE_API_URL || 'http://localhost:8000'
  const apiOrigin = new URL(apiTarget).origin

  return {
    plugins: [
      react(),
    ],
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        }
      },
      headers: {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        // Relaxed CSP for Vite dev (HMR needs ws:, injected scripts need unsafe-inline/eval)
        'Content-Security-Policy':
          "default-src 'self'; " +
          "script-src  'self' 'unsafe-inline' 'unsafe-eval'; " +
          "style-src   'self' 'unsafe-inline' https://fonts.googleapis.com; " +
          "img-src     'self' data: blob:; " +
          "font-src    'self' data: https://fonts.gstatic.com; " +
          `connect-src 'self' ${apiOrigin} ws: wss:; ` +
          "object-src  'none'; " +
          "base-uri    'self'; " +
          "worker-src  'self' blob:;",
      },
    },
    optimizeDeps: {
      force: false,
    },
    // Strip console.* and debugger statements from production bundles
    esbuild: {
      drop: mode === 'production' ? ['console', 'debugger'] : [],
    },
    test: {
      environment: 'node',
      include: ['src/**/*.test.{js,jsx}'],
    },
  }
})
