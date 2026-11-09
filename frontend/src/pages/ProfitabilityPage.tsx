import { useState, type CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { profitabilityApi } from '../services/api'
import { Card, Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { TrendingUp } from 'lucide-react'
import { fmtCurrency, fmtHours, fmtDate, extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'

interface MilestoneItem {
  id: string | number
  name: string
  is_completed?: boolean
  is_billed?: boolean
  due_date?: string
  billing_amount?: number
  billing_pct?: number
  completed_date?: string | null
  billed_at?: string | null
  [key: string]: unknown
}

interface ProfitabilityProjectItem {
  project_id?: string | number
  project_name?: string
  project_code?: string
  client_name?: string
  department?: string
  billing_revenue?: number
  internal_cost?: number
  total_cost?: number
  gross_margin?: number
  margin_pct?: number
  total_hours?: number
}

interface ProfitabilityPortfolio {
  total_revenue?: number
  total_cost?: number
  total_margin?: number
  margin_pct?: number
  project_count?: number
}

interface ProfitabilitySummaryResponse {
  projects?: ProfitabilityProjectItem[]
  portfolio?: ProfitabilityPortfolio
}

interface ProjectDetailData {
  project_code: string
  project_name: string
  margin_pct: number
  billing_revenue: number
  internal_cost: number
  expenses_cost?: number
  subcontract_cost?: number
  total_cost?: number
  gross_margin: number
  eac?: number
  etc?: number
  vac?: number
  margin_at_completion?: number
  cpi?: number
  spi?: number
  cv?: number
  sv?: number
  risk_flag?: 'critical' | 'warning' | 'ok'
  total_hours?: number
  billable_hours?: number
  budget_hours?: number
  avg_cost_rate?: number
  billing_rate?: number
  by_person?: Array<{ user_id: string | number; user_name?: string; hours: number; cost: number }>
  by_week?: Array<{ week: string; hours: number }>
  milestones?: MilestoneItem[]
}

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
    <div style={{ position: 'relative', height: 6, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
      <div style={{ position: 'absolute', left: margin_pct < 0 ? `${50 - w/2}%` : '0', width: `${margin_pct < 0 ? w/2 : Math.min(margin_pct, 100)}%`, height: '100%', background: color, borderRadius: 4 }} />
    </div>
  )
}

function MilestoneRow({ m, projectId, onUpdate }: { m: MilestoneItem; projectId: string | number; onUpdate?: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
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
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: m.is_completed ? 'var(--success-bg)' : 'var(--surface-2)', border: `1px solid ${m.is_completed ? 'var(--success-border)' : 'var(--surface-4)'}`, borderRadius: 8 }}>
      <input type="checkbox" checked={m.is_completed} onChange={e => update({ is_completed: e.target.checked, completed_date: e.target.checked ? new Date().toISOString().split('T')[0] : null })} style={{ width: 16, height: 16, cursor: 'pointer' }} />
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: "var(--text-base)", fontWeight: 600, textDecoration: m.is_completed ? 'line-through' : 'none', color: m.is_completed ? 'var(--text-2)' : 'var(--text-1)' }}>{m.name}</div>
        {m.due_date && <div style={{ fontSize: "var(--text-xs)", color: new Date(m.due_date) < new Date() && !m.is_completed ? 'var(--danger)' : 'var(--text-2)' }}>📅 {fmtDate(m.due_date)}</div>}
      </div>
      {m.billing_amount && (
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{fmtCurrency(m.billing_amount)}</div>
          {m.billing_pct && <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>{m.billing_pct}% contrato</div>}
        </div>
      )}
      <div style={{ display: 'flex', gap: 6 }}>
        {/* Se factura en Facturación por hitos, que pide aprobación y genera la factura (revisión 2026-11). */}
        {m.is_completed && !m.is_billed && (
          <Link to="/milestone-billing" style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--success)', fontSize: "var(--text-xs)", textDecoration: 'none' }}>💶 Facturar en Hitos →</Link>
        )}
        {m.is_billed && <span style={{ fontSize: "var(--text-xs)", color: 'var(--success)' }}>✓ Facturado</span>}
        <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar este hito de facturación?', onConfirm: () => del(), danger: true }) }} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
      </div>
    </div>
  )
}

