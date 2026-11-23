import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
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
import type { OpcionesDeFiltroAnalitico } from '../services/api/tipos-analitica'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ArrowLeft, BarChart2, Download, FileText, Percent, TrendingDown, TrendingUp, Users } from 'lucide-react'
import { Button, EmptyState, EstadoDeError, KpiCard, SelectorDePeriodo, Spinner, Pulsable, TablaSimple } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { usePeriodo } from '../hooks/usePeriodo'
import { SIN_HORA, codigoDeErrorDePeriodo, type ParamsPeriodoApi } from '../utils/periodo'
import { fmtNumber, fmtPct } from '../utils/helpers'
import './BIProjectDetailPage.css'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
type Translator = (key: string, params?: Record<string, unknown>) => string

type ApiFilters = Partial<ParamsPeriodoApi> & {
  project_id?: string | number
  user_id?: string | number
}

type AnalyticsRow = {
  label?: string
  full_label?: string
  value?: number | string
  revenue?: number | string
  cost?: number | string
  margin?: number
}


type FilterOptions = Partial<OpcionesDeFiltroAnalitico>

type MemberRow = AnalyticsRow & { userId?: string | number }

function toCsv(rows: Array<Record<string, unknown>>): string {
  if (!rows || !rows.length) return ''
  const keys = Array.from(rows.reduce((acc, row) => {
    Object.keys(row || {}).forEach((k) => acc.add(k))
    return acc
  }, new Set<string>()))
  const esc = (v: unknown) => {
    if (v == null) return ''
    const s = String(v)
    if (s.includes(',') || s.includes('"') || s.includes('\n')) return `"${s.replace(/"/g, '""')}"`
    return s
  }
  const head = keys.join(',')
  const body = rows.map((r) => keys.map((k) => esc(r[k])).join(',')).join('\n')
  return `${head}\n${body}`
}

