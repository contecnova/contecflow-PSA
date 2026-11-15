import { useId, useMemo, useState } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import { openConfirmGlobal, pedirTexto } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { projectsApi, projectChangesApi, cabApi } from '../services/api'
import type { CambioEnCab } from '../services/api/tipos-cambios'
import type { SolicitudDeCambio } from '../services/api/tipos-proyectos'
import { Button, Modal, Spinner, EmptyState, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ArrowLeftRight } from 'lucide-react'
import { fmtCurrency, fmtDateTime, extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'
import { alpha } from '../constants/theme'
import DsBadge from '../components/ui/StatusBadge'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './ChangesPage.css'
type ChangeStatus = 'draft' | 'submitted' | 'under_review' | 'approved' | 'rejected' | 'implemented' | string
type MainTab = 'changes' | 'cab'
type ChangesTab = 'project' | 'pending'

type ProjectPick = {
  id: string | number
  code?: string
  name?: string
}

type RoleAuth = {
  hasRole: (...roles: string[]) => boolean
}

type TFn = (key: string, params?: Record<string, unknown>) => string

const IMPACT_CFG: Record<string, { labelKey: string; color: string }> = {
  low:      { labelKey: 'changes.impact_low',      color: 'var(--success)' },
  medium:   { labelKey: 'changes.impact_medium',   color: 'var(--accent)' },
  high:     { labelKey: 'changes.impact_high',     color: 'var(--warning)' },
  critical: { labelKey: 'changes.impact_critical', color: 'var(--danger)' },
}
const STATUS_CFG: Record<string, { labelKey: string; color: string }> = {
  draft:        { labelKey: 'changes.status_draft',        color: 'var(--text-2)' },
  submitted:    { labelKey: 'changes.status_submitted',    color: 'var(--accent)' },
  under_review: { labelKey: 'changes.status_under_review', color: 'var(--warning)' },
  approved:     { labelKey: 'changes.status_approved',     color: 'var(--success)' },
  rejected:     { labelKey: 'changes.status_rejected',     color: 'var(--danger)' },
  implemented:  { labelKey: 'changes.status_implemented',  color: 'var(--purple)' },
}

/** Tabs (primitiva compartida) fija su margen en línea; solo admite el ajuste por `style`. */


/** Color dinámico (impacto/estado) como propiedad CSS que consume `.chg-tone`. */
const tone = (color: string): CSSProperties => ({ '--chg-tone': color } as CSSProperties)

const crearCrSchema = (t: TFn) => z.object({
  title: z.string().trim().min(1, t('changes.err_title_required')),
  description: z.string().trim().min(1, t('changes.err_description_required')),
  justification: z.string().optional(),
  impact: z.enum(['low', 'medium', 'high', 'critical']),
  cost_impact: z.preprocess(
    (v) => (v === '' || v === null || typeof v === 'undefined' ? undefined : v),
    z.coerce.number().min(0, t('changes.err_cost_negative')).optional(),
  ),
  schedule_impact_days: z.preprocess(
    (v) => (v === '' || v === null || typeof v === 'undefined' ? undefined : v),
    z.coerce.number().int(t('changes.err_integer')).min(0, t('changes.err_negative')).optional(),
  ),
  scope_impact: z.string().optional(),
})

const crearReviewSchema = (t: TFn) => z.object({
  approved: z.boolean(),
  resolution_notes: z.string().trim().optional(),
}).superRefine((values, ctx) => {
  if (!values.approved && !values.resolution_notes) {
    ctx.addIssue({
      code: 'custom',
      path: ['resolution_notes'],
      message: t('changes.err_notes_required'),
    })
  }
})

function StatusBadge({ status }: { status?: ChangeStatus }) {
  const t = useAppT()
  const cfg = (status && STATUS_CFG[status]) || STATUS_CFG.draft
  return <DsBadge color={cfg.color}>{t(cfg.labelKey)}</DsBadge>
}

function CRFormModal({ cr, projectId, onClose }: { cr?: SolicitudDeCambio | null; projectId: string | number; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
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
  const crSchema = useMemo(() => crearCrSchema(t), [t])
  const validation = useFormValidation(crSchema)
  const set = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }
  /** Props de error accesibles: borde rojo vía `[aria-invalid]` y mensaje enlazado. */
  const err = (k: keyof typeof form) => ({
    'aria-invalid': !!validation.errors[k] || undefined,
    'aria-describedby': validation.errors[k] ? `${idPrefix}-${k}-err` : undefined,
  })
  const errMsg = (k: keyof typeof form) => validation.errors[k]
    ? <p id={`${idPrefix}-${k}-err`} className="u-field-error">{validation.errors[k]}</p>
    : null

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
    <Modal open title={isEdit ? t('changes.edit_cr_title', { code: cr.code }) : t('changes.new_cr_title')} onClose={onClose} width={620}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label htmlFor={`${idPrefix}-title`} className="chg-label">{t('changes.titulo')}</label>
          <input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} className="chg-input" {...err('title')} placeholder={t('changes.titulo_de_la_solicitud')} />
          {errMsg('title')}
        </div>
        <div className="u-col-full">
          <label htmlFor={`${idPrefix}-description`} className="chg-label">{t('changes.descripcion')}</label>
          <textarea id={`${idPrefix}-description`} value={form.description} onChange={set('description')} rows={3} className="chg-input" {...err('description')} placeholder={t('changes.describe_el_cambio_solicitado')} />
          {errMsg('description')}
        </div>
        <div className="u-col-full">
          <label htmlFor={`${idPrefix}-justification`} className="chg-label">{t('changes.justificacion')}</label>
          <textarea id={`${idPrefix}-justification`} value={form.justification} onChange={set('justification')} rows={2} className="chg-input" {...err('justification')} placeholder={t('changes.justificacion_del_cambio')} />
          {errMsg('justification')}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-impact`} className="chg-label">{t('changes.impact')}</label>
          <select id={`${idPrefix}-impact`} value={form.impact} onChange={set('impact')} className="chg-input" {...err('impact')}>
            {Object.entries(IMPACT_CFG).map(([v, c]) => <option key={v} value={v}>{t(c.labelKey)}</option>)}
          </select>
          {errMsg('impact')}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-cost-impact`} className="chg-label">{t('changes.cost_impact_label', { symbol: fmtMoneda.simbolo })}</label>
          <input id={`${idPrefix}-cost-impact`} type="number" value={form.cost_impact} onChange={set('cost_impact')} className="chg-input" {...err('cost_impact')} placeholder={t('changes.cost_impact_ph')} />
          {errMsg('cost_impact')}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-schedule-impact`} className="chg-label">{t('changes.impacto_en_plazo_dias')}</label>
          <input id={`${idPrefix}-schedule-impact`} type="number" value={form.schedule_impact_days} onChange={set('schedule_impact_days')} className="chg-input" {...err('schedule_impact_days')} placeholder={t('changes.extra_days_ph')} />
          {errMsg('schedule_impact_days')}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-scope-impact`} className="chg-label">{t('changes.scope_impact_label')}</label>
          <input id={`${idPrefix}-scope-impact`} value={form.scope_impact} onChange={set('scope_impact')} className="chg-input" {...err('scope_impact')} placeholder={t('changes.impacto_en_el_alcance')} />
          {errMsg('scope_impact')}
        </div>
        <div className="chg-form-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={isPending} loading={isPending}>
            {isPending ? t('common.saving') : isEdit ? t('common.save') : t('changes.create_cr')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ReviewCRModal({ cr, projectId, onClose }: { cr: SolicitudDeCambio; projectId: string | number; onClose: () => void }) {
  const t = useAppT()
  const idPrefix = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const [notes, setNotes] = useState('')
  const reviewSchema = useMemo(() => crearReviewSchema(t), [t])
  const validation = useFormValidation(reviewSchema)
  const { mutate, isPending } = useMutation({
    mutationFn: ({ approved, resolution_notes }: { approved: boolean; resolution_notes?: string }) => projectChangesApi.review(projectId, cr.id, { approved, resolution_notes }),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['changes', projectId] }); qc.invalidateQueries({ queryKey: ['all-pending-crs'] }); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const impact = (cr.impact && IMPACT_CFG[cr.impact]) || IMPACT_CFG.medium
  const notesErr = validation.errors.resolution_notes

  const submitReview = (approved: boolean) => {
    const result = validation.validateForm({ approved, resolution_notes: notes })
    if (!result.success) return
    mutate({ ...result.data, approved })
  }

  return (
    <Modal open title={t('changes.review_cr_title', { code: cr.code })} onClose={onClose} width={520}>
      <div className="u-mb-16">
        <div className="chg-review-title">{cr.title}</div>
        <p className="chg-review-desc">{cr.description}</p>
        <div className="chg-review-grid">
          {[
            { key: 'impact', label: t('changes.impact'), value: <span className="chg-tone" style={tone(impact.color)}>{t(impact.labelKey)}</span> },
            { key: 'cost', label: t('changes.extra_cost'), value: cr.cost_impact ? fmtCurrency(cr.cost_impact) : '—' },
            { key: 'days', label: t('changes.extra_days'), value: cr.schedule_impact_days ? t('changes.plus_days', { n: cr.schedule_impact_days }) : '—' },
          ].map(({ key, label, value }) => (
            <div key={key} className="chg-review-cell">
              <div className="chg-review-cell__label">{label}</div>
              <div className="u-base-600">{value}</div>
            </div>
          ))}
        </div>
        {cr.scope_impact && <p className="chg-review-scope"><span aria-hidden="true">📋 </span>{cr.scope_impact}</p>}
      </div>
      <div className="u-mb-16">
        <label htmlFor={`${idPrefix}-resolution-notes`} id={`${idPrefix}-resolution-notes-etiqueta`} className="chg-label chg-label--notes">{t('changes.notas_de_resolucion')}</label>
        <textarea id={`${idPrefix}-resolution-notes`} aria-labelledby={`${idPrefix}-resolution-notes-etiqueta`} value={notes} onChange={e => { setNotes(e.target.value); validation.clearFieldError('resolution_notes') }} rows={2}
          className="chg-input" aria-invalid={!!notesErr || undefined} aria-describedby={notesErr ? `${idPrefix}-resolution-notes-err` : undefined} />
        {notesErr && <p id={`${idPrefix}-resolution-notes-err`} className="u-field-error">{notesErr}</p>}
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="danger" onClick={() => submitReview(false)} disabled={isPending} loading={isPending}>✕ {t('changes.reject')}</Button>
        <Button onClick={() => submitReview(true)} disabled={isPending} loading={isPending}>✓ {t('changes.approve')}</Button>
      </div>
    </Modal>
  )
}

// ── CAB Board Tab ─────────────────────────────────────────────────────────────
function CABBoard() {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const { hasRole } = useAuth() as RoleAuth
  // Cerrar es de admin en el servidor. Contra el recuento, o con empate, pide motivo (revisión 2026-11).
  const cerrar = async (cr: CambioEnCab, decision: 'approved' | 'rejected') => {
    const aFavor = cr.votes?.approve ?? 0, enContra = cr.votes?.reject ?? 0
    const mayoria = aFavor > enContra ? 'approved' : enContra > aFavor ? 'rejected' : null
    if (decision === mayoria) { close({ id: cr.id, decision }); return }
    const reason = await pedirTexto({
      title: t('changes.close_reason_title'),
      message: t('changes.close_reason_msg', { approve: aFavor, reject: enContra }),
      label: t('changes.close_reason_label'),
      required: true,
      multiline: true,
    })
    if (reason && reason.trim()) close({ id: cr.id, decision, reason })
  }
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
  const { mutate: vote } = useMutation({
    mutationFn: ({ id, vote, comment }: { id: string | number; vote: 'approve' | 'reject' | 'abstain'; comment?: string }) => cabApi.vote(id, { vote, comment }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cab-pending'] }); qc.invalidateQueries({ queryKey: ['changes'] }); qc.invalidateQueries({ queryKey: ['all-pending-crs'] }); },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: close } = useMutation({
    mutationFn: ({ id, decision, reason }: { id: string | number; decision: 'approved' | 'rejected'; reason?: string }) => cabApi.close(id, { decision, reason }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cab-pending'] }); qc.invalidateQueries({ queryKey: ['changes'] }); qc.invalidateQueries({ queryKey: ['all-pending-crs'] }); },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const VOTE_LABEL: Record<string, string> = {
    approve: t('changes.vote_approve'),
    reject: t('changes.vote_reject'),
    abstain: t('changes.vote_abstain'),
  }

  return (
    <div>
      <div className="chg-cab-grid">
        <div>
          <div className="chg-section-title">{t('changes.cab_pending_title', { count: pendingCRs.length })}</div>
          {isLoading ? <div className="u-text2-base">{t('common.loading')}</div> :
            pendingCRs.length === 0 ? (
              <div className="chg-card chg-card--empty">{t('changes.sin_crs_pendientes_de_votacion')}</div>
            ) : pendingCRs.map((cr) => {
              const ic = (cr.impact && IMPACT_CFG[cr.impact]) || IMPACT_CFG.medium
              return (
                <div key={cr.id} className="chg-card chg-card--cr">
                  <div className="chg-cab-head">
                    <div>
                      <div className="chg-meta">{cr.project_code} · {cr.code}</div>
                      <div className="chg-cab-title">{cr.title}</div>
                      <div className="chg-facts">
                        <span className="chg-tone chg-tone--500" style={tone(ic.color)}>{t('changes.impact_suffix', { level: t(ic.labelKey) })}</span>
                        {cr.cost_impact && <span className="u-danger">+{fmtMoneda(cr.cost_impact)}</span>}
                        {cr.schedule_impact_days && <span className="u-warning">{t('changes.plus_days', { n: cr.schedule_impact_days })}</span>}
                      </div>
                    </div>
                    <div className="chg-votes">
                      <div className="chg-votes__count" aria-label={t('changes.votes_aria', { approve: cr.votes?.approve ?? 0, reject: cr.votes?.reject ?? 0 })}>✓ {cr.votes?.approve} | ✗ {cr.votes?.reject}</div>
                      <div>{cr.requester}</div>
                    </div>
                  </div>
                  <div className="chg-cab-actions">
                    {cr.my_vote ? (
                      <span className="chg-my-vote">{t('changes.you_voted', { vote: VOTE_LABEL[cr.my_vote] ?? cr.my_vote })}</span>
                    ) : <>
                      <button type="button" onClick={() => vote({ id:cr.id, vote:'approve' })} className="chg-vote-btn chg-vote-btn--success">✓ {t('changes.approve')}</button>
                      <button type="button" onClick={() => vote({ id:cr.id, vote:'reject' })} className="chg-vote-btn chg-vote-btn--danger">✗ {t('changes.reject')}</button>
                      <button type="button" onClick={() => vote({ id:cr.id, vote:'abstain' })} className="chg-vote-btn">{t('changes.abstain')}</button>
                    </>}
                    {hasRole('admin') && ['submitted', 'under_review'].includes(cr.status ?? '') && (
                      <div className="chg-admin-actions">
                        <button type="button" onClick={() => cerrar(cr, 'approved')} className="chg-vote-btn chg-vote-btn--success chg-vote-btn--close">{t('changes.close_approved')}</button>
                        <button type="button" onClick={() => cerrar(cr, 'rejected')} className="chg-vote-btn chg-vote-btn--danger chg-vote-btn--close">{t('changes.close_rejected')}</button>
                      </div>
                    )}
                  </div>
                </div>
              )
            })
          }
        </div>

        <div>
          <div className="chg-section-title">{t('changes.ventanas_de_mantenimiento')}</div>
          {windows.length === 0 ? (
            <div className="chg-card chg-card--empty chg-card--empty-sm">{t('changes.sin_ventanas_programadas')}</div>
          ) : windows.slice(0,5).map((w) => (
            <div key={w.id} className="chg-card chg-card--window">
              <div className="chg-window-name">{w.name}</div>
              <div className="chg-meta">{fmtDateTime(w.start_dt)} → {fmtDateTime(w.end_dt)}</div>
              <div className="chg-env">{w.environment}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function ChangesPage(): JSX.Element {
  const t = useAppT()
  const toast = useToast()
  const [mainTab, setMainTab] = useState<MainTab>('changes')

  const { hasRole } = useAuth() as RoleAuth
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState<string | number>('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<SolicitudDeCambio | null>(null)
  const [reviewing, setReviewing] = useState<SolicitudDeCambio | null>(null)
  const [tab, setTab] = useState<ChangesTab>('project')

  const { data: projects = [] } = useQuery<ProjectPick[]>({ queryKey: ['projects'], queryFn: () => projectsApi.list({}).then(r => (r.data ?? []) as ProjectPick[]) })

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
    mutationFn: (cr: SolicitudDeCambio) => projectChangesApi.submit(cr.project_id, cr.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['changes', selectedProject] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: implement } = useMutation({
    mutationFn: (cr: SolicitudDeCambio) => projectChangesApi.implement(cr.project_id, cr.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['changes', selectedProject] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: (cr: SolicitudDeCambio) => projectChangesApi.delete(cr.project_id, cr.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['changes', selectedProject] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const crs = changesData?.change_requests || []
  const summary = changesData?.summary

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
          { id: 'changes', label: t('changes.tab_changes') },
          { id: 'cab',     label: t('changes.tab_cab') },
        ]}
        active={mainTab}
        onChange={(id: string) => setMainTab(id as MainTab)}
        className="changes-page-e1"
      />
      {mainTab === 'cab' && <CABBoard />}
      {mainTab === 'changes' && <div>

      <Tabs
        items={[
          { id: 'project', label: t('changes.tab_project') },
          ...(hasRole('admin', 'pm') ? [{ id: 'pending', label: t('changes.tab_pending'), count: allPending.length }] : []),
        ]}
        active={tab}
        onChange={(id: string) => setTab(id as ChangesTab)}
        className="changes-page-e2"
      />
      {tab === 'project' && (
        <>
          <div className="chg-toolbar">
            <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
              aria-label={t('changes.project_select_aria')} className="chg-input chg-input--project">
              <option value="">{t('changes.select_project_ph')}</option>
              {projects.map((p) => <option key={p.id} value={String(p.id)}>{p.code} — {p.name}</option>)}
            </select>
            {selectedProject && <Button onClick={() => setShowCreate(true)} icon="＋">{t('changes.nueva_cr')}</Button>}
          </div>

          {selectedProject && summary && (summary.total ?? 0) > 0 && (
            <div className="chg-summary">
              {[
                { key: 'total', label: t('changes.stat_total'), value: summary.total, color: 'var(--text-2)' },
                { key: 'pending', label: t('changes.stat_pending'), value: summary.pending, color: 'var(--warning)' },
                { key: 'approved', label: t('changes.stat_approved'), value: summary.approved, color: 'var(--success)' },
                { key: 'cost', label: t('changes.extra_cost'), value: fmtCurrency(summary.total_cost_impact), color: 'var(--danger)' },
                { key: 'days', label: t('changes.extra_days'), value: t('changes.plus_days', { n: summary.total_schedule_impact ?? 0 }), color: 'var(--danger)' },
              ].map(({ key, label, value, color }) => (
                <div key={key} className="chg-stat">
                  <div className="chg-stat__value" style={tone(color)}>{value}</div>
                  <div className="chg-stat__label">{label}</div>
                </div>
              ))}
            </div>
          )}

          {!selectedProject ? (
            <EmptyState icon="📋" title={t('changes.selecciona_un_proyecto')} description={t('changes.select_project_desc')} />
          ) : isLoading ? <Spinner /> : crs.length === 0 ? (
            <EmptyState icon="✅" title={t('changes.no_changes')} description={t('changes.no_crs_desc')} />
          ) : (
            <div data-export-table="changes-list" className="u-stack-10">
              {crs.map((cr) => {
                const impact = (cr.impact && IMPACT_CFG[cr.impact]) || IMPACT_CFG.medium
                const borde = alpha((STATUS_CFG[cr.status ?? '']?.color ?? 'var(--surface-4)'), '30')
                return (
                  <div key={cr.id} className="chg-cr" style={{ '--chg-border': borde } as CSSProperties}>
                    <div className="chg-cr__row">
                      <div className="u-flex1">
                        <div className="chg-cr__head">
                          <span className="u-text2-mono-xs">{cr.code}</span>
                          <span className="u-md-700">{cr.title}</span>
                        </div>
                        <p className="chg-cr__desc">{cr.description}</p>
                        <div className="chg-facts chg-facts--wide">
                          <span className="chg-tone" style={tone(impact.color)}><span aria-hidden="true">⚡ </span>{t(impact.labelKey)}</span>
                          {cr.cost_impact && <span className="u-danger"><span aria-hidden="true">💰 </span>+{fmtCurrency(cr.cost_impact)}</span>}
                          {cr.schedule_impact_days && <span className="u-warning"><span aria-hidden="true">📅 </span>{t('changes.plus_days', { n: cr.schedule_impact_days })}</span>}
                          {cr.requester_name && <span className="u-text2"><span aria-hidden="true">👤 </span>{cr.requester_name}</span>}
                        </div>
                        {cr.resolution_notes && <div className="chg-cr__notes"><span aria-hidden="true">💬 </span>{cr.resolution_notes}</div>}
                      </div>
                      <div className="chg-cr__side">
                        <StatusBadge status={cr.status} />
                        <div className="u-row-6">
                          {cr.status === 'draft' && <>
                            <button type="button" onClick={() => setEditing(cr)} className="chg-icon-btn" aria-label={t('changes.edit_aria', { code: cr.code ?? '' })} title={t('changes.edit_aria', { code: cr.code ?? '' })}><span aria-hidden="true">✏️</span></button>
                            <Button size="sm" onClick={() => submit(cr)} loading={saving}>{t('changes.send')}</Button>
                          </>}
                          {['submitted', 'under_review'].includes(cr.status ?? '') && hasRole('admin', 'pm') && (
                            <Button size="sm" onClick={() => setReviewing(cr)}>{t('changes.review')}</Button>
                          )}
                          {cr.status === 'approved' && (
                            <Button size="sm" onClick={() => implement(cr)}>✓ {t('changes.implement')}</Button>
                          )}
                          <button type="button" onClick={() => { openConfirmGlobal({ message: t('changes.delete_confirm'), onConfirm: () => del(cr), danger: true }) }} className="chg-icon-btn chg-icon-btn--danger" aria-label={t('changes.delete_aria', { code: cr.code ?? '' })} title={t('changes.delete_aria', { code: cr.code ?? '' })}><span aria-hidden="true">🗑</span></button>
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
          <EmptyState icon="✅" title={t('changes.sin_pendientes')} description={t('changes.no_pending_desc')} />
        ) : (
          <div data-export-table="changes-list" className="u-stack-10">
            {allPending.map((cr) => {
              const impact = (cr.impact && IMPACT_CFG[cr.impact]) || IMPACT_CFG.medium
              return (
                <div key={cr.id} className="chg-cr chg-cr--pending">
                  <div className="chg-cr__row">
                    <div className="u-flex1">
                      <div className="u-text2-xs-mb4">{cr.project_code} · {cr.project_name} · {cr.code}</div>
                      <div className="chg-cr__title">{cr.title}</div>
                      <div className="chg-facts chg-facts--wide">
                        <span className="chg-tone" style={tone(impact.color)}>{t(impact.labelKey)}</span>
                        {cr.cost_impact && <span className="u-danger">+{fmtCurrency(cr.cost_impact)}</span>}
                        {cr.schedule_impact_days && <span className="u-warning">{t('changes.plus_days', { n: cr.schedule_impact_days })}</span>}
                      </div>
                    </div>
                    <Button size="sm" onClick={() => { setSelectedProject(cr.project_id); setReviewing(cr); setTab('project') }}>{t('changes.review')}</Button>
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
