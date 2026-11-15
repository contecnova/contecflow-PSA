import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { sdMetricsApi } from '../../services/api'
import type { SdRendimientoDeAgente } from '../../services/api/tipos-sd'
import { Spinner, EmptyState, useSort, SortableTH, ariaSort } from '../../components/ui'
import { KpiCard } from '../../components/dashboard/DashKit'
import { COLOR, alpha } from '../../constants/theme'
import PageShell from '../../components/layout/PageShell'
import { useAppLang } from '../../i18n/AppLangContext'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import './MetricsDashboardTab.css'

/* ── Helpers ──────────────────────────────────────────────────────────────── */
function fmtMinutes(m: number | null | undefined) {
  if (m == null || m === 0) return '—'
  if (m < 60) return `${Math.round(m)}m`
  const h = Math.floor(m / 60)
  const min = Math.round(m % 60)
  return min > 0 ? `${h}h ${min}m` : `${h}h`
}

function dateRange(days: number) {
  const d_to = new Date().toISOString().slice(0, 10)
  const d_from = new Date(Date.now() - days * 86400_000).toISOString().slice(0, 10)
  return { d_from, d_to }
}

/* ── Design tokens (inline so no external CSS needed) ────────────────────── */
const S: Record<string, CSSProperties> = {
  card: {
    background: 'var(--surface-2)',
    border: '1px solid var(--surface-4)',
    borderRadius: 'var(--radius-lg)',
    overflow: 'hidden',
  },
  cardPad: { padding: '20px 24px' },
  sectionTitle: {
    fontSize: "var(--text-xs)",
    fontWeight: 700,
    color: 'var(--text-3)',
    textTransform: 'uppercase',
    letterSpacing: '0.09em',
    marginBottom: 16,
  },
}

const PRIORITY_META: Record<string, { label: string; color: string; bg: string }> = {
  p1_critical: { label: 'P1 Crítico',  color: COLOR.danger,  bg: COLOR.dangerBg },
  p2_high:     { label: 'P2 Alto',     color: COLOR.orange,  bg: 'var(--orange-bg)' },
  p3_medium:   { label: 'P3 Medio',    color: COLOR.warning, bg: COLOR.warningBg },
  p4_low:      { label: 'P4 Bajo',     color: COLOR.text2,   bg: 'transparent' },
}

/* ── Sub-components ───────────────────────────────────────────────────────── */
function PeriodButton({ active, label, onClick }: { active: boolean; label: ReactNode; onClick: () => void }) {
  return (
    <button className="medata-box-17"
      onClick={onClick}
      style={{ borderRadius: 8, border: `1px solid ${active ? COLOR.accent : 'var(--surface-4)'}`, background: active ? COLOR.accentMuted : 'transparent', color: active ? COLOR.accent : 'var(--text-2)' }}
    >
      {label}
    </button>
  )
}

function BarRow({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  return (
    <div className="u-mb-14">
      <div className="medata-row-1">
        <span className="medata-txt-1">
          {label.replace(/_/g, ' ')}
        </span>
        <div className="u-row-center-8">
          <span className="medata-box-1">
            {count}
          </span>
          <span className="medata-box-2">
            {pct}%
          </span>
        </div>
      </div>
      <div className="medata-box-3">
        <div className="medata-box-18" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}

function RingGauge({ value, color, size = 64 }: { value?: number | null; color?: string; size?: number }) {
  const r = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const progress = Math.min(Math.max(value ?? 0, 0), 100) / 100
  return (
    <svg width={size} height={size} className="medata-box-4">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-4)" strokeWidth={7} />
      <circle
        cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke={color} strokeWidth={7}
        strokeDasharray={circ}
        strokeDashoffset={circ * (1 - progress)}
        strokeLinecap="round"
      />
    </svg>
  )
}

function GaugeCard({ label, value, color, suffix = '%', sub }: { label?: ReactNode; value?: number | null; color?: string; suffix?: string; sub?: ReactNode }) {
  return (
    <div style={{ ...S.card, ...S.cardPad, display: 'flex', alignItems: 'center', gap: 16 }}>
      <div className="medata-box-5">
        <RingGauge value={typeof value === 'number' ? value : 0} color={color} size={68} />
        <div className="medata-row-9" style={{ color }}>
          {value != null ? `${value}` : '—'}
        </div>
      </div>
      <div>
        <div className="medata-box-6">
          {label}
        </div>
        <div className="medata-txt-4" style={{ color }}>
          {value != null ? `${value}${suffix}` : '—'}
        </div>
        {sub && <div className="u-hint">{sub}</div>}
      </div>
    </div>
  )
}

function AgentAvatar({ name }: { name?: string }) {
  const initials = (name || '?')
    .split(' ')
    .slice(0, 2)
    .map((w: string) => w[0])
    .join('')
    .toUpperCase()
  const colors = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, 'var(--chart-teal)', 'var(--orange)']
  const idx = (name || '').charCodeAt(0) % colors.length
  return (
    <div className="medata-row-10" style={{ borderRadius: '50%', background: alpha(colors[idx], '22'), border: `1.5px solid ${alpha(colors[idx], '44')}`, color: colors[idx] }}>
      {initials}
    </div>
  )
}

