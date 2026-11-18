/**
 * Catálogo de Configuración (18-11-2026): la única lista de ajustes del operador.
 *
 * Antes la configuración estaba repartida en 23 pestañas de `/settings`, 20
 * pantallas sueltas del menú «Configuración» y pestañas «Configuración» dentro
 * de los módulos (Ausencias, Horas extra, Service desk). Ver
 * docs/CONFIGURACION.md (estructura nueva) y docs/CONFIGURACION_INVENTARIO.md
 * (estado medido antes de reorganizar).
 *
 * Cada sección:
 * - vive en `/settings/<id>` (la pinta `SettingsPage`, con navegación lateral
 *   agrupada y buscador);
 * - declara quién la ve (`roles`, y `soloSuperadmin`), alineado con lo que el
 *   backend deja escribir: una sección no aparece a quien recibiría 403;
 * - si antes tenía ruta propia (`rutaAntigua`), esa ruta redirige aquí
 *   (`<Navigate replace>` en App.tsx) y el bloqueo por ruta del usuario
 *   (`blocked_routes`) se sigue respetando con la ruta antigua;
 * - o es un `enlace` a una herramienta a pantalla completa (diseñador gráfico)
 *   que no cabe en el panel.
 *
 * Textos: `ajustes.g_<grupo>`, `ajustes.s_<id>` y `ajustes.s_<id>_d` (id con
 * guiones bajos) en i18n/langs/{es,en,zh}.mjs. La descripción incluye los
 * subapartados para que el buscador los encuentre.
 */
import { lazy } from 'react'
import type { ComponentType, LazyExoticComponent, ReactNode } from 'react'
import {
  Bell, Brain, Building2, FolderKanban, Globe, LifeBuoy, Plug, Scale, Server, ShieldCheck, Users, Wallet,
} from 'lucide-react'
import type { Role } from '../../context/AuthContext'

/** Props que reciben las secciones: la subpestaña pedida por `?sub=`. */
export type PropsDeSeccion = { subInicial?: string }
type Componente = LazyExoticComponent<ComponentType<PropsDeSeccion>>

export type GrupoDeAjustes = { id: string; icono: ReactNode }

export type SeccionDeAjustes = {
  id: string
  grupo: string
  roles: Role[]
  /** Solo el superadmin (gestión de empresas de la plataforma). */
  soloSuperadmin?: boolean
  /** Ruta con la que se llegaba antes; App.tsx la redirige a `/settings/<id>`. */
  rutaAntigua?: string
  /** Componente que se pinta en el panel. */
  componente?: Componente
  /** Envolver con la tarjeta `SeccionDeAjustes` (título y descripción del catálogo). */
  envolver?: boolean
  /** En lugar de panel: herramienta a pantalla completa (se abre su ruta). */
  enlace?: string
}

const TODOS: Role[] = ['admin', 'pm', 'team_lead', 'hr', 'employee', 'subcontractor']
const ADMIN: Role[] = ['admin']
const ADMIN_RRHH: Role[] = ['admin', 'hr']
const ADMIN_PM: Role[] = ['admin', 'pm']

// Un `lazy` por export con nombre: cada sección carga su código al abrirse.
const seccionDe = (k: string): Componente =>
  lazy(() => import('../SettingsPageSections').then(m => ({ default: (m as unknown as Record<string, ComponentType<PropsDeSeccion>>)[k] })))
const pagina = (cargar: () => Promise<{ default: ComponentType<never> }>): Componente =>
  lazy(cargar as unknown as () => Promise<{ default: ComponentType<PropsDeSeccion> }>)

/** Aprobaciones en modo configuración (el mismo componente sirve la bandeja). */
const FlujosDeAprobacion = lazy(() => import('../ApprovalsPage').then(m => {
  const Paginas = m.default
  return { default: () => <Paginas mode="config" /> }
}))

export const GRUPOS_DE_AJUSTES: GrupoDeAjustes[] = [
  { id: 'empresa', icono: <Building2 size={15} /> },
  { id: 'personas', icono: <Users size={15} /> },
  { id: 'proyectos', icono: <FolderKanban size={15} /> },
  { id: 'servicedesk', icono: <LifeBuoy size={15} /> },
  { id: 'finanzas', icono: <Wallet size={15} /> },
  { id: 'aprobaciones', icono: <Scale size={15} /> },
  { id: 'ia', icono: <Brain size={15} /> },
  { id: 'integraciones', icono: <Plug size={15} /> },
  { id: 'seguridad', icono: <ShieldCheck size={15} /> },
  { id: 'portal', icono: <Globe size={15} /> },
  { id: 'alertas', icono: <Bell size={15} /> },
  { id: 'sistema', icono: <Server size={15} /> },
]

