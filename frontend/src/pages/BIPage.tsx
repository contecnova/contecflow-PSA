import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi, dashboardApi } from '../services/api'
import { cacheBiKpis, getCachedBiKpis, cacheBiProjects, getCachedBiProjects, purgeExpiredBiCache } from '../services/biOfflineDb'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Spinner } from '../components/ui'
import { PieChart as PieChartIcon } from 'lucide-react'
import { useAppT, useAppLang } from '../i18n/AppLangContext'
import NarrativeCard from '../components/bi/NarrativeCard'
import AskDataWidget from '../components/bi/AskDataWidget'
import useMediaQuery from '../hooks/useMediaQuery'
import { localeActivo } from '../utils/helpers'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
// Lo que devuelve `olap/query_engine.get_kpi_summary` (auditoria 2026-11: la
// pagina leia `revenue_total`, `cost_total`… que no existen, y salia 0 €). Las
// cifras de horas y coste son del mes en curso; no hay filtro por periodo.
interface BiKpis {
  hours_mtd?: number
  cost_mtd?: number
  billability_pct?: number
  active_projects?: number
  avg_margin_pct?: number
  high_risk_projects?: number
  open_opps?: number
  pipeline_weighted?: number
  won_revenue?: number
}

interface BiProjectHealth {
  id?: string | number
  project_id?: string | number
  code?: string
  name?: string
  project_name?: string
  status?: string
  risk_level?: string
  budget_used_pct?: number
  progress_pct?: number
}

function getLocale(lang: string) {
  return localeActivo(lang || undefined)
}

function fmtNum(v: unknown, lang = 'es') {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return new Intl.NumberFormat(getLocale(lang), { maximumFractionDigits: 1 }).format(Number(v))
}

