// Codemod (20-11-2026, regla contec/sin-input-nativo): <input> de texto y
// <textarea> sueltos → Input / Textarea del kit (components/ui).
//
// Qué hace, sin cambiar el comportamiento:
//  - <input type=text|search|email|number|password|url|tel|(sin type)> → <Input>
//  - <textarea> → <Textarea>
//  - `className`: `ds-input` se descarta (el kit ya pinta la caja); el resto de
//    clases (u-mono, clases de la pantalla) pasan a `inputClassName`.
//  - `<label className="sdm-field"><span>X</span><input/></label>` → `<Input label="X" />`
//  - El resto de atributos (value, onChange, onKeyDown, ref, list...) se conservan.
//
// Se salta (queda en la cuota de kit-pendientes.json): spread, `style`, className
// no literal, type dinámico, clases cuyo CSS toca el layout del propio campo
// (flex/grid/margen/posición), campos que son hijos directos de un contenedor
// flex/grid en fila (el envoltorio ui-field cambiaría el reparto) y ficheros que ya
// usan otro `Input`/`Textarea`.
//
// Uso: node scripts/codemods/inputs-al-kit.mjs [--dry-run] [--solo=ruta1,ruta2]
import fs from 'node:fs'
import path from 'node:path'
import { parse } from '@babel/parser'

const RAIZ = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..', '..')
const SRC = path.join(RAIZ, 'src')
const KIT = path.join(SRC, 'components', 'ui')
const dry = process.argv.includes('--dry-run')
const solo = (process.argv.find((a) => a.startsWith('--solo=')) || '').slice(7).split(',').filter(Boolean)
const TIPOS = new Set(['text', 'search', 'email', 'number', 'password', 'url', 'tel'])

function* recorrer(dir, re) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) { if (e.name !== 'node_modules') yield* recorrer(p, re) } else if (re.test(e.name)) yield p
  }
}

