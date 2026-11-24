/**
 * PIR (migración 206, docs/PIR.md): piezas comunes — estado (con «vencida»), resultado y
 * la etiqueta del origen. Textos en `pir.*` (i18n/langs/{es,en,zh}.mjs).
 */
import { AlertTriangle } from 'lucide-react'
import { StatusBadge } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { useAppT } from '../../i18n/AppLangContext'
import type { EstadoPir, Pir, ResultadoPir } from '../../services/api/pir'

const TONO_ESTADO: Record<EstadoPir, StatusBadgeKind> = {
  programado: 'neutral', en_curso: 'info', enviado: 'accent', aprobado: 'success', cerrado: 'success', descartado: 'neutral',
}
const TONO_RESULTADO: Record<ResultadoPir, StatusBadgeKind> = { exito: 'success', exito_parcial: 'warning', fallo: 'danger' }

export const ESTADOS_PIR: EstadoPir[] = ['programado', 'en_curso', 'enviado', 'aprobado', 'cerrado', 'descartado']
export const RESULTADOS_PIR: ResultadoPir[] = ['exito', 'exito_parcial', 'fallo']

export function EstadoDePir({ pir }: { pir: Pick<Pir, 'estado' | 'vencida'> }) {
  const t = useAppT()
  if (pir.vencida) {
    return <StatusBadge kind="danger"><span className="pir-insignia"><AlertTriangle size={12} aria-hidden />{t('pir.estado_vencido')}</span></StatusBadge>
  }
  return <StatusBadge kind={TONO_ESTADO[pir.estado] ?? 'neutral'}>{t(`pir.estado_${pir.estado}`)}</StatusBadge>
}

export function ResultadoDePir({ resultado }: { resultado: ResultadoPir | null }) {
  const t = useAppT()
  if (!resultado) return <span className="pir-apagado">—</span>
  return <StatusBadge kind={TONO_RESULTADO[resultado]}>{t(`pir.resultado_${resultado}`)}</StatusBadge>
}

/** «CHG00012 · Título» o «PRJ-007 · Nombre» con el ámbito delante. */
export function OrigenDePir({ pir }: { pir: Pick<Pir, 'origen_tipo' | 'origen_ref' | 'origen_nombre'> }) {
  const t = useAppT()
  return (
    <span className="pir-origen">
      <span className="pir-apagado">{t(`pir.origen_${pir.origen_tipo}`)}</span>
      {' '}{[pir.origen_ref, pir.origen_nombre].filter(Boolean).join(' · ') || '—'}
    </span>
  )
}