function ResolutionBar({ resolved, total }: { resolved: number; total: number }) {
  const pct = total > 0 ? Math.round((resolved / total) * 100) : 0
  const color = pct >= 80 ? COLOR.success : pct >= 60 ? COLOR.warning : COLOR.danger
  return (
    <div className="medata-row-2">
      <div className="medata-box-7">
        <div className="medata-box-19" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="medata-box-20" style={{ color }}>{pct}%</span>
    </div>
  )
}

function StarRating({ value }: { value: number | null }) {
  if (value == null) return <span className="u-text3-sm">—</span>
  const filled = Math.round(value)
  const color = value >= 4 ? COLOR.success : value >= 3 ? COLOR.warning : COLOR.danger
  return (
    <div className="medata-row-3">
      <div className="medata-row-4">
        {Array.from({ length: 5 }, (_, i) => (
          <svg key={i} width="10" height="10" viewBox="0 0 10 10">
            <polygon
              points="5,1 6.2,3.5 9,3.8 7,5.7 7.6,8.5 5,7 2.4,8.5 3,5.7 1,3.8 3.8,3.5"
              fill={i < filled ? color : 'var(--surface-4)'}
            />
          </svg>
        ))}
      </div>
      <span className="medata-txt-5" style={{ color }}>{value.toFixed(1)}</span>
    </div>
  )
}

/* ── Empty state ──────────────────────────────────────────────────────────── */
/* ── Main component ───────────────────────────────────────────────────────── */
type AgentPerf = SdRendimientoDeAgente

