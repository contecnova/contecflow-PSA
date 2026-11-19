// Reorganización de Configuración (18-11-2026): un solo sitio por ajuste,
// secciones según rol (sin enlaces a 403), redirecciones de las rutas de antes
// y textos en es/en/zh. Ver docs/CONFIGURACION.md.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import es from '../i18n/langs/es.mjs'
import en from '../i18n/langs/en.mjs'
import zh from '../i18n/langs/zh.mjs'
import type { Capacidad } from '../permisos/capacidades'
import { puedeComo } from './capacidadesDelBackend'
import {
  GRUPOS_DE_AJUSTES, IDS_ANTIGUOS, SECCIONES_DE_AJUSTES, puedeVerSeccion,
} from '../pages/settings/catalogoDeAjustes'

const raiz = resolve(__dirname, '..')
const app = readFileSync(resolve(raiz, 'App.tsx'), 'utf8')
const layout = readFileSync(resolve(raiz, 'components/layout/Layout.tsx'), 'utf8')

// 19-11-2026: las secciones piden capacidades; el rol se simula con el catálogo del backend.
const visiblesPara = (rol: string, esSuperadmin = false) => SECCIONES_DE_AJUSTES
  .filter(s => puedeVerSeccion(s, { puede: (c: Capacidad) => puedeComo(rol, esSuperadmin)(c), canOpen: () => true }))
  .map(s => s.id)

describe('catálogo de Configuración', () => {
  it('ids únicos, cada sección en un grupo existente y ningún grupo vacío', () => {
    const ids = SECCIONES_DE_AJUSTES.map(s => s.id)
    expect(new Set(ids).size).toBe(ids.length)
    const grupos = new Set(GRUPOS_DE_AJUSTES.map(g => g.id))
    for (const s of SECCIONES_DE_AJUSTES) expect(grupos.has(s.grupo)).toBe(true)
    for (const g of GRUPOS_DE_AJUSTES) expect(SECCIONES_DE_AJUSTES.some(s => s.grupo === g.id)).toBe(true)
    for (const s of SECCIONES_DE_AJUSTES) expect(Boolean(s.componente) !== Boolean(s.enlace)).toBe(true)
  })

  it('títulos, descripciones y grupos traducidos en es, en y zh', () => {
    for (const dic of [es, en, zh] as unknown as Array<{ ajustes: Record<string, string> }>) {
      for (const g of GRUPOS_DE_AJUSTES) expect(dic.ajustes[`g_${g.id}`]).toBeTruthy()
      for (const s of SECCIONES_DE_AJUSTES) {
        const k = `s_${s.id.replace(/-/g, '_')}`
        expect(dic.ajustes[k], k).toBeTruthy()
        expect(dic.ajustes[`${k}_d`], `${k}_d`).toBeTruthy()
      }
    }
  })

  it('cada rol ve solo lo que el backend le deja usar', () => {
    const rrhh = visiblesPara('hr')
    expect(rrhh).toEqual(expect.arrayContaining(['users', 'depts', 'ausencias', 'vacations', 'horas-extra', 'user-costs', 'mfa']))
    // Políticas y flujos de aprobación: escritura require_admin (antes RRHH llegaba por enlace y recibía 403).
    expect(rrhh).not.toContain('policies')
    expect(rrhh).not.toContain('approval-workflows')
    const pm = visiblesPara('pm')
    expect(pm).toEqual(expect.arrayContaining(['rates', 'issue-types', 'project-workflows', 'custom-fields', 'sd']))
    expect(pm).not.toContain('approval-workflows')
    expect(pm).not.toContain('ai-hub')
    expect(pm).not.toContain('jira')
    expect(visiblesPara('employee')).toEqual(['mfa'])
    expect(visiblesPara('admin')).not.toContain('organizations')
    expect(visiblesPara('admin', true)).toContain('organizations')
  })

  it('el bloqueo por ruta del usuario sigue valiendo con la ruta de antes', () => {
    const tarifas = SECCIONES_DE_AJUSTES.find(s => s.id === 'rates')!
    expect(puedeVerSeccion(tarifas, { puede: () => true, canOpen: r => r !== '/rate-cards' })).toBe(false)
  })

  it('las rutas de antes redirigen a su sección y ya no pintan su propia pantalla', () => {
    expect(app).toMatch(/SECCIONES_DE_AJUSTES\.filter\(s => s\.rutaAntigua\)/)
    expect(app).toMatch(/<Route path="\/settings\/:seccion"/)
    for (const s of SECCIONES_DE_AJUSTES.filter(x => x.rutaAntigua)) {
      expect(app, s.rutaAntigua).not.toContain(`<Route path="${s.rutaAntigua}"`)
    }
    for (const v of ['/settings/policies', '/settings/approval-workflows', '/settings/chat-admin', '/settings/project-workflows']) {
      expect(app).not.toContain(`<Route path="${v}"`)
    }
    // Ids retirados por duplicados.
    expect(IDS_ANTIGUOS['task-types']).toBe('issue-types')
    expect(IDS_ANTIGUOS['email-inbound']).toBe('sd?sub=mail')
  })

  it('el menú tiene una sola entrada de Configuración', () => {
    const grupo = layout.slice(layout.indexOf("{ id: 'configuracion'"), layout.indexOf("]},", layout.indexOf("{ id: 'configuracion'")))
    expect(grupo.match(/\{ to: '/g)).toHaveLength(1)
    for (const r of ['/rate-cards', '/user-costs', '/sla-calendars', '/sd/workflow-designer']) {
      expect(layout).not.toContain(`{ to: '${r}'`)
    }
  })
})