function downloadCsv(content: string, filename: string): void {
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

/**
 * Imprime solo `node` en la propia página (23-11-2026, auditoría 04 M11 y 05
 * A.1.8). Antes se abría una ventana y se reescribía con `document.write` el
 * `outerHTML` del nodo y un `color:#111` fijo: DOM reinyectado y color fuera de
 * token. Ahora `@media print` (BIProjectDetailPage.css) oculta todo menos el
 * nodo marcado; el título del documento se cambia durante la impresión.
 */
function printNodeInNewWindow(node: HTMLElement | null, title: string): void {
  if (!node) return
  const tituloAnterior = document.title
  node.classList.add('bi-impresion-objetivo')
  document.body.classList.add('bi-imprimiendo')
  document.title = title
  const limpiar = () => {
    node.classList.remove('bi-impresion-objetivo')
    document.body.classList.remove('bi-imprimiendo')
    document.title = tituloAnterior
    window.removeEventListener('afterprint', limpiar)
  }
  window.addEventListener('afterprint', limpiar)
  window.print()
}

export default function BIProjectDetailPage(): JSX.Element {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT() as Translator
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId: string }>()
  const location = useLocation() as { state?: { projectName?: string; fromFilters?: Record<string, unknown> } }
  const [selectedUserId, setSelectedUserId] = useState<string | number>('')
  // Periodo libre (16-11-2026): antes una ventana de 4/8/12 semanas guardada en
  // el navegador; ahora el selector común (en la URL). Las métricas agrupan por
  // semana o mes de calendario: sin hora y sin elegir agrupación.
  const periodo = usePeriodo({ defecto: '90d', granularidades: SIN_HORA })

  const projectName = location.state?.projectName || t('bi_project_detail.project_fallback', { id: projectId })
  const apiFilters = useMemo<ApiFilters>(() => ({ ...periodo.params, project_id: projectId }), [periodo.params, projectId])

  const { data: hoursRows = [], isLoading: hoursLoading, error: errorHoras } = useQuery<AnalyticsRow[]>({
    queryKey: ['bi-project-hours-week', projectId, apiFilters],
    // Un periodo no válido (422 `periodo.*`) se explica; cualquier otro error se pinta con EstadoDeError
    // (23-11-2026: antes los `.catch(() => [])` lo escondían como «sin datos»).
    queryFn: () => analyticsApi.query('hours_by_week', apiFilters).then(r => r.data.rows as AnalyticsRow[]),
    retry: false,
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(errorHoras)

  const { data: costRows = [], isLoading: costLoading, error: errorCoste } = useQuery<AnalyticsRow[]>({
    queryKey: ['bi-project-cost-month', projectId, apiFilters],
    queryFn: () => analyticsApi.query('cost_by_month', apiFilters).then(r => r.data.rows as AnalyticsRow[]),
  })

  const { data: marginRows = [], isLoading: marginLoading, error: errorMargen } = useQuery<AnalyticsRow[]>({
    queryKey: ['bi-project-margin', projectId, apiFilters],
    queryFn: () => analyticsApi.query('margin_by_project', apiFilters).then(r => r.data.rows as AnalyticsRow[]),
  })

  const { data: membersRows = [], isLoading: membersLoading, error: errorMiembros } = useQuery<AnalyticsRow[]>({
    queryKey: ['bi-project-members', projectId, apiFilters],
    queryFn: () => analyticsApi.query('hours_by_person', apiFilters).then(r => r.data.rows as AnalyticsRow[]),
  })

  const { data: filterOptions = {} as FilterOptions } = useQuery<FilterOptions>({
    queryKey: ['bi-filter-options-detail'],
    queryFn: () => analyticsApi.filterOptions().then(r => r.data), // sin .catch: avisa el onError global
  })

  const marginCard = marginRows?.[0]
  const marginPct = marginCard?.margin ?? 0

  const usersByLabel = useMemo<Record<string, string | number>>(() => {
    const out: Record<string, string | number> = {}
    ;(filterOptions.users || []).forEach((u) => {
      out[String(u.label || '').trim().toLowerCase()] = u.id
    })
    return out
  }, [filterOptions.users])

  const membersWithUserId = useMemo<MemberRow[]>(() => (
    (membersRows || []).map((r: AnalyticsRow) => ({
      ...r,
      userId: usersByLabel[String(r.label || '').trim().toLowerCase()] || '',
    }))
  ), [membersRows, usersByLabel])

  useEffect(() => {
    if (selectedUserId) return
    const first = membersWithUserId.find((m) => m.userId)
    if (first?.userId) setSelectedUserId(first.userId)
  }, [membersWithUserId, selectedUserId])

  const weeklyByPersonParams = useMemo<ApiFilters>(() => ({
    ...apiFilters,
    user_id: selectedUserId || undefined,
  }), [apiFilters, selectedUserId])

  const { data: weeklyByPersonRows = [], isLoading: weeklyByPersonLoading, error: errorSemanaPersona } = useQuery<AnalyticsRow[]>({
    enabled: Boolean(selectedUserId),
    queryKey: ['bi-project-hours-week-person', projectId, weeklyByPersonParams],
    queryFn: () => analyticsApi.query('hours_by_week', weeklyByPersonParams).then(r => r.data.rows as AnalyticsRow[]),
  })

  const { data: weeklyTeamRows = [], isLoading: weeklyTeamLoading, error: errorSemanaEquipo } = useQuery<AnalyticsRow[]>({
    queryKey: ['bi-project-hours-week-team', projectId, apiFilters],
    queryFn: () => analyticsApi.query('hours_by_week', apiFilters).then(r => r.data.rows as AnalyticsRow[]),
  })

  // 23-11-2026: un único aviso de error (con reintento) si alguna de las consultas del detalle falla.
  const qc = useQueryClient()
  const errorDeCarga = (errorHoras && !errorDePeriodo ? errorHoras : null) ?? errorCoste ?? errorMargen ?? errorMiembros ?? errorSemanaPersona ?? errorSemanaEquipo ?? null

  const hoursChart = (hoursRows || []).map((r) => ({
    label: r.label || r.full_label || '',
    value: Number(r.value || 0),
  }))

  const costChart = (costRows || []).map((r) => ({
    label: r.label || '',
    value: Number(r.value || 0),
  }))

  const detailBars = marginRows.slice(0, 8).map((r) => ({
    label: r.label || t('bi.project_fallback'),
    revenue: Number(r.revenue || 0),
    cost: Number(r.cost || 0),
  }))

  const teamCount = Math.max(1, membersWithUserId.filter((m) => m.userId).length)
  const compareChart = useMemo(() => {
    const teamMap: Record<string, number> = {}
    const personMap: Record<string, number> = {}
    ;(weeklyTeamRows || []).forEach((r: AnalyticsRow) => {
      const k = r.label || r.full_label || ''
      teamMap[k] = Number(r.value || 0)
    })
    ;(weeklyByPersonRows || []).forEach((r: AnalyticsRow) => {
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
    printNodeInNewWindow(node, t('bi_project_detail.print_title', { id: projectId }))
  }

  return (
    <PageShell>
      <div id="bi-project-detail-root">
      <PageHeader
        icon={<BarChart2 size={18} />}
        title={t('bi.detail_title')}
        subtitle={t('bi_project_detail.subtitle', { projectName })}
        actions={
          <>
            <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => navigate('/executive')}>{t('bi.back_dashboard')}</Button>
            <Button variant="secondary" icon={<Download size={14} />} onClick={handleExportMembersCsv}>{t('bi.csv_members')}</Button>
            <Button variant="secondary" icon={<Download size={14} />} onClick={handleExportTrendCsv}>{t('bi.csv_trend')}</Button>
            <Button variant="secondary" icon={<FileText size={14} />} onClick={handleExportPdf}>{t('bi.dashboard_pdf')}</Button>
          </>
        }
      />

      <div className="ds-toolbar bipd-filtros">
        <span className="u-text2-sm">{t('bi.analysis_window')}</span>
        <SelectorDePeriodo {...periodo.selector} sinGranularidad />
      </div>
      {errorDePeriodo && (
        <EmptyState title={t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
      )}
      {errorDeCarga && (
        <EstadoDeError error={errorDeCarga} onReintentar={() => { void qc.invalidateQueries({ predicate: q => String(q.queryKey[0]).startsWith('bi-') }) }} />
      )}

      <div className="ds-grid-stats bipd-kpis">
        <KpiCard icon={<Percent size={16} />} label={t('bi.current_margin')} value={fmtPct(marginPct)}
          danger={marginPct < 0} warning={marginPct >= 0 && marginPct < 20} />
        <KpiCard icon={<TrendingUp size={16} />} label={t('bi.revenues')} value={fmtMoneda(Number(marginCard?.revenue || 0), { decimales: 0 })} accent />
        <KpiCard icon={<TrendingDown size={16} />} label={t('bi.cost')} value={fmtMoneda(Number(marginCard?.cost || 0), { decimales: 0 })} />
      </div>

      <div className="bipd-grid2">
        <div className="bipd-panel">
          <h2 className="bipd-title">{t('bi.hours_by_week')}</h2>
          <div className="bipd-chart">
            {hoursLoading ? (
              <Spinner label={t('bi.loading')} />
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

        <div className="bipd-panel">
          <h2 className="bipd-title">{t('bi.cost_by_month')}</h2>
          <div className="bipd-chart">
            {costLoading ? (
              <Spinner label={t('bi.loading')} />
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

      <div className="bipd-panel bipd-panel--mt">
        <h2 className="bipd-title">{t('bi.revenue_vs_cost')}</h2>
        <div className="bipd-chart bipd-chart--lg">
          {marginLoading ? (
            <Spinner label={t('bi.loading')} />
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

      <div className="bipd-grid2 bipd-grid2--mt">
        <div className="bipd-panel">
          <h2 className="bipd-title">{t('bi.project_members')}</h2>
          {membersLoading ? (
            <Spinner label={t('bi.loading')} />
          ) : !membersWithUserId.length ? (
            <EmptyState icon={<Users size={28} />} title={t('bi.no_member_data')} />
          ) : (
            <div className="bipd-members">
              <TablaSimple claseTabla="u-table-sm">
                <thead>
                  <tr>
                    <th scope="col">{t('bi.person')}</th>
                    <th scope="col" className="bipd-num">{t('bi.hours')}</th>
                  </tr>
                </thead>
                <tbody>
                  {membersWithUserId.map((m, idx) => {
                    const isSelected = Boolean(selectedUserId) && m.userId === selectedUserId
                    return (
                      <tr
                        key={`${m.label || 'persona'}-${idx}`}
                        onClick={() => m.userId && setSelectedUserId(m.userId)}
                        className={`${m.userId ? 'is-clickable' : ''}${isSelected ? ' is-selected' : ''}`.trim() || undefined}
                      >
                        <td>
                          {m.userId ? (
                            <Pulsable type="button" className="bipd-member-btn" aria-pressed={isSelected}>
                              {m.label || t('bi.no_name')}
                            </Pulsable>
                          ) : (m.label || t('bi.no_name'))}
                        </td>
                        <td className="bipd-num">{fmtNumber(Number(m.value || 0), 1)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </TablaSimple>
            </div>
          )}
        </div>

        <div className="bipd-panel">
          <h2 className="bipd-title">{t('bi.weekly_trend')}</h2>
          {!selectedUserId ? (
            <EmptyState icon={<Users size={28} />} title={t('bi.select_person')} />
          ) : weeklyByPersonLoading || weeklyTeamLoading ? (
            <Spinner label={t('bi.loading')} />
          ) : (
            <div className="bipd-chart bipd-chart--lg bipd-chart--stack">
              <div className="bipd-chart__caption">
                {selectedMember?.label || t('bi.person')} {t('bi.vs_team_avg')}
              </div>
              <div className="bipd-chart__body">
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
            </div>
          )}
        </div>
      </div>
      </div>
    </PageShell>
  )
}
