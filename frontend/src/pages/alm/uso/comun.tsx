/**
 * Piezas comunes de las pantallas de uso real de licencias (fase 2, 16-11-2026):
 * insignias de estado y fiabilidad, nombres de fuente y el aviso de error con el
 * código del backend traducido.
 */
import { StatusBadge } from '../../../components/ui'
import type { StatusBadgeKind } from '../../../components/ui/StatusBadge'
import { useToast } from '../../../context/ToastContext'
import { useOrgSettings } from '../../../hooks/useOrgSettings'
import { useAppT } from '../../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../../i18n/etiquetaCodigo'
import { codigoDeError } from '../../../services/api/almUso'
import type { EstadoDeUso, Fiabilidad } from '../../../services/api/almUso'

export type Traducir = ReturnType<typeof useAppT>

const TONO_DE_ESTADO: Record<string, StatusBadgeKind> = {
  en_uso: 'success', infrautilizada: 'warning', sin_uso: 'danger', sin_datos: 'neutral',
  deficit: 'danger', excedente: 'warning', conforme: 'success', sin_limite: 'neutral',
  ok: 'success', parcial: 'warning', error: 'danger', en_curso: 'info', nunca: 'neutral',
  aviso_persona: 'info', aviso_responsable: 'warning', pendiente_aprobacion: 'purple', liberada: 'success',
  conservada: 'neutral', cancelada: 'neutral', rechazada: 'neutral',
  nuevo: 'info', dado_de_alta: 'success', descartado: 'neutral',
  iniciaria: 'warning', avanzaria: 'orange', cerraria_por_uso: 'success', protegida: 'neutral', sin_politica: 'info',
}

const TONO_DE_FIABILIDAD: Record<Fiabilidad, StatusBadgeKind> = { alta: 'success', media: 'info', baja: 'warning' }

/** Un estado del backend (uso, posición, sincronización, recuperación…) con su color y su nombre traducido. */
export function Estado({ codigo, catalogo = 'alm_uso.estado' }: { codigo: string | null | undefined; catalogo?: string }) {
  const t = useAppT()
  if (!codigo) return <span className="u-text3">—</span>
  return <StatusBadge kind={TONO_DE_ESTADO[codigo] ?? 'neutral'} dot caps={false}>{etiquetaCodigo(t, catalogo, codigo)}</StatusBadge>
}

export function FiabilidadBadge({ valor }: { valor: Fiabilidad | null | undefined }) {
  const t = useAppT()
  if (!valor) return <span className="u-text3">—</span>
  return <StatusBadge kind={TONO_DE_FIABILIDAD[valor]} outline caps={false}>{etiquetaCodigo(t, 'alm_uso.fiabilidad', valor)}</StatusBadge>
}

export function nombreDeFuente(t: Traducir, clave: string | null | undefined): string {
  return clave ? clave.split(',').map(c => etiquetaCodigo(t, 'alm_uso.fuente', c.trim())).join(', ') : '—'
}

export function textoDeEstado(t: Traducir, e: EstadoDeUso): string {
  return etiquetaCodigo(t, 'alm_uso.estado', e)
}

/** Aviso de error con el código del backend traducido (`alm_uso.err.<CODE>`) o su mensaje. */
export function useErrorDeUso() {
  const t = useAppT()
  const toast = useToast()
  return (e: unknown) => {
    const { codigo, mensaje } = codigoDeError(e)
    toast.error(codigo ? etiquetaCodigo(t, 'alm_uso.err', codigo, mensaje) : (mensaje || t('alm_uso.error_generico')))
  }
}

/** La moneda de la empresa (en ella vienen los importes agregados del backend). */
export function useMoneda(): string {
  return useOrgSettings().currency
}
