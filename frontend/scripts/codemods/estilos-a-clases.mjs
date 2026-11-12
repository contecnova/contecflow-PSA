// Codemod (auditoria 2026-11, #17): estilos en linea repetidos -> clases de utilidad.
//
// Mide los `style={{...}}` estaticos (solo literales) de src/ y sustituye por
// una clase `u-*` de src/index.css los que coinciden EXACTAMENTE con uno de los
// patrones de la tabla PATRONES (mismas propiedades y mismos valores; el orden
// de las propiedades da igual porque ninguno mezcla abreviada y larga).
//
// Que se toca y que no, para que el resultado se vea igual:
//  - Solo elementos nativos (<div>, <span>...): un componente puede no aceptar
//    className.
//  - Sin `{...spread}`: podria traer su propio className o style.
//  - Si ya hay className, solo si es un literal ("a b"): se le anade la clase.
//    Con un className dinamico no se toca.
//  - Las clases u-* van al FINAL de index.css: con la misma especificidad ganan a
//    las anteriores, como ganaba el estilo en linea. Un selector mas especifico
//    (p. ej. `.ds-card h3`) que fije la misma propiedad si ganaria ahora: es el
//    riesgo residual (ver informe).
//
// Idempotente: tras una pasada no queda ningun style que coincida.
//
// Uso:
//   node scripts/codemods/estilos-a-clases.mjs --medir [N]   # top N patrones (por defecto 40)
//   node scripts/codemods/estilos-a-clases.mjs --dry-run
//   node scripts/codemods/estilos-a-clases.mjs
import fs from 'node:fs'
import path from 'node:path'
import { parse } from '@babel/parser'

const RAIZ = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..', '..')
const SRC = path.join(RAIZ, 'src')
const dry = process.argv.includes('--dry-run')
const medir = process.argv.includes('--medir')

// Los 40 patrones mas repetidos medidos en 2026-11 (todos con >= 25 apariciones).
// [clase, estilo]. La regla CSS de cada uno esta en src/index.css (bloque
// "Utilidades u-*"), con los mismos valores.
export const PATRONES = [
  ['u-text3-xs', { color: 'var(--text-3)', fontSize: 'var(--text-xs)' }],
  ['u-text2-sm', { color: 'var(--text-2)', fontSize: 'var(--text-sm)' }],
  ['u-text2-xs', { color: 'var(--text-2)', fontSize: 'var(--text-xs)' }],
  ['u-flex1', { flex: 1 }],
  ['u-col-full', { gridColumn: '1/-1' }],
  ['u-field-error', { color: 'var(--danger)', fontSize: 'var(--text-xs)', marginTop: 4 }],
  ['u-flex1-min0', { flex: 1, minWidth: 0 }],
  ['u-text3-sm', { color: 'var(--text-3)', fontSize: 'var(--text-sm)' }],
  ['u-stack-14', { display: 'flex', flexDirection: 'column', gap: 14 }],
  ['u-text2', { color: 'var(--text-2)' }],
  ['u-stack-10', { display: 'flex', flexDirection: 'column', gap: 10 }],
  ['u-row-8', { display: 'flex', gap: 8 }],
  ['u-text3', { color: 'var(--text-3)' }],
  ['u-row-center-8', { display: 'flex', alignItems: 'center', gap: 8 }],
  ['u-actions-10', { display: 'flex', gap: 10, justifyContent: 'flex-end' }],
  ['u-text1', { color: 'var(--text-1)' }],
  ['u-row-6', { display: 'flex', gap: 6 }],
  ['u-stack-12', { display: 'flex', flexDirection: 'column', gap: 12 }],
  ['u-actions-8', { display: 'flex', gap: 8, justifyContent: 'flex-end' }],
  ['u-md-700', { fontSize: 'var(--text-md)', fontWeight: 700 }],
  ['u-stack-8', { display: 'flex', flexDirection: 'column', gap: 8 }],
  ['u-base-600', { fontSize: 'var(--text-base)', fontWeight: 600 }],
  ['u-sm', { fontSize: 'var(--text-sm)' }],
  ['u-grid2-12', { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }],
  ['u-stack-16', { display: 'flex', flexDirection: 'column', gap: 16 }],
  ['u-mb-16', { marginBottom: 16 }],
  ['u-scroll-x', { overflowX: 'auto' }],
  ['u-text2-base', { color: 'var(--text-2)', fontSize: 'var(--text-base)' }],
  ['u-row-center-10', { display: 'flex', alignItems: 'center', gap: 10 }],
  ['u-stack-6', { display: 'flex', flexDirection: 'column', gap: 6 }],
  ['u-wrap-8', { display: 'flex', flexWrap: 'wrap', gap: 8 }],
  ['u-mb-20', { marginBottom: 20 }],
  ['u-hint', { color: 'var(--text-3)', fontSize: 'var(--text-xs)', marginTop: 4 }],
  ['u-danger', { color: 'var(--danger)' }],
  ['u-text3-2xs', { color: 'var(--text-3)', fontSize: 'var(--text-2xs)' }],
  ['u-wrap-6', { display: 'flex', flexWrap: 'wrap', gap: 6 }],
  ['u-xs', { fontSize: 'var(--text-xs)' }],
  ['u-row-between', { display: 'flex', alignItems: 'center', justifyContent: 'space-between' }],
  ['u-warning', { color: 'var(--warning)' }],
  ['u-min0', { minWidth: 0 }],
]

