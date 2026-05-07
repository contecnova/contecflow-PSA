import { useId, useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { projectsApi, projectChangesApi, cabApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ArrowLeftRight } from 'lucide-react'
import { fmtCurrency, extractErr } from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const IMPACT_CFG = {
  low:      { label: 'Bajo',    color: 'var(--success)' },
  medium:   { label: 'Medio',   color: 'var(--accent)' },
  high:     { label: 'Alto',    color: 'var(--warning)' },
  critical: { label: 'Crítico', color: 'var(--danger)' },
}
const STATUS_CFG = {
  draft:        { label: 'Borrador',     color: 'var(--text-2)' },
  submitted:    { label: 'Enviado',      color: 'var(--accent)' },
  under_review: { label: 'En revisión',  color: 'var(--warning)' },
  approved:     { label: 'Aprobado',     color: 'var(--success)' },
  rejected:     { label: 'Rechazado',    color: 'var(--danger)' },
  implemented:  { label: 'Implementado', color: 'var(--purple)' },
}

const crSchema = z.object({
  title: z.string().trim().min(1, 'El titulo es obligatorio'),
  description: z.string().trim().min(1, 'La descripcion es obligatoria'),
  justification: z.string().optional(),
  impact: z.enum(['low', 'medium', 'high', 'critical']),
  cost_impact: z.preprocess(
    (v) => (v === '' || v === null || typeof v === 'undefined' ? undefined : v),
    z.coerce.number().min(0, 'El impacto en coste no puede ser negativo').optional(),
  ),
  schedule_impact_days: z.preprocess(
    (v) => (v === '' || v === null || typeof v === 'undefined' ? undefined : v),
    z.coerce.number().int('Debe ser un numero entero').min(0, 'No puede ser negativo').optional(),
  ),
  scope_impact: z.string().optional(),
})

const reviewSchema = z.object({
  approved: z.boolean(),
  resolution_notes: z.string().trim().optional(),
}).superRefine((values, ctx) => {
  if (!values.approved && !values.resolution_notes) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['resolution_notes'],
      message: 'Las notas de resolucion son obligatorias al rechazar',
    })
  }
})

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.draft
  return <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: cfg.color + '20', color: cfg.color, border: `1px solid ${cfg.color}40`, textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{cfg.label}</span>
}

