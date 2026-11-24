/**
 * Catálogo de Configuración (18-11-2026): la única lista de ajustes del operador.
 *
 * Antes la configuración estaba repartida en 23 pestañas de `/settings`, 20
 * pantallas sueltas del menú «Configuración» y pestañas «Configuración» dentro
 * de los módulos (Ausencias, Horas extra, Service desk; el 19-11-2026 también
 * Git, Entrada a la cartera, Asignación IA, informes de Microsoft 365 y las
 * herramientas Agente, Autorresolución y Voz del service desk). Ver
 * docs/CONFIGURACION.md (estructura nueva) y docs/CONFIGURACION_INVENTARIO.md
 * (estado medido antes de reorganizar).
 *
 * Cada sección:
 * - vive en `/settings/<id>` (la pinta `SettingsPage`, con navegación lateral
 *   agrupada y buscador);
 * - declara quién la ve con una `capacidad` de la matriz de permisos
 *   (`app/core/capacidades.py`, 19-11-2026; sin capacidad = cualquiera con
 *   sesión), alineada con lo que el backend deja escribir: una sección no
 *   aparece a quien recibiría 403;
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
import type { Capacidad } from '../../permisos/capacidades'

/** Props que reciben las secciones: la subpestaña pedida por `?sub=`. */
export type PropsDeSeccion = { subInicial?: string }
type Componente = LazyExoticComponent<ComponentType<PropsDeSeccion>>

export type GrupoDeAjustes = { id: string; icono: ReactNode }

export type SeccionDeAjustes = {
  id: string
  grupo: string
  /** Capacidad que abre la sección (sin ella: cualquiera con sesión). */
  capacidad?: Capacidad
  /** Ruta con la que se llegaba antes; App.tsx la redirige a `/settings/<id>`. */
  rutaAntigua?: string
  /** Componente que se pinta en el panel. */
  componente?: Componente
  /** Envolver con la tarjeta `SeccionDeAjustes` (título y descripción del catálogo). */
  envolver?: boolean
  /** En lugar de panel: herramienta a pantalla completa (se abre su ruta). */
  enlace?: string
}

