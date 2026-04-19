import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi, usersApi } from '../services/api'
import { Card, Button, Modal, Spinner, EmptyState, useSort, ViewToggle } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { AlertTriangle } from 'lucide-react'
import { fmtCurrency, extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const PROB_OPTIONS = [
  { value: 'very_low', label: 'Muy baja (<10%)' },
  { value: 'low', label: 'Baja (10-30%)' },
  { value: 'medium', label: 'Media (30-60%)' },
  { value: 'high', label: 'Alta (60-80%)' },
  { value: 'very_high', label: 'Muy alta (>80%)' },
]
const IMPACT_OPTIONS = [
  { value: 'negligible', label: 'Insignificante' },
  { value: 'minor', label: 'Menor' },
  { value: 'moderate', label: 'Moderado' },
  { value: 'major', label: 'Mayor' },
  { value: 'critical', label: 'Crítico' },
]
const STATUS_OPTIONS = [
  { value: 'identified', label: 'Identificado' },
  { value: 'analyzing', label: 'Analizando' },
  { value: 'mitigating', label: 'Mitigando' },
  { value: 'monitoring', label: 'Monitorizando' },
  { value: 'closed', label: 'Cerrado' },
  { value: 'materialized', label: 'Materializado' },
]
const CATEGORIES = [
  { value: 'technical', label: 'Técnico' },
  { value: 'financial', label: 'Financiero' },
  { value: 'schedule', label: 'Planificación' },
  { value: 'resource', label: 'Recursos' },
  { value: 'external', label: 'Externo' },
  { value: 'quality', label: 'Calidad' },
]
const RESPONSE_TYPES = [
  { value: 'avoid', label: 'Evitar' },
  { value: 'mitigate', label: 'Mitigar' },
  { value: 'transfer', label: 'Transferir' },
  { value: 'accept', label: 'Aceptar' },
]
const LEVEL_CFG = {
  critical: { color: 'var(--danger)', bg: 'var(--danger-bg)', label: 'Crítico' },
  high:     { color: 'var(--warning)', bg: 'var(--warning-bg)', label: 'Alto' },
  medium:   { color: 'var(--accent)', bg: 'var(--accent-muted)', label: 'Medio' },
  low:      { color: 'var(--success)', bg: 'var(--success-bg)', label: 'Bajo' },
}

function RiskMatrix({ risks }) {
  const probs = ['very_low', 'low', 'medium', 'high', 'very_high']
  const impacts = ['negligible', 'minor', 'moderate', 'major', 'critical']
  const probLabels = { very_low: 'MBaja', low: 'Baja', medium: 'Media', high: 'Alta', very_high: 'MAlta' }
  const impactLabels = { negligible: 'Insig.', minor: 'Menor', moderate: 'Mod.', major: 'Mayor', critical: 'Crítico' }

  const getColor = (p, i) => {
    const ps = probs.indexOf(p)
    const is = impacts.indexOf(i)
    const score = (ps + 1) * (is + 1)
    if (score >= 15) return 'var(--danger)'
    if (score >= 8) return 'var(--warning)'
    if (score >= 4) return 'var(--accent)'
    return 'var(--success)'
  }

  const cellRisks = (p, i) => risks.filter(r => r.probability === p && r.impact === i)

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'separate', borderSpacing: 4 }}>
        <thead>
          <tr>
            <th style={{ padding: '6px 10px', fontSize: 11, color: 'var(--text-2)', textAlign: 'right' }}>Prob →<br />Impacto ↓</th>
            {probs.map(p => <th key={p} style={{ padding: '6px 10px', fontSize: 11, color: 'var(--text-2)', textAlign: 'center', width: 90 }}>{probLabels[p]}</th>)}
          </tr>
        </thead>
        <tbody>
          {[...impacts].reverse().map(imp => (
            <tr key={imp}>
              <td style={{ padding: '4px 10px', fontSize: 11, color: 'var(--text-2)', textAlign: 'right', whiteSpace: 'nowrap' }}>{impactLabels[imp]}</td>
              {probs.map(prob => {
                const color = getColor(prob, imp)
                const cr = cellRisks(prob, imp)
                return (
                  <td key={prob} style={{ padding: 4 }}>
                    <div style={{ width: 82, height: 52, borderRadius: 6, background: color + '20', border: `1px solid ${color}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
                      {cr.length > 0 && (
                        <>
                          <div style={{ fontSize: 16, fontWeight: 800, color, fontFamily: "'Space Mono', monospace" }}>{cr.length}</div>
                          <div style={{ fontSize: 9, color: color, maxWidth: 70, textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {cr[0].code}
                            {cr.length > 1 ? ` +${cr.length - 1}` : ''}
                          </div>
                        </>
                      )}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RiskFormModal({ risk, projectId, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { _invalidate } = useInvalidate()
  const isEdit = !!risk?.id
  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const [form, setForm] = useState({
    title: risk?.title || '',
    description: risk?.description || '',
    category: risk?.category || 'technical',
    probability: risk?.probability || 'medium',
    impact: risk?.impact || 'moderate',
    status: risk?.status || 'identified',
    mitigation_plan: risk?.mitigation_plan || '',
    contingency_plan: risk?.contingency_plan || '',
    response_type: risk?.response_type || 'mitigate',
    owner_id: risk?.owner_id || '',
    review_date: risk?.review_date || '',
    cost_impact_min: risk?.cost_impact_min || '',
    cost_impact_max: risk?.cost_impact_max || '',
    schedule_impact_days: risk?.schedule_impact_days || '',
    notes: risk?.notes || '',
  })
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  const { mutate, isPending } = useMutation({
    mutationFn: (data) => isEdit
      ? api.patch(`/risks/${projectId}/${risk.id}`, data)
      : api.post(`/risks/${projectId}`, data),
    onSuccess: () => { qc.invalidateQueries(['risks', projectId]); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open title={isEdit ? `Editar riesgo` : 'Nuevo Riesgo'} onClose={onClose} width={660}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Título *</label>
          <input value={form.title} onChange={set('title')} style={fs} placeholder={t(modulo.clave)} />
        </div>
        <div>
          <label style={ls}>Categoría</label>
          <select value={form.category} onChange={set('category')} style={fs}>
            {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Estado</label>
          <select value={form.status} onChange={set('status')} style={fs}>
            {STATUS_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Probabilidad *</label>
          <select value={form.probability} onChange={set('probability')} style={fs}>
            {PROB_OPTIONS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Impacto *</label>
          <select value={form.impact} onChange={set('impact')} style={fs}>
            {IMPACT_OPTIONS.map(i => <option key={i.value} value={i.value}>{i.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Tipo de respuesta</label>
          <select value={form.response_type} onChange={set('response_type')} style={fs}>
            {RESPONSE_TYPES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Responsable</label>
          <select value={form.owner_id} onChange={set('owner_id')} style={fs}>
            <option value="">Sin asignar</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Coste mínimo €</label>
          <input type="number" value={form.cost_impact_min} onChange={set('cost_impact_min')} style={fs} placeholder={t(modulo.clave)} />
        </div>
        <div>
          <label style={ls}>Coste máximo €</label>
          <input type="number" value={form.cost_impact_max} onChange={set('cost_impact_max')} style={fs} placeholder={t(modulo.clave)} />
        </div>
        <div>
          <label style={ls}>Impacto en días</label>
          <input type="number" value={form.schedule_impact_days} onChange={set('schedule_impact_days')} style={fs} placeholder={t(modulo.clave)} />
        </div>
        <div>
          <label style={ls}>Fecha revisión</label>
          <input type="date" value={form.review_date} onChange={set('review_date')} style={fs} />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Descripción</label>
          <textarea value={form.description} onChange={set('description')} rows={2} style={{ ...fs, resize: 'vertical' }} />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Plan de mitigación</label>
          <textarea value={form.mitigation_plan} onChange={set('mitigation_plan')} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder={t(modulo.clave)} />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Plan de contingencia</label>
          <textarea value={form.contingency_plan} onChange={set('contingency_plan')} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder={t(modulo.clave)} />
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar' : 'Crear riesgo'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function RisksPage() {
  const t = useAppT()
  const toast = useToast()
  const [selectedProject, setSelectedProject] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(null)
  const [tab, setTab] = useState('register')
  const [riskLevelFilter, setRiskLevelFilter] = useState('')
  const [riskSortBy, setRiskSortBy] = useState('risk_level')
  const [view, setView] = useState('list')
  const qc = useQueryClient()

  const { data: projects = [] } = useQuery({ queryKey: ['projects', { status: 'active' }], queryFn: () => projectsApi.list({ status: 'active' }).then(r => r.data) })

  const { data: risksData, isLoading } = useQuery({
    queryKey: ['risks', selectedProject],
    queryFn: () => selectedProject
      ? api.get(`/risks/${selectedProject}`).then(r => r.data)
      : api.get('/risks/all/portfolio').then(r => ({ risks: r.data, summary: { total: r.data.length } })),
  })

  const { mutate: deleteRisk } = useMutation({
    mutationFn: ({ projectId, riskId }) => api.delete(`/risks/${projectId}/${riskId}`),
    onSuccess: () => qc.invalidateQueries(['risks', selectedProject]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const risks = risksData?.risks || []
  const summary = risksData?.summary || {}
  const filteredRisks = riskLevelFilter ? risks.filter(r => r.risk_level === riskLevelFilter) : risks
  const { sortedData: sortedRisks } = useSort(filteredRisks, riskSortBy)

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<AlertTriangle size={18} />}
        title={t('risks.title')}
        subtitle={t('risks.subtitle')}
        actions={
          <div style={{ display: 'flex', gap: 10 }}>
            <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
              style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer', minWidth: 200 }}>
              <option value="">Todos los proyectos</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
            {selectedProject && <Button onClick={() => setShowCreate(true)} icon="＋">Nuevo riesgo</Button>}
          </div>
        }
      />

      {/* Summary */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 24, flexWrap: 'wrap' }}>
        {[
          { label: 'Total riesgos', value: summary.total || risks.length, color: 'var(--text-2)' },
          { label: 'Abiertos', value: summary.open || risks.filter(r => !['closed','materialized'].includes(r.status)).length, color: 'var(--warning)' },
          { label: 'Críticos', value: summary.critical_count || risks.filter(r => r.risk_level === 'critical').length, color: 'var(--danger)' },
          { label: 'Altos', value: summary.high_count || risks.filter(r => r.risk_level === 'high').length, color: 'var(--warning)' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, padding: '14px 18px', flex: 1 }}>
            <div style={{ fontSize: 24, fontWeight: 800, fontFamily: "'Space Mono', monospace", color }}>{value}</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 24 }}>
        {[['register', '📋 Registro'], ['matrix', '🎯 Matriz']].map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            style={{ padding: '8px 18px', borderRadius: 8, border: `1px solid ${tab === t ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: tab === t ? 'var(--accent-muted)' : 'transparent', color: tab === t ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {isLoading ? <Spinner /> : risks.length === 0 ? (
        <EmptyState icon="🛡️" title={t(modulo.clave)} description={selectedProject ? "Este proyecto no tiene riesgos identificados" : "Selecciona un proyecto o no hay riesgos en la cartera"} />
      ) : tab === 'matrix' ? (
        <Card style={{ padding: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 16, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Matriz de probabilidad × impacto</h3>
          <RiskMatrix risks={risks} />
        </Card>
      ) : (
        <div>
          <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            <select value={riskLevelFilter} onChange={e => setRiskLevelFilter(e.target.value)}
              style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 14px', color: riskLevelFilter ? 'var(--danger)' : 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="">Todos los niveles</option>
              <option value="critical">🚨 Crítico</option>
              <option value="high">🔴 Alto</option>
              <option value="medium">🟡 Medio</option>
              <option value="low">🟢 Bajo</option>
            </select>
            <select value={riskSortBy} onChange={e => setRiskSortBy(e.target.value)}
              style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="risk_level">Ordenar por nivel</option>
              <option value="title">Ordenar por título</option>
              <option value="status">Ordenar por estado</option>
              <option value="project_name">Ordenar por proyecto</option>
            </select>
            <div style={{ marginLeft: 'auto' }}>
              <ViewToggle view={view} onChange={setView} />
            </div>
          </div>
          {view === 'list' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {sortedRisks.map(r => {
            const lvl = LEVEL_CFG[r.risk_level] || LEVEL_CFG.low
            return (
              <div key={r.id} style={{ padding: '16px 20px', background: 'var(--surface-2)', border: `1px solid ${lvl.color}30`, borderRadius: 12 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: lvl.color, marginTop: 4, flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                      <div>
                        <span style={{ fontSize: 14, fontWeight: 700 }}>{r.title}</span>
                        <span style={{ fontSize: 11, color: 'var(--text-2)', marginLeft: 8, fontFamily: "'Space Mono', monospace" }}>{r.code}</span>
                        {r.project_name && <span style={{ fontSize: 11, color: 'var(--text-2)', marginLeft: 8 }}>· {r.project_name}</span>}
                      </div>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: lvl.bg, color: lvl.color, border: `1px solid ${lvl.color}40` }}>{lvl.label}</span>
                        <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{r.status_label}</span>
                        <button onClick={() => setEditing(r)} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏️</button>
                        <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar este riesgo?', onConfirm: () => deleteRisk({ projectId: r.project_id, riskId: r.id, danger: true }) }) }} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-2)', marginBottom: r.mitigation_plan ? 8 : 0 }}>
                      <span>Prob: <span style={{ color: 'var(--text-1)' }}>{r.probability_label}</span></span>
                      <span>Impacto: <span style={{ color: 'var(--text-1)' }}>{r.impact_label}</span></span>
                      {r.category_label && <span>Tipo: <span style={{ color: 'var(--text-1)' }}>{r.category_label}</span></span>}
                      {r.owner_name && <span>Responsable: <span style={{ color: 'var(--text-1)' }}>{r.owner_name}</span></span>}
                      {r.cost_impact_max && <span>Impacto €: <span style={{ color: 'var(--warning)' }}>hasta {fmtCurrency(r.cost_impact_max)}</span></span>}
                      {r.schedule_impact_days && <span>Plazo: <span style={{ color: 'var(--warning)' }}>+{r.schedule_impact_days}d</span></span>}
                    </div>
                    {r.mitigation_plan && (
                      <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-2)', background: 'var(--surface-3)', borderRadius: 6, padding: '6px 10px' }}>
                        🛡️ <span style={{ color: 'var(--text-1)' }}>{r.mitigation_plan}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
          </div>
          ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
            {sortedRisks.map(r => {
              const lvl = LEVEL_CFG[r.risk_level] || LEVEL_CFG.low
              return (
                <div key={r.id} style={{ padding: '14px 16px', background: 'var(--surface-2)', border: `1px solid ${lvl.color}30`, borderRadius: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ width: 10, height: 10, borderRadius: '50%', background: lvl.color, flexShrink: 0 }} />
                      <span style={{ fontSize: 12, fontWeight: 700, padding: '2px 7px', borderRadius: 20, background: lvl.bg, color: lvl.color }}>{lvl.label}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 4 }}>
                      <button onClick={() => setEditing(r)} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 5, padding: '2px 7px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏️</button>
                      <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar este riesgo?', onConfirm: () => deleteRisk({ projectId: r.project_id, riskId: r.id, danger: true }) }) }} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 5, padding: '2px 7px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                    </div>
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{r.title}</div>
                  {r.project_name && <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 6 }}>📁 {r.project_name}</div>}
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                    <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 4, background: 'var(--surface-3)', color: 'var(--text-2)' }}>P: {r.probability_label}</span>
                    <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 4, background: 'var(--surface-3)', color: 'var(--text-2)' }}>I: {r.impact_label}</span>
                    {r.owner_name && <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 4, background: 'var(--surface-3)', color: 'var(--text-2)' }}>👤 {r.owner_name}</span>}
                  </div>
                  {r.mitigation_plan && (
                    <div style={{ fontSize: 11, color: 'var(--text-2)', lineHeight: 1.4, borderTop: '1px solid #1e2d45', paddingTop: 6, marginTop: 4 }}>
                      🛡️ {r.mitigation_plan.length > 80 ? r.mitigation_plan.slice(0, 80) + '…' : r.mitigation_plan}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          )}
        </div>
      )}

      {showCreate && <RiskFormModal projectId={selectedProject} onClose={() => setShowCreate(false)} />}
      {editing && <RiskFormModal risk={editing} projectId={editing.project_id} onClose={() => setEditing(null)} />}
    </div>
  )
}