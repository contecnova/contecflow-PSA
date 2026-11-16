// Verificación 16-11-2026: en el menú lateral se cortaban nombres («Flujos de
// estado de proyecto») y /settings quedaba marcado a la vez que /settings/*.
// Se comprueba en las fuentes porque el corte depende del ancho real del texto.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const raiz = resolve(__dirname, '..')
const layout = readFileSync(resolve(raiz, 'components/layout/Layout.tsx'), 'utf8')
const css = readFileSync(resolve(raiz, 'components/layout/Layout.css'), 'utf8')

function regla(selector: string): string {
  const m = css.match(new RegExp(selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}'))
  return m ? m[1] : ''
}

describe('menú lateral', () => {
  it('el nombre de una entrada pasa a dos líneas en lugar de cortarse', () => {
    const etiqueta = regla('.layo-box-4')
    expect(etiqueta).toMatch(/white-space:\s*normal/)
    expect(etiqueta).toMatch(/min-width:\s*0/)
    expect(etiqueta).not.toMatch(/text-overflow|nowrap/)
    expect(regla('.nav-enlace')).not.toMatch(/nowrap/)
  })

  it('una ruta padre de otra entrada del menú solo se marca exacta', () => {
    expect(layout).toMatch(/end=\{RUTAS_PADRE_DEL_MENU\.has\(/)
    expect(layout).toMatch(/o\.startsWith\(r \+ '\/'\)/)
  })
})
