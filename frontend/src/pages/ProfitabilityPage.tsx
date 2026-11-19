/**
 * ProfitabilityPage — rentabilidad por proyecto (/profitability).
 *
 * 16-11-2026: pasada de diseño. El filtro de estado sale de la cabecera a una
 * barra bajo ella; KPIs con KpiCard e icono lucide (antes emojis y cifras en
 * monoespaciada); vacíos con icono lucide (antes emojis como icono); botones y
 * campos del kit (antes «＋», papelera emoji, campos grises); EVM con KpiCard y
 * StatusBadge (antes emojis de semáforo en los textos).
 */
import { useState, type CSSProperties, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { profitabilityApi } from '../services/api'
import type { HitoDeRentabilidad, RentabilidadDetallada, ResumenDeRentabilidad } from '../services/api/tipos-finanzas'
import { Card, Button, Modal, Spinner, EmptyState, Input, KpiCard, Checkbox, Pulsable, Select } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { TrendingUp, Plus, Trash2, CalendarDays, Wallet, Receipt, PieChart, Percent, FolderOpen, Users, Flag, Coins, ArrowRight } from 'lucide-react'
import { fmtCurrency, fmtHours, fmtDate, extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import EvolucionDelMargen from './profitability/EvolucionDelMargen'
import './ProfitabilityPage.css'
import { TOOLTIP_SUPERFICIE_3_REDONDO_XS } from '../constants/estilosGrafico'
type MilestoneItem = HitoDeRentabilidad



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
    <div className="prof-barra">
      <div className="prof-barra__relleno" style={{ '--prof-izq': margin_pct < 0 ? `${50 - w/2}%` : '0', '--prof-ancho': `${margin_pct < 0 ? w/2 : Math.min(margin_pct, 100)}%`, '--prof-color': color } as CSSProperties} />
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
    <div className={`prof-hito${m.is_completed ? ' prof-hito--hecho' : ''}`}>
      <Checkbox aria-label={m.name} checked={!!m.is_completed} onChange={v => update({ is_completed: v, completed_date: v ? new Date().toISOString().split('T')[0] : null })} />
      <div className="u-flex1-min0">
        <div className="prof-hito__nombre">{m.name}</div>
        {m.due_date && <div className={`prof-hito__fecha${new Date(m.due_date) < new Date() && !m.is_completed ? ' prof-hito__fecha--vencida' : ''}`}><CalendarDays size={12} aria-hidden /> {fmtDate(m.due_date)}</div>}
      </div>
      {m.billing_amount && (
        <div className="prof-text">
          <div className="prof-cifra prof-cifra--ok">{fmtCurrency(m.billing_amount)}</div>
          {m.billing_pct && <div className="u-text2-2xs">{t('rentabilidad_ui.pct_contrato', { n: m.billing_pct })}</div>}
        </div>
      )}
      <div className="u-row-center-6">
        {/* Se factura en Facturación por hitos, que pide aprobación y genera la factura (revisión 2026-11). */}
        {m.is_completed && !m.is_billed && (
          <Link to="/milestone-billing" className="prof-enlace">{t('rentabilidad_ui.facturar_en_hitos')} <ArrowRight size={12} aria-hidden /></Link>
        )}
        {m.is_billed && <StatusBadge kind="success" caps={false}>{t('rentabilidad_ui.facturado')}</StatusBadge>}
        <Pulsable className="prof-icono-borrar" aria-label={t('rentabilidad_ui.eliminar_hito')} title={t('rentabilidad_ui.eliminar_hito')} onClick={() => { openConfirmGlobal({ message: t('rentabilidad_ui.eliminar_hito_confirm'), onConfirm: () => del(), danger: true }) }}><Trash2 size={14} aria-hidden /></Pulsable>
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

  const margenMalo = data.margin_pct < 0
  const margenFlojo = !margenMalo && data.margin_pct < 15
  const riesgo = data.risk_flag === 'critical' ? { kind: 'danger' as const, label: t('rentabilidad_ui.riesgo_alto') }
    : data.risk_flag === 'warning' ? { kind: 'warning' as const, label: t('rentabilidad_ui.atencion') }
    : { kind: 'success' as const, label: t('rentabilidad_ui.ok') }

  return (
    <Modal open title={`${data.project_code} — ${data.project_name}`} onClose={onClose} width={720}>
      {/* KPIs */}
      <div className="u-stack-16">
      <div className="ds-grid-stats">
        <KpiCard icon={<Wallet size={16} />} label={t('rentabilidad_ui.ingresos')} value={fmtCurrency(data.billing_revenue)} />
        <KpiCard icon={<Receipt size={16} />} label={t('rentabilidad_ui.coste')} value={fmtCurrency(data.total_cost ?? data.internal_cost)} />
        <KpiCard icon={<Coins size={16} />} label={t('rentabilidad_ui.margen_bruto')} value={fmtCurrency(data.gross_margin)} danger={margenMalo} warning={margenFlojo} />
        <KpiCard icon={<Percent size={16} />} label={t('rentabilidad_ui.pct_margen')} value={`${data.margin_pct.toFixed(1)}%`} danger={margenMalo} warning={margenFlojo} />
      </div>
      {/* El coste: personal (imputaciones) + gastos del proyecto (su parte del reparto) + subcontrata. */}
      <div className="prof-desglose">
        <span>{t('rentabilidad_ui.personal')} <strong>{fmtCurrency(data.internal_cost)}</strong></span>
        <span>{t('rentabilidad_ui.gastos')} <strong>{fmtCurrency(data.expenses_cost ?? 0)}</strong></span>
        <span>{t('rentabilidad_ui.subcontrata')} <strong>{fmtCurrency(data.subcontract_cost ?? 0)}</strong></span>
      </div>

      {/* Panel EVM — Earned Value Management */}
      {data.eac !== undefined && (
        <Card className="prof-seccion">
          <div className="prof-seccion__cabecera">
            <h4 className="prof-seccion__titulo">{t('rentabilidad_ui.evm')}</h4>
            <StatusBadge kind={riesgo.kind} dot caps={false}>{riesgo.label}</StatusBadge>
          </div>
          <div className="ds-grid-stats">
            <KpiCard label="EAC" value={fmtCurrency(data.eac)} sub={t('rentabilidad_ui.eac_desc')} danger={data.vac != null && data.vac < 0} />
            <KpiCard label="ETC" value={fmtCurrency(data.etc)} sub={t('rentabilidad_ui.etc_desc')} />
            <KpiCard label="VAC" value={fmtCurrency(data.vac)} sub={t('rentabilidad_ui.vac_desc')} danger={data.vac != null && data.vac < 0} />
            <KpiCard label={t('rentabilidad_ui.margen_final')} value={data.margin_at_completion == null ? '—' : `${data.margin_at_completion.toFixed(1)}%`} sub={t('rentabilidad_ui.margen_final_desc')} danger={data.margin_at_completion != null && data.margin_at_completion < 10} />
            <KpiCard label="CPI" value={data.cpi == null ? '—' : data.cpi.toFixed(2)} sub={t('rentabilidad_ui.cpi_desc')} danger={data.cpi != null && data.cpi < 1} />
            <KpiCard label="SPI" value={data.spi == null ? '—' : data.spi.toFixed(2)} sub={t('rentabilidad_ui.spi_desc')} danger={data.spi != null && data.spi < 1} />
            <KpiCard label="CV" value={fmtCurrency(data.cv)} sub={t('rentabilidad_ui.cv_desc')} danger={data.cv != null && data.cv < 0} />
            <KpiCard label="SV" value={fmtCurrency(data.sv)} sub={t('rentabilidad_ui.sv_desc')} danger={data.sv != null && data.sv < 0} />
          </div>
          <div className="prof-nota">
            {t('profitability.cpi_1_bajo_coste_spi_1_adelantado')}
          </div>
        </Card>
      )}

      <div className="prof-dos-columnas">
        {/* Hours */}
        <Card className="prof-seccion">
          <h4 className="prof-seccion__titulo">{t('rentabilidad_ui.horas')}</h4>
          {[
            { label: t('rentabilidad_ui.totales'), value: fmtHours(data.total_hours) },
            { label: t('rentabilidad_ui.facturables'), value: fmtHours(data.billable_hours) },
            { label: t('rentabilidad_ui.presupuestadas'), value: data.budget_hours ? fmtHours(data.budget_hours) : '—' },
            { label: t('rentabilidad_ui.tarifa_media_coste'), value: `${fmtMoneda(data.avg_cost_rate)}/h` },
            { label: t('rentabilidad_ui.tarifa_cliente'), value: data.billing_rate ? `${fmtMoneda(data.billing_rate)}/h` : '—' },
          ].map(({ label, value }) => (
            <div className="prof-dato" key={label}>
              <span className="u-text2">{label}</span>
              <span className="u-600">{value}</span>
            </div>
          ))}
        </Card>

        {/* By person */}
        <Card className="prof-seccion">
          <h4 className="prof-seccion__titulo">{t('profitability.por_persona')}</h4>
          {!data.by_person?.length ? <EmptyState icon={<Users size={28} />} title={t('profitability.sin_detalle_por_persona')} description={t('rentabilidad_ui.sin_personas_desc')} /> : (
            data.by_person?.slice(0, 6).map(p => (
              <div className="prof-dato" key={p.user_id}>
                <span className="u-min0">{p.user_name}</span>
                <div className="u-row-center-12">
                  <span className="u-text2">{fmtHours(p.hours)}</span>
                  <span className="prof-cifra">{fmtCurrency(p.cost)}</span>
                </div>
              </div>
            ))
          )}
        </Card>
      </div>

      {/* Weekly evolution */}
      {(data.by_week?.length ?? 0) > 0 && (
        <Card className="prof-seccion">
          <h4 className="prof-seccion__titulo">{t('profitability.evolucion_semanal')}</h4>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={data.by_week} margin={{ top: 0, right: 0, left: -20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
              <XAxis dataKey="week" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} tickFormatter={w => w.slice(5)} angle={-30} textAnchor="end" />
              <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
              <Tooltip contentStyle={TOOLTIP_SUPERFICIE_3_REDONDO_XS} formatter={v => [`${(v as number).toFixed(1)}h`, t('rentabilidad_ui.horas')]} />
              <Bar dataKey="hours" fill="var(--accent)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Milestones */}
      <Card className="prof-seccion">
        <div className="prof-seccion__cabecera">
          <h4 className="prof-seccion__titulo">{t('profitability.hitos_de_facturacion')}</h4>
          <Button size="sm" onClick={() => setShowAddMilestone(true)} icon={<Plus size={13} />}>{t('profitability.anadir_hito')}</Button>
        </div>
        {!data.milestones?.length ? (
          <EmptyState icon={<Flag size={28} />} title={t('profitability.sin_hitos_de_facturacion')} description={t('rentabilidad_ui.sin_hitos_desc')} />
        ) : (
          <div className="u-stack-8">
            {(data.milestones ?? []).map(m => (
              <MilestoneRow key={m.id} m={m} projectId={projectId} />
            ))}
            <div className="prof-total">
              <span className="u-text2">{t('rentabilidad_ui.total_facturado')}</span>
              <span className="prof-cifra prof-cifra--ok">
                {fmtCurrency((data.milestones ?? []).filter(m => m.is_billed).reduce((s, m) => s + (m.billing_amount || 0), 0))}
              </span>
            </div>
          </div>
        )}

        {showAddMilestone && (
          <div className="prof-nuevo-hito">
            <div className="prof-nuevo-hito__campos">
              <Input label={t('rentabilidad_ui.nombre')} value={msForm.name} onChange={e => setMsForm(f => ({ ...f, name: e.target.value }))} placeholder={t('profitability.nombre_del_hito')} />
              <div className="ui-field"><label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-1`}>{t('rentabilidad_ui.fecha')}</label><DateInput id={`${idCampo}-1`} value={msForm.due_date} onChange={e => setMsForm(f => ({ ...f, due_date: e.target.value }))} className="ds-input" /></div>
              <Input label={t('rentabilidad_ui.importe_moneda', { moneda: fmtMoneda.simbolo })} type="number" value={msForm.billing_amount} onChange={e => setMsForm(f => ({ ...f, billing_amount: e.target.value }))} placeholder={t('profitability.importe_del_hito')} />
              <Input label={t('rentabilidad_ui.pct_contrato_label')} type="number" value={msForm.billing_pct} onChange={e => setMsForm(f => ({ ...f, billing_pct: e.target.value }))} placeholder={t('profitability.porcentaje_del_contrato')} />
            </div>
            <div className="u-row-8">
              <Button size="sm" icon={<Plus size={13} />} onClick={() => addMilestone(msForm)} disabled={!msForm.name}>{t('profitability.anadir')}</Button>
              <Button size="sm" variant="secondary" onClick={() => setShowAddMilestone(false)}>{t('common.cancel')}</Button>
            </div>
          </div>
        )}
      </Card>
      </div>
    </Modal>
  )
}

export default function ProfitabilityPage() {
  const t = useAppT()
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
        showListExport={false}
      />

      <div className="u-stack-16">
      <div className="ds-toolbar">
        <Select suelto placeholder={false} className="prof-filtro" aria-label={t('rentabilidad_ui.filtro_estado')} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="active">{t('rentabilidad_ui.proyectos_activos')}</option>
          <option value="closed">{t('rentabilidad_ui.cerrados')}</option>
        </Select>
      </div>

      {/* Portfolio KPIs */}
      {(portfolio.project_count ?? 0) > 0 && (
        <div className="ds-grid-stats">
          <KpiCard icon={<Wallet size={16} />} label={t('rentabilidad_ui.ingresos_cartera')} value={fmtCurrency(portfolio.total_revenue)} />
          <KpiCard icon={<Receipt size={16} />} label={t('rentabilidad_ui.coste_total')} value={fmtCurrency(portfolio.total_cost)} />
          <KpiCard icon={<Coins size={16} />} label={t('rentabilidad_ui.margen_total')} value={fmtCurrency(portfolio.total_margin)} danger={portfolio.total_margin != null && portfolio.total_margin < 0} />
          <KpiCard icon={<PieChart size={16} />} label={t('rentabilidad_ui.margen_medio')} value={portfolio.margin_pct == null ? '—' : `${portfolio.margin_pct.toFixed(1)}%`}
            danger={portfolio.margin_pct != null && portfolio.margin_pct < 10} warning={portfolio.margin_pct != null && portfolio.margin_pct >= 10 && portfolio.margin_pct < 20} />
          <KpiCard icon={<FolderOpen size={16} />} label={t('rentabilidad_ui.proyectos')} value={portfolio.project_count} />
        </div>
      )}

      {/* 17-11-2026: evolución de ingreso, coste y margen con periodo libre y desglose. */}
      <EvolucionDelMargen />

      {isLoading ? <Spinner /> : projects.length === 0 ? (
        <EmptyState icon={<TrendingUp size={28} />} title={t('profitability.sin_datos_de_rentabilidad')} description={t('rentabilidad_ui.sin_datos_desc')} />
      ) : (
        <>
          {/* Chart */}
          <Card className="prof-seccion">
            <h3 className="prof-seccion__titulo">{t('profitability.margen_por_proyecto')}</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={projects.slice().reverse()} margin={{ top: 0, right: 0, left: 0, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="project_code" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} angle={-35} textAnchor="end" />
                <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={v => `${v.toFixed(0)}%`} />
                <Tooltip contentStyle={TOOLTIP_SUPERFICIE_3_REDONDO_XS} formatter={v => [`${(v as number).toFixed(1)}%`, t('rentabilidad_ui.margen')]} />
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
            <div className="prof-tabla-scroll">
            <div className="prof-fila prof-fila--cabecera">
              <span>{t('rentabilidad_ui.proyecto')}</span><span>{t('rentabilidad_ui.ingresos')}</span><span>{t('rentabilidad_ui.coste')}</span><span>{t('rentabilidad_ui.margen')}</span><span>{t('rentabilidad_ui.pct_margen')}</span><span>{t('rentabilidad_ui.horas')}</span><span></span>
            </div>
            {projects.map(p => (
              <div className="prof-fila" key={p.project_id}
                role="button" tabIndex={0}
                onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && p.project_id != null) { e.preventDefault(); setSelectedProject(p.project_id) } }}
                onClick={() => p.project_id != null && setSelectedProject(p.project_id)}>
                <div className="u-min0">
                  <div className="u-base-600">{p.project_name}</div>
                  <div className="u-text2-xs">{p.project_code} · {p.client_name || p.department || '—'}</div>
                </div>
                <span className="prof-cifra">{fmtCurrency(p.billing_revenue)}</span>
                <span className="prof-cifra">{fmtCurrency(p.total_cost ?? p.internal_cost)}</span>
                <span className="prof-cifra prof-cifra--fuerte prof-cifra--color" style={{ '--prof-color': colorDeSigno(p.gross_margin) } as CSSProperties}>{fmtCurrency(p.gross_margin)}</span>
                <div>
                  <div className="prof-cifra prof-cifra--fuerte prof-cifra--color prof-cifra--barra" style={{ '--prof-color': colorDeMargen(p.margin_pct, [0, 15, Infinity]) } as CSSProperties}>{p.margin_pct == null ? '—' : `${p.margin_pct.toFixed(1)}%`}</div>
                  <MarginBar margin_pct={p.margin_pct ?? 0} />
                </div>
                <span className="u-text2-sm">{fmtHours(p.total_hours)}</span>
                <Button size="xs" variant="secondary" onClick={e => { e.stopPropagation(); if (p.project_id != null) setSelectedProject(p.project_id) }}>{t('rentabilidad_ui.detalle')}</Button>
              </div>
            ))}
            </div>
          </div>
        </>
      )}
      </div>

      {selectedProject && <ProjectDetail projectId={selectedProject} onClose={() => setSelectedProject(null)} />}
    </PageShell>
  )
}