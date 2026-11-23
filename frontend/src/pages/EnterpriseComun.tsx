// Formularios, tipos y utilidades compartidos por las pestañas de Enterprise. 23-11-2026: troceado de EnterprisePage sin cambio de comportamiento.
import type { IntegracionOAuth } from '../services/api/tipos'
import { CalendarDays, Github, KanbanSquare, MessageSquare, Plug, Receipt, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { SMALL_PAGE_SIZE } from '../constants/pagination'

export const GDPR_POR_PAGINA = SMALL_PAGE_SIZE

// ── Formularios (las respuestas van tipadas en services/api/tipos.ts) ───────
export interface WebhookForm { name: string; slug: string; workflow_id: string }

export interface GdprForm { request_type: string; subject_user_id: string; subject_email: string; notes: string }

export interface SendEmailForm { to: string; subject: string; body_html: string; template_id: string }

export interface NewTemplateForm { name: string; subject: string; body_html: string; category: string }

interface IntegrationField { key: string; label: string; type?: string; placeholder?: string }

export interface IntegrationCatalogEntry { type: string; label: string; icon: string; desc?: string; fields?: IntegrationField[] }

/** Fila de la lista: las de `integration_configs` y la conexión Jira de la empresa (sin `config`). */
export type OAuthIntegration = Pick<IntegracionOAuth, 'id' | 'name' | 'integration_type' | 'is_active' | 'last_sync_at'> & { config?: IntegracionOAuth['config'] }

export interface IntegrationForm { name: string; access_token?: string; config: Record<string, string>; integration_type?: string }

export const JIRA_ID = 'jira-config'

export interface ApiKeyForm { name: string; rate_limit_per_hour: number }

/** El formulario de alta de cada pestaña se abre desde la cabecera de la página. */
export interface AltaProps { showCreate: boolean; setShowCreate: (v: boolean) => void }

/** Icono de cada integración del catálogo (el catálogo trae emojis: no se pintan). */
const ICONO_INTEGRACION: Record<string, LucideIcon> = {
  slack: MessageSquare, teams: Users, jira: KanbanSquare, github: Github,
  google_calendar: CalendarDays, xero: Receipt, quickbooks: Receipt,
}

export const iconoIntegracion = (tipo?: string) => ICONO_INTEGRACION[tipo || ''] || Plug

/** Etiqueta de un código (`<prefijo>_<codigo>`); si no hay clave, el código tal cual. */
export const etiq = (t: (k: string, f?: string) => string, prefijo: string, codigo?: string | null) =>
  codigo ? t(`${prefijo}_${String(codigo).toLowerCase()}`, String(codigo)) : '—'
