// Comprobación de CSS de la migración al kit (16-11-2026, fase 1). No hay
// stylelint en el proyecto: este analizador mínimo lo usan el test
// src/__tests__/kitCssSinRestos.test.ts y scripts/kit_pendientes.mjs.
//
// Fuera de src/components/ui y de src/index.css (donde viven el kit y los
// tokens), una hoja de estilos no puede tener:
//   mayusculas       text-transform: uppercase | capitalize   → la tipografía del kit (ds-eyebrow si de verdad es un rótulo)
//   monoespaciada    font-family/font con letra monoespaciada → texto normal; cifras con font-variant-numeric: tabular-nums
//   colorLiteral     #hex, rgb()/rgba()/hsl()/hsla() con números → var(--token) de index.css
//   altoFijoControl  height: NNpx en un botón/campo/select       → el alto de los controles del kit (38/32 px) o min-height
//   minAltoCampo     min-height: NNpx en un campo/select/buscador → --alto-control / --alto-control-sm (23-11-2026)
//   selectorDsInput  un selector con `.ds-input`                  → la clase propia del campo (inputClassName) o la API
//                    del kit: el Input/Textarea/Select del kit NO llevan ds-input, y una regla `.ds-input.x` o
//                    `.algo .ds-input` deja de aplicarse sin avisar (23-11-2026: 22 reglas muertas así)
import fs from 'node:fs'
import path from 'node:path'

export const COMPROBACIONES_CSS = ['mayusculas', 'monoespaciada', 'colorLiteral', 'altoFijoControl', 'minAltoCampo', 'selectorDsInput']

const RE_MAYUSCULAS = /\b(uppercase|capitalize)\b/i
const RE_MONO = /mono|courier|consolas|menlo/i
const RE_HEX = /#[0-9a-f]{3,8}\b/i
const RE_FUNCION_COLOR = /\b(rgba?|hsla?)\(\s*[\d.]/i
const RE_SELECTOR_CONTROL = /\b(button|input|select|textarea)\b|btn|boton|control|campo|toggle|switch/i
const RE_PX = /^-?\d+(\.\d+)?px$/
// Campos de texto/desplegables (no botones, casillas, interruptores ni áreas de texto).
const RE_SELECTOR_CAMPO = /\b(input|select)\b|campo|buscar|buscador|search|filtro|filter/i
const RE_NO_CAMPO = /textarea|check|radio|color|range|switch|subir|file|nql|multi|area\b/i

/** Recorre las declaraciones de una hoja: (selector, propiedad, valor, línea). */
export function declaraciones(texto) {
  const limpio = texto.replace(/\/\*[\s\S]*?\*\//g, (c) => c.replace(/[^\n]/g, ' '))
  const pila = []
  const salida = []
  let buffer = ''
  let inicio = 0
  let parentesis = 0
  let comilla = null
  let linea = 1
  const cerrarDeclaracion = () => {
    const d = buffer.trim()
    buffer = ''
    if (!pila.length || !d) return
    const i = d.indexOf(':')
    if (i <= 0) return
    salida.push({ selector: pila[pila.length - 1], propiedad: d.slice(0, i).trim().toLowerCase(), valor: d.slice(i + 1).trim(), linea: inicio })
  }
  for (const c of limpio) {
    if (c === '\n') linea++
    if (!buffer.trim() && !/\s/.test(c)) inicio = linea
    if (comilla) { buffer += c; if (c === comilla) comilla = null; continue }
    if (c === '"' || c === "'") { comilla = c; buffer += c; continue }
    if (c === '(') parentesis++
    if (c === ')') parentesis = Math.max(0, parentesis - 1)
    if (parentesis) { buffer += c; continue }
    if (c === '{') { pila.push(buffer.trim()); buffer = ''; continue }
    if (c === '}') { cerrarDeclaracion(); pila.pop(); continue }
    if (c === ';') { cerrarDeclaracion(); continue }
    buffer += c
  }
  return salida
}

/** Incumplimientos de una hoja: { comprobacion: [{ linea, texto }] }. */
export function analizarCss(texto) {
  const r = Object.fromEntries(COMPROBACIONES_CSS.map((c) => [c, []]))
  for (const d of declaraciones(texto)) {
    const texto = `${d.propiedad}: ${d.valor}`
    if (d.propiedad === 'text-transform' && RE_MAYUSCULAS.test(d.valor)) r.mayusculas.push({ linea: d.linea, texto })
    if ((d.propiedad === 'font-family' || d.propiedad === 'font') && RE_MONO.test(d.valor)) r.monoespaciada.push({ linea: d.linea, texto })
    if (RE_HEX.test(d.valor) || RE_FUNCION_COLOR.test(d.valor)) r.colorLiteral.push({ linea: d.linea, texto })
    if (d.propiedad === 'height' && RE_PX.test(d.valor) && RE_SELECTOR_CONTROL.test(d.selector)) r.altoFijoControl.push({ linea: d.linea, texto: `${d.selector} { ${texto} }` })
    if (d.propiedad === 'min-height' && RE_PX.test(d.valor) && RE_SELECTOR_CAMPO.test(d.selector) && !RE_NO_CAMPO.test(d.selector)) r.minAltoCampo.push({ linea: d.linea, texto: `${d.selector} { ${texto} }` })
    if (/\.ds-input(?![\w-])/.test(d.selector)) r.selectorDsInput.push({ linea: d.linea, texto: `${d.selector} { ${texto} }` })
  }
  return r
}

/** Las hojas sujetas a la comprobación (rutas relativas a `raiz`, con /). */
export function hojasFueraDelKit(raiz) {
  const src = path.join(raiz, 'src')
  const salida = []
  const recorrer = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name)
      if (e.isDirectory()) { recorrer(p); continue }
      if (!e.name.endsWith('.css')) continue
      const rel = path.relative(raiz, p).split(path.sep).join('/')
      if (rel === 'src/index.css' || rel.startsWith('src/components/ui/')) continue
      salida.push(rel)
    }
  }
  recorrer(src)
  return salida.sort()
}

/** Recuento por comprobación y fichero: { comprobacion: { fichero: n } }. */
export function recuentoCss(raiz) {
  const r = Object.fromEntries(COMPROBACIONES_CSS.map((c) => [c, {}]))
  for (const rel of hojasFueraDelKit(raiz)) {
    const a = analizarCss(fs.readFileSync(path.join(raiz, rel), 'utf8'))
    for (const c of COMPROBACIONES_CSS) if (a[c].length) r[c][rel] = a[c].length
  }
  return r
}
