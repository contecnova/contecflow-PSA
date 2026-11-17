/**
 * ColaPorRiesgo — mis tickets ordenados por riesgo de SLA y valor de negocio
 * (`GET /sd/tickets/my-queue/prioritized`). El peso de cada parte es el ajuste
 * `SD_QUEUE_SLA_RISK_WEIGHT` de la empresa.
 *
 * 16-11-2026 (pasada de diseño): el vacío lleva icono y explicación.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ListOrdered } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { EmptyState, Pulsable, Spinner, StatusBadge, Section, TablaSimple } from '../ui'
import Pagination from '../ui/Pagination'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { iaDelTicketApi } from '../../services/api/serviceDeskMercado'
import { fmtDate } from '../../utils/helpers'
import { POLL_DEFAULT_MS } from '../../constants/timings'
import './sdMercado.css'

const TAMANO = 25
const pct = (v: number) => `${Math.round((v || 0) * 100)}`
/** Bandas de color del riesgo de SLA (solo presentación). */
const BANDA_ALTA = 0.7
const BANDA_MEDIA = 0.4

export default function ColaPorRiesgo({ onSelect }: { onSelect: (id: string) => void }) {
  const t = useAppT()
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({
    queryKey: ['sdm-cola-riesgo', page],
    queryFn: () => iaDelTicketApi.colaPriorizada({ page, page_size: TAMANO }),
    refetchInterval: POLL_DEFAULT_MS,
  })
  const items = data?.items ?? []
  const total = data?.meta?.total ?? items.length

  return (
    <Section title={<span className="u-row-center-6"><ListOrdered size={16} aria-hidden="true" />{t('sd_mercado.cola_riesgo')}</span>}
      subtitle={t('sd_mercado.cola_riesgo_desc')}>
      {isLoading ? <Spinner /> : items.length === 0 ? (
        <EmptyState icon={<ListOrdered size={28} />} title={t('sd_mercado.cola_vacia')} description={t('sd_mercado.cola_riesgo_desc')} />
      ) : (
        <div className="sdm-table-wrap">
          <TablaSimple claseTabla="u-table">
            <thead><tr>
              <th>{t('sd_mercado.ticket')}</th><th>{t('sd_mercado.prioridad')}</th><th>{t('sd_mercado.puntuacion')}</th>
              <th>{t('sd_mercado.riesgo_sla')}</th><th>{t('sd_mercado.valor_negocio')}</th><th>{t('sd_mercado.vence')}</th>
            </tr></thead>
            <tbody>
              {items.map(tk => (
                <tr key={tk.id} className="u-border-b">
                  <td><Pulsable className="u-btn-outline-sm sdm-wrap" onClick={() => onSelect(tk.id)}>
                    <span className="u-mono">{tk.number}</span> {tk.title}</Pulsable></td>
                  <td><StatusBadge caps={false}>{etiquetaCodigo(t, 'estado', tk.priority)}</StatusBadge></td>
                  <td className="u-600">{pct(tk.priority_score)}</td>
                  <td><StatusBadge kind={tk.sla_risk_score >= BANDA_ALTA ? 'danger' : tk.sla_risk_score >= BANDA_MEDIA ? 'warning' : 'success'} caps={false}>{pct(tk.sla_risk_score)}</StatusBadge></td>
                  <td>{pct(tk.business_value_score)}</td>
                  <td className="u-text2-xs">{tk.sla_resolution_due ? fmtDate(tk.sla_resolution_due) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
          <Pagination page={page} totalPages={Math.max(1, Math.ceil(total / TAMANO))} onChange={setPage} total={total} pageSize={TAMANO} />
        </div>
      )}
    </Section>
  )
}
