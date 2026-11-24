import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi, dashboardApi } from '../services/api'
import { cacheBiKpis, getCachedBiKpis, cacheBiProjects, getCachedBiProjects, purgeExpiredBiCache } from '../services/biOfflineDb'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Spinner, KpiCard, EmptyState, TablaSimple } from '../components/ui'
import { BarChart3, Briefcase, Clock, FolderKanban, Percent, PieChart as PieChartIcon, Wallet } from 'lucide-react'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { useAppT, useAppLang } from '../i18n/AppLangContext'
import NarrativeCard from '../components/bi/NarrativeCard'
import AskDataWidget from '../components/bi/AskDataWidget'
import MetricasIncrustadas from '../components/conectores/MetricasIncrustadas'
import useMediaQuery from '../hooks/useMediaQuery'
import { localeActivo } from '../utils/helpers'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { STALE_LIVE_MS } from '../constants/timings'
import './BIPage.css'
// Los KPI son los de `olap/query_engine.get_kpi_summary` (auditoria 2026-11: la
// pagina leia `revenue_total`, `cost_total`… que no existen, y salia 0 €). Las
// cifras de horas y coste son del mes en curso; no hay filtro por periodo.
import type { KpisOlap, SaludDeProyecto } from '../services/api/tipos-analitica'

function getLocale(lang: string) {
  return localeActivo(lang || undefined)
}

function fmtNum(v: unknown, lang = 'es') {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return new Intl.NumberFormat(getLocale(lang), { maximumFractionDigits: 1 }).format(Number(v))
}

