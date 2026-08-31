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
function bloqueDe(ns) {
  const apertura = lineas.findIndex((l) => new RegExp(`^\\s{2,4}${ns}:\\s*\\{`).test(l))
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

// Se procesan los namespaces de ABAJO ARRIBA del fichero para que insertar en uno
// no desplace los índices de los que quedan por procesar.
const nsOrdenados = Object.keys(porNs)
  .map((ns) => ({ ns, bloque: bloqueDe(ns) }))
  .sort((a, b) => (b.bloque?.apertura ?? -1) - (a.bloque?.apertura ?? -1))

for (const { ns, bloque } of nsOrdenados) {
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
    if (partes.length > 2) {
      // Clave anidada a más de un nivel: este script sólo maneja el primer nivel
      // dentro del namespace. Se informa en lugar de colocarla mal.
      anidadas.push(clave)
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
