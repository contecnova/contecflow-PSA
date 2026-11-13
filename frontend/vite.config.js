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
          // Auditoria 2026-11 (#19): solo se nombran los vendor que necesita el
          // arranque (React, router, react-query, axios). Antes todas las paginas
          // de src/pages caian en route-*/route-misc (3 MB) y todo node_modules sin
          // regla en vendor-core; como el shell importa modulos compartidos que
          // vivian en esos chunks, index.html los precargaba enteros y las rutas
          // "lazy" no lo eran. Ahora Rollup trocea por import() dinamico: cada
          // pagina y cada libreria pesada (recharts, d3, bpmn, xyflow, livekit,
          // yjs...) va en su propio chunk y solo se descarga al visitarla.
          manualChunks(id) {
            if (!id.includes('node_modules')) return
            if (/[\/]node_modules[\/](react|react-dom|scheduler)[\/]/.test(id)) return 'vendor-react'
            if (id.includes('react-router')) return 'vendor-router'
            if (id.includes('@tanstack')) return 'vendor-react-query'
            if (id.includes('/axios/')) return 'vendor-axios'
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.{js,jsx,ts,tsx}'],
      setupFiles: ['./src/vitest.setup.ts'],
      globals: true,
    },
  }
})
