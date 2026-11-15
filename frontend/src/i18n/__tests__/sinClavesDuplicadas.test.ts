// Ninguna clave de los diccionarios puede declararse dos veces en el mismo
// objeto. En un literal JS la ÚLTIMA gana en silencio, así que la traducción
// anterior se pierde sin aviso (Segunda auditoría 2026-11).
//
// Se analiza el AST con el parser de TypeScript, no el texto: hay líneas con
// varias claves (`a: 'x', b: 'y'`) que un análisis por líneas no ve.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

const IDIOMAS = ['es', 'en', 'zh'] as const

function duplicadas(codigo: string): string[] {
  const ruta = join(__dirname, '..', 'langs', `${codigo}.mjs`)
  const fuente = readFileSync(ruta, 'utf8')
  const sf = ts.createSourceFile(ruta, fuente, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS)
  const out: string[] = []

  const visitar = (nodo: ts.Node, camino: string): void => {
    if (ts.isObjectLiteralExpression(nodo)) {
      const vistas = new Set<string>()
      for (const p of nodo.properties) {
        if (!ts.isPropertyAssignment(p) || !(ts.isIdentifier(p.name) || ts.isStringLiteral(p.name))) {
          ts.forEachChild(p, (h) => visitar(h, camino))
          continue
        }
        const clave = p.name.text
        const completa = camino ? `${camino}.${clave}` : clave
        if (vistas.has(clave)) {
          const { line } = sf.getLineAndCharacterOfPosition(p.getStart())
          out.push(`${completa} (línea ${line + 1})`)
        }
        vistas.add(clave)
        visitar(p.initializer, completa)
      }
      return
    }
    ts.forEachChild(nodo, (h) => visitar(h, camino))
  }
  visitar(sf, '')
  return out
}

describe('diccionarios sin claves ni módulos duplicados', () => {
  for (const codigo of IDIOMAS) {
    it(`${codigo}.mjs no declara ninguna clave dos veces`, () => {
      expect(duplicadas(codigo)).toEqual([])
    })
  }
})
