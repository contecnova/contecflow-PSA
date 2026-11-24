// Matriz de permisos (19-11-2026): una sola declaración para rutas y menú, un
// solo hook (`usePermiso` / `puede`) y una sola fuente (el backend,
// `app/core/capacidades.py`). Ver DOCS.md («Matriz de permisos»).
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AuthContext } from '../context/AuthContext'
import type { AuthContextValue } from '../context/AuthContext'
import { CAPACIDADES, tieneCapacidad } from '../permisos/capacidades'
import type { Capacidad } from '../permisos/capacidades'
import { RUTAS, paginaDeInicio, puedeAbrir, rutaDeclarada } from '../permisos/navegacion'
import { usePermiso } from '../permisos/usePermiso'
import { CATALOGO_DEL_BACKEND, capacidadesDe, puedeComo } from './capacidadesDelBackend'

const raiz = resolve(__dirname, '..')
const app = readFileSync(resolve(raiz, 'App.tsx'), 'utf8')
// Menú personalizable (23-11-2026): NAV_GROUPS salió de Layout.tsx a menuLateral.tsx
// (y la personalización a permisos/menuPersonal.ts); se miran los tres.
const layout = ['components/layout/Layout.tsx', 'components/layout/menuLateral.tsx', 'permisos/menuPersonal.ts']
  .map(f => readFileSync(resolve(raiz, f), 'utf8')).join('\n')

/** Rutas con `<ProtectedRoute>` en App.tsx. */
const rutasProtegidas = [...app.matchAll(/<Route path="([^"]+)"\s+element=\{\s*<ProtectedRoute/g)].map(m => m[1])
/** Destinos del menú lateral. */
const destinosDelMenu = [...layout.matchAll(/\{ to: '([^']+)'/g)].map(m => m[1])

function fuentes(dir: string): string[] {
  return readdirSync(dir).flatMap(n => {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) return n === '__tests__' ? [] : fuentes(p)
    return /\.(ts|tsx)$/.test(n) && !/\.test\./.test(n) ? [p] : []
  })
}

describe('catálogo de capacidades', () => {
  it('coincide con el del backend', () => {
    expect([...CAPACIDADES].sort()).toEqual(Object.keys(CATALOGO_DEL_BACKEND).sort())
  })

  it('cada capacidad del backend tiene roles reales', () => {
    const reales = ['admin', 'pm', 'team_lead', 'hr', 'employee', 'subcontractor']
    for (const [n, roles] of Object.entries(CATALOGO_DEL_BACKEND)) {
      expect(roles, n).toBeDefined()
      for (const r of roles) expect(reales, `${n}: ${r}`).toContain(r)
    }
    expect(CATALOGO_DEL_BACKEND['plataforma.empresas']).toEqual([])
  })

  it('flujo de demanda (migración 195): ver internos, gestionar admin y PM, configurar admin', () => {
    expect([...CATALOGO_DEL_BACKEND['demanda.ver']].sort()).toEqual(['admin', 'employee', 'hr', 'pm', 'team_lead'])
    expect([...CATALOGO_DEL_BACKEND['demanda.gestionar']].sort()).toEqual(['admin', 'pm'])
    expect(CATALOGO_DEL_BACKEND['demanda.config']).toEqual(['admin'])
    expect(CAPACIDADES).toEqual(expect.arrayContaining(['demanda.ver', 'demanda.gestionar', 'demanda.config']))
    // «Mis solicitudes» llega a cualquier sesión: /demand no pide demanda.ver (lo filtra la API).
    expect(capacidadesDe('subcontractor')).not.toContain('demanda.ver')
  })

  it('tieneCapacidad: sin lista, no', () => {
    expect(tieneCapacidad(undefined, 'org.administrar')).toBe(false)
    expect(tieneCapacidad(['org.administrar'], 'org.administrar')).toBe(true)
  })
})

