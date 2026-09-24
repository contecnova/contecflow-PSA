// Une las claves que dicen lo mismo dentro de un mismo módulo.
//
// ── Por qué existe: un defecto de la extracción de §3.untrigies ───────────────
//
// `i18n_extraer_literales.mjs` genera la clave a partir del texto, y el
// insertor sólo saltaba las que ya existían **con ese nombre**. Cuando el
// módulo ya tenía ese mismo texto con OTRO nombre —`wiki.no_pages` para «Sin
// páginas»— se creaba una segunda clave, `wiki.sin_paginas`, con el mismo
// castellano.
//
// Dos claves para una frase no es sólo ruido: cada una se tradujo por su
// cuenta, así que el mismo texto castellano acabó con dos chinos distintos
// —«无页面» y «暂无页面»— y la interfaz dice una cosa u otra según el sitio.
// Lo destapó `check_i18n_variables.mjs` al comparar términos por módulo.
//
// El arreglo no es igualar las dos traducciones: es quedarse con la clave que
// ya existía, apuntar el código a ella y borrar la nueva. Menos claves, y la
// divergencia deja de ser posible.
//
// Uso:
//   node scripts/i18n_fusionar_duplicadas.mjs            (sólo informa)
//   node scripts/i18n_fusionar_duplicadas.mjs --aplicar
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import es from '../src/i18n/langs/es.mjs'

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const APLICAR = process.argv.includes('--aplicar')

function aplanar(obj, prefijo = '', salida = {}) {
  for (const [k, v] of Object.entries(obj || {})) {
    const clave = prefijo ? `${prefijo}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) aplanar(v, clave, salida)
    else salida[clave] = v
  }
  return salida
}

const sinAcentos = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '')

/** La misma regla con la que `i18n_extraer_literales.mjs` fabrica una clave. */
function slug(texto) {
  return sinAcentos(texto).toLowerCase()
    .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
    .split('_').filter(Boolean).slice(0, 7).join('_') || 'texto'
}

const BASE = aplanar(es)
const porTexto = new Map()
for (const [clave, valor] of Object.entries(BASE)) {
  if (typeof valor !== 'string' || valor.length < 3) continue
  const modulo = clave.split('.')[0]
  const agrupador = `${modulo}||${valor}`
  if (!porTexto.has(agrupador)) porTexto.set(agrupador, [])
  porTexto.get(agrupador).push(clave)
}

const fusiones = []
for (const [agrupador, claves] of porTexto) {
  if (claves.length < 2) continue
  const texto = agrupador.split('||').slice(1).join('||')
  // La «mía» es la que coincide exactamente con el slug del texto.
  const generadas = claves.filter((k) => k.split('.').slice(1).join('.') === slug(texto))
  const previas = claves.filter((k) => !generadas.includes(k))
  if (!generadas.length || !previas.length) continue
  // Se conserva la más corta de las previas: suele ser la semántica (`no_pages`
  // antes que `empty_state_no_pages_title`).
  //
  // Salvo cuando la «previa» es en realidad el sufijo de colisión que generó la
  // propia extracción: `nueva_contrasena_2` no es más antigua que
  // `nueva_contrasena`, es la segunda. Ahí el destino correcto es la de nombre
  // limpio, y la fusión va en el otro sentido.
  const sufijo = new RegExp(`^${slug(texto)}_\\d+$`)
  const limpias = previas.filter((k) => !sufijo.test(k.split('.').slice(1).join('.')))
  if (!limpias.length) {
    const destino = generadas.sort((a, b) => a.length - b.length)[0]
    for (const origen of previas) fusiones.push({ origen, destino, texto })
    continue
  }
  const destino = limpias.sort((a, b) => a.length - b.length)[0]
  for (const origen of generadas) fusiones.push({ origen, destino, texto })
}

console.log(`Claves duplicadas dentro de su módulo: ${fusiones.length}`)
for (const f of fusiones) {
  console.log(`  ${f.origen}  ->  ${f.destino}   ${JSON.stringify(f.texto.slice(0, 44))}`)
}
if (!APLICAR) {
  console.log('\n(sólo informe: pasa --aplicar para hacerlo)')
  process.exit(0)
}

// ── 1. Repuntar el código ────────────────────────────────────────────────────
function ficheros(dir) {
  const salida = []
  for (const e of readdirSync(dir)) {
    const p = join(dir, e)
    if (statSync(p).isDirectory()) {
      if (e !== 'node_modules') salida.push(...ficheros(p))
    } else if (p.endsWith('.tsx') || p.endsWith('.ts')) salida.push(p)
  }
  return salida
}

let usos = 0
for (const f of ficheros(join(RAIZ, 'src'))) {
  let texto = readFileSync(f, 'utf8')
  const antes = texto
  for (const { origen, destino } of fusiones) {
    const rx = new RegExp(`(['"\`])${origen.replace(/\./g, '\\.')}\\1`, 'g')
    texto = texto.replace(rx, (m, q) => {
      usos += 1
      return `${q}${destino}${q}`
    })
  }
  if (texto !== antes) writeFileSync(f, texto, 'utf8')
}

// ── 2. Borrar la clave sobrante de los tres idiomas ──────────────────────────
let borradas = 0
for (const lang of ['es', 'en', 'zh']) {
  const ruta = join(RAIZ, 'src', 'i18n', 'langs', `${lang}.mjs`)
  let lineas = readFileSync(ruta, 'utf8').split('\n')
  for (const { origen } of fusiones) {
    const [modulo, ...resto] = origen.split('.')
    const hoja = resto.join('.')
    const apertura = lineas.findIndex((l) => new RegExp(`^\\s+${modulo}:\\s*\\{\\s*$`).test(l))
    if (apertura < 0) continue
    const sangria = lineas[apertura].match(/^\s*/)[0]
    const cierre = lineas.findIndex(
      (l, i) => i > apertura && new RegExp(`^${sangria}\\},?$`).test(l.trimEnd()))
    if (cierre < 0) continue
    const i = lineas.findIndex(
      (l, idx) => idx > apertura && idx < cierre
        && new RegExp(`^\\s+'?${hoja.replace(/\./g, '\\.')}'?:`).test(l))
    if (i >= 0) {
      lineas.splice(i, 1)
      borradas += 1
    }
  }
  writeFileSync(ruta, lineas.join('\n'), 'utf8')
}

console.log(`\n✓ ${usos} usos repuntados en el código, ${borradas} entradas borradas de los diccionarios.`)
