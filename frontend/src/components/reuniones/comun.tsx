/**
 * Piezas comunes del asistente de reuniones (19-11-2026): tono y texto de
 * estado y origen, marca `mm:ss`, tamaños y claves de React Query.
 */
import { StatusBadge } from '../ui'
import type { StatusBadgeKind } from '../ui'
import type { EstadoReunion, OrigenReunion } from '../../services/api/reuniones'
import { ESTADOS_EN_CURSO } from '../../services/api/reuniones'
import { useAppT } from '../../i18n/AppLangContext'

export const TONO_DE_ESTADO: Record<EstadoReunion, StatusBadgeKind> = {
  programada: 'neutral',
  bot_unido: 'info',
  grabando: 'danger',
  procesando: 'accent',
  esperando_consentimiento: 'warning',
  lista: 'success',
  error: 'danger',
}

/** Claves de React Query del asistente (una sola fuente para invalidar). */
export const CLAVES = {
  lista: ['reuniones'] as const,
  detalle: (id: string) => ['reunion', id] as const,
  audio: (id: string) => ['reunion-audio', id] as const,
  preferencias: ['reuniones-preferencias'] as const,
  config: ['reuniones-config'] as const,
}

/** Mientras la reunión cambia sola (bot, grabación, análisis) se refresca. */
export const REFRESCO_EN_CURSO_MS = 5000
export const enCurso = (estado?: EstadoReunion | null) => !!estado && ESTADOS_EN_CURSO.includes(estado)

/** Milisegundos → `mm:ss` (o `h:mm:ss` pasada la hora). */
export function mmss(ms: number | null | undefined): string {
  const total = Math.max(0, Math.floor((ms ?? 0) / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const dos = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${dos(m)}:${dos(s)}` : `${dos(m)}:${dos(s)}`
}

/** Bytes legibles (KB / MB). */
export function tamano(bytes: number | null | undefined): string {
  const b = bytes ?? 0
  if (b >= 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.max(1, Math.round(b / 1024))} KB`
}

export function EstadoDeReunion({ estado }: { estado: EstadoReunion }) {
  const t = useAppT()
  return <StatusBadge kind={TONO_DE_ESTADO[estado] ?? 'neutral'} dot caps={false}>{t(`reuniones.estado.${estado}`)}</StatusBadge>
}

export function OrigenDeReunion({ origen }: { origen: OrigenReunion }) {
  const t = useAppT()
  return <StatusBadge kind="neutral" outline caps={false}>{t(`reuniones.origen.${origen}`)}</StatusBadge>
}
