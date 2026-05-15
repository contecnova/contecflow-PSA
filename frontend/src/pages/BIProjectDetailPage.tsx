import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'
import { analyticsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { BarChart2 } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const WEEKS_WINDOW_STORAGE_KEY = 'bi_project_detail_weeks_window_v1'

const panelStyle = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 12,
  padding: 16,
}

function loadStoredWeeksWindow() {
  try {
    const raw = window.localStorage.getItem(WEEKS_WINDOW_STORAGE_KEY)
    const value = Number(raw)
    if ([4, 8, 12].includes(value)) return value
    return 8
  } catch {
    return 8
  }
}

function toApiFilters(filters = {}) {
  return {
    project_id: filters.projectId || undefined,
    date_from: filters.dateFrom || undefined,
    date_to: filters.dateTo || undefined,
  }
}

function toIsoDate(d) {
  return d.toISOString().slice(0, 10)
}

function buildRangeForWeeks(weeks) {
  const end = new Date()
  const start = new Date(end)
  start.setDate(end.getDate() - (weeks * 7 - 1))
  return { date_from: toIsoDate(start), date_to: toIsoDate(end) }
}

function toCsv(rows) {
  if (!rows || !rows.length) return ''
  const keys = Array.from(rows.reduce((acc, row) => {
    Object.keys(row || {}).forEach((k) => acc.add(k))
    return acc
  }, new Set()))
  const esc = (v) => {
    if (v == null) return ''
    const s = String(v)
    if (s.includes(',') || s.includes('"') || s.includes('\n')) return `"${s.replaceAll('"', '""')}"`
    return s
  }
  const head = keys.join(',')
  const body = rows.map((r) => keys.map((k) => esc(r[k])).join(',')).join('\n')
  return `${head}\n${body}`
}

