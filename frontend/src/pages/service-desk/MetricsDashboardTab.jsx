import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import api from '../../services/api'
import DashboardGrid from '../../components/dashboard/DashboardGrid'
import { Spinner, useSort, SortableTH } from '../../components/ui'
import { COLOR } from '../../constants/theme'

const PRIORITY_COLOR = {
  p1_critical: COLOR.danger,
  p2_high: '#fb923c',
  p3_medium: COLOR.warning,
  p4_low: COLOR.text2,
}

const PRIORITY_LABEL = {
  p1_critical: 'P1 Critico',
  p2_high: 'P2 Alto',
  p3_medium: 'P3 Medio',
  p4_low: 'P4 Bajo',
}

function fmtMinutes(m) {
  if (!m) return '-'
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  const min = Math.round(m % 60)
  return min > 0 ? `${h}h ${min}m` : `${h}h`
}

function KpiCard({ label, value, sub, color, icon }) {
  return (
    <div style={{
      background: 'var(--surface-2)',
      border: '1px solid var(--surface-4)',
      borderRadius: 12,
      padding: '16px 20px',
      display: 'flex',
      gap: 14,
      alignItems: 'center',
    }}>
      {icon && <div style={{ fontSize: 24 }}>{icon}</div>}
      <div>
        <div style={{
          fontSize: 11,
          color: 'var(--text-2)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          marginBottom: 4,
        }}>{label}</div>
        <div style={{
          fontSize: 26,
          fontWeight: 600,
          color: color || 'var(--text-1)',
          lineHeight: 1,
        }}>{value ?? '-'}</div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3 }}>{sub}</div>}
      </div>
    </div>
  )
}

const SD_METRICS_WIDGETS = [
  { id: 'kpis', title: 'KPIs ITIL', icon: '📊', fitContent: true, fitContentExtraPx: 12, defaultPos: { x: 0, y: 0, w: 12, h: 4, minW: 6, minH: 3 } },
  { id: 'byType', title: 'Volumen por tipo', icon: '🗂', fitContent: true, fitContentExtraPx: 12, defaultPos: { x: 0, y: 4, w: 6, h: 6, minW: 4, minH: 3 } },
  { id: 'byPriority', title: 'Distribucion prioridad', icon: '🚨', fitContent: true, fitContentExtraPx: 12, defaultPos: { x: 6, y: 4, w: 6, h: 6, minW: 4, minH: 3 } },
  { id: 'agents', title: 'Rendimiento agentes', icon: '👥', fitContent: true, fitContentExtraPx: 12, fitContentMaxRows: 14, defaultPos: { x: 0, y: 10, w: 12, h: 8, minW: 6, minH: 4 } },
]