export default function MetricsDashboardTab() {
  const { t } = useAppLang()
  const [days, setDays] = useState(30)

  const { data: metrics, isLoading } = useQuery({
    queryKey: ['sd-itil-metrics', days],
    queryFn: () => {
      const { d_from, d_to } = dateRange(days)
      return sdMetricsApi.itil({ date_from: d_from, date_to: d_to }).then(r => r.data)
    },
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: agents } = useQuery({
    queryKey: ['sd-agent-perf', days],
    queryFn: () => {
      const { d_from, d_to } = dateRange(days)
      return sdMetricsApi.agentPerformance({ date_from: d_from, date_to: d_to }).then(r => r.data)
    },
    staleTime: STALE_DEFAULT_MS,
  })

  const { sort: agentSort, setSort: setAgentSort, sortedData: sortedAgents } = useSort<AgentPerf>(agents || [], 'total', 'desc')

  if (isLoading) {
    return (
      <div className="medata-row-5">
        <Spinner />
      </div>
    )
  }

  if (!metrics) return <EmptyState icon="📊" title={t('metricsdashboard.sin_datos_de_metricas')} description={t('metricsdashboard.crea_y_gestiona_tickets_para_ver_las')} />

  const slaColor = (metrics.sla_compliance_pct ?? 100) >= 95
    ? COLOR.success
    : (metrics.sla_compliance_pct ?? 100) >= 80
      ? COLOR.warning
      : COLOR.danger

  const fcrColor = (metrics.fcr_percent ?? 0) >= 70 ? COLOR.success
    : (metrics.fcr_percent ?? 0) >= 50 ? COLOR.warning
    : COLOR.danger

  const typeEntries = Object.entries<number>(metrics.by_type || {}).sort((a, b) => b[1] - a[1])
  const priorityEntries = Object.entries<number>(metrics.by_priority || {})
  const totalTickets = metrics.volume?.total || 1

  /* palette for type bars */
  const typePalette = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, 'var(--chart-teal)', 'var(--orange)']

  return (
    <PageShell>

      {/* ── Header ── */}
      <div className="medata-row-6">
        <div>
          <h2 className="medata-box-8">
            {t('metricsdashboard.metricas_itil')}
          </h2>
          <p className="medata-box-9">
            {t('metricsdashboard.service_desk_ultimos')} {days} {t('metricsdashboard.dias')}
          </p>
        </div>
        <div className="u-row-6">
          {[7, 30, 90].map(d => (
            <PeriodButton
              key={d}
              active={days === d}
              label={`${d}d`}
              onClick={() => setDays(d)}
            />
          ))}
        </div>
      </div>

      {/* ── KPI row: volume ── */}
      <div className="medata-grid-1">
        <KpiCard
          icon="🎫"
          label="Tickets totales"
          value={metrics.volume?.total ?? 0}
          color="var(--text-1)"
          accentBar={COLOR.accent}
        />
        <KpiCard
          icon="🔓"
          label="Abiertos"
          value={metrics.volume?.open ?? 0}
          color={(metrics.volume?.open ?? 0) > 20 ? COLOR.warning : 'var(--text-1)'}
          accentBar={(metrics.volume?.open ?? 0) > 20 ? COLOR.warning : COLOR.accent}
        />
        <KpiCard
          icon="✅"
          label="Resueltos"
          value={metrics.volume?.resolved ?? 0}
          color={COLOR.success}
          accentBar={COLOR.success}
        />
        <KpiCard
          icon="⏱"
          label="MTTR"
          value={fmtMinutes(metrics.mttr_minutes)}
          sub="Tiempo medio resolución"
          color={COLOR.accent}
          accentBar={COLOR.accent}
        />
        <KpiCard
          icon="⭐"
          label="CSAT medio"
          value={metrics.avg_csat ? `${Number(metrics.avg_csat).toFixed(1)}/5` : '—'}
          color={(metrics.avg_csat ?? 0) >= 4 ? COLOR.success : (metrics.avg_csat ?? 0) >= 3 ? COLOR.warning : COLOR.danger}
          accentBar={COLOR.warning}
        />
        <KpiCard
          icon="🚨"
          label="Brechas SLA"
          value={metrics.volume?.breached_sla ?? 0}
          color={(metrics.volume?.breached_sla ?? 0) > 0 ? COLOR.danger : COLOR.success}
          accentBar={(metrics.volume?.breached_sla ?? 0) > 0 ? COLOR.danger : COLOR.success}
        />
      </div>

      {/* ── SLA + FCR gauges ── */}
      <div className="medata-grid-2">
        <GaugeCard
          label="Cumplimiento SLA"
          value={metrics.sla_compliance_pct}
          color={slaColor}
          sub={(metrics.sla_compliance_pct ?? 0) >= 95 ? 'Excelente' : (metrics.sla_compliance_pct ?? 0) >= 80 ? 'Aceptable' : 'Por debajo del objetivo'}
        />
        <GaugeCard
          label="FCR — 1er contacto"
          value={metrics.fcr_percent}
          color={fcrColor}
          sub="Resolución en primer contacto"
        />
      </div>

      {/* ── Charts row ── */}
      <div className="medata-grid-3">
        {/* By type */}
        <div style={S.card}>
          <div className="medata-cardpad">
            <div style={S.sectionTitle}>{t('metricsdashboard.volumen_por_tipo')}</div>
          </div>
          <div className="medata-cardpad2">
            {typeEntries.length === 0 ? (
              <div className="medata-box-10">
                {t('metricsdashboard.sin_datos')}
              </div>
            ) : (
              typeEntries.map(([type, count], i) => (
                <BarRow
                  key={type}
                  label={type}
                  count={count}
                  total={totalTickets}
                  color={typePalette[i % typePalette.length]}
                />
              ))
            )}
          </div>
        </div>

        {/* By priority */}
        <div style={S.card}>
          <div className="medata-cardpad">
            <div style={S.sectionTitle}>{t('metricsdashboard.distribucion_por_prioridad')}</div>
          </div>
          <div style={S.cardPad}>
            {priorityEntries.length === 0 ? (
              <div className="medata-box-10">
                {t('metricsdashboard.sin_datos')}
              </div>
            ) : (
              priorityEntries.map(([prio, count]) => {
                const meta = PRIORITY_META[prio] || { label: prio, color: COLOR.text2 }
                return (
                  <BarRow
                    key={prio}
                    label={meta.label}
                    count={count}
                    total={totalTickets}
                    color={meta.color}
                  />
                )
              })
            )}
          </div>
        </div>
      </div>

      {/* ── Agent performance ── */}
      <div style={S.card}>
        <div className="medata-cardpad3">
          <div style={S.sectionTitle}>{t('metricsdashboard.rendimiento_de_agentes')}</div>
          {sortedAgents.length > 0 && (
            <span className="medata-box-11">
              {sortedAgents.length}
            </span>
          )}
        </div>

        {sortedAgents.length === 0 ? (
          <div className="medata-box-12">
            {t('metricsdashboard.sin_datos_de_agentes_en_este_periodo')}
          </div>
        ) : (
          <div className="u-scroll-x">
            <table className="u-table">
              <thead>
                <tr className="medata-box-13">
                  {[
                    { col: 'agent_name', label: 'Agente' },
                    { col: 'total', label: 'Total' },
                    { col: 'resolved', label: 'Tasa resolución' },
                    { col: 'mttr_minutes', label: 'MTTR' },
                    { col: 'avg_csat', label: 'CSAT' },
                    { col: 'sla_breaches', label: 'Breaches SLA' },
                  ].map(({ col, label }) => (
                    <th className="medata-box-21" aria-sort={ariaSort(agentSort, col)}
                      key={col}
                      style={{ textAlign: col === 'agent_name' ? 'left' : 'center' }}
                    >
                      <SortableTH col={col} sort={agentSort} onSort={setAgentSort}>
                        {label}
                      </SortableTH>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedAgents.map((a, idx) => (
                  <tr className="medata-box-22"
                    key={a.agent_id}
                    style={{ background: idx % 2 === 0 ? 'transparent' : 'color-mix(in srgb, var(--surface-3) 3%, transparent)' }}
                  >
                    <td className="medata-sp-1">
                      <div className="u-row-center-10">
                        <AgentAvatar name={a.agent_name} />
                        <span className="medata-txt-2">
                          {a.agent_name}
                        </span>
                      </div>
                    </td>
                    <td className="medata-box-14">
                      <span className="medata-txt-3">
                        {a.total}
                      </span>
                    </td>
                    <td className="medata-box-15">
                      <div className="medata-row-7">
                        <ResolutionBar resolved={a.resolved} total={a.total} />
                      </div>
                    </td>
                    <td className="medata-box-14">
                      <span className="medata-box-16">
                        {fmtMinutes(a.mttr_minutes)}
                      </span>
                    </td>
                    <td className="medata-sp-1">
                      <div className="medata-row-8">
                        <StarRating value={a.avg_csat ? Number(a.avg_csat) : null} />
                      </div>
                    </td>
                    <td className="medata-box-14">
                      {a.sla_breaches > 0 ? (
                        <span className="medata-row-11" style={{ color: COLOR.danger, background: COLOR.dangerBg, border: `1px solid ${COLOR.dangerBorder}`, borderRadius: 'var(--radius-sm)' }}>
                          ⚠ {a.sla_breaches}
                        </span>
                      ) : (
                        <span className="medata-row-11" style={{ color: COLOR.success, background: COLOR.successBg, border: `1px solid ${COLOR.successBorder}`, borderRadius: 'var(--radius-sm)' }}>
                          ✓ 0
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </PageShell>
  )
}
