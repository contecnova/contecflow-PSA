// Texto visible escrito a pelo en el JSX, que no pasa por `t()`.
//
// Por qué hace falta otro medidor de i18n habiendo tres. Los que ya existen
// —`check_i18n_coverage.mjs`, `check_i18n.mjs`, `check_i18n_no_new_debt.mjs`—
// comparan los diccionarios entre sí: cuántas claves tiene `es` y cuántas de
// esas están en `en` y en `zh`. Los tres están al 100 %, y eso es cierto.
//
// Pero miden el diccionario, no las pantallas. Una cadena escrita directamente
// en el JSX —`<h2>Resumen del proyecto</h2>`— no tiene clave, así que no le
// falta traducción a ningún idioma y ninguno de los tres la ve. El 100 % de
// cobertura convive con pantallas enteras que sólo existen en castellano.
//
// Esto lo mide por el AST de TypeScript, no con expresiones regulares: un
// `>` de una comparación dentro de una llave no es texto, y una regex no lo
// distingue. Se miran dos cosas, las dos visibles para el usuario:
//
//   1. nodos `JsxText`             -> `<h2>Resumen del proyecto</h2>`
//   2. atributos de texto visible  -> `placeholder="Buscar cliente"`
//
// Uso:
//   node scripts/check_i18n_literales.mjs            gate (falla si empeora)
//   node scripts/check_i18n_literales.mjs --detalle  lista fichero a fichero
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const FUENTES = join(RAIZ, 'src')

// ── El trinquete ─────────────────────────────────────────────────────────────
//
// Dos direcciones, como los demás guardianes de este repo: no puede crecer, y
// si baja hay que actualizarlo aquí. Lo segundo no es burocracia — es lo que
// mantiene la foto honesta y hace visible cada mejora en el diff.
//
// Al traducir una pantalla, baja este número. Nunca lo subas.
//
// La primera medición se hizo con expresiones regulares y dio 1325. El AST da
// 1852 (en 134 ficheros): la regex no veía el texto que ocupa varias líneas —que es la mitad de
// los títulos y descripciones largas— ni distinguía un `>` de comparación de
// una etiqueta que se cierra. La cifra buena es la del AST, y se deja dicho
// para que nadie lea una mejora de 527 donde sólo hubo un instrumento mejor.
const DEUDA_REGISTRADA = 1094

// Atributos cuyo valor lee el usuario. `name`, `id`, `type` y compañía no.
const ATRIBUTOS_VISIBLES = new Set([
  'placeholder', 'title', 'label', 'aria-label', 'alt', 'aria-placeholder',
])

// Castellano: un acento, una eñe, una apertura de interrogación, o una palabra
// funcional que en inglés no existe. No pretende ser exacto sobre una palabra
// suelta —«Total» o «Email» son iguales en los dos idiomas y no se cuentan—,
// sino no dar por traducido lo que evidentemente no lo está.
const CASTELLANO = new RegExp(
  '[áéíóúñÁÉÍÓÚÑ¿¡]|\\b(de|la|el|los|las|del|para|con|sin|por|que|una|un|se|su|al|no|mas|este|esta|hay|son|como|cuando|todos|todas|nuevo|nueva)\\b',
  'i',
)

function ficherosTsx(dir) {
  const salida = []
  for (const entrada of readdirSync(dir)) {
    const p = join(dir, entrada)
    if (statSync(p).isDirectory()) {
      if (entrada === '__tests__' || entrada === 'node_modules') continue
      salida.push(...ficherosTsx(p))
    } else if (p.endsWith('.tsx') && !p.includes('.test.')) {
      salida.push(p)
    }
  }
  return salida
}

function literalesDe(ruta) {
  const fuente = ts.createSourceFile(
    ruta, readFileSync(ruta, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX,
  )
  const hallazgos = []

  function visitar(nodo) {
    if (ts.isJsxText(nodo)) {
      const texto = nodo.text.trim()
      if (texto && CASTELLANO.test(texto)) {
        hallazgos.push({ tipo: 'texto', texto, pos: nodo.getStart(fuente) })
      }
    } else if (ts.isJsxAttribute(nodo) && nodo.initializer) {
      const nombre = nodo.name.getText(fuente)
      if (ATRIBUTOS_VISIBLES.has(nombre) && ts.isStringLiteral(nodo.initializer)) {
        const texto = nodo.initializer.text.trim()
        if (texto && CASTELLANO.test(texto)) {
          hallazgos.push({ tipo: nombre, texto, pos: nodo.getStart(fuente) })
        }
      }
    }
    ts.forEachChild(nodo, visitar)
  }

  visitar(fuente)
  return hallazgos
}

const porFichero = new Map()
let total = 0
for (const f of ficherosTsx(FUENTES)) {
  const hallazgos = literalesDe(f)
  if (hallazgos.length) {
    porFichero.set(relative(RAIZ, f), hallazgos)
    total += hallazgos.length
  }
}

const detalle = process.argv.includes('--detalle')
const orden = [...porFichero.entries()].sort((a, b) => b[1].length - a[1].length)

console.log(`Texto visible fuera de t(): ${total} en ${porFichero.size} ficheros`)
console.log(`Registrado: ${DEUDA_REGISTRADA}\n`)

if (detalle) {
  for (const [f, hallazgos] of orden) {
    console.log(`${String(hallazgos.length).padStart(4)}  ${f}`)
    for (const h of hallazgos.slice(0, 6)) {
      console.log(`        ${h.tipo}: ${JSON.stringify(h.texto.slice(0, 70))}`)
    }
    if (hallazgos.length > 6) console.log(`        … y ${hallazgos.length - 6} más`)
  }
} else {
  console.log('Los 15 ficheros con más:')
  for (const [f, hallazgos] of orden.slice(0, 15)) {
    console.log(`  ${String(hallazgos.length).padStart(4)}  ${f}`)
  }
}

if (total > DEUDA_REGISTRADA) {
  console.error(
    `\n✗ La deuda de traducción CRECE: ${total} > ${DEUDA_REGISTRADA}.\n` +
    '  Todo texto que lea el usuario tiene que pasar por t(). Ejecuta con\n' +
    '  --detalle para ver cuál, y usa una clave en vez del literal.',
  )
  process.exit(1)
}

if (total < DEUDA_REGISTRADA) {
  console.error(
    `\n✗ La deuda ha BAJADO a ${total} y DEUDA_REGISTRADA sigue en ` +
    `${DEUDA_REGISTRADA}.\n` +
    '  Actualízala en scripts/check_i18n_literales.mjs. Falla a propósito: un\n' +
    '  trinquete sólo sirve si la foto es honesta, y así cada mejora se ve en\n' +
    '  el diff en vez de diluirse en el margen.',
  )
  process.exit(1)
}

console.log('\n✓ La deuda de traducción no empeora.')
