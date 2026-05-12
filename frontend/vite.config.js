import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const apiTarget = process.env.VITE_API_URL || process.env.API_URL || 'http://localhost:8000'
  let apiOrigin = 'http://localhost:8000'
  try {
    apiOrigin = new URL(apiTarget, 'http://localhost:8000').origin
  } catch {
    apiOrigin = 'http://localhost:8000'
  }

  return {
    plugins: [
      react(),
    ],
    server: {
      port: Number(process.env.VITE_PORT) || 3000,
      proxy: {
        '/api': {
          target: apiOrigin,
          changeOrigin: true,
          ws: true,
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
          "media-src   'self' blob:; " +
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
    build: {
      // ECharts bundle is intentionally isolated and lazy-loaded on BI routes.
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return
            if (id.includes('/react/') || id.includes('/react-dom/')) return 'vendor-react'
            if (id.includes('lucide-react')) return 'vendor-icons'
            if (id.includes('recharts')) return 'vendor-recharts'
            if (id.includes('echarts') || id.includes('echarts-for-react')) return 'vendor-echarts'
            if (id.includes('react-grid-layout') || id.includes('react-window')) return 'vendor-layout'
            if (id.includes('yjs') || id.includes('y-websocket')) return 'vendor-realtime'
            if (id.includes('html2canvas')) return 'vendor-html2canvas'
            if (id.includes('@tanstack')) return 'vendor-react-query'
            if (id.includes('react-router')) return 'vendor-router'
            if (id.includes('axios')) return 'vendor-axios'
            if (id.includes('date-fns')) return 'vendor-date'
            if (id.includes('zod')) return 'vendor-validation'
            return 'vendor-core'
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.{js,jsx}'],
      setupFiles: ['./src/vitest.setup.js'],
      globals: true,
    },
  }
})