export const SECCIONES_DE_AJUSTES: SeccionDeAjustes[] = [
  // Empresa y marca
  { id: 'setup', grupo: 'empresa', roles: ADMIN, componente: pagina(() => import('../settings-sections/PuestaEnMarchaSection')) },
  { id: 'general', grupo: 'empresa', roles: ADMIN, componente: seccionDe('GeneralSection') },
  { id: 'branding', grupo: 'empresa', roles: ADMIN, componente: pagina(() => import('../settings-sections/MarcaSection')) },
  { id: 'offices', grupo: 'empresa', roles: ADMIN, componente: seccionDe('OfficesSection') },
  { id: 'depts', grupo: 'empresa', roles: ADMIN_RRHH, componente: seccionDe('DepartmentsSection') },
  { id: 'numbering', grupo: 'empresa', roles: ADMIN, componente: seccionDe('NumberingSection') },
  { id: 'organizations', grupo: 'empresa', roles: ADMIN, soloSuperadmin: true, rutaAntigua: '/organizations', componente: pagina(() => import('../OrganizationsPage')) },

  // Personas y jornada
  { id: 'users', grupo: 'personas', roles: ADMIN_RRHH, componente: seccionDe('UsersSection') },
  { id: 'roles', grupo: 'personas', roles: ADMIN, componente: seccionDe('RolesSection') },
  { id: 'ausencias', grupo: 'personas', roles: ADMIN_RRHH, envolver: true, componente: pagina(() => import('../../components/ausencias/admin/AdminDeAusencias')) },
  { id: 'vacations', grupo: 'personas', roles: ADMIN_RRHH, componente: seccionDe('VacationSection') },
  { id: 'horas-extra', grupo: 'personas', roles: ADMIN_RRHH, envolver: true, componente: pagina(() => import('../../components/horas-extra/ConfigHorasExtra')) },

  // Proyectos y trabajo
  { id: 'project-templates', grupo: 'proyectos', roles: ADMIN_PM, rutaAntigua: '/project-templates', componente: pagina(() => import('../ProjectTemplatesPage')) },
  { id: 'issue-types', grupo: 'proyectos', roles: ADMIN_PM, rutaAntigua: '/issue-types', componente: pagina(() => import('../IssueTypesPage')) },
  { id: 'project-workflows', grupo: 'proyectos', roles: ADMIN_PM, componente: pagina(() => import('../WorkflowsPage')) },
  { id: 'custom-fields', grupo: 'proyectos', roles: ADMIN_PM, rutaAntigua: '/custom-fields', componente: pagina(() => import('./CamposPersonalizados')) },
  { id: 'project-permissions', grupo: 'proyectos', roles: ADMIN_PM, rutaAntigua: '/project-permissions', componente: pagina(() => import('../ProjectPermissionsPage')) },

  // Service desk (las escrituras son require_admin salvo las respuestas rápidas, require_any_manager)
  { id: 'sd', grupo: 'servicedesk', roles: ['admin', 'pm', 'team_lead', 'hr'], envolver: true, componente: pagina(() => import('../service-desk/ConfigTab')) },
  { id: 'sla-calendars', grupo: 'servicedesk', roles: ADMIN_PM, rutaAntigua: '/sla-calendars', componente: pagina(() => import('../SLACalendarsPage')) },
  { id: 'sd-workflows', grupo: 'servicedesk', roles: ADMIN_PM, enlace: '/sd/workflow-designer' },

  // Finanzas
  { id: 'rates', grupo: 'finanzas', roles: ADMIN_PM, rutaAntigua: '/rate-cards', componente: pagina(() => import('../RateCardsPage')) },
  { id: 'user-costs', grupo: 'finanzas', roles: ADMIN_RRHH, rutaAntigua: '/user-costs', componente: pagina(() => import('../UserCostsPage')) },

  // Aprobaciones y políticas (escritura: require_admin en los dos)
  { id: 'approval-workflows', grupo: 'aprobaciones', roles: ADMIN, componente: FlujosDeAprobacion },
  { id: 'policies', grupo: 'aprobaciones', roles: ADMIN, componente: pagina(() => import('../PoliticasPage')) },

  // IA e idiomas
  { id: 'ai-hub', grupo: 'ia', roles: ADMIN, rutaAntigua: '/ai-hub', componente: pagina(() => import('../AIHubPage')) },
  { id: 'ai-governance', grupo: 'ia', roles: ADMIN, rutaAntigua: '/governance', componente: pagina(() => import('../GovernancePage')) },
  { id: 'idiomas', grupo: 'ia', roles: ADMIN, componente: seccionDe('IdiomasSection') },
  { id: 'traduccion', grupo: 'ia', roles: ADMIN, componente: pagina(() => import('../settings-sections/TraduccionSection')) },

  // Integraciones
  { id: 'integrations', grupo: 'integraciones', roles: ADMIN, componente: seccionDe('IntegrationCredentialsSection') },
  { id: 'esign', grupo: 'integraciones', roles: ADMIN, componente: seccionDe('ESignSettingsSection') },
  { id: 'm365', grupo: 'integraciones', roles: ADMIN, rutaAntigua: '/m365', componente: pagina(() => import('../M365Page')) },
  { id: 'jira', grupo: 'integraciones', roles: ADMIN, rutaAntigua: '/jira-integration', componente: pagina(() => import('../JiraIntegrationPage')) },
  { id: 'enterprise', grupo: 'integraciones', roles: ADMIN, rutaAntigua: '/enterprise', componente: pagina(() => import('../EnterprisePage')) },
  { id: 'webhook-log', grupo: 'integraciones', roles: ADMIN, rutaAntigua: '/webhook-log', componente: pagina(() => import('../WebhookLogPage')) },
  { id: 'developer', grupo: 'integraciones', roles: ADMIN_PM, rutaAntigua: '/developer', componente: pagina(() => import('../DeveloperPortalPage')) },
  { id: 'import', grupo: 'integraciones', roles: ADMIN_PM, rutaAntigua: '/import', componente: pagina(() => import('../ImportPage')) },

  // Seguridad y GRC
  { id: 'session', grupo: 'seguridad', roles: ADMIN, componente: seccionDe('SessionSecuritySection') },
  { id: 'mfa', grupo: 'seguridad', roles: TODOS, rutaAntigua: '/mfa', componente: pagina(() => import('../MFAPage')) },
  { id: 'grc', grupo: 'seguridad', roles: ADMIN, rutaAntigua: '/grc', componente: pagina(() => import('../GrcPage')) },
  { id: 'chat-admin', grupo: 'seguridad', roles: ADMIN, componente: pagina(() => import('../ChatAdminPage')) },

  // Portal de clientes
  { id: 'public-forms', grupo: 'portal', roles: ADMIN_PM, rutaAntigua: '/public-forms', componente: pagina(() => import('../PublicFormsPage')) },
  { id: 'portal-translations', grupo: 'portal', roles: ADMIN, envolver: true, componente: pagina(() => import('../../components/traduccion/RevisionDeContenidoDelPortal')) },

  // Alertas y métricas
  { id: 'alert-config', grupo: 'alertas', roles: ADMIN, componente: seccionDe('AlertConfigSection') },
  { id: 'metrics', grupo: 'alertas', roles: ADMIN, componente: seccionDe('MetricsSection') },

  // Sistema
  { id: 'runtime-flags', grupo: 'sistema', roles: ADMIN, componente: seccionDe('RuntimeFlagsSection') },
  { id: 'log-level', grupo: 'sistema', roles: ADMIN, componente: seccionDe('LogLevelSection') },
  { id: 'system-state', grupo: 'sistema', roles: ADMIN, componente: seccionDe('SystemStateSection') },
]

