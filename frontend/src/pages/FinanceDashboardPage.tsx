// @ts-nocheck
import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { currencyApi, userCostsApi, unwrapList } from '../services/api'
import {
  DollarSign, TrendingUp, TrendingDown, CheckCircle2, Building2, Target, FileText,
  Calculator, AlertTriangle, Ruler, X, Plus,
} from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { useToast } from '../context/ToastContext'
import { extractErr } from '../utils/helpers'
import {
  COLOR, DashPageShell, KpiCard, KpiIcon, KpiCardSkeleton, GaugeCard, BarRow, SectionCard, DashEmpty,
  dateRange, fmtCur, typePalette,
} from '../components/dashboard/DashKit'

export default function FinanceDashboardPage(): JSX.Element {
  const [days, setDays] = useState<number>(90)
  const { lang } = useAppLang()
  const toast = useToast()
  const params = dateRange(days)

  const { data: profitSummary, isLoading: lp, isError: profitError } = useQuery({
    queryKey: ['fin-dash-profit', days],
    queryFn: () => api.get('/profitability/summary', { params: { ...params, period: 'custom' } }).then(r => r.data),
    staleTime: 60_000,
    retry: 1,
  })

  const { data: clients = [], isLoading: lc } = useQuery({
    queryKey: ['fin-dash-clients'],
    queryFn: () => api.get('/clients', { params: { page_size: 200 } }).then(unwrapList).catch(() => []),
    staleTime: 60_000,
  })

  const { data: pipeline = [] } = useQuery({
    queryKey: ['fin-dash-pipeline'],
    queryFn: () => api.get('/pipeline', { params: { page_size: 100 } }).then(unwrapList).catch(() => []),
    staleTime: 60_000,
  })

  const { data: invoicesData } = useQuery({
    queryKey: ['fin-dash-invoices'],
    queryFn: () => api.get('/invoices', { params: { page_size: 200 } }).then(unwrapList).catch(() => []),
    staleTime: 60_000,
  })

  const { data: topProjects = [] } = useQuery({
    queryKey: ['fin-dash-top-proj', days],
    queryFn: () => api.get('/profitability/projects', { params }).then(r => r.data).catch(() => []),
    staleTime: 60_000,
  })

  const qc = useQueryClient()
  const [showRateForm, setShowRateForm] = useState(false)
  const [rateForm, setRateForm] = useState({ from_currency: 'EUR', to_currency: 'USD', rate: '' })
  const { data: rates = [] } = useQuery({
    queryKey: ['currency-rates'],
    queryFn: () => currencyApi.rates().then(r => r.data).catch(() => []),
    staleTime: 300_000,
  })

  // True cost-per-hour summary (admin/hr only — endpoint returns 403 otherwise)
  const { data: costSummary } = useQuery({
    queryKey: ['fin-dash-cost-summary'],
    queryFn: () => userCostsApi.summary().then(r => r.data).catch(() => null),
    staleTime: 5 * 60_000,
    retry: false,
  })
  const { mutate: upsertRate, isPending: savingRate } = useMutation({
    mutationFn: d => currencyApi.upsert(d),
    onSuccess: () => { qc.invalidateQueries(['currency-rates']); setShowRateForm(false); setRateForm({ from_currency:'EUR', to_currency:'USD', rate:'' }) },
    onError: e => toast.error(extractErr(e, 'Error al guardar tipo de cambio')),
  })

  useEffect(() => {
    if (profitError) toast.error('No se pudieron cargar los datos de rentabilidad')
  }, [profitError]) // eslint-disable-line react-hooks/exhaustive-deps

  const revenue   = profitSummary?.total_revenue ?? 0
  const costs     = profitSummary?.total_cost ?? 0
  const margin    = revenue - costs
  const marginPct = revenue > 0 ? Math.round((margin / revenue) * 100) : null
  const marginColor = marginPct == null ? COLOR.accent : marginPct >= 30 ? COLOR.success : marginPct >= 15 ? COLOR.warning : COLOR.danger

  const invoices        = Array.isArray(invoicesData) ? invoicesData : []
  const pendingInvoices = invoices.filter(i => i.status === 'sent' || i.status === 'overdue')
  const overdueInvoices = invoices.filter(i => i.status === 'overdue')
  const pendingAmount   = pendingInvoices.reduce((s, i) => s + (i.total || i.amount || 0), 0)
  const overdueAmount   = overdueInvoices.reduce((s, i) => s + (i.total || i.amount || 0), 0)

  const activeClients    = clients.filter(c => c.status === 'active').length
  const pipelineValue    = pipeline.reduce((s, o) => s + (o.value || o.amount || 0), 0)
  const openOpportunities = pipeline.filter(o => o.status !== 'closed_won' && o.status !== 'closed_lost').length

  const revenueByClient = topProjects.reduce((acc, p) => {
    const name = p.client_name || 'Sin cliente'
    const rev = p.revenue_actual ?? p.budget_amount ?? 0
    if (rev > 0) acc[name] = (acc[name] || 0) + rev
    return acc
  }, {})
  const clientRows = Object.entries(revenueByClient)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([name, revenue]) => ({ name, revenue }))
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
      <div className="ds-page">
        {/* KPI row */}
        <div className="ds-grid-stats">
          {(lp || lc) ? Array.from({ length: 6 }).map((_, i) => <KpiCardSkeleton key={i} />) : <>
            <KpiCard icon={<KpiIcon icon={TrendingUp} />} label="Ingresos"
              value={fmtCur(revenue, lang)}
              color={COLOR.accent} accentBar={COLOR.accent} />
            <KpiCard icon={<KpiIcon icon={TrendingDown} />} label="Costes"
              value={fmtCur(costs, lang)}
              color={COLOR.warning} accentBar={COLOR.warning} />
            <KpiCard icon={<KpiIcon icon={CheckCircle2} />} label="Margen bruto"
              value={fmtCur(margin, lang)}
              color={margin >= 0 ? COLOR.success : COLOR.danger}
              accentBar={margin >= 0 ? COLOR.success : COLOR.danger}
              sub={marginPct != null ? `${marginPct}% de margen` : undefined} />
            <KpiCard icon={<KpiIcon icon={Building2} />} label="Clientes activos"
              value={activeClients} color={COLOR.accent} accentBar={COLOR.accent}
              sub={`${clients.length} total`} />
            <KpiCard icon={<KpiIcon icon={Target} />} label="Pipeline"
              value={fmtCur(pipelineValue, lang)}
              color={COLOR.purple} accentBar={COLOR.purple}
              sub={`${openOpportunities} oportunidades abiertas`} />
            <KpiCard icon={<KpiIcon icon={FileText} />} label="Facturas pendientes"
              value={fmtCur(pendingAmount, lang)}
              color={overdueAmount > 0 ? COLOR.danger : COLOR.warning}
              accentBar={overdueAmount > 0 ? COLOR.danger : COLOR.warning}
              sub={overdueAmount > 0 ? `${fmtCur(overdueAmount, lang)} vencidas` : `${pendingInvoices.length} por cobrar`} />
          </>}
        </div>

        {/* Cost-structure KPIs (admin/hr only) */}
        {costSummary && (
          <div className="ds-grid-stats">
            <KpiCard icon={<KpiIcon icon={Calculator} />} label="Coste/hora medio"
              value={fmtCur(costSummary.avg_cost_per_hour, lang)}
              color={COLOR.accent} accentBar={COLOR.accent}
              sub={`${costSummary.users_with_cost} de ${costSummary.total_users} personas`} />
            <KpiCard icon={<KpiIcon icon={AlertTriangle} />} label="Sin estructura de coste"
              value={costSummary.users_missing_cost}
              color={costSummary.users_missing_cost > 0 ? COLOR.warning : COLOR.success}
              accentBar={costSummary.users_missing_cost > 0 ? COLOR.warning : COLOR.success}
              sub={costSummary.users_missing_cost > 0 ? 'Margen real incompleto' : 'Margen real fiable'} />
            {revenue > 0 && costSummary.avg_cost_per_hour > 0 && (
              <KpiCard icon={<KpiIcon icon={Ruler} />} label="Margen real estimado"
                value={`${Math.round(((revenue - costs) / revenue) * 100)}%`}
                color={COLOR.purple} accentBar={COLOR.purple}
                sub="Snapshots actualizados con coste real al imputar" />
            )}
          </div>
        )}

      {/* Gauges */}
      {!lp && marginPct != null && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-3)' }}>
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
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 'var(--space-3)' }}>
        {/* Top clients */}
        <SectionCard title="Top clientes por ingresos" badge={clientRows.length}>
          {clientRows.length === 0
            ? <DashEmpty title="Sin datos de ingresos por cliente" description="Asocia proyectos e ingresos a clientes para ver esta métrica" />
            : clientRows.map((c, i) => (
                <BarRow key={c.name}
                  label={c.name}
                  count={c.revenue}
                  total={maxRevenue}
                  color={typePalette[i % typePalette.length]}
                  displayValue={fmtCur(c.revenue, lang)} />
              ))
          }
        </SectionCard>

        {/* Pipeline by stage */}
        <SectionCard title="Pipeline por etapa" badge={openOpportunities}>
          {stageRows.length === 0
            ? <DashEmpty title="Sin oportunidades en pipeline" />
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
                      fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)',
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
                        <div style={{ fontSize: "var(--text-base)", fontWeight: 500, color: 'var(--text-1)' }}>
                          {p.project_name || p.name}
                        </div>
                        {p.client_name && (
                          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{p.client_name}</div>
                        )}
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center', fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>
                        {fmtCur(rev, lang)}
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center' }}>
                        <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', background: 'var(--surface-4)', padding: '3px 8px', borderRadius: 6 }}>
                          {fmtCur(cost, lang)}
                        </span>
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center', fontSize: "var(--text-sm)", fontWeight: 700, color: mColor }}>
                        {fmtCur(mgn, lang)}
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center' }}>
                        <span style={{
                          fontSize: "var(--text-sm)", fontWeight: 700, color: mColor,
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

      {/* Currency exchange rates */}
      <SectionCard title="Tipos de cambio"
        badge={
          <button onClick={() => setShowRateForm(v => !v)}
            style={{ fontSize: 'var(--text-xs)', padding: '3px 9px', borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)',
              cursor: 'pointer', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {showRateForm ? <><X size={11} /> Cerrar</> : <><Plus size={11} /> Añadir</>}
          </button>
        }
      >
        {showRateForm && (
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'flex-end', marginBottom: 'var(--space-3)', flexWrap: 'wrap' }}>
            {[['from_currency', 'De', 'EUR'], ['to_currency', 'A', 'USD']].map(([k, l, ph]) => (
              <div key={k} style={{ flex: '0 0 90px' }}>
                <div className="ds-eyebrow" style={{ marginBottom: 4 }}>{l}</div>
                <input maxLength={3} value={rateForm[k]} onChange={e => setRateForm(f => ({ ...f, [k]: e.target.value.toUpperCase() }))}
                  className="ds-input" placeholder={ph} />
              </div>
            ))}
            <div style={{ flex: '0 0 110px' }}>
              <div className="ds-eyebrow" style={{ marginBottom: 4 }}>Tasa</div>
              <input type="number" step="0.0001" min="0" value={rateForm.rate}
                onChange={e => setRateForm(f => ({ ...f, rate: e.target.value }))}
                className="ds-input" placeholder="1.0850" />
            </div>
            <button onClick={() => upsertRate({ from_currency: rateForm.from_currency, to_currency: rateForm.to_currency, rate: parseFloat(rateForm.rate) })}
              disabled={savingRate || !rateForm.from_currency || !rateForm.to_currency || !rateForm.rate}
              style={{ padding: '8px 14px', borderRadius: 'var(--radius-md)',
                border: '1px solid var(--accent)', background: 'var(--accent-muted)', color: 'var(--accent)',
                cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
              {savingRate ? '...' : 'Guardar'}
            </button>
          </div>
        )}
        {rates.length === 0 ? (
          <DashEmpty title="Sin tipos de cambio" description="Añade tasas de conversión para gestionar proyectos multi-divisa" />
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
            {rates.map(r => (
              <div key={r.id} className="ds-card--inset" style={{
                padding: '8px 14px', fontSize: 'var(--text-base)',
                display: 'inline-flex', alignItems: 'center', gap: 6,
              }}>
                <span style={{ fontWeight: 700, color: 'var(--text-1)' }}>{r.from_currency}</span>
                <span className="ds-muted">→</span>
                <span style={{ fontWeight: 700, color: 'var(--text-1)' }}>{r.to_currency}</span>
                <span style={{ marginLeft: 6, fontWeight: 600, color: 'var(--accent)' }}>{r.rate}</span>
                {r.effective_date && <span className="ds-muted" style={{ marginLeft: 4 }}>{r.effective_date}</span>}
              </div>
            ))}
          </div>
        )}
      </SectionCard>
      </div>
    </DashPageShell>
  )
}
