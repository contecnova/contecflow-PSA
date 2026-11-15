import { useState, type CSSProperties, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { profitabilityApi } from '../services/api'
import type { HitoDeRentabilidad, RentabilidadDetallada, ResumenDeRentabilidad } from '../services/api/tipos-finanzas'
import { Card, Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { TrendingUp } from 'lucide-react'
import { fmtCurrency, fmtHours, fmtDate, extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './ProfitabilityPage.css'
type MilestoneItem = HitoDeRentabilidad

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const _BILLING_TYPES = [
  { value: 'time_material', label: 'Tiempo y material' },
  { value: 'fixed_price', label: 'Precio fijo' },
  { value: 'hourly_bag', label: 'Bolsa de horas' },
]


// ─────────────────────────────────────────────────────────────────────────────
// El color de una cifra de dinero
//
// Auditoria 2026-09 (modo estricto): los 20 errores de este fichero eran todos
// la misma pregunta —«¿de que color pinto un margen que puede no venir?»— y la
// respuesta que daba el codigo era, sin querer, **verde**: en JavaScript
// `undefined < 0` es `false`, asi que un margen ausente caia en la rama buena de
// cada ternaria y se pintaba como si el proyecto fuera bien.
//
// Se corrige a proposito: sin dato el color es **neutro**. Un dato que falta no
// es un dato bueno, y en una pantalla de rentabilidad esa diferencia se lee como
// una afirmacion sobre el negocio. Es un cambio de comportamiento, y va escrito
// aqui para que se vea que es intencionado y no un efecto colateral de tipar.
// ─────────────────────────────────────────────────────────────────────────────

/** Neutro: ni bien ni mal, porque no hay dato. */
const SIN_DATO = 'var(--text-3)'

/** Verde por encima de cero, rojo por debajo, neutro sin dato. */
function colorDeSigno(valor?: number, positivo = 'var(--accent)'): string {
  if (valor == null) return SIN_DATO
  return valor >= 0 ? positivo : 'var(--danger)'
}

/** El semaforo de un margen en porcentaje, con los cortes del negocio. */
function colorDeMargen(pct?: number, cortes: number[] = [0, 15, 30]): string {
  if (pct == null) return SIN_DATO
  const [malo, flojo, medio] = cortes as [number, number, number]
  if (pct < malo) return 'var(--danger)'
  if (pct < flojo) return 'var(--warning)'
  if (pct < medio) return 'var(--accent)'
  return 'var(--success)'
}

function MarginBar({ margin_pct }: { margin_pct: number }) {
  const color = margin_pct < 0 ? 'var(--danger)' : margin_pct < 15 ? 'var(--warning)' : margin_pct < 30 ? 'var(--accent)' : 'var(--success)'
  const w = Math.min(Math.abs(margin_pct), 100)
  return (
    <div className="prof-card">
      <div className="prof-box" style={{ '--prof-box-left': margin_pct < 0 ? `${50 - w/2}%` : '0', '--prof-box-width': `${margin_pct < 0 ? w/2 : Math.min(margin_pct, 100)}%`, '--prof-box-background': color } as CSSProperties} />
    </div>
  )
}

function MilestoneRow({ m, projectId, onUpdate }: { m: MilestoneItem; projectId: string | number; onUpdate?: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const t = useAppT()
  const { mutate: update } = useMutation({
    mutationFn: (data: Partial<MilestoneItem>) => profitabilityApi.updateMilestone(projectId, m.id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profitability-detail', projectId] }); if (onUpdate) onUpdate() },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: () => profitabilityApi.deleteMilestone(projectId, m.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profitability-detail', projectId] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div className="prof-row" style={{ '--prof-row-background': m.is_completed ? 'var(--success-bg)' : 'var(--surface-2)', '--prof-row-border': `1px solid ${m.is_completed ? 'var(--success-border)' : 'var(--surface-4)'}` } as CSSProperties}>
      <input className="prof-input" type="checkbox" aria-label={m.name} checked={m.is_completed} onChange={e => update({ is_completed: e.target.checked, completed_date: e.target.checked ? new Date().toISOString().split('T')[0] : null })} />
      <div className="u-flex1">
        <div className="prof-text-base" style={{ '--prof-text-base-text-decoration': m.is_completed ? 'line-through' : 'none', '--prof-text-base-color': m.is_completed ? 'var(--text-2)' : 'var(--text-1)' } as CSSProperties}>{m.name}</div>
        {m.due_date && <div className="prof-text-xs" style={{ '--prof-text-xs-color': new Date(m.due_date) < new Date() && !m.is_completed ? 'var(--danger)' : 'var(--text-2)' } as CSSProperties}>📅 {fmtDate(m.due_date)}</div>}
      </div>
      {m.billing_amount && (
        <div className="prof-text">
          <div className="prof-text-success-base-strong-mono">{fmtCurrency(m.billing_amount)}</div>
          {m.billing_pct && <div className="u-text2-2xs">{t('rentabilidad_ui.pct_contrato', { n: m.billing_pct })}</div>}
        </div>
      )}
      <div className="u-row-6">
        {/* Se factura en Facturación por hitos, que pide aprobación y genera la factura (revisión 2026-11). */}
        {m.is_completed && !m.is_billed && (
          <Link to="/milestone-billing" className="prof-enlace-facturar">{t('rentabilidad_ui.facturar_en_hitos')}</Link>
        )}
        {m.is_billed && <span className="prof-text-success-xs">{t('rentabilidad_ui.facturado')}</span>}
        <button className="prof-btn-danger-xs" aria-label={t('rentabilidad_ui.eliminar_hito')} title={t('rentabilidad_ui.eliminar_hito')} onClick={() => { openConfirmGlobal({ message: t('rentabilidad_ui.eliminar_hito_confirm'), onConfirm: () => del(), danger: true }) }}>🗑</button>
      </div>
    </div>
  )
}

function ProjectDetail({ projectId, onClose }: { projectId: string | number; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showAddMilestone, setShowAddMilestone] = useState(false)
  const [msForm, setMsForm] = useState({ name: '', due_date: '', billing_amount: '', billing_pct: '', sort_order: 0 })

  const { data, isLoading } = useQuery<RentabilidadDetallada>({
    queryKey: ['profitability-detail', projectId],
    queryFn: () => profitabilityApi.get(projectId).then(r => r.data),
  })

  const { mutate: addMilestone } = useMutation({
    mutationFn: (d: { name: string; due_date: string; billing_amount: string; billing_pct: string; sort_order: number }) => profitabilityApi.createMilestone(projectId, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profitability-detail', projectId] }); setShowAddMilestone(false); setMsForm({ name: '', due_date: '', billing_amount: '', billing_pct: '', sort_order: 0 }) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (isLoading) return <Modal open title={t('rentabilidad_ui.cargando')} onClose={onClose}><Spinner /></Modal>
  if (!data) return null

  const marginColor = data.margin_pct < 0 ? 'var(--danger)' : data.margin_pct < 15 ? 'var(--warning)' : data.margin_pct < 30 ? 'var(--accent)' : 'var(--success)'

  return (
    <Modal open title={`${data.project_code} — ${data.project_name}`} onClose={onClose} width={720}>
      {/* KPIs */}
      <div className="prof-grid">
        {[
          { label: t('rentabilidad_ui.ingresos'), value: fmtCurrency(data.billing_revenue), color: 'var(--success)' },
          { label: t('rentabilidad_ui.coste'), value: fmtCurrency(data.total_cost ?? data.internal_cost), color: 'var(--warning)' },
          { label: t('rentabilidad_ui.margen_bruto'), value: fmtCurrency(data.gross_margin), color: marginColor },
          { label: t('rentabilidad_ui.pct_margen'), value: `${data.margin_pct.toFixed(1)}%`, color: marginColor },
        ].map(({ label, value, color }) => (
          <div className="prof-card-2" key={label}>
            <div className="prof-text-muted-xs">{label}</div>
            <div className="prof-text-xl-strong-mono" style={{ '--prof-text-xl-strong-mono-color': color } as CSSProperties}>{value}</div>
          </div>
        ))}
      </div>
      {/* El coste: personal (imputaciones) + gastos del proyecto (su parte del reparto) + subcontrata. */}
      <div className="prof-row-muted">
        <span>{t('rentabilidad_ui.personal')} <strong>{fmtCurrency(data.internal_cost)}</strong></span>
        <span>{t('rentabilidad_ui.gastos')} <strong>{fmtCurrency(data.expenses_cost ?? 0)}</strong></span>
        <span>{t('rentabilidad_ui.subcontrata')} <strong>{fmtCurrency(data.subcontract_cost ?? 0)}</strong></span>
      </div>

      {/* Panel EVM — Earned Value Management */}
      {data.eac !== undefined && (
        <div className="prof-card-3">
          <div className="prof-row-2">
            {t('rentabilidad_ui.evm')}
            <span className="prof-box-2" style={{ '--prof-box-2-background': data.risk_flag === 'critical' ? 'var(--danger-bg)' : data.risk_flag === 'warning' ? 'var(--warning-bg)' : 'var(--success-bg)', '--prof-box-2-color': data.risk_flag === 'critical' ? 'var(--danger)' : data.risk_flag === 'warning' ? 'var(--warning)' : 'var(--success)' } as CSSProperties}>
              {data.risk_flag === 'critical' ? t('rentabilidad_ui.riesgo_alto') : data.risk_flag === 'warning' ? t('rentabilidad_ui.atencion') : t('rentabilidad_ui.ok')}
            </span>
          </div>
          <div className="prof-grid-2">
            {[
              { label: 'EAC', value: fmtCurrency(data.eac), desc: t('rentabilidad_ui.eac_desc'), color: colorDeSigno(data.vac, 'var(--success)') },
              { label: 'ETC', value: fmtCurrency(data.etc), desc: t('rentabilidad_ui.etc_desc'),        color: 'var(--accent)' },
              { label: 'VAC', value: fmtCurrency(data.vac), desc: t('rentabilidad_ui.vac_desc'),  color: colorDeSigno(data.vac, 'var(--success)') },
              { label: t('rentabilidad_ui.margen_final'), value: `${data.margin_at_completion?.toFixed(1) || '—'}%`, desc: t('rentabilidad_ui.margen_final_desc'), color: (data.margin_at_completion||0) < 10 ? 'var(--danger)' : 'var(--success)' },
            ].map(k => (
              <div className="prof-card-4" key={k.label}>
                <div className="prof-text-muted-2xs">{k.label}</div>
                <div className="prof-text-lg-strong-mono prof-text-2" style={{ '--prof-text-2-color': k.color } as CSSProperties}>{k.value}</div>
                <div className="prof-text-muted-2xs-2">{k.desc}</div>
              </div>
            ))}
          </div>
          <div className="prof-grid-3">
            {[
              { label: 'CPI', value: data.cpi?.toFixed(2) || '—', desc: t('rentabilidad_ui.cpi_desc'), ok: (data.cpi||0) >= 1 },
              { label: 'SPI', value: data.spi?.toFixed(2) || '—', desc: t('rentabilidad_ui.spi_desc'), ok: (data.spi||0) >= 1 },
              { label: 'CV',  value: fmtCurrency(data.cv),          desc: t('rentabilidad_ui.cv_desc'), ok: (data.cv||0) >= 0 },
              { label: 'SV',  value: fmtCurrency(data.sv),          desc: t('rentabilidad_ui.sv_desc'), ok: (data.sv||0) >= 0 },
            ].map(k => (
              <div className="prof-card-4" key={k.label}>
                <div className="prof-text-muted-2xs">{k.label}</div>
                <div className="prof-text-lg-strong-mono-2" style={{ '--prof-text-lg-strong-mono-2-color': k.ok ? 'var(--success)' : 'var(--danger)' } as CSSProperties}>{k.value}</div>
                <div className="prof-text-muted-2xs-2">{k.desc}</div>
              </div>
            ))}
          </div>
          <div className="prof-box-muted">
            {t('profitability.cpi_1_bajo_coste_spi_1_adelantado')}
          </div>
        </div>
      )}

      <div className="prof-grid-4">
        {/* Hours */}
        <Card className="profitab-sx1">
          <h4 className="prof-title-muted-base-strong">{t('rentabilidad_ui.horas')}</h4>
          {[
            { label: t('rentabilidad_ui.totales'), value: fmtHours(data.total_hours) },
            { label: t('rentabilidad_ui.facturables'), value: fmtHours(data.billable_hours) },
            { label: t('rentabilidad_ui.presupuestadas'), value: data.budget_hours ? fmtHours(data.budget_hours) : '—' },
            { label: t('rentabilidad_ui.tarifa_media_coste'), value: `${fmtMoneda(data.avg_cost_rate)}/h` },
            { label: t('rentabilidad_ui.tarifa_cliente'), value: data.billing_rate ? `${fmtMoneda(data.billing_rate)}/h` : '—' },
          ].map(({ label, value }) => (
            <div className="prof-row-3" key={label}>
              <span className="u-text2">{label}</span>
              <span className="u-600">{value}</span>
            </div>
          ))}
        </Card>

        {/* By person */}
        <Card className="profitab-sx1">
          <h4 className="prof-title-muted-base-strong">{t('profitability.por_persona')}</h4>
          {data.by_person?.length === 0 ? <EmptyState icon="👤" title={t('profitability.sin_detalle_por_persona')} /> : (
            data.by_person?.slice(0, 6).map(p => (
              <div className="prof-row-4" key={p.user_id}>
                <span>{p.user_name}</span>
                <div className="prof-row-5">
                  <span className="u-text2">{fmtHours(p.hours)}</span>
                  <span className="prof-text-warning-mono">{fmtCurrency(p.cost)}</span>
                </div>
              </div>
            ))
          )}
        </Card>
      </div>

      {/* Weekly evolution */}
      {(data.by_week?.length ?? 0) > 0 && (
        <Card className="profitab-sx2">
          <h4 className="prof-title-muted-base-strong">{t('profitability.evolucion_semanal')}</h4>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={data.by_week} margin={{ top: 0, right: 0, left: -20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
              <XAxis dataKey="week" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} tickFormatter={w => w.slice(5)} angle={-30} textAnchor="end" />
              <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
              <Tooltip contentStyle={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-xs)" }} formatter={v => [`${(v as number).toFixed(1)}h`, t('rentabilidad_ui.horas')]} />
              <Bar dataKey="hours" fill="var(--accent)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Milestones */}
      <Card className="profitab-sx1">
        <div className="prof-row-6">
          <h4 className="prof-title-muted-base-strong-2">{t('profitability.hitos_de_facturacion')}</h4>
          <Button size="sm" onClick={() => setShowAddMilestone(true)} icon="＋">{t('profitability.anadir_hito')}</Button>
        </div>
        {data.milestones?.length === 0 ? (
          <EmptyState icon="🏁" title={t('profitability.sin_hitos_de_facturacion')} description={t('rentabilidad_ui.sin_hitos_desc')} />
        ) : (
          <div className="u-stack-8">
            {(data.milestones ?? []).map(m => (
              <MilestoneRow key={m.id} m={m} projectId={projectId} />
            ))}
            <div className="prof-row-7">
              <span className="u-text2">{t('rentabilidad_ui.total_facturado')}</span>
              <span className="prof-text-success-strong-mono">
                {fmtCurrency((data.milestones ?? []).filter(m => m.is_billed).reduce((s, m) => s + (m.billing_amount || 0), 0))}
              </span>
            </div>
          </div>
        )}

        {showAddMilestone && (
          <div className="prof-card-5">
            <div className="prof-grid-5">
              <div><label className="prof-ls" id={`${idCampo}-eta356`} htmlFor={`${idCampo}-a356`}>{t('rentabilidad_ui.nombre')}</label><input className="prof-fs" id={`${idCampo}-a356`} aria-labelledby={`${idCampo}-eta356`} value={msForm.name} onChange={e => setMsForm(f => ({ ...f, name: e.target.value }))} placeholder={t('profitability.nombre_del_hito')} /></div>
              <div><label className="prof-ls" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{t('rentabilidad_ui.fecha')}</label><DateInput id={`${idCampo}-1`} value={msForm.due_date} onChange={e => setMsForm(f => ({ ...f, due_date: e.target.value }))} className="prof-fs" /></div>
              <div><label className="prof-ls" htmlFor={`${idCampo}-importe`}>{t('rentabilidad_ui.importe_moneda', { moneda: fmtMoneda.simbolo })}</label><input className="prof-fs" id={`${idCampo}-importe`} type="number" value={msForm.billing_amount} onChange={e => setMsForm(f => ({ ...f, billing_amount: e.target.value }))} placeholder={t('profitability.importe_del_hito')} aria-label={t('profitability.importe_del_hito')} /></div>
              <div><label className="prof-ls" id={`${idCampo}-eta359`} htmlFor={`${idCampo}-a359`}>{t('rentabilidad_ui.pct_contrato_label')}</label><input className="prof-fs" id={`${idCampo}-a359`} aria-labelledby={`${idCampo}-eta359`} type="number" value={msForm.billing_pct} onChange={e => setMsForm(f => ({ ...f, billing_pct: e.target.value }))} placeholder={t('profitability.porcentaje_del_contrato')} /></div>
            </div>
            <div className="u-row-8">
              <Button size="sm" onClick={() => addMilestone(msForm)} disabled={!msForm.name}>{t('profitability.anadir')}</Button>
              <Button size="sm" variant="secondary" onClick={() => setShowAddMilestone(false)}>{t('common.cancel')}</Button>
            </div>
          </div>
        )}
      </Card>
    </Modal>
  )
}

export default function ProfitabilityPage() {
  const t = useAppT()
  const { hasRole: _hasRole } = useAuth()
  const [selectedProject, setSelectedProject] = useState<string | number | null>(null)
  const [statusFilter, setStatusFilter] = useState('active')

  const { data, isLoading } = useQuery<ResumenDeRentabilidad>({
    queryKey: ['profitability-summary', statusFilter],
    queryFn: () => profitabilityApi.summary({ status: statusFilter }).then(r => r.data),
  })

  const projects = data?.projects || []
  const portfolio: Partial<ResumenDeRentabilidad['portfolio']> = data?.portfolio ?? {}

  return (
    <PageShell>
      <PageHeader
        icon={<TrendingUp size={18} />}
        title={t('profitability.title')}
        subtitle={t('profitability.subtitle')}
        actions={
          <select className="prof-input-2" aria-label={t('rentabilidad_ui.filtro_estado')} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option value="active">{t('rentabilidad_ui.proyectos_activos')}</option>
            <option value="closed">{t('rentabilidad_ui.cerrados')}</option>
          </select>
        }
      showListExport={false}
      />

      {/* Portfolio KPIs */}
      {(portfolio.project_count ?? 0) > 0 && (
        <div className="prof-row-8">
          {[
            { label: t('rentabilidad_ui.ingresos_cartera'), value: fmtCurrency(portfolio.total_revenue), color: 'var(--success)', icon: '💰' },
            { label: t('rentabilidad_ui.coste_total'), value: fmtCurrency(portfolio.total_cost), color: 'var(--warning)', icon: '💸' },
            { label: t('rentabilidad_ui.margen_total'), value: fmtCurrency(portfolio.total_margin), color: colorDeSigno(portfolio.total_margin), icon: '📊' },
            { label: t('rentabilidad_ui.margen_medio'), value: portfolio.margin_pct == null ? '—' : `${portfolio.margin_pct.toFixed(1)}%`, color: colorDeMargen(portfolio.margin_pct, [10, 20, Infinity]), icon: '📈' },
            { label: t('rentabilidad_ui.proyectos'), value: portfolio.project_count, color: 'var(--text-2)', icon: '📁' },
          ].map(({ label, value, color, icon }) => (
            <div className="prof-card-6" key={label}>
              <div className="prof-text-xl">{icon}</div>
              <div className="prof-text-xl-em-strong-mono" style={{ '--prof-text-xl-em-strong-mono-color': color } as CSSProperties}>{value}</div>
              <div className="prof-text-muted-sm">{label}</div>
            </div>
          ))}
        </div>
      )}

      {isLoading ? <Spinner /> : projects.length === 0 ? (
        <EmptyState icon="💰" title={t('profitability.sin_datos_de_rentabilidad')} description={t('rentabilidad_ui.sin_datos_desc')} />
      ) : (
        <>
          {/* Chart */}
          <Card className="profitab-sx3">
            <h3 className="prof-title-muted-md-strong">{t('profitability.margen_por_proyecto')}</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={projects.slice().reverse()} margin={{ top: 0, right: 0, left: 0, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="project_code" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} angle={-35} textAnchor="end" />
                <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={v => `${v.toFixed(0)}%`} />
                <Tooltip contentStyle={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-xs)" }} formatter={v => [`${(v as number).toFixed(1)}%`, t('rentabilidad_ui.margen')]} />
                <Bar dataKey="margin_pct" radius={[3, 3, 0, 0]}>
                  {projects.slice().reverse().map((p, i) => (
                    <Cell key={i} fill={colorDeMargen(p.margin_pct)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>

          {/* Table */}
          <div className="ds-card ds-card--plano">
            <div className="prof-grid-muted">
              <span>{t('rentabilidad_ui.proyecto')}</span><span>{t('rentabilidad_ui.ingresos')}</span><span>{t('rentabilidad_ui.coste')}</span><span>{t('rentabilidad_ui.margen')}</span><span>{t('rentabilidad_ui.pct_margen')}</span><span>{t('rentabilidad_ui.horas')}</span><span></span>
            </div>
            {projects.map(p => (
              <div className="prof-grid-6" key={p.project_id}
                role="button" tabIndex={0}
                onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && p.project_id != null) { e.preventDefault(); setSelectedProject(p.project_id) } }}
                onClick={() => p.project_id != null && setSelectedProject(p.project_id)}>
                <div>
                  <div className="u-base-600">{p.project_name}</div>
                  <div className="u-text2-xs">{p.project_code} · {p.client_name || p.department || '—'}</div>
                </div>
                <span className="prof-text-success-base-mono">{fmtCurrency(p.billing_revenue)}</span>
                <span className="prof-text-warning-base-mono">{fmtCurrency(p.total_cost ?? p.internal_cost)}</span>
                <span className="prof-text-base-strong-mono prof-text-3" style={{ '--prof-text-3-color': colorDeSigno(p.gross_margin) } as CSSProperties}>{fmtCurrency(p.gross_margin)}</span>
                <div>
                  <div className="prof-text-base-strong-mono-2 prof-text-4" style={{ '--prof-text-4-color': colorDeMargen(p.margin_pct, [0, 15, Infinity]) } as CSSProperties}>{p.margin_pct == null ? '—' : `${p.margin_pct.toFixed(1)}%`}</div>
                  <MarginBar margin_pct={p.margin_pct ?? 0} />
                </div>
                <span className="u-text2-sm">{fmtHours(p.total_hours)}</span>
                <button className="prof-btn-xs" onClick={e => { e.stopPropagation(); if (p.project_id != null) setSelectedProject(p.project_id) }}>{t('rentabilidad_ui.detalle')}</button>
              </div>
            ))}
          </div>
        </>
      )}

      {selectedProject && <ProjectDetail projectId={selectedProject} onClose={() => setSelectedProject(null)} />}
    </PageShell>
  )
}