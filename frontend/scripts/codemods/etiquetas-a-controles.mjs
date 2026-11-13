// Codemod (auditoria 2026-11, #10): etiquetas y nombres accesibles de controles.
//
// Tres patrones mecanicos, sin cambiar nada visible:
//  1. `<label>Texto</label>` seguido (hermano inmediato) de `<input|select|
//     textarea|DateInput>` sin asociar. Se asocian con un id generado con
//     useId() en el componente: la label recibe `id` y `htmlFor`; el control,
//     `id` (si no lo tenia) y, si es nativo, `aria-labelledby` (la regla
//     control-has-associated-label no puede ver un htmlFor de otro elemento).
//     Solo si el par esta en el cuerpo del propio componente: dentro de un
//     .map() o de una funcion auxiliar se salta (un hook ahi rompe las reglas de
//     hooks y un id fijo se repetiria en cada fila).
//  2. `<input>`/`<textarea>` sin etiqueta pero con placeholder descriptivo:
//     `aria-label` con ese mismo texto (no si es un ejemplo: "Ej: ...", "e.g.").
//  3. `<button>` solo con icono y con `title`: `aria-label` con el title.
//
// Idempotente: lo que ya esta asociado o etiquetado no se vuelve a tocar.
// Uso: node scripts/codemods/etiquetas-a-controles.mjs [--dry-run]
import fs from 'node:fs'
import path from 'node:path'
import { parse } from '@babel/parser'

const RAIZ = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..', '..')
const SRC = path.join(RAIZ, 'src')
const dry = process.argv.includes('--dry-run')
const NATIVOS = new Set(['input', 'select', 'textarea'])
const CONTROLES = new Set([...NATIVOS, 'DateInput'])
const HOOK = 'idCampo'

function* recorrer(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) yield* recorrer(p)
    else if (/\.tsx$/.test(e.name) && !/\.test\./.test(e.name) && !p.includes('__tests__')) yield p
  }
}

function visitar(n, padre, fn) {
  if (!n || typeof n.type !== 'string') return
  n._padre = padre
  fn(n)
  for (const k of Object.keys(n)) {
    if (k === 'loc' || k === '_padre' || k === 'leadingComments' || k === 'trailingComments' || k === 'innerComments') continue
    const v = n[k]
    if (Array.isArray(v)) v.forEach((h) => h && typeof h.type === 'string' && visitar(h, n, fn))
    else if (v && typeof v.type === 'string') visitar(v, n, fn)
  }
}

const nombre = (el) => (el.openingElement.name.type === 'JSXIdentifier' ? el.openingElement.name.name : null)
const attr = (el, n) => el.openingElement.attributes.find((a) => a.type === 'JSXAttribute' && a.name.name === n)
const conSpread = (el) => el.openingElement.attributes.some((a) => a.type === 'JSXSpreadAttribute')
const esFuncion = (n) => /^(FunctionDeclaration|FunctionExpression|ArrowFunctionExpression)$/.test(n.type)

/** El componente (funcion con nombre en mayuscula) si `n` esta directamente en su cuerpo. */
function componenteDe(n) {
  let p = n._padre
  while (p && !esFuncion(p)) p = p._padre
  if (!p || p.body.type !== 'BlockStatement') return null
  let nombreFn = p.type === 'FunctionDeclaration' && p.id ? p.id.name : null
  if (!nombreFn) {
    let q = p._padre
    while (q && q.type === 'CallExpression') q = q._padre   // forwardRef(...), memo(...)
    if (q && q.type === 'VariableDeclarator' && q.id.type === 'Identifier') nombreFn = q.id.name
  }
  return nombreFn && /^[A-Z]/.test(nombreFn) ? p : null
}

function hermanoSiguiente(el) {
  const padre = el._padre
  if (!padre || !padre.children) return null
  const i = padre.children.indexOf(el)
  for (let j = i + 1; j < padre.children.length; j++) {
    const h = padre.children[j]
    if (h.type === 'JSXText' && !h.value.trim()) continue
    return h.type === 'JSXElement' ? h : null
  }
  return null
}

function contieneControl(el) {
  let hay = false
  visitar(el, el._padre, (n) => { if (n !== el && n.type === 'JSXElement' && CONTROLES.has(nombre(n))) hay = true })
  return hay
}

