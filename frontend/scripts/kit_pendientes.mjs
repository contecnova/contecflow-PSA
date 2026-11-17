#!/usr/bin/env node
// Lista de pendientes de la migración al kit (16-11-2026, fase 1).
//
// Cuenta, fichero a fichero, lo que hoy incumplen las reglas del kit
// (scripts/eslint/kit-sin-marcado-propio.mjs) y la comprobación de CSS
// (scripts/kit/comprobarCss.mjs), y escribe:
//   kit-pendientes.json    las excepciones temporales (las leen eslint.config.js
//                          y src/__tests__/kitCssSinRestos.test.ts)
//   kit-migracion-plan.md  el plan de la fase 2, en 3 bloques
//
// Uso (desde frontend/):
//   node scripts/kit_pendientes.mjs              encoge: baja cada cupo a lo que queda, quita los
//                                                ficheros ya limpios; nunca sube un cupo ni añade
//                                                ficheros (si hay incumplimientos nuevos, los lista y sale con 1)
//   node scripts/kit_pendientes.mjs --comprobar  solo comprueba (no escribe); sale con 1 si algo supera su cupo
//   node scripts/kit_pendientes.mjs --regenerar  rehace la lista desde cero con lo que hay hoy
//                                                (solo para crearla; después, encoger)
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { ESLint } from 'eslint'
import tsParser from '@typescript-eslint/parser'
import { reglasDelKit, IGNORADOS_KIT, NOMBRES_DE_REGLAS } from './eslint/kit-sin-marcado-propio.mjs'
import { recuentoCss, COMPROBACIONES_CSS } from './kit/comprobarCss.mjs'

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const FICHERO = path.join(RAIZ, 'kit-pendientes.json')
const PLAN = path.join(RAIZ, 'kit-migracion-plan.md')
const modo = process.argv.includes('--regenerar') ? 'regenerar' : process.argv.includes('--comprobar') ? 'comprobar' : 'encoger'

async function recuentoEslint() {
  const eslint = new ESLint({
    cwd: RAIZ,
    overrideConfigFile: true,
    overrideConfig: [{
      files: ['src/**/*.{js,jsx,ts,tsx}'],
      ignores: IGNORADOS_KIT,
      linterOptions: { reportUnusedDisableDirectives: 'off' },
      languageOptions: { parser: tsParser, parserOptions: { ecmaFeatures: { jsx: true } } },
      plugins: { contec: { rules: reglasDelKit } },
      rules: Object.fromEntries(NOMBRES_DE_REGLAS.map((r) => [r, 'error'])),
    }],
  })
  const resultados = await eslint.lintFiles(['src/**/*.{js,jsx,ts,tsx}'])
  const r = Object.fromEntries(NOMBRES_DE_REGLAS.map((n) => [n, {}]))
  for (const res of resultados) {
    const rel = path.relative(RAIZ, res.filePath).split(path.sep).join('/')
    for (const m of res.messages) {
      if (!m.ruleId) { if (m.fatal) console.warn(`[kit] ${rel}: ${m.message}`); continue }
      if (!r[m.ruleId]) continue // reglas de comentarios eslint-disable que esta config no carga
      r[m.ruleId][rel] = (r[m.ruleId][rel] || 0) + 1
    }
  }
  return r
}

const ordenar = (o) => Object.fromEntries(Object.entries(o).sort(([a], [b]) => a.localeCompare(b)))

function combinar(previo, actual, nuevos, seccion) {
  const salida = {}
  for (const [regla, ficheros] of Object.entries(actual)) {
    const cupos = (previo && previo[regla]) || {}
    salida[regla] = {}
    for (const [f, n] of Object.entries(ficheros)) {
      if (modo === 'regenerar') { salida[regla][f] = n; continue }
      const cupo = cupos[f] || 0
      if (n > cupo) nuevos.push(`${seccion} ${regla}: ${f} tiene ${n} (cupo ${cupo})`)
      if (cupo) salida[regla][f] = Math.min(cupo, n)
    }
    salida[regla] = ordenar(salida[regla])
  }
  return salida
}

// ── Plan de la fase 2 ────────────────────────────────────────────────────────