function fmtPct(v: unknown) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${Number(v).toFixed(1)}%`
}

function KpiCard({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 14 }}>
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, color: 'var(--text-1)', lineHeight: 1.1 }}>{value}</div>
      {note ? <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 6 }}>{note}</div> : null}
    </div>
  )
}

function EmptyDash() {
  const t = useAppT()
  return (
    <div style={{ textAlign: 'center', color: 'var(--text-3)', border: '1px dashed var(--surface-4)', borderRadius: 12, padding: 30 }}>
      {t('bi.no_hay_datos_para_el_periodo_seleccionado')}
    </div>
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

  const { data: kpis, isLoading: loadingKpis } = useQuery<BiKpis | null>({
    queryKey: ['bi-kpis'],
    queryFn: async () => {
      try {
        const data = await analyticsApi.olapKpis().then((r) => r.data)
        await cacheBiKpis(periodKey, data)
        return data
      } catch {
        return await getCachedBiKpis(periodKey)
      }
    },
    staleTime: 10_000,
  })

  const { data: projectsHealth = [], isLoading: loadingHealth } = useQuery<BiProjectHealth[]>({
    queryKey: ['bi-projects-health'],
    queryFn: async () => {
      try {
        const data = await dashboardApi.projectsHealth().then((r) => r.data)
        await cacheBiProjects(periodKey, data)
        return data ?? []
      } catch {
        return (await getCachedBiProjects(periodKey)) ?? []
      }
    },
    staleTime: 10_000,
  })

  const isLoading = loadingKpis || loadingHealth
  if (isLoading) {
    return (
      <div style={{ minHeight: 280, display: 'grid', placeItems: 'center' }}>
        <Spinner size={28} />
      </div>
    )
  }

  const activeProjects = Number(kpis?.active_projects || 0)
  const hayDatos = activeProjects > 0 || (projectsHealth?.length || 0) > 0 || Number(kpis?.open_opps || 0) > 0

  return (
    <PageShell dense style={{ paddingLeft: isMobile ? 12 : undefined, paddingRight: isMobile ? 12 : undefined }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 18 }}>
        <PageHeader icon={<PieChartIcon size={18} />} title={t('bi.title')} subtitle="Dashboard ejecutivo de KPIs" />
      </div>

      {!hayDatos ? (
        <EmptyDash />
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12, marginBottom: 16 }}>
            <KpiCard label={`${t('bi.kpi_coste')} · ${t('bi.kpi_mes')}`} value={fmtMoneda(kpis?.cost_mtd as number | null | undefined, { decimales: 0 })} />
            <KpiCard label={`${t('bi.kpi_horas')} · ${t('bi.kpi_mes')}`} value={fmtNum(kpis?.hours_mtd, lang)}
              note={`${t('bi.kpi_facturables')}: ${fmtPct(kpis?.billability_pct)}`} />
            <KpiCard label={t('bi.kpi_margen')} value={fmtPct(kpis?.avg_margin_pct)} note={t('bi.kpi_margen_nota')} />
            <KpiCard label={t('bi.kpi_pipeline')} value={fmtMoneda(kpis?.pipeline_weighted as number | null | undefined, { decimales: 0 })}
              note={`${t('bi.kpi_abiertas')}: ${kpis?.open_opps ?? 0} · ${t('bi.kpi_ganado')}: ${fmtMoneda(kpis?.won_revenue as number | null | undefined, { decimales: 0 })}`} />
            <KpiCard label={t('bi.kpi_proyectos')} value={activeProjects}
              note={`${t('bi.kpi_riesgo_alto')}: ${kpis?.high_risk_projects ?? 0}`} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(360px, 1fr))', gap: 12, marginBottom: 16 }}>
            <NarrativeCard lang={lang} />
            <AskDataWidget />
          </div>

          <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ padding: 12, borderBottom: '1px solid var(--surface-4)', fontWeight: 700, color: 'var(--text-1)' }}>
              {t('bi.estado_de_proyectos')}
            </div>
            {isMobile ? (
              <div style={{ display: 'grid', gap: 8, padding: 10 }}>
                {(projectsHealth || []).slice(0, 12).map((p) => (
                  <div
                    key={p.id || p.project_id || p.code}
                    style={{
                      border: '1px solid var(--surface-4)',
                      borderRadius: 'var(--radius-md)',
                      padding: 10,
                      background: 'var(--surface-2)',
                    }}
                  >
                    <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>
                      {p.name || p.project_name || p.code || '—'}
                    </div>
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 3 }}>{t('bi.col_estado')}: {p.status || '—'} · {t('bi.col_riesgo')}: {p.risk_level || '—'}</div>
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', fontWeight: 700 }}>{t('bi.col_presupuesto')}: {fmtPct(p.budget_used_pct)} · {t('bi.col_avance')}: {fmtPct(p.progress_pct)}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="u-scroll-x">
                <table className="u-table-sm">
                  <thead>
                    <tr style={{ background: 'var(--surface-2)' }}>
                      <th style={{ textAlign: 'left', padding: '10px 12px' }}>{t('bi.col_proyecto')}</th>
                      <th style={{ textAlign: 'left', padding: '10px 12px' }}>{t('bi.col_estado')}</th>
                      <th style={{ textAlign: 'left', padding: '10px 12px' }}>{t('bi.col_riesgo')}</th>
                      <th style={{ textAlign: 'right', padding: '10px 12px' }}>{t('bi.col_presupuesto')}</th>
                      <th style={{ textAlign: 'right', padding: '10px 12px' }}>{t('bi.col_avance')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(projectsHealth || []).slice(0, 12).map((p) => (
                      <tr key={p.id || p.project_id || p.code} style={{ borderTop: '1px solid var(--surface-4)' }}>
                        <td style={{ padding: '9px 12px', color: 'var(--text-1)' }}>{p.name || p.project_name || p.code || '—'}</td>
                        <td style={{ padding: '9px 12px', color: 'var(--text-2)' }}>{p.status || '—'}</td>
                        <td style={{ padding: '9px 12px', color: 'var(--text-2)' }}>{p.risk_level || '—'}</td>
                        <td style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--text-1)' }}>{fmtPct(p.budget_used_pct)}</td>
                        <td style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--text-1)' }}>{fmtPct(p.progress_pct)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </PageShell>
  )
}