const texto = (src, n) => src.slice(n.start, n.end)
const esEjemplo = (s) => /^\s*(ej[.:]|e\.g\.|p\. ?ej|ex[.:]|https?:|[0-9#@+(]|\.\.\.|…)/i.test(s)

const total = { pares: 0, saltados: 0, placeholder: 0, botones: 0, ficheros: 0 }
for (const fichero of recorrer(SRC)) {
  const src = fs.readFileSync(fichero, 'utf8')
  if (!/<label|placeholder|title=/.test(src)) continue
  const ast = parse(src, { sourceType: 'module', plugins: ['jsx', 'typescript'] })
  const cambios = []                       // [pos, texto a insertar]
  const usados = new Map()                 // componente -> contador
  const elementos = []
  visitar(ast.program, null, (n) => { if (n.type === 'JSXElement') elementos.push(n) })

  const asociados = new Set()
  for (const el of elementos) {
    if (nombre(el) !== 'label' || attr(el, 'htmlFor') || conSpread(el) || contieneControl(el)) continue
    const ctl = hermanoSiguiente(el)
    if (!ctl || !CONTROLES.has(nombre(ctl)) || conSpread(ctl)) continue
    if (attr(ctl, 'aria-labelledby') || attr(ctl, 'aria-label')) continue
    const comp = componenteDe(el)
    if (!comp || componenteDe(ctl) !== comp) { total.saltados++; continue }
    const n = (usados.get(comp) || 0) + 1
    usados.set(comp, n)
    const idCtl = attr(ctl, 'id')
    const refCtl = idCtl ? texto(src, idCtl.value) : `{\`\${${HOOK}}-${n}\`}`
    const idEt = attr(el, 'id')
    const refEt = idEt ? texto(src, idEt.value) : `{\`\${${HOOK}}-et${n}\`}`
    const finNombreEt = el.openingElement.name.end
    cambios.push([finNombreEt, `${idEt ? '' : ` id=${refEt}`} htmlFor=${refCtl}`])
    const finNombreCtl = ctl.openingElement.name.end
    const extra = `${idCtl ? '' : ` id=${refCtl}`}${NATIVOS.has(nombre(ctl)) ? ` aria-labelledby=${refEt}` : ''}`
    if (extra) cambios.push([finNombreCtl, extra])
    asociados.add(ctl)
    total.pares++
  }

  for (const el of elementos) {
    const nm = nombre(el)
    if ((nm === 'input' || nm === 'textarea') && !asociados.has(el) && !conSpread(el)) {
      if (attr(el, 'id') || attr(el, 'aria-label') || attr(el, 'aria-labelledby')) continue
      const tipo = attr(el, 'type')
      if (tipo && tipo.value && tipo.value.type === 'StringLiteral' && /^(hidden|file|checkbox|radio|submit|button)$/.test(tipo.value.value)) continue
      // Dentro de una <label> ya tiene nombre.
      let p = el._padre, enLabel = false
      while (p && !esFuncion(p)) { if (p.type === 'JSXElement' && nombre(p) === 'label') { enLabel = true; break } p = p._padre }
      if (enLabel) continue
      const ph = attr(el, 'placeholder')
      if (!ph || !ph.value) continue
      let valor = null
      if (ph.value.type === 'StringLiteral') { if (ph.value.value.trim().length > 1 && !esEjemplo(ph.value.value)) valor = texto(src, ph.value) }
      else if (ph.value.type === 'JSXExpressionContainer') {
        const e = ph.value.expression
        if (e.type === 'StringLiteral' && !esEjemplo(e.value) && e.value.trim().length > 1) valor = texto(src, ph.value)
        else if (e.type === 'CallExpression' && e.callee.type === 'Identifier' && e.callee.name === 't') valor = texto(src, ph.value)
      }
      if (!valor) continue
      cambios.push([el.openingElement.name.end, ` aria-label=${valor}`])
      total.placeholder++
    }
    if (nm === 'button' && !attr(el, 'aria-label') && !attr(el, 'aria-labelledby') && !conSpread(el)) {
      const title = attr(el, 'title')
      if (!title || !title.value) continue
      const hijos = el.children.filter((h) => !(h.type === 'JSXText' && !h.value.trim()))
      const soloIcono = hijos.every((h) => h.type === 'JSXElement' && (/^[A-Z]/.test(nombre(h) || '') || nombre(h) === 'svg'))
      if (!soloIcono) continue
      cambios.push([el.openingElement.name.end, ` aria-label=${texto(src, title.value)}`])
      total.botones++
    }
  }

  if (!cambios.length) continue
  // Hook al principio de cada componente que lo necesita.
  let usaReactDefault = false
  for (const comp of usados.keys()) {
    const cuerpo = comp.body
    if (src.slice(cuerpo.start, cuerpo.end).includes(`const ${HOOK} =`)) continue
    const primera = cuerpo.body[0]
    const ini = primera ? primera.start : cuerpo.start + 1
    const finLinea = src.lastIndexOf('\n', ini) + 1
    const sangria = primera ? src.slice(finLinea, ini) : '  '
    const llamada = /^import React\b/m.test(src) && !/^import \{[^}]*\}\s*from 'react'/m.test(src) ? 'React.useId()' : 'useId()'
    if (llamada === 'React.useId()') usaReactDefault = true
    const fin = src.includes('\r\n') ? '\r\n' : '\n'
    cambios.push([ini, `const ${HOOK} = ${llamada}${fin}${/^\s*$/.test(sangria) ? sangria : '  '}`])
  }
  let nuevo = src
  for (const [pos, ins] of cambios.sort((a, b) => b[0] - a[0])) nuevo = nuevo.slice(0, pos) + ins + nuevo.slice(pos)
  if (usados.size && !usaReactDefault) {
    const nl = nuevo.includes('\r\n') ? '\r\n' : '\n'
    const m = nuevo.match(/^import \{([^}]*)\}\s*from 'react'/m)
    if (m) {
      const items = m[1].split(',').map((s) => s.trim()).filter(Boolean)
      if (!items.includes('useId')) nuevo = nuevo.replace(m[0], `import { ${[...items, 'useId'].join(', ')} } from 'react'`)
    } else {
      const m2 = nuevo.match(/^import type \{[^}]*\}\s*from 'react'.*$/m) || nuevo.match(/^import .*$/m)
      const pos = m2 ? m2.index + m2[0].length : 0
      nuevo = nuevo.slice(0, pos) + `${nl}import { useId } from 'react'` + nuevo.slice(pos)
    }
  }
  total.ficheros++
  if (!dry) fs.writeFileSync(fichero, nuevo)
}
console.log(`${dry ? '[dry] ' : ''}pares label/control asociados: ${total.pares} (saltados por estar en .map/auxiliar: ${total.saltados}); aria-label desde placeholder: ${total.placeholder}; botones de icono con aria-label: ${total.botones}; ficheros: ${total.ficheros}`)
