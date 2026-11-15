// Codemod (auditoria 2026-11, pasada final de estilos en linea).
//
// Clasifica cada `style={{...}}` de src/ (AST de Babel) y lo reescribe:
//  (a) valores estaticos       -> clase en el CSS del fichero (con tokens)
//  (b) ternarios/condicionales -> clases modificadoras (`cond ? 'x-m1' : 'x-m2'`)
//  (c) colores/tamanos literales -> var(--token) cuando coincide exactamente con uno
//  (d) valores de datos        -> propiedad CSS personalizada (`'--x': valor`)
//                                 consumida por la clase; nunca propiedades crudas.
//
// Cascada: los estilos en linea ganaban a todo. Las reglas generadas van al
// final del CSS del fichero; las modificadoras despues de las base, de modo que
// una propiedad larga condicional gana a una abreviada estatica (como en linea).
// Un par abreviada/larga cuyo orden no se pueda reproducir deja el atributo como
// esta (se informa como residual).
//
// Seguro: solo elementos nativos o componentes cuyo codigo recibe `className`;
// nada con `{...spread}` en el elemento; solo objetos resolubles por completo.
// Idempotente (los residuales se quedan). Uso:
//   node scripts/codemods/estilos-en-linea.mjs --medir      # clasifica, no escribe
//   node scripts/codemods/estilos-en-linea.mjs --dry-run
//   node scripts/codemods/estilos-en-linea.mjs [--residuales]
import fs from 'node:fs'
import path from 'node:path'
import { parse } from '@babel/parser'
import postcss from 'postcss'

const RAIZ = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..', '..')
const SRC = path.join(RAIZ, 'src')
const MEDIR = process.argv.includes('--medir')
const DRY = process.argv.includes('--dry-run')
const RESIDUALES = process.argv.includes('--residuales')

// ── Tokens (index.css) ───────────────────────────────────────────────────────
const indexCss = fs.readFileSync(path.join(SRC, 'index.css'), 'utf8')
const raiz = postcss.parse(indexCss).nodes.find((n) => n.type === 'rule' && n.selector === ':root')
const normColor = (v) => v.toLowerCase().replace(/\s+/g, '').replace(/(^|[^0-9])0\./g, '$1.')
const PRIORIDAD = ['surface', 'text-', 'accent', 'success', 'warning', 'danger', 'info', 'purple', 'orange', 'coral']
const COLORES = new Map()
const TAMANOS = new Map()
for (const d of raiz.nodes) {
  if (d.type !== 'decl' || !d.prop.startsWith('--')) continue
  const nombre = d.prop.slice(2)
  const val = d.value.trim()
  if (/^(#[0-9a-f]{3,8}|rgba?\(.*\))$/i.test(val)) {
    const k = normColor(val)
    const previo = COLORES.get(k)
    const rango = (n) => { const i = PRIORIDAD.findIndex((p) => n.startsWith(p)); return i < 0 ? 99 : i }
    if (!previo || rango(nombre) < rango(previo)) COLORES.set(k, nombre)
  }
  const m = /^text-(.+)$/.exec(nombre)
  if (m && /^\d+(\.\d+)?px$/.test(val) && !/-(h|em)$/.test(nombre) && !TAMANOS.has(val)) TAMANOS.set(val, nombre)
}
// En --text-md-em y similares (15px...) solo si no hay otro nombre.
for (const d of raiz.nodes) {
  if (d.type === 'decl' && /^--text-/.test(d.prop) && /^\d+(\.\d+)?px$/.test(d.value.trim()) && !TAMANOS.has(d.value.trim()) && !/-h$/.test(d.prop)) TAMANOS.set(d.value.trim(), d.prop.slice(2))
}
const RADIOS = new Map([['6px', 'radius-sm'], ['10px', 'radius-md'], ['14px', 'radius-lg'], ['18px', 'radius-xl'], ['999px', 'radius-full'], ['9999px', 'radius-full']])

// ── Utilidades de AST ────────────────────────────────────────────────────────
function* recorrer(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) { if (e.name !== '__tests__') yield* recorrer(p) }
    else if (/\.(tsx|jsx)$/.test(e.name) && !/\.test\./.test(e.name)) yield p
  }
}
function visitar(n, fn, padre = null) {
  if (!n || typeof n.type !== 'string') return
  fn(n, padre)
  for (const k of Object.keys(n)) {
    if (k === 'loc') continue
    const v = n[k]
    if (Array.isArray(v)) v.forEach((h) => h && typeof h.type === 'string' && visitar(h, fn, n))
    else if (v && typeof v.type === 'string') visitar(v, fn, n)
  }
}
const quitarTs = (n) => { while (n && (n.type === 'TSAsExpression' || n.type === 'TSSatisfiesExpression' || n.type === 'ParenthesizedExpression' || n.type === 'TSNonNullExpression')) n = n.expression; return n }

