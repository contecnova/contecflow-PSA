// Tipos, clases y hook compartidos por las secciones de ConfigTab. 23-11-2026: troceado de ConfigTab sin cambio de comportamiento.
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import type { TipoDeContenidoDelPortal } from '../../services/api/traduccion'
import { type SlaCalendar, type UserListItem } from '../../services/api'
import type { SdAnuncio, SdCategoriaDeCatalogo, SdGrupo, SdPlantillaDeTicket, SdPoliticaSla, SdRespuestaRapida, SdServicioDeCatalogo } from '../../services/api/tipos-sd'
import { PRIORITY_LABEL } from './sdUtils'

// ── Local types ─────────────────────────────────────────────────────────────
/** El servicio del catalogo; `category_id` lo pone la pantalla al editar (el backend no lo envia). */
export type Svc = SdServicioDeCatalogo & { category_id?: string }

export type Cat = SdCategoriaDeCatalogo

export type Policy = SdPoliticaSla

export type Calendario = SlaCalendar

export type Member = SdGrupo['members'][number]

export type Group = SdGrupo

// #24b: la lista de usuarios ya llega tipada desde usersApi (UserPublic).
export type User = UserListItem

/** Solo llegan las activas: desactivar una la saca de la lista (y no se puede reactivar). */
export type Template = SdPlantillaDeTicket

export type Canned = SdRespuestaRapida

export type CannedForm = { title: string; body: string; category: string; shortcut: string }

export type Ann = SdAnuncio

export const PRIORITY_LABEL_MAP = PRIORITY_LABEL as Record<string, string>

/** Clases de los formularios: el campo del sistema de diseño (`ds-input`). */
export const IS_BASE = 'ds-input sdcfg-input'

export const LS_BASE = 'sdcfg-label'

/** Lo que se está traduciendo (versiones en los idiomas del portal, 17-11-2026). */
export type Traduciendo = { tipo: TipoDeContenidoDelPortal; id: string; etiqueta: string }

/** Tras guardar un original con versiones: cuántas han quedado desactualizadas. */
export function useAvisoDeDesactualizadas() {
  const t = useAppT()
  const toast = useToast()
  return (n?: number) => { if (n && n > 0) toast.warning(t('traduccion_admin.portal_quedan_desactualizadas', { n })) }
}
