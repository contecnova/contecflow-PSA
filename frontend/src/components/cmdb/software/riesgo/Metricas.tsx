/**
 * Pestaña Riesgo → Métricas de gestión de vulnerabilidades (22-11-2026):
 * activos con vulnerabilidades (todos, internos y máquinas), densidad, MTTP,
 * antigüedad media de lo no parcheado, SO sin soporte y repartos por impacto y
 * por estado.
 *
 * Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11.6.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Clock, Gauge, Server, ShieldAlert } from 'lucide-react'
import { useAppT } from '../../../../i18n/AppLangContext'
import { cmdbRiesgoApi } from '../../../../services/api/cmdbRiesgo'
import type { Ambito } from '../../../../services/api/cmdbRiesgo'
import { EmptyState, KpiCard, Section, Segmentado, Spinner } from '../../../ui'
import { BarraPct, pct, redondeo } from './comunRiesgo'

const DIAS = [30, 90, 180, 365]

export default function Metricas({ ambito }: { ambito: Ambito }) {
  const t = useAppT()
  const [dias, setDias] = useState(90)
  const { data: m, isLoading } = useQuery({
    queryKey: ['swr', 'metricas', ambito.scope_type, ambito.scope_id ?? '', dias],
    queryFn: () => cmdbRiesgoApi.metricas(ambito, dias),
  })
  if (isLoading) return <Spinner />
  if (!m) return <EmptyState icon={<Gauge size={28} />} title={t('swr.sin_metricas')} />
  const totalImpacto = Math.max(1, m.by_impact.high + m.by_impact.medium + m.by_impact.low)
  const totalEstado = Math.max(1, m.by_state.new + m.by_state.in_progress + m.by_state.resolved + m.by_state.accepted)
  const impactos: [string, number, string][] = [
    ['high', m.by_impact.high, 'critical'], ['medium', m.by_impact.medium, 'medium'], ['low', m.by_impact.low, 'low'],
  ]
  const estados: [string, number][] = [['new', m.by_state.new], ['in_progress', m.by_state.in_progress], ['resolved', m.by_state.resolved], ['accepted', m.by_state.accepted]]
  return (
    <div className="u-stack-20">
      <div className="u-wrap-8">
        <Segmentado aria-label={t('swr.periodo')} valor={String(dias)} onChange={v => setDias(Number(v))}
          opciones={DIAS.map(d => ({ valor: String(d), etiqueta: t('swr.n_dias', { n: d }) }))} />
      </div>
      <div className="ds-grid-stats">
        <KpiCard label={t('swr.m_activos_con_vulns')} value={pct(m.pct_assets_with_vulns)} icon={<ShieldAlert size={14} />}
          danger={(m.pct_assets_with_vulns ?? 0) > 50} sub={t('swr.m_de_n', { n: m.assets_with_vulns, total: m.assets })} />
        <KpiCard label={t('swr.m_internos_con_vulns')} value={pct(m.pct_internal_with_vulns)} sub={t('swr.m_de_n', { n: m.internal_with_vulns, total: m.internal_assets })} />
        <KpiCard label={t('swr.m_maquinas_con_vulns')} value={pct(m.pct_machines_with_vulns)} icon={<Server size={14} />} sub={t('swr.m_de_n', { n: m.machines_with_vulns, total: m.machines })} />
        <KpiCard label={t('swr.m_densidad_activo')} value={redondeo(m.density_per_asset, 2)} sub={t('swr.m_densidad_maquina', { n: redondeo(m.density_per_machine, 2) })} />
        <KpiCard label={t('swr.m_mttp')} value={m.mttp_days == null ? '—' : t('swr.m_dias', { n: redondeo(m.mttp_days, 1) })} icon={<Clock size={14} />}
          sub={t('swr.m_mttp_muestra', { n: m.mttp_sample, dias: m.days })} />
        <KpiCard label={t('swr.m_antiguedad')} value={m.avg_age_unpatched_days == null ? '—' : t('swr.m_dias', { n: redondeo(m.avg_age_unpatched_days, 1) })}
          warning={(m.avg_age_unpatched_days ?? 0) > 30} />
        <KpiCard label={t('swr.m_so_sin_soporte')} value={m.os_unsupported} danger={m.os_unsupported > 0} />
      </div>
      <div className="sdm-grid">
        <Section title={t('swr.m_por_impacto')} subtitle={t('swr.m_por_impacto_desc', { alto: m.impact_ranges.high_from, medio: m.impact_ranges.medium_from })}>
          <ul className="swr-factores">
            {impactos.map(([k, n, nivel]) => (
              <li key={k} className="swr-factor">
                <span>{t(`swr.impacto_${k}`)}</span>
                <BarraPct pct={(n / totalImpacto) * 100} nivel={nivel} />
                <span className="swr-factor__datos">{n}</span>
              </li>
            ))}
          </ul>
        </Section>
        <Section title={t('swr.m_por_estado')} subtitle={t('swr.m_por_estado_desc', { dias: m.days })}>
          <ul className="swr-factores">
            {estados.map(([k, n]) => (
              <li key={k} className="swr-factor">
                <span>{t(`swr.estado_${k}`)}</span>
                <BarraPct pct={(n / totalEstado) * 100} />
                <span className="swr-factor__datos">{n}</span>
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </div>
  )
}
