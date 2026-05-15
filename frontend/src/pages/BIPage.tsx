import { useEffect, useMemo, useState } from 'react'
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

function dateRange(days) {
  const to = new Date()
  const from = new Date(to)
  from.setDate(from.getDate() - Number(days || 30))
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  }
}

function getLocale(lang) {
  return String(lang || 'es').toLowerCase().startsWith('en') ? 'en-US' : 'es-ES'
}

function fmtCur(v, lang = 'es') {
  if (v == null || Number.isNaN(Number(v))) return '—'
  const locale = getLocale(lang)
  return new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(Number(v))
}

function fmtPct(v) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${Number(v).toFixed(1)}%`
}

function PeriodButton({ active, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        border: active ? '1px solid var(--accent)' : '1px solid var(--surface-4)',
        background: active ? 'var(--accent-border-soft)' : 'transparent',
        color: active ? 'var(--accent)' : 'var(--text-2)',
        borderRadius: 8,
        minHeight: 48,
        minWidth: 48,
        padding: '6px 10px',
        fontSize: "var(--text-sm)",
        fontWeight: 700,
        cursor: 'pointer',
      }}
    >
      {label}
    </button>
  )
}

function KpiCard({ label, value, note }) {
  return (
    <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 14 }}>
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, color: 'var(--text-1)', lineHeight: 1.1 }}>{value}</div>
      {note ? <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 6 }}>{note}</div> : null}
    </div>
  )
}

function EmptyDash() {
  return (
    <div style={{ textAlign: 'center', color: 'var(--text-3)', border: '1px dashed var(--surface-4)', borderRadius: 12, padding: 30 }}>
      No hay datos para el período seleccionado.
    </div>
  )
}

export default function BIPage(): JSX.Element {
  const t = useAppT()
  const { lang } = useAppLang()
  const [days, setDays] = useState(30)
  const isMobile = useMediaQuery('(max-width: 900px)')
  const params = useMemo(() => dateRange(days), [days])
  const periodKey = `${days}d`

  // Purge stale Dexie cache on first mount
  useEffect(() => { purgeExpiredBiCache() }, [])

  const { data: kpis, isLoading: loadingKpis } = useQuery({
    queryKey: ['bi-kpis', params],
    queryFn: async () => {
      try {
        const data = await analyticsApi.olapKpis(params).then((r) => r.data)
        await cacheBiKpis(periodKey, data)
        return data
      } catch {
        return await getCachedBiKpis(periodKey)
      }
    },
    staleTime: 10_000,
  })

  const { data: projectsHealth = [], isLoading: loadingHealth } = useQuery({
    queryKey: ['bi-projects-health', params],
    queryFn: async () => {
      try {
        const data = await dashboardApi.projectsHealth(params).then((r) => r.data)
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

  const totalProjects = Number(kpis?.projects_total || projectsHealth?.length || 0)
  const revenue = Number(kpis?.revenue_total || 0)
  const cost = Number(kpis?.cost_total || 0)
  const margin = revenue - cost
  const marginPct = revenue > 0 ? (margin / revenue) * 100 : null
  const activeProjects = Number(kpis?.projects_active || 0)

  return (
    <PageShell dense style={{ paddingLeft: isMobile ? 12 : undefined, paddingRight: isMobile ? 12 : undefined }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 18 }}>
        <PageHeader icon={<PieChartIcon size={18} />} title={t('bi.title')} subtitle="Dashboard ejecutivo de KPIs" />
        <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
          {[7, 30, 90, 365].map((d) => (
            <PeriodButton key={d} active={days === d} label={d === 365 ? '1a' : `${d}d`} onClick={() => setDays(d)} />
          ))}
        </div>
      </div>

      {!totalProjects && !revenue ? (
        <EmptyDash />
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12, marginBottom: 16 }}>
            <KpiCard label="Revenue" value={fmtCur(revenue, lang)} />
            <KpiCard label="Coste" value={fmtCur(cost, lang)} />
            <KpiCard label="Margen" value={fmtCur(margin, lang)} note={`Margen %: ${fmtPct(marginPct)}`} />
            <KpiCard label="Proyectos" value={totalProjects} note={`Activos: ${activeProjects}`} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(360px, 1fr))', gap: 12, marginBottom: 16 }}>
            <NarrativeCard lang={lang} />
            <AskDataWidget />
          </div>

          <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ padding: 12, borderBottom: '1px solid var(--surface-4)', fontWeight: 700, color: 'var(--text-1)' }}>
              Estado de proyectos
            </div>
            {isMobile ? (
              <div style={{ display: 'grid', gap: 8, padding: 10 }}>
                {(projectsHealth || []).slice(0, 12).map((p) => (
                  <div
                    key={p.id || p.project_id || p.code}
                    style={{
                      border: '1px solid var(--surface-4)',
                      borderRadius: 10,
                      padding: 10,
                      background: 'var(--surface-2)',
                    }}
                  >
                    <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>
                      {p.name || p.project_name || p.code || '—'}
                    </div>
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 3 }}>Cliente: {p.client_name || '—'}</div>
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 3 }}>Estado: {p.status || '—'}</div>
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', fontWeight: 700 }}>Budget: {fmtCur(p.budget_amount, lang)}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-sm)" }}>
                  <thead>
                    <tr style={{ background: 'var(--surface-2)' }}>
                      <th style={{ textAlign: 'left', padding: '10px 12px' }}>Proyecto</th>
                      <th style={{ textAlign: 'left', padding: '10px 12px' }}>Cliente</th>
                      <th style={{ textAlign: 'left', padding: '10px 12px' }}>Estado</th>
                      <th style={{ textAlign: 'right', padding: '10px 12px' }}>Budget</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(projectsHealth || []).slice(0, 12).map((p) => (
                      <tr key={p.id || p.project_id || p.code} style={{ borderTop: '1px solid var(--surface-4)' }}>
                        <td style={{ padding: '9px 12px', color: 'var(--text-1)' }}>{p.name || p.project_name || p.code || '—'}</td>
                        <td style={{ padding: '9px 12px', color: 'var(--text-2)' }}>{p.client_name || '—'}</td>
                        <td style={{ padding: '9px 12px', color: 'var(--text-2)' }}>{p.status || '—'}</td>
                        <td style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--text-1)' }}>{fmtCur(p.budget_amount, lang)}</td>
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
