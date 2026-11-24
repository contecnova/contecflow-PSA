// Comprobación de campos de la migración al kit (24-11-2026). La usa scripts/kit_pendientes.mjs
// (sección `campos` de kit-pendientes.json, con cupo que solo puede bajar).
//
// Dos reglas, contadas por fichero:
//   campoConEtiquetaPropia   un <label> (o un <span>/<div>/<p> con clase de etiqueta que no sea la del kit)
//                            junto a un Select/Input/Textarea/CampoFecha/DateInput/SelectRico/Buscador/…
//                            del kit, o un <label> que lo envuelve. El campo con etiqueta se escribe SIEMPRE
//                            con la prop del componente del kit: `<Select label=… />`, `<Input label=… />`…
//                            (etiqueta `uiinde-estiloetiqueta`, alto `--alto-control`, ancho de desplegable
//                            estándar `--ancho-min-desplegable`). Nunca label + control sueltos con clases propias.
//   selectorDeContextoAMano  un Select/ProjectSelect/ClientSelect de contexto de la pantalla (proyecto, cliente,
//                            sprint, unidad…) fuera de <SelectorDeContexto>, que es el único patrón permitido
//                            (tarjeta + etiqueta del kit + desplegable de ancho estándar). Los selectores de
//                            formularios en un Modal/Drawer/FormField no cuentan.
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

export const COMPROBACIONES_CAMPOS = ['campoConEtiquetaPropia', 'selectorDeContextoAMano']

const K = ts.SyntaxKind
const CONTROLES = new Set([
  'Select', 'Input', 'Textarea', 'SelectRico', 'DateInput', 'CampoFecha', 'ClientSelect', 'UserSelect', 'ProjectSelect',
  'SprintSelect', 'EpicSelect', 'Buscador', 'SelectorDePeriodo', 'CampoRangoDeFechas',
])
const DE_CONTEXTO = new Set(['Select', 'ProjectSelect', 'ClientSelect'])
const RE_CLASE_ETIQUETA = /(^|[\s_-])(label|lbl|etiqueta|ls)([\s_-]|$)|__label|\{\s*(ls|LS|labelStyle)\s*\}/i
const RE_VALOR_DE_CONTEXTO = /^(selected)?(project|client|sprint|unit|unidad|proyecto|cliente)(id)?$/i
// 24-11-2026: también un diálogo propio (`role="dialog"`, p. ej. la ficha flotante de una reserva): es un formulario.
const CONTENEDORES_DE_FORMULARIO = new Set(['Modal', 'Drawer', 'FormField', 'SelectorDeContexto', 'form', 'dialog'])
const DEL_KIT_O_FUERA = /^src\/(components\/ui\/|__tests__\/)|\.test\.tsx$/

const nombre = (n) => (n.openingElement || n).tagName.getText()
const esElemento = (n) => n.kind === K.JsxElement || n.kind === K.JsxSelfClosingElement
const hijos = (n) => n.children.filter((c) => !(c.kind === K.JsxText && !c.text.trim()))
const atributos = (n) => (n.openingElement || n).attributes.properties
const atributo = (n, nom) => atributos(n).find((a) => a.name && a.name.getText() === nom)
const claseDe = (n) => {
  const a = atributo(n, 'className')
  return a && a.initializer ? a.initializer.getText() : ''
}

function archivos(dir, salida = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) { if (e.name !== 'node_modules') archivos(p, salida) } else if (/\.tsx$/.test(e.name)) salida.push(p)
  }
  return salida
}

/** Hijos del elemento que son controles del kit (a cualquier profundidad de un solo nivel de envoltorio). */
function contieneControl(n) {
  return hijos(n).some((c) => esElemento(c) && CONTROLES.has(nombre(c)))
}
function contieneCasilla(n) {
  const re = /<(Checkbox|Radio|Switch|GrupoDeOpciones)\b|type="(checkbox|radio|file)"/
  return re.test(n.getText())
}

export function recuentoCampos(raiz) {
  const r = Object.fromEntries(COMPROBACIONES_CAMPOS.map((c) => [c, {}]))
  for (const f of archivos(path.join(raiz, 'src'))) {
    const rel = path.relative(raiz, f).split(path.sep).join('/')
    if (DEL_KIT_O_FUERA.test(rel)) continue
    const texto = fs.readFileSync(f, 'utf8')
    const sf = ts.createSourceFile(f, texto, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    const suma = (regla) => { r[regla][rel] = (r[regla][rel] || 0) + 1 }
    const visitar = (n, ancestros) => {
      if (n.kind === K.JsxElement || n.kind === K.JsxFragment) {
        const k = hijos(n)
        for (let i = 0; i < k.length; i++) {
          const a = k[i]
          if (a.kind !== K.JsxElement) continue
          const ta = nombre(a)
          const clase = claseDe(a)
          if (/uiinde-estiloetiqueta/.test(clase)) continue
          if (ta === 'label') {
            if (contieneCasilla(a)) continue
            const b = k[i + 1]
            // Un <label> que envuelve su propio control nativo (input/select/textarea) no es la etiqueta del hermano.
            if (!contieneControl(a) && /<(input|select|textarea)\b/.test(a.getText())) continue
            if (contieneControl(a) || (b && esElemento(b) && CONTROLES.has(nombre(b)))) suma('campoConEtiquetaPropia')
          } else if ((ta === 'span' || ta === 'div' || ta === 'p') && RE_CLASE_ETIQUETA.test(clase)) {
            // Una etiqueta es solo texto: con un icono u otro componente dentro es una marca (chip), no una etiqueta.
            if (hijos(a).some((c) => esElemento(c))) continue
            const b = k[i + 1]
            if (b && esElemento(b) && CONTROLES.has(nombre(b))) suma('campoConEtiquetaPropia')
          }
        }
      }
      if (esElemento(n) && DE_CONTEXTO.has(nombre(n))) {
        const v = atributo(n, 'value')
        const expr = v && v.initializer && v.initializer.kind === K.JsxExpression ? v.initializer.expression : null
        const ident = expr && (expr.kind === K.Identifier ? expr.getText() : expr.kind === K.PropertyAccessExpression ? expr.name.getText() : '')
        if (ident && RE_VALOR_DE_CONTEXTO.test(ident) && !ancestros.some((x) => CONTENEDORES_DE_FORMULARIO.has(x))) suma('selectorDeContextoAMano')
      }
      const nom = esElemento(n) || n.kind === K.JsxElement ? nombre(n) : null
      const rol = esElemento(n) ? atributo(n, 'role')?.initializer?.getText() : null
      const sig = nom ? [...ancestros, nom, ...(rol === '"dialog"' ? ['dialog'] : [])] : ancestros
      ts.forEachChild(n, (c) => visitar(c, sig))
    }
    visitar(sf, [])
  }
  for (const c of COMPROBACIONES_CAMPOS) r[c] = Object.fromEntries(Object.entries(r[c]).sort(([a], [b]) => a.localeCompare(b)))
  return r
}