/** Área de un fichero: la pantalla o la carpeta. */
function area(rel) {
  let m = /^src\/pages\/([^/]+)\//.exec(rel)
  if (m) return `pages/${m[1]}`
  m = /^src\/pages\/([^/.]+?)(Page)?(Sections)?\.\w+$/.exec(rel)
  if (m) return `pages/${m[1]}`
  m = /^src\/components\/([^/]+)\//.exec(rel)
  if (m) return `components/${m[1]}`
  m = /^src\/([^/]+)\//.exec(rel)
  if (m) return m[1]
  return rel.replace(/^src\//, '').replace(/\.\w+$/, '')
}

export const BLOQUES = {
  A: 'Operador A–L',
  B: 'Operador M–Z (incluido service desk)',
  C: 'Portal de clientes, componentes compartidos y Ajustes',
}

/** Bloque de un fichero. Las carpetas de componentes propias de un área van
 *  con sus pantallas (un mismo agente migra el área entera); el resto de
 *  components/ es compartido. Ajustes (Settings*, settings-sections) va al
 *  bloque C para equilibrar: con él, M–Z tendría ~45 % de los incumplimientos. */
export function bloque(rel) {
  if (/^src\/pages\/(portal-client\/|Portal|ClientPortalPage)/.test(rel) || /^src\/components\/portal\//.test(rel)) return 'C'
  if (/^src\/pages\/(settings-sections\/|SettingsPage)/.test(rel)) return 'C'
  if (/^src\/pages\/(service-desk\/|ServiceDeskPage)/.test(rel)) return 'B'
  const m = /^src\/pages\/([^/]+)/.exec(rel)
  if (m) return /^[a-l]/i.test(m[1]) ? 'A' : 'B'
  const c = /^src\/components\/([^/]+)\//.exec(rel)
  if (c && COMPONENTES_POR_BLOQUE[c[1]]) return COMPONENTES_POR_BLOQUE[c[1]]
  return 'C'
}
/** Carpetas de components/ que son de un área concreta (no compartidas). */
const COMPONENTES_POR_BLOQUE = {
  alm: 'A', aprobaciones: 'A', externos: 'A', flujos: 'A', gastos: 'A', invoices: 'A',
  servicedesk: 'B', cmdb: 'B',
}

const ABREV = {
  'contec/sin-boton-nativo': 'botón', 'contec/sin-tabla-propia': 'tabla', 'contec/sin-select-nativo': 'select',
  'contec/sin-casilla-suelta': 'casilla', 'contec/sin-fieldset-propio': 'fieldset',
  mayusculas: 'MAYÚS', monoespaciada: 'mono', colorLiteral: 'color', altoFijoControl: 'alto px',
}

function escribirPlan(lista) {
  const columnas = [...NOMBRES_DE_REGLAS, ...COMPROBACIONES_CSS]
  const porFichero = {}
  for (const r of NOMBRES_DE_REGLAS) for (const [f, n] of Object.entries(lista.eslint[r] || {})) (porFichero[f] ??= {})[r] = n
  for (const c of COMPROBACIONES_CSS) for (const [f, n] of Object.entries(lista.css[c] || {})) (porFichero[f] ??= {})[c] = n
  const total = (f) => columnas.reduce((s, c) => s + (porFichero[f][c] || 0), 0)
  const totales = Object.fromEntries(columnas.map((c) => [c, 0]))
  for (const f of Object.keys(porFichero)) for (const c of columnas) totales[c] += porFichero[f][c] || 0

  const L = []
  L.push('# Migración al kit — plan de la fase 2', '')
  L.push('> Generado por `node scripts/kit_pendientes.mjs` a partir de `kit-pendientes.json`. No se edita a mano:')
  L.push('> al terminar un fichero, se vuelve a ejecutar el script (encoge la lista y rehace este plan).', '')
  L.push('Cada fichero tiene un cupo de incumplimientos por regla (lo que tenía al crear la lista). ESLint y el test')
  L.push('`kitCssSinRestos` fallan si un fichero supera su cupo o si aparece en un fichero que no está en la lista.')
  L.push('Objetivo: dejar cada fichero a 0 y que salga de la lista. Piezas y cuándo usarlas: `src/components/ui/DESIGN_SYSTEM.md`, «Migración al kit».', '')
  L.push('## Recuento total', '', '| Regla | Incumplimientos | Ficheros |', '|---|---:|---:|')
  for (const c of columnas) {
    const nombre = c.startsWith('contec/') ? `\`${c}\`` : `CSS \`${c}\``
    L.push(`| ${nombre} | ${totales[c]} | ${Object.keys(c.startsWith('contec/') ? lista.eslint[c] || {} : lista.css[c] || {}).length} |`)
  }
  const sumaTotal = Object.values(totales).reduce((a, b) => a + b, 0)
  L.push(`| **Total** | **${sumaTotal}** | **${Object.keys(porFichero).length}** |`, '')

  const bloques = { A: [], B: [], C: [] }
  for (const f of Object.keys(porFichero)) bloques[bloque(f)].push(f)
  L.push('## Reparto', '', '| Bloque | Ficheros | Incumplimientos |', '|---|---:|---:|')
  for (const [b, fs_] of Object.entries(bloques)) L.push(`| ${b}. ${BLOQUES[b]} | ${fs_.length} | ${fs_.reduce((s, f) => s + total(f), 0)} |`)
  L.push('')
  L.push('Columnas: botón = `<button>`, tabla = `<table>`, select = `<select>`, casilla = checkbox/radio suelto,')
  L.push('fieldset = `<fieldset>` propio, MAYÚS = text-transform, mono = letra monoespaciada, color = hex/rgb literal,')
  L.push('alto px = `height` fijo en un control.', '')

  for (const [b, ficheros] of Object.entries(bloques)) {
    const porArea = {}
    for (const f of ficheros) (porArea[area(f)] ??= []).push(f)
    const areas = Object.entries(porArea).sort(([a], [b2]) => a.localeCompare(b2))
    L.push(`## Bloque ${b}. ${BLOQUES[b]} — ${ficheros.length} ficheros, ${ficheros.reduce((s, f) => s + total(f), 0)} incumplimientos`, '')
    L.push(`| Área | Fichero | ${columnas.map((c) => ABREV[c]).join(' | ')} | Total |`)
    L.push(`|---|---|${columnas.map(() => '---:').join('|')}|---:|`)
    for (const [a, fsArea] of areas) {
      fsArea.sort((x, y) => total(y) - total(x) || x.localeCompare(y))
      for (const f of fsArea) L.push(`| ${a} | \`${f.replace(/^src\//, '')}\` | ${columnas.map((c) => porFichero[f][c] || '').join(' | ')} | ${total(f)} |`)
    }
    L.push('')
  }
  fs.writeFileSync(PLAN, L.join('\n'))
}

// ── Principal ────────────────────────────────────────────────────────────────

const previo = fs.existsSync(FICHERO) ? JSON.parse(fs.readFileSync(FICHERO, 'utf8')) : null
if (!previo && modo !== 'regenerar') {
  console.error('[kit] No existe kit-pendientes.json: créalo con --regenerar.')
  process.exit(1)
}
const actualEslint = await recuentoEslint()
const actualCss = recuentoCss(RAIZ)
const nuevos = []
const lista = {
  _leeme: 'Excepciones temporales de la migración al kit: cupo de incumplimientos por regla y fichero. Solo puede encoger. Regenera con node scripts/kit_pendientes.mjs (ver cabecera del script).',
  eslint: combinar(previo?.eslint, actualEslint, nuevos, 'eslint'),
  css: combinar(previo?.css, actualCss, nuevos, 'css'),
}

if (nuevos.length) {
  console.error(`[kit] ${nuevos.length} incumplimientos por encima del cupo (usa el kit; la lista no crece):`)
  for (const n of nuevos) console.error(`  - ${n}`)
}
if (modo !== 'comprobar') {
  fs.writeFileSync(FICHERO, `${JSON.stringify(lista, null, 2)}\n`)
  escribirPlan(lista)
  const cuenta = (s) => Object.values(s).reduce((a, o) => a + Object.values(o).reduce((x, y) => x + y, 0), 0)
  console.log(`[kit] ${modo}: eslint ${cuenta(lista.eslint)} · css ${cuenta(lista.css)} pendientes. Escritos kit-pendientes.json y kit-migracion-plan.md.`)
}
process.exit(nuevos.length ? 1 : 0)