// ── CSS: reglas por clase ───────────────────────────────────────────────────
const cssPorClase = new Map() // clase -> [{ selector, cuerpo }]
for (const f of recorrer(SRC, /\.css$/)) {
  const txt = fs.readFileSync(f, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
  for (const m of txt.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    for (const c of m[1].matchAll(/\.([A-Za-z_][\w-]*)/g)) {
      if (!cssPorClase.has(c[1])) cssPorClase.set(c[1], [])
      cssPorClase.get(c[1]).push({ selector: m[1].trim(), cuerpo: m[2] })
    }
  }
}
const PROP_LAYOUT = /(^|;)\s*(flex|flex-grow|flex-shrink|flex-basis|grid-column|grid-row|grid-area|margin(-[a-z]+)?|position|align-self|justify-self|order|float|display|inset|top|left|right|bottom|transform)\s*:/i
/** ¿Alguna regla de la clase toca el layout del propio campo? (reglas de descendiente `.x .clase` cuentan igual) */
function claseConLayout(c) {
  return (cssPorClase.get(c) || []).some((r) => PROP_LAYOUT.test(';' + r.cuerpo))
}
const CLASES_SIN_CSS_RELEVANTE = new Set(['ds-input', 'u-mono'])
function esFlexEnFila(clases) {
  for (const c of clases) {
    for (const r of cssPorClase.get(c) || []) {
      if (/display\s*:\s*(inline-)?flex/i.test(r.cuerpo) && !/flex-direction\s*:\s*column/i.test(r.cuerpo)) return true
    }
  }
  return false
}

// ── AST ─────────────────────────────────────────────────────────────────────
function visitar(n, padre, fn) {
  if (!n || typeof n.type !== 'string') return
  n._padre = padre
  fn(n)
  for (const k of Object.keys(n)) {
    if (k === 'loc' || k === '_padre' || /Comments$/.test(k)) continue
    const v = n[k]
    if (Array.isArray(v)) v.forEach((h) => h && typeof h.type === 'string' && visitar(h, n, fn))
    else if (v && typeof v.type === 'string') visitar(v, n, fn)
  }
}
const nom = (opening) => (opening.name.type === 'JSXIdentifier' ? opening.name.name : null)
const atr = (opening, n) => opening.attributes.find((a) => a.type === 'JSXAttribute' && a.name.name === n)
const esTextoBlanco = (h) => h.type === 'JSXText' && !h.value.trim()

const stats = { migrados: 0, saltados: {} }
const salta = (m) => { stats.saltados[m] = (stats.saltados[m] || 0) + 1 }

function procesar(fichero) {
  const src = fs.readFileSync(fichero, 'utf8')
  if (!/<(input|textarea)\b/.test(src)) return
  let ast
  try { ast = parse(src, { sourceType: 'module', plugins: ['jsx', 'typescript'] }) } catch (e) { console.warn('no se pudo leer', fichero); return }
  const rel = path.relative(RAIZ, fichero).split(path.sep).join('/')

  // ¿hay ya un Input/Textarea propio en el fichero (no importado del kit)?
  let importKit = null
  const importados = new Set()
  for (const d of ast.program.body) {
    if (d.type !== 'ImportDeclaration') continue
    for (const s of d.specifiers) importados.add(s.local.name)
    if (/(^|\/)ui(\/index)?$/.test(d.source.value) && d.importKind !== 'type') importKit = d
  }
  const choca = (nombre) => importados.has(nombre) && !(importKit && importKit.specifiers.some((s) => s.local.name === nombre && s.imported?.name === nombre))
    || (!importados.has(nombre) && new RegExp(`\\b${nombre}\\b`).test(src.replace(/<\/?(input|textarea)\b/g, '')))

  // constantes de clase: const IS = 'ds-input x' (una sola declaración con ese nombre en el fichero)
  const constantes = new Map()
  const vistos = new Map()
  visitar(ast, null, (d) => {
    if (d.type === 'VariableDeclarator' && d.id.type === 'Identifier') {
      vistos.set(d.id.name, (vistos.get(d.id.name) || 0) + 1)
      if (d.init && d.init.type === 'StringLiteral') constantes.set(d.id.name, d.init.value)
    }
  })
  for (const k of [...constantes.keys()]) if (vistos.get(k) !== 1) constantes.delete(k)

  const cambios = [] // { start, end, texto }
  const usados = new Set()

  visitar(ast, null, (n) => {
    if (n.type !== 'JSXElement') return
    const op = n.openingElement
    const tag = nom(op)
    if (tag !== 'input' && tag !== 'textarea') return
    const atributos = op.attributes
    if (tag === 'input') {
      const t = atr(op, 'type')
      if (t) {
        const v = t.value
        if (!v || v.type !== 'StringLiteral') return salta('type dinámico')
        if (!TIPOS.has(v.value.trim().toLowerCase())) return // checkbox/radio/file/month...: no es de esta regla
      }
    }
    const nuevo = tag === 'input' ? 'Input' : 'Textarea'
    if (choca(nuevo)) return salta(`ya existe ${nuevo} propio en el fichero`)
    if (!n.closingElement && !op.selfClosing) return
    if (n.children.length) return salta('textarea con hijos')
    if (atributos.some((a) => a.type === 'JSXSpreadAttribute')) return salta('spread')
    if (atr(op, 'style')) return salta('style en línea')
    if (atr(op, 'dangerouslySetInnerHTML')) return salta('otro')
    const cn = atr(op, 'className')
    let clases = []
    if (cn) {
      if (cn.value && cn.value.type === 'StringLiteral') clases = cn.value.value.split(/\s+/).filter(Boolean)
      else if (cn.value && cn.value.type === 'JSXExpressionContainer' && cn.value.expression.type === 'Identifier' && constantes.has(cn.value.expression.name)) {
        clases = constantes.get(cn.value.expression.name).split(/\s+/).filter(Boolean)
      } else return salta('className no literal')
    }
    const propias = clases.filter((c) => !CLASES_SIN_CSS_RELEVANTE.has(c))
    if (propias.some(claseConLayout)) return salta('su clase toca el layout (flex/margen/posición...)')

    // Contexto: label envolvente o contenedor en fila
    let envoltorio = null
    const padre = n._padre
    if (padre && padre.type === 'JSXElement' && nom(padre.openingElement) === 'label') {
      const lop = padre.openingElement
      const hijos = padre.children.filter((h) => !esTextoBlanco(h))
      const lcn = atr(lop, 'className')
      const claseLabel = lcn && lcn.value && lcn.value.type === 'StringLiteral' ? lcn.value.value.trim() : null
      const spanI = hijos.findIndex((h) => h.type === 'JSXElement' && nom(h.openingElement) === 'span' && h.openingElement.attributes.length === 0)
      if (hijos.length === 2 && spanI === 0 && hijos[1] === n
        && lop.attributes.length === (lcn ? 1 : 0) && (claseLabel === null || claseLabel === 'sdm-field')
        && !atr(op, 'aria-labelledby')) {
        envoltorio = { label: padre, span: hijos[0] }
      }
    }
    if (!envoltorio) {
      // contenedor directo
      let p = n._padre
      while (p && p.type !== 'JSXElement') p = p._padre
      if (p) {
        const pn = nom(p.openingElement)
        if (pn && /^[A-Z]/.test(pn)) { if (/Toolbar|Barra|Fila|Row|Segment|Stack|Group|Inline/i.test(pn)) return salta('hijo de contenedor en fila (componente)') }
        else {
          const pcn = atr(p.openingElement, 'className')
          const pcl = pcn && pcn.value && pcn.value.type === 'StringLiteral' ? pcn.value.value.split(/\s+/) : []
          if (esFlexEnFila(pcl)) return salta('hijo de contenedor flex/grid en fila')
          if (pcn && pcn.value && pcn.value.type !== 'StringLiteral') return salta('hijo de contenedor con className dinámico')
          if (atr(p.openingElement, 'style')) return salta('hijo de contenedor con style')
        }
      }
    }

    // Atributos del nuevo elemento
    const partes = []
    for (const a of atributos) {
      if (a === cn) continue
      partes.push(src.slice(a.start, a.end))
    }
    const claseInput = clases.filter((c) => c !== 'ds-input').join(' ')
    if (claseInput) partes.push(`inputClassName="${claseInput}"`)
    if (envoltorio) {
      const hs = envoltorio.span.children
      let etiqueta
      if (hs.length === 1 && hs[0].type === 'JSXText') {
        const t = hs[0].value.replace(/\s+/g, ' ').trim()
        etiqueta = /["&<>{}\\]/.test(t) ? `{${JSON.stringify(t)}}` : `"${t}"`
      } else if (hs.length === 1 && hs[0].type === 'JSXExpressionContainer' && hs[0].expression.type !== 'JSXEmptyExpression') {
        etiqueta = `{${src.slice(hs[0].expression.start, hs[0].expression.end)}}`
      } else if (!hs.length) return salta('span vacío')
      else etiqueta = `{<>${src.slice(hs[0].start, hs[hs.length - 1].end)}</>}`
      partes.unshift(`label=${etiqueta}`)
    }
    const texto = `<${nuevo} ${partes.join(' ')} />`
    const objetivo = envoltorio ? envoltorio.label : n
    cambios.push({ start: objetivo.start, end: objetivo.end, texto })
    usados.add(nuevo)
    stats.migrados++
  })

  if (!cambios.length) return
  // sin solapes
  cambios.sort((a, b) => a.start - b.start)
  const limpios = []
  for (const c of cambios) { if (!limpios.length || c.start >= limpios[limpios.length - 1].end) limpios.push(c); else { stats.migrados--; salta('solape') } }
  let salida = src
  for (const c of [...limpios].reverse()) salida = salida.slice(0, c.start) + c.texto + salida.slice(c.end)

  // import
  if (importKit) {
    const ya = new Set(importKit.specifiers.map((s) => s.local.name))
    const faltan = [...usados].filter((u) => !ya.has(u))
    if (faltan.length) {
      const ultimo = importKit.specifiers[importKit.specifiers.length - 1]
      if (ultimo) {
        const pos = ultimo.end
        // las posiciones del import son anteriores a todos los cambios (los imports van arriba)
        salida = salida.slice(0, pos) + ', ' + faltan.join(', ') + salida.slice(pos)
      } else {
        const m = /import\s*\{\s*\}/.exec(salida)
        if (m) salida = salida.replace(m[0], `import { ${faltan.join(', ')} }`)
      }
    }
  } else {
    let r = path.relative(path.dirname(fichero), KIT).split(path.sep).join('/')
    if (!r.startsWith('.')) r = './' + r
    const imp = `import { ${[...usados].join(', ')} } from '${r}'\n`
    const ult = [...ast.program.body].filter((d) => d.type === 'ImportDeclaration').pop()
    if (ult) salida = salida.slice(0, ult.end) + '\n' + imp.trimEnd() + salida.slice(ult.end)
    else salida = imp + salida
  }
  if (!dry) fs.writeFileSync(fichero, salida)
  console.log(`${rel}: ${limpios.length}`)
}

for (const f of recorrer(SRC, /\.tsx$/)) {
  if (f.startsWith(KIT) || /__tests__|\.test\./.test(f)) continue
  const rel = path.relative(RAIZ, f).split(path.sep).join('/')
  if (solo.length && !solo.some((s) => rel.includes(s))) continue
  procesar(f)
}
console.log(JSON.stringify(stats, null, 1))
