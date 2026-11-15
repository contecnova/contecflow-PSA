// @vitest-environment node
import fs from 'node:fs'
import path from 'node:path'
import { parse } from '@babel/parser'
import { describe, expect, it } from 'vitest'
import * as grafico from '../constants/estilosGrafico'
import { etiquetaDelTema, tooltipDelTema, tooltipDelTemaConBorde } from '../constants/estilosGrafico'

// Pasada final de estilos 2026-11. `style` en línea solo con propiedades CSS
// personalizadas (`'--x': valor`); un `...style` que pasa quien llama no cuenta
// (como en la regla de ESLint). Residual aceptado: 0.
const RESIDUAL_MAXIMO = 0
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
  it('no queda ningún style={{…}} con propiedades CSS crudas', () => {
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
          if (p.type === 'SpreadElement') return true
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

  it('ningún style={f(…)} devuelve un objeto crudo: solo ayudantes de variables CSS', () => {
    const permitidas = new Set(['varCss', 'cssVars', 'colorVar', 'colorVars', 'chipColor', 'medidasDeEsqueleto', 'varsBadge', 'cVar', 'catVar', 'evColor', 'riskVar', 'estadoVar', 'anchura', 'tone', 'color', 'chip'])
    const crudas: string[] = []
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
        if (x.type !== 'CallExpression') return
        const c = x.callee as Nodo
        const nombre = (c.type === 'Identifier' ? c.name : (c.property as Nodo | undefined)?.name) as string
        if (!permitidas.has(nombre)) crudas.push(`${path.relative(SRC, f)}: ${nombre}()`)
      })
    }
    expect(crudas).toEqual([])
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
      if (typeof estilo === 'function') continue
      for (const [prop, valor] of Object.entries(estilo as Record<string, string | number>)) {
        if (/^(color|background|border|fontSize)$/.test(prop)) expect(`${nombre}.${prop}=${valor}`).toMatch(/var\(--/)
      }
    }
  })

  it('los objetos de gráfico con colores del tema usan el color resuelto y nada literal', () => {
    const tokens = { tooltipBg: '#101820', textColor: '#e0e8f0' }
    expect(tooltipDelTema(tokens)).toEqual({ background: '#101820', border: 'none', borderRadius: 8, color: 'var(--text-1)' })
    expect(tooltipDelTemaConBorde(tokens).background).toBe('#101820')
    expect(etiquetaDelTema(tokens)).toEqual({ color: '#e0e8f0' })
  })

  it('los literales de color de estilos en línea tienen token (sin rgba/hex en los bloques generados)', () => {
    const literales: string[] = []
    const recorrer = (dir: string) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, e.name)
        if (e.isDirectory()) { recorrer(p); continue }
        if (!/\.css$/.test(e.name)) continue
        const t = fs.readFileSync(p, 'utf8')
        const a = t.indexOf('>>> estilos-en-linea')
        const b = t.indexOf('<<< estilos-en-linea')
        if (a < 0) continue
        for (const l of t.slice(a, b).split('\n')) if (/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(l) && !l.startsWith('/*')) literales.push(`${e.name}: ${l.trim()}`)
      }
    }
    recorrer(SRC)
    expect(literales).toEqual([])
  })

  it('los tokens nuevos existen en :root y en el tema light', () => {
    const css = fs.readFileSync(path.join(SRC, 'index.css'), 'utf8')
    const light = css.slice(css.indexOf('[data-theme="light"] {'), css.indexOf('[data-theme="high-contrast"] {'))
    for (const t of ['--success-bg-strong', '--warning-bg-strong', '--danger-ring', '--shadow-menu', '--overlay-scrim', '--shadow-drawer-lateral']) expect(css).toContain(`${t}:`)
    for (const t of ['--shadow-menu', '--overlay-scrim', '--shadow-drawer-lateral', '--shadow-sidebar']) expect(light).toContain(`${t}:`)
  })
})
