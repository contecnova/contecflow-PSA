// @vitest-environment node
import fs from 'node:fs'
import path from 'node:path'
import { parse } from '@babel/parser'
import { describe, expect, it } from 'vitest'
import * as grafico from '../constants/estilosGrafico'

// Pasada final de estilos 2026-11. `style` en línea solo con propiedades CSS
// personalizadas; lo residual (spreads de props `style` ajenas, componentes sin
// `className`) tiene un tope que solo puede bajar.
const RESIDUAL_MAXIMO = 64
const SRC = path.resolve(__dirname, '..')

function* ficheros(dir: string): Generator<string> {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) { if (e.name !== '__tests__') yield* ficheros(p) }
    else if (/\.tsx$/.test(e.name) && !/\.test\./.test(e.name)) yield p
  }
}
type Nodo = { type: string; [k: string]: unknown }
function visitar(n: unknown, fn: (n: Nodo) => void): void {
  if (!n || typeof (n as Nodo).type !== 'string') return
  fn(n as Nodo)
  for (const [k, v] of Object.entries(n as Nodo)) {
    if (k === 'loc') continue
    if (Array.isArray(v)) v.forEach((h) => visitar(h, fn))
    else if (v && typeof v === 'object') visitar(v, fn)
  }
}

describe('estilos en línea', () => {
  it('los style={{…}} crudos no superan el residual conocido', () => {
    let crudos = 0
    for (const f of ficheros(SRC)) {
      const t = fs.readFileSync(f, 'utf8')
      if (!t.includes('style={')) continue
      const ast = parse(t, { sourceType: 'module', plugins: ['jsx', 'typescript'] })
      visitar(ast.program, (n) => {
        if (n.type !== 'JSXAttribute' || (n.name as Nodo).name !== 'style') return
        const v = n.value as Nodo | null
        if (!v || v.type !== 'JSXExpressionContainer') return
        let x = v.expression as Nodo
        while (x.type === 'TSAsExpression') x = x.expression as Nodo
        if (x.type !== 'ObjectExpression') return
        const props = x.properties as Nodo[]
        const soloVars = props.every((p) => {
          if (p.type !== 'ObjectProperty') return false
          let k = p.key as Nodo
          while (k.type === 'TSAsExpression') k = k.expression as Nodo
          const nombre = (k.name ?? k.value) as string
          return typeof nombre === 'string' && nombre.startsWith('--')
        })
        if (!soloVars) crudos++
      })
    }
    expect(crudos).toBeLessThanOrEqual(RESIDUAL_MAXIMO)
  })

  it('cada clase generada (-eN / -mN) que se usa en un .tsx existe en el CSS del fichero', () => {
    const faltan: string[] = []
    for (const f of ficheros(SRC)) {
      const t = fs.readFileSync(f, 'utf8')
      const usadas = new Set([...t.matchAll(/['"` ]([a-z0-9]+(?:-[a-z0-9]+)*-[em]\d+)(?=['"` ])/g)].map((m) => m[1]))
      if (!usadas.size) continue
      const dir = path.dirname(f)
      const base = path.basename(f).replace(/\.tsx$/, '')
      const css = [`${base}.css`, `${base}.estilos.css`].map((n) => path.join(dir, n)).filter((p) => fs.existsSync(p)).map((p) => fs.readFileSync(p, 'utf8')).join('\n')
      for (const c of usadas) if (/-[em]\d+$/.test(c) && !css.includes(`.${c} `) && !css.includes(`.${c}{`) ) faltan.push(`${path.relative(SRC, f)}: ${c}`)
    }
    // Solo cuentan las clases con el prefijo generado del propio fichero.
    const propias = faltan.filter((x) => {
      const [f, c] = x.split(': ')
      const prefijo = path.basename(f).replace(/\.tsx$/, '').replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()
      return c.startsWith(`${prefijo}-`)
    })
    expect(propias).toEqual([])
  })

  it('los objetos de gráfico solo usan var(--token) en colores y tamaños de texto', () => {
    for (const [nombre, estilo] of Object.entries(grafico)) {
      for (const [prop, valor] of Object.entries(estilo as Record<string, string | number>)) {
        if (/^(color|background|border|fontSize)$/.test(prop)) expect(`${nombre}.${prop}=${valor}`).toMatch(/var\(--/)
      }
    }
  })
})