export default function MetricsDashboardTab() {
  const [days, setDays] = useState(30)
  const { data: metrics, isLoading } = useQuery({
    queryKey: ['sd-itil-metrics', days],
    queryFn: () => {
      const d_to = new Date().toISOString().slice(0, 10)
      const d_from = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10)
      return api.get('/sd/metrics/itil', { params: { date_from: d_from, date_to: d_to } }).then(r => r.data)
    },
    staleTime: 60000,
  })

  const { data: agents } = useQuery({
    queryKey: ['sd-agent-perf', days],
    queryFn: () => {
      const d_to = new Date().toISOString().slice(0, 10)
      const d_from = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10)
      return api.get('/sd/metrics/agent-performance', { params: { date_from: d_from, date_to: d_to } }).then(r => r.data)
    },
  })

  const { sort: agentSort, setSort: setAgentSort, sortedData: sortedAgents } = useSort(agents || [], 'total', 'desc')

  if (isLoading) return <div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>
  if (!metrics) {
    return (
      <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-3)' }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>📊</div>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Sin datos de metricas</div>
        <div style={{ fontSize: 12 }}>Crea y gestiona tickets para ver las metricas ITIL aqui</div>
      </div>
    )
  }

  const slaColor = (metrics.sla_compliance_pct ?? 100) >= 95
    ? COLOR.success
    : (metrics.sla_compliance_pct ?? 100) >= 80
      ? COLOR.warning
      : COLOR.danger

  const periodSelector = (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {[7, 30, 90].map(d => (
        <button key={d} onClick={() => setDays(d)} style={{
          padding: '6px 16px',
          borderRadius: 8,
          border: '1px solid var(--surface-4)',
          background: days === d ? 'var(--accent-muted)' : 'transparent',
          color: days === d ? 'var(--accent)' : 'var(--text-2)',
          fontSize: 12,
          fontWeight: 600,
          cursor: 'pointer',
          fontFamily: 'inherit',
        }}>Ultimos {d}d</button>
      ))}
    </div>
  )

  const renderWidget = (id) => {
    switch (id) {
      case 'kpis':
        return (
          <div style={{ padding: '8px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px,1fr))', gap: 12 }}>
              <KpiCard icon="🎫" label="Tickets totales" value={metrics.volume?.total} />
              <KpiCard icon="🔓" label="Tickets abiertos" value={metrics.volume?.open} color={metrics.volume?.open > 20 ? COLOR.warning : COLOR.text1} />
              <KpiCard icon="✅" label="Tickets resueltos" value={metrics.volume?.resolved} color={COLOR.success} />
              <KpiCard icon="⏱" label="MTTR" value={fmtMinutes(metrics.mttr_minutes)} sub="Tiempo medio resolucion" color={COLOR.accent} />
              <KpiCard icon="🎯" label="Cumplimiento SLA" value={`${metrics.sla_compliance_pct}%`} color={slaColor} />
              <KpiCard icon="📞" label="FCR" value={`${metrics.fcr_percent}%`} sub="Resolucion 1er contacto" color={metrics.fcr_percent >= 70 ? COLOR.success : COLOR.warning} />
              <KpiCard icon="⭐" label="CSAT medio" value={metrics.avg_csat ? `${metrics.avg_csat}/5` : '-'} color={COLOR.warning} />
              <KpiCard icon="🚨" label="Brechas SLA" value={metrics.volume?.breached_sla} color={metrics.volume?.breached_sla > 0 ? COLOR.danger : COLOR.success} />
            </div>
          </div>
        )
      case 'byType':
        return (
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 20, boxSizing: 'border-box' }}>
            {Object.entries(metrics.by_type || {}).map(([type, count]) => {
              const total = metrics.volume?.total || 1
              const pct = Math.round(count / total * 100)
              return (
                <div key={type} style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                    <span style={{ color: 'var(--text-2)', textTransform: 'capitalize' }}>{type.replace(/_/g, ' ')}</span>
                    <span style={{ color: 'var(--text-1)', fontWeight: 600 }}>{count} ({pct}%)</span>
                  </div>
                  <div style={{ height: 5, background: 'var(--surface-4)', borderRadius: 3 }}>
                    <div style={{ width: `${pct}%`, height: '100%', background: COLOR.accent, borderRadius: 3 }} />
                  </div>
                </div>
              )
            })}
          </div>
        )
      case 'byPriority':
        return (
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 20, boxSizing: 'border-box' }}>
            {Object.entries(metrics.by_priority || {}).map(([prio, count]) => {
              const total = metrics.volume?.total || 1
              const pct = Math.round(count / total * 100)
              const color = PRIORITY_COLOR[prio] || COLOR.text2
              return (
                <div key={prio} style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                    <span style={{ color }}>{PRIORITY_LABEL[prio] || prio}</span>
                    <span style={{ color: 'var(--text-1)', fontWeight: 600 }}>{count} ({pct}%)</span>
                  </div>
                  <div style={{ height: 5, background: 'var(--surface-4)', borderRadius: 3 }}>
                    <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3 }} />
                  </div>
                </div>
              )
            })}
          </div>
        )
      case 'agents':
        return agents?.length > 0 ? (
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 20, boxSizing: 'border-box' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
                  <th style={{ padding: '8px 12px' }}><SortableTH col="agent_name" sort={agentSort} onSort={setAgentSort}>Agente</SortableTH></th>
                  <th style={{ padding: '8px 12px' }}><SortableTH col="total" sort={agentSort} onSort={setAgentSort}>Total</SortableTH></th>
                  <th style={{ padding: '8px 12px' }}><SortableTH col="resolved" sort={agentSort} onSort={setAgentSort}>Resueltos</SortableTH></th>
                  <th style={{ padding: '8px 12px' }}><SortableTH col="mttr_minutes" sort={agentSort} onSort={setAgentSort}>MTTR</SortableTH></th>
                  <th style={{ padding: '8px 12px' }}><SortableTH col="avg_csat" sort={agentSort} onSort={setAgentSort}>CSAT</SortableTH></th>
                  <th style={{ padding: '8px 12px' }}><SortableTH col="sla_breaches" sort={agentSort} onSort={setAgentSort}>Breaches SLA</SortableTH></th>
                </tr>
              </thead>
              <tbody>
                {sortedAgents.map(a => (
                  <tr key={a.agent_id} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                    <td style={{ padding: '10px 12px', fontSize: 13, color: 'var(--text-1)' }}>{a.agent_name}</td>
                    <td style={{ padding: '10px 12px', fontSize: 13 }}>{a.total}</td>
                    <td style={{ padding: '10px 12px', fontSize: 13, color: COLOR.success }}>{a.resolved}</td>
                    <td style={{ padding: '10px 12px', fontSize: 12, color: 'var(--text-2)' }}>{fmtMinutes(a.mttr_minutes)}</td>
                    <td style={{ padding: '10px 12px', fontSize: 12, color: COLOR.warning }}>{a.avg_csat ? `${a.avg_csat}/5` : '-'}</td>
                    <td style={{ padding: '10px 12px', fontSize: 12, color: a.sla_breaches > 0 ? COLOR.danger : COLOR.success }}>{a.sla_breaches}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>Sin rendimiento de agentes</div>
        )
      default:
        return null
    }
  }

  return (
    <DashboardGrid
      storageKey="sd-metrics-dashboard-layout"
      title="Metricas ITIL"
      subtitle={`Service Desk · Ultimos ${days} dias`}
      allWidgets={SD_METRICS_WIDGETS}
      renderWidget={renderWidget}
      api={api}
      headerExtra={periodSelector}
    />
  )
}
