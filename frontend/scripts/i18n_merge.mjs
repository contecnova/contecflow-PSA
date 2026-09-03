// Fusiona traducciones nuevas en el fichero de un idioma, preservando formato.
//
// Auditoría 2026-08 (hallazgo 16). Escribir 1.419 claves a mano en un fichero de
// 3.000 líneas es la forma de romperlo, así que lo hace este script.
//
// Reglas que respeta, y por qué cada una:
//
//  · NO sobrescribe una clave que ya existe. Traducir dos veces la misma clave
//    con textos distintos es un error silencioso; si hace falta corregir una
//    traducción, se edita el fichero.
//  · Inserta en ORDEN ALFABÉTICO dentro de su namespace, que es como está el
//    resto del fichero. Un fichero ordenado hace que los huecos se vean.
//  · Escapa las comillas simples y las contrabarras del texto, porque el fichero
//    usa comillas simples.
//  · Rechaza una clave cuyo namespace no exista todavía en el fichero de destino:
//    crear jerarquía nueva a ciegas es como se acaba con dos ramas que compiten.
//
// Uso:
//   node scripts/i18n_merge.mjs <idioma> <fichero.json>
//   node scripts/i18n_merge.mjs en lote.json --dry-run
//
// El JSON es {"namespace.clave.anidada": "texto traducido", ...}
import { readFileSync, writeFileSync } from 'node:fs'

const args = process.argv.slice(2)
const [idioma, ficheroJson] = args.filter((a) => !a.startsWith('--'))
const simulado = args.includes('--dry-run')

if (!idioma || !ficheroJson) {
  console.error('Uso: node scripts/i18n_merge.mjs <idioma> <fichero.json> [--dry-run]')
  process.exit(1)
}

const RUTA = `src/i18n/langs/${idioma}.mjs`
let fuente
try {
  fuente = readFileSync(RUTA, 'utf8')
} catch {
  console.error(`✗ no existe ${RUTA}`)
  process.exit(1)
}

const nuevas = JSON.parse(readFileSync(ficheroJson, 'utf8'))
const claves = Object.keys(nuevas)
console.log(`${claves.length} claves a fusionar en ${RUTA}`)

