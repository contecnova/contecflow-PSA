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
            if (id.includes('/src/pages/')) {
              if (id.includes('/pages/service-desk/')) return 'route-service-desk'
              if (id.includes('/pages/portal-client/') || id.includes('PortalClientePage') || id.includes('PortalPublicViewPage')) return 'route-portal'
              if (id.includes('/pages/BI') || id.includes('DataExplorerPage') || id.includes('PredictionsPage') || id.includes('DataPlatformPage') || id.includes('DataGovernancePage')) return 'route-bi'
              if (id.includes('AIHubPage') || id.includes('NexusAgentPage') || id.includes('OraclePage') || id.includes('MeetingsAIPage') || id.includes('ContractsAIPage') || id.includes('SemanticEnginePage')) return 'route-ai'
              if (id.includes('ProjectsPage') || id.includes('TasksPage') || id.includes('GanttPage') || id.includes('Sprint') || id.includes('Kanban')) return 'route-delivery'
              if (id.includes('ProfitabilityPage') || id.includes('RevenuePage') || id.includes('BudgetsPage') || id.includes('InvoicesPage') || id.includes('ExpensesPage')) return 'route-finance'
              // NO trocear route-misc por dominio todavía (auditoría 2026-08 §7.b).
              // Se probó agrupando en route-settings/collab/process/people/itsm/
              // governance: el tamaño mejora (route-misc 666 -> 481 kB gzip), pero
              // los avisos de "Circular chunk" de rollup pasan de 7 a 11, porque las
              // páginas se importan entre sí a través de componentes compartidos.
              // Nota: esos 7 ya existen hoy, no los introduce el troceo — pero
              // añadir 4 ciclos más a un grafo ya circular por 185 kB no compensa,
              // y el orden de carga resultante no es verificable sin probar la app.
              // Requisito previo: extraer lo compartido entre páginas a módulos
              // propios, resolver los 7 ciclos actuales, y luego reintentar.
              return 'route-misc'
            }
            if (!id.includes('node_modules')) return
            if (id.includes('/react/') || id.includes('/react-dom/')) return 'vendor-react'
            if (id.includes('lucide-react')) return 'vendor-icons'
            if (id.includes('recharts')) return 'vendor-recharts'
            if (id.includes('react-grid-layout') || id.includes('react-window')) return 'vendor-layout'
            if (id.includes('yjs') || id.includes('y-websocket')) return 'vendor-realtime'
            if (id.includes('html2canvas')) return 'vendor-html2canvas'
            if (id.includes('@tanstack')) return 'vendor-react-query'
            if (id.includes('react-router')) return 'vendor-router'
            if (id.includes('axios')) return 'vendor-axios'
            if (id.includes('date-fns')) return 'vendor-date'
            if (id.includes('zod')) return 'vendor-validation'
            // Auditoría 2026-08 §7.b: estas no tenían regla (plotly y echarts salieron del
            // proyecto en 2026-11, #31) y caían todas en
            // vendor-core, que llegó a 6,4 MB (1,95 MB gzip). Son librerías pesadas
            // y de uso puntual (una o dos rutas cada una), así que separarlas evita
            // pagarlas en la carga inicial.
            if (id.includes('bpmn-js') || id.includes('diagram-js') || id.includes('bpmn-moddle')) return 'vendor-bpmn'
            if (id.includes('@xyflow')) return 'vendor-flow'
            if (id.includes('livekit-client')) return 'vendor-livekit'
            if (id.includes('/d3-') || id.includes('/d3/')) return 'vendor-d3'
            return 'vendor-core'
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
