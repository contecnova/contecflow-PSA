/**
 * `global` para el código CommonJS de `plotly.js/lib/*`.
 *
 * Auditoría 2026-11: `plotly.js/lib/core` trae `has-hover`, que lee
 * `global.matchMedia`. En el build, el plugin commonjs de Rollup traduce
 * `global`; en desarrollo Vite pre-empaqueta con esbuild y no lo hace, y la
 * página que pintaba una gráfica (topología de la CMDB, box, violín, 3D)
 * reventaba con «ReferenceError: global is not defined».
 *
 * Tiene que importarse ANTES que plotly: los imports se evalúan en orden.
 */
const g = globalThis as typeof globalThis & { global?: typeof globalThis }
if (typeof g.global === 'undefined') g.global = globalThis

export {}
