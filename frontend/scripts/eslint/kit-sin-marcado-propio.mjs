// Reglas de ESLint de la migración al kit (16-11-2026, fase 1): fuera de
// src/components/ui no se pinta marcado propio para lo que el kit ya resuelve.
//
//   contec/sin-boton-nativo     <button>                       → Button / IconButton / Pulsable / Chip / Segmentado
//   contec/sin-tabla-propia     <table>                        → Tabla / TablaSimple
//   contec/sin-select-nativo    <select>                       → Select (suelto en barras y celdas)
//   contec/sin-casilla-suelta   <input type="checkbox|radio">  → Checkbox / Radio / Switch / GrupoDeOpciones
//   contec/sin-input-nativo    <input> de texto / <textarea>  → Input / Textarea / SearchInput
//   contec/sin-fieldset-propio  <fieldset> sin ds-grupo-opciones → GrupoDeOpciones
//   contec/sin-boton-de-icono-propio  <button>/<Pulsable>/<Button> con solo un icono de lucide
//                                     → IconButton (variante="caja" en tarjetas y filas; 23-11-2026)
//
// Excepciones temporales: la opción `pendientes` ({ 'src/x.tsx': n }) admite
// en ese fichero hasta n incumplimientos (los que tenía al crear la lista). Si
// el fichero tiene más, se marcan todos; un fichero que no está en la lista no
// admite ninguno. La lista vive en kit-pendientes.json y la regenera/encoge
// scripts/kit_pendientes.mjs. `raiz` es la carpeta respecto a la que van las
// rutas de la lista (la del frontend; por defecto, el cwd de ESLint).
import path from 'node:path'

const nombre = (node) => (node.name && node.name.type === 'JSXIdentifier' ? node.name.name : null)

function atributo(node, clave) {
  return node.attributes.find((a) => a.type === 'JSXAttribute' && a.name && a.name.name === clave)
}

/** Los textos literales que puede tomar el valor de un atributo. */
function literales(valor) {
  if (!valor) return []
  if (valor.type === 'Literal') return [String(valor.value)]
  if (valor.type === 'JSXExpressionContainer') return literalesDeExpresion(valor.expression)
  return []
}
function literalesDeExpresion(e) {
  if (!e) return []
  if (e.type === 'Literal') return [String(e.value)]
  if (e.type === 'TemplateLiteral') return e.quasis.map((q) => q.value.cooked ?? '')
  if (e.type === 'ConditionalExpression') return [...literalesDeExpresion(e.consequent), ...literalesDeExpresion(e.alternate)]
  if (e.type === 'LogicalExpression') return [...literalesDeExpresion(e.left), ...literalesDeExpresion(e.right)]
  return []
}

export const ESQUEMA = [{
  type: 'object',
  properties: {
    pendientes: { type: 'object', additionalProperties: { type: 'integer', minimum: 0 } },
    raiz: { type: 'string' },
  },
  additionalProperties: false,
}]

function rutaRelativa(context, raiz) {
  const base = raiz || context.cwd || process.cwd()
  return path.relative(base, context.filename).split(path.sep).join('/')
}

function crearRegla({ mensaje, detectar }) {
  return {
    meta: {
      type: 'problem',
      schema: ESQUEMA,
      messages: {
        prohibido: mensaje,
        excedido: `${mensaje} Este fichero está en kit-pendientes.json con {{permitidos}} pendientes y ahora tiene {{total}}: la lista solo puede encoger.`,
      },
    },
    create(context) {
      const opciones = context.options[0] || {}
      const permitidos = (opciones.pendientes || {})[rutaRelativa(context, opciones.raiz)] || 0
      const hallados = []
      return {
        JSXOpeningElement(node) { if (detectar(node, context)) hallados.push(node) },
        'Program:exit'() {
          if (hallados.length <= permitidos) return
          for (const node of hallados) {
            context.report({ node, messageId: permitidos ? 'excedido' : 'prohibido', data: { permitidos: String(permitidos), total: String(hallados.length) } })
          }
        },
      }
    },
  }
}

// 24-11-2026: también `month` (el `Input` del kit lo admite: `<Input label=… type="month" />`).
const TIPOS_DE_TEXTO = new Set(['', 'text', 'search', 'email', 'number', 'password', 'url', 'tel', 'month'])

