#!/usr/bin/env node
/**
 * check_strict.mjs — el gate de tipos en modo estricto.
 *
 * Corre `tsc --noEmit -p tsconfig.strict.json` y falla con cualquier error.
 *
 * Auditoría 2026-09 — por qué este script ya no filtra nada
 * ---------------------------------------------------------
 * Hasta hoy leía la lista `include` de `tsconfig.strict.json` y sólo contaba
 * los errores de esos ficheros, porque la migración a estricto iba fichero a
 * fichero. La migración ha terminado: el config cubre todo `src/`, tests
 * incluidos, con cero errores.
 *
 * Y el filtro no sólo sobraba: **se había vuelto peligroso**. Ahora que
 * `include` son globs (`src/**\/*.ts`), la comparación que hacía
 * —`file === entrada || file.endsWith('/' + entrada)`— no habría encajado con
 * ningún fichero real, así que habría dado por bueno un proyecto con cualquier
 * número de errores. Un gate que no puede fallar es peor que no tener gate,
 * porque además da tranquilidad.
 *
 * Lo mismo valía para un fichero nuevo: mientras nadie lo añadiera a mano a la
 * lista, sus errores no contaban. Con `tsc` mandando sobre todo el proyecto eso
 * ya no puede pasar.
 *
 * Uso:
 *   node scripts/check_strict.mjs
 */
import { spawnSync } from 'node:child_process'

const tsc = spawnSync(
  'node',
  ['node_modules/typescript/bin/tsc', '--noEmit', '-p', 'tsconfig.strict.json'],
  { encoding: 'utf-8' },
)

const salida = `${tsc.stdout || ''}${tsc.stderr || ''}`
const errores = salida.split('\n').filter((l) => /\(\d+,\d+\): error /.test(l))

if (errores.length === 0 && tsc.status === 0) {
  console.log('check_strict: 0 errores en todo src/ (tests incluidos).')
  process.exit(0)
}

console.error(`check_strict: ${errores.length} error(es) en modo estricto.\n`)
for (const linea of errores) console.error('  ' + linea)
// `tsc` puede fallar sin emitir errores con formato (config mal, binario
// ausente). Eso también es un fallo del gate, no un pase.
if (errores.length === 0) console.error(salida.trim())
process.exit(1)
