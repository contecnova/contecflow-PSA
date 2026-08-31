// Gate: ninguna ruta debe depender ESTÁTICAMENTE de un vendor chunk grande.
//
// Auditoría 2026-08 (hallazgo 19). El troceo por vendor ya estaba bien hecho
// —plotly, echarts, d3, bpmn y livekit tenían cada uno su chunk—, así que el
// problema no era el troceo sino QUIÉN los importa.
//
// `src/pages/CMDBPage.tsx` importaba `CMDBTopologyGraph` de forma estática, y ese
// componente depende de react-plotly.js. Resultado medido sobre el build: el
// chunk `route-misc` llevaba un import estático de `vendor-plotly` (4.633 kB, el
// 38 % de todo el JS del proyecto), así que abrir CUALQUIERA de las páginas de
// ese chunk descargaba plotly entero — incluidas las que no muestran ninguna
// gráfica. Con `Cmdb3dGraph` pasaba lo mismo con `vendor-d3`.
//
// Un import estático así no se ve leyendo el código: hay que mirar el grafo del
// build. Por eso existe este gate, que lo mira por nosotros.
//
// ── El criterio es el TAMAÑO, no una lista de nombres ────────────────────────
// La primera versión de este gate llevaba una lista escrita a mano de librerías
// «pesadas» e incluía `recharts`. Eso estaba mal: recharts (304 kB) es la
// librería de gráficas PRINCIPAL, usada en 18 sitios, y pagarla en una ruta que
// muestra gráficas es correcto — diferirla pondría un indicador de carga en cada
// panel. Un umbral de tamaño no tiene ese problema y no hay que mantenerlo.
//
// La forma correcta de usar un componente pesado es `lazy(() => import(...))`
// con un límite de `Suspense`, como ya hacía `charts/DynamicChart`.
//
// Uso:
//   node scripts/check_heavy_chunks.mjs            # gate (sale 1 si hay alguno)
//   node scripts/check_heavy_chunks.mjs --report   # sólo informe, sale 0
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const DIST = 'dist/assets'

// Por encima de esto, el chunk no debe ser dependencia estática de una ruta.
// Separa las librerías de uso puntual (plotly 4.633, echarts 812, livekit 499,
// bpmn 477) de la de uso general (recharts 304).
const LIMITE_KB = 400

// Estos son la base de la aplicación: son estáticos por diseño y siempre se
// cargan. Excluirlos no debilita el gate, evita un falso positivo permanente.
const BASE = new Set(['vendor-core', 'vendor-react'])

// Chunks que SÍ pueden depender de un vendor grande: son los envoltorios de la
// propia gráfica, que ya se cargan de forma diferida.
const ENVOLTORIOS = /^(vendor-|.*Chart.*|.*Graph.*)/

const soloInforme = process.argv.includes('--report')

let ficheros
try {
  ficheros = readdirSync(DIST).filter((f) => f.endsWith('.js'))
} catch {
  console.error(
    `✗ no existe ${DIST}. Este gate necesita un build: ejecuta "npm run build" antes.`,
  )
  process.exit(soloInforme ? 0 : 1)
}

const kB = (bytes) => `${Math.round(bytes / 1024)} kB`

// Tamaño por nombre de vendor, sin el hash.
const tamanoPorFichero = new Map()
const tamanoPorVendor = new Map()
for (const nombre of ficheros) {
  const bytes = statSync(join(DIST, nombre)).size
  tamanoPorFichero.set(nombre, bytes)
  const m = nombre.match(/^(vendor-[a-z0-9]+)-/)
  if (m) tamanoPorVendor.set(m[1], bytes)
}

// Sólo los imports ESTÁTICOS cuentan: un `import()` dinámico es precisamente la
// solución, no el problema.
const IMPORT_ESTATICO = /from"\.\/(vendor-[a-z0-9]+)-[^"]+"/g

const infracciones = []
for (const nombre of ficheros) {
  if (ENVOLTORIOS.test(nombre)) continue
  const src = readFileSync(join(DIST, nombre), 'utf8')
  const vendors = new Set()
  for (const m of src.matchAll(IMPORT_ESTATICO)) vendors.add(m[1])

  for (const vendor of vendors) {
    if (BASE.has(vendor)) continue
    const bytes = tamanoPorVendor.get(vendor) ?? 0
    if (bytes / 1024 > LIMITE_KB) infracciones.push({ chunk: nombre, vendor, bytes })
  }
}

const totalJs = [...tamanoPorFichero.values()].reduce((a, b) => a + b, 0)
console.log(`JS total en ${DIST}: ${kB(totalJs)} en ${ficheros.length} ficheros`)
console.log(`Umbral de dependencia estática: ${LIMITE_KB} kB`)

const mayores = [...tamanoPorFichero.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5)
console.log('Los 5 chunks mayores:')
for (const [nombre, bytes] of mayores) console.log(`  ${kB(bytes).padStart(8)}  ${nombre}`)

if (!infracciones.length) {
  console.log(
    `\n✓ ninguna ruta importa estáticamente un vendor de más de ${LIMITE_KB} kB`,
  )
  process.exit(0)
}

console.error('\n✗ dependencias estáticas de vendors grandes:')
let coste = 0
for (const { chunk, vendor, bytes } of infracciones) {
  coste += bytes
  console.error(`  ${chunk}\n      → ${vendor} (${kB(bytes)})`)
}
console.error(
  `\nCoste añadido a esas rutas: ${kB(coste)}.\n` +
    'Se arregla con `lazy(() => import(...))` y un límite de `Suspense` en el\n' +
    'componente que la usa, como en charts/DynamicChart.',
)
process.exit(soloInforme ? 0 : 1)
