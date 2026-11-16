/**
 * Piezas comunes de la integración de licencias y hardware (fase 4): traducción
 * de errores y estados del backend, y la pastilla de estado.
 */
import { StatusBadge } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { extractErr } from '../../utils/helpers'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'

type T = (clave: string, segundo?: string | Record<string, unknown>) => string

/** Mensaje de un error del backend: los códigos `almint_*` (fase 4) y `alm_*`
 *  (fases 1 y 3) se traducen; cualquier otro texto se enseña tal cual. */
export function mensajeDeError(t: T, e: unknown): string {
  const detalle = extractErr(e, '')
  if (detalle.startsWith('almint_')) return t(`almint.err_${detalle.slice('almint_'.length)}`, t('almint.err_generico'))
  if (detalle.startsWith('alm_')) return t(`alm.err_${detalle}`, t(`alm.err_${detalle.slice('alm_'.length)}`, t('almint.err_generico')))
  return detalle || t('almint.err_generico')
}

/** Color de cada estado que devuelve el backend (bajas, devoluciones, peticiones, propuestas, tickets). */
const TONO: Record<string, StatusBadgeKind> = {
  pendiente: 'warning', programada: 'info', pendiente_devolucion: 'warning', cerrada: 'success', anulada: 'neutral',
  recibida: 'info', perdida: 'danger', cumplida: 'success', en_compra: 'info', rechazada: 'danger', error: 'danger',
  confirmada: 'success', descartada: 'neutral', active: 'success', pending: 'warning', ended: 'neutral',
  pending_signature: 'warning', signed: 'success', unsigned: 'neutral', void: 'neutral',
  new: 'info', assigned: 'info', in_progress: 'accent', resolved: 'success', closed: 'neutral', cancelled: 'neutral',
}

/** Pastilla con el estado traducido (`almint.estado.<código>`). */
export function Estado({ t, codigo }: { t: T; codigo?: string | null }) {
  if (!codigo) return null
  return <StatusBadge kind={TONO[codigo] ?? 'neutral'} caps={false}>{etiquetaCodigo(t as never, 'almint.estado', codigo)}</StatusBadge>
}

/** Etiqueta traducida de un código (tipo de equipo, motivo, origen…). */
export function etiqueta(t: T, catalogo: string, codigo?: string | null): string {
  return etiquetaCodigo(t as never, `almint.${catalogo}`, codigo ?? '')
}
