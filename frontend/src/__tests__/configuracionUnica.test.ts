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
// Menú personalizable (23-11-2026): NAV_GROUPS salió de Layout.tsx a menuLateral.tsx.
const layout = readFileSync(resolve(raiz, 'components/layout/menuLateral.tsx'), 'utf8')

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
    // 23-11-2026: «Agentes de código (MCP)» pide `mcp.usar`, que el backend da a TODOS
    // (cada persona genera sus propias credenciales; las herramientas piden además la
    // capacidad de su ruta REST). Encender o apagar MCP sigue siendo de gobierno.administrar.
    expect(visiblesPara('employee')).toEqual(['mcp', 'mfa'])
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

// 19-11-2026: pestañas de configuración que quedaban en módulos, movidas a Configuración.
describe('configuración que salió de los módulos (19-11-2026)', () => {
  const leer = (f: string) => readFileSync(resolve(raiz, f), 'utf8')
  // [sección, grupo, capacidad, fichero del módulo, componente de la sección]
  const MOVIDAS: Array<[string, string, Capacidad, string, string]> = [
    ['git', 'integraciones', 'proyectos.gobierno', 'pages/GitPage.tsx', 'components/git/ConfigGit.tsx'],
    ['cartera', 'proyectos', 'cartera.gestionar', 'pages/CarteraIntakePage.tsx', 'components/cartera/ConfigCartera.tsx'],
    ['m365-informes', 'integraciones', 'org.administrar', 'components/bi/BiO365Panel.tsx', 'components/bi/ConfigBiO365.tsx'],
    ['sd-agente', 'servicedesk', 'sd.administrar', 'components/servicedesk/AgenteAutonomoPanel.tsx', 'components/servicedesk/ConfigAgenteAutonomo.tsx'],
    ['sd-voz', 'servicedesk', 'sd.administrar', 'components/servicedesk/VoiceAgentPanel.tsx', 'components/servicedesk/ConfigAgenteDeVoz.tsx'],
    ['sd-autorresolucion', 'servicedesk', 'sd.administrar', 'components/servicedesk/AutoResolutionPanel.tsx', 'components/servicedesk/ConfigAutoResolucion.tsx'],
    ['ia-asignacion', 'ia', 'ia.asignacion_config', 'pages/SemanticEnginePage.tsx', 'components/asignacion-ia/ConfigMotorSemantico.tsx'],
    // 19-11-2026: asistente de reuniones (nace en Configuración; la pantalla no tiene botón «Configurar»).
    ['reuniones', 'ia', 'reuniones.config', 'pages/MeetingsAIPage.tsx', 'components/reuniones/ConfigReuniones.tsx'],
    // 20-11-2026: proveedores y CMDB de software también nacen en Configuración (sin botón «Configurar» en el módulo).
    ['proveedores', 'finanzas', 'proveedores.config', 'pages/SubcontractorsPage.tsx', 'pages/proveedores/ConfigProveedores.tsx'],
    ['cmdb-software', 'servicedesk', 'software.config', 'pages/CMDBPage.tsx', 'components/cmdb/software/ConfigSoftware.tsx'],
  ]

  it('cada una es una sección de su grupo, con su capacidad', () => {
    for (const [id, grupo, capacidad] of MOVIDAS) {
      const s = SECCIONES_DE_AJUSTES.find(x => x.id === id)
      expect(s, id).toBeTruthy()
      expect(s!.grupo, id).toBe(grupo)
      expect(s!.capacidad, id).toBe(capacidad)
      expect(s!.componente, id).toBeTruthy()
    }
  })

  // 19-11-2026: los módulos no llevan botón «Configurar»; toda la configuración se
  // hace desde Configuración. Solo hay enlaces contextuales («Ir a Configuración»)
  // donde una acción no funciona por falta de configuración.
  it('el módulo ya no tiene la pestaña ni el botón «Configurar»; la sección existe en Configuración', () => {
    for (const [id, , , modulo, seccion] of MOVIDAS) {
      const src = leer(modulo)
      expect(src, modulo).not.toMatch(/id: '(config|overview)'/)
      expect(src, modulo).not.toMatch(/\b(t|traducir)\('ajustes\.configurar'\)/)
      expect(SECCIONES_DE_AJUSTES.some(s => s.id === id), id).toBe(true)
      // El formulario ya no vive en el módulo.
      expect(leer(seccion).length).toBeGreaterThan(0)
    }
  })

  it('los enlaces con ?tab=config de las páginas redirigen a la sección', () => {
    for (const [id, f] of [['git', 'pages/GitPage.tsx'], ['cartera', 'pages/CarteraIntakePage.tsx'], ['ia-asignacion', 'pages/SemanticEnginePage.tsx']]) {
      expect(leer(f), f).toMatch(new RegExp(`<Navigate to="/settings/${id}" replace />`))
    }
  })

  it('cada rol ve solo las que el backend le deja guardar', () => {
    const pm = visiblesPara('pm')
    expect(pm).toEqual(expect.arrayContaining(['git', 'cartera']))
    for (const id of ['m365-informes', 'sd-agente', 'sd-voz', 'sd-autorresolucion', 'ia-asignacion']) expect(pm).not.toContain(id)
    const rrhh = visiblesPara('hr')
    expect(rrhh).toContain('ia-asignacion')
    for (const id of ['git', 'cartera', 'm365-informes', 'sd-agente', 'sd-voz', 'sd-autorresolucion']) expect(rrhh).not.toContain(id)
    expect(visiblesPara('team_lead')).not.toContain('git')
    expect(visiblesPara('admin')).toEqual(expect.arrayContaining(MOVIDAS.map(m => m[0])))
  })

  it('no se movieron: el portal de cada cliente (dato del cliente) ni Microsoft 365 (ya montado en Configuración)', () => {
    expect(leer('pages/clients/ClientsTabsPortal.tsx')).toContain("{ id: 'config'")
    expect(SECCIONES_DE_AJUSTES.find(s => s.id === 'm365')?.rutaAntigua).toBe('/m365')
  })
})