/**
 * Ids de antes que ya no son una sección propia → a dónde van ahora
 * (`/settings?tab=<viejo>` y `/settings/<viejo>`). Duplicados quitados:
 * - `task-types`: tabla `task_types` que no leía nadie; las tareas usan los
 *   tipos de incidencia por proyecto.
 * - `email-inbound`: la misma pantalla que Service desk → Correo entrante.
 * - `fields`: Campos personalizados (globales y por proyecto, una sección).
 */
export const IDS_ANTIGUOS: Record<string, string> = {
  'task-types': 'issue-types',
  'email-inbound': 'sd?sub=mail',
  fields: 'custom-fields',
  'workflows': 'project-workflows',
}

/** Clave i18n de una sección (`ajustes.s_<id>`). */
export const claveDeSeccion = (id: string) => `ajustes.s_${id.replace(/-/g, '_')}`

type Quien = { hasRole: (...r: Role[]) => boolean; esSuperadmin: boolean; canOpen: (ruta: string) => boolean }

/** ¿Puede esta persona usar la sección? Rol, superadmin y bloqueo por ruta (nueva y antigua). */
export function puedeVerSeccion(s: SeccionDeAjustes, q: Quien): boolean {
  if (!q.hasRole(...s.roles)) return false
  if (s.soloSuperadmin && !q.esSuperadmin) return false
  if (!q.canOpen(`/settings/${s.id}`)) return false
  if (s.rutaAntigua && !q.canOpen(s.rutaAntigua)) return false
  if (s.enlace && !q.canOpen(s.enlace)) return false
  return true
}

/** Roles que ven al menos una sección (para el menú y la ruta). */
export const ROLES_CON_AJUSTES: Role[] = Array.from(new Set(SECCIONES_DE_AJUSTES.flatMap(s => s.roles)))
