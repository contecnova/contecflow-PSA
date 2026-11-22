/**
 * PanelDelCab — los cambios que esperan al CAB, del más al menos arriesgado
 * (`GET /sd/changes/cab-dashboard`, mejoras de mercado 16-11-2026), con el
 * riesgo calculado, si tienen análisis de impacto y la ventana sugerida.
 *
 * 16-11-2026 (pasada de diseño): KPIs con icono; el filtro de riesgo mínimo en
 * una barra estrecha (antes un campo a todo el ancho); vacío con icono; fecha
 * y hora con el formateador de la app.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ClipboardCheck, Users } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { EmptyState, KpiCard, Pulsable, Spinner, StatusBadge, TablaSimple, Input } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import Pagination from '../ui/Pagination'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { fmtDateTime } from '../../utils/helpers'
import { etiquetaSd } from '../../pages/service-desk/sdUtils'
import { cambiosApi } from '../../services/api/serviceDeskMercado'
import './sdMercado.css'
import './PanelDelCab.css'

const TAMANO = 25
const RIESGO: Record<string, StatusBadgeKind> = { critical: 'danger', high: 'danger', medium: 'warning', low: 'success' }

export default function PanelDelCab({ onOpen }: { onOpen: (id: string) => void }) {
  const t = useAppT()
  const [page, setPage] = useState(1)
  const [minimo, setMinimo] = useState(0)
  const { data, isLoading } = useQuery({
    queryKey: ['sdm-cab-panel', page, minimo],
    queryFn: () => cambiosApi.panelDelCab({ page, page_size: TAMANO, min_risk_score: minimo }),
  })
  const items = data?.items ?? []
  const total = data?.total ?? items.length
  return (
    <div className="u-stack-12">
      <div className="ds-grid-stats">
        <KpiCard icon={<Users size={16} />} label={t('sd_mercado.cab_pendientes')} value={total} />
        <KpiCard icon={<AlertTriangle size={16} />} label={t('sd_mercado.cab_sin_puntuar')} value={data?.unscored ?? 0} warning={(data?.unscored ?? 0) > 0} />
      </div>
      <div className="pcab-filtros"><label className="sdm-field pcab-campo"><span>{t('sd_mercado.riesgo_minimo')}</span>
        <Input type="number" min={0} max={100} value={minimo} onChange={e => { setMinimo(Number(e.target.value) || 0); setPage(1) }} /></label></div>
      {isLoading ? <Spinner /> : items.length === 0 ? <EmptyState icon={<ClipboardCheck size={28} />} title={t('sd_mercado.cab_vacio')} /> : (
        <div className="sdm-table-wrap">
          <TablaSimple claseTabla="u-table">
            <thead><tr>
              <th>{t('sd_mercado.cambio')}</th><th>{t('sd_mercado.tipo_cambio')}</th><th>{t('sd_mercado.riesgo')}</th>
              <th>{t('sd_mercado.analizado')}</th><th>{t('sd_mercado.inicio_previsto')}</th>
            </tr></thead>
            <tbody>
              {items.map(c => (
                <tr key={c.id} className="u-border-b">
                  <td><Pulsable className="u-btn-outline-sm sdm-wrap" onClick={() => onOpen(c.id)}><span className="u-mono">{c.number}</span> {c.title}</Pulsable></td>
                  <td>{etiquetaSd('chg_type', c.change_type)}</td>
                  <td>{c.auto_risk_label
                    ? <StatusBadge kind={RIESGO[c.auto_risk_label] || 'neutral'} caps={false}>{etiquetaCodigo(t, 'sd_mercado.nivel_riesgo', c.auto_risk_label)} · {Math.round(c.auto_risk_score ?? 0)}</StatusBadge>
                    : <span className="u-text2-xs">{t('sd_mercado.sin_puntuar')}</span>}</td>
                  <td>{t(c.impact_analyzed ? 'sd_mercado.si' : 'sd_mercado.no')}</td>
                  <td className="u-text2-xs">{fmtDateTime(c.planned_start)}</td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        </div>
      )}
      <Pagination page={page} totalPages={Math.max(1, Math.ceil(total / TAMANO))} onChange={setPage} total={total} pageSize={TAMANO} />
    </div>
  )
}
