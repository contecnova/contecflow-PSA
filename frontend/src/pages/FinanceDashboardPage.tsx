import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { currencyApi, userCostsApi, unwrapList } from '../services/api'
import { todasLasPaginas } from '../services/api/todasLasPaginas'
import { useAuth } from '../context/AuthContext'
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
import { alpha } from '../constants/theme'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
interface ClientItem { status?: string }
// Campos de `pipeline_service` (auditoria 2026-11: se leian `value`/`amount` y
// `status`, que no vienen: el pipeline salia a 0 y contaba ganadas y perdidas).
interface PipelineItem { stage?: string; expected_revenue?: number }
interface InvoiceItem { status?: string; total?: number; amount?: number }
interface ProjectProfitItem {
  project_id?: string | number
  id?: string | number
  project_name?: string
  name?: string
  client_name?: string
  // Nombres de `calc_project_profitability` (auditoria 2026-11: se leian
  // `revenue_actual`/`cost_actual`, que no existen, y salia el presupuesto como
  // ingreso con coste 0).
  billing_revenue?: number
  internal_cost?: number
  total_cost?: number
}
interface CurrencyRate {
  id: string | number
  from_currency: string
  to_currency: string
  rate: number
  effective_date?: string
}
interface CostSummary {
  avg_cost_per_hour: number
  users_with_cost: number
  total_users: number
  users_missing_cost: number
}
// El resumen trae los totales dentro de `portfolio` (auditoria 2026-11: se leian
// en la raiz y el panel enseñaba siempre 0).
interface ProfitSummary {
  portfolio?: { total_revenue?: number; total_cost?: number }
}
interface RateFormState {
  from_currency: string
  to_currency: string
  rate: string
}


