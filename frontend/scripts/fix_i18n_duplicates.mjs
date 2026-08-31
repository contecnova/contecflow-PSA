// Fusiona las declaraciones duplicadas de un fichero de idioma.
//
// Auditoría 2026-08 (hallazgo 16). `check_i18n_duplicates.mjs` encontró 204
// traducciones escritas, presentes en el repositorio, y **descartadas en
// silencio** porque su clave estaba declarada dos o más veces y en JavaScript
// gana la última.
//
// ── La regla que hace esto seguro ────────────────────────────────────────────
// El texto que el usuario ve HOY no cambia. Cuando dos declaraciones de la misma
// clave tienen textos distintos, se conserva **la última**, que es exactamente la
// que gana ahora al cargar el módulo. Lo que se recupera son las claves que sólo
// existen en las declaraciones anteriores y que hoy se pierden enteras.
//
// Así el arreglo sólo puede AÑADIR traducciones, nunca cambiar una que ya se
// mostraba. Es la diferencia entre recuperar trabajo perdido y reescribir el
// producto sin querer.
//
// Uso:
//   node scripts/fix_i18n_duplicates.mjs <idioma> [--dry-run]
import { readFileSync, writeFileSync } from 'node:fs'

const args = process.argv.slice(2)
const idioma = args.find((a) => !a.startsWith('--'))
const simulado = args.includes('--dry-run')

if (!idioma) {
  console.error('Uso: node scripts/fix_i18n_duplicates.mjs <idioma> [--dry-run]')
  process.exit(1)
}

// ── La única excepción a «gana la última» ────────────────────────────────────
//
// La regla general conserva la última declaración porque es la que se muestra
// hoy, y así el arreglo no puede cambiar lo que ve el usuario. Pero cuando lo que
// se muestra hoy está MAL, conservarlo sería perpetuar el fallo.
//
// `es.alm.subtitle` está declarada 13 veces dentro del namespace `alm`, y las 12
// posteriores a la primera son subtítulos de OTROS módulos que alguien volcó ahí:
// Kanban, sprints, imputaciones — y una en francés, resto de cuando había siete
// idiomas. Resultado: la pantalla de «Licencias y Activos» muestra hoy
// «Registra tu tiempo de trabajo y conviértelo en imputaciones».
//
// Los doce huérfanos son basura verificada: kanban, sprints, sprint_planning,
// timesheet, timesheets y tasks ya tienen su propio `subtitle` correcto en su
// namespace, así que borrarlos no deja ninguna pantalla sin subtítulo.
const GANA_LA_PRIMERA = {
  es: {
    'alm.subtitle':
      'Las 12 declaraciones posteriores son subtítulos de otros módulos volcados ' +
      'aquí (Kanban, sprints, imputaciones, una en francés). La primera es la ' +
      'descripción real de ALM.',
  },
}
const excepciones = GANA_LA_PRIMERA[idioma] ?? {}

const RUTA = `src/i18n/langs/${idioma}.mjs`
const lineas = readFileSync(RUTA, 'utf8').split('\n')

/**
 * Estructura del fichero: para cada objeto abierto, su ruta y sus líneas.
 * Se sigue el balance de llaves, no la indentación: en estos ficheros la
 * indentación no es fiable (hay namespaces a 2 y a 4 espacios en el mismo
 * objeto), y precisamente por eso el duplicado era invisible.
 */
