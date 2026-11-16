/**
 * Historial inmutable de licencias y hardware (fase 1): quién tuvo qué, cuándo
 * y por qué. Sale de `GET /alm/history`, filtrado por recurso o por titular.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History } from 'lucide-react'
import { EmptyState, Spinner } from '../ui'
import Pagination from '../ui/Pagination'
import { useAppT } from '../../i18n/AppLangContext'
import { almApi } from '../../services/api/alm'
import type { EventoAlm } from '../../services/api/alm'
import { fmtDate, fmtDateTime } from '../../utils/helpers'
import { textoDeEvento, textoDeTitular } from './almFases'

const POR_PAGINA = 25

/** Los datos del evento que se pueden enseñar (fechas, cantidades, decisiones). */
function detalle(t: ReturnType<typeof useAppT>, e: EventoAlm): string | null {
  const d = e.data || {}
  const partes: string[] = []
  if (typeof d.mode === 'string' && d.mode !== 'assignment') partes.push(t(`alm.mode_${d.mode}`, d.mode))
  if (typeof d.quantity === 'number' && d.quantity > 1) partes.push(t('alm.quantity_n', { n: d.quantity }))
  if (typeof d.valid_to === 'string') partes.push(t('alm.until_date', { date: fmtDate(d.valid_to) }))
  if (typeof d.decision === 'string') partes.push(t(`alm.decision_${d.decision}`, d.decision))
  if (typeof d.new_term === 'string') partes.push(t('alm.new_term', { date: fmtDate(d.new_term) }))
  if (typeof d.peak === 'number') partes.push(t('alm.peak_n', { n: d.peak }))
  if (typeof d.origin === 'string') partes.push(t(`alm.source_${d.origin}`, d.origin))
  if (typeof d.method === 'string') partes.push(t(`alm.disposal_method_${d.method}`, d.method))
  if (typeof d.reason === 'string') partes.push(t(`alm.disposal_reason_${d.reason}`, d.reason))
  return partes.length ? partes.join(' · ') : null
}

export default function HistorialAlm({ filtro, vacio }: { filtro: Record<string, string | undefined>; vacio?: string }) {
  const t = useAppT()
  const [pagina, setPagina] = useState(1)
  const { data, isLoading } = useQuery({
    queryKey: ['alm-history', filtro, pagina],
    queryFn: () => almApi.historial({ ...filtro, page: pagina, page_size: POR_PAGINA }),
  })
  if (isLoading) return <Spinner />
  const filas = data?.items ?? []
  if (!filas.length) return <EmptyState svgIcon={<History size={28} />} title={vacio ?? t('alm.history_empty')} />
  const paginas = Math.max(1, Math.ceil((data?.total ?? 0) / POR_PAGINA))
  return (
    <div className="almf-bloque">
      <ol className="almf-linea-de-tiempo">
        {filas.map(e => {
          const extra = detalle(t, e)
          return (
            <li key={e.id} className="almf-evento">
              <span className="almf-evento__titulo">
                {textoDeEvento(t, e.event)}
                {e.holder_name ? ` · ${textoDeTitular(t, e.holder_type)}: ${e.holder_name}` : ''}
              </span>
              <span className="almf-evento__meta">
                {e.created_at ? fmtDateTime(e.created_at) : ''}{e.actor_name ? ` · ${e.actor_name}` : ` · ${t('alm.actor_system')}`}
                {extra ? ` · ${extra}` : ''}
              </span>
              {e.reason && <span className="almf-evento__motivo">{e.reason}</span>}
            </li>
          )
        })}
      </ol>
      {paginas > 1 && <Pagination page={pagina} totalPages={paginas} onChange={setPagina} total={data?.total ?? 0} pageSize={POR_PAGINA} maxVisible={5} />}
    </div>
  )
}
