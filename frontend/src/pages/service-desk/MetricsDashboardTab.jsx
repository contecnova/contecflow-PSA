import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../services/api'
import { Spinner, useSort, SortableTH } from '../../components/ui'
import { COLOR } from '../../constants/theme'

/* ── Helpers ──────────────────────────────────────────────────────────────── */
function fmtMinutes(m) {
  if (m == null || m === 0) return '—'
  if (m < 60) return `${Math.round(m)}m`
  const h = Math.floor(m / 60)
  const min = Math.round(m % 60)
  return min > 0 ? `${h}h ${min}m` : `${h}h`
}

function dateRange(days) {
  const d_to = new Date().toISOString().slice(0, 10)
  const d_from = new Date(Date.now() - days * 86400_000).toISOString().slice(0, 10)
  return { d_from, d_to }
}

/* ── Design tokens (inline so no external CSS needed) ────────────────────── */
const S = {
  card: {
    background: 'var(--surface-2)',
    border: '1px solid var(--surface-4)',
    borderRadius: 14,
    overflow: 'hidden',
  },
  cardPad: { padding: '20px 24px' },
  sectionTitle: {
    fontSize: 11,
    fontWeight: 700,
    color: 'var(--text-3)',
    textTransform: 'uppercase',
    letterSpacing: '0.09em',
    marginBottom: 16,
  },
}

const PRIORITY_META = {
  p1_critical: { label: 'P1 Crítico',  color: COLOR.danger,  bg: COLOR.dangerBg },
  p2_high:     { label: 'P2 Alto',     color: '#fb923c',     bg: 'rgba(251,146,60,0.08)' },
  p3_medium:   { label: 'P3 Medio',    color: COLOR.warning, bg: COLOR.warningBg },
  p4_low:      { label: 'P4 Bajo',     color: COLOR.text2,   bg: 'transparent' },
}

/* ── Sub-components ───────────────────────────────────────────────────────── */
function PeriodButton({ active, label, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '7px 18px',
        borderRadius: 8,
        border: `1px solid ${active ? COLOR.accent : 'var(--surface-4)'}`,
        background: active ? COLOR.accentMuted : 'transparent',
        color: active ? COLOR.accent : 'var(--text-2)',
        fontSize: 12,
        fontWeight: 600,
        cursor: 'pointer',
        fontFamily: 'inherit',
        transition: 'all 0.15s',
      }}
    >
      {label}
    </button>
  )
}