function fmtPct(v: unknown, lang = 'es') {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${new Intl.NumberFormat(getLocale(lang), { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(Number(v))}%`
}

function EmptyDash() {
  const t = useAppT()
  return (
    <EmptyState icon={<BarChart3 size={28} />} title={t('bi.no_hay_datos_para_el_periodo_seleccionado')} />
  )
}

export default function BIPage(): JSX.Element {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const { lang } = useAppLang()
  const isMobile = useMediaQuery('(max-width: 900px)')
  const periodKey = 'mtd'

  // Purge stale Dexie cache on first mount
  useEffect(() => { purgeExpiredBiCache() }, [])

  const { data: kpis, isLoading: loadingKpis } = useQuery<KpisOlap | null>({
    queryKey: ['bi-kpis'],
    queryFn: async () => {
      try {
        const data = await analyticsApi.olapKpis().then((r) => r.data)
        await cacheBiKpis(periodKey, data)
        return data
      } catch {
        return (await getCachedBiKpis(periodKey)) as KpisOlap | null  // la copia guardada arriba
      }
    },
    staleTime: STALE_LIVE_MS,
  })

  const { data: projectsHealth = [], isLoading: loadingHealth } = useQuery<SaludDeProyecto[]>({
    queryKey: ['bi-projects-health'],
    queryFn: async () => {
      try {
        const data = await dashboardApi.projectsHealth().then((r) => r.data)
        await cacheBiProjects(periodKey, data)
        return data ?? []
      } catch {
        return ((await getCachedBiProjects(periodKey)) as SaludDeProyecto[] | null) ?? []
      }
    },
    staleTime: STALE_LIVE_MS,
  })

  const isLoading = loadingKpis || loadingHealth
  const cabecera = <PageHeader icon={<PieChartIcon size={18} />} title={t('nav.executive')} subtitle={t('bi.kpi_dashboard_subtitle')} />
  if (isLoading) {
    return (
      <PageShell dense className="bi-page">
        {cabecera}
        <div className="bi-loading" role="status" aria-label={t('bi.loading')}>
          <Spinner size={28} />
        </div>
      </PageShell>
    )
  }

  const activeProjects = Number(kpis?.active_projects || 0)
  const hayDatos = activeProjects > 0 || (projectsHealth?.length || 0) > 0 || Number(kpis?.open_opps || 0) > 0

  return (
    <PageShell dense className="bi-page">
      {cabecera}

      {!hayDatos ? (
        <EmptyDash />
      ) : (
        <>
          <div className="ds-grid-stats bi-kpi-grid">
            <KpiCard icon={<Wallet size={16} />} label={`${t('bi.kpi_coste')} · ${t('bi.kpi_mes')}`} value={fmtMoneda(kpis?.cost_mtd, { decimales: 0 })} />
            <KpiCard icon={<Clock size={16} />} label={`${t('bi.kpi_horas')} · ${t('bi.kpi_mes')}`} value={fmtNum(kpis?.hours_mtd, lang)}
              sub={`${t('bi.kpi_facturables')}: ${fmtPct(kpis?.billability_pct, lang)}`} />
            <KpiCard icon={<Percent size={16} />} label={t('bi.kpi_margen')} value={fmtPct(kpis?.avg_margin_pct, lang)} sub={t('bi.kpi_margen_nota')} />
            <KpiCard icon={<Briefcase size={16} />} label={t('bi.kpi_pipeline')} value={fmtMoneda(kpis?.pipeline_weighted, { decimales: 0 })}
              sub={`${t('bi.kpi_abiertas')}: ${kpis?.open_opps ?? 0} · ${t('bi.kpi_ganado')}: ${fmtMoneda(kpis?.won_revenue, { decimales: 0 })}`} />
            <KpiCard icon={<FolderKanban size={16} />} label={t('bi.kpi_proyectos')} value={activeProjects}
              sub={`${t('bi.kpi_riesgo_alto')}: ${kpis?.high_risk_projects ?? 0}`} danger={Number(kpis?.high_risk_projects ?? 0) > 0} />
          </div>

          <div className="bi-widget-grid">
            <NarrativeCard lang={lang} />
            <AskDataWidget />
          </div>

          {/* 23-11-2026: métricas certificadas de contecintelligence (token acotado; solo si su origen está en la CSP). */}
          <MetricasIncrustadas />

          <section className="bi-panel" aria-labelledby="bi-estado-proyectos">
            <h2 id="bi-estado-proyectos" className="bi-panel__title">
              {t('bi.estado_de_proyectos')}
            </h2>
            {isMobile ? (
              <div className="bi-cards">
                {(projectsHealth || []).slice(0, 12).map((p) => (
                  <div key={p.project_id} className="bi-card">
                    <div className="bi-card__name">
                      {p.project_name || p.project_code || '—'}
                    </div>
                    <div className="bi-card__meta">{t('bi.col_estado')}: {etiquetaCodigo(t, 'estado', p.status) || '—'} · {t('bi.col_riesgo')}: {etiquetaCodigo(t, 'estado', p.risk_level) || '—'}</div>
                    <div className="bi-card__nums">{t('bi.col_presupuesto')}: {fmtPct(p.budget_used_pct, lang)} · {t('bi.col_avance')}: {fmtPct(p.progress_pct, lang)}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="u-scroll-x">
                <TablaSimple claseTabla="u-table-sm bi-table">
                  <thead>
                    <tr>
                      <th scope="col">{t('bi.col_proyecto')}</th>
                      <th scope="col">{t('bi.col_estado')}</th>
                      <th scope="col">{t('bi.col_riesgo')}</th>
                      <th scope="col" className="bi-num">{t('bi.col_presupuesto')}</th>
                      <th scope="col" className="bi-num">{t('bi.col_avance')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(projectsHealth || []).slice(0, 12).map((p) => (
                      <tr key={p.project_id}>
                        <td>{p.project_name || p.project_code || '—'}</td>
                        <td className="bi-sec">{etiquetaCodigo(t, 'estado', p.status) || '—'}</td>
                        <td className="bi-sec">{etiquetaCodigo(t, 'estado', p.risk_level) || '—'}</td>
                        <td className="bi-num">{fmtPct(p.budget_used_pct, lang)}</td>
                        <td className="bi-num">{fmtPct(p.progress_pct, lang)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TablaSimple>
              </div>
            )}
          </section>
        </>
      )}
    </PageShell>
  )
}
