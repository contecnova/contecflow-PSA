/**
 * Matriz de permisos (19-11-2026): la ÚNICA declaración de qué capacidad abre
 * cada pantalla. La leen a la vez:
 *
 * - las rutas (`ProtectedRoute` en App.tsx busca aquí la de la ruta pedida;
 *   sin capacidad → a /403),
 * - el menú (`components/layout/Layout.tsx`: un elemento se ve si su `to`
 *   está permitido aquí),
 * - y la página de inicio tras entrar (`paginaDeInicio`).
 *
 * Antes las rutas llevaban `roles={[...]}` y el menú `roles: [...]`, escritos
 * a mano y en desacuerdo (p. ej. /lessons, /projects, /expenses, /documents).
 * Una ruta sin capacidad aquí la abre cualquier persona con sesión. El bloqueo
 * por módulo del rol personalizado (`blocked_routes`) se sigue aplicando aparte
 * (`canOpen`).
 */
import { matchPath } from 'react-router-dom'
import type { Capacidad } from './capacidades'

export type RutaDeclarada = { patron: string; capacidad?: Capacidad }

const con = (capacidad: Capacidad | undefined, patrones: string[]): RutaDeclarada[] =>
  patrones.map(patron => ({ patron, capacidad }))

export const RUTAS: RutaDeclarada[] = [
  // Cualquiera con sesión (cada uno lo suyo; el servidor acota los datos).
  ...con(undefined, [
    '/', '/403', '/work-dashboard', '/tasks', '/time', '/imputar', '/timer', '/timesheets', '/absences', '/overtime',
    '/inbox', '/my-equipment', '/settings', '/settings/:seccion',
  ]),
  ...con('proyectos.ver', ['/projects', '/projects/:id']),
  ...con('colaboracion.ver', [
    '/chat', '/chat/call/:callId', '/calendar', '/documents', '/wiki', '/search', '/ask-company', '/approvals',
    '/portfolio/intake', '/skills', '/training', '/reports',
  ]),
  ...con('gastos.ver', ['/expenses']),
  // Flujo de demanda (22-11-2026): «Mis solicitudes» es para cualquiera con sesión; las vistas de gestión las acota el servidor (demanda.ver).
  ...con(undefined, ['/demand']),
  ...con('proyectos.trabajo', [
    '/lessons', '/sprints', '/raci', '/changelog', '/uat', '/gantt', '/epic-gantt', '/epics', '/dependencies',
  ]),
  // Asistente de reuniones (19-11-2026): antes con `proyectos.trabajo`.
  ...con('reuniones.usar', ['/meetings-ai']),
  ...con('proyectos.panel', ['/projects-dashboard']),
  ...con('proyectos.gobierno', ['/deliverables', '/changes', '/risks', '/git', '/esign']),
  ...con('equipo.ver', ['/team-dashboard', '/resources/planning', '/alm/altas-y-bajas']),
  ...con('recursos.ver', ['/resources', '/capacity', '/org-chart', '/okrs', '/performance-reviews']),
  ...con('recursos.prevision', ['/resource-forecast', '/resource-scheduler', '/bpm']),
  ...con('finanzas.ver', [
    '/finance-dashboard', '/clients', '/pipeline', '/contracts', '/invoices', '/milestone-billing', '/profitability',
    '/revenue', '/budgets', '/scenarios', '/nps', '/client-portal',
  ]),
  // Proveedores (migración 191): la ficha la ven los gestores (`proveedores.ver`, como
  // `/api/v1/suppliers`), no solo finanzas; el portal, los externos contacto de su proveedor.
  ...con('proveedores.ver', ['/subcontractors']),
  ...con('proveedores.portal', ['/supplier-portal']),
  // Clientes internos (22-11-2026): cuadro de dirección y cargos (gestión) y portal «Mi departamento».
  ...con('interno.gestionar', ['/internal-clients']),
  ...con('interno.portal', ['/mi-departamento']),
  ...con('soporte.panel', ['/support-dashboard']),
  ...con('sd.ver', ['/service-desk']),
  ...con('sd.disenar_flujos', ['/sd/workflow-designer']),
  ...con('cmdb.ver', ['/cmdb', '/agent-dashboard']),
  ...con('alm.ver', ['/alm']),
  ...con('analitica.ver', [
    '/executive', '/data-explorer', '/report-builder', '/predictions', '/evm', '/portfolio', '/sprint-charts',
    '/cumulative-flow', '/risk-scores', '/projects/:id/analytics',
  ]),
  ...con('alertas.ver', ['/alerts']),
  ...con('exportar.ver', ['/exports']),
  ...con('datos.plataforma', ['/data-platform', '/data-governance']),
  ...con('ia.ver', ['/nexus-agent', '/oracle', '/automations', '/contracts-ai', '/sprint-planning']),
  ...con('ia.asignacion', ['/semantic-engine']),
  ...con('org.administrar', ['/chat/admin']),
]

/** La declaración de una ruta concreta (`/projects/7/analytics`), o undefined si no está declarada. */
export function rutaDeclarada(ruta: string): RutaDeclarada | undefined {
  const limpia = ruta.split(/[?#]/)[0]
  return RUTAS.find(r => matchPath({ path: r.patron, end: true }, limpia))
}

type Puede = (capacidad: Capacidad) => boolean

/**
 * ¿Abre esta persona la ruta? Declarada: según su capacidad. No declarada:
 * `noDeclarada` (las rutas protegidas de App.tsx están todas declaradas; lo
 * comprueba `permisos.test.ts`).
 */
export function puedeAbrir(ruta: string, puede: Puede, noDeclarada = false): boolean {
  const r = rutaDeclarada(ruta)
  if (!r) return noDeclarada
  return !r.capacidad || puede(r.capacidad)
}

/**
 * Página de inicio tras entrar: salud del portfolio para quien la ve (dirección,
 * PM, jefe de equipo), capacidad del equipo para quien gestiona personas (RRHH),
 * «Mi día» para el resto (empleado, externo).
 */
export function paginaDeInicio(puede: Puede): string {
  if (puede('proyectos.panel')) return '/projects-dashboard'
  if (puede('equipo.ver')) return '/team-dashboard'
  return '/work-dashboard'
}