// ── Botón de solo icono (23-11-2026) ─────────────────────────────────────────
// Los nombres locales que el fichero importa de lucide-react (por programa).
const iconosPorPrograma = new WeakMap()
function iconosImportados(context) {
  const ast = context.sourceCode.ast
  if (!iconosPorPrograma.has(ast)) {
    const nombres = new Set()
    for (const s of ast.body) {
      if (s.type !== 'ImportDeclaration' || s.source.value !== 'lucide-react') continue
      for (const e of s.specifiers) if (e.type === 'ImportSpecifier' || e.type === 'ImportDefaultSpecifier') nombres.add(e.local.name)
    }
    iconosPorPrograma.set(ast, nombres)
  }
  return iconosPorPrograma.get(ast)
}
/** ¿Es la expresión solo un icono de lucide (o un ternario/&& entre iconos)? */
function esIcono(e, iconos) {
  if (!e) return false
  if (e.type === 'JSXElement') {
    const n = e.openingElement.name
    return n.type === 'JSXIdentifier' && iconos.has(n.name)
  }
  if (e.type === 'ConditionalExpression') return esIcono(e.consequent, iconos) && esIcono(e.alternate, iconos)
  if (e.type === 'LogicalExpression') return esIcono(e.right, iconos)
  return false
}
/** <button>, <Pulsable> o <Button> cuyo único hijo es un icono de lucide, o
 *  <Button icon={…}> sin texto. */
export function esBotonDeSoloIcono(n, context) {
  const nom = nombre(n)
  if (nom !== 'button' && nom !== 'Pulsable' && nom !== 'Button') return false
  const hijos = n.selfClosing ? [] : n.parent.children.filter((h) => !(h.type === 'JSXText' && !h.value.trim())
    && !(h.type === 'JSXExpressionContainer' && h.expression.type === 'JSXEmptyExpression'))
  if (nom === 'Button' && hijos.length === 0 && atributo(n, 'icon')) return true
  const iconos = iconosImportados(context)
  if (!iconos.size || hijos.length !== 1) return false
  const h = hijos[0]
  return esIcono(h.type === 'JSXExpressionContainer' ? h.expression : h, iconos)
}

export const reglasDelKit = {
  'sin-boton-nativo': crearRegla({
    mensaje: '<button> propio: usa Button (variant primary/secondary/ghost/danger/link), IconButton, Chip, Segmentado o Pulsable del kit (components/ui).',
    detectar: (n) => nombre(n) === 'button',
  }),
  'sin-boton-de-icono-propio': crearRegla({
    mensaje: 'Botón de solo icono hecho a mano (<button>, <Pulsable> o <Button> con un icono de lucide como único hijo): usa IconButton del kit; en tarjetas y filas, <IconButton variante="caja" tono="neutro|peligro|acento" ariaLabel="…"> dentro de .ui-acciones (cuadrado de alto fijo, no se estira).',
    detectar: esBotonDeSoloIcono,
  }),
  'sin-tabla-propia': crearRegla({
    mensaje: '<table> propia: usa Tabla (columnas declarativas) o TablaSimple (marcado libre con el estilo contecflow-table) del kit.',
    detectar: (n) => nombre(n) === 'table',
  }),
  'sin-select-nativo': crearRegla({
    mensaje: '<select> nativo: usa Select del kit (con `suelto` en barras de filtros y celdas; las <option> van como `options` o hijos).',
    detectar: (n) => nombre(n) === 'select',
  }),
  'sin-casilla-suelta': crearRegla({
    mensaje: '<input type="checkbox|radio"> suelto: usa Checkbox, Radio, Switch o GrupoDeOpciones del kit.',
    detectar: (n) => nombre(n) === 'input' && literales(atributo(n, 'type')?.value).some((v) => /^(checkbox|radio)$/.test(v.trim())),
  }),
  'sin-input-nativo': crearRegla({
    mensaje: '<input>/<textarea> nativo de texto: usa Input/Textarea del kit (components/ui) o SearchInput para buscadores; no se pintan campos a mano.',
    detectar: (n) => {
      const nom = nombre(n)
      if (nom === 'textarea') return true
      if (nom !== 'input') return false
      const attr = atributo(n, 'type')
      if (!attr) return true
      const tipos = literales(attr.value).map((v) => v.trim().toLowerCase())
      if (tipos.length === 0) return true // type dinámico: se asume texto
      return tipos.some((v) => TIPOS_DE_TEXTO.has(v))
    },
  }),
  'sin-fieldset-propio': crearRegla({
    mensaje: '<fieldset> sin la clase ds-grupo-opciones: usa GrupoDeOpciones del kit (o la clase ds-grupo-opciones con su <legend>).',
    detectar: (n, context) => {
      if (nombre(n) !== 'fieldset') return false
      const clase = atributo(n, 'className')
      return !clase || !clase.value || !context.sourceCode.getText(clase.value).includes('ds-grupo-opciones')
    },
  }),
}

/** Donde no se aplican: el propio kit y las pruebas. */
export const IGNORADOS_KIT = ['src/components/ui/**', 'src/**/__tests__/**', 'src/**/*.test.{js,jsx,ts,tsx}']

export const NOMBRES_DE_REGLAS = Object.keys(reglasDelKit).map((r) => `contec/${r}`)

export default reglasDelKit