function escapar(texto) {
  return String(texto).replace(/\\/g, '\\\\').replace(/'/g, "\\'")
}

const lineas = fuente.split('\n')

/**
 * Localiza el bloque de un namespace: la línea de apertura y la de cierre.
 * Se busca por indentación en lugar de parsear JS: el fichero tiene un formato
 * estable y regular, y un parser completo aquí sería desproporcionado.
 */
/**
 * Indentación de los namespaces de PRIMER nivel del fichero.
 *
 * Hay que calcularla, no suponerla: es de 4 espacios en `en.mjs` y de 2 en
 * `zh.mjs`. Con un `\s{2,4}` se aceptan las dos y `findIndex` devuelve la PRIMERA
 * coincidencia, que puede ser un namespace ANIDADO con el mismo nombre. Pasó: 16
 * claves de `alerts` se insertaron en un `alerts` anidado de la línea 306,
 * mientras el de primer nivel —el que gana al cargar el módulo— estaba en la
 * 2928. La cobertura seguía marcándolas como faltantes y no había ningún error.
 */
function sangriaPrimerNivel() {
  let prof = 0
  for (const l of lineas) {
    const m = l.match(/^(\s+)([A-Za-z0-9_]+)\s*:\s*\{\s*$/)
    if (m && prof === 1) return m[1]
    prof += (l.match(/\{/g) || []).length
    prof -= (l.match(/\}/g) || []).length
    if (prof < 0) prof = 0
  }
  return '  '
}

const SANGRIA_NS = sangriaPrimerNivel()

function bloqueDe(ns) {
  // Indentación EXACTA del primer nivel: así nunca se acierta un anidado.
  const apertura = lineas.findIndex((l) => l === `${SANGRIA_NS}${ns}: {`)
  if (apertura === -1) return null
  const sangria = lineas[apertura].match(/^(\s*)/)[1]
  for (let i = apertura + 1; i < lineas.length; i++) {
    if (lineas[i] === `${sangria}},` || lineas[i] === `${sangria}}`) {
      return { apertura, cierre: i, sangria }
    }
  }
  return null
}

// Agrupar por namespace de primer nivel.
const porNs = {}
for (const clave of claves) {
  const ns = clave.split('.')[0]
  ;(porNs[ns] ??= []).push(clave)
}

let insertadas = 0
const yaExistian = []
const sinNamespace = []
const anidadas = []
const subObjetos = []

// Se procesan los namespaces de ABAJO ARRIBA del fichero para que insertar en uno
// no desplace los índices de los que quedan por procesar.
const nsOrdenados = Object.keys(porNs)
  .map((ns) => ({ ns, bloque: bloqueDe(ns) }))
  .sort((a, b) => (b.bloque?.apertura ?? -1) - (a.bloque?.apertura ?? -1))

// Namespaces que no existen todavia en el destino: se crean vacios ANTES de
// insertar, en orden alfabetico al nivel de los demas. La primera version del
// script los rechazaba, que era prudente al principio pero dejaba fuera 19
// claves de cuatro pantallas (dashboard, gantt, inbox, semantic_engine).
const nsQueFaltan = nsOrdenados.filter((x) => !x.bloque).map((x) => x.ns)
if (nsQueFaltan.length) {
  // Sangria y posiciones de los namespaces existentes de primer nivel.
  const primerNivel = []
  let prof = 0
  for (let i = 0; i < lineas.length; i++) {
    const l = lineas[i]
    const m = l.match(/^(\s+)([A-Za-z0-9_]+)\s*:\s*\{\s*$/)
    if (m && prof === 1) primerNivel.push({ nombre: m[2], linea: i, sangria: m[1] })
    prof += (l.match(/\{/g) || []).length
    prof -= (l.match(/\}/g) || []).length
    if (prof < 0) prof = 0
  }
  if (!primerNivel.length) {
    console.error('✗ no se pudo determinar la estructura del fichero')
    process.exit(1)
  }
  const sangriaNs = primerNivel[0].sangria
  // De mayor a menor posicion, para no desplazar indices.
  const creaciones = nsQueFaltan
    .map((ns) => {
      const posterior = primerNivel.find((p) => p.nombre > ns)
      return { ns, destino: posterior ? posterior.linea : primerNivel[primerNivel.length - 1].linea }
    })
    .sort((a, b) => b.destino - a.destino)
  for (const { ns, destino } of creaciones) {
    lineas.splice(destino, 0, `${sangriaNs}${ns}: {`, `${sangriaNs}},`)
    console.log(`  + namespace creado: ${ns}`)
  }
}

// Se recalculan los bloques: crear namespaces ha desplazado las lineas.
const nsFinales = Object.keys(porNs)
  .map((ns) => ({ ns, bloque: bloqueDe(ns) }))
  .sort((a, b) => (b.bloque?.apertura ?? -1) - (a.bloque?.apertura ?? -1))

for (const { ns, bloque } of nsFinales) {
  if (!bloque) {
    sinNamespace.push(...porNs[ns])
    continue
  }
  const { apertura, cierre, sangria } = bloque
  const sangriaClave = `${sangria}  `

  // Las claves existentes del bloque, para no duplicar y para saber dónde entra
  // cada nueva por orden alfabético.
  //
  // Sólo cuentan las del nivel EXACTO del namespace. Un escáner que aceptase
  // cualquier indentación cogería también las de los sub-objetos anidados, y
  // entonces una clave nueva llamada igual que una anidada se descartaría como
  // «ya existía» — silenciosamente. Pasó: descartaba 59 claves legítimas.
  const existentes = []
  let profundidad = 0
  for (let i = apertura + 1; i < cierre; i++) {
    const linea = lineas[i]
    if (profundidad === 0) {
      const m = linea.match(/^(\s*)([A-Za-z0-9_]+):/)
      if (m && m[1] === sangriaClave) existentes.push({ nombre: m[2], linea: i })
    }
    // Se lleva la cuenta de los sub-objetos abiertos para saltárselos por
    // completo, incluidos los anidados a varios niveles.
    profundidad += (linea.match(/\{/g) || []).length
    profundidad -= (linea.match(/\}/g) || []).length
    if (profundidad < 0) profundidad = 0
  }

  const aInsertar = []
  for (const clave of porNs[ns]) {
    const partes = clave.split('.')
    if (partes.length > 3) {
      // Mas de tres niveles: no aparece en los datos actuales, asi que se informa
      // en lugar de adivinar donde va.
      anidadas.push(clave)
      continue
    }
    if (partes.length === 3) {
      // Sub-objeto dentro del namespace. Se procesan aparte porque exigen crear
      // o localizar el objeto intermedio.
      subObjetos.push({ ns, sub: partes[1], hoja: partes[2], texto: nuevas[clave] })
      continue
    }
    const nombre = partes[1]
    if (existentes.some((e) => e.nombre === nombre)) {
      yaExistian.push(clave)
      continue
    }
    aInsertar.push({ nombre, texto: nuevas[clave] })
  }

  // Insertar de mayor a menor posición, por el mismo motivo que arriba.
  const colocadas = aInsertar
    .map((it) => {
      const posterior = existentes.find((e) => e.nombre > it.nombre)
      return { ...it, destino: posterior ? posterior.linea : cierre }
    })
    .sort((a, b) => b.destino - a.destino)

  for (const { nombre, texto, destino } of colocadas) {
    lineas.splice(destino, 0, `${sangriaClave}${nombre}: '${escapar(texto)}',`)
    insertadas++
  }
}

// ── Claves a tres niveles: namespace.subObjeto.hoja ─────────────────────────
// Se procesan al final porque pueden necesitar crear el objeto intermedio, y eso
// desplaza lineas: hacerlo antes invalidaria los indices de los bloques.
let subInsertadas = 0
const porSub = {}
for (const it of subObjetos) {
  const k = `${it.ns}.${it.sub}`
  ;(porSub[k] ??= []).push(it)
}
for (const [ruta, items] of Object.entries(porSub)) {
  const [ns, sub] = ruta.split('.')
  const bloqueNs = bloqueDe(ns)
  if (!bloqueNs) {
    sinNamespace.push(...items.map((i) => `${ns}.${sub}.${i.hoja}`))
    continue
  }
  const sangriaSub = `${bloqueNs.sangria}  `
  // ¿Existe ya el sub-objeto dentro del namespace?
  let aperturaSub = -1
  for (let i = bloqueNs.apertura + 1; i < bloqueNs.cierre; i++) {
    if (lineas[i] === `${sangriaSub}${sub}: {`) {
      aperturaSub = i
      break
    }
  }
  if (aperturaSub === -1) {
    // Se crea vacio al final del namespace.
    lineas.splice(bloqueNs.cierre, 0, `${sangriaSub}${sub}: {`, `${sangriaSub}},`)
    aperturaSub = bloqueNs.cierre
    console.log(`  + sub-objeto creado: ${ruta}`)
  }
  // Cierre del sub-objeto.
  let cierreSub = -1
  for (let i = aperturaSub + 1; i < lineas.length; i++) {
    if (lineas[i] === `${sangriaSub}},` || lineas[i] === `${sangriaSub}}`) {
      cierreSub = i
      break
    }
  }
  const existentesSub = new Set()
  for (let i = aperturaSub + 1; i < cierreSub; i++) {
    const m = lineas[i].match(/^\s*([A-Za-z0-9_]+)\s*:/)
    if (m) existentesSub.add(m[1])
  }
  for (const it of items) {
    if (existentesSub.has(it.hoja)) {
      yaExistian.push(`${ruta}.${it.hoja}`)
      continue
    }
    lineas.splice(cierreSub, 0, `${sangriaSub}  ${it.hoja}: '${escapar(it.texto)}',`)
    subInsertadas++
  }
}
if (subInsertadas) console.log(`  insertadas en sub-objetos: ${subInsertadas}`)
insertadas += subInsertadas

console.log(`  insertadas:     ${insertadas}`)
if (yaExistian.length) console.log(`  ya existían:    ${yaExistian.length}`)
if (anidadas.length) {
  console.log(`  ✗ anidadas a >2 niveles (no insertadas): ${anidadas.length}`)
  console.log(`      ${anidadas.slice(0, 5).join(', ')}`)
}
if (sinNamespace.length) {
  const nss = [...new Set(sinNamespace.map((k) => k.split('.')[0]))]
  console.log(`  ✗ namespace inexistente en ${idioma} (no insertadas): ${sinNamespace.length}`)
  console.log(`      namespaces: ${nss.join(', ')}`)
}

if (simulado) {
  console.log('\n(--dry-run: no se ha escrito nada)')
  process.exit(0)
}

writeFileSync(RUTA, lineas.join('\n'), 'utf8')
console.log(`\n✓ ${RUTA} actualizado`)
if (anidadas.length || sinNamespace.length) process.exit(2)
