// Esquemas, tipos y utilidades compartidos por las pestañas del portal de cliente de un proyecto. 23-11-2026: troceado de ClientPortalPage sin cambio de comportamiento.
import type { ChangeEvent, CSSProperties } from 'react'
import { z } from 'zod'
import type { PortalPeticion, PortalSesionUat, PortalUsuario, WikiPaginaEnArbol } from '../services/api/tipos-alm'
import { SMALL_PAGE_SIZE } from '../constants/pagination'
import { type StatusConfig } from '../constants/sharedStatus'
import { useAppT } from '../i18n/AppLangContext'
import DsBadge from '../components/ui/StatusBadge'

type Traductor = ReturnType<typeof useAppT>

/** Color de datos (estado, severidad, prioridad...) → custom property que consumen las clases `.cpp-*`. */
export const colorVar = (color: string | undefined): CSSProperties => ({ '--cpp-color': color || 'var(--text-2)' } as CSSProperties)

/** Props de un campo con error: aria-invalid (lo pinta `.cpp-input`) + enlace al mensaje. */
export function propsDeError(errors: Record<string, string | undefined>, key: string, idBase: string) {
  return errors[key] ? { 'aria-invalid': true as const, 'aria-describedby': `${idBase}-err-${key}` } : {}
}

export function MensajeError({ errors, campo, idBase }: { errors: Record<string, string | undefined>; campo: string; idBase: string }) {
  return errors[campo] ? <p id={`${idBase}-err-${campo}`} className="u-field-error">{errors[campo]}</p> : null
}

// Esquemas construidos con el traductor activo: los mensajes salen en el idioma del usuario.
export function crearEsquemaUat(t: Traductor) {
  return z.object({
    title: z.string().trim().min(1, t('clientportalpage.err_titulo')),
    description: z.string().optional(),
    deliverable_id: z.string().optional(),
    test_environment: z.string().optional(),
    test_credentials: z.string().optional(),
    test_guide_url: z.string().optional(),
    available_from: z.string().optional(),
    deadline: z.string().optional(),
  }).superRefine((values, ctx) => {
    if (values.available_from && values.deadline && values.deadline < values.available_from) {
      ctx.addIssue({
        code: 'custom',
        path: ['deadline'],
        message: t('clientportalpage.err_fecha_limite'),
      })
    }
  })
}

export function crearEsquemaAltaCliente(t: Traductor) {
  return z.object({
    full_name: z.string().trim().min(1, t('clientportalpage.err_nombre')),
    email: z.string().trim().pipe(z.email(t('clientportalpage.err_email'))),
    job_title: z.string().optional(),
    company: z.string().optional(),
    phone: z.string().optional(),
    can_approve_deliverables: z.boolean(),
    can_request_changes: z.boolean(),
    can_view_budget: z.boolean(),
    can_view_team: z.boolean(),
  })
}

export function crearEsquemaEdicionCliente(t: Traductor) {
  return z.object({
    full_name: z.string().trim().min(1, t('clientportalpage.err_nombre')),
    email: z.string().trim().pipe(z.email(t('clientportalpage.err_email'))),
    job_title: z.string().optional(),
    company: z.string().optional(),
    phone: z.string().optional(),
    project_ids: z.array(z.union([z.string(), z.number()])),
    can_approve_deliverables: z.boolean(),
    can_request_changes: z.boolean(),
    can_view_budget: z.boolean(),
    can_view_team: z.boolean(),
  })
}

export type DatosAltaCliente = z.infer<ReturnType<typeof crearEsquemaAltaCliente>>

export type DatosEdicionCliente = z.infer<ReturnType<typeof crearEsquemaEdicionCliente>>

// STATUS_CFG y FR_STATUS_CFG centralizados en constants/sharedStatus.js

// ── Tipos de las respuestas del portal: services/api/tipos-alm ───────────────
export type ClientePortal = PortalUsuario

export type PermisoCliente = 'can_approve_deliverables' | 'can_request_changes' | 'can_view_budget' | 'can_view_team'

export type FormCliente = {
  full_name: string; email: string; job_title: string; company: string; phone: string
} & Record<PermisoCliente, boolean>

export type FormEdicionCliente = FormCliente & { project_ids: string[] }

export type EventoDeCampo = ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>

export type SesionUat = PortalSesionUat

export type FormUat = z.infer<ReturnType<typeof crearEsquemaUat>>

export type CasoNuevo = { title: string; steps: string; expected_result: string }

export type PeticionDeCambio = PortalPeticion

export type RespuestaPeticion = { pm_response: string; estimated_hours: string; estimated_cost: string; estimated_delivery_weeks: string; status: string }

export type FormDocumento = { title: string; description: string; category: string; file_url: string; file_name: string; requires_signature: boolean }

/** epics_service.serialize_page: el backend NO envía `visibility` ni tiene ruta para cambiarla
 *  (WikiPageIn no la acepta); el selector de visibilidad no puede funcionar sin ese cambio. */
/** El árbol de páginas en una lista (con su profundidad): la visibilidad se fija por página. */
export function aplanarPaginas(paginas: WikiPaginaEnArbol[], nivel = 0): Array<WikiPaginaEnArbol & { nivel: number }> {
  return paginas.flatMap(p => [{ ...p, nivel }, ...aplanarPaginas(p.children, nivel + 1)])
}

export function StatusBadge({ status, cfg }: { status: string; cfg: Record<string, StatusConfig> }) {
  const t = useAppT()
  const c = cfg[status]
  // La etiqueta sale de i18n (`clientportalpage.estado_<estado>`); sharedStatus solo aporta el color.
  if (!c) return <DsBadge color="var(--text-2)">{t('client_portal.unknown_status')}</DsBadge>
  return <DsBadge color={c.color}>{t(`clientportalpage.estado_${status}`)}</DsBadge>
}

// ── Client Users Management ───────────────────────────────────────────────────
/** Contactos del portal por página (#22: /portal/clients pagina con page/page_size). */
export const CONTACTOS_POR_PAGINA = SMALL_PAGE_SIZE