function CRFormModal({ cr, projectId, onClose }) {
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!cr?.id
  const [form, setForm] = useState({
    title: cr?.title || '',
    description: cr?.description || '',
    justification: cr?.justification || '',
    impact: cr?.impact || 'medium',
    cost_impact: cr?.cost_impact || '',
    schedule_impact_days: cr?.schedule_impact_days || '',
    scope_impact: cr?.scope_impact || '',
  })
  const validation = useFormValidation(crSchema)
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = (k) => (e) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const { mutate, isPending } = useMutation({
    mutationFn: (data) => isEdit
      ? projectChangesApi.update(projectId, cr.id, data)
      : projectChangesApi.create(projectId, data),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries(['changes', projectId]); qc.invalidateQueries(['all-pending-crs']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data)
  }

  return (
    <Modal open title={isEdit ? `Editar CR — ${cr.code}` : 'Nueva Solicitud de Cambio'} onClose={onClose} width={620}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label htmlFor={`${idPrefix}-title`} style={ls}>Título *</label>
          <input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} style={validation.inputStyle(fs, 'title')} placeholder="Titulo de la solicitud" aria-label="Titulo de la solicitud" />
          {validation.errors.title && <p style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--danger)' }}>{validation.errors.title}</p>}
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label htmlFor={`${idPrefix}-description`} style={ls}>Descripción *</label>
          <textarea id={`${idPrefix}-description`} value={form.description} onChange={set('description')} rows={3} style={validation.inputStyle({ ...fs, resize: 'vertical' }, 'description')} placeholder="Describe el cambio solicitado" aria-label="Descripcion del cambio" />
          {validation.errors.description && <p style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--danger)' }}>{validation.errors.description}</p>}
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label htmlFor={`${idPrefix}-justification`} style={ls}>Justificación</label>
          <textarea id={`${idPrefix}-justification`} value={form.justification} onChange={set('justification')} rows={2} style={validation.inputStyle({ ...fs, resize: 'vertical' }, 'justification')} placeholder="Justificacion del cambio" aria-label="Justificacion del cambio" />
          {validation.errors.justification && <p style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--danger)' }}>{validation.errors.justification}</p>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-impact`} style={ls}>Impacto</label>
          <select id={`${idPrefix}-impact`} value={form.impact} onChange={set('impact')} style={validation.inputStyle(fs, 'impact')}>
            {Object.entries(IMPACT_CFG).map(([v, c]) => <option key={v} value={v}>{c.label}</option>)}
          </select>
          {validation.errors.impact && <p style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--danger)' }}>{validation.errors.impact}</p>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-cost-impact`} style={ls}>Impacto en coste (€)</label>
          <input id={`${idPrefix}-cost-impact`} type="number" value={form.cost_impact} onChange={set('cost_impact')} style={validation.inputStyle(fs, 'cost_impact')} placeholder="Impacto economico" aria-label="Impacto economico" />
          {validation.errors.cost_impact && <p style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--danger)' }}>{validation.errors.cost_impact}</p>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-schedule-impact`} style={ls}>Impacto en plazo (días)</label>
          <input id={`${idPrefix}-schedule-impact`} type="number" value={form.schedule_impact_days} onChange={set('schedule_impact_days')} style={validation.inputStyle(fs, 'schedule_impact_days')} placeholder="Dias adicionales" aria-label="Dias adicionales" />
          {validation.errors.schedule_impact_days && <p style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--danger)' }}>{validation.errors.schedule_impact_days}</p>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-scope-impact`} style={ls}>Impacto en alcance</label>
          <input id={`${idPrefix}-scope-impact`} value={form.scope_impact} onChange={set('scope_impact')} style={validation.inputStyle(fs, 'scope_impact')} placeholder="Impacto en el alcance" aria-label="Impacto en el alcance" />
          {validation.errors.scope_impact && <p style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--danger)' }}>{validation.errors.scope_impact}</p>}
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={submit} disabled={isPending} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar' : 'Crear CR'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ReviewCRModal({ cr, projectId, onClose }) {
  const idPrefix = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const [notes, setNotes] = useState('')
  const validation = useFormValidation(reviewSchema)
  const { mutate, isPending } = useMutation({
    mutationFn: ({ approved, resolution_notes }) => projectChangesApi.review(projectId, cr.id, { approved, resolution_notes }),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries(['changes', projectId]); qc.invalidateQueries(['all-pending-crs']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const impact = IMPACT_CFG[cr.impact] || IMPACT_CFG.medium

  const submitReview = (approved) => {
    const result = validation.validateForm({ approved, resolution_notes: notes })
    if (!result.success) return
    mutate(result.data)
  }

  return (
    <Modal open title={`Revisar CR — ${cr.code}`} onClose={onClose} width={520}>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: "var(--text-lg)", fontWeight: 700, marginBottom: 8 }}>{cr.title}</div>
        <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 12 }}>{cr.description}</p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 12 }}>
          {[
            { label: 'Impacto', value: <span style={{ color: impact.color, fontWeight: 700 }}>{impact.label}</span> },
            { label: 'Coste adicional', value: cr.cost_impact ? fmtCurrency(cr.cost_impact) : '—' },
            { label: 'Días adicionales', value: cr.schedule_impact_days ? `+${cr.schedule_impact_days}d` : '—' },
          ].map(({ label, value }) => (
            <div key={label} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 3 }}>{label}</div>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{value}</div>
            </div>
          ))}
        </div>
        {cr.scope_impact && <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', background: 'var(--surface-3)', borderRadius: 8, padding: '8px 12px' }}>📋 {cr.scope_impact}</p>}
      </div>
      <div style={{ marginBottom: 16 }}>
        <label htmlFor={`${idPrefix}-resolution-notes`} style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }}>Notas de resolución</label>
        <textarea id={`${idPrefix}-resolution-notes`} value={notes} onChange={e => { setNotes(e.target.value); validation.clearFieldError('resolution_notes') }} rows={2}
          style={validation.inputStyle({ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box' }, 'resolution_notes')} />
        {validation.errors.resolution_notes && <p style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--danger)' }}>{validation.errors.resolution_notes}</p>}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button variant="danger" onClick={() => submitReview(false)} disabled={isPending} loading={isPending}>✕ Rechazar</Button>
        <Button onClick={() => submitReview(true)} disabled={isPending} loading={isPending}>✓ Aprobar</Button>
      </div>
    </Modal>
  )
}

// ── CAB Board Tab ─────────────────────────────────────────────────────────────
function CABBoard() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: pendingCRs = [], isLoading } = useQuery({
    queryKey: ['cab-pending'],
    queryFn: () => cabApi.changes().then(r => r.data),
  })
  const { data: windows = [] } = useQuery({
    queryKey: ['maintenance-windows'],
    queryFn: () => cabApi.windows().then(r => r.data),
  })
  const { mutate: vote, isPending: _saving } = useMutation({
    mutationFn: ({ id, vote, comment }) => cabApi.vote(id, { vote, comment }),
    onSuccess: () => { qc.invalidateQueries(['cab-pending']); qc.invalidateQueries(['changes']); qc.invalidateQueries(['all-pending-crs']); },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: close } = useMutation({
    mutationFn: ({ id, decision }) => cabApi.close(id, { decision }),
    onSuccess: () => { qc.invalidateQueries(['cab-pending']); qc.invalidateQueries(['changes']); qc.invalidateQueries(['all-pending-crs']); },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const IMPACT_CFG = {
    low:{ label:'Bajo', color:'var(--success)' },
    medium:{ label:'Medio', color:'var(--accent)' },
    high:{ label:'Alto', color:'var(--warning)' },
    critical:{ label:'Crítico', color:'var(--danger)' },
  }
  const card = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }

  return (
    <div>
      <div style={{ display:'grid', gridTemplateColumns:'2fr 1fr', gap:20 }}>
        <div>
          <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:14 }}>CRs pendientes de votación CAB ({pendingCRs.length})</div>
          {isLoading ? <div style={{ color:'var(--text-2)', fontSize: "var(--text-base)" }}>Cargando...</div> :
            pendingCRs.length === 0 ? (
              <div style={{ ...card, padding:32, textAlign:'center', color:'var(--text-3)', fontSize: "var(--text-base)" }}>Sin CRs pendientes de votación</div>
            ) : pendingCRs.map(cr => {
              const ic = IMPACT_CFG[cr.impact] || IMPACT_CFG.medium
              return (
                <div key={cr.id} style={{ ...card, padding:'16px 20px', marginBottom:12 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:10 }}>
                    <div>
                      <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:2 }}>{cr.project_code} · {cr.code}</div>
                      <div style={{ fontSize: "var(--text-md)", fontWeight:500, marginBottom:6 }}>{cr.title}</div>
                      <div style={{ display:'flex', gap:12, fontSize: "var(--text-sm)" }}>
                        <span style={{ color:ic.color, fontWeight:500 }}>{ic.label} impacto</span>
                        {cr.cost_impact && <span style={{ color:'var(--danger)' }}>+{cr.cost_impact}€</span>}
                        {cr.schedule_impact_days && <span style={{ color:'var(--warning)' }}>+{cr.schedule_impact_days}d</span>}
                      </div>
                    </div>
                    <div style={{ textAlign:'right', fontSize: "var(--text-sm)", color:'var(--text-2)' }}>
                      <div style={{ marginBottom:4 }}>✓ {cr.votes?.approve} | ✗ {cr.votes?.reject}</div>
                      <div>{cr.requester}</div>
                    </div>
                  </div>
                  <div style={{ display:'flex', gap:8 }}>
                    {cr.my_vote ? (
                      <span style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', fontStyle:'italic' }}>Has votado: {cr.my_vote}</span>
                    ) : <>
                      <button onClick={() => vote({ id:cr.id, vote:'approve' })} style={{ background:'var(--success-bg)', border:'.5px solid rgba(52,211,153,0.25)', borderRadius:6, padding:'4px 14px', color:'var(--success)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>✓ Aprobar</button>
                      <button onClick={() => vote({ id:cr.id, vote:'reject' })} style={{ background:'var(--danger-bg)', border:'.5px solid rgba(239,68,68,0.25)', borderRadius:6, padding:'4px 14px', color:'var(--danger)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>✗ Rechazar</button>
                      <button onClick={() => vote({ id:cr.id, vote:'abstain' })} style={{ background:'transparent', border:'.5px solid var(--surface-4)', borderRadius:6, padding:'4px 14px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>Abstener</button>
                    </>}
                    {cr.votes?.total >= 3 && !['approved','rejected'].includes(cr.status) && (
                      <div style={{ marginLeft:'auto', display:'flex', gap:6 }}>
                        <button onClick={() => close({ id:cr.id, decision:'approved' })} style={{ background:'var(--success-bg)', border:'.5px solid rgba(52,211,153,0.25)', borderRadius:6, padding:'4px 12px', color:'var(--success)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit', fontWeight:500 }}>Cerrar: Aprobada</button>
                        <button onClick={() => close({ id:cr.id, decision:'rejected' })} style={{ background:'var(--danger-bg)', border:'.5px solid rgba(239,68,68,0.25)', borderRadius:6, padding:'4px 12px', color:'var(--danger)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit', fontWeight:500 }}>Cerrar: Rechazada</button>
                      </div>
                    )}
                  </div>
                </div>
              )
            })
          }
        </div>

        <div>
          <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:14 }}>Ventanas de mantenimiento</div>
          {windows.length === 0 ? (
            <div style={{ ...card, padding:24, textAlign:'center', color:'var(--text-3)', fontSize: "var(--text-base)" }}>Sin ventanas programadas</div>
          ) : windows.slice(0,5).map(w => (
            <div key={w.id} style={{ ...card, padding:'12px 14px', marginBottom:10 }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:4 }}>{w.name}</div>
              <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:2 }}>{w.start_dt} → {w.end_dt}</div>
              <div style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--surface-2)', color:'var(--text-2)', display:'inline-block' }}>{w.environment}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}


export default function ChangesPage() {
  const t = useAppT()
  const toast = useToast()
  const [mainTab, setMainTab] = useState('changes')

  const { hasRole } = useAuth()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(null)
  const [reviewing, setReviewing] = useState(null)
  const [tab, setTab] = useState('project')

  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data) })

  const { data: changesData, isLoading } = useQuery({
    queryKey: ['changes', selectedProject],
    queryFn: () => projectChangesApi.list(selectedProject).then(r => r.data),
    enabled: !!selectedProject,
  })

  const { data: allPending = [] } = useQuery({
    queryKey: ['all-pending-crs'],
    queryFn: () => projectChangesApi.allPending().then(r => r.data),
    enabled: hasRole('admin', 'pm') && tab === 'pending',
  })

  const { mutate: submit, isPending: saving } = useMutation({
    mutationFn: (cr) => projectChangesApi.submit(cr.project_id, cr.id),
    onSuccess: () => qc.invalidateQueries(['changes', selectedProject]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: implement } = useMutation({
    mutationFn: (cr) => projectChangesApi.implement(cr.project_id, cr.id),
    onSuccess: () => qc.invalidateQueries(['changes', selectedProject]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: (cr) => projectChangesApi.delete(cr.project_id, cr.id),
    onSuccess: () => qc.invalidateQueries(['changes', selectedProject]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const crs = changesData?.change_requests || []
  const summary = changesData?.summary || {}

  return (
    <PageShell>
      <PageHeader
        icon={<ArrowLeftRight size={18} />}
        title={t('changes.title')}
        subtitle={t('changes.subtitle')}
        showListExport={mainTab === 'changes' && ((tab === 'project' && crs.length > 0) || (tab === 'pending' && allPending.length > 0))}
        exportTargetSelector='[data-export-table="changes-list"]'
        exportFilePrefix='changes'
      />
      <Tabs
        items={[
          { id: 'changes', label: '🔀 Control de cambios' },
          { id: 'cab',     label: '📋 CAB & Ventanas' },
        ]}
        active={mainTab}
        onChange={setMainTab}
        style={{ marginBottom: 24 }}
      />
      {mainTab === 'cab' && <CABBoard />}
      {mainTab === 'changes' && <div>

      <Tabs
        items={[
          { id: 'project', label: '📁 Por proyecto' },
          ...(hasRole('admin', 'pm') ? [{ id: 'pending', label: '⏳ Pendientes', count: allPending.length }] : []),
        ]}
        active={tab}
        onChange={setTab}
        style={{ marginBottom: 20, paddingBottom: 12, borderBottom: '1px solid var(--surface-4)' }}
      />
      {tab === 'project' && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 24, alignItems: 'center' }}>
            <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
              style={{ flex: 1, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="">Seleccionar proyecto...</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
            {selectedProject && <Button onClick={() => setShowCreate(true)} icon="＋">Nueva CR</Button>}
          </div>

          {selectedProject && summary.total > 0 && (
            <div style={{ display: 'flex', gap: 14, marginBottom: 20 }}>
              {[
                { label: 'Total CRs', value: summary.total, color: 'var(--text-2)' },
                { label: 'Pendientes', value: summary.pending, color: 'var(--warning)' },
                { label: 'Aprobadas', value: summary.approved, color: 'var(--success)' },
                { label: 'Coste adicional', value: fmtCurrency(summary.total_cost_impact), color: 'var(--danger)' },
                { label: 'Días adicionales', value: `+${summary.total_schedule_impact}d`, color: 'var(--danger)' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '12px 16px', flex: 1 }}>
                  <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, fontFamily: 'var(--font-mono)', color }}>{value}</div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
                </div>
              ))}
            </div>
          )}

          {!selectedProject ? (
            <EmptyState icon="📋" title="Selecciona un proyecto" description="Elige un proyecto para ver y gestionar sus solicitudes de cambio" />
          ) : isLoading ? <Spinner /> : crs.length === 0 ? (
            <EmptyState icon="✅" title="Sin solicitudes de cambio" description="Este proyecto no tiene CRs registradas" />
          ) : (
            <div data-export-table="changes-list" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {crs.map(cr => {
                const impact = IMPACT_CFG[cr.impact] || IMPACT_CFG.medium
                return (
                  <div key={cr.id} style={{ padding: '16px 20px', background: 'var(--surface-2)', border: `1px solid ${STATUS_CFG[cr.status]?.color + '30' || 'var(--surface-4)'}`, borderRadius: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 6 }}>
                          <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{cr.code}</span>
                          <span style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{cr.title}</span>
                        </div>
                        <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 8 }}>{cr.description}</p>
                        <div style={{ display: 'flex', gap: 14, fontSize: "var(--text-sm)" }}>
                          <span style={{ color: impact.color, fontWeight: 700 }}>⚡ {impact.label}</span>
                          {cr.cost_impact && <span style={{ color: 'var(--danger)' }}>💰 +{fmtCurrency(cr.cost_impact)}</span>}
                          {cr.schedule_impact_days && <span style={{ color: 'var(--warning)' }}>📅 +{cr.schedule_impact_days}d</span>}
                          {cr.requester_name && <span style={{ color: 'var(--text-2)' }}>👤 {cr.requester_name}</span>}
                        </div>
                        {cr.resolution_notes && <div style={{ marginTop: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)', background: 'var(--surface-3)', borderRadius: 6, padding: '6px 10px' }}>💬 {cr.resolution_notes}</div>}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
                        <StatusBadge status={cr.status} />
                        <div style={{ display: 'flex', gap: 6 }}>
                          {cr.status === 'draft' && <>
                            <button onClick={() => setEditing(cr)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏️</button>
                            <Button size="sm" onClick={() => submit(cr)} loading={saving}>Enviar</Button>
                          </>}
                          {['submitted', 'under_review'].includes(cr.status) && hasRole('admin', 'pm') && (
                            <Button size="sm" onClick={() => setReviewing(cr)}>Revisar</Button>
                          )}
                          {cr.status === 'approved' && (
                            <Button size="sm" onClick={() => implement(cr)}>✓ Implementar</Button>
                          )}
                          <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta solicitud de cambio?', onConfirm: () => del(cr), danger: true }) }} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {tab === 'pending' && (
        allPending.length === 0 ? (
          <EmptyState icon="✅" title="Sin pendientes" description="No hay solicitudes de cambio pendientes de revision" />
        ) : (
          <div data-export-table="changes-list" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {allPending.map(cr => {
              const impact = IMPACT_CFG[cr.impact] || IMPACT_CFG.medium
              return (
                <div key={cr.id} style={{ padding: '16px 20px', background: 'var(--surface-2)', border: '1px solid var(--warning-border)', borderRadius: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>{cr.project_code} · {cr.project_name} · {cr.code}</div>
                      <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 6 }}>{cr.title}</div>
                      <div style={{ display: 'flex', gap: 14, fontSize: "var(--text-sm)" }}>
                        <span style={{ color: impact.color, fontWeight: 700 }}>{impact.label}</span>
                        {cr.cost_impact && <span style={{ color: 'var(--danger)' }}>+{fmtCurrency(cr.cost_impact)}</span>}
                        {cr.schedule_impact_days && <span style={{ color: 'var(--warning)' }}>+{cr.schedule_impact_days}d</span>}
                      </div>
                    </div>
                    <Button size="sm" onClick={() => { setSelectedProject(cr.project_id); setReviewing(cr); setTab('project') }}>Revisar</Button>
                  </div>
                </div>
              )
            })}
          </div>
        )
      )}

      {showCreate && selectedProject && <CRFormModal projectId={selectedProject} onClose={() => setShowCreate(false)} />}
      {editing && <CRFormModal cr={editing} projectId={editing.project_id} onClose={() => setEditing(null)} />}
      {reviewing && <ReviewCRModal cr={reviewing} projectId={reviewing.project_id || selectedProject} onClose={() => setReviewing(null)} />}
      </div>}
    </PageShell>
  )
}