export default function FinanceDashboardPage(): JSX.Element {
  const fmtMoneda = useFormatoMoneda()
  const { t } = useAppLang()
  const [days, setDays] = useState<number>(90)
  const { lang } = useAppLang()
  const toast = useToast()
  const params = dateRange(days)

  const { data: profitSummaryRaw, isLoading: lp, isError: profitError } = useQuery({
    queryKey: ['fin-dash-profit', days],
    queryFn: () => api.get('/profitability/summary', { params: { ...params, period: 'custom' } }).then(r => r.data),
    staleTime: 60_000,
    retry: 1,
  })
  const profitSummary = (profitSummaryRaw ?? null) as ProfitSummary | null

  // Revisión 2026-11: clientes, pipeline y facturas son la foto de hoy (no del
  // periodo), completos y sin tragarse errores: antes se cortaban en 200/100 y un
  // fallo se veía como «sin datos».
  const { data: clientsRaw = [], isLoading: lc, isError: e1 } = useQuery({
    queryKey: ['fin-dash-clients'],
    queryFn: () => todasLasPaginas('/clients').then(r => r.data),
    staleTime: 60_000,
  })
  const clients = clientsRaw as ClientItem[]

  const { data: pipelineRaw = [], isError: e2 } = useQuery({
    queryKey: ['fin-dash-pipeline'],
    queryFn: () => api.get('/pipeline').then(unwrapList),
    staleTime: 60_000,
  })
  const pipeline = pipelineRaw as PipelineItem[]

  const { data: invoicesDataRaw, isError: e3 } = useQuery({
    queryKey: ['fin-dash-invoices'],
    queryFn: async () => {
      // `/invoices` pagina con skip/limit (máximo 500): se recorre entero.
      const todas: unknown[] = []
      for (let skip = 0; ; skip += 500) {
        const lote = unwrapList(await api.get('/invoices', { params: { skip, limit: 500 } })) as unknown[]
        todas.push(...lote)
        if (lote.length < 500) return todas
      }
    },
    staleTime: 60_000,
  })
  const invoicesData = (invoicesDataRaw ?? []) as InvoiceItem[]

  const { data: topProjectsRaw = [], isError: e4 } = useQuery({
    queryKey: ['fin-dash-top-proj', days],
    queryFn: () => api.get('/profitability/projects', { params }).then(r => r.data),
    staleTime: 60_000,
  })
  const topProjects = topProjectsRaw as ProjectProfitItem[]

  const qc = useQueryClient()
  const [showRateForm, setShowRateForm] = useState(false)
  const [rateForm, setRateForm] = useState<RateFormState>({ from_currency: fmtMoneda.moneda, to_currency: 'USD', rate: '' })
  const { data: ratesRaw = [], isError: e5 } = useQuery({
    queryKey: ['currency-rates'],
    queryFn: () => currencyApi.rates({}).then(r => r.data),
    staleTime: 300_000,
  })
  const rates = ratesRaw as CurrencyRate[]

  // Coste/hora real: sólo admin y hr (el endpoint da 403 al resto, que no lo pide).
  const { hasRole } = useAuth()
  const veCostes = hasRole('admin', 'hr')
  const puedeGuardarCambio = hasRole('admin')
  const { data: costSummaryRaw, isError: e6 } = useQuery({
    queryKey: ['fin-dash-cost-summary'],
    enabled: veCostes,
    queryFn: () => userCostsApi.summary(undefined).then(r => r.data),
    staleTime: 5 * 60_000,
    retry: false,
  })
  const costSummary = (costSummaryRaw ?? null) as CostSummary | null
  const { mutate: upsertRate, isPending: savingRate } = useMutation({
    mutationFn: (d: { from_currency: string; to_currency: string; rate: number }) => currencyApi.upsert(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['currency-rates'] }); setShowRateForm(false); setRateForm({ from_currency: fmtMoneda.moneda, to_currency:'USD', rate:'' }) },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al guardar tipo de cambio')),
  })

  const algunFallo = profitError || e1 || e2 || e3 || e4 || e5 || e6
  useEffect(() => {
    if (algunFallo) toast.error('No se pudieron cargar todos los datos del panel')
  }, [algunFallo]) // eslint-disable-line react-hooks/exhaustive-deps

  const revenue   = profitSummary?.portfolio?.total_revenue ?? 0
  const costs     = profitSummary?.portfolio?.total_cost ?? 0
  const margin    = revenue - costs
  const marginPct = revenue > 0 ? Math.round((margin / revenue) * 100) : null
  const marginColor = marginPct == null ? COLOR.accent : marginPct >= 30 ? COLOR.success : marginPct >= 15 ? COLOR.warning : COLOR.danger

  const invoices = Array.isArray(invoicesData) ? invoicesData : []
  const pendingInvoices = invoices.filter(i => i.status === 'sent' || i.status === 'overdue')
  const overdueInvoices = invoices.filter(i => i.status === 'overdue')
  const pendingAmount   = pendingInvoices.reduce((s, i) => s + (i.total || i.amount || 0), 0)
  const overdueAmount   = overdueInvoices.reduce((s, i) => s + (i.total || i.amount || 0), 0)

  const activeClients    = clients.filter(c => c.status === 'active').length
  const abiertas         = pipeline.filter(o => o.stage !== 'won' && o.stage !== 'lost')
  const pipelineValue    = abiertas.reduce((s, o) => s + (o.expected_revenue || 0), 0)
  const openOpportunities = abiertas.length

  const revenueByClient = topProjects.reduce<Record<string, number>>((acc, p) => {
    const name = p.client_name || 'Sin cliente'
    const rev = p.billing_revenue ?? 0
    if (rev > 0) acc[name] = (acc[name] || 0) + rev
    return acc
  }, {})
  const clientRows = Object.entries(revenueByClient)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([name, revenue]) => ({ name, revenue }))
  const maxRevenue = clientRows[0]?.revenue || 1

  const pipelineByStage = pipeline.reduce<Record<string, { count: number; value: number }>>((acc, o) => {
    const stage = o.stage || 'Sin etapa'
    if (!acc[stage]) acc[stage] = { count: 0, value: 0 }
    acc[stage].count += 1
    acc[stage].value += (o.expected_revenue || 0)
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
              sub={`${clients.length} total · hoy`} />
            <KpiCard icon={<KpiIcon icon={Target} />} label="Pipeline"
              value={fmtCur(pipelineValue, lang)}
              color={COLOR.purple} accentBar={COLOR.purple}
              sub={`${openOpportunities} oportunidades abiertas · hoy`} />
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
            <KpiCard icon={<KpiIcon icon={AlertTriangle} />} label={t('financedashboard.sin_estructura_de_coste')}
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
        <SectionCard title={t('financedashboard.top_clientes_por_ingresos')} badge={clientRows.length}>
          {clientRows.length === 0
            ? <DashEmpty title={t('financedashboard.sin_datos_de_ingresos_por_cliente')} description="Asocia proyectos e ingresos a clientes para ver esta métrica" />
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
        <SectionCard title={t('financedashboard.pipeline_por_etapa')} badge={openOpportunities}>
          {stageRows.length === 0
            ? <DashEmpty title={t('financedashboard.sin_oportunidades_en_pipeline')} />
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
        <SectionCard title={t('financedashboard.rentabilidad_por_proyecto')} badge={topProjects.length}>
          <div className="u-scroll-x">
            <table className="u-table">
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
                  const rev  = p.billing_revenue ?? 0
                  const cost = p.total_cost ?? p.internal_cost ?? 0   // personal + gastos + subcontrata
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
                          <div className="u-text3-xs">{p.client_name}</div>
                        )}
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center', fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>
                        {fmtCur(rev, lang)}
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center' }}>
                        <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', background: 'var(--surface-4)', padding: '3px 8px', borderRadius: 'var(--radius-sm)' }}>
                          {fmtCur(cost, lang)}
                        </span>
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center', fontSize: "var(--text-sm)", fontWeight: 700, color: mColor }}>
                        {fmtCur(mgn, lang)}
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'center' }}>
                        <span style={{
                          fontSize: "var(--text-sm)", fontWeight: 700, color: mColor,
                          background: alpha(mColor, '18'), border: `1px solid ${alpha(mColor, '30')}`,
                          borderRadius: 'var(--radius-sm)', padding: '3px 9px',
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
      <SectionCard title={t('financedashboard.tipos_de_cambio')}
        badge={puedeGuardarCambio && (
          <button onClick={() => setShowRateForm(v => !v)}
            style={{ fontSize: 'var(--text-xs)', padding: '3px 9px', borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)',
              cursor: 'pointer', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {showRateForm ? <><X size={11} /> Cerrar</> : <><Plus size={11} /> {t('financedashboard.anadir')}</>}
          </button>
        )}
      >
        {showRateForm && (
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'flex-end', marginBottom: 'var(--space-3)', flexWrap: 'wrap' }}>
            {([['from_currency', 'De', 'EUR'], ['to_currency', 'A', 'USD']] as const).map(([k, l, ph]) => (
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
          <DashEmpty title={t('financedashboard.sin_tipos_de_cambio')} description="Añade tasas de conversión para gestionar proyectos multi-divisa" />
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