function downloadCsv(content, filename) {
  if (!content) return
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function printNodeInNewWindow(node, title) {
  if (!node) return
  const w = window.open('', '_blank', 'width=1280,height=900')
  if (!w) return
  w.document.write(`
    <html>
      <head>
        <title>${title}</title>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 20px; color: #111; }
          .sheet { max-width: 1200px; margin: 0 auto; }
        </style>
      </head>
      <body>
        <div class="sheet">${node.outerHTML}</div>
      </body>
    </html>
  `)
  w.document.close()
  w.focus()
  w.print()
}

export default function BIProjectDetailPage(): JSX.Element {
  const t = useAppT()
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId: string }>()
  // TODO type: location.state shape depends on calling pages (Batch F/G2)
  const location = useLocation() as { state?: { projectName?: string; fromFilters?: Record<string, unknown> } }
  const [selectedUserId, setSelectedUserId] = useState('')
  const [weeksWindow, setWeeksWindow] = useState(loadStoredWeeksWindow)

  const projectName = location.state?.projectName || `Proyecto ${projectId}`
  const apiFilters = useMemo(() => {
    const fromFilters = location.state?.fromFilters || { projectId }
    const base = { ...toApiFilters(fromFilters), project_id: projectId }
    return { ...base, ...buildRangeForWeeks(weeksWindow) }
  }, [location.state, projectId, weeksWindow])

  const { data: hoursRows = [], isLoading: hoursLoading } = useQuery({
    queryKey: ['bi-project-hours-week', projectId, apiFilters],
    queryFn: () => analyticsApi.query('hours_by_week', apiFilters).then(r => r.data?.rows || []).catch(() => []),
  })

  const { data: costRows = [], isLoading: costLoading } = useQuery({
    queryKey: ['bi-project-cost-month', projectId, apiFilters],
    queryFn: () => analyticsApi.query('cost_by_month', apiFilters).then(r => r.data?.rows || []).catch(() => []),
  })

  const { data: marginRows = [], isLoading: marginLoading } = useQuery({
    queryKey: ['bi-project-margin', projectId, apiFilters],
    queryFn: () => analyticsApi.query('margin_by_project', apiFilters).then(r => r.data?.rows || []).catch(() => []),
  })

  const { data: membersRows = [], isLoading: membersLoading } = useQuery({
    queryKey: ['bi-project-members', projectId, apiFilters],
    queryFn: () => analyticsApi.query('hours_by_person', apiFilters).then(r => r.data?.rows || []).catch(() => []),
  })

  const { data: filterOptions = {} } = useQuery({
    queryKey: ['bi-filter-options-detail'],
    queryFn: () => analyticsApi.filterOptions().then(r => r.data).catch(() => ({})),
  })

  const marginCard = marginRows?.[0]
  const marginPct = marginCard?.margin ?? 0

  const usersByLabel = useMemo(() => {
    const out = {}
    ;(filterOptions.users || []).forEach((u) => {
      out[String(u.label || '').trim().toLowerCase()] = u.id
    })
    return out
  }, [filterOptions.users])

  const membersWithUserId = useMemo(() => (
    (membersRows || []).map((r) => ({
      ...r,
      userId: usersByLabel[String(r.label || '').trim().toLowerCase()] || '',
    }))
  ), [membersRows, usersByLabel])

  useEffect(() => {
    if (selectedUserId) return
    const first = membersWithUserId.find((m) => m.userId)
    if (first?.userId) setSelectedUserId(first.userId)
  }, [membersWithUserId, selectedUserId])

  const weeklyByPersonParams = useMemo(() => ({
    ...apiFilters,
    user_id: selectedUserId || undefined,
  }), [apiFilters, selectedUserId])

  const { data: weeklyByPersonRows = [], isLoading: weeklyByPersonLoading } = useQuery({
    enabled: Boolean(selectedUserId),
    queryKey: ['bi-project-hours-week-person', projectId, weeklyByPersonParams],
    queryFn: () => analyticsApi.query('hours_by_week', weeklyByPersonParams).then(r => r.data?.rows || []).catch(() => []),
  })

  const { data: weeklyTeamRows = [], isLoading: weeklyTeamLoading } = useQuery({
    queryKey: ['bi-project-hours-week-team', projectId, apiFilters],
    queryFn: () => analyticsApi.query('hours_by_week', apiFilters).then(r => r.data?.rows || []).catch(() => []),
  })

  const hoursChart = (hoursRows || []).map(r => ({
    label: r.label || r.full_label || '',
    value: Number(r.value || 0),
  }))

  const costChart = (costRows || []).map(r => ({
    label: r.label || '',
    value: Number(r.value || 0),
  }))

  const detailBars = marginRows.slice(0, 8).map(r => ({
    label: r.label || 'Proyecto',
    revenue: Number(r.revenue || 0),
    cost: Number(r.cost || 0),
  }))

  const teamCount = Math.max(1, membersWithUserId.filter((m) => m.userId).length)
  const compareChart = useMemo(() => {
    const teamMap = {}
    const personMap = {}
    ;(weeklyTeamRows || []).forEach((r) => {
      const k = r.label || r.full_label || ''
      teamMap[k] = Number(r.value || 0)
    })
    ;(weeklyByPersonRows || []).forEach((r) => {
      const k = r.label || r.full_label || ''
      personMap[k] = Number(r.value || 0)
    })
    const labels = Array.from(new Set([...Object.keys(teamMap), ...Object.keys(personMap)])).sort()
    return labels.map((label) => ({
      label,
      persona: personMap[label] || 0,
      mediaEquipo: (teamMap[label] || 0) / teamCount,
    }))
  }, [weeklyTeamRows, weeklyByPersonRows, teamCount])

  const selectedMember = membersWithUserId.find((m) => m.userId === selectedUserId)

  const handleExportMembersCsv = () => {
    const csv = toCsv(membersWithUserId.map((m) => ({ persona: m.label || '', horas: Number(m.value || 0).toFixed(1) })))
    downloadCsv(csv, `bi_project_${projectId}_miembros_${new Date().toISOString().slice(0, 10)}.csv`)
  }

  const handleExportTrendCsv = () => {
    const csv = toCsv(compareChart.map((r) => ({ semana: r.label, persona_horas: r.persona.toFixed(1), media_equipo_horas: r.mediaEquipo.toFixed(1) })))
    downloadCsv(csv, `bi_project_${projectId}_tendencia_${selectedUserId || 'equipo'}_${new Date().toISOString().slice(0, 10)}.csv`)
  }

  const handleExportPdf = () => {
    const node = document.getElementById('bi-project-detail-root')
    printNodeInNewWindow(node, `BI Project Detail ${projectId}`)
  }

  useEffect(() => {
    try {
      window.localStorage.setItem(WEEKS_WINDOW_STORAGE_KEY, String(weeksWindow))
    } catch {
      // ignore storage errors
    }
  }, [weeksWindow])

  return (
    <PageShell>
      <div id="bi-project-detail-root">
      <PageHeader
        icon={<BarChart2 size={18} />}
        title={t('bi.detail_title')}
        subtitle={t('bi_project_detail.subtitle', { projectName })}
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              onClick={handleExportMembersCsv}
              style={{
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid var(--surface-4)',
                background: 'var(--surface-3)',
                color: 'var(--text-1)',
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              {t('bi.csv_members')}
            </button>
            <button
              onClick={handleExportTrendCsv}
              style={{
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid var(--surface-4)',
                background: 'var(--surface-3)',
                color: 'var(--text-1)',
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              {t('bi.csv_trend')}
            </button>
            <button
              onClick={handleExportPdf}
              style={{
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid var(--surface-4)',
                background: 'var(--surface-3)',
                color: 'var(--text-1)',
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              PDF
            </button>
            <button
              onClick={() => navigate('/executive')}
              style={{
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid var(--surface-4)',
                background: 'var(--surface-3)',
                color: 'var(--text-1)',
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              {t('bi.back_dashboard')}
            </button>
          </div>
        }
      />

      <div style={{ ...panelStyle, marginBottom: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{t('bi.analysis_window')}</div>
        <div style={{ display: 'flex', gap: 6 }}>
          {[4, 8, 12].map((w) => (
            <button
              key={w}
              onClick={() => setWeeksWindow(w)}
              style={{
                padding: '5px 10px',
                borderRadius: 7,
                border: '1px solid var(--surface-4)',
                background: weeksWindow === w ? 'var(--accent-muted)' : 'var(--surface-3)',
                color: weeksWindow === w ? 'var(--accent)' : 'var(--text-2)',
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontSize: "var(--text-sm)",
                fontWeight: 600,
              }}
            >
              {w} {t('bi.weeks')}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 }}>
        <div style={panelStyle}>
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{t('bi.current_margin')}</div>
          <div style={{ fontSize: "var(--text-2xl-em)", fontWeight: 800, color: marginPct >= 20 ? 'var(--success)' : marginPct >= 0 ? 'var(--warning)' : 'var(--danger)' }}>
            {marginPct.toFixed(1)}%
          </div>
        </div>
        <div style={panelStyle}>
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{t('bi.revenues')}</div>
          <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: 'var(--accent)' }}>
            {Math.round(Number(marginCard?.revenue || 0)).toLocaleString('es-ES')} €
          </div>
        </div>
        <div style={panelStyle}>
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{t('bi.cost')}</div>
          <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: 'var(--danger)' }}>
            {Math.round(Number(marginCard?.cost || 0)).toLocaleString('es-ES')} €
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div style={panelStyle}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>{t('bi.hours_by_week')}</div>
          <div style={{ height: 260 }}>
            {hoursLoading ? (
              <div style={{ color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>{t('bi.loading')}</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={hoursChart} margin={{ top: 6, right: 4, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                  <XAxis dataKey="label" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-3)' }} />
                  <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-3)' }} />
                  <Tooltip />
                  <Area type="monotone" dataKey="value" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.2} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div style={panelStyle}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>{t('bi.cost_by_month')}</div>
          <div style={{ height: 260 }}>
            {costLoading ? (
              <div style={{ color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>{t('bi.loading')}</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={costChart} margin={{ top: 6, right: 4, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                  <XAxis dataKey="label" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-3)' }} />
                  <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-3)' }} />
                  <Tooltip />
                  <Bar dataKey="value" fill="var(--danger)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      <div style={{ ...panelStyle, marginTop: 16 }}>
        <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>{t('bi.revenue_vs_cost')}</div>
        <div style={{ height: 280 }}>
          {marginLoading ? (
            <div style={{ color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>{t('bi.loading')}</div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={detailBars} margin={{ top: 6, right: 4, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="label" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-3)' }} />
                <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-3)' }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="revenue" name={t('bi.revenues')} fill="var(--accent)" radius={[4, 4, 0, 0]} />
                <Bar dataKey="cost" name={t('bi.cost')} fill="var(--warning)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
        <div style={panelStyle}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>{t('bi.project_members')}</div>
          {membersLoading ? (
            <div style={{ color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>{t('bi.loading')}</div>
          ) : !membersWithUserId.length ? (
            <div style={{ color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>{t('bi.no_member_data')}</div>
          ) : (
            <div style={{ overflow: 'auto', maxHeight: 280 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-sm)" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', color: 'var(--text-3)', borderBottom: '1px solid var(--surface-4)', padding: '6px 4px' }}>{t('bi.person')}</th>
                    <th style={{ textAlign: 'right', color: 'var(--text-3)', borderBottom: '1px solid var(--surface-4)', padding: '6px 4px' }}>{t('bi.hours')}</th>
                  </tr>
                </thead>
                <tbody>
                  {membersWithUserId.map((m, idx) => {
                    const isSelected = Boolean(selectedUserId) && m.userId === selectedUserId
                    return (
                      <tr
                        key={`${m.label || 'persona'}-${idx}`}
                        onClick={() => m.userId && setSelectedUserId(m.userId)}
                        style={{
                          cursor: m.userId ? 'pointer' : 'default',
                          background: isSelected ? 'var(--accent-muted)' : 'transparent',
                        }}
                      >
                        <td style={{ padding: '7px 4px', borderBottom: '1px solid var(--surface-4)', color: 'var(--text-1)' }}>{m.label || t('bi.no_name')}</td>
                        <td style={{ padding: '7px 4px', borderBottom: '1px solid var(--surface-4)', color: 'var(--text-2)', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{Number(m.value || 0).toFixed(1)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div style={panelStyle}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>{t('bi.weekly_trend')}</div>
          {!selectedUserId ? (
            <div style={{ color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>{t('bi.select_person')}</div>
          ) : weeklyByPersonLoading || weeklyTeamLoading ? (
            <div style={{ color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>{t('bi.loading')}</div>
          ) : (
            <div style={{ height: 280 }}>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 8 }}>
                {selectedMember?.label || t('bi.person')} {t('bi.vs_team_avg')}
              </div>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={compareChart} margin={{ top: 6, right: 4, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                  <XAxis dataKey="label" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-3)' }} />
                  <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-3)' }} />
                  <Tooltip />
                  <Legend />
                  <Area type="monotone" dataKey="persona" name={t('bi.person')} stroke="var(--success)" fill="var(--success)" fillOpacity={0.18} strokeWidth={2} />
                  <Area type="monotone" dataKey="mediaEquipo" name={t('bi.team_avg')} stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.12} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
      </div>
    </PageShell>
  )
}