function ProjectDetail({ projectId, onClose }: { projectId: string | number; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showAddMilestone, setShowAddMilestone] = useState(false)
  const [msForm, setMsForm] = useState({ name: '', due_date: '', billing_amount: '', billing_pct: '', sort_order: 0 })
  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  const { data, isLoading } = useQuery<ProjectDetailData>({
    queryKey: ['profitability-detail', projectId],
    queryFn: () => profitabilityApi.get(projectId).then(r => r.data),
  })

  const { mutate: addMilestone } = useMutation({
    mutationFn: (d: { name: string; due_date: string; billing_amount: string; billing_pct: string; sort_order: number }) => profitabilityApi.createMilestone(projectId, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profitability-detail', projectId] }); setShowAddMilestone(false); setMsForm({ name: '', due_date: '', billing_amount: '', billing_pct: '', sort_order: 0 }) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (isLoading) return <Modal open title="Cargando rentabilidad" onClose={onClose}><Spinner /></Modal>
  if (!data) return null

  const marginColor = data.margin_pct < 0 ? 'var(--danger)' : data.margin_pct < 15 ? 'var(--warning)' : data.margin_pct < 30 ? 'var(--accent)' : 'var(--success)'

  return (
    <Modal open title={`${data.project_code} — ${data.project_name}`} onClose={onClose} width={720}>
      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(140px, 100%), 1fr))', gap: 12, marginBottom: 8 }}>
        {[
          { label: 'Ingresos', value: fmtCurrency(data.billing_revenue), color: 'var(--success)' },
          { label: 'Coste', value: fmtCurrency(data.total_cost ?? data.internal_cost), color: 'var(--warning)' },
          { label: 'Margen bruto', value: fmtCurrency(data.gross_margin), color: marginColor },
          { label: '% Margen', value: `${data.margin_pct.toFixed(1)}%`, color: marginColor },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ background: 'var(--surface-3)', borderRadius: 10, padding: '14px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
            <div style={{ fontSize: "var(--text-xl)", fontWeight: 800, fontFamily: 'var(--font-mono)', color }}>{value}</div>
          </div>
        ))}
      </div>
      {/* El coste: personal (imputaciones) + gastos del proyecto (su parte del reparto) + subcontrata. */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', justifyContent: 'center', fontSize: 'var(--text-xs)', color: 'var(--text-2)', marginBottom: 24 }}>
        <span>Personal: <strong>{fmtCurrency(data.internal_cost)}</strong></span>
        <span>Gastos: <strong>{fmtCurrency(data.expenses_cost ?? 0)}</strong></span>
        <span>Subcontrata: <strong>{fmtCurrency(data.subcontract_cost ?? 0)}</strong></span>
      </div>

      {/* Panel EVM — Earned Value Management */}
      {data.eac !== undefined && (
        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '16px 20px', marginBottom: 20 }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            📐 Earned Value Management (EVM)
            <span style={{
              fontSize: "var(--text-2xs)", padding: '2px 8px', borderRadius: 20, fontWeight: 700,
              background: data.risk_flag === 'critical' ? 'var(--danger-bg)' : data.risk_flag === 'warning' ? 'var(--warning-bg)' : 'var(--success-bg)',
              color:      data.risk_flag === 'critical' ? 'var(--danger)'   : data.risk_flag === 'warning' ? 'var(--warning)'   : 'var(--success)',
            }}>
              {data.risk_flag === 'critical' ? '🔴 Riesgo alto' : data.risk_flag === 'warning' ? '🟡 Atención' : '🟢 OK'}
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 12 }}>
            {[
              { label: 'EAC', value: fmtCurrency(data.eac), desc: 'Coste total estimado', color: colorDeSigno(data.vac, 'var(--success)') },
              { label: 'ETC', value: fmtCurrency(data.etc), desc: 'Coste restante',        color: 'var(--accent)' },
              { label: 'VAC', value: fmtCurrency(data.vac), desc: 'Desviación al cierre',  color: colorDeSigno(data.vac, 'var(--success)') },
              { label: 'Margen final est.', value: `${data.margin_at_completion?.toFixed(1) || '—'}%`, desc: 'Al completar proyecto', color: (data.margin_at_completion||0) < 10 ? 'var(--danger)' : 'var(--success)' },
            ].map(k => (
              <div key={k.label} style={{ background: 'var(--surface-2)', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k.label}</div>
                <div style={{ fontSize: "var(--text-lg)", fontWeight: 800, color: k.color, fontFamily: 'var(--font-mono)' }}>{k.value}</div>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 2 }}>{k.desc}</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
            {[
              { label: 'CPI', value: data.cpi?.toFixed(2) || '—', desc: 'Cost Performance Index', ok: (data.cpi||0) >= 1 },
              { label: 'SPI', value: data.spi?.toFixed(2) || '—', desc: 'Schedule Performance Index', ok: (data.spi||0) >= 1 },
              { label: 'CV',  value: fmtCurrency(data.cv),          desc: 'Variación de coste', ok: (data.cv||0) >= 0 },
              { label: 'SV',  value: fmtCurrency(data.sv),          desc: 'Variación de cronograma', ok: (data.sv||0) >= 0 },
            ].map(k => (
              <div key={k.label} style={{ background: 'var(--surface-2)', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k.label}</div>
                <div style={{ fontSize: "var(--text-lg)", fontWeight: 800, color: k.ok ? 'var(--success)' : 'var(--danger)', fontFamily: 'var(--font-mono)' }}>{k.value}</div>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 2 }}>{k.desc}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, fontSize: "var(--text-xs)", color: 'var(--text-2)', borderTop: '1px solid var(--surface-4)', paddingTop: 10 }}>
            {t('profitability.cpi_1_bajo_coste_spi_1_adelantado')}
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        {/* Hours */}
        <Card style={{ padding: 16 }}>
          <h4 style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 14, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Horas</h4>
          {[
            { label: 'Totales', value: fmtHours(data.total_hours) },
            { label: 'Facturables', value: fmtHours(data.billable_hours) },
            { label: 'Presupuestadas', value: data.budget_hours ? fmtHours(data.budget_hours) : '—' },
            { label: 'Tarifa media coste', value: `${data.avg_cost_rate}€/h` },
            { label: 'Tarifa cliente', value: data.billing_rate ? `${data.billing_rate}€/h` : '—' },
          ].map(({ label, value }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', fontSize: "var(--text-base)" }}>
              <span style={{ color: 'var(--text-2)' }}>{label}</span>
              <span style={{ fontWeight: 600 }}>{value}</span>
            </div>
          ))}
        </Card>

        {/* By person */}
        <Card style={{ padding: 16 }}>
          <h4 style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 14, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t('profitability.por_persona')}</h4>
          {data.by_person?.length === 0 ? <EmptyState icon="👤" title={t('profitability.sin_detalle_por_persona')} /> : (
            data.by_person?.slice(0, 6).map(p => (
              <div key={p.user_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', fontSize: "var(--text-sm)" }}>
                <span>{p.user_name}</span>
                <div style={{ display: 'flex', gap: 12 }}>
                  <span style={{ color: 'var(--text-2)' }}>{fmtHours(p.hours)}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--warning)' }}>{fmtCurrency(p.cost)}</span>
                </div>
              </div>
            ))
          )}
        </Card>
      </div>

      {/* Weekly evolution */}
      {(data.by_week?.length ?? 0) > 0 && (
        <Card style={{ padding: 16, marginBottom: 20 }}>
          <h4 style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 14, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t('profitability.evolucion_semanal')}</h4>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={data.by_week} margin={{ top: 0, right: 0, left: -20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
              <XAxis dataKey="week" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} tickFormatter={w => w.slice(5)} angle={-30} textAnchor="end" />
              <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
              <Tooltip contentStyle={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-xs)" }} formatter={v => [`${(v as number).toFixed(1)}h`, 'Horas']} />
              <Bar dataKey="hours" fill="#4f8ef7" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Milestones */}
      <Card style={{ padding: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <h4 style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t('profitability.hitos_de_facturacion')}</h4>
          <Button size="sm" onClick={() => setShowAddMilestone(true)} icon="＋">{t('profitability.anadir_hito')}</Button>
        </div>
        {data.milestones?.length === 0 ? (
          <EmptyState icon="🏁" title={t('profitability.sin_hitos_de_facturacion')} description="Anade hitos para seguir la facturacion del proyecto" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {(data.milestones ?? []).map(m => (
              <MilestoneRow key={m.id} m={m} projectId={projectId} />
            ))}
            <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 10, display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-base)" }}>
              <span style={{ color: 'var(--text-2)' }}>Total facturado:</span>
              <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>
                {fmtCurrency((data.milestones ?? []).filter(m => m.is_billed).reduce((s, m) => s + (m.billing_amount || 0), 0))}
              </span>
            </div>
          </div>
        )}

        {showAddMilestone && (
          <div style={{ marginTop: 14, padding: 14, background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 10 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 10, marginBottom: 10 }}>
              <div><label style={ls}>Nombre</label><input value={msForm.name} onChange={e => setMsForm(f => ({ ...f, name: e.target.value }))} style={fs} placeholder={t('profitability.nombre_del_hito')} aria-label={t('profitability.nombre_del_hito')} /></div>
              <div><label style={ls}>Fecha</label><input type="date" value={msForm.due_date} onChange={e => setMsForm(f => ({ ...f, due_date: e.target.value }))} style={fs} /></div>
              <div><label style={ls}>Importe €</label><input type="number" value={msForm.billing_amount} onChange={e => setMsForm(f => ({ ...f, billing_amount: e.target.value }))} style={fs} placeholder={t('profitability.importe_del_hito')} aria-label={t('profitability.importe_del_hito')} /></div>
              <div><label style={ls}>% Contrato</label><input type="number" value={msForm.billing_pct} onChange={e => setMsForm(f => ({ ...f, billing_pct: e.target.value }))} style={fs} placeholder={t('profitability.porcentaje_del_contrato')} aria-label={t('profitability.porcentaje_del_contrato')} /></div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button size="sm" onClick={() => addMilestone(msForm)} disabled={!msForm.name}>{t('profitability.anadir')}</Button>
              <Button size="sm" variant="secondary" onClick={() => setShowAddMilestone(false)}>Cancelar</Button>
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

  const { data, isLoading } = useQuery<ProfitabilitySummaryResponse>({
    queryKey: ['profitability-summary', statusFilter],
    queryFn: () => profitabilityApi.summary({ status: statusFilter }).then(r => r.data),
  })

  const projects = data?.projects || []
  const portfolio = data?.portfolio || {}

  return (
    <PageShell>
      <PageHeader
        icon={<TrendingUp size={18} />}
        title={t('profitability.title')}
        subtitle={t('profitability.subtitle')}
        actions={
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
            <option value="active">Proyectos activos</option>
            <option value="closed">Cerrados</option>
          </select>
        }
      showListExport={false}
      />

      {/* Portfolio KPIs */}
      {(portfolio.project_count ?? 0) > 0 && (
        <div style={{ display: 'flex', gap: 14, marginBottom: 28, flexWrap: 'wrap' }}>
          {[
            { label: 'Ingresos cartera', value: fmtCurrency(portfolio.total_revenue), color: 'var(--success)', icon: '💰' },
            { label: 'Coste total', value: fmtCurrency(portfolio.total_cost), color: 'var(--warning)', icon: '💸' },
            { label: 'Margen total', value: fmtCurrency(portfolio.total_margin), color: colorDeSigno(portfolio.total_margin), icon: '📊' },
            { label: 'Margen medio', value: portfolio.margin_pct == null ? '—' : `${portfolio.margin_pct.toFixed(1)}%`, color: colorDeMargen(portfolio.margin_pct, [10, 20, Infinity]), icon: '📈' },
            { label: 'Proyectos', value: portfolio.project_count, color: 'var(--text-2)', icon: '📁' },
          ].map(({ label, value, color, icon }) => (
            <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '16px 20px', flex: 1, minWidth: 140 }}>
              <div style={{ fontSize: "var(--text-xl)", marginBottom: 6 }}>{icon}</div>
              <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, fontFamily: 'var(--font-mono)', color }}>{value}</div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {isLoading ? <Spinner /> : projects.length === 0 ? (
        <EmptyState icon="💰" title={t('profitability.sin_datos_de_rentabilidad')} description="No hay proyectos con informacion de rentabilidad para este filtro" />
      ) : (
        <>
          {/* Chart */}
          <Card style={{ marginBottom: 24, padding: 20 }}>
            <h3 style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 16, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t('profitability.margen_por_proyecto')}</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={projects.slice().reverse()} margin={{ top: 0, right: 0, left: 0, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="project_code" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} angle={-35} textAnchor="end" />
                <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={v => `${v.toFixed(0)}%`} />
                <Tooltip contentStyle={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-xs)" }} formatter={v => [`${(v as number).toFixed(1)}%`, 'Margen']} />
                <Bar dataKey="margin_pct" radius={[3, 3, 0, 0]}>
                  {projects.slice().reverse().map((p, i) => (
                    <Cell key={i} fill={colorDeMargen(p.margin_pct)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>

          {/* Table */}
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 100px 80px', gap: 16, padding: '10px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              <span>Proyecto</span><span>Ingresos</span><span>Coste</span><span>Margen</span><span>% Margen</span><span>Horas</span><span></span>
            </div>
            {projects.map(p => (
              <div key={p.project_id}
                style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 100px 80px', gap: 16, padding: '14px 20px', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', alignItems: 'center', cursor: 'pointer', transition: 'background 0.15s' }}
                role="button" tabIndex={0}
                onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && p.project_id != null) { e.preventDefault(); setSelectedProject(p.project_id) } }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                onClick={() => p.project_id != null && setSelectedProject(p.project_id)}>
                <div>
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{p.project_name}</div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{p.project_code} · {p.client_name || p.department || '—'}</div>
                </div>
                <span style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{fmtCurrency(p.billing_revenue)}</span>
                <span style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)', color: 'var(--warning)' }}>{fmtCurrency(p.total_cost ?? p.internal_cost)}</span>
                <span style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)', color: colorDeSigno(p.gross_margin), fontWeight: 700 }}>{fmtCurrency(p.gross_margin)}</span>
                <div>
                  <div style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)', color: colorDeMargen(p.margin_pct, [0, 15, Infinity]), fontWeight: 700, marginBottom: 4 }}>{p.margin_pct == null ? '—' : `${p.margin_pct.toFixed(1)}%`}</div>
                  <MarginBar margin_pct={p.margin_pct ?? 0} />
                </div>
                <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{fmtHours(p.total_hours)}</span>
                <button onClick={e => { e.stopPropagation(); if (p.project_id != null) setSelectedProject(p.project_id) }} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>Detalle</button>
              </div>
            ))}
          </div>
        </>
      )}

      {selectedProject && <ProjectDetail projectId={selectedProject} onClose={() => setSelectedProject(null)} />}
    </PageShell>
  )
}