const ADMIN: Capacidad = 'org.administrar'

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
  { id: 'setup', grupo: 'empresa', capacidad: ADMIN, componente: pagina(() => import('../settings-sections/PuestaEnMarchaSection')) },
  { id: 'general', grupo: 'empresa', capacidad: ADMIN, componente: seccionDe('GeneralSection') },
  { id: 'branding', grupo: 'empresa', capacidad: ADMIN, componente: pagina(() => import('../settings-sections/MarcaSection')) },
  { id: 'offices', grupo: 'empresa', capacidad: ADMIN, componente: seccionDe('OfficesSection') },
  { id: 'depts', grupo: 'empresa', capacidad: 'personas.config', componente: seccionDe('DepartmentsSection') },
  { id: 'numbering', grupo: 'empresa', capacidad: ADMIN, componente: seccionDe('NumberingSection') },
  { id: 'organizations', grupo: 'empresa', capacidad: 'plataforma.empresas', rutaAntigua: '/organizations', componente: pagina(() => import('../OrganizationsPage')) },

  // Personas y jornada
  { id: 'users', grupo: 'personas', capacidad: 'personas.config', componente: seccionDe('UsersSection') },
  { id: 'roles', grupo: 'personas', capacidad: ADMIN, componente: seccionDe('RolesSection') },
  // 23-11-2026 (menú personalizable): orden de categorías y pestañas ocultas del menú lateral por rol (auditado).
  { id: 'menu-por-defecto', grupo: 'personas', capacidad: ADMIN, envolver: true, componente: pagina(() => import('../settings-sections/MenuPorDefectoSection')) },
  { id: 'ausencias', grupo: 'personas', capacidad: 'ausencias.config', envolver: true, componente: pagina(() => import('../../components/ausencias/admin/AdminDeAusencias')) },
  // 19-11-2026: también el máximo asignable (VACATION_MAX_DAYS_ENTITLED, grupo locale; sólo admin lo edita).
  { id: 'vacations', grupo: 'personas', capacidad: 'personas.config', componente: seccionDe('VacationSection') },
  { id: 'horas-extra', grupo: 'personas', capacidad: 'horas_extra.config', envolver: true, componente: pagina(() => import('../../components/horas-extra/ConfigHorasExtra')) },
  // 23-11-2026: «Mi cuaderno» — etiquetas por defecto, plantillas, baja, papelera, IA, voz y acceso excepcional (docs/CUADERNO.md).
  { id: 'cuaderno', grupo: 'personas', capacidad: 'cuaderno.config', envolver: true, componente: pagina(() => import('../../components/cuaderno/ConfigCuaderno')) },

  // Proyectos y trabajo
  // 19-11-2026: tipos de proyecto, sectores y categorías de gasto (antes enums cerrados de la BD).
  { id: 'catalogos', grupo: 'proyectos', capacidad: 'proyectos.config', componente: pagina(() => import('./CatalogosDeClave')) },
  { id: 'project-templates', grupo: 'proyectos', capacidad: 'proyectos.config', rutaAntigua: '/project-templates', componente: pagina(() => import('../ProjectTemplatesPage')) },
  { id: 'issue-types', grupo: 'proyectos', capacidad: 'proyectos.config', rutaAntigua: '/issue-types', componente: pagina(() => import('../IssueTypesPage')) },
  { id: 'project-workflows', grupo: 'proyectos', capacidad: 'proyectos.config', componente: pagina(() => import('../WorkflowsPage')) },
  { id: 'custom-fields', grupo: 'proyectos', capacidad: 'proyectos.config', rutaAntigua: '/custom-fields', componente: pagina(() => import('./CamposPersonalizados')) },
  { id: 'project-permissions', grupo: 'proyectos', capacidad: 'proyectos.config', rutaAntigua: '/project-permissions', componente: pagina(() => import('../ProjectPermissionsPage')) },
  // 19-11-2026: antes pestaña «Configuración» de /portfolio/intake (escritura require_admin_or_pm).
  { id: 'cartera', grupo: 'proyectos', capacidad: 'cartera.gestionar', envolver: true, componente: pagina(() => import('../../components/cartera/ConfigCartera')) },

  // Service desk (las escrituras son require_admin salvo las respuestas rápidas, require_any_manager)
  // 19-11-2026: la rampa y los minutos del despliegue canario (CHANGE_CANARY_*) van en Escalado y avisos (grupo service_desk).
  { id: 'sd', grupo: 'servicedesk', capacidad: 'sd.config', envolver: true, componente: pagina(() => import('../service-desk/ConfigTab')) },
  { id: 'sla-calendars', grupo: 'servicedesk', capacidad: 'sd.disenar_flujos', rutaAntigua: '/sla-calendars', componente: pagina(() => import('../SLACalendarsPage')) },
  { id: 'sd-workflows', grupo: 'servicedesk', capacidad: 'sd.disenar_flujos', enlace: '/sd/workflow-designer' },
  // 19-11-2026: antes pestañas/tarjetas «Configuración» de Service desk → Herramientas (escritura require_admin).
  { id: 'sd-agente', grupo: 'servicedesk', capacidad: 'sd.administrar', envolver: true, componente: pagina(() => import('../../components/servicedesk/ConfigAgenteAutonomo')) },
  { id: 'sd-autorresolucion', grupo: 'servicedesk', capacidad: 'sd.administrar', envolver: true, componente: pagina(() => import('../../components/servicedesk/ConfigAutoResolucion')) },
  { id: 'sd-voz', grupo: 'servicedesk', capacidad: 'sd.administrar', envolver: true, componente: pagina(() => import('../../components/servicedesk/ConfigAgenteDeVoz')) },
  // 23-11-2026 (A-SD19): catálogo de cambios estándar preaprobados por el CAB.
  { id: 'sd-cambios-estandar', grupo: 'servicedesk', capacidad: 'sd.gestionar', envolver: true, componente: pagina(() => import('../../components/servicedesk/CatalogoDeCambiosEstandar')) },
  // Migración 206 (docs/PIR.md): revisión posterior a la implantación de cambios y proyectos.
  { id: 'pir', grupo: 'servicedesk', capacidad: 'pir.administrar', envolver: true, componente: pagina(() => import('../../components/pir/ConfigPir')) },
  // 19-11-2026: CMDB de software y vulnerabilidades (fuentes de avisos, credenciales, plazos, licencias).
  { id: 'cmdb-software', grupo: 'servicedesk', capacidad: 'software.config', envolver: true, componente: pagina(() => import('../../components/cmdb/software/ConfigSoftware')) },

  // Finanzas
  { id: 'rates', grupo: 'finanzas', capacidad: 'tarifas.config', rutaAntigua: '/rate-cards', componente: pagina(() => import('../RateCardsPage')) },
  { id: 'user-costs', grupo: 'finanzas', capacidad: 'costes.config', rutaAntigua: '/user-costs', componente: pagina(() => import('../UserCostsPage')) },
  // 19-11-2026 (migración 189): plantillas de contrato, tipos de servicio, unidades de cobro y umbrales de proveedores.
  { id: 'proveedores', grupo: 'finanzas', capacidad: 'proveedores.config', componente: pagina(() => import('../proveedores/ConfigProveedores')) },
  // 22-11-2026: clientes internos — servicios compartidos y criterios de reparto (docs/CLIENTES_INTERNOS.md §4).
  { id: 'clientes-internos', grupo: 'finanzas', capacidad: 'interno.cargos', componente: pagina(() => import('../internos/ConfigClientesInternos')) },

  // Aprobaciones y políticas (escritura: require_admin en los dos)
  { id: 'approval-workflows', grupo: 'aprobaciones', capacidad: ADMIN, componente: FlujosDeAprobacion },
  { id: 'policies', grupo: 'aprobaciones', capacidad: ADMIN, componente: pagina(() => import('../PoliticasPage')) },
  // 22-11-2026: tipos de solicitud y flujos de demanda (docs/FLUJO_DE_DEMANDA.md).
  { id: 'demanda', grupo: 'aprobaciones', capacidad: 'demanda.config', envolver: true, componente: pagina(() => import('../../components/demanda/ConfigDemanda')) },

  // IA e idiomas
  { id: 'ai-hub', grupo: 'ia', capacidad: ADMIN, rutaAntigua: '/ai-hub', componente: pagina(() => import('../AIHubPage')) },
  { id: 'ai-governance', grupo: 'ia', capacidad: ADMIN, rutaAntigua: '/governance', componente: pagina(() => import('../GovernancePage')) },
  { id: 'idiomas', grupo: 'ia', capacidad: ADMIN, componente: seccionDe('IdiomasSection') },
  { id: 'traduccion', grupo: 'ia', capacidad: ADMIN, componente: pagina(() => import('../settings-sections/TraduccionSection')) },
  // 19-11-2026: antes pestaña «Configuración» de /semantic-engine (escritura admin y RRHH).
  { id: 'ia-asignacion', grupo: 'ia', capacidad: 'ia.asignacion_config', envolver: true, componente: pagina(() => import('../../components/asignacion-ia/ConfigMotorSemantico')) },
  // 19-11-2026: asistente de reuniones (consentimiento, retención, Teams/Zoom/Meet, bot y RGPD por persona).
  { id: 'reuniones', grupo: 'ia', capacidad: 'reuniones.config', envolver: true, componente: pagina(() => import('../../components/reuniones/ConfigReuniones')) },

  // Integraciones
  { id: 'integrations', grupo: 'integraciones', capacidad: ADMIN, componente: seccionDe('IntegrationCredentialsSection') },
  { id: 'esign', grupo: 'integraciones', capacidad: ADMIN, componente: seccionDe('ESignSettingsSection') },
  // 23-11-2026 (A4 del 04b): las fuentes de uso de licencias (credenciales, prueba,
  // sincronización, mapeo) estaban dentro de ALM → Uso real; la configuración vive aquí.
  { id: 'alm-fuentes', grupo: 'integraciones', capacidad: ADMIN, envolver: true, componente: pagina(() => import('../alm/uso/FuentesPanel')) },
  { id: 'm365', grupo: 'integraciones', capacidad: ADMIN, rutaAntigua: '/m365', componente: pagina(() => import('../M365Page')) },
  // 19-11-2026: antes pestaña «Configuración» del panel Office 365 de la Plataforma de datos.
  // No se unifica con `m365`: aquella usa variables de entorno de la instalación (calendario, Teams);
  // esta guarda credenciales de Graph por empresa para los informes de uso (bi_o365_service).
  { id: 'm365-informes', grupo: 'integraciones', capacidad: ADMIN, envolver: true, componente: pagina(() => import('../../components/bi/ConfigBiO365')) },
  // 19-11-2026: antes pestaña «Configuración» de /git (solo lectura; GET /git/webhooks es require_admin_or_pm).
  { id: 'git', grupo: 'integraciones', capacidad: 'proyectos.gobierno', envolver: true, componente: pagina(() => import('../../components/git/ConfigGit')) },
  { id: 'jira', grupo: 'integraciones', capacidad: ADMIN, rutaAntigua: '/jira-integration', componente: pagina(() => import('../JiraIntegrationPage')) },
  { id: 'enterprise', grupo: 'integraciones', capacidad: ADMIN, rutaAntigua: '/enterprise', componente: pagina(() => import('../EnterprisePage')) },
  { id: 'webhook-log', grupo: 'integraciones', capacidad: ADMIN, rutaAntigua: '/webhook-log', componente: pagina(() => import('../WebhookLogPage')) },
  { id: 'developer', grupo: 'integraciones', capacidad: 'integraciones.desarrollo', rutaAntigua: '/developer', componente: pagina(() => import('../DeveloperPortalPage')) },
  // 23-11-2026 (docs/integraciones/MCP.md): agentes de código (OpenCode, Claude Code) por MCP: estado de la
  // empresa (lo cambia `gobierno.administrar`), cómo conectar, credenciales propias y herramientas disponibles.
  { id: 'mcp', grupo: 'integraciones', capacidad: 'mcp.usar', envolver: true, componente: pagina(() => import('../../components/mcp/ConfigMcp')) },
  // 23-11-2026 (migración 203, docs/integraciones/TICKET_A_PR.md): «Del ticket al PR» — módulo, motor y modelo,
  // credenciales Git cifradas, repositorios por proyecto, seguridad, límites, plantillas, prueba y coste.
  { id: 'ticket-a-pr', grupo: 'integraciones', capacidad: 'ticket_pr.config', envolver: true, componente: pagina(() => import('../../components/ticket-a-pr/ConfigTicketAPr')) },
  { id: 'import', grupo: 'integraciones', capacidad: 'integraciones.desarrollo', rutaAntigua: '/import', componente: pagina(() => import('../ImportPage')) },

  // Seguridad y GRC
  // 23-11-2026 (docs/seguridad/politicas_de_cuenta.md): políticas de cuenta (contraseñas, bloqueo, MFA,
  // sesiones —incluida la inactividad, que era la sección «session»—, acceso), usuarios, sesiones,
  // aprobaciones con segundo administrador y campañas de recertificación.
  { id: 'seguridad-cuentas', grupo: 'seguridad', capacidad: 'seguridad.administrar', componente: pagina(() => import('../settings-sections/SeguridadDeCuentasSection')) },
  { id: 'recertificacion', grupo: 'seguridad', capacidad: 'seguridad.recertificar', componente: pagina(() => import('../settings-sections/RecertificacionSection')) },
  { id: 'mfa', grupo: 'seguridad', rutaAntigua: '/mfa', componente: pagina(() => import('../MFAPage')) },
  { id: 'grc', grupo: 'seguridad', capacidad: ADMIN, rutaAntigua: '/grc', componente: pagina(() => import('../GrcPage')) },
  // Migración 212 (docs/CERTIFICACIONES.md): avisos, caducidad de evidencias, acceso de auditores, NIS2 y CAPA.
  { id: 'certificaciones', grupo: 'seguridad', capacidad: 'certificaciones.administrar', envolver: true, componente: pagina(() => import('../../components/certificaciones/ConfigCertificaciones')) },
  // 19-11-2026: también los meses de retención propuestos (CHAT_RETENTION_PROPOSED_MONTHS, grupo audit).
  { id: 'chat-admin', grupo: 'seguridad', capacidad: ADMIN, componente: pagina(() => import('../ChatAdminPage')) },

  // Portal de clientes
  { id: 'public-forms', grupo: 'portal', capacidad: 'portal.formularios', rutaAntigua: '/public-forms', componente: pagina(() => import('../PublicFormsPage')) },
  { id: 'portal-translations', grupo: 'portal', capacidad: ADMIN, envolver: true, componente: pagina(() => import('../../components/traduccion/RevisionDeContenidoDelPortal')) },
  // 24-11-2026 (docs/portal/CHAT_DEL_PORTAL.md): llamadas, vídeo, adjuntos y plazos del chat del portal (grupo `portal_chat`).
  { id: 'portal-chat', grupo: 'portal', capacidad: ADMIN, envolver: true, componente: pagina(() => import('../../components/portal/AjustesDelChatDelPortal')) },

  // Alertas y métricas
  { id: 'alert-config', grupo: 'alertas', capacidad: ADMIN, componente: seccionDe('AlertConfigSection') },
  { id: 'metrics', grupo: 'alertas', capacidad: ADMIN, componente: seccionDe('MetricsSection') },

  // Sistema
  // 19-11-2026: los plazos de evaluaciones de desempeño (PERF_*) están en su pestaña Automatizaciones.
  { id: 'runtime-flags', grupo: 'sistema', capacidad: ADMIN, componente: seccionDe('RuntimeFlagsSection') },
  { id: 'log-level', grupo: 'sistema', capacidad: ADMIN, componente: seccionDe('LogLevelSection') },
  { id: 'system-state', grupo: 'sistema', capacidad: ADMIN, componente: seccionDe('SystemStateSection') },
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
  // 23-11-2026: la inactividad vive en Seguridad de cuentas › Sesiones.
  session: 'seguridad-cuentas',
}

/** Clave i18n de una sección (`ajustes.s_<id>`). */
export const claveDeSeccion = (id: string) => `ajustes.s_${id.replace(/-/g, '_')}`

type Quien = { puede: (c: Capacidad) => boolean; canOpen: (ruta: string) => boolean }

/** ¿Puede esta persona usar la sección? Capacidad (superadmin incluido) y bloqueo por ruta (nueva y antigua). */
export function puedeVerSeccion(s: SeccionDeAjustes, q: Quien): boolean {
  if (s.capacidad && !q.puede(s.capacidad)) return false
  if (!q.canOpen(`/settings/${s.id}`)) return false
  if (s.rutaAntigua && !q.canOpen(s.rutaAntigua)) return false
  if (s.enlace && !q.canOpen(s.enlace)) return false
  return true
}