function analizar() {
  const pila = []
  const bloques = [] // { ruta, inicio, fin, sangriaHijos }
  const hojas = [] // { ruta, linea, texto }

  for (let i = 0; i < lineas.length; i++) {
    const linea = lineas[i]
    if (linea.trim().startsWith('//')) continue

    const abre = linea.match(/^(\s*)([A-Za-z0-9_]+)\s*:\s*\{\s*$/)
    if (abre) {
      pila.push({
        nombre: abre[2],
        ruta: [...pila.map((p) => p.nombre), abre[2]].join('.'),
        inicio: i,
        sangria: abre[1],
      })
      continue
    }

    const hoja = linea.match(/^\s*([A-Za-z0-9_]+)\s*:\s*(['"`])/)
    if (hoja) {
      hojas.push({
        ruta: [...pila.map((p) => p.nombre), hoja[1]].join('.'),
        nombre: hoja[1],
        linea: i,
        texto: linea,
      })
      continue
    }

    if (/^\s*\}\s*,?\s*;?\s*$/.test(linea) && pila.length) {
      const b = pila.pop()
      bloques.push({ ...b, fin: i })
    }
  }
  return { bloques, hojas }
}

const { bloques, hojas } = analizar()

// ── Duplicados de OBJETO (un namespace declarado dos veces) ─────────────────
const bloquesPorRuta = new Map()
for (const b of bloques) {
  if (!bloquesPorRuta.has(b.ruta)) bloquesPorRuta.set(b.ruta, [])
  bloquesPorRuta.get(b.ruta).push(b)
}

// ── Duplicados de HOJA ───────────────────────────────────────────────────────
const hojasPorRuta = new Map()
for (const h of hojas) {
  if (!hojasPorRuta.has(h.ruta)) hojasPorRuta.set(h.ruta, [])
  hojasPorRuta.get(h.ruta).push(h)
}

const aBorrar = new Set() // índices de línea a eliminar
const aInsertar = [] // { destino, texto }
let recuperadas = 0
let hojasLimpiadas = 0
const textosDistintos = []

// 1. Objetos duplicados: se recuperan las hojas que sólo están en los bloques
//    anteriores y se vuelcan al ÚLTIMO, que es el que gana hoy.
for (const [ruta, apariciones] of bloquesPorRuta) {
  if (apariciones.length < 2) continue
  const ordenados = [...apariciones].sort((a, b) => a.inicio - b.inicio)
  const ganador = ordenados[ordenados.length - 1]

  // Hojas directas del ganador: son las que YA se muestran.
  const nombresGanador = new Set(
    hojas
      .filter((h) => h.ruta.startsWith(`${ruta}.`) && h.linea > ganador.inicio && h.linea < ganador.fin)
      .map((h) => h.nombre),
  )

  for (const perdedor of ordenados.slice(0, -1)) {
    const dentro = hojas.filter(
      (h) => h.ruta.startsWith(`${ruta}.`) && h.linea > perdedor.inicio && h.linea < perdedor.fin,
    )
    for (const h of dentro) {
      if (nombresGanador.has(h.nombre)) continue // el ganador ya la tiene
      // Se mueve al bloque ganador, respetando su indentación.
      const sangria = `${ganador.sangria}  `
      const cuerpo = h.texto.trim()
      aInsertar.push({ destino: ganador.fin, texto: `${sangria}${cuerpo}` })
      nombresGanador.add(h.nombre)
      recuperadas++
    }
    // El bloque perdedor entero desaparece.
    for (let i = perdedor.inicio; i <= perdedor.fin; i++) aBorrar.add(i)
  }
}

// 2. Hojas duplicadas dentro del MISMO objeto: se queda la última.
for (const [ruta, apariciones] of hojasPorRuta) {
  if (apariciones.length < 2) continue
  // Si su objeto contenedor ya se fusionó arriba, no se toca aquí.
  const contenedor = ruta.split('.').slice(0, -1).join('.')
  if ((bloquesPorRuta.get(contenedor)?.length ?? 0) > 1) continue

  const ordenados = [...apariciones].sort((a, b) => a.linea - b.linea)
  const valores = new Set(ordenados.map((h) => h.texto.trim()))

  // Por defecto se conserva la ÚLTIMA (la que se muestra hoy). Las excepciones
  // documentadas conservan la primera, y se dice por qué.
  const conservarPrimera = ruta in excepciones
  const conservada = conservarPrimera ? ordenados[0] : ordenados[ordenados.length - 1]

  if (conservarPrimera) {
    console.log(`  ↺ ${ruta}: se conserva la PRIMERA (línea ${conservada.linea + 1})`)
    console.log(`      motivo: ${excepciones[ruta]}`)
  } else if (valores.size > 1) {
    textosDistintos.push({ ruta, apariciones: ordenados.map((h) => h.linea + 1) })
  }

  for (const h of ordenados) {
    if (h.linea === conservada.linea) continue
    aBorrar.add(h.linea)
    hojasLimpiadas++
  }
}

console.log(`${RUTA}`)
console.log(`  traducciones recuperadas de bloques duplicados: ${recuperadas}`)
console.log(`  declaraciones de hoja redundantes eliminadas:   ${hojasLimpiadas}`)
if (textosDistintos.length) {
  console.log(
    `  ⚠ ${textosDistintos.length} claves duplicadas con TEXTOS DISTINTOS — se conserva la` +
      ' última, que es la que se muestra hoy:',
  )
  for (const d of textosDistintos.slice(0, 8)) {
    console.log(`      ${d.ruta} (líneas ${d.apariciones.join(', ')})`)
  }
}

if (!recuperadas && !hojasLimpiadas) {
  console.log('  nada que hacer')
  process.exit(0)
}

// Reconstruir: primero las inserciones (de mayor a menor destino), luego los
// borrados. Se hace en dos pasadas sobre índices originales para no desplazarlos.
const salida = []
const insercionesPorLinea = new Map()
for (const it of aInsertar) {
  if (!insercionesPorLinea.has(it.destino)) insercionesPorLinea.set(it.destino, [])
  insercionesPorLinea.get(it.destino).push(it.texto)
}

for (let i = 0; i < lineas.length; i++) {
  if (insercionesPorLinea.has(i)) salida.push(...insercionesPorLinea.get(i))
  if (!aBorrar.has(i)) salida.push(lineas[i])
}

if (simulado) {
  console.log('\n(--dry-run: no se ha escrito nada)')
  process.exit(0)
}

writeFileSync(RUTA, salida.join('\n'), 'utf8')
console.log(`\n✓ ${RUTA} reescrito (${lineas.length} → ${salida.length} líneas)`)