function KpiCard({ label, value, sub, color, icon, accentBar }) {
  const bar = accentBar ?? color ?? COLOR.accent
  return (
    <div style={{ ...S.card, display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 3, background: bar, borderRadius: '14px 14px 0 0' }} />
      <div style={{ ...S.cardPad, flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {icon && (
            <span style={{
              fontSize: 18,
              background: `${bar}18`,
              borderRadius: 8,
              padding: '5px 7px',
              lineHeight: 1,
            }}>
              {icon}
            </span>
          )}
          <span style={{
            fontSize: 10,
            fontWeight: 700,
            color: 'var(--text-3)',
            textTransform: 'uppercase',
            letterSpacing: '0.09em',
          }}>
            {label}
          </span>
        </div>
        <div style={{
          fontSize: 34,
          fontWeight: 700,
          color: color || 'var(--text-1)',
          lineHeight: 1.1,
          letterSpacing: '-0.5px',
        }}>
          {value ?? '—'}
        </div>
        {sub && (
          <div style={{ fontSize: 11, color: 'var(--text-3)', lineHeight: 1.4 }}>{sub}</div>
        )}
      </div>
    </div>
  )
}

function BarRow({ label, count, total, color }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-2)', textTransform: 'capitalize' }}>
          {label.replace(/_/g, ' ')}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: 11,
            fontWeight: 700,
            color: 'var(--text-1)',
            background: 'var(--surface-4)',
            borderRadius: 6,
            padding: '2px 7px',
          }}>
            {count}
          </span>
          <span style={{ fontSize: 11, color: 'var(--text-3)', minWidth: 32, textAlign: 'right' }}>
            {pct}%
          </span>
        </div>
      </div>
      <div style={{
        height: 7,
        background: 'var(--surface-4)',
        borderRadius: 4,
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${pct}%`,
          height: '100%',
          background: color,
          borderRadius: 4,
          transition: 'width 0.6s cubic-bezier(0.4,0,0.2,1)',
        }} />
      </div>
    </div>
  )
}

function RingGauge({ value, color, size = 64 }) {
  const r = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const progress = Math.min(Math.max(value ?? 0, 0), 100) / 100
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', flexShrink: 0 }}>
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

function GaugeCard({ label, value, color, suffix = '%', sub }) {
  return (
    <div style={{ ...S.card, ...S.cardPad, display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <RingGauge value={typeof value === 'number' ? value : 0} color={color} size={68} />
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 12,
          fontWeight: 700,
          color,
        }}>
          {value != null ? `${value}` : '—'}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.09em', marginBottom: 4 }}>
          {label}
        </div>
        <div style={{ fontSize: 26, fontWeight: 700, color, lineHeight: 1, letterSpacing: '-0.5px' }}>
          {value != null ? `${value}${suffix}` : '—'}
        </div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{sub}</div>}
      </div>
    </div>
  )
}

function AgentAvatar({ name }) {
  const initials = (name || '?')
    .split(' ')
    .slice(0, 2)
    .map(w => w[0])
    .join('')
    .toUpperCase()
  const colors = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, '#2dd4bf', '#fb923c']
  const idx = (name || '').charCodeAt(0) % colors.length
  return (
    <div style={{
      width: 32,
      height: 32,
      borderRadius: '50%',
      background: `${colors[idx]}22`,
      border: `1.5px solid ${colors[idx]}44`,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: 11,
      fontWeight: 700,
      color: colors[idx],
      flexShrink: 0,
    }}>
      {initials}
    </div>
  )
}

function ResolutionBar({ resolved, total }) {
  const pct = total > 0 ? Math.round((resolved / total) * 100) : 0
  const color = pct >= 80 ? COLOR.success : pct >= 60 ? COLOR.warning : COLOR.danger
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 100 }}>
      <div style={{ flex: 1, height: 5, background: 'var(--surface-4)', borderRadius: 3 }}>
        <div style={{
          width: `${pct}%`,
          height: '100%',
          background: color,
          borderRadius: 3,
          transition: 'width 0.5s ease',
        }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color, minWidth: 32 }}>{pct}%</span>
    </div>
  )
}

function StarRating({ value }) {
  if (value == null) return <span style={{ color: 'var(--text-3)', fontSize: 12 }}>—</span>
  const filled = Math.round(value)
  const color = value >= 4 ? COLOR.success : value >= 3 ? COLOR.warning : COLOR.danger
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <div style={{ display: 'flex', gap: 2 }}>
        {Array.from({ length: 5 }, (_, i) => (
          <svg key={i} width="10" height="10" viewBox="0 0 10 10">
            <polygon
              points="5,1 6.2,3.5 9,3.8 7,5.7 7.6,8.5 5,7 2.4,8.5 3,5.7 1,3.8 3.8,3.5"
              fill={i < filled ? color : 'var(--surface-4)'}
            />
          </svg>
        ))}
      </div>
      <span style={{ fontSize: 11, fontWeight: 600, color }}>{value.toFixed(1)}</span>
    </div>
  )
}

/* ── Empty state ──────────────────────────────────────────────────────────── */
function EmptyState() {
  return (
    <div style={{
      textAlign: 'center',
      padding: '80px 24px',
      color: 'var(--text-3)',
    }}>
      <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.4 }}>📊</div>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8, color: 'var(--text-2)' }}>
        Sin datos de métricas
      </div>
      <div style={{ fontSize: 13, maxWidth: 280, margin: '0 auto', lineHeight: 1.6 }}>
        Crea y gestiona tickets para ver las métricas ITIL aquí
      </div>
    </div>
  )
}

/* ── Main component ───────────────────────────────────────────────────────── */
export default function MetricsDashboardTab() {
  const [days, setDays] = useState(30)

  const { data: metrics, isLoading } = useQuery({
    queryKey: ['sd-itil-metrics', days],
    queryFn: () => {
      const { d_from, d_to } = dateRange(days)
      return api.get('/sd/metrics/itil', { params: { date_from: d_from, date_to: d_to } }).then(r => r.data)
    },
    staleTime: 60_000,
  })

  const { data: agents } = useQuery({
    queryKey: ['sd-agent-perf', days],
    queryFn: () => {
      const { d_from, d_to } = dateRange(days)
      return api.get('/sd/metrics/agent-performance', { params: { date_from: d_from, date_to: d_to } }).then(r => r.data)
    },
    staleTime: 60_000,
  })

  const { sort: agentSort, setSort: setAgentSort, sortedData: sortedAgents } = useSort(agents || [], 'total', 'desc')

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
        <Spinner />
      </div>
    )
  }

  if (!metrics) return <EmptyState />

  const slaColor = (metrics.sla_compliance_pct ?? 100) >= 95
    ? COLOR.success
    : (metrics.sla_compliance_pct ?? 100) >= 80
      ? COLOR.warning
      : COLOR.danger

  const fcrColor = (metrics.fcr_percent ?? 0) >= 70 ? COLOR.success
    : (metrics.fcr_percent ?? 0) >= 50 ? COLOR.warning
    : COLOR.danger

  const typeEntries = Object.entries(metrics.by_type || {}).sort((a, b) => b[1] - a[1])
  const priorityEntries = Object.entries(metrics.by_priority || {})
  const totalTickets = metrics.volume?.total || 1

  /* palette for type bars */
  const typePalette = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, '#2dd4bf', '#fb923c']

  return (
    <div style={{ padding: '24px 28px', maxWidth: 1400, margin: '0 auto' }}>

      {/* ── Header ── */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 16,
        marginBottom: 28,
      }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: 'var(--text-1)' }}>
            Métricas ITIL
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-3)' }}>
            Service Desk · últimos {days} días
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
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
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
        gap: 14,
        marginBottom: 14,
      }}>
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
          color={metrics.avg_csat >= 4 ? COLOR.success : metrics.avg_csat >= 3 ? COLOR.warning : COLOR.danger}
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
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: 14,
        marginBottom: 20,
      }}>
        <GaugeCard
          label="Cumplimiento SLA"
          value={metrics.sla_compliance_pct}
          color={slaColor}
          sub={metrics.sla_compliance_pct >= 95 ? 'Excelente' : metrics.sla_compliance_pct >= 80 ? 'Aceptable' : 'Por debajo del objetivo'}
        />
        <GaugeCard
          label="FCR — 1er contacto"
          value={metrics.fcr_percent}
          color={fcrColor}
          sub="Resolución en primer contacto"
        />
      </div>

      {/* ── Charts row ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: 14,
        marginBottom: 20,
      }}>
        {/* By type */}
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Volumen por tipo</div>
          </div>
          <div style={{ ...S.cardPad }}>
            {typeEntries.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12, padding: '16px 0' }}>
                Sin datos
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
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Distribución por prioridad</div>
          </div>
          <div style={S.cardPad}>
            {priorityEntries.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12, padding: '16px 0' }}>
                Sin datos
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
        <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={S.sectionTitle}>Rendimiento de agentes</div>
          {sortedAgents.length > 0 && (
            <span style={{
              fontSize: 10,
              fontWeight: 700,
              color: 'var(--text-3)',
              background: 'var(--surface-4)',
              borderRadius: 12,
              padding: '2px 8px',
              marginLeft: 4,
              marginTop: -14,
            }}>
              {sortedAgents.length}
            </span>
          )}
        </div>

        {sortedAgents.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12, padding: '32px 0' }}>
            Sin datos de agentes en este período
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--surface-3)' }}>
                  {[
                    { col: 'agent_name', label: 'Agente' },
                    { col: 'total', label: 'Total' },
                    { col: 'resolved', label: 'Tasa resolución' },
                    { col: 'mttr_minutes', label: 'MTTR' },
                    { col: 'avg_csat', label: 'CSAT' },
                    { col: 'sla_breaches', label: 'Breaches SLA' },
                  ].map(({ col, label }) => (
                    <th
                      key={col}
                      style={{
                        padding: '10px 16px',
                        textAlign: col === 'agent_name' ? 'left' : 'center',
                        fontSize: 10,
                        fontWeight: 700,
                        color: 'var(--text-3)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.08em',
                        whiteSpace: 'nowrap',
                      }}
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
                  <tr
                    key={a.agent_id}
                    style={{
                      borderBottom: '1px solid var(--surface-4)',
                      background: idx % 2 === 0 ? 'transparent' : 'var(--surface-3)08',
                    }}
                  >
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <AgentAvatar name={a.agent_name} />
                        <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-1)' }}>
                          {a.agent_name}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      <span style={{
                        fontSize: 15,
                        fontWeight: 700,
                        color: 'var(--text-1)',
                      }}>
                        {a.total}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', minWidth: 160 }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <ResolutionBar resolved={a.resolved} total={a.total} />
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      <span style={{
                        fontSize: 12,
                        fontWeight: 600,
                        color: 'var(--text-2)',
                        background: 'var(--surface-4)',
                        padding: '3px 8px',
                        borderRadius: 6,
                        whiteSpace: 'nowrap',
                      }}>
                        {fmtMinutes(a.mttr_minutes)}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ display: 'flex', justifyContent: 'center' }}>
                        <StarRating value={a.avg_csat ? Number(a.avg_csat) : null} />
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      {a.sla_breaches > 0 ? (
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          fontSize: 12,
                          fontWeight: 700,
                          color: COLOR.danger,
                          background: COLOR.dangerBg,
                          border: `1px solid ${COLOR.dangerBorder}`,
                          borderRadius: 6,
                          padding: '3px 9px',
                        }}>
                          ⚠ {a.sla_breaches}
                        </span>
                      ) : (
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          fontSize: 12,
                          fontWeight: 700,
                          color: COLOR.success,
                          background: COLOR.successBg,
                          border: `1px solid ${COLOR.successBorder}`,
                          borderRadius: 6,
                          padding: '3px 9px',
                        }}>
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

    </div>
  )
}
