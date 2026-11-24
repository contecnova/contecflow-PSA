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
 *
 * Auditoría 22-11-2026 (M16), 23-11-2026: cada ruta pide la capacidad que exige
 * la API que carga (`app/core/capacidades.py` + guardas de los endpoints):
 * /bpm → `bpm.usar`, /agent-dashboard → `cmdb.gestionar`, /portfolio/intake →
 * `cartera.usar`; /reports se queda en `colaboracion.ver` (API abierta a
 * cualquiera con sesión).
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
    '/skills', '/training',
    // M16 (23-11-2026): /reports se queda aquí a propósito: su API (`/analytics/catalogue|query`) la abre
    // cualquiera con sesión y `colaboracion.ver` (internos) dice «…informes». La pestaña de programados
    // se ve solo con `informes.programar` (ReportsPage).
    '/reports',
  ]),
  // M16: la API del intake de cartera es `cartera.usar` (proponer) / `cartera.gestionar` (decidir).
  ...con('cartera.usar', ['/portfolio/intake']),
  ...con('gastos.ver', ['/expenses']),
  // Flujo de demanda (22-11-2026): «Mis solicitudes» es para cualquiera con sesión; las vistas de gestión las acota el servidor (demanda.ver).
  ...con(undefined, ['/demand']),
  ...con('proyectos.trabajo', [
    '/lessons', '/sprints', '/raci', '/changelog', '/uat', '/gantt', '/epic-gantt', '/epics', '/dependencies',
  ]),
  // Asistente de reuniones (19-11-2026): antes con `proyectos.trabajo`.
  ...con('reuniones.usar', ['/meetings-ai']),
  // «Mi cuaderno» (migración 202): cada persona con acceso a gestión (no el portal de clientes).
  ...con('cuaderno.usar', ['/notebook']),
  // Revisiones posteriores a la implantación (migración 206): las mías, todas (acotadas) e informes.
  ...con('pir.ver', ['/pir']),
  ...con('proyectos.panel', ['/projects-dashboard']),
  ...con('proyectos.gobierno', ['/deliverables', '/changes', '/risks', '/git', '/esign']),
  ...con('equipo.ver', ['/team-dashboard', '/resources/planning', '/alm/altas-y-bajas']),
  ...con('recursos.ver', ['/resources', '/capacity', '/org-chart', '/okrs', '/performance-reviews']),
  ...con('recursos.prevision', ['/resource-forecast', '/resource-scheduler']),
  // M16: la API de procesos e instancias BPMN es `bpm.usar` (catálogo, bandeja) / `bpm.gestionar` (editar).
  ...con('bpm.usar', ['/bpm']),
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
  ...con('cmdb.ver', ['/cmdb']),
  // M16: `GET /cmdb/agent-dashboard/{id}` exige `cmdb.gestionar`; con `cmdb.ver` la pantalla abría y daba 403.
  ...con('cmdb.gestionar', ['/agent-dashboard']),
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
