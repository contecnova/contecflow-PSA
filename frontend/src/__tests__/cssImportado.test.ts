// 23-11-2026: al trocear PortalDashboard.tsx se perdió `import './PortalDashboard.css'`
// y el panel del portal salió sin estilos (tarjetas a todo el ancho, filas
// apiladas). Ni tsc ni eslint lo detectan: un CSS sin importar no da error.
// Esta comprobación estática lo impide:
//   1. cada `X.tsx`/`X.ts` con un `X.css` al lado lo importa (o está en EXCEPCIONES
//      porque lo importa otro módulo que lo usa);
//   2. ningún .css de src queda sin importar en ningún sitio.
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const RAIZ = path.resolve(__dirname, '..')

/** Componente → módulo que importa su CSS en su lugar (motivo). */
const EXCEPCIONES: Record<string, string> = {
  'components/traduccion/VersionesKbPanel.tsx': 'lo importa components/traduccion/VersionesPanel.tsx, que lo usa',
}

function recorrer(dir: string, salida: string[] = []): string[] {
  for (const nombre of fs.readdirSync(dir)) {
    const ruta = path.join(dir, nombre)
    if (fs.statSync(ruta).isDirectory()) {
      if (nombre !== 'node_modules') recorrer(ruta, salida)
    } else {
      salida.push(ruta)
    }
  }
  return salida
}

const ficheros = recorrer(RAIZ)
const css = ficheros.filter(f => f.endsWith('.css'))
const codigo = ficheros.filter(f => /\.(tsx?|jsx?|mjs)$/.test(f) && !f.includes('__tests__'))
const fuentes = new Map(codigo.map(f => [f, fs.readFileSync(f, 'utf8')]))
const rel = (f: string) => path.relative(RAIZ, f).split(path.sep).join('/')
const importa = (fuente: string, nombreCss: string) =>
  fuente.includes(`'./${nombreCss}'`) || fuente.includes(`"./${nombreCss}"`)

describe('cada componente carga su CSS', () => {
  it('X.tsx importa el X.css que tiene al lado', () => {
    const sinImportar: string[] = []
    for (const hoja of css) {
      const base = hoja.slice(0, -4)
      for (const ext of ['.tsx', '.ts']) {
        const comp = base + ext
        if (!fuentes.has(comp)) continue
        if (EXCEPCIONES[rel(comp)]) continue
        if (!importa(fuentes.get(comp) as string, path.basename(hoja))) sinImportar.push(rel(comp))
      }
    }
    expect(sinImportar, 'importa el CSS en el componente (o añádelo a EXCEPCIONES con el motivo)').toEqual([])
  })

  it('ningún .css queda sin importar en ningún sitio', () => {
    const todo = [...fuentes.values()].join('\n')
    const huerfanos = css.filter(h => !todo.includes(path.basename(h))).map(rel)
    expect(huerfanos).toEqual([])
  })

  it('las excepciones siguen siendo ciertas', () => {
    for (const comp of Object.keys(EXCEPCIONES)) {
      const hoja = path.basename(comp).replace(/\.tsx?$/, '.css')
      const algunoLoImporta = [...fuentes.values()].some(f => importa(f, hoja))
      expect(algunoLoImporta, `${comp}: nadie importa ${hoja}`).toBe(true)
    }
  })
})
