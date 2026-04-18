import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Card, Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { fmtCurrency, fmtHours, fmtDate, extractErr } from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const _BILLING_TYPES = [
  { value: 'time_material', label: 'Tiempo y material' },
  { value: 'fixed_price', label: 'Precio fijo' },
  { value: 'hourly_bag', label: 'Bolsa de horas' },
]

function MarginBar({ margin_pct }) {
  const color = margin_pct < 0 ? 'var(--danger)' : margin_pct < 15 ? 'var(--warning)' : margin_pct < 30 ? 'var(--accent)' : 'var(--success)'
  const w = Math.min(Math.abs(margin_pct), 100)
  return (
    <div style={{ position: 'relative', height: 6, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
      <div style={{ position: 'absolute', left: margin_pct < 0 ? `${50 - w/2}%` : '0', width: `${margin_pct < 0 ? w/2 : Math.min(margin_pct, 100)}%`, height: '100%', background: color, borderRadius: 4 }} />
    </div>
  )
}

function MilestoneRow({ m, projectId, onUpdate }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { mutate: update } = useMutation({
    mutationFn: (data) => api.patch(`/profitability/${projectId}/milestones/${m.id}`, data),
    onSuccess: () => { qc.invalidateQueries(['profitability-detail', projectId]); if (onUpdate) onUpdate() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: () => api.delete(`/profitability/${projectId}/milestones/${m.id}`),
    onSuccess: () => qc.invalidateQueries(['profitability-detail', projectId]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: m.is_completed ? 'var(--success-bg)' : 'var(--surface-2)', border: `1px solid ${m.is_completed ? 'var(--success-border)' : 'var(--surface-4)'}`, borderRadius: 8 }}>
      <input type="checkbox" checked={m.is_completed} onChange={e => update({ is_completed: e.target.checked, completed_date: e.target.checked ? new Date().toISOString().split('T')[0] : null })} style={{ width: 16, height: 16, cursor: 'pointer' }} />
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600, textDecoration: m.is_completed ? 'line-through' : 'none', color: m.is_completed ? 'var(--text-2)' : 'var(--text-1)' }}>{m.name}</div>
        {m.due_date && <div style={{ fontSize: 11, color: new Date(m.due_date) < new Date() && !m.is_completed ? 'var(--danger)' : 'var(--text-2)' }}>📅 {fmtDate(m.due_date)}</div>}
      </div>
      {m.billing_amount && (
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 13, fontWeight: 700, fontFamily: "'Space Mono', monospace", color: 'var(--success)' }}>{fmtCurrency(m.billing_amount)}</div>
          {m.billing_pct && <div style={{ fontSize: 10, color: 'var(--text-2)' }}>{m.billing_pct}% contrato</div>}
        </div>
      )}
      <div style={{ display: 'flex', gap: 6 }}>
        {m.is_completed && !m.is_billed && (
          <button onClick={() => update({ is_billed: true, billed_at: new Date().toISOString().split('T')[0] })} style={{ background: 'var(--success-bg)', border: '1px solid #00e5a030', borderRadius: 6, padding: '3px 8px', color: 'var(--success)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>💶 Facturar</button>
        )}
        {m.is_billed && <span style={{ fontSize: 11, color: 'var(--success)' }}>✓ Facturado</span>}
        <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar este hito de facturación?', onConfirm: () => del(), danger: true }) }} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
      </div>
    </div>
  )
}

function ProjectDetail({ projectId, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showAddMilestone, setShowAddMilestone] = useState(false)
  const [msForm, setMsForm] = useState({ name: '', due_date: '', billing_amount: '', billing_pct: '', sort_order: 0 })
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  const { data, isLoading } = useQuery({
    queryKey: ['profitability-detail', projectId],
    queryFn: () => api.get(`/profitability/${projectId}`).then(r => r.data),
  })

  const { mutate: addMilestone } = useMutation({
    mutationFn: (d) => api.post(`/profitability/${projectId}/milestones`, d),
    onSuccess: () => { qc.invalidateQueries(['profitability-detail', projectId]); setShowAddMilestone(false); setMsForm({ name: '', due_date: '', billing_amount: '', billing_pct: '', sort_order: 0 }) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  if (isLoading) return <Modal open title="Cargando..." onClose={onClose}><Spinner /></Modal>
  if (!data) return null

  const marginColor = data.margin_pct < 0 ? 'var(--danger)' : data.margin_pct < 15 ? 'var(--warning)' : data.margin_pct < 30 ? 'var(--accent)' : 'var(--success)'

  return (
    <Modal open title={`${data.project_code} — ${data.project_name}`} onClose={onClose} width={720}>
      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: 'Ingresos', value: fmtCurrency(data.billing_revenue), color: 'var(--success)' },
          { label: 'Coste interno', value: fmtCurrency(data.internal_cost), color: 'var(--warning)' },
          { label: 'Margen bruto', value: fmtCurrency(data.gross_margin), color: marginColor },
          { label: '% Margen', value: `${data.margin_pct.toFixed(1)}%`, color: marginColor },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ background: 'var(--surface-3)', borderRadius: 10, padding: '14px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
            <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "'Space Mono', monospace", color }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Panel EVM — Earned Value Management */}
      {data.eac !== undefined && (
        <div style={{ background: 'var(--surface-1)', border: '1px solid #1e2d45', borderRadius: 12, padding: '16px 20px', marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            📐 Earned Value Management (EVM)
            <span style={{
              fontSize: 10, padding: '2px 8px', borderRadius: 20, fontWeight: 700,
              background: data.risk_flag === 'critical' ? 'var(--danger-bg)' : data.risk_flag === 'warning' ? 'var(--warning-bg)' : 'var(--success-bg)',
              color:      data.risk_flag === 'critical' ? 'var(--danger)'   : data.risk_flag === 'warning' ? 'var(--warning)'   : 'var(--success)',
            }}>
              {data.risk_flag === 'critical' ? '🔴 Riesgo alto' : data.risk_flag === 'warning' ? '🟡 Atención' : '🟢 OK'}
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 12 }}>
            {[
              { label: 'EAC', value: fmtCurrency(data.eac), desc: 'Coste total estimado', color: data.vac < 0 ? 'var(--danger)' : 'var(--success)' },
              { label: 'ETC', value: fmtCurrency(data.etc), desc: 'Coste restante',        color: 'var(--accent)' },
              { label: 'VAC', value: fmtCurrency(data.vac), desc: 'Desviación al cierre',  color: data.vac < 0 ? 'var(--danger)' : 'var(--success)' },
              { label: 'Margen final est.', value: `${data.margin_at_completion?.toFixed(1) || '—'}%`, desc: 'Al completar proyecto', color: (data.margin_at_completion||0) < 10 ? 'var(--danger)' : 'var(--success)' },
            ].map(k => (
              <div key={k.label} style={{ background: 'var(--surface-2)', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
                <div style={{ fontSize: 10, color: 'var(--text-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k.label}</div>
                <div style={{ fontSize: 16, fontWeight: 800, color: k.color, fontFamily: "'Space Mono', monospace" }}>{k.value}</div>
                <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>{k.desc}</div>
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
                <div style={{ fontSize: 10, color: 'var(--text-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k.label}</div>
                <div style={{ fontSize: 16, fontWeight: 800, color: k.ok ? 'var(--success)' : 'var(--danger)', fontFamily: "'Space Mono', monospace" }}>{k.value}</div>
                <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>{k.desc}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, fontSize: 11, color: 'var(--text-2)', borderTop: '1px solid #1e2d45', paddingTop: 10 }}>
            CPI &gt; 1 = bajo coste · SPI &gt; 1 = adelantado · EAC = coste total estimado al finalizar · VAC = presupuesto disponible restante
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        {/* Hours */}
        <Card style={{ padding: 16 }}>
          <h4 style={{ fontSize: 13, fontWeight: 700, marginBottom: 14, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Horas</h4>
          {[
            { label: 'Totales', value: fmtHours(data.total_hours) },
            { label: 'Facturables', value: fmtHours(data.billable_hours) },
            { label: 'Presupuestadas', value: data.budget_hours ? fmtHours(data.budget_hours) : '—' },
            { label: 'Tarifa media coste', value: `${data.avg_cost_rate}€/h` },
            { label: 'Tarifa cliente', value: data.billing_rate ? `${data.billing_rate}€/h` : '—' },
          ].map(({ label, value }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #1e2d4530', fontSize: 13 }}>
              <span style={{ color: 'var(--text-2)' }}>{label}</span>
              <span style={{ fontWeight: 600 }}>{value}</span>
            </div>
          ))}
        </Card>

        {/* By person */}
        <Card style={{ padding: 16 }}>
          <h4 style={{ fontSize: 13, fontWeight: 700, marginBottom: 14, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Por persona</h4>
          {data.by_person?.length === 0 ? <EmptyState icon="👤" title="Sin imputaciones" /> : (
            data.by_person?.slice(0, 6).map(p => (
              <div key={p.user_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid #1e2d4530', fontSize: 12 }}>
                <span>{p.user_name}</span>
                <div style={{ display: 'flex', gap: 12 }}>
                  <span style={{ color: 'var(--text-2)' }}>{fmtHours(p.hours)}</span>
                  <span style={{ fontFamily: "'Space Mono', monospace", color: 'var(--warning)' }}>{fmtCurrency(p.cost)}</span>
                </div>
              </div>
            ))
          )}
        </Card>
      </div>

      {/* Weekly evolution */}
      {data.by_week?.length > 0 && (
        <Card style={{ padding: 16, marginBottom: 20 }}>
          <h4 style={{ fontSize: 13, fontWeight: 700, marginBottom: 14, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Evolución semanal</h4>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={data.by_week} margin={{ top: 0, right: 0, left: -20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
              <XAxis dataKey="week" tick={{ fontSize: 10, fill: 'var(--text-2)' }} tickFormatter={w => w.slice(5)} angle={-30} textAnchor="end" />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text-2)' }} />
              <Tooltip contentStyle={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, fontSize: 11 }} formatter={v => [`${v.toFixed(1)}h`, 'Horas']} />
              <Bar dataKey="hours" fill="#00d4ff" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Milestones */}
      <Card style={{ padding: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <h4 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Hitos de facturación</h4>
          <Button size="sm" onClick={() => setShowAddMilestone(true)} icon="＋">Añadir hito</Button>
        </div>
        {data.milestones?.length === 0 ? (
          <EmptyState icon="🏁" title="Sin hitos definidos" description="Añade hitos para controlar la facturación por entregables" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {data.milestones.map(m => (
              <MilestoneRow key={m.id} m={m} projectId={projectId} />
            ))}
            <div style={{ borderTop: '1px solid #1e2d45', paddingTop: 10, display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
              <span style={{ color: 'var(--text-2)' }}>Total facturado:</span>
              <span style={{ fontWeight: 700, fontFamily: "'Space Mono', monospace", color: 'var(--success)' }}>
                {fmtCurrency(data.milestones.filter(m => m.is_billed).reduce((s, m) => s + (m.billing_amount || 0), 0))}
              </span>
            </div>
          </div>
        )}

        {showAddMilestone && (
          <div style={{ marginTop: 14, padding: 14, background: 'var(--accent-muted)', border: '1px dashed #00d4ff30', borderRadius: 10 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 10, marginBottom: 10 }}>
              <div><label style={ls}>Nombre</label><input value={msForm.name} onChange={e => setMsForm(f => ({ ...f, name: e.target.value }))} style={fs} placeholder="Entrega fase 1" /></div>
              <div><label style={ls}>Fecha</label><input type="date" value={msForm.due_date} onChange={e => setMsForm(f => ({ ...f, due_date: e.target.value }))} style={fs} /></div>
              <div><label style={ls}>Importe €</label><input type="number" value={msForm.billing_amount} onChange={e => setMsForm(f => ({ ...f, billing_amount: e.target.value }))} style={fs} placeholder="0" /></div>
              <div><label style={ls}>% Contrato</label><input type="number" value={msForm.billing_pct} onChange={e => setMsForm(f => ({ ...f, billing_pct: e.target.value }))} style={fs} placeholder="0" /></div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button size="sm" onClick={() => addMilestone(msForm)} disabled={!msForm.name}>Añadir</Button>
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
  const { _hasRole } = useAuth()
  const [selectedProject, setSelectedProject] = useState(null)
  const [statusFilter, setStatusFilter] = useState('active')

  const { data, isLoading } = useQuery({
    queryKey: ['profitability-summary', statusFilter],
    queryFn: () => api.get(`/profitability/summary?status=${statusFilter}`).then(r => r.data),
  })

  const projects = data?.projects || []
  const portfolio = data?.portfolio || {}

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        title={t('profitability.title')}
        subtitle={t('profitability.subtitle')}
        actions={
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
            <option value="active">Proyectos activos</option>
            <option value="closed">Cerrados</option>
          </select>
        }
      />

      {/* Portfolio KPIs */}
      {portfolio.project_count > 0 && (
        <div style={{ display: 'flex', gap: 14, marginBottom: 28, flexWrap: 'wrap' }}>
          {[
            { label: 'Ingresos cartera', value: fmtCurrency(portfolio.total_revenue), color: 'var(--success)', icon: '💰' },
            { label: 'Coste total', value: fmtCurrency(portfolio.total_cost), color: 'var(--warning)', icon: '💸' },
            { label: 'Margen total', value: fmtCurrency(portfolio.total_margin), color: portfolio.total_margin >= 0 ? 'var(--accent)' : 'var(--danger)', icon: '📊' },
            { label: 'Margen medio', value: `${portfolio.margin_pct?.toFixed(1)}%`, color: portfolio.margin_pct >= 20 ? 'var(--success)' : portfolio.margin_pct >= 10 ? 'var(--warning)' : 'var(--danger)', icon: '📈' },
            { label: 'Proyectos', value: portfolio.project_count, color: 'var(--text-2)', icon: '📁' },
          ].map(({ label, value, color, icon }) => (
            <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, padding: '16px 20px', flex: 1, minWidth: 140 }}>
              <div style={{ fontSize: 20, marginBottom: 6 }}>{icon}</div>
              <div style={{ fontSize: 22, fontWeight: 800, fontFamily: "'Space Mono', monospace", color }}>{value}</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {isLoading ? <Spinner /> : projects.length === 0 ? (
        <EmptyState icon="💰" title="Sin datos de rentabilidad" description="Configura tarifas en los proyectos y usuarios para ver la rentabilidad" />
      ) : (
        <>
          {/* Chart */}
          <Card style={{ marginBottom: 24, padding: 20 }}>
            <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 16, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Margen por proyecto</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={projects.slice().reverse()} margin={{ top: 0, right: 0, left: 0, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
                <XAxis dataKey="project_code" tick={{ fontSize: 11, fill: 'var(--text-2)' }} angle={-35} textAnchor="end" />
                <YAxis tick={{ fontSize: 11, fill: 'var(--text-2)' }} tickFormatter={v => `${v.toFixed(0)}%`} />
                <Tooltip contentStyle={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, fontSize: 11 }} formatter={v => [`${v.toFixed(1)}%`, 'Margen']} />
                <Bar dataKey="margin_pct" radius={[3, 3, 0, 0]}>
                  {projects.slice().reverse().map((p, i) => (
                    <Cell key={i} fill={p.margin_pct < 0 ? 'var(--danger)' : p.margin_pct < 15 ? 'var(--warning)' : p.margin_pct < 30 ? 'var(--accent)' : 'var(--success)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>

          {/* Table */}
          <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 100px 80px', gap: 16, padding: '10px 20px', borderBottom: '1px solid #1e2d45', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              <span>Proyecto</span><span>Ingresos</span><span>Coste</span><span>Margen</span><span>% Margen</span><span>Horas</span><span></span>
            </div>
            {projects.map(p => (
              <div key={p.project_id}
                style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 100px 80px', gap: 16, padding: '14px 20px', borderBottom: '1px solid #1e2d4530', alignItems: 'center', cursor: 'pointer', transition: 'background 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                onClick={() => setSelectedProject(p.project_id)}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{p.project_name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{p.project_code} · {p.client_name || p.department || '—'}</div>
                </div>
                <span style={{ fontSize: 13, fontFamily: "'Space Mono', monospace", color: 'var(--success)' }}>{fmtCurrency(p.billing_revenue)}</span>
                <span style={{ fontSize: 13, fontFamily: "'Space Mono', monospace", color: 'var(--warning)' }}>{fmtCurrency(p.internal_cost)}</span>
                <span style={{ fontSize: 13, fontFamily: "'Space Mono', monospace", color: p.gross_margin >= 0 ? 'var(--accent)' : 'var(--danger)', fontWeight: 700 }}>{fmtCurrency(p.gross_margin)}</span>
                <div>
                  <div style={{ fontSize: 13, fontFamily: "'Space Mono', monospace", color: p.margin_pct < 0 ? 'var(--danger)' : p.margin_pct < 15 ? 'var(--warning)' : 'var(--success)', fontWeight: 700, marginBottom: 4 }}>{p.margin_pct.toFixed(1)}%</div>
                  <MarginBar margin_pct={p.margin_pct} />
                </div>
                <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{fmtHours(p.total_hours)}</span>
                <button onClick={e => { e.stopPropagation(); setSelectedProject(p.project_id) }} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>Detalle</button>
              </div>
            ))}
          </div>
        </>
      )}

      {selectedProject && <ProjectDetail projectId={selectedProject} onClose={() => setSelectedProject(null)} />}
    </div>
  )
}