const canon = (pares) => JSON.stringify([...pares].sort((a, b) => (a[0] < b[0] ? -1 : 1)))
const PORCLAVE = new Map(PATRONES.map(([cls, st]) => [canon(Object.entries(st)), cls]))

function* recorrer(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) yield* recorrer(p)
    else if (/\.(tsx|jsx)$/.test(e.name) && !/\.test\./.test(e.name) && !p.includes('__tests__')) yield p
  }
}

function visitar(n, fn) {
  if (!n || typeof n.type !== 'string') return
  fn(n)
  for (const k of Object.keys(n)) {
    if (k === 'loc') continue
    const v = n[k]
    if (Array.isArray(v)) v.forEach((h) => h && typeof h.type === 'string' && visitar(h, fn))
    else if (v && typeof v.type === 'string') visitar(v, fn)
  }
}

/** Los pares [prop, valor] de un objeto de estilo SOLO de literales; si no, null. */
function literal(obj) {
  const pares = []
  for (const p of obj.properties) {
    if (p.type !== 'ObjectProperty' || p.computed) return null
    const k = p.key.type === 'Identifier' ? p.key.name : p.key.type === 'StringLiteral' ? p.key.value : null
    let v = null
    if (p.value.type === 'StringLiteral' || p.value.type === 'NumericLiteral') v = p.value.value
    else if (p.value.type === 'UnaryExpression' && p.value.operator === '-' && p.value.argument.type === 'NumericLiteral') v = -p.value.argument.value
    if (k == null || v == null) return null
    pares.push([k, v])
  }
  return pares
}

let estilosTotales = 0
let sustituidos = 0
let ficheros = 0
const conteo = new Map()
for (const fichero of recorrer(SRC)) {
  const texto = fs.readFileSync(fichero, 'utf8')
  if (!texto.includes('style={{')) continue
  const ast = parse(texto, { sourceType: 'module', plugins: ['jsx', 'typescript'] })
  const cambios = []
  visitar(ast.program, (n) => {
    if (n.type !== 'JSXOpeningElement') return
    const st = n.attributes.find((a) => a.type === 'JSXAttribute' && a.name.name === 'style')
    if (!st || !st.value || st.value.type !== 'JSXExpressionContainer' || st.value.expression.type !== 'ObjectExpression') return
    estilosTotales++
    const pares = literal(st.value.expression)
    if (!pares) return
    if (n.name.type !== 'JSXIdentifier' || !/^[a-z]/.test(n.name.name)) return
    if (n.attributes.some((a) => a.type === 'JSXSpreadAttribute')) return
    const cn = n.attributes.find((a) => a.type === 'JSXAttribute' && a.name.name === 'className')
    if (cn && (!cn.value || cn.value.type !== 'StringLiteral')) return
    const clave = canon(pares)
    if (medir) { conteo.set(clave, (conteo.get(clave) || 0) + 1); return }
    const cls = PORCLAVE.get(clave)
    if (!cls) return
    if (cn) {
      const actual = cn.value.value.split(/\s+/).filter(Boolean)
      if (!actual.includes(cls)) {
        const q = texto[cn.value.start]
        cambios.push([cn.value.start, cn.value.end, `${q}${[...actual, cls].join(' ')}${q}`])
      }
      // Quita el style y el espacio que lo precede (o la linea entera si va solo).
      let ini = st.start
      while (ini > 0 && /[ \t]/.test(texto[ini - 1])) ini--
      let fin = st.end
      if (texto[ini - 1] === '\n') {
        let f = st.end
        while (/[ \t]/.test(texto[f])) f++
        if (texto[f] === '\r') f++
        if (texto[f] === '\n') fin = f + 1
        else ini = st.start
      }
      cambios.push([ini, fin, ''])
    } else {
      cambios.push([st.start, st.end, `className="${cls}"`])
    }
    sustituidos++
  })
  if (!cambios.length) continue
  let nuevo = texto
  for (const [ini, fin, rep] of cambios.sort((a, b) => b[0] - a[0])) nuevo = nuevo.slice(0, ini) + rep + nuevo.slice(fin)
  ficheros++
  if (!dry) fs.writeFileSync(fichero, nuevo)
}

if (medir) {
  const n = Number(process.argv[process.argv.indexOf('--medir') + 1]) || 40
  const orden = [...conteo].sort((a, b) => b[1] - a[1])
  let acum = 0
  console.log(`style={{}} totales: ${estilosTotales}; estaticos y aptos: ${[...conteo.values()].reduce((a, b) => a + b, 0)}; distintos: ${conteo.size}`)
  for (const [k, c] of orden.slice(0, n)) { acum += c; console.log(String(c).padStart(5), String(acum).padStart(6), PORCLAVE.get(k) || '-', k) }
} else {
  console.log(`style={{}} totales: ${estilosTotales}. ${sustituidos} ${dry ? 'a sustituir' : 'sustituidos'} por clases u-* en ${ficheros} ficheros.`)
}
