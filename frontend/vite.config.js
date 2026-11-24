import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

// Auditoria 2026-11 (#24a): el ingles ya no va en el chunk inicial, pero el
// castellano tiene claves sin traducir que hasta ahora se resolvian con el
// ingles. Este modulo virtual lleva SOLO esas entradas inglesas (unos pocos kB),
// calculadas en cada build a partir de los dos diccionarios: no hay fichero
// generado que se pueda quedar desfasado.
const RESPALDO_ID = 'virtual:i18n-respaldo-en'
function respaldoInglesDelCastellano() {
  const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), 'src', 'i18n', 'langs') + path.sep
  const usable = (v, clave) => typeof v === 'string' && v.trim() !== '' && v !== clave
  const esObjeto = (v) => v != null && typeof v === 'object' && !Array.isArray(v)
  // Hojas de `en` cuyo equivalente en `es` no resolveria (falta, vacio o igual a la clave).
  function faltantes(en, es) {
    const out = {}
    for (const [k, v] of Object.entries(en)) {
      const e = esObjeto(es) ? es[k] : undefined
      if (esObjeto(v)) {
        const sub = faltantes(v, e)
        if (Object.keys(sub).length) out[k] = sub
      } else if (!usable(e, k)) {
        out[k] = v
      }
    }
    return out
  }
  return {
    name: 'i18n-respaldo-en',
    resolveId: (id) => (id === RESPALDO_ID ? '\0' + RESPALDO_ID : undefined),
    async load(id) {
      if (id !== '\0' + RESPALDO_ID) return undefined
      const cargar = async (lang) => {
        const fichero = dir + lang + '.mjs'
        this.addWatchFile(fichero)
        return (await import(pathToFileURL(fichero).href + '?t=' + Date.now())).default
      }
      const [es, en] = await Promise.all([cargar('es'), cargar('en')])
      return 'export default ' + JSON.stringify(faltantes(en, es))
    },
  }
}

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
      respaldoInglesDelCastellano(),
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
          "style-src   'self' 'unsafe-inline'; " +
          "img-src     'self' data: blob:; " +
          "media-src   'self' blob:; " +
          "font-src    'self' data:; " +
          // 23-11-2026: + los origenes de contecintelligence incrustables (mismo ajuste que el backend).
          `connect-src 'self' ${apiOrigin}${(process.env.CONTECINTELLIGENCE_EMBED_ORIGINS || '').split(',').map(o => o.trim()).filter(o => /^https?:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/.test(o)).map(o => ` ${o}`).join('')} ws: wss:; ` +
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
