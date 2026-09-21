// Claves que el código pide a `t()` y que no existen en ningún diccionario.
//
// ── Por qué esto no lo veía ningún gate, y por qué importa ────────────────────
//
// Los otros cuatro comparan los diccionarios entre sí (¿tiene `en` todo lo que
// tiene `es`?) o miran el JSX (¿queda texto fuera de `t()`?). Una clave que el
// código invoca pero que **nadie declaró** se escapa de los dos: no está en
// `es`, así que a `en` y a `zh` no les «falta»; y el JSX sí pasa por `t()`, así
// que tampoco es un literal.
//
// Y no se queda en blanco, que sería evidente. `resolveTranslation` tiene un
// último recurso que **humaniza la clave**:
//
//     t('tasks.add_comment')        ->  "Add comment"
//     t('tasks.tab_details')        ->  "Tab details"
//     t('settings.empty_templates_title')  ->  "Empty templates title"
//
// Un usuario español ve texto inventado en inglés, con aspecto de estar bien.
// Nadie lo reporta como «falta la traducción» porque no parece que falte nada.
// Auditoría 2026-09: **110 de estas** llevaban en producción sin que ninguno de
// los cuatro gates dijera una palabra.
//
// Uso:  node scripts/check_i18n_claves_sin_definir.mjs
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'
import es from '../src/i18n/langs/es.mjs'

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const FUENTES = join(RAIZ, 'src')

// Se lee por AST y no por texto para no contar lo que hay en comentarios: el
// docstring de `AppLangContext` documenta la API con `t('module.key')`, y un
// grep ingenuo lo denuncia como clave rota.
function llamadasAT(ruta) {
  const fuente = ts.createSourceFile(
    ruta, readFileSync(ruta, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX,
  )
  const salida = []

  function visitar(nodo) {
    if (ts.isCallExpression(nodo) && ts.isIdentifier(nodo.expression)
        && (nodo.expression.text === 't' || nodo.expression.text === 'traducir'
            || nodo.expression.text === 'traducirSinHook')
        && nodo.arguments.length >= 1
        && ts.isStringLiteral(nodo.arguments[0])) {
      // `t('mod.key', 'Texto por defecto')` trae su propio respaldo y no rompe
      // nada aunque la clave no exista; sólo se miran las llamadas sin él.
      const conRespaldo = nodo.arguments.length > 1
        && ts.isStringLiteral(nodo.arguments[1])
      if (!conRespaldo) salida.push(nodo.arguments[0].text)
    }
    ts.forEachChild(nodo, visitar)
  }

  visitar(fuente)
  return salida
}

function ficheros(dir) {
  const salida = []
  for (const entrada of readdirSync(dir)) {
    const p = join(dir, entrada)
    if (statSync(p).isDirectory()) {
      if (entrada === '__tests__' || entrada === 'node_modules') continue
      salida.push(...ficheros(p))
    } else if ((p.endsWith('.tsx') || p.endsWith('.ts')) && !p.includes('.test.')) {
      salida.push(p)
    }
  }
  return salida
}

function existe(clave) {
  const partes = clave.split('.')
  let nodo = es
  for (const paso of partes) {
    if (nodo === null || typeof nodo !== 'object' || !(paso in nodo)) return false
    nodo = nodo[paso]
  }
  return typeof nodo === 'string'
}

const rotas = new Map()
for (const f of ficheros(FUENTES)) {
  for (const clave of llamadasAT(f)) {
    // Sin punto no es una clave: `t(variable)` no se puede comprobar, y
    // `t('modulo', 'clave')` usa la otra forma de la API.
    if (!clave.includes('.')) continue
    if (existe(clave)) continue
    if (!rotas.has(clave)) rotas.set(clave, new Set())
    rotas.get(clave).add(relative(RAIZ, f))
  }
}

if (rotas.size === 0) {
  console.log('✓ Ninguna clave pedida a t() se queda sin definir.')
  process.exit(0)
}

console.error(`✗ ${rotas.size} claves pedidas a t() NO existen en es.mjs.\n`)
console.error('  No salen en blanco: `resolveTranslation` humaniza la clave, así que')
console.error('  el usuario ve texto inventado en inglés con aspecto de estar bien.\n')
for (const [clave, donde] of [...rotas].sort()) {
  console.error(`  ${clave}`)
  for (const f of donde) console.error(`      ${f}`)
}
process.exit(1)
