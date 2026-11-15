import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { currencyApi, invoicesApi, profitabilityApi, userCostsApi, unwrapList } from '../services/api'
import type { Factura } from '../services/api/tipos-finanzas'
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
import { STALE_5_MIN_MS, STALE_DEFAULT_MS } from '../constants/timings'
import { INVOICES_BATCH_SIZE } from '../constants/pagination'
import './FinanceDashboardPage.css'
interface ClientItem { status?: string }
// Campos de `pipeline_service` (auditoria 2026-11: se leian `value`/`amount` y
// `status`, que no vienen: el pipeline salia a 0 y contaba ganadas y perdidas).
interface PipelineItem { stage?: string; expected_revenue?: number }
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

  // El resumen trae los totales dentro de `portfolio` (auditoria 2026-11: se leian en la raiz).
  const { data: profitSummary = null, isLoading: lp, isError: profitError } = useQuery({
    queryKey: ['fin-dash-profit', days],
    queryFn: () => profitabilityApi.summary({ ...params, period: 'custom' }).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
    retry: 1,
  })

  // Revisión 2026-11: clientes, pipeline y facturas son la foto de hoy (no del
  // periodo), completos y sin tragarse errores: antes se cortaban en 200/100 y un
  // fallo se veía como «sin datos».
  const { data: clientsRaw = [], isLoading: lc, isError: e1 } = useQuery({
    queryKey: ['fin-dash-clients'],
    queryFn: () => todasLasPaginas('/clients').then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })
  const clients = clientsRaw as ClientItem[]

  const { data: pipelineRaw = [], isError: e2 } = useQuery({
    queryKey: ['fin-dash-pipeline'],
    queryFn: () => api.get('/pipeline').then(unwrapList),
    staleTime: STALE_DEFAULT_MS,
  })
  const pipeline = pipelineRaw as PipelineItem[]

  const { data: invoicesData = [], isError: e3 } = useQuery({
    queryKey: ['fin-dash-invoices'],
    queryFn: async () => {
      // `/invoices` pagina con skip/limit (máximo 500): se recorre entero.
      const todas: Factura[] = []
      for (let skip = 0; ; skip += 500) {
        const lote = (await invoicesApi.list({ skip, limit: INVOICES_BATCH_SIZE })).data
        todas.push(...lote)
        if (lote.length < 500) return todas
      }
    },
    staleTime: STALE_DEFAULT_MS,
  })

  // Nombres de `calc_project_profitability` (auditoria 2026-11: se leian `revenue_actual`/`cost_actual`).
  const { data: topProjects = [], isError: e4 } = useQuery({
    queryKey: ['fin-dash-top-proj', days],
    queryFn: () => profitabilityApi.projects(params).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const qc = useQueryClient()
  const [showRateForm, setShowRateForm] = useState(false)
  const [rateForm, setRateForm] = useState<RateFormState>({ from_currency: fmtMoneda.moneda, to_currency: 'USD', rate: '' })
  const { data: rates = [], isError: e5 } = useQuery({
    queryKey: ['currency-rates'],
    queryFn: () => currencyApi.rates({}).then(r => r.data),
    staleTime: STALE_5_MIN_MS,
  })

  // Coste/hora real: sólo admin y hr (el endpoint da 403 al resto, que no lo pide).
  const { hasRole } = useAuth()
  const veCostes = hasRole('admin', 'hr')
  const puedeGuardarCambio = hasRole('admin')
  const { data: costSummary = null, isError: e6 } = useQuery({
    queryKey: ['fin-dash-cost-summary'],
    enabled: veCostes,
    queryFn: () => userCostsApi.summary().then(r => r.data),
    staleTime: STALE_5_MIN_MS,
    retry: false,
  })
  const { mutate: upsertRate, isPending: savingRate } = useMutation({
    mutationFn: (d: { from_currency: string; to_currency: string; rate: number }) => currencyApi.upsert(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['currency-rates'] }); setShowRateForm(false); setRateForm({ from_currency: fmtMoneda.moneda, to_currency:'USD', rate:'' }) },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_findash.error_al_guardar_tipo_de_cambio'))),
  })

  const algunFallo = profitError || e1 || e2 || e3 || e4 || e5 || e6
  useEffect(() => {
    if (algunFallo) toast.error(t('pagina_findash.no_se_pudieron_cargar_todos_los'))
  }, [algunFallo]) // eslint-disable-line react-hooks/exhaustive-deps

  const revenue   = profitSummary?.portfolio?.total_revenue ?? 0
  const costs     = profitSummary?.portfolio?.total_cost ?? 0
  const margin    = revenue - costs
  const marginPct = revenue > 0 ? Math.round((margin / revenue) * 100) : null
  const marginColor = marginPct == null ? COLOR.accent : marginPct >= 30 ? COLOR.success : marginPct >= 15 ? COLOR.warning : COLOR.danger

  const invoices = Array.isArray(invoicesData) ? invoicesData : []
  const pendingInvoices = invoices.filter(i => i.status === 'sent' || i.status === 'overdue')
  const overdueInvoices = invoices.filter(i => i.status === 'overdue')
  const pendingAmount   = pendingInvoices.reduce((s, i) => s + (i.total ?? 0), 0)
  const overdueAmount   = overdueInvoices.reduce((s, i) => s + (i.total ?? 0), 0)

  const activeClients    = clients.filter(c => c.status === 'active').length
  const abiertas         = pipeline.filter(o => o.stage !== 'won' && o.stage !== 'lost')
  const pipelineValue    = abiertas.reduce((s, o) => s + (o.expected_revenue || 0), 0)
  const openOpportunities = abiertas.length

  const revenueByClient = topProjects.reduce<Record<string, number>>((acc, p) => {
    const name = p.client_name || t('pagina_findash.sin_cliente')
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
    const stage = o.stage || t('pagina_findash.sin_etapa')
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
      title={t('pagina_findash.clientes_y_finanzas')}
      subtitle={t('pagina_findash.rentabilidad_facturacion_cartera_de_clientes_y')}
      days={days} setDays={setDays}
      periods={[30, 90, 365]}
    >
      <div className="ds-page">
        {/* KPI row */}
        <div className="ds-grid-stats">
          {(lp || lc) ? Array.from({ length: 6 }).map((_, i) => <KpiCardSkeleton key={i} />) : <>
            <KpiCard icon={<KpiIcon icon={TrendingUp} />} label={t('pagina_findash.ingresos')}
              value={fmtCur(revenue, lang)}
              color={COLOR.accent} accentBar={COLOR.accent} />
            <KpiCard icon={<KpiIcon icon={TrendingDown} />} label={t('pagina_findash.costes')}
              value={fmtCur(costs, lang)}
              color={COLOR.warning} accentBar={COLOR.warning} />
            <KpiCard icon={<KpiIcon icon={CheckCircle2} />} label={t('pagina_findash.margen_bruto')}
              value={fmtCur(margin, lang)}
              color={margin >= 0 ? COLOR.success : COLOR.danger}
              accentBar={margin >= 0 ? COLOR.success : COLOR.danger}
              sub={marginPct != null ? t('pagina_findash.de_margen', { marginPct }) : undefined} />
            <KpiCard icon={<KpiIcon icon={Building2} />} label={t('pagina_findash.clientes_activos')}
              value={activeClients} color={COLOR.accent} accentBar={COLOR.accent}
              sub={t('pagina_findash.total_hoy', { length: clients.length })} />
            <KpiCard icon={<KpiIcon icon={Target} />} label={t('pagina_findash.pipeline')}
              value={fmtCur(pipelineValue, lang)}
              color={COLOR.purple} accentBar={COLOR.purple}
              sub={t('pagina_findash.oportunidades_abiertas_hoy', { openOpportunities })} />
            <KpiCard icon={<KpiIcon icon={FileText} />} label={t('pagina_findash.facturas_pendientes')}
              value={fmtCur(pendingAmount, lang)}
              color={overdueAmount > 0 ? COLOR.danger : COLOR.warning}
              accentBar={overdueAmount > 0 ? COLOR.danger : COLOR.warning}
              sub={overdueAmount > 0 ? t('pagina_findash.vencidas', { v1: fmtCur(overdueAmount, lang) }) : t('pagina_findash.por_cobrar', { length: pendingInvoices.length })} />
          </>}
        </div>

        {/* Cost-structure KPIs (admin/hr only) */}
        {costSummary && (
          <div className="ds-grid-stats">
            <KpiCard icon={<KpiIcon icon={Calculator} />} label={t('pagina_findash.coste_hora_medio')}
              value={fmtCur(costSummary.avg_cost_per_hour, lang)}
              color={COLOR.accent} accentBar={COLOR.accent}
              sub={t('pagina_findash.de_personas', { users_with_cost: costSummary.users_with_cost, total_users: costSummary.total_users })} />
            <KpiCard icon={<KpiIcon icon={AlertTriangle} />} label={t('financedashboard.sin_estructura_de_coste')}
              value={costSummary.users_missing_cost}
              color={costSummary.users_missing_cost > 0 ? COLOR.warning : COLOR.success}
              accentBar={costSummary.users_missing_cost > 0 ? COLOR.warning : COLOR.success}
              sub={costSummary.users_missing_cost > 0 ? t('pagina_findash.margen_real_incompleto') : t('pagina_findash.margen_real_fiable')} />
            {revenue > 0 && costSummary.avg_cost_per_hour > 0 && (
              <KpiCard icon={<KpiIcon icon={Ruler} />} label={t('pagina_findash.margen_real_estimado')}
                value={`${Math.round(((revenue - costs) / revenue) * 100)}%`}
                color={COLOR.purple} accentBar={COLOR.purple}
                sub={t('pagina_findash.snapshots_actualizados_con_coste_real_al')} />
            )}
          </div>
        )}

      {/* Gauges */}
      {!lp && marginPct != null && (
        <div className="findash-grid">
          <GaugeCard label={t('pagina_findash.margen_bruto')}
            value={marginPct} color={marginColor}
            sub={marginPct >= 30 ? t('pagina_findash.rentabilidad_excelente') : marginPct >= 15 ? t('pagina_findash.rentabilidad_aceptable') : t('pagina_findash.margen_bajo_revisar_costes')} />
          {pendingAmount > 0 && revenue > 0 && (
            <GaugeCard label={t('pagina_findash.cobrado_vs_facturado')}
              value={Math.round(((revenue - pendingAmount) / revenue) * 100)}
              color={COLOR.success}
              sub={t('pagina_findash.pendiente_de_cobro', { v1: fmtCur(pendingAmount, lang) })} />
          )}
          {pipelineValue > 0 && revenue > 0 && (
            <GaugeCard label={t('pagina_findash.pipeline_ingresos')}
              value={Math.min(Math.round((pipelineValue / revenue) * 100), 999)}
              suffix="%" color={COLOR.purple}
              sub={t('pagina_findash.ratio_pipeline_sobre_ingresos_actuales')} />
          )}
        </div>
      )}

      {/* Charts */}
      <div className="findash-grid-2">
        {/* Top clients */}
        <SectionCard title={t('financedashboard.top_clientes_por_ingresos')} badge={clientRows.length}>
          {clientRows.length === 0
            ? <DashEmpty title={t('financedashboard.sin_datos_de_ingresos_por_cliente')} description={t('pagina_findash.asocia_proyectos_e_ingresos_a_clientes')} />
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
                <tr className="findash-row">
                  {[t('pagina_findash.proyecto'), t('pagina_findash.ingresos'), t('pagina_findash.costes'), t('pagina_findash.margen'), '%'].map((col, i) => (
                    <th key={col} className="findash-th" style={{ textAlign: i === 0 ? 'left' : 'center' }}>{col}</th>
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
                    <tr key={p.project_id} className="u-border-b" style={{ background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)' }}>
                      <td className="findash-td">
                        <div className="findash-box">
                          {p.project_name}
                        </div>
                        {p.client_name && (
                          <div className="u-text3-xs">{p.client_name}</div>
                        )}
                      </td>
                      <td className="findash-td-2">
                        {fmtCur(rev, lang)}
                      </td>
                      <td className="findash-td-3">
                        <span className="findash-card">
                          {fmtCur(cost, lang)}
                        </span>
                      </td>
                      <td className="findash-td-4" style={{ color: mColor }}>
                        {fmtCur(mgn, lang)}
                      </td>
                      <td className="findash-td-3">
                        <span className="findash-label" style={{ color: mColor, background: alpha(mColor, '18'), border: `1px solid ${alpha(mColor, '30')}`, borderRadius: 'var(--radius-sm)' }}>{pct}%</span>
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
            className="findash-btn">
            {showRateForm ? <><X size={11} />{' '}{t('pagina_findash.cerrar')}</> : <><Plus size={11} /> {t('financedashboard.anadir')}</>}
          </button>
        )}
      >
        {showRateForm && (
          <div className="findash-row-2">
            {([['from_currency', t('pagina_findash.de'), 'EUR'], ['to_currency', 'A', 'USD']] as const).map(([k, l, ph]) => (
              <div key={k} className="findash-box-2">
                <div className="ds-eyebrow findash-box-3">{l}</div>
                <input maxLength={3} aria-label={l} value={rateForm[k]} onChange={e => setRateForm(f => ({ ...f, [k]: e.target.value.toUpperCase() }))}
                  className="ds-input" placeholder={ph} />
              </div>
            ))}
            <div className="findash-box-4">
              <div className="ds-eyebrow findash-box-3">{t('pagina_findash.tasa')}</div>
              <input type="number" step="0.0001" min="0" aria-label={t('pagina_findash.tasa')} value={rateForm.rate}
                onChange={e => setRateForm(f => ({ ...f, rate: e.target.value }))}
                className="ds-input" placeholder="1.0850" />
            </div>
            <button onClick={() => upsertRate({ from_currency: rateForm.from_currency, to_currency: rateForm.to_currency, rate: parseFloat(rateForm.rate) })}
              disabled={savingRate || !rateForm.from_currency || !rateForm.to_currency || !rateForm.rate}
              className="findash-btn-2">
              {savingRate ? '...' : t('pagina_findash.guardar')}
            </button>
          </div>
        )}
        {rates.length === 0 ? (
          <DashEmpty title={t('financedashboard.sin_tipos_de_cambio')} description={t('pagina_findash.anade_tasas_de_conversion_para_gestionar')} />
        ) : (
          <div className="findash-row-3">
            {rates.map(r => (
              <div key={r.id} className="ds-card--inset findash-row-4">
                <span className="findash-label-2">{r.from_currency}</span>
                <span className="ds-muted">→</span>
                <span className="findash-label-2">{r.to_currency}</span>
                <span className="findash-label-3">{r.rate}</span>
                {r.effective_date && <span className="ds-muted findash-label-4">{r.effective_date}</span>}
              </div>
            ))}
          </div>
        )}
      </SectionCard>
      </div>
    </DashPageShell>
  )
}
