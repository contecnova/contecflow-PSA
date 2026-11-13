import { useId, useState } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import { openConfirmGlobal, pedirTexto } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { projectsApi, projectChangesApi, cabApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ArrowLeftRight } from 'lucide-react'
import { fmtCurrency, extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'
import { alpha } from '../constants/theme'
import DsBadge from '../components/ui/StatusBadge'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
type ImpactLevel = 'low' | 'medium' | 'high' | 'critical' | string
type ChangeStatus = 'draft' | 'submitted' | 'under_review' | 'approved' | 'rejected' | 'implemented' | string
type MainTab = 'changes' | 'cab'
type ChangesTab = 'project' | 'pending'

type ProjectPick = {
  id: string | number
  code?: string
  name?: string
}

type ChangeRequest = {
  id: string | number
  code?: string
  project_id: string | number
  project_code?: string
  project_name?: string
  title: string
  description?: string
  justification?: string
  impact?: ImpactLevel
  cost_impact?: number
  schedule_impact_days?: number
  scope_impact?: string
  requester_name?: string
  requester?: string
  owner_name?: string
  status?: ChangeStatus
  resolution_notes?: string
  votes?: { approve?: number; reject?: number; total?: number }
  my_vote?: string
}

type ChangesSummary = {
  total?: number
  pending?: number
  approved?: number
  total_cost_impact?: number
  total_schedule_impact?: number
}

type ChangesData = {
  change_requests?: ChangeRequest[]
  summary?: ChangesSummary
}

type MaintenanceWindow = {
  id: string | number
  name?: string
  start_dt?: string
  end_dt?: string
  environment?: string
}

type RoleAuth = {
  hasRole: (...roles: string[]) => boolean
}

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const IMPACT_CFG: Record<string, { label: string; color: string }> = {
  low:      { label: 'Bajo',    color: 'var(--success)' },
  medium:   { label: 'Medio',   color: 'var(--accent)' },
  high:     { label: 'Alto',    color: 'var(--warning)' },
  critical: { label: 'Crítico', color: 'var(--danger)' },
}
const STATUS_CFG: Record<string, { label: string; color: string }> = {
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

function StatusBadge({ status }: { status?: ChangeStatus }) {
  const cfg = (status && STATUS_CFG[status]) || STATUS_CFG.draft
  return <DsBadge color={cfg.color}>{cfg.label}</DsBadge>
}

function CRFormModal({ cr, projectId, onClose }: { cr?: ChangeRequest | null; projectId: string | number; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT() as (key: string) => string
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
  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const { mutate, isPending } = useMutation({
    mutationFn: (data: Record<string, unknown>) => isEdit && cr
      ? projectChangesApi.update(projectId, cr.id, data)
      : projectChangesApi.create(projectId, data),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['changes', projectId] }); qc.invalidateQueries({ queryKey: ['all-pending-crs'] }); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data)
  }

  return (
    <Modal open title={isEdit ? `Editar CR — ${cr.code}` : 'Nueva Solicitud de Cambio'} onClose={onClose} width={620}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label htmlFor={`${idPrefix}-title`} style={ls}>{t('changes.titulo')}</label>
          <input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} style={validation.inputStyle(fs, 'title')} placeholder={t('changes.titulo_de_la_solicitud')} aria-label={t('changes.titulo_de_la_solicitud')} />
          {validation.errors.title && <p className="u-field-error">{validation.errors.title}</p>}
        </div>
        <div className="u-col-full">
          <label htmlFor={`${idPrefix}-description`} style={ls}>{t('changes.descripcion')}</label>
          <textarea id={`${idPrefix}-description`} value={form.description} onChange={set('description')} rows={3} style={validation.inputStyle({ ...fs, resize: 'vertical' }, 'description')} placeholder={t('changes.describe_el_cambio_solicitado')} aria-label={t('changes.descripcion_del_cambio')} />
          {validation.errors.description && <p className="u-field-error">{validation.errors.description}</p>}
        </div>
        <div className="u-col-full">
          <label htmlFor={`${idPrefix}-justification`} style={ls}>{t('changes.justificacion')}</label>
          <textarea id={`${idPrefix}-justification`} value={form.justification} onChange={set('justification')} rows={2} style={validation.inputStyle({ ...fs, resize: 'vertical' }, 'justification')} placeholder={t('changes.justificacion_del_cambio')} aria-label={t('changes.justificacion_del_cambio')} />
          {validation.errors.justification && <p className="u-field-error">{validation.errors.justification}</p>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-impact`} style={ls}>Impacto</label>
          <select id={`${idPrefix}-impact`} value={form.impact} onChange={set('impact')} style={validation.inputStyle(fs, 'impact')}>
            {Object.entries(IMPACT_CFG).map(([v, c]) => <option key={v} value={v}>{c.label}</option>)}
          </select>
          {validation.errors.impact && <p className="u-field-error">{validation.errors.impact}</p>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-cost-impact`} style={ls}>Impacto en coste ({fmtMoneda.simbolo})</label>
          <input id={`${idPrefix}-cost-impact`} type="number" value={form.cost_impact} onChange={set('cost_impact')} style={validation.inputStyle(fs, 'cost_impact')} placeholder="Impacto economico" aria-label="Impacto economico" />
          {validation.errors.cost_impact && <p className="u-field-error">{validation.errors.cost_impact}</p>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-schedule-impact`} style={ls}>{t('changes.impacto_en_plazo_dias')}</label>
          <input id={`${idPrefix}-schedule-impact`} type="number" value={form.schedule_impact_days} onChange={set('schedule_impact_days')} style={validation.inputStyle(fs, 'schedule_impact_days')} placeholder="Dias adicionales" aria-label="Dias adicionales" />
          {validation.errors.schedule_impact_days && <p className="u-field-error">{validation.errors.schedule_impact_days}</p>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-scope-impact`} style={ls}>Impacto en alcance</label>
          <input id={`${idPrefix}-scope-impact`} value={form.scope_impact} onChange={set('scope_impact')} style={validation.inputStyle(fs, 'scope_impact')} placeholder={t('changes.impacto_en_el_alcance')} aria-label={t('changes.impacto_en_el_alcance')} />
          {validation.errors.scope_impact && <p className="u-field-error">{validation.errors.scope_impact}</p>}
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={isPending} loading={isPending}>
            {isPending ? t('common.saving') : isEdit ? t('common.save') : 'Crear CR'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ReviewCRModal({ cr, projectId, onClose }: { cr: ChangeRequest; projectId: string | number; onClose: () => void }) {
  const t = useAppT() as (key: string) => string
  const idPrefix = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const [notes, setNotes] = useState('')
  const validation = useFormValidation(reviewSchema)
  const { mutate, isPending } = useMutation({
    mutationFn: ({ approved, resolution_notes }: { approved: boolean; resolution_notes?: string }) => projectChangesApi.review(projectId, cr.id, { approved, resolution_notes }),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['changes', projectId] }); qc.invalidateQueries({ queryKey: ['all-pending-crs'] }); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const impact = (cr.impact && IMPACT_CFG[cr.impact]) || IMPACT_CFG.medium

  const submitReview = (approved: boolean) => {
    const result = validation.validateForm({ approved, resolution_notes: notes })
    if (!result.success) return
    mutate({ ...result.data, approved })
  }

  return (
    <Modal open title={`Revisar CR — ${cr.code}`} onClose={onClose} width={520}>
      <div className="u-mb-16">
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
              <div className="u-base-600">{value}</div>
            </div>
          ))}
        </div>
        {cr.scope_impact && <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', background: 'var(--surface-3)', borderRadius: 8, padding: '8px 12px' }}>📋 {cr.scope_impact}</p>}
      </div>
      <div className="u-mb-16">
        <label htmlFor={`${idPrefix}-resolution-notes`} style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }}>{t('changes.notas_de_resolucion')}</label>
        <textarea id={`${idPrefix}-resolution-notes`} value={notes} onChange={e => { setNotes(e.target.value); validation.clearFieldError('resolution_notes') }} rows={2}
          style={validation.inputStyle({ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box' }, 'resolution_notes')} />
        {validation.errors.resolution_notes && <p className="u-field-error">{validation.errors.resolution_notes}</p>}
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="danger" onClick={() => submitReview(false)} disabled={isPending} loading={isPending}>✕ Rechazar</Button>
        <Button onClick={() => submitReview(true)} disabled={isPending} loading={isPending}>✓ Aprobar</Button>
      </div>
    </Modal>
  )
}

// ── CAB Board Tab ─────────────────────────────────────────────────────────────
function CABBoard() {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT() as (key: string) => string
  const { hasRole } = useAuth() as RoleAuth
  // Cerrar es de admin en el servidor. Contra el recuento, o con empate, pide motivo (revisión 2026-11).
  const cerrar = async (cr: ChangeRequest, decision: 'approved' | 'rejected') => {
    const aFavor = cr.votes?.approve ?? 0, enContra = cr.votes?.reject ?? 0
    const mayoria = aFavor > enContra ? 'approved' : enContra > aFavor ? 'rejected' : null
    if (decision === mayoria) { close({ id: cr.id, decision }); return }
    const reason = await pedirTexto({
      title: 'Motivo de la decisión',
      message: `La decisión no sigue la votación (${aFavor} a favor, ${enContra} en contra).`,
      label: 'Motivo',
      required: true,
      multiline: true,
    })
    if (reason && reason.trim()) close({ id: cr.id, decision, reason })
  }
  const toast = useToast()
  const qc = useQueryClient()
  const { data: pendingCRs = [], isLoading } = useQuery<ChangeRequest[]>({
    queryKey: ['cab-pending'],
    queryFn: () => cabApi.changes().then(r => (r.data?.items ?? r.data ?? []) as ChangeRequest[]),
  })
  const { data: windows = [] } = useQuery<MaintenanceWindow[]>({
    queryKey: ['maintenance-windows'],
    queryFn: () => cabApi.windows().then(r => (r.data?.items ?? r.data ?? []) as MaintenanceWindow[]),
  })
  const { mutate: vote, isPending: _saving } = useMutation({
    mutationFn: ({ id, vote, comment }: { id: string | number; vote: 'approve' | 'reject' | 'abstain'; comment?: string }) => cabApi.vote(id, { vote, comment }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cab-pending'] }); qc.invalidateQueries({ queryKey: ['changes'] }); qc.invalidateQueries({ queryKey: ['all-pending-crs'] }); },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: close } = useMutation({
    mutationFn: ({ id, decision, reason }: { id: string | number; decision: 'approved' | 'rejected'; reason?: string }) => cabApi.close(id, { decision, reason }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cab-pending'] }); qc.invalidateQueries({ queryKey: ['changes'] }); qc.invalidateQueries({ queryKey: ['all-pending-crs'] }); },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const card: CSSProperties = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }

  return (
    <div>
      <div style={{ display:'grid', gridTemplateColumns:'2fr 1fr', gap:20 }}>
        <div>
          <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:14 }}>{t('changes.crs_pendientes_de_votacion_cab')}{pendingCRs.length})</div>
          {isLoading ? <div className="u-text2-base">{t('common.loading')}</div> :
            pendingCRs.length === 0 ? (
              <div style={{ ...card, padding:32, textAlign:'center', color:'var(--text-3)', fontSize: "var(--text-base)" }}>{t('changes.sin_crs_pendientes_de_votacion')}</div>
            ) : pendingCRs.map((cr) => {
              const ic = (cr.impact && IMPACT_CFG[cr.impact]) || IMPACT_CFG.medium
              return (
                <div key={cr.id} style={{ ...card, padding:'16px 20px', marginBottom:12 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:10 }}>
                    <div>
                      <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:2 }}>{cr.project_code} · {cr.code}</div>
                      <div style={{ fontSize: "var(--text-md)", fontWeight:500, marginBottom:6 }}>{cr.title}</div>
                      <div style={{ display:'flex', gap:12, fontSize: "var(--text-sm)" }}>
                        <span style={{ color:ic.color, fontWeight:500 }}>{ic.label} impacto</span>
                        {cr.cost_impact && <span className="u-danger">+{fmtMoneda(cr.cost_impact)}</span>}
                        {cr.schedule_impact_days && <span className="u-warning">+{cr.schedule_impact_days}d</span>}
                      </div>
                    </div>
                    <div style={{ textAlign:'right', fontSize: "var(--text-sm)", color:'var(--text-2)' }}>
                      <div style={{ marginBottom:4 }}>✓ {cr.votes?.approve} | ✗ {cr.votes?.reject}</div>
                      <div>{cr.requester}</div>
                    </div>
                  </div>
                  <div className="u-row-8">
                    {cr.my_vote ? (
                      <span style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', fontStyle:'italic' }}>Has votado: {cr.my_vote}</span>
                    ) : <>
                      <button onClick={() => vote({ id:cr.id, vote:'approve' })} style={{ background:'var(--success-bg)', border:'.5px solid rgba(52,211,153,0.25)', borderRadius:'var(--radius-sm)', padding:'4px 14px', color:'var(--success)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>✓ Aprobar</button>
                      <button onClick={() => vote({ id:cr.id, vote:'reject' })} style={{ background:'var(--danger-bg)', border:'.5px solid rgba(239,68,68,0.25)', borderRadius:'var(--radius-sm)', padding:'4px 14px', color:'var(--danger)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>✗ Rechazar</button>
                      <button onClick={() => vote({ id:cr.id, vote:'abstain' })} style={{ background:'transparent', border:'.5px solid var(--surface-4)', borderRadius:'var(--radius-sm)', padding:'4px 14px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>Abstener</button>
                    </>}
                    {hasRole('admin') && ['submitted', 'under_review'].includes(cr.status ?? '') && (
                      <div style={{ marginLeft:'auto', display:'flex', gap:6 }}>
                        <button onClick={() => cerrar(cr, 'approved')} style={{ background:'var(--success-bg)', border:'.5px solid rgba(52,211,153,0.25)', borderRadius:'var(--radius-sm)', padding:'4px 12px', color:'var(--success)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit', fontWeight:500 }}>Cerrar: Aprobada</button>
                        <button onClick={() => cerrar(cr, 'rejected')} style={{ background:'var(--danger-bg)', border:'.5px solid rgba(239,68,68,0.25)', borderRadius:'var(--radius-sm)', padding:'4px 12px', color:'var(--danger)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit', fontWeight:500 }}>Cerrar: Rechazada</button>
                      </div>
                    )}
                  </div>
                </div>
              )
            })
          }
        </div>

        <div>
          <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:14 }}>{t('changes.ventanas_de_mantenimiento')}</div>
          {windows.length === 0 ? (
            <div style={{ ...card, padding:24, textAlign:'center', color:'var(--text-3)', fontSize: "var(--text-base)" }}>{t('changes.sin_ventanas_programadas')}</div>
          ) : windows.slice(0,5).map((w) => (
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


export default function ChangesPage(): JSX.Element {
  const t = useAppT() as (key: string) => string
  const toast = useToast()
  const [mainTab, setMainTab] = useState<MainTab>('changes')

  const { hasRole } = useAuth() as RoleAuth
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState<string | number>('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<ChangeRequest | null>(null)
  const [reviewing, setReviewing] = useState<ChangeRequest | null>(null)
  const [tab, setTab] = useState<ChangesTab>('project')

  const { data: projects = [] } = useQuery<ProjectPick[]>({ queryKey: ['projects'], queryFn: () => projectsApi.list({}).then(r => (r.data ?? []) as ProjectPick[]) })

  const { data: changesData, isLoading } = useQuery<ChangesData>({
    queryKey: ['changes', selectedProject],
    queryFn: () => projectChangesApi.list(selectedProject).then(r => r.data as ChangesData),
    enabled: !!selectedProject,
  })

  const { data: allPending = [] } = useQuery<ChangeRequest[]>({
    queryKey: ['all-pending-crs'],
    queryFn: () => projectChangesApi.allPending().then(r => (r.data?.items ?? r.data ?? []) as ChangeRequest[]),
    enabled: hasRole('admin', 'pm') && tab === 'pending',
  })

  const { mutate: submit, isPending: saving } = useMutation({
    mutationFn: (cr: ChangeRequest) => projectChangesApi.submit(cr.project_id, cr.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['changes', selectedProject] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: implement } = useMutation({
    mutationFn: (cr: ChangeRequest) => projectChangesApi.implement(cr.project_id, cr.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['changes', selectedProject] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: (cr: ChangeRequest) => projectChangesApi.delete(cr.project_id, cr.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['changes', selectedProject] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
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
        onChange={(id: string) => setMainTab(id as MainTab)}
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
        onChange={(id: string) => setTab(id as ChangesTab)}
        style={{ marginBottom: 20, paddingBottom: 12, borderBottom: '1px solid var(--surface-4)' }}
      />
      {tab === 'project' && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 24, alignItems: 'center' }}>
            <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
              style={{ flex: 1, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="">Seleccionar proyecto...</option>
              {projects.map((p) => <option key={p.id} value={String(p.id)}>{p.code} — {p.name}</option>)}
            </select>
            {selectedProject && <Button onClick={() => setShowCreate(true)} icon="＋">{t('changes.nueva_cr')}</Button>}
          </div>

          {selectedProject && (summary.total ?? 0) > 0 && (
            <div style={{ display: 'flex', gap: 14, marginBottom: 20 }}>
              {[
                { label: 'Total CRs', value: summary.total, color: 'var(--text-2)' },
                { label: 'Pendientes', value: summary.pending, color: 'var(--warning)' },
                { label: 'Aprobadas', value: summary.approved, color: 'var(--success)' },
                { label: 'Coste adicional', value: fmtCurrency(summary.total_cost_impact), color: 'var(--danger)' },
                { label: 'Días adicionales', value: `+${summary.total_schedule_impact}d`, color: 'var(--danger)' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '12px 16px', flex: 1 }}>
                  <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, fontFamily: 'var(--font-mono)', color }}>{value}</div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
                </div>
              ))}
            </div>
          )}

          {!selectedProject ? (
            <EmptyState icon="📋" title={t('changes.selecciona_un_proyecto')} description="Elige un proyecto para ver y gestionar sus solicitudes de cambio" />
          ) : isLoading ? <Spinner /> : crs.length === 0 ? (
            <EmptyState icon="✅" title={t('changes.no_changes')} description="Este proyecto no tiene CRs registradas" />
          ) : (
            <div data-export-table="changes-list" className="u-stack-10">
              {crs.map((cr) => {
                const impact = (cr.impact && IMPACT_CFG[cr.impact]) || IMPACT_CFG.medium
                return (
                  <div key={cr.id} style={{ padding: '16px 20px', background: 'var(--surface-2)', border: `1px solid ${alpha((STATUS_CFG[cr.status ?? '']?.color ?? 'var(--surface-4)'), '30')}`, borderRadius: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                      <div className="u-flex1">
                        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 6 }}>
                          <span className="u-text2-mono-xs">{cr.code}</span>
                          <span className="u-md-700">{cr.title}</span>
                        </div>
                        <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 8 }}>{cr.description}</p>
                        <div style={{ display: 'flex', gap: 14, fontSize: "var(--text-sm)" }}>
                          <span style={{ color: impact.color, fontWeight: 700 }}>⚡ {impact.label}</span>
                          {cr.cost_impact && <span className="u-danger">💰 +{fmtCurrency(cr.cost_impact)}</span>}
                          {cr.schedule_impact_days && <span className="u-warning">📅 +{cr.schedule_impact_days}d</span>}
                          {cr.requester_name && <span className="u-text2">👤 {cr.requester_name}</span>}
                        </div>
                        {cr.resolution_notes && <div style={{ marginTop: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)', background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)', padding: '6px 10px' }}>💬 {cr.resolution_notes}</div>}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
                        <StatusBadge status={cr.status} />
                        <div className="u-row-6">
                          {cr.status === 'draft' && <>
                            <button onClick={() => setEditing(cr)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏️</button>
                            <Button size="sm" onClick={() => submit(cr)} loading={saving}>Enviar</Button>
                          </>}
                          {['submitted', 'under_review'].includes(cr.status ?? '') && hasRole('admin', 'pm') && (
                            <Button size="sm" onClick={() => setReviewing(cr)}>Revisar</Button>
                          )}
                          {cr.status === 'approved' && (
                            <Button size="sm" onClick={() => implement(cr)}>✓ Implementar</Button>
                          )}
                          <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta solicitud de cambio?', onConfirm: () => del(cr), danger: true }) }} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
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
          <EmptyState icon="✅" title={t('changes.sin_pendientes')} description="No hay solicitudes de cambio pendientes de revision" />
        ) : (
          <div data-export-table="changes-list" className="u-stack-10">
            {allPending.map((cr) => {
              const impact = (cr.impact && IMPACT_CFG[cr.impact]) || IMPACT_CFG.medium
              return (
                <div key={cr.id} style={{ padding: '16px 20px', background: 'var(--surface-2)', border: '1px solid var(--warning-border)', borderRadius: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                    <div className="u-flex1">
                      <div className="u-text2-xs-mb4">{cr.project_code} · {cr.project_name} · {cr.code}</div>
                      <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 6 }}>{cr.title}</div>
                      <div style={{ display: 'flex', gap: 14, fontSize: "var(--text-sm)" }}>
                        <span style={{ color: impact.color, fontWeight: 700 }}>{impact.label}</span>
                        {cr.cost_impact && <span className="u-danger">+{fmtCurrency(cr.cost_impact)}</span>}
                        {cr.schedule_impact_days && <span className="u-warning">+{cr.schedule_impact_days}d</span>}
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