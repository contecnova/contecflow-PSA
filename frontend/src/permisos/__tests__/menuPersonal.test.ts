// Menú lateral personalizable (23-11-2026): fusión con categorías/pestañas nuevas,
// ocultar sin quitar permisos y menú por defecto del rol.
import { describe, expect, it } from 'vitest'
import {
  aplicarMenu, alternarOculta, menuEfectivo, moverCategoria, moverPestana, normalizarPreferencia,
  VERSION_DEL_MENU, type PreferenciaDeMenu,
} from '../menuPersonal'
import { puedeAbrir } from '../navegacion'
import { NAV_GROUPS, PANEL_DE_CATEGORIA } from '../../components/layout/menuLateral'

const G = (id: string, ...rutas: string[]) => ({ id, items: rutas.map(to => ({ to })) })
const ids = (gs: { id?: string }[]) => gs.map(g => g.id)
const rutas = (g: { items: { to?: string }[] }) => g.items.map(i => i.to)

describe('normalizarPreferencia', () => {
  it('sin preferencia o con otra forma: null', () => {
    expect(normalizarPreferencia(null)).toBeNull()
    expect(normalizarPreferencia('x')).toBeNull()
    expect(normalizarPreferencia([1])).toBeNull()
  })
  it('limpia tipos, duplicados y claves desconocidas', () => {
    expect(normalizarPreferencia({ orden: ['a', 'a', 3], ocultas: { a: ['/x', '/x'], b: [] }, raro: 1 })).toEqual({
      version: VERSION_DEL_MENU, orden: ['a'], ocultas: { a: ['/x'] }, orden_pestanas: {},
    })
  })
})

describe('aplicarMenu: fusión tolerante', () => {
  const pref: PreferenciaDeMenu = {
    version: 1, orden: ['b', 'ya_no_existe', 'a'],
    ocultas: { a: ['/a2', '/borrada'] }, orden_pestanas: { a: ['/a3', '/a1'] },
  }
  it('ordena, oculta e ignora lo que ya no existe', () => {
    const r = aplicarMenu([G('a', '/a1', '/a2', '/a3'), G('b', '/b1')], pref)
    expect(ids(r)).toEqual(['b', 'a'])
    expect(rutas(r[1])).toEqual(['/a3', '/a1'])
  })
  it('categorías y pestañas nuevas: al final y visibles', () => {
    const r = aplicarMenu([G('nueva', '/n1'), G('a', '/a1', '/a2', '/a3', '/a4'), G('b', '/b1')], pref)
    expect(ids(r)).toEqual(['b', 'a', 'nueva'])
    expect(rutas(r[1])).toEqual(['/a3', '/a1', '/a4'])
    expect(rutas(r[2])).toEqual(['/n1'])
  })
  it('sin preferencia: el orden del código', () => {
    const gs = [G('a', '/a1'), G('b', '/b1')]
    expect(aplicarMenu(gs, null)).toBe(gs)
  })
})

describe('ocultar no quita ni da permisos', () => {
  it('una ruta no permitida en la preferencia no aparece', () => {
    // El menú llega filtrado por permisos: /a2 no está (no permitida).
    const pref: PreferenciaDeMenu = { version: 1, orden: [], ocultas: {}, orden_pestanas: { a: ['/a2', '/a1'] } }
    expect(rutas(aplicarMenu([G('a', '/a1')], pref)[0])).toEqual(['/a1'])
  })
  it('la ruta oculta sigue abriéndose (la matriz de permisos no mira el menú)', () => {
    const todo = () => true
    const oculta = alternarOculta(null, 'proyectos', '/gantt')
    expect(rutas(aplicarMenu([G('proyectos', '/projects', '/gantt')], oculta)[0])).toEqual(['/projects'])
    expect(puedeAbrir('/gantt', todo)).toBe(true)
  })
  it('volver a marcarla la enseña', () => {
    const p = alternarOculta(alternarOculta(null, 'a', '/a1'), 'a', '/a1')
    expect(p.ocultas).toEqual({})
  })
})

describe('reordenar', () => {
  it('categorías y pestañas', () => {
    expect(moverCategoria(null, ['a', 'b', 'c'], 2, 0).orden).toEqual(['c', 'a', 'b'])
    expect(moverPestana(null, 'a', ['/1', '/2'], 0, 1).orden_pestanas).toEqual({ a: ['/2', '/1'] })
    expect(moverCategoria(null, ['a', 'b'], 0, 5).orden).toEqual(['a', 'b'])
  })
})

describe('menú por defecto del rol', () => {
  const delRol: PreferenciaDeMenu = { version: 1, orden: ['b'], ocultas: {}, orden_pestanas: {} }
  const personal: PreferenciaDeMenu = { version: 1, orden: ['a'], ocultas: {}, orden_pestanas: {} }
  it('manda la de la persona; sin ella, la del rol; sin ninguna, el código', () => {
    expect(menuEfectivo(personal, delRol)).toBe(personal)
    expect(menuEfectivo(null, delRol)).toBe(delRol)
    expect(menuEfectivo(null, null)).toBeNull()
  })
  it('restablecer (borrar la personal) vuelve a la del rol', () => {
    expect(ids(aplicarMenu([G('a', '/a'), G('b', '/b')], menuEfectivo(null, delRol)))).toEqual(['b', 'a'])
  })
})

describe('panel de cada categoría', () => {
  it('es una pestaña de su categoría', () => {
    for (const [id, panel] of Object.entries(PANEL_DE_CATEGORIA)) {
      const g = NAV_GROUPS.find(x => x.id === id)
      expect(g?.items.some(i => i.to === panel)).toBe(true)
    }
  })
})