describe('rutas y menú salen de la misma declaración', () => {
  it('App.tsx no escribe roles a mano y todas sus rutas protegidas están declaradas', () => {
    expect(app).not.toMatch(/roles=\{/)
    expect(rutasProtegidas.length).toBeGreaterThan(80)
    const sinDeclarar = rutasProtegidas.filter(r => !RUTAS.some(d => d.patron === r))
    expect(sinDeclarar).toEqual([])
  })

  it('el menú no escribe roles a mano y cada destino está declarado', () => {
    expect(layout).not.toMatch(/\broles: /)
    expect(destinosDelMenu.length).toBeGreaterThan(70)
    expect(destinosDelMenu.filter(d => !rutaDeclarada(d))).toEqual([])
  })

  it('cada declaración es una ruta real de App.tsx (sin entradas muertas)', () => {
    for (const d of RUTAS) expect(rutasProtegidas, d.patron).toContain(d.patron)
  })

  it('para cada rol, lo que el menú enseña la ruta lo abre (misma función)', () => {
    for (const rol of ['admin', 'pm', 'team_lead', 'hr', 'employee', 'subcontractor']) {
      const puede = puedeComo(rol) as (c: Capacidad) => boolean
      for (const d of destinosDelMenu) {
        expect(puedeAbrir(d, puede), `${rol} ${d}`).toBe(puedeAbrir(d, puede, true))
      }
    }
  })

  it('los desacuerdos de antes quedan resueltos', () => {
    const empleado = puedeComo('employee') as (c: Capacidad) => boolean
    const externo = puedeComo('subcontractor') as (c: Capacidad) => boolean
    const jefe = puedeComo('team_lead') as (c: Capacidad) => boolean
    // /lessons: el menú no la daba al empleado y la ruta sí → ahora ambos sí (API require_internal_user).
    expect(puedeAbrir('/lessons', empleado)).toBe(true)
    // /expenses y /documents: el externo no las ve ni las abre.
    expect(puedeAbrir('/expenses', externo)).toBe(false)
    expect(puedeAbrir('/documents', externo)).toBe(false)
    expect(puedeAbrir('/expenses', jefe)).toBe(true)
    // /projects/:id: parámetros resueltos con la misma declaración.
    expect(puedeAbrir('/projects/7', externo)).toBe(true)
    expect(puedeAbrir('/projects/7/analytics', empleado)).toBe(false)
    expect(puedeAbrir('/finance-dashboard', empleado)).toBe(false)
    // /search: la API es require_internal_user; el externo ya no entra a recibir 403.
    expect(puedeAbrir('/search', externo)).toBe(false)
  })

  it('el superadmin abre todo lo declarado', () => {
    const superadmin = puedeComo('admin', true) as (c: Capacidad) => boolean
    for (const d of RUTAS) expect(puedeAbrir(d.patron.replace(/:[a-zA-Z]+/g, 'x'), superadmin), d.patron).toBe(true)
  })

  it('página de inicio según capacidades', () => {
    const inicio = (rol: string) => paginaDeInicio(puedeComo(rol) as (c: Capacidad) => boolean)
    expect(inicio('admin')).toBe('/projects-dashboard')
    expect(inicio('pm')).toBe('/projects-dashboard')
    expect(inicio('team_lead')).toBe('/projects-dashboard')
    expect(inicio('hr')).toBe('/team-dashboard')
    expect(inicio('employee')).toBe('/work-dashboard')
    expect(inicio('subcontractor')).toBe('/work-dashboard')
  })
})

describe('hook único', () => {
  function Prueba({ c }: { c: Capacidad }) {
    return <span>{usePermiso(c) ? 'si' : 'no'}</span>
  }
  const conCapacidades = (caps: string[]) => ({
    puede: (c: Capacidad) => tieneCapacidad(caps, c),
  }) as unknown as AuthContextValue

  it('usePermiso responde con las capacidades del usuario', () => {
    const { unmount } = render(
      <AuthContext.Provider value={conCapacidades(capacidadesDe('pm'))}><Prueba c="finanzas.ver" /></AuthContext.Provider>)
    expect(screen.getByText('si')).toBeTruthy()
    unmount()
    render(<AuthContext.Provider value={conCapacidades(capacidadesDe('pm'))}><Prueba c="org.administrar" /></AuthContext.Provider>)
    expect(screen.getByText('no')).toBeTruthy()
  })

  it('nadie pregunta por rol: sin hasRole ni role === en el código', () => {
    const malos: string[] = []
    for (const f of fuentes(raiz)) {
      const s = readFileSync(f, 'utf8').replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, '')
      if (/\bhasRole\(/.test(s)) malos.push(`${f}: hasRole`)
      if (/(user|yo)\??\.role\s*===|includes\((user|yo)\?\.role|is_superadmin/.test(s)) malos.push(`${f}: rol/superadmin`)
    }
    expect(malos).toEqual([])
  }, 60_000)

  it('sin listas de roles escritas a mano ni roles inexistentes en los selectores de rol de usuario', () => {
    // Pantallas que tenían su propia lista de roles de usuario (los papeles de proyecto,
    // `ProjectMember.role`, son otro catálogo y no cuentan).
    const conSelector = [
      'pages/ApprovalsPage.tsx', 'pages/WorkflowsPage.tsx', 'pages/DocumentsPage.tsx', 'pages/EnterprisePage.tsx',
      'pages/TeamDashboardPage.tsx', 'pages/SettingsPageSections.tsx', 'pages/ResourcesPage.tsx',
      // Troceado de EnterprisePage (23-11-2026, auditoría M12).
      ...['EnterpriseComun', 'EnterpriseWebhooksGdprEmail', 'EnterpriseIntegraciones', 'EnterpriseAuditoriaYClaves',
        'EnterpriseSso'].map(n => `pages/${n}.tsx`),
      // Troceado de ApprovalsPage, DocumentsPage y SettingsPageSections (23-11-2026, auditoría M12).
      ...['aprobaciones/compartido', 'aprobaciones/PasosYDetalle', 'aprobaciones/MisPendientes', 'aprobaciones/Plantillas',
        'aprobaciones/SimuladorYCuellos', 'aprobaciones/GruposYCarga', 'documentos/compartido', 'documentos/TarjetasDeDocumento',
        'documentos/SubidaYCompartir', 'documentos/CajonDeDocumento', 'settings-sections/SeccionGeneral',
        'settings-sections/SeccionUsuariosYRoles', 'settings-sections/SeccionAlertasYMetricas',
        'settings-sections/SeccionOrganizacion', 'settings-sections/SeccionCamposDeEntidad',
        'settings-sections/SeccionFirmaElectronica'].map(n => `pages/${n}.tsx`), 'pages/settings-sections/tiposDeAjustes.ts',
      'components/servicedesk/AnalisisDelCambio.tsx', 'context/AuthContext.tsx', 'constants/api.ts', 'utils/helpers.ts',
    ]
    for (const rel of conSelector) {
      const s = readFileSync(resolve(raiz, rel), 'utf8').replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, '')
      expect(s, rel).not.toMatch(/'(designer|developer|finance|client_user|sales|superadmin)'/)
      expect(s, rel).not.toMatch(/\[\s*'admin',\s*'pm',/)
      expect(s, rel).not.toMatch(/ROLE_LABELS|ROLE_COLORS|ROLES_AVAILABLE|ROLES_SSO|ROLES_RESPONSABLES/)
    }
    expect(readFileSync(resolve(raiz, 'constants/constants.json'), 'utf8')).not.toMatch(/"ROLES"/)
    expect(readFileSync(resolve(raiz, 'constants/business_config.json'), 'utf8')).not.toMatch(/"ROLE_LABELS"|"ROLE_COLORS"/)
  })
})
