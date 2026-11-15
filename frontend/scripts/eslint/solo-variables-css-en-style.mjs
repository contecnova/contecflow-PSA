// Regla de ESLint (auditoria 2026-11, pasada final de estilos): el atributo
// `style` solo lleva propiedades CSS personalizadas (`'--x': valor`), que una
// clase consume con `var(--x)`. Cualquier otra propiedad (color, width, display...)
// va a una clase del CSS del fichero, con tokens de index.css.
//
// Se marca `style={{ ... }}` (tambien dentro de `as CSSProperties`) y los
// ternarios/`&&` cuyas ramas sean objetos con propiedades que no son `--x`.
// No se marcan `style={variable}` ni llamadas: no se puede saber su contenido.
//
// Terceros: componentes cuya API solo admite `style` (graficos, flujos) van en
// la opcion `componentesPermitidos`; las props `contentStyle`, `labelStyle`,
// `itemStyle`, `wrapperStyle` y similares no son `style` y no se miran (esos
// objetos viven en constantes de modulo, ver constants/estilosGrafico.ts).

const POR_DEFECTO = ['Cell', 'Bar', 'Line', 'Area', 'Pie', 'XAxis', 'YAxis', 'Tooltip', 'Legend', 'ResponsiveContainer', 'ReactFlow', 'MiniMap', 'Controls', 'Background', 'Handle']

const sinTs = (n) => {
  while (n && (n.type === 'TSAsExpression' || n.type === 'TSSatisfiesExpression' || n.type === 'TSNonNullExpression')) n = n.expression
  return n
}

function esPropiedadPersonalizada(p) {
  if (p.type !== 'Property' && p.type !== 'ObjectProperty') return false
  let k = p.key
  if (p.computed) k = sinTs(k)
  const nombre = k.type === 'Identifier' && !p.computed ? k.name : k.type === 'Literal' ? k.value : null
  return typeof nombre === 'string' && nombre.startsWith('--')
}

function propiedadesCrudas(expr) {
  expr = sinTs(expr)
  if (!expr) return []
  if (expr.type === 'ObjectExpression') return expr.properties.filter((p) => !esPropiedadPersonalizada(p))
  if (expr.type === 'ConditionalExpression') return [...propiedadesCrudas(expr.consequent), ...propiedadesCrudas(expr.alternate)]
  if (expr.type === 'LogicalExpression') return [...propiedadesCrudas(expr.left), ...propiedadesCrudas(expr.right)]
  return []
}

export default {
  meta: {
    type: 'suggestion',
    schema: [{ type: 'object', properties: { componentesPermitidos: { type: 'array', items: { type: 'string' } } }, additionalProperties: false }],
    messages: {
      cruda: "style en línea con propiedades CSS ({{props}}): muévelas a una clase del CSS del fichero (con var(--token)); en `style` solo van propiedades personalizadas ('--x': valor) para valores de datos.",
    },
  },
  create(context) {
    const permitidos = new Set(context.options[0]?.componentesPermitidos ?? POR_DEFECTO)
    return {
      JSXAttribute(node) {
        if (node.name.type !== 'JSXIdentifier' || node.name.name !== 'style') return
        if (!node.value || node.value.type !== 'JSXExpressionContainer') return
        const el = node.parent?.name
        if (el && el.type === 'JSXIdentifier' && permitidos.has(el.name)) return
        const crudas = propiedadesCrudas(node.value.expression)
        if (!crudas.length) return
        const nombres = crudas.map((p) => (p.type === 'SpreadElement' ? '...' : p.key?.name ?? p.key?.value ?? '?'))
        context.report({ node, messageId: 'cruda', data: { props: [...new Set(nombres)].slice(0, 4).join(', ') } })
      },
    }
  },
}
