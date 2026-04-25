import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { Spinner } from '../components/ui'
import { DollarSign } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import {
  COLOR, S, DashPageShell, KpiCard, GaugeCard, BarRow, SectionCard, DashEmpty,
  dateRange, fmtCur, typePalette,
} from '../components/dashboard/DashKit'

export default function FinanceDashboardPage() {
  const [days, setDays] = useState(90)
  const { lang } = useAppLang()
  const params = dateRange(days)

  const { data: profitSummary, isLoading: lp } = useQuery({
    queryKey: ['fin-dash-profit', days],
    queryFn: () => api.get('/profitability/summary', { params: { ...params, period: 'custom' } }).then(r => r.data).catch(() => null),
    staleTime: 60_000,
  })

  const { data: clients = [], isLoading: lc } = useQuery({
    queryKey: ['fin-dash-clients'],
    queryFn: () => api.get('/clients', { params: { page_size: 200 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  const { data: pipeline = [] } = useQuery({
    queryKey: ['fin-dash-pipeline'],
    queryFn: () => api.get('/pipeline', { params: { page_size: 100 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  const { data: invoicesData } = useQuery({
    queryKey: ['fin-dash-invoices'],
    queryFn: () => api.get('/invoices', { params: { page_size: 200 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items || [])
    }).catch(() => []),
    staleTime: 60_000,
  })

  const { data: topProjects = [] } = useQuery({
    queryKey: ['fin-dash-top-proj', days],
    queryFn: () => api.get('/profitability/projects', { params }).then(r => r.data).catch(() => []),
    staleTime: 60_000,
  })

  if (lp || lc) return (
    <div style={{ padding: 32, display: 'flex', justifyContent: 'center', minHeight: 300, alignItems: 'center' }}>
      <Spinner />
    </div>
  )

  const revenue   = profitSummary?.total_revenue ?? 0
  const costs     = profitSummary?.total_cost ?? 0
  const margin    = revenue - costs
  const marginPct = revenue > 0 ? Math.round((margin / revenue) * 100) : null
  const marginColor = marginPct == null ? COLOR.accent : marginPct >= 30 ? COLOR.success : marginPct >= 15 ? COLOR.warning : COLOR.danger

  const invoices        = Array.isArray(invoicesData) ? invoicesData : []
  const pendingInvoices = invoices.filter(i => i.status === 'pending' || i.status === 'sent')
  const overdueInvoices = invoices.filter(i => i.status === 'overdue')
  const pendingAmount   = pendingInvoices.reduce((s, i) => s + (i.amount || i.total || 0), 0)
  const overdueAmount   = overdueInvoices.reduce((s, i) => s + (i.amount || i.total || 0), 0)

  const activeClients    = clients.filter(c => c.status === 'active').length
  const pipelineValue    = pipeline.reduce((s, o) => s + (o.value || o.amount || 0), 0)
  const openOpportunities = pipeline.filter(o => o.status !== 'closed_won' && o.status !== 'closed_lost').length

  const clientRows = clients
    .filter(c => (c.revenue || 0) > 0)
    .sort((a, b) => (b.revenue || 0) - (a.revenue || 0))
    .slice(0, 6)
  const maxRevenue = clientRows[0]?.revenue || 1

  const pipelineByStage = pipeline.reduce((acc, o) => {
    const stage = o.stage || o.status || 'Sin etapa'
    if (!acc[stage]) acc[stage] = { count: 0, value: 0 }
    acc[stage].count += 1
    acc[stage].value += (o.value || o.amount || 0)
    return acc
  }, {})
  const stageRows = Object.entries(pipelineByStage)
    .sort((a, b) => b[1].value - a[1].value)
  const maxStageValue = Math.max(...stageRows.map(([, v]) => v.value), 1)

  return (
    <DashPageShell
      icon={<DollarSign size={18} />}
      title="Clientes y Finanzas"
      subtitle="Rentabilidad, facturación, cartera de clientes y pipeline comercial"
      days={days} setDays={setDays}
      periods={[30, 90, 365]}
    >
      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 14, marginBottom: 14 }}>
        <KpiCard icon="📈" label="Ingresos"
          value={fmtCur(revenue, lang)}
          color={COLOR.accent} accentBar={COLOR.accent} />
        <KpiCard icon="💸" label="Costes"
          value={fmtCur(costs, lang)}
          color={COLOR.warning} accentBar={COLOR.warning} />
        <KpiCard icon="✅" label="Margen bruto"
          value={fmtCur(margin, lang)}
          color={margin >= 0 ? COLOR.success : COLOR.danger}
          accentBar={margin >= 0 ? COLOR.success : COLOR.danger}
          sub={marginPct != null ? `${marginPct}% de margen` : undefined} />
        <KpiCard icon="🏢" label="Clientes activos"
          value={activeClients} color={COLOR.accent} accentBar={COLOR.accent}
          sub={`${clients.length} total`} />
        <KpiCard icon="🎯" label="Pipeline"
          value={fmtCur(pipelineValue, lang)}
          color={COLOR.purple} accentBar={COLOR.purple}
          sub={`${openOpportunities} oportunidades abiertas`} />
        <KpiCard icon="📄" label="Facturas pendientes"
          value={fmtCur(pendingAmount, lang)}
          color={overdueAmount > 0 ? COLOR.danger : COLOR.warning}
          accentBar={overdueAmount > 0 ? COLOR.danger : COLOR.warning}
          sub={overdueAmount > 0 ? `${fmtCur(overdueAmount, lang)} vencidas` : `${pendingInvoices.length} por cobrar`} />
      </div>

      {/* Gauges */}
      {marginPct != null && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginBottom: 20 }}>
          <GaugeCard label="Margen bruto"
            value={marginPct} color={marginColor}
            sub={marginPct >= 30 ? 'Rentabilidad excelente' : marginPct >= 15 ? 'Rentabilidad aceptable' : 'Margen bajo — revisar costes'} />
          {pendingAmount > 0 && revenue > 0 && (
            <GaugeCard label="Cobrado vs facturado"
              value={Math.round(((revenue - pendingAmount) / revenue) * 100)}
              color={COLOR.success}
              sub={`${fmtCur(pendingAmount, lang)} pendiente de cobro`} />
          )}
          {pipelineValue > 0 && revenue > 0 && (
            <GaugeCard label="Pipeline / ingresos"
              value={Math.min(Math.round((pipelineValue / revenue) * 100), 999)}
              suffix="%" color={COLOR.purple}
              sub="Ratio pipeline sobre ingresos actuales" />
          )}
        </div>
      )}

      {/* Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14, marginBottom: 20 }}>
        {/* Top clients */}
        <SectionCard title="Top clientes por ingresos" badge={clientRows.length}>
          {clientRows.length === 0
            ? <DashEmpty icon="🏢" title="Sin datos de ingresos por cliente" description="Asocia proyectos e ingresos a clientes para ver esta métrica" />
            : clientRows.map((c, i) => (
                <BarRow key={c.id || c.name}
                  label={c.name || c.short_name || 'Cliente'}
                  count={c.revenue || 0}
                  total={maxRevenue}
                  color={typePalette[i % typePalette.length]}
                  displayValue={fmtCur(c.revenue, lang)} />
              ))
          }
        </SectionCard>

        {/* Pipeline by stage */}
        <SectionCard title="Pipeline por etapa" badge={openOpportunities}>
          {stageRows.length === 0
            ? <DashEmpty icon="🎯" title="Sin oportunidades en pipeline" />
            : stageRows.map(([stage, data], i) => (
                <BarRow key={stage}
                  label={stage}
                  count={data.value}
                  total={maxStageValue}
                  color={typePalette[i % typePalette.length]}
                  displayValue={`${fmtCur(data.value, lang)} (${data.count})`} />
              ))
          }
        </SectionCard>
      </div>

      {/* Top projects by margin */}
      {topProjects.length > 0 && (
        <SectionCard title="Rentabilidad por proyecto" badge={topProjects.length}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--surface-3)' }}>
                  {['Proyecto', 'Ingresos', 'Costes', 'Margen', '%'].map((col, i) => (
                    <th key={col} style={{
                      padding: '10px 16px',
                      textAlign: i === 0 ? 'left' : 'center',
                      fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
                      textTransform: 'uppercase', letterSpacing: '0.08em',
                    }}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {topProjects.slice(0, 8).map((p, idx) => {
                  const rev  = p.revenue_actual ?? p.budget_amount ?? 0
                  const cost = p.cost_actual ?? 0
                  const mgn  = rev - cost
                  const pct  = rev > 0 ? Math.round((mgn / rev) * 100) : 0
                  const mColor = pct >= 30 ? COLOR.success : pct >= 15 ? COLOR.warning : COLOR.danger
                  return (
                    <tr key={p.project_id || p.id} style={{
                      borderBottom: '1px solid var(--surface-4)',
                      background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)',
                    }}>
                      <td style={{ padding: '11px 16px' }}>
                        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-1)' }}>
                          {p.project_name || p.name}
                        </div>
                        {p.client_name && (
                          <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{p.client_name}</div>
                        )}
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center', fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>
                        {fmtCur(rev, lang)}
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center' }}>
                        <span style={{ fontSize: 12, color: 'var(--text-2)', background: 'var(--surface-4)', padding: '3px 8px', borderRadius: 6 }}>
                          {fmtCur(cost, lang)}
                        </span>
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center', fontSize: 12, fontWeight: 700, color: mColor }}>
                        {fmtCur(mgn, lang)}
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center' }}>
                        <span style={{
                          fontSize: 12, fontWeight: 700, color: mColor,
                          background: `${mColor}18`, border: `1px solid ${mColor}30`,
                          borderRadius: 6, padding: '3px 9px',
                        }}>{pct}%</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </DashPageShell>
  )
}