/** Valor estatico: {v: string|number} o null. */
function estatico(n) {
  n = quitarTs(n)
  if (!n) return null
  if (n.type === 'StringLiteral') return { v: n.value }
  if (n.type === 'NumericLiteral') return { v: n.value }
  if (n.type === 'UnaryExpression' && n.operator === '-' && n.argument.type === 'NumericLiteral') return { v: -n.argument.value }
  if (n.type === 'TemplateLiteral' && n.expressions.length === 0) return { v: n.quasis[0].value.cooked }
  return null
}
function ausente(n) {
  n = quitarTs(n)
  return !!n && ((n.type === 'Identifier' && n.name === 'undefined') || n.type === 'NullLiteral' || (n.type === 'BooleanLiteral' && n.value === false) || (n.type === 'StringLiteral' && n.value === ''))
}
function nombreClave(p) {
  let k = p.key
  if (p.computed) { k = quitarTs(k); return k.type === 'StringLiteral' ? k.value : null }
  return k.type === 'Identifier' ? k.name : k.type === 'StringLiteral' ? k.value : null
}

// ── Propiedades CSS ──────────────────────────────────────────────────────────
const SIN_UNIDAD = new Set(['animationIterationCount', 'aspectRatio', 'borderImageOutset', 'borderImageSlice', 'borderImageWidth', 'boxFlex', 'boxFlexGroup', 'boxOrdinalGroup', 'columnCount', 'columns', 'flex', 'flexGrow', 'flexPositive', 'flexShrink', 'flexNegative', 'flexOrder', 'gridArea', 'gridRow', 'gridRowEnd', 'gridRowSpan', 'gridRowStart', 'gridColumn', 'gridColumnEnd', 'gridColumnSpan', 'gridColumnStart', 'fontWeight', 'lineClamp', 'lineHeight', 'opacity', 'order', 'orphans', 'scale', 'tabSize', 'widows', 'zIndex', 'zoom', 'WebkitLineClamp', 'fillOpacity', 'floodOpacity', 'stopOpacity', 'strokeDasharray', 'strokeDashoffset', 'strokeMiterlimit', 'strokeOpacity', 'strokeWidth'])
const kebab = (p) => {
  if (p.startsWith('--')) return p
  const s = p.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase())
  return /^(Webkit|Moz|O)[A-Z]/.test(p) ? '-' + s.replace(/^-/, '') : /^ms[A-Z]/.test(p) ? '-' + s : s
}
const LONGITUDES = /^(width|height|top|left|right|bottom|inset|margin\w*|padding\w*|gap|rowGap|columnGap|fontSize|borderRadius|border(Top|Bottom|Left|Right)Width|borderWidth|flexBasis|(min|max)(Width|Height)|letterSpacing|textIndent|outlineOffset|border(Top|Bottom)(Left|Right)Radius)$/
const esLongitud = (p) => LONGITUDES.test(p)
const ABREV = {
  margin: ['marginTop', 'marginRight', 'marginBottom', 'marginLeft', 'marginInline', 'marginBlock'],
  padding: ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'paddingInline', 'paddingBlock'],
  border: ['borderTop', 'borderRight', 'borderBottom', 'borderLeft', 'borderColor', 'borderWidth', 'borderStyle', 'borderTopColor', 'borderRightColor', 'borderBottomColor', 'borderLeftColor', 'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth', 'borderTopStyle', 'borderBottomStyle', 'borderLeftStyle', 'borderRightStyle'],
  borderTop: ['borderTopColor', 'borderTopWidth', 'borderTopStyle'],
  borderBottom: ['borderBottomColor', 'borderBottomWidth', 'borderBottomStyle'],
  borderLeft: ['borderLeftColor', 'borderLeftWidth', 'borderLeftStyle'],
  borderRight: ['borderRightColor', 'borderRightWidth', 'borderRightStyle'],
  borderColor: ['borderTopColor', 'borderRightColor', 'borderBottomColor', 'borderLeftColor'],
  borderWidth: ['borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth'],
  borderStyle: ['borderTopStyle', 'borderRightStyle', 'borderBottomStyle', 'borderLeftStyle'],
  borderRadius: ['borderTopLeftRadius', 'borderTopRightRadius', 'borderBottomLeftRadius', 'borderBottomRightRadius'],
  background: ['backgroundColor', 'backgroundImage', 'backgroundSize', 'backgroundPosition', 'backgroundRepeat', 'backgroundClip', 'backgroundOrigin', 'backgroundAttachment'],
  font: ['fontSize', 'fontWeight', 'fontFamily', 'lineHeight', 'fontStyle', 'fontVariant'],
  flex: ['flexGrow', 'flexShrink', 'flexBasis'],
  flexFlow: ['flexDirection', 'flexWrap'],
  overflow: ['overflowX', 'overflowY'],
  gap: ['rowGap', 'columnGap'],
  inset: ['top', 'right', 'bottom', 'left'],
  outline: ['outlineColor', 'outlineWidth', 'outlineStyle', 'outlineOffset'],
  transition: ['transitionProperty', 'transitionDuration', 'transitionTimingFunction', 'transitionDelay'],
  animation: ['animationName', 'animationDuration', 'animationTimingFunction', 'animationDelay', 'animationIterationCount', 'animationDirection', 'animationFillMode'],
  textDecoration: ['textDecorationLine', 'textDecorationColor', 'textDecorationStyle', 'textDecorationThickness'],
  gridColumn: ['gridColumnStart', 'gridColumnEnd'],
  gridRow: ['gridRowStart', 'gridRowEnd'],
  placeItems: ['alignItems', 'justifyItems'],
  placeContent: ['alignContent', 'justifyContent'],
  listStyle: ['listStyleType', 'listStylePosition', 'listStyleImage'],
}
const solapan = (a, b) => a === b || (ABREV[a] || []).includes(b) || (ABREV[b] || []).includes(a)
  || Object.values(ABREV).some((l) => l.includes(a) && l.includes(b) && false)

/** Valor estatico -> texto CSS (con tokens cuando coincide exactamente). */
function valorCss(prop, v) {
  let s
  if (typeof v === 'number') s = v === 0 || SIN_UNIDAD.has(prop) ? String(v) : `${v}px`
  else s = v
  const t = s.trim()
  if (/^(color|background|backgroundColor|borderColor|borderTopColor|borderBottomColor|borderLeftColor|borderRightColor|fill|stroke|outlineColor|border|borderTop|borderBottom|borderLeft|borderRight|outline|boxShadow|textShadow)$/.test(prop)) {
    // Sustituye cada color literal por su token si coincide exactamente.
    return t.replace(/#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)/g, (c) => { const n = COLORES.get(normColor(c)); return n ? `var(--${n})` : c })
  }
  if (prop === 'fontSize' && TAMANOS.has(t)) return `var(--${TAMANOS.get(t)})`
  if (prop === 'borderRadius' && RADIOS.has(t)) return `var(--${RADIOS.get(t)})`
  return t
}
const esLiteralDeTema = (prop, v) => {
  const s = String(v)
  if (/(color|background|border|fill|stroke|outline|shadow)/i.test(prop) && /#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(s)) return true
  return (prop === 'fontSize' && typeof v === 'number') || (prop === 'borderRadius' && typeof v === 'number' && v !== 0)
}

// ── Constantes de estilo del modulo (para resolver `...S.card`) ──────────────
function constantesDelModulo(ast) {
  // Todas las `const X = {…}` del fichero, de cualquier nivel, con el alcance
  // (bloque que las contiene). `get(nombre, pos)` devuelve la mas cercana que
  // contiene a `pos`; asi dos `const fs` distintas en componentes distintos no se mezclan.
  const lista = []
  const pila = [ast.program]
  ;(function rec(n, padre) {
    if (!n || typeof n.type !== 'string') return
    const abre = n.type === 'BlockStatement' || n.type === 'Program'
    if (abre) pila.push(n)
    if (n.type === 'VariableDeclaration' && n.kind === 'const' && n.declarations.length === 1 && !(padre && padre.type === 'ExportNamedDeclaration')) {
      const dec = n.declarations[0]
      const init = quitarTs(dec.init)
      if (dec.id.type === 'Identifier' && init && init.type === 'ObjectExpression') {
        const ambito = pila[pila.length - 1]
        const sentencia = n
        lista.push({ nombre: dec.id.name, obj: init, sentencia, ini: ambito.start, fin: ambito.end })
      }
    }
    for (const k of Object.keys(n)) {
      if (k === 'loc') continue
      const v = n[k]
      if (Array.isArray(v)) v.forEach((h) => rec(h, n))
      else if (v && typeof v.type === 'string') rec(v, n)
    }
    if (abre) pila.pop()
  })(ast.program, null)
  return {
    lista,
    get(nombre, pos) {
      let mejor = null
      for (const d of lista) if (d.nombre === nombre && pos >= d.ini && pos <= d.fin && (!mejor || d.fin - d.ini < mejor.fin - mejor.ini)) mejor = d
      return mejor
    },
  }
}
function resolverMiembro(n, consts, usadas) {
  n = quitarTs(n)
  if (n.type === 'Identifier') { const c = consts.get(n.name, n.start); if (c) { usadas.add(n.name); return c.obj } return null }
  if (n.type === 'MemberExpression') {
    const base = resolverMiembro(n.object, consts, usadas)
    if (!base) return null
    const clave = n.computed ? (n.property.type === 'StringLiteral' ? n.property.value : null) : n.property.name
    const p = base.properties.find((q) => q.type === 'ObjectProperty' && nombreClave(q) === clave)
    const v = p && quitarTs(p.value)
    return v && v.type === 'ObjectExpression' ? v : null
  }
  return null
}

// ── Recogida de entradas de un objeto de estilo ──────────────────────────────
// entrada: {prop, tipo: 'est'|'dyn'|'var'|'cond', ...}
function recoger(obj, texto, ctx, entradas, soloEstatico) {
  for (const p of obj.properties) {
    if (p.type === 'SpreadElement') {
      const arg = quitarTs(p.argument)
      const r = resolverMiembro(arg, ctx.consts, ctx.usadas)
      if (r) { if (!recoger(r, texto, ctx, entradas, true)) return false; continue }
      if (soloEstatico) return false
      if (arg.type === 'ConditionalExpression' || (arg.type === 'LogicalExpression' && arg.operator === '&&')) {
        const test = arg.type === 'ConditionalExpression' ? arg.test : arg.left
        const ramas = arg.type === 'ConditionalExpression' ? [arg.consequent, arg.alternate] : [arg.right, null]
        const lista = []
        for (const rama of ramas) {
          if (!rama || ausente(rama)) { lista.push([]); continue }
          const o = quitarTs(rama)
          if (o.type !== 'ObjectExpression') return false
          const sub = []
          if (!recoger(o, texto, ctx, sub, true)) return false
          if (sub.some((e) => e.tipo !== 'est')) return false
          lista.push(sub)
        }
        const t = texto.slice(test.start, test.end)
        const props = new Set([...lista[0], ...lista[1]].map((e) => e.prop))
        for (const prop of props) {
          const on = lista[0].find((e) => e.prop === prop)
          const off = lista[1].find((e) => e.prop === prop)
          entradas.push({ prop, tipo: 'cond', test: t, on: on ? on.v : null, off: off ? off.v : null })
        }
        continue
      }
      // `...style` / `...props.style` al FINAL: lo que pasa quien llama. Las clases
      // no pueden ganarle (el estilo en linea gana siempre), igual que antes ganaba
      // al final del objeto. Se conserva como `style={paso}`.
      if (p === obj.properties[obj.properties.length - 1] && !ctx.paso && obj === ctx.raiz) { ctx.paso = texto.slice(arg.start, arg.end); continue }
      return false
    }
    if (p.type !== 'ObjectProperty') return false
    const prop = nombreClave(p)
    if (!prop) return false
    const valor = quitarTs(p.value)
    const est = estatico(valor)
    if (prop.startsWith('--')) {
      if (est) entradas.push({ prop, tipo: 'est', v: est.v })
      else if (soloEstatico) return false
      else entradas.push({ prop, tipo: 'var', texto: texto.slice(p.start, p.end) })
      continue
    }
    if (est) { entradas.push({ prop, tipo: 'est', v: est.v }); continue }
    if (soloEstatico) return false
    if (valor.type === 'ConditionalExpression') {
      const a = estatico(valor.consequent), b = estatico(valor.alternate)
      const aa = ausente(valor.consequent), bb = ausente(valor.alternate)
      const t = texto.slice(valor.test.start, valor.test.end)
      if ((a || aa) && (b || bb)) {
        if (aa && bb) continue
        entradas.push({ prop, tipo: 'cond', test: t, on: a ? a.v : null, off: b ? b.v : null }); continue
      }
      if (aa && !(b || bb)) { entradas.push({ prop, tipo: 'condDyn', test: `!(${t})`, expr: texto.slice(valor.start, valor.end), nodo: valor }); continue }
      if (bb && !(a || aa)) { entradas.push({ prop, tipo: 'condDyn', test: t, expr: texto.slice(valor.start, valor.end), nodo: valor }); continue }
    }
    entradas.push({ prop, tipo: 'dyn', expr: texto.slice(p.value.start, p.value.end), nodo: valor })
  }
  return true
}

/** Duplicados y orden abreviada/larga. null si no se puede reproducir. */
function normalizar(entradas) {
  const res = []
  for (const e of entradas) {
    const i = res.findIndex((x) => x.prop === e.prop)
    if (i >= 0) {
      const x = res[i]
      if (x.tipo === 'est' && e.tipo === 'est') { res.splice(i, 1); res.push(e); continue }
      if (x.tipo === 'est' && e.tipo === 'cond') { res.push(e); continue }
      if (x.tipo === 'est' && e.tipo === 'dyn') { res.splice(i, 1); res.push(e); continue }
      return null
    }
    res.push(e)
  }
  const rango = (e) => (e.tipo === 'cond' || e.tipo === 'condDyn' ? 1 : 0)
  for (let i = 0; i < res.length; i++) {
    for (let j = i + 1; j < res.length; j++) {
      if (!solapan(res[i].prop, res[j].prop)) continue
      if (rango(res[i]) > rango(res[j])) return null
      if (rango(res[i]) === 1 && rango(res[j]) === 1 && res[i].test !== res[j].test) return null
    }
  }
  return res
}

// ── Estado de CSS por fichero ────────────────────────────────────────────────
const INI = '/* >>> estilos-en-linea (generado por scripts/codemods/estilos-en-linea.mjs; las modificadoras `-m` van despues de las base para ganar en la cascada como ganaba el estilo en linea) */'
const FIN = '/* <<< estilos-en-linea */'
class CssDelFichero {
  constructor(rutaTsx, texto) {
    this.dir = path.dirname(rutaTsx)
    this.base = path.basename(rutaTsx).replace(/\.(tsx|jsx)$/, '')
    const propio = path.join(this.dir, `${this.base}.css`)
    const importaPropio = new RegExp(`import\\s+['"]\\./${this.base}\\.css['"]`).test(texto)
    this.ruta = fs.existsSync(propio) && importaPropio ? propio : path.join(this.dir, `${this.base}.estilos.css`)
    this.importar = path.basename(this.ruta)
    this.yaImportado = new RegExp(`import\\s+['"]\\./${this.importar.replace(/\./g, '\\.')}['"]`).test(texto)
    const nombre = this.base === 'index' ? `${path.basename(this.dir)}-index` : this.base
    this.prefijo = nombre.replace(/([a-z0-9])([A-Z])/g, '$1-$2').replace(/[^A-Za-z0-9]+/g, '-').toLowerCase()
    this.base_ = new Map() // texto de decls -> clase
    this.mods = new Map()
    this.cargarPrevio()
  }
  cargarPrevio() {
    this.previo = fs.existsSync(this.ruta) ? fs.readFileSync(this.ruta, 'utf8') : ''
    const a = this.previo.indexOf(INI), b = this.previo.indexOf(FIN)
    this.fuera = a < 0 ? this.previo.replace(/\s*$/, '') : (this.previo.slice(0, a) + this.previo.slice(b + FIN.length)).replace(/\s*$/, '')
    if (a >= 0) {
      const bloque = this.previo.slice(a + INI.length, b)
      postcss.parse(bloque).walkRules((r) => {
        const cls = r.selector.slice(1)
        const clave = r.nodes.map((d) => `${d.prop}:${d.value}`).join(';')
        ;(/-m\d+$/.test(cls) ? this.mods : this.base_).set(clave, cls)
      })
    }
  }
  clase(decls, esMod) {
    const mapa = esMod ? this.mods : this.base_
    const clave = decls.map(([p, v]) => `${p}:${v}`).join(';')
    let c = mapa.get(clave)
    if (!c) {
      const n = Math.max(0, ...[...this.base_.values(), ...this.mods.values()].filter((x) => x.endsWith(esMod ? '' : '')).map((x) => (x.startsWith(`${this.prefijo}-`) && /-[em]\d+$/.test(x) ? +x.match(/(\d+)$/)[1] : 0))) + 1
      c = `${this.prefijo}-${esMod ? 'm' : 'e'}${n}`
      mapa.set(clave, c)
      this.nuevo = true
    }
    return c
  }
  bloque() {
    const reglas = (mapa) => [...mapa.entries()].sort((x, y) => +x[1].match(/(\d+)$/)[1] - +y[1].match(/(\d+)$/)[1])
      .map(([clave, cls]) => `.${cls} {\n${clave.split(';').map((d) => { const i = d.indexOf(':'); return `  ${d.slice(0, i)}: ${d.slice(i + 1)};` }).join('\n')}\n}`).join('\n')
    return `${INI}\n${reglas(this.base_)}\n${reglas(this.mods)}\n${FIN}\n`
  }
  escribir() {
    if (!this.nuevo) return
    const out = (this.fuera ? this.fuera + '\n\n' : '') + this.bloque()
    if (!DRY) fs.writeFileSync(this.ruta, out)
  }
}

// ── Componentes que reciben className ────────────────────────────────────────
const COMPONENTES_CLASSNAME = new Set(['Button', 'Card', 'Tabs', 'Toolbar', 'PortalCard', 'ClientSelect', 'RefreshCw', 'ChevronRight', 'Link', 'NavLink', 'Drawer', 'DateInput', 'IconButton', 'MarkdownText', 'Input', 'Select', 'PortalInput'])
// Solo los componentes cuyo codigo se ha comprobado a mano (reciben className en la raiz).

// ── Reescritura de un fichero ────────────────────────────────────────────────
const stats = { attrs: 0, convertidos: 0, residual: {}, props: { a: 0, b: 0, c: 0, d: 0, otros: 0 }, ficheros: new Set(), vars: 0, soloVars: 0, listaResiduales: [] }
const residual = (motivo, fichero, linea, trozo) => { stats.residual[motivo] = (stats.residual[motivo] || 0) + 1; stats.listaResiduales.push(`${motivo}\t${path.relative(SRC, fichero)}:${linea}\t${trozo.replace(/\s+/g, ' ').slice(0, 140)}`) }

function procesar(fichero) {
  const texto = fs.readFileSync(fichero, 'utf8')
  if (!texto.includes('style={{') && !texto.includes('style={ {')) return
  const ast = parse(texto, { sourceType: 'module', plugins: ['jsx', 'typescript'] })
  const consts = constantesDelModulo(ast)
  const css = new CssDelFichero(fichero, texto)
  const ediciones = []
  const usadasGlobal = new Set()
  let usaVars = false, usaPx = false, usaCss = false

  visitar(ast.program, (n) => {
    if (n.type !== 'JSXOpeningElement') return
    const st = n.attributes.find((a) => a.type === 'JSXAttribute' && a.name.name === 'style')
    if (!st || !st.value || st.value.type !== 'JSXExpressionContainer') return
    let expr = quitarTs(st.value.expression)
    // `style={S.card}` / `style={fs}` con una constante estatica del fichero: se trata
    // como `{...S.card}` (la clase la sustituye igual).
    if (expr.type === 'Identifier' || expr.type === 'MemberExpression') {
      const r = resolverMiembro(expr, consts, new Set())
      if (!r) return
      if (r.properties.every((q) => q.type === 'ObjectProperty' && (nombreClave(q) || '').startsWith('--'))) return
      expr = { type: 'ObjectExpression', start: expr.start, end: expr.end, properties: [{ type: 'SpreadElement', argument: expr, start: expr.start, end: expr.end }] }
    }
    if (expr.type !== 'ObjectExpression') return
    stats.attrs++
    if (expr.properties.some((q) => q.type === 'ObjectProperty') && expr.properties.every((q) => q.type === 'SpreadElement' || (q.type === 'ObjectProperty' && (nombreClave(q) || '').startsWith('--')))) { if (!MEDIR) stats.soloVars++; return }
    const linea = st.loc.start.line
    const ctx = { consts, usadas: new Set(), raiz: expr, paso: null }
    const entradas = []
    const ok = recoger(expr, texto, ctx, entradas, false)
    // Clasificacion (medir): por propiedad.
    if (ok) for (const e of entradas) {
      if (e.tipo === 'est') stats.props[esLiteralDeTema(e.prop, e.v) ? 'c' : 'a']++
      else if (e.tipo === 'cond') stats.props.b++
      else stats.props.d++
    } else stats.props.otros += expr.properties.length
    if (MEDIR) return
    const nombreTag = n.name.type === 'JSXIdentifier' ? n.name.name : null
    if (!nombreTag) return residual('componente-miembro', fichero, linea, texto.slice(st.start, st.end))
    if (/^[A-Z]/.test(nombreTag) && !COMPONENTES_CLASSNAME.has(nombreTag)) return residual(`componente-sin-className:${nombreTag}`, fichero, linea, texto.slice(st.start, st.end))
    if (n.attributes.some((a) => a.type === 'JSXSpreadAttribute')) return residual('spread-en-el-elemento', fichero, linea, texto.slice(st.start, st.end))
    if (!ok) return residual('objeto-no-resoluble', fichero, linea, texto.slice(st.start, st.end))
    const lista = normalizar(entradas)
    if (!lista) return residual('orden-abreviada-larga/duplicado', fichero, linea, texto.slice(st.start, st.end))
    // Si ya solo hay propiedades personalizadas dinamicas, esta bien como esta.
    if (lista.every((e) => e.tipo === 'var')) { stats.soloVars++; return }
    if (!lista.length && ctx.paso) { stats.soloVars++; return }

    // Declaraciones.
    const pref = css.prefijo
    const base = [], vars = []
    const grupos = new Map() // test -> {on: [], off: []}
    const varDe = (prop) => `--${pref}-${kebab(prop).replace(/^-+/, '')}`
    let pxUsado = false
    for (const e of lista) {
      if (e.tipo === 'est') base.push([kebab(e.prop), valorCss(e.prop, e.v)])
      else if (e.tipo === 'dyn') {
        base.push([kebab(e.prop), `var(${varDe(e.prop)})`])
        vars.push([varDe(e.prop), valorVar(e.prop, e.expr, e.nodo, texto)]); if (esLongitud(e.prop) && vars.at(-1)[1].startsWith('px(')) pxUsado = true
      } else if (e.tipo === 'var') vars.push(e)
      else {
        if (!grupos.has(e.test)) grupos.set(e.test, { on: [], off: [] })
        const g = grupos.get(e.test)
        if (e.tipo === 'cond') {
          if (e.on != null) g.on.push([kebab(e.prop), valorCss(e.prop, e.on)])
          if (e.off != null) g.off.push([kebab(e.prop), valorCss(e.prop, e.off)])
        } else {
          g.on.push([kebab(e.prop), `var(${varDe(e.prop)})`])
          vars.push([varDe(e.prop), valorVar(e.prop, e.expr, e.nodo, texto)]); if (vars.at(-1)[1].startsWith('px(')) pxUsado = true
        }
      }
    }
    const clases = []
    if (base.length) clases.push(css.clase(base, false))
    const condicionales = []
    for (const [test, g] of grupos) {
      const on = g.on.length ? css.clase(g.on, true) : ''
      const off = g.off.length ? css.clase(g.off, true) : ''
      condicionales.push(`${test} ? '${on}' : '${off}'`.replace(/^(.*) \? '' : ''$/, '$1 ? \'\' : \'\''))
    }
    // Clase existente.
    const cn = n.attributes.find((a) => a.type === 'JSXAttribute' && a.name.name === 'className')
    let cnTexto
    const fijas = clases.join(' ')
    const plantilla = (previo) => {
      // previo: texto ya dentro de una plantilla (sin comillas) o ''.
      const partes = [previo, fijas, ...condicionales.map((c) => `\${${c}}`)].filter(Boolean)
      return partes.join(' ')
    }
    if (!cn) {
      cnTexto = condicionales.length ? `className={\`${plantilla('')}\`}` : (fijas ? `className="${fijas}"` : '')
    } else if (!cn.value) return residual('className-sin-valor', fichero, linea, '')
    else if (cn.value.type === 'StringLiteral') {
      const prev = cn.value.value.trim()
      cnTexto = condicionales.length ? `className={\`${plantilla(prev)}\`}` : `className="${[prev, fijas].filter(Boolean).join(' ')}"`
    } else if (cn.value.type === 'JSXExpressionContainer') {
      const e2 = cn.value.expression
      if (e2.type === 'TemplateLiteral') {
        const interior = texto.slice(e2.start + 1, e2.end - 1)
        cnTexto = `className={\`${interior.replace(/\s+$/, '')} ${[fijas, ...condicionales.map((c) => `\${${c}}`)].filter(Boolean).join(' ')}\`}`
      } else {
        const orig = texto.slice(e2.start, e2.end)
        cnTexto = `className={\`\${${orig} || ''} ${[fijas, ...condicionales.map((c) => `\${${c}}`)].filter(Boolean).join(' ')}\`}`
      }
    } else return residual('className-raro', fichero, linea, '')
    let estiloTexto = ''
    if (ctx.paso && !vars.length) estiloTexto = `style={${ctx.paso}}`
    else if (vars.length) {
      const cuerpo = (ctx.paso ? [`...${ctx.paso}`] : []).concat(vars.map((v) => (Array.isArray(v) ? `'${v[0]}': ${v[1]}` : v.texto))).join(', ')
      estiloTexto = `style={{ ${cuerpo} } as CSSProperties}`
      usaVars = true
    }
    if (pxUsado) usaPx = true
    for (const u of ctx.usadas) usadasGlobal.add(u)
    // Ediciones: className y style.
    const quitar = (a) => { let s = a.start; while (s > 0 && /\s/.test(texto[s - 1])) s--; return { start: s, end: a.end, nuevo: '' } }
    if (cn) {
      ediciones.push({ start: cn.start, end: cn.end, nuevo: cnTexto })
      ediciones.push(estiloTexto ? { start: st.start, end: st.end, nuevo: estiloTexto } : quitar(st))
    } else {
      ediciones.push({ start: st.start, end: st.end, nuevo: [cnTexto, estiloTexto].filter(Boolean).join(' ') || '' })
      if (!cnTexto && !estiloTexto) ediciones[ediciones.length - 1] = quitar(st)
    }
    if (clases.length || condicionales.length) usaCss = true
    stats.convertidos++
    if (vars.length) stats.vars++
  })
  if (MEDIR || !ediciones.length) return

  // Sin solapes: se descartan las ediciones que pisan a otra (otra pasada las coge).
  ediciones.sort((a, b) => a.start - b.start)
  let nuevoTexto = texto
  let ultimo = -1
  const buenas = []
  for (const e of ediciones) { if (e.start < ultimo) { stats.convertidos--; continue } buenas.push(e); ultimo = e.end }
  for (const e of buenas.reverse()) nuevoTexto = nuevoTexto.slice(0, e.start) + e.nuevo + nuevoTexto.slice(e.end)

  // Constantes de estilo que ya no se usan (todas las `const` de ese nombre).
  for (const nombre of usadasGlobal) {
    const decls = consts.lista.filter((d) => d.nombre === nombre)
    let resto = nuevoTexto
    for (const d of decls) resto = resto.replace(texto.slice(d.sentencia.start, d.sentencia.end), '')
    if (!new RegExp('\\b' + nombre + '\\b').test(resto)) nuevoTexto = resto.replace(/\n[ \t]*\n[ \t]*\n/g, '\n\n')
  }
  // Importaciones.
  const ultimaImport = [...nuevoTexto.matchAll(/^import[\s\S]*?;?\s*(?:from\s+)?['"][^'"]+['"]\s*;?\s*$/gm)].pop()
  const insertarImport = (linea) => {
    const re = [...nuevoTexto.matchAll(/^(?:import\s[^;]*?from\s+)?import\s*['"][^'"]+['"]|^import\s[\s\S]*?\sfrom\s+['"][^'"]+['"]/gm)]
    const fin = re.length ? re.at(-1).index + re.at(-1)[0].length : 0
    const finLinea = nuevoTexto.indexOf('\n', fin)
    nuevoTexto = nuevoTexto.slice(0, finLinea + 1) + linea + '\n' + nuevoTexto.slice(finLinea + 1)
  }
  void ultimaImport
  if (usaCss && !css.yaImportado) insertarImport(`import './${css.importar}'`)
  if (usaPx) {
    const rel = path.relative(path.dirname(fichero), path.join(SRC, 'utils', 'estilos')).replace(/\\/g, '/')
    if (!/\bpx\b[^\n]*from\s+['"][^'"]*utils\/estilos['"]/.test(nuevoTexto)) insertarImport(`import { px } from '${rel.startsWith('.') ? rel : './' + rel}'`)
  }
  if (usaVars) nuevoTexto = asegurarCssProperties(nuevoTexto)
  else nuevoTexto = limpiarCssProperties(nuevoTexto)
  if (!DRY) fs.writeFileSync(fichero, nuevoTexto)
  css.escribir()
  stats.ficheros.add(path.relative(SRC, fichero))
}

function valorVar(prop, exprTexto, nodo, texto) {
  if (!esLongitud(prop)) return exprTexto
  const v = quitarTs(nodo)
  if (v.type === 'TemplateLiteral' && /(px|%|rem|em|vh|vw|vmin|vmax|\)|\s[a-z-]+)$/.test(v.quasis.at(-1).value.cooked) && v.expressions.length) return exprTexto
  if (v.type === 'StringLiteral') return exprTexto
  if (v.type === 'ConditionalExpression') {
    const todoCadena = [v.consequent, v.alternate].every((r) => { r = quitarTs(r); return r.type === 'StringLiteral' || r.type === 'TemplateLiteral' || ausente(r) })
    if (todoCadena) return exprTexto
  }
  return `px(${exprTexto})`
}

function asegurarCssProperties(t) {
  const lineasReact = t.match(/^import\s[^\n;]*from\s+['"]react['"];?/m)
  if (/\bimport\s[^;]*\bCSSProperties\b[^;]*from\s+['"]react['"]/.test(t)) return t
  if (lineasReact) {
    const l = lineasReact[0]
    let n
    if (/^import\s+type\s*\{/.test(l)) n = l.replace('{', '{ CSSProperties,')
    else if (/\{[^}]*\}/.test(l)) n = l.replace(/\{/, '{ type CSSProperties,').replace('{ type CSSProperties,  ', '{ type CSSProperties, ')
    else if (/import\s+\*\s+as/.test(l)) n = null
    else if (/^import\s+type/.test(l)) n = null
    else n = l.replace(/^import\s+(\w+)\s+from/, 'import $1, { type CSSProperties } from')
    if (n) return t.replace(l, n)
  }
  const re = [...t.matchAll(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?|^import\s+['"][^'"]+['"];?/gm)]
  const fin = re.length ? re.at(-1).index + re.at(-1)[0].length : 0
  const f = t.indexOf('\n', fin)
  return t.slice(0, f + 1) + "import type { CSSProperties } from 'react'\n" + t.slice(f + 1)
}
function limpiarCssProperties(t) {
  const usos = (t.match(/\bCSSProperties\b/g) || []).length
  if (usos !== 1) return t
  return t.replace(/\{\s*type CSSProperties,\s*/, '{ ').replace(/,\s*type CSSProperties\s*\}/, ' }').replace(/,\s*\{\s*type CSSProperties\s*\}/, '').replace(/^import type \{ CSSProperties \} from 'react'\n/m, '')
}

for (const f of recorrer(SRC)) procesar(f)
if (process.argv.includes("--comps")) console.log([...COMPONENTES_CLASSNAME].join(" "))

const resumen = {
  atributos_style_objeto: stats.attrs,
  propiedades: stats.props,
  convertidos: stats.convertidos,
  ya_solo_vars: stats.soloVars,
  con_variables_css: stats.vars,
  ficheros_tocados: stats.ficheros.size,
  residuales: stats.residual,
}
console.log(JSON.stringify(resumen, null, 2))
if (RESIDUALES) console.log(stats.listaResiduales.join('\n'))
