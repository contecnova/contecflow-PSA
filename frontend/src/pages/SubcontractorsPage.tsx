import { useState, useId } from 'react'
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent } from 'react'
import { extractErr, fmtDate, fmtHours, fmtNumber, simboloMoneda } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { enterpriseSubsApi, subcontractorsApi, projectsApi, skillsApi } from '../services/api'
import type { ProjectListItem } from '../services/api/projects'
import type { SkillDelCatalogo, SubAsignacion, SubFactura, SubParteDeHoras, SubTrabajador, Subcontratista } from '../services/api/tipos-alm'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Users } from 'lucide-react'
import { Button, Modal, EmptyState, useSort, SortableTH, ViewToggle, Tabs, Table } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { STALE_5_MIN_MS } from '../constants/timings'
import DateInput from '../components/ui/DateInput'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './SubcontractorsPage.css'
/** Estados de factura de subcontratista y niveles de skill: su color sale de la clase. */
const ESTADOS_FACTURA = ['received', 'approved', 'paid', 'rejected']
const NIVELES = ['basic', 'intermediate', 'advanced', 'expert']
const claseNivel = (nivel: string) => NIVELES.includes(nivel) ? ` sub-skill--${nivel}` : ''

// Respuestas de /enterprise/subcontractors* y /skills/catalog: services/api/tipos-alm.
type Skill = SkillDelCatalogo
type Worker = SubTrabajador
type Sub = Subcontratista
type Timelog = SubParteDeHoras
type Invoice = SubFactura
type CredsInfo = { username?: string; password?: string }

function onKeyboardActivate(event: ReactKeyboardEvent, action: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

// ── Worker Modal ──────────────────────────────────────────────────────────────
function WorkerModal({ subId, worker, onClose, onSaved }: { subId: string; worker?: Worker; onClose: () => void; onSaved?: () => void }) {
  const idCampo = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const { currency: defaultCurrency } = useOrgSettings()
  const isEdit = !!worker
  const [form, setForm] = useState({
    name: worker?.name || '',
    role: worker?.role || '',
    email: worker?.email || '',
    phone: worker?.phone || '',
    cost_rate: worker?.cost_rate || '',
    sell_rate: worker?.sell_rate || '',
    currency: worker?.currency || defaultCurrency,
    available_from: worker?.available_from || '',
    available_until: worker?.available_until || '',
    notes: worker?.notes || '',
  })
  const [skillForm, setSkillForm] = useState({ skill_id: '', level: 'intermediate', years_experience: '', certified: false, cert_name: '' })
  const [showSkillForm, setShowSkillForm] = useState(false)

  const t = useAppT()
  const etiquetaNivel = (nivel: string) => NIVELES.includes(nivel) ? t(`subcontractors.nivel_${nivel}`) : nivel
  const { data: skillCatalog = [] } = useQuery<Skill[]>({
    queryKey: ['skills-catalog'],
    queryFn: () => skillsApi.catalog().then(r => r.data),
    staleTime: STALE_5_MIN_MS,
  })

  const [credsInfo, setCredsInfo] = useState<CredsInfo | null>(null)

  const { mutate: save, isPending: saving } = useMutation({
    // El alta devuelve además la contraseña temporal del usuario creado (SubTrabajadorCreado).
    mutationFn: async (d: Record<string, unknown>): Promise<SubTrabajador & { temp_password?: string }> => isEdit
      ? (await enterpriseSubsApi.updateWorker(worker!.id, d)).data
      : (await enterpriseSubsApi.createWorker(subId, d)).data,
    onSuccess: (creado) => {
      qc.invalidateQueries({ queryKey: ['sub-workers', subId] })
      qc.invalidateQueries({ queryKey: ['users'] })
      onSaved?.()
      if (!isEdit && creado?.login_username) {
        setCredsInfo({ username: creado.login_username, password: creado.temp_password })
      } else {
        onClose()
        toast.success(isEdit ? t('subcontractors.trabajador_actualizado') : t('subcontractors.trabajador_anadido'))
      }
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: addSkill, isPending: addingSkill } = useMutation({
    mutationFn: (d: Record<string, unknown>) => enterpriseSubsApi.addWorkerSkill(worker?.id, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sub-workers', subId] }); setShowSkillForm(false); setSkillForm({ skill_id: '', level: 'intermediate', years_experience: '', certified: false, cert_name: '' }); toast.success(t('subcontractors.skill_anadida')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: removeSkill } = useMutation({
    mutationFn: (skill_id: string) => enterpriseSubsApi.removeWorkerSkill(worker?.id, skill_id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sub-workers', subId] }); toast.success(t('subcontractors.skill_eliminada')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  // group skill catalog by category
  const byCategory: Record<string, Skill[]> = skillCatalog.reduce((acc: Record<string, Skill[]>, s: Skill) => {
    const cat = s.category || 'other'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(s)
    return acc
  }, {} as Record<string, Skill[]>)

  if (credsInfo) {
    return (
      <Modal open title={t('subcontractors.person_added')} onClose={onClose} width={480}>
        <div className="sub-creds">
          <div className="sub-creds-icon" aria-hidden="true">🎉</div>
          <div className="sub-creds-title">{t('subcontractors.person_added')}</div>
          <div className="u-text2-base-mb20">{t('subcontractors.person_created_user')}</div>
          <div className="sub-creds-box">
            <div className="u-mb-10">
              <div className="sub-creds-label">{t('subcontractors.username')}</div>
              <div className="sub-creds-value">{credsInfo.username}</div>
            </div>
            <div>
              <div className="sub-creds-label">{t('subcontractors.temp_password')}</div>
              <div className="sub-creds-value sub-creds-value--warning">{credsInfo.password}</div>
            </div>
          </div>
          <div className="sub-creds-warning">
            {t('subcontractors.creds_warning')}
          </div>
          <Button onClick={onClose} className="sub-full">{t('subcontractors.understood')}</Button>
        </div>
      </Modal>
    )
  }

  return (
    <Modal open title={isEdit ? `${t('subcontractors.edit_person', { name: worker?.name })}` : t('subcontractors.new_person')} onClose={onClose} width={560}>
      <div className="sub-form-grid">
        <div className="u-col-full">
          <label id={`${idCampo}-1-et`} htmlFor={`${idCampo}-1`} className="sub-label">{t('subcontractors.placeholder_name')} *</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-1-et`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="sub-input" placeholder={t('subcontractors.placeholder_name')} />
        </div>
        <div>
          <label id={`${idCampo}-2-et`} htmlFor={`${idCampo}-2`} className="sub-label">{t('subcontractors.placeholder_role')}</label>
          <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-2-et`} value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} className="sub-input" placeholder={t('subcontractors.placeholder_role')} />
        </div>
        <div>
          <label id={`${idCampo}-3-et`} htmlFor={`${idCampo}-3`} className="sub-label">{t('subcontractors.email')}</label>
          <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-3-et`} type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} className="sub-input" />
        </div>
        <div>
          <label id={`${idCampo}-4-et`} htmlFor={`${idCampo}-4`} className="sub-label">{t('subcontractors.tarifa_coste_moneda', { moneda: simboloMoneda(form.currency || defaultCurrency) })}</label>
          <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-4-et`} type="number" value={form.cost_rate} onChange={e => setForm(f => ({ ...f, cost_rate: e.target.value }))} className="sub-input" min="0" step="0.5" />
        </div>
        <div>
          <label id={`${idCampo}-5-et`} htmlFor={`${idCampo}-5`} className="sub-label">{t('subcontractors.tarifa_venta_moneda', { moneda: simboloMoneda(form.currency || defaultCurrency) })}</label>
          <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-5-et`} type="number" value={form.sell_rate} onChange={e => setForm(f => ({ ...f, sell_rate: e.target.value }))} className="sub-input" min="0" step="0.5" />
        </div>
        <div>
          <label id={`${idCampo}-6-et`} htmlFor={`${idCampo}-6`} className="sub-label">{t('subcontractors.available_from')}</label>
          <DateInput id={`${idCampo}-6`} aria-labelledby={`${idCampo}-6-et`} value={form.available_from} onChange={e => setForm(f => ({ ...f, available_from: e.target.value }))} className="sub-input" />
        </div>
        <div>
          <label id={`${idCampo}-7-et`} htmlFor={`${idCampo}-7`} className="sub-label">{t('subcontractors.available_until')}</label>
          <DateInput id={`${idCampo}-7`} aria-labelledby={`${idCampo}-7-et`} value={form.available_until} onChange={e => setForm(f => ({ ...f, available_until: e.target.value }))} className="sub-input" />
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-8-et`} htmlFor={`${idCampo}-8`} className="sub-label">{t('subcontractors.notes')}</label>
          <textarea id={`${idCampo}-8`} aria-labelledby={`${idCampo}-8-et`} value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} className="sub-input sub-textarea sub-textarea--sm" />
        </div>
      </div>

      {/* Skills section — only shown in edit mode */}
      {isEdit && (
        <div className="sub-skills-block">
          <div className="sub-skills-head">
            <div className="u-text1-sm-600">{t('subcontractors.skills')}</div>
            <button type="button" className="sub-btn-accent-xs" aria-expanded={showSkillForm} onClick={() => setShowSkillForm(s => !s)}>
              {showSkillForm ? t('subcontractors.cancel_skill') : t('subcontractors.add_skill')}
            </button>
          </div>

          {/* Existing skills */}
          <div className={`sub-skills${showSkillForm ? ' sub-skills--open' : ''}`}>
            {(worker?.skills || []).map(s => (
              <span key={s.skill_id} className={`sub-skill${claseNivel(s.level)}`}>
                {s.skill_name}
                <span className="sub-skill-level">({etiquetaNivel(s.level)})</span>
                {s.certified && <span title={t('subcontractors.certified')} role="img" aria-label={t('subcontractors.certified')}>🏆</span>}
                <button type="button" className="sub-skill-remove" onClick={() => removeSkill(s.skill_id)}
                  aria-label={t('subcontractors.quitar_skill', { skill: s.skill_name })} title={t('subcontractors.quitar_skill', { skill: s.skill_name })}>✕</button>
              </span>
            ))}
            {(worker.skills || []).length === 0 && !showSkillForm && (
              <span className="u-text3-sm">{t('subcontractors.no_skills')}</span>
            )}
          </div>

          {/* Add skill form */}
          {showSkillForm && (
            <div className="sub-skill-form">
              <div className="u-col-full">
                <label id={`${idCampo}-9-et`} htmlFor={`${idCampo}-9`} className="sub-label">{t('subcontractors.add_skill')} *</label>
                <select id={`${idCampo}-9`} aria-labelledby={`${idCampo}-9-et`} value={skillForm.skill_id} onChange={e => setSkillForm(f => ({ ...f, skill_id: e.target.value }))} className="sub-input">
                  <option value="">{t('subcontractors.select_skill')}</option>
                  {Object.entries(byCategory).map(([cat, skills]) => (
                    <optgroup key={cat} label={cat.charAt(0).toUpperCase() + cat.slice(1)}>
                      {skills.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </optgroup>
                  ))}
                </select>
              </div>
              <div>
                <label id={`${idCampo}-10-et`} htmlFor={`${idCampo}-10`} className="sub-label">{t('subcontractors.level')}</label>
                <select id={`${idCampo}-10`} aria-labelledby={`${idCampo}-10-et`} value={skillForm.level} onChange={e => setSkillForm(f => ({ ...f, level: e.target.value }))} className="sub-input">
                  {NIVELES.map(l => <option key={l} value={l}>{etiquetaNivel(l)}</option>)}
                </select>
              </div>
              <div>
                <label id={`${idCampo}-11-et`} htmlFor={`${idCampo}-11`} className="sub-label">{t('subcontractors.years_experience')}</label>
                <input id={`${idCampo}-11`} aria-labelledby={`${idCampo}-11-et`} type="number" value={skillForm.years_experience} onChange={e => setSkillForm(f => ({ ...f, years_experience: e.target.value }))} className="sub-input" min="0" step="0.5" />
              </div>
              <div className="sub-check-row">
                <input type="checkbox" id={`${idCampo}-cert`} aria-labelledby={`${idCampo}-cert-et`} checked={skillForm.certified} onChange={e => setSkillForm(f => ({ ...f, certified: e.target.checked }))} />
                <label id={`${idCampo}-cert-et`} htmlFor={`${idCampo}-cert`} className="sub-check-label">{t('subcontractors.certified')}</label>
                {skillForm.certified && (
                  <input aria-label={t('subcontractors.placeholder_cert')} value={skillForm.cert_name} onChange={e => setSkillForm(f => ({ ...f, cert_name: e.target.value }))} className="sub-input sub-input--flex" placeholder={t('subcontractors.placeholder_cert')} />
                )}
              </div>
              <div className="sub-row-end-full">
                <Button size="sm" onClick={() => addSkill(skillForm)} loading={addingSkill} disabled={!skillForm.skill_id || addingSkill}>{t('subcontractors.assign_skill')}</Button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="u-actions-8">
        <button type="button" onClick={onClose} className="u-btn-outline-sm">
          {isEdit ? t('subcontractors.close') : t('subcontractors.cancel')}
        </button>
        <Button onClick={() => save(form)} loading={saving} disabled={!form.name || saving}>{isEdit ? t('subcontractors.save_changes') : t('subcontractors.add_person')}</Button>
      </div>
    </Modal>
  )
}

// ── Workers Panel ─────────────────────────────────────────────────────────────
function WorkersPanel({ subId }: { subId: string }) {
  const toast = useToast()
  const qc = useQueryClient()
  const t = useAppT()
  const fmtMoneda = useFormatoMoneda()
  const [showCreate, setShowCreate] = useState(false)
  const [editWorker, setEditWorker] = useState<Worker | null>(null)
  const [deactivateTarget, setDeactivateTarget] = useState<Worker | null>(null)

  const { data: workers = [], isLoading } = useQuery<Worker[]>({
    queryKey: ['sub-workers', subId],
    queryFn: () => enterpriseSubsApi.workers(subId).then(r => r.data),
  })

  const { mutate: deactivate } = useMutation({
    mutationFn: (id: string) => enterpriseSubsApi.deleteWorker(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sub-workers', subId] })
      qc.invalidateQueries({ queryKey: ['users'] })
      toast.success(t('subcontractors.trabajador_desactivado'))
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (isLoading) return <div className="sub-loading">{t('common.loading')}</div>

  return (
    <div>
      <div className="sub-toolbar-end">
        <Button size="sm" onClick={() => setShowCreate(true)}>{t('subcontractors.add_person_btn')}</Button>
      </div>

      {workers.length === 0 ? (
        <EmptyState icon="👤" title={t('subcontractors.empty_people_title')} description={t('subcontractors.empty_people_desc')} />
      ) : (
        <div className="u-stack-10">
          {workers.map(w => (
            <div key={w.id} className="sub-panel sub-panel--item">
              <div className="sub-worker">
                <div className="u-flex1-min0">
                  <div className="sub-worker-head">
                    <div className="u-md-700">{w.name}</div>
                    {w.role && <span className="sub-role">{w.role}</span>}
                    {!w.is_active && <span className="sub-tag-inactive">{t('subcontractors.inactivo')}</span>}
                  </div>
                  {w.email && <div className="u-text2-xs-mb4"><span aria-hidden="true">📧 </span>{w.email}</div>}
                  {(!!w.cost_rate || !!w.sell_rate) && (
                    <div className="sub-rates">
                      {!!w.cost_rate && t('subcontractors.coste_por_hora', { importe: fmtMoneda(w.cost_rate, { moneda: w.currency }) })}
                      {!!w.cost_rate && !!w.sell_rate && ' · '}
                      {!!w.sell_rate && t('subcontractors.venta_por_hora', { importe: fmtMoneda(w.sell_rate, { moneda: w.currency }) })}
                    </div>
                  )}
                  {/* Skills */}
                  <div className="sub-skills sub-skills--compact">
                    {(w.skills || []).map(s => (
                      <span key={s.skill_id} className={`sub-skill sub-skill--chip${claseNivel(s.level)}`}>
                        {s.skill_name}
                        {s.certified && ' 🏆'}
                      </span>
                    ))}
                    {(w.skills || []).length === 0 && <span className="sub-no-skills">{t('subcontractors.no_skills_short')}</span>}
                  </div>
                </div>
                <div className="sub-worker-actions">
                  {(w.available_from || w.available_until) && (
                    <div className="sub-availability">
                      {w.available_from && <div>{t('subcontractors.desde_fecha', { fecha: fmtDate(w.available_from) })}</div>}
                      {w.available_until && <div>{t('subcontractors.hasta_fecha', { fecha: fmtDate(w.available_until) })}</div>}
                    </div>
                  )}
                    <button type="button" className="sub-btn-xs" onClick={() => setEditWorker(w)}>
                      {t('subcontractors.edit')}
                    </button>
                  {w.is_active && (
                    <button type="button" className="sub-btn-xs sub-btn-xs--danger" onClick={() => setDeactivateTarget(w)}
                      aria-label={t('subcontractors.desactivar_a', { name: w.name })} title={t('subcontractors.desactivar_a', { name: w.name })}>
                      🗑
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && <WorkerModal subId={subId} onClose={() => setShowCreate(false)} onSaved={() => qc.invalidateQueries({ queryKey: ['subcontractors'] })} />}
      {editWorker && <WorkerModal subId={subId} worker={editWorker} onClose={() => setEditWorker(null)} onSaved={() => qc.invalidateQueries({ queryKey: ['subcontractors'] })} />}
      {deactivateTarget && (
        <Modal open title={t('subcontractors.desactivar_trabajador')} onClose={() => setDeactivateTarget(null)} width={380}>
          <p className="sub-confirm-text">
            {t('subcontractors.se_desactivara_a')} <strong>{deactivateTarget.name}</strong> {t('subcontractors.y_no_podra_iniciar_sesion_ni_ser')}
          </p>
          <div className="u-actions-8">
            <Button variant="ghost" onClick={() => setDeactivateTarget(null)}>{t('subcontractors.cancel')}</Button>
            <Button variant="danger" onClick={() => { deactivate(deactivateTarget.id); setDeactivateTarget(null) }}>{t('subcontractors.deactivate')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
function SubDetail({ sub, onBack }: { sub: Sub; onBack: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const t = useAppT()
  const [tab, setTab] = useState('workers')
  const [showTimelog, setShowTimelog] = useState(false)
  const [showInvoice, setShowInvoice] = useState(false)
  const [showAssign, setShowAssign] = useState(false)
  const [tlForm, setTlForm] = useState({ assignment_id: '', log_date: new Date().toISOString().slice(0,10), hours: 8, description: '', task_reference: '' })
  const [invForm, setInvForm] = useState({ invoice_number: '', issue_date: new Date().toISOString().slice(0,10), due_date: '', amount: '', tax_pct: 21, description: '' })
  const [asgForm, setAsgForm] = useState({ project_id: '', po_number: '', po_amount: '', hours_contracted: '', start_date: '', end_date: '', notes: '' })

  const { data: assignments = [] } = useQuery<SubAsignacion[]>({
    queryKey: ['sub-assignments', sub.id],
    queryFn: () => enterpriseSubsApi.assignments(sub.id).then(r => r.data),
  })
  const { data: timelogs = [] } = useQuery<Timelog[]>({
    queryKey: ['sub-timelogs', sub.id],
    queryFn: () => enterpriseSubsApi.timelogs(sub.id).then(r => r.data),
  })
  const { data: invoices = [] } = useQuery<Invoice[]>({
    queryKey: ['sub-invoices', sub.id],
    queryFn: () => enterpriseSubsApi.invoices(sub.id).then(r => r.data),
  })
  const { data: projects = [] } = useQuery<ProjectListItem[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => ((r.data as { items?: ProjectListItem[] })?.items ?? r.data ?? []).filter((p: ProjectListItem) => p.status === 'active')),
  })

  const { mutate: logHours, isPending: logging } = useMutation({
    mutationFn: (d: Record<string, unknown>) => enterpriseSubsApi.createTimelog(sub.id, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sub-timelogs', sub.id] }); setShowTimelog(false); toast.success(t('subcontractors.hours_logged')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: createInv, isPending: invoicing } = useMutation({
    mutationFn: (d: Record<string, unknown>) => enterpriseSubsApi.createInvoice(sub.id, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sub-invoices', sub.id] }); setShowInvoice(false); toast.success(t('subcontractors.invoice_logged')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: createAssign, isPending: assigning } = useMutation({
    mutationFn: (d: Record<string, unknown>) => enterpriseSubsApi.createAssignment(sub.id, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sub-assignments', sub.id] }); setShowAssign(false); toast.success(t('subcontractors.assignment_created')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: updateInvStatus } = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => enterpriseSubsApi.updateInvoice(sub.id, id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sub-invoices', sub.id] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const totalHours    = timelogs.reduce((s: number, l: Timelog) => s + l.hours, 0)
  const totalCost     = timelogs.reduce((s: number, l: Timelog) => s + (l.cost_amount || 0), 0)
  const pendingAmount = invoices.filter((i: Invoice) => i.status === 'received').reduce((s: number, i: Invoice) => s + i.total, 0)

  return (
    <div>
      <div className="sub-detail-head">
        <button type="button" className="sub-back" onClick={onBack}>{t('subcontractors.volver')}</button>
        <div className="u-flex1">
          <div className="sub-detail-title">{sub.name} <span className="sub-detail-code">{sub.code}</span></div>
          {sub.company && <div className="u-text2-sm">{sub.company} · {sub.email}</div>}
        </div>
      </div>

      {/* KPIs */}
      <div className="sub-kpis">
        {[
          { label: t('subcontractors.kpi_personas'), value: sub.worker_count ?? '—', color: 'purple' },
          { label: t('subcontractors.kpi_asignaciones'), value: assignments.length, color: 'accent' },
          { label: t('subcontractors.hours_logged'), value: `${fmtNumber(totalHours, 1)}h`, color: 'success' },
          { label: t('subcontractors.kpi_coste_acumulado'), value: fmtMoneda(totalCost), color: 'warning' },
          { label: t('subcontractors.kpi_facturas_pendientes'), value: fmtMoneda(pendingAmount), color: pendingAmount > 0 ? 'danger' : '' },
        ].map(k => (
          <div key={k.label} className="sub-kpi">
            <div className={`sub-kpi-value${k.color ? ` sub-kpi-value--${k.color}` : ''}`}>{k.value}</div>
            <div className="sub-kpi-label">{k.label}</div>
          </div>
        ))}
      </div>

      <Tabs
        items={[
          { id: 'workers',     label: t('subcontractors.kpi_personas') },
          { id: 'assignments', label: t('subcontractors.kpi_asignaciones'), count: assignments.length || undefined },
          { id: 'timelogs',    label: t('subcontractors.tab_horas'),        count: timelogs.length || undefined },
          { id: 'invoices',    label: t('subcontractors.tab_facturas'),     count: invoices.length || undefined },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel={t('subcontractors.secciones_del_subcontratista')}
      />

      {/* Personas (Workers) */}
      {tab === 'workers' && <WorkersPanel subId={sub.id} />}

      {/* Asignaciones */}
      {tab === 'assignments' && (
        <div>
          <div className="sub-toolbar-end">
            <Button size="sm" onClick={() => setShowAssign(true)}>{t('subcontractors.nueva_asignacion')}</Button>
          </div>
          {assignments.length === 0 ? (
            <EmptyState icon="📋" title={t('subcontractors.empty_assignments_title')} description={t('subcontractors.empty_assignments_desc')} />
          ) : assignments.map(a => (
            <div key={a.id} className="sub-panel sub-panel--item sub-panel--mb8">
              <div className="u-row-between">
                <div>
                  <div className="u-base-700">{a.project_code} — {a.project_name}</div>
                  <div className="u-text2-sm-mt2">
                    {[
                      a.po_number && t('subcontractors.po_numero', { po: a.po_number }),
                      !!a.po_amount && t('subcontractors.techo_importe', { importe: fmtMoneda(a.po_amount) }),
                      !!a.hours_contracted && t('subcontractors.horas_contratadas_n', { horas: fmtNumber(a.hours_contracted, 1) }),
                    ].filter(Boolean).join(' · ')}
                  </div>
                  {!!a.hours_contracted && (
                    <div className="sub-progress-wrap">
                      <div className="sub-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.min(a.budget_used_pct || 0, 100)}
                        aria-label={t('subcontractors.consumo_de_horas')}>
                        <div className={`sub-progress-bar${(a.budget_used_pct || 0) > 90 ? ' sub-progress-bar--over' : ''}`}
                          style={{ '--pct': `${Math.min(a.budget_used_pct || 0, 100)}%` } as CSSProperties} />
                      </div>
                      <div className="sub-progress-text">{fmtHours(a.hours_logged)} / {fmtHours(a.hours_contracted)} ({fmtNumber(a.budget_used_pct || 0, 1)}%)</div>
                    </div>
                  )}
                </div>
                <Button size="sm" onClick={() => { setTlForm(f => ({...f, assignment_id: a.id})); setShowTimelog(true) }}>{t('subcontractors.registrar_horas_btn')}</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Timelogs */}
      {tab === 'timelogs' && (
        <div>
          <div className="sub-toolbar-end">
            <Button size="sm" onClick={() => setShowTimelog(true)}>{t('subcontractors.registrar_horas_btn')}</Button>
          </div>
          {timelogs.length === 0 ? (
            <EmptyState icon="🕐" title={t('subcontractors.empty_hours_title')} description={t('subcontractors.empty_hours_desc')} />
          ) : (
            <div className="sub-panel sub-panel--clip">
              <Table
                data={timelogs}
                columns={[
                  { key: 'log_date', label: t('subcontractors.col_fecha'), render: (_v, l) => <span className="u-text2-sm">{fmtDate(l.log_date)}</span> },
                  { key: 'hours', label: t('subcontractors.tab_horas'), render: (_v, l) => <span className="sub-hours">{fmtHours(l.hours)}</span> },
                  { key: 'description', label: t('subcontractors.descripcion'), render: (_v, l) => <span className="sub-ellipsis" title={l.description || undefined}>{l.description || '—'}</span> },
                  { key: 'task_reference', label: t('subcontractors.col_ref_tarea'), render: (_v, l) => <span className="u-text2-xs">{l.task_reference || '—'}</span> },
                  { key: 'cost_amount', label: t('subcontractors.col_coste'), render: (_v, l) => (
                    <span className="sub-money-warning">
                      {l.cost_amount ? fmtMoneda(l.cost_amount) : '—'}
                    </span>
                  ) },
                  { key: 'project_name', label: t('subcontractors.col_proyecto'), render: (_v, l) => <span className="u-text2-xs">{l.project_name || '—'}</span> },
                ]}
              />
            </div>
          )}
        </div>
      )}

      {/* Facturas */}
      {tab === 'invoices' && (
        <div>
          <div className="sub-toolbar-end">
            <Button size="sm" onClick={() => setShowInvoice(true)}>{t('subcontractors.registrar_factura_btn')}</Button>
          </div>
          {invoices.length === 0 ? (
            <EmptyState icon="🧾" title={t('subcontractors.empty_invoices_title')} description={t('subcontractors.empty_invoices_desc')} />
          ) : (
            <div className="sub-panel sub-panel--clip u-scroll-x">
              <table className="u-table">
                <thead>
                  <tr className="u-border-b">
                    {[t('subcontractors.col_n_factura'), t('subcontractors.col_fecha'), t('subcontractors.col_importe'), t('subcontractors.col_total_iva'), t('subcontractors.col_estado'), t('subcontractors.col_acciones')].map(h => (
                      <th key={h} scope="col" className="sub-th">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {invoices.map(inv => (
                    <tr key={inv.id} className="sub-tr">
                      <td className="sub-td sub-td--strong">{inv.invoice_number}</td>
                      <td className="sub-td sub-td--muted">{fmtDate(inv.issue_date)}</td>
                      <td className="sub-td sub-td--mono">{fmtMoneda(inv.amount)}</td>
                      <td className="sub-td sub-td--total">{fmtMoneda(inv.total)}</td>
                      <td className="sub-td">
                        <span className={`sub-inv-status${ESTADOS_FACTURA.includes(inv.status || '') ? ` sub-inv-status--${inv.status}` : ''}`}>
                          {ESTADOS_FACTURA.includes(inv.status || '') ? t(`subcontractors.factura_${inv.status}`) : inv.status}
                        </span>
                      </td>
                      <td className="sub-td">
                        <div className="u-row-6">
                          {inv.status === 'received' && (
                            <button type="button" className="sub-btn-pill-xs" onClick={() => updateInvStatus({ id: inv.id, status: 'approved' })}>{t('subcontractors.approve')}</button>
                          )}
                          {inv.status === 'approved' && (
                            <button type="button" className="sub-btn-pill-xs sub-btn-pill-xs--success" onClick={() => updateInvStatus({ id: inv.id, status: 'paid' })}>{t('subcontractors.marcar_pagada')}</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Modal registrar horas */}
      {showTimelog && (
        <Modal open title={t('subcontractors.registrar_horas')} onClose={() => setShowTimelog(false)} width={480}>
          <div className="sub-form-grid">
            <div>
              <label id={`${idCampo}-1-et`} htmlFor={`${idCampo}-1`} className="sub-label">{t('subcontractors.asignacion')}</label>
              <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-1-et`} value={tlForm.assignment_id} onChange={e => setTlForm(f=>({...f,assignment_id:e.target.value}))} className="sub-input">
                <option value="">{t('subcontractors.sin_asignacion')}</option>
                {assignments.map(a => <option key={a.id} value={a.id}>{a.project_code} — {a.project_name}</option>)}
              </select>
            </div>
            <div>
              <label id={`${idCampo}-2-et`} htmlFor={`${idCampo}-2`} className="sub-label">{t('subcontractors.col_fecha')}</label>
              <DateInput id={`${idCampo}-2`} aria-labelledby={`${idCampo}-2-et`} value={tlForm.log_date} onChange={e => setTlForm(f=>({...f,log_date:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-3-et`} htmlFor={`${idCampo}-3`} className="sub-label">{t('subcontractors.horas_obligatorio')}</label>
              <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-3-et`} type="number" value={tlForm.hours} onChange={e => setTlForm(f=>({...f,hours:+e.target.value}))} className="sub-input" min="0.5" step="0.5" />
            </div>
            <div>
              <label id={`${idCampo}-a599-et`} htmlFor={`${idCampo}-a599`} className="sub-label">{t('subcontractors.referencia_de_tarea')}</label>
              <input id={`${idCampo}-a599`} aria-labelledby={`${idCampo}-a599-et`} value={tlForm.task_reference} onChange={e => setTlForm(f=>({...f,task_reference:e.target.value}))} className="sub-input" placeholder={t('subcontractors.referencia_de_tarea')} />
            </div>
            <div className="u-col-full">
              <label id={`${idCampo}-tl-desc-et`} htmlFor={`${idCampo}-tl-desc`} className="sub-label">{t('subcontractors.descripcion')}</label>
              <input id={`${idCampo}-tl-desc`} aria-labelledby={`${idCampo}-tl-desc-et`} value={tlForm.description} onChange={e => setTlForm(f=>({...f,description:e.target.value}))} className="sub-input" placeholder={t('subcontractors.descripcion_del_parte')} />
            </div>
          </div>
          <div className="u-actions-8">
            <button type="button" onClick={() => setShowTimelog(false)} className="u-btn-outline-sm">{t('common.cancel')}</button>
            <Button onClick={() => logHours(tlForm)} loading={logging} disabled={!tlForm.hours || logging}>{t('subcontractors.registrar_horas')}</Button>
          </div>
        </Modal>
      )}

      {/* Modal registrar factura */}
      {showInvoice && (
        <Modal open title={t('subcontractors.registrar_factura')} onClose={() => setShowInvoice(false)} width={480}>
          <div className="sub-form-grid">
            <div>
              <label id={`${idCampo}-a619-et`} htmlFor={`${idCampo}-a619`} className="sub-label">{t('subcontractors.n_factura_obligatorio')}</label>
              <input id={`${idCampo}-a619`} aria-labelledby={`${idCampo}-a619-et`} value={invForm.invoice_number} onChange={e => setInvForm(f=>({...f,invoice_number:e.target.value}))} className="sub-input" placeholder={t('subcontractors.numero_de_factura')} />
            </div>
            <div>
              <label id={`${idCampo}-4-et`} htmlFor={`${idCampo}-4`} className="sub-label">{t('subcontractors.fecha_emision')}</label>
              <DateInput id={`${idCampo}-4`} aria-labelledby={`${idCampo}-4-et`} value={invForm.issue_date} onChange={e => setInvForm(f=>({...f,issue_date:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-5-et`} htmlFor={`${idCampo}-5`} className="sub-label">{t('subcontractors.importe_base_moneda', { moneda: fmtMoneda.simbolo })}</label>
              <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-5-et`} type="number" value={invForm.amount} onChange={e => setInvForm(f=>({...f,amount:e.target.value}))} className="sub-input" min="0" step="0.01" />
            </div>
            <div>
              <label id={`${idCampo}-6-et`} htmlFor={`${idCampo}-6`} className="sub-label">{t('subcontractors.iva_pct')}</label>
              <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-6-et`} type="number" value={invForm.tax_pct} onChange={e => setInvForm(f=>({...f,tax_pct:+e.target.value}))} className="sub-input" min="0" max="30" />
            </div>
            {invForm.amount && (
              <div className="sub-total-box">
                {t('subcontractors.total_con_iva')} <strong>{fmtMoneda(+invForm.amount * (1 + invForm.tax_pct/100))}</strong>
              </div>
            )}
            <div className="u-col-full">
              <label id={`${idCampo}-7-et`} htmlFor={`${idCampo}-7`} className="sub-label">{t('subcontractors.descripcion')}</label>
              <input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-7-et`} value={invForm.description} onChange={e => setInvForm(f=>({...f,description:e.target.value}))} className="sub-input" />
            </div>
          </div>
          <div className="u-actions-8">
            <button type="button" onClick={() => setShowInvoice(false)} className="u-btn-outline-sm">{t('common.cancel')}</button>
            <Button onClick={() => createInv(invForm)} loading={invoicing} disabled={!invForm.invoice_number || !invForm.amount || invoicing}>{t('subcontractors.registrar_factura')}</Button>
          </div>
        </Modal>
      )}

      {/* Modal nueva asignación */}
      {showAssign && (
        <Modal open title={t('subcontractors.nueva_asignacion_2')} onClose={() => setShowAssign(false)} width={500}>
          <div className="sub-form-grid">
            <div className="u-col-full">
              <label id={`${idCampo}-8-et`} htmlFor={`${idCampo}-8`} className="sub-label">{t('subcontractors.proyecto_obligatorio')}</label>
              <select id={`${idCampo}-8`} aria-labelledby={`${idCampo}-8-et`} value={asgForm.project_id} onChange={e => setAsgForm(f=>({...f,project_id:e.target.value}))} className="sub-input">
                <option value="">{t('subcontractors.seleccionar')}</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
            <div>
              <label id={`${idCampo}-a663-et`} htmlFor={`${idCampo}-a663`} className="sub-label">{t('subcontractors.n_pedido_po')}</label>
              <input id={`${idCampo}-a663`} aria-labelledby={`${idCampo}-a663-et`} value={asgForm.po_number} onChange={e => setAsgForm(f=>({...f,po_number:e.target.value}))} className="sub-input" placeholder={t('subcontractors.numero_de_pedido')} />
            </div>
            <div>
              <label id={`${idCampo}-9-et`} htmlFor={`${idCampo}-9`} className="sub-label">{t('subcontractors.techo_po_moneda', { moneda: fmtMoneda.simbolo })}</label>
              <input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-9-et`} type="number" value={asgForm.po_amount} onChange={e => setAsgForm(f=>({...f,po_amount:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-10-et`} htmlFor={`${idCampo}-10`} className="sub-label">{t('subcontractors.horas_contratadas')}</label>
              <input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-10-et`} type="number" value={asgForm.hours_contracted} onChange={e => setAsgForm(f=>({...f,hours_contracted:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-11-et`} htmlFor={`${idCampo}-11`} className="sub-label">{t('subcontractors.fecha_inicio')}</label>
              <DateInput id={`${idCampo}-11`} aria-labelledby={`${idCampo}-11-et`} value={asgForm.start_date} onChange={e => setAsgForm(f=>({...f,start_date:e.target.value}))} className="sub-input" />
            </div>
          </div>
          <div className="u-actions-8">
            <button type="button" onClick={() => setShowAssign(false)} className="u-btn-outline-sm">{t('common.cancel')}</button>
            <Button onClick={() => createAssign(asgForm)} loading={assigning} disabled={!asgForm.project_id || assigning}>{t('subcontractors.crear_asignacion')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function SubcontractorsPage() {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { currency, currencies: monedasDeLaEmpresa } = useOrgSettings()
  const [selected, setSelected] = useState<Sub | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', company: '', email: '', phone: '', country: 'España', currency: currency, vat_number: '', notes: '' })

  const { data: dashboard } = useQuery({
    queryKey: ['sub-dashboard'],
    queryFn: () => enterpriseSubsApi.dashboard().then(r => r.data),
  })
  const { data: subs = [], isLoading } = useQuery<Sub[]>({
    queryKey: ['subcontractors'],
    queryFn: () => subcontractorsApi.list().then(r => r.data),
  })

  const [showEdit, setShowEdit] = useState(false)
  const [editTarget, setEditTarget] = useState<Sub | null>(null)
  const [editForm, setEditForm] = useState<Record<string, string>>({})
  const [view, setView] = useState('grid')
  const { sort: subSort, setSort: setSubSort, sortedData: sortedSubs } = useSort<Sub>(subs, 'name')

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => subcontractorsApi.create(d),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['subcontractors'] })
      setShowCreate(false)
      setForm({ name: '', company: '', email: '', phone: '', country: 'España', currency: currency, vat_number: '', notes: '' })
      setSelected(res.data)
      toast.success(t('subcontractors.subcontratista_creado'))
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: update, isPending: updating } = useMutation({
    mutationFn: ({ id, ...d }: { id: string; [k: string]: unknown }) => subcontractorsApi.update(id, d),
    onSuccess: (_res) => {
      qc.invalidateQueries({ queryKey: ['subcontractors'] })
      setShowEdit(false)
      setEditTarget(null)
      toast.success(t('subcontractors.subcontratista_actualizado'))
    },
    onError: e => toast.error(extractErr(e, t('common.error_update'))),
  })
  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => subcontractorsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subcontractors'] })
      qc.invalidateQueries({ queryKey: ['sub-dashboard'] })
      toast.success(t('subcontractors.subcontratista_eliminado'))
    },
    onError: e => toast.error(extractErr(e, t('common.error_delete'))),
  })

  const abrirEdicion = (s: Sub) => {
    setEditTarget(s)
    setEditForm({ name: s.name||'', company: s.company||'', email: s.email||'', phone: s.phone||'', country: s.country||'España', currency: s.currency||currency, vat_number: s.vat_number||'', notes: s.notes||'' })
    setShowEdit(true)
  }
  const confirmarEliminar = (s: Sub) =>
    openConfirmGlobal({ message: t('subcontractors.confirmar_eliminar', { name: s.name }), onConfirm: () => remove(s.id), danger: true })

  if (selected) return <SubDetail sub={selected} onBack={() => setSelected(null)} />

  return (
    <PageShell>
      <PageHeader icon={<Users size={18} />} title={t('subcontractors.title')} subtitle={t('subcontractors.subtitle')} />

      {/* KPIs */}
      {dashboard && (
        <div className="sub-kpis sub-kpis--3">
          {[
            { label: t('subcontractors.kpi_activos'),             value: dashboard.total_active_subs,       color: 'accent' },
            { label: t('subcontractors.hours_logged'),            value: fmtHours(dashboard.total_hours_logged), color: 'success' },
            { label: t('subcontractors.kpi_facturas_pendientes'), value: dashboard.pending_invoices,       color: dashboard.pending_invoices > 0 ? 'warning' : '' },
          ].map(k => (
            <div key={k.label} className="sub-kpi">
              <div className={`sub-kpi-value${k.color ? ` sub-kpi-value--${k.color}` : ''}`}>{k.value}</div>
              <div className="sub-kpi-label">{k.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="sub-actions-bar">
        <ViewToggle view={view} onChange={setView} />
        <Button onClick={() => setShowCreate(true)}>{t('subcontractors.nuevo_subcontratista')}</Button>
      </div>

      {isLoading ? (
        <div className="sub-loading sub-loading--lg">{t('common.loading')}</div>
      ) : subs.length === 0 ? (
        <EmptyState icon="🤝" title={t('subcontractors.sin_subcontratistas')} description={t('subcontractors.vacio_descripcion')} />
      ) : view === 'grid' ? (
        <div className="sub-grid">
          {sortedSubs.map(s => (
            <div key={s.id} onClick={() => setSelected(s)}
              role="button"
              tabIndex={0}
              onKeyDown={e => { if (e.target === e.currentTarget) onKeyboardActivate(e, () => setSelected(s)) }}
              className="sub-card"
            >
              <div className="sub-card-head">
                <div>
                  <div className="u-md-700">{s.name}</div>
                  {s.company && <div className="u-text2-xs">{s.company}</div>}
                </div>
                <span className={`sub-state${s.is_active ? ' sub-state--active' : ''}`}>
                  {s.is_active ? t('subcontractors.activo') : t('subcontractors.inactivo')}
                </span>
              </div>
              {s.email && <div className="u-text2-xs"><span aria-hidden="true">📧 </span>{s.email}</div>}
              <div className="sub-card-meta">
                <span aria-hidden="true">👥 </span>{t((s.worker_count || 0) === 1 ? 'subcontractors.n_persona' : 'subcontractors.n_personas', { n: s.worker_count || 0 })} · {t((s.assignment_count || 0) === 1 ? 'subcontractors.n_asignacion' : 'subcontractors.n_asignaciones', { n: s.assignment_count || 0 })}
              </div>
              <div className="sub-card-actions">
                <button type="button" className="sub-card-btn" onClick={e => { e.stopPropagation(); abrirEdicion(s) }}>
                  ✏ {t('subcontractors.edit')}
                </button>
                <button type="button" className="sub-card-btn sub-card-btn--danger" onClick={e => { e.stopPropagation(); confirmarEliminar(s) }}>
                  🗑 {t('subcontractors.delete')}
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="ds-card ds-card--plano">
          <div className="sub-table-head">
            <SortableTH col="name" sort={subSort} onSort={setSubSort}>{t('subcontractors.col_empresa_nombre')}</SortableTH>
            <SortableTH col="code" sort={subSort} onSort={setSubSort}>{t('subcontractors.codigo')}</SortableTH>
            <SortableTH col="email" sort={subSort} onSort={setSubSort}>{t('subcontractors.email')}</SortableTH>
            <SortableTH col="worker_count" sort={subSort} onSort={setSubSort}>{t('subcontractors.kpi_personas')}</SortableTH>
            <SortableTH col="assignment_count" sort={subSort} onSort={setSubSort}>{t('subcontractors.kpi_asignaciones')}</SortableTH>
            <SortableTH col="is_active" sort={subSort} onSort={setSubSort}>{t('subcontractors.col_estado')}</SortableTH>
            <span>{t('subcontractors.col_acciones')}</span>
          </div>
          {sortedSubs.map(s => (
            <div key={s.id} className="sub-row"
              role="button"
              tabIndex={0}
              onKeyDown={e => { if (e.target === e.currentTarget) onKeyboardActivate(e, () => setSelected(s)) }}
              onClick={() => setSelected(s)}>
              <div>
                <div className="u-base-600">{s.name}</div>
                {s.company && <div className="u-text2-xs">{s.company}</div>}
              </div>
              <span className="u-text2-mono-xs">{s.code || '—'}</span>
              <span className="u-text2-sm">{s.email || '—'}</span>
              <span className="u-sm">{s.worker_count || 0}</span>
              <span className="u-sm">{s.assignment_count || 0}</span>
              <span className={`sub-state sub-state--table${s.is_active ? ' sub-state--active' : ''}`}>
                {s.is_active ? t('subcontractors.activo') : t('subcontractors.inactivo')}
              </span>
              <div className="sub-row-actions">
                <button type="button" className="sub-icon-btn" onClick={e => { e.stopPropagation(); abrirEdicion(s) }}
                  aria-label={t('subcontractors.editar_a', { name: s.name })} title={t('subcontractors.editar_a', { name: s.name })}>✏</button>
                <button type="button" className="sub-icon-btn sub-icon-btn--danger" onClick={e => { e.stopPropagation(); confirmarEliminar(s) }}
                  aria-label={t('subcontractors.eliminar_a', { name: s.name })} title={t('subcontractors.eliminar_a', { name: s.name })}>🗑</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <Modal open title={t('subcontractors.nuevo_subcontratista_2')} onClose={() => setShowCreate(false)} width={520}>
          <div className="sub-form-grid sub-form-grid--mb16">
            <div>
              <label id={`${idCampo}-nombre-et`} htmlFor={`${idCampo}-nombre`} className="sub-label">{t('subcontractors.nombre_razon_social')}</label>
              <input id={`${idCampo}-nombre`} aria-labelledby={`${idCampo}-nombre-et`} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} className="sub-input" placeholder={t('subcontractors.nombre_o_razon_social')} />
            </div>
            <div>
              <label id={`${idCampo}-1-et`} htmlFor={`${idCampo}-1`} className="sub-label">{t('subcontractors.empresa_si_es_persona_fisica')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-1-et`} value={form.company} onChange={e => setForm(f=>({...f,company:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-2-et`} htmlFor={`${idCampo}-2`} className="sub-label">{t('subcontractors.email')}</label>
              <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-2-et`} type="email" value={form.email} onChange={e => setForm(f=>({...f,email:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-3-et`} htmlFor={`${idCampo}-3`} className="sub-label">{t('subcontractors.telefono')}</label>
              <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-3-et`} value={form.phone} onChange={e => setForm(f=>({...f,phone:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-4-et`} htmlFor={`${idCampo}-4`} className="sub-label">{t('subcontractors.nif_vat')}</label>
              <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-4-et`} value={form.vat_number} onChange={e => setForm(f=>({...f,vat_number:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-5-et`} htmlFor={`${idCampo}-5`} className="sub-label">{t('subcontractors.moneda')}</label>
              <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-5-et`} value={form.currency} onChange={e => setForm(f=>({...f,currency:e.target.value}))} className="sub-input">
                {monedasDeLaEmpresa.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div className="u-mb-16">
            <label id={`${idCampo}-6-et`} htmlFor={`${idCampo}-6`} className="sub-label">{t('subcontractors.notes')}</label>
            <textarea id={`${idCampo}-6`} aria-labelledby={`${idCampo}-6-et`} value={form.notes} onChange={e => setForm(f=>({...f,notes:e.target.value}))} className="sub-input sub-textarea" />
          </div>
          <div className="u-actions-8">
            <button type="button" onClick={() => setShowCreate(false)} className="u-btn-outline-sm">{t('common.cancel')}</button>
            <Button onClick={() => create(form)} loading={isPending} disabled={!form.name || isPending}>{t('subcontractors.crear_subcontratista')}</Button>
          </div>
        </Modal>
      )}

      {showEdit && editTarget && (
        <Modal open title={t('subcontractors.editar_subcontratista')} onClose={() => { setShowEdit(false); setEditTarget(null) }} width={520}>
          <div className="sub-form-grid sub-form-grid--mb16">
            <div>
              <label id={`${idCampo}-7-et`} htmlFor={`${idCampo}-7`} className="sub-label">{t('subcontractors.nombre_razon_social')}</label>
              <input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-7-et`} value={editForm.name} onChange={e => setEditForm(f=>({...f,name:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-8-et`} htmlFor={`${idCampo}-8`} className="sub-label">{t('subcontractors.empresa')}</label>
              <input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-8-et`} value={editForm.company} onChange={e => setEditForm(f=>({...f,company:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-9-et`} htmlFor={`${idCampo}-9`} className="sub-label">{t('subcontractors.email')}</label>
              <input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-9-et`} type="email" value={editForm.email} onChange={e => setEditForm(f=>({...f,email:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-10-et`} htmlFor={`${idCampo}-10`} className="sub-label">{t('subcontractors.telefono')}</label>
              <input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-10-et`} value={editForm.phone} onChange={e => setEditForm(f=>({...f,phone:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-11-et`} htmlFor={`${idCampo}-11`} className="sub-label">{t('subcontractors.nif_vat')}</label>
              <input id={`${idCampo}-11`} aria-labelledby={`${idCampo}-11-et`} value={editForm.vat_number} onChange={e => setEditForm(f=>({...f,vat_number:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-12-et`} htmlFor={`${idCampo}-12`} className="sub-label">{t('subcontractors.moneda')}</label>
              <select id={`${idCampo}-12`} aria-labelledby={`${idCampo}-12-et`} value={editForm.currency} onChange={e => setEditForm(f=>({...f,currency:e.target.value}))} className="sub-input">
                {monedasDeLaEmpresa.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div className="u-mb-16">
            <label id={`${idCampo}-13-et`} htmlFor={`${idCampo}-13`} className="sub-label">{t('subcontractors.notes')}</label>
            <textarea id={`${idCampo}-13`} aria-labelledby={`${idCampo}-13-et`} value={editForm.notes} onChange={e => setEditForm(f=>({...f,notes:e.target.value}))} className="sub-input sub-textarea" />
          </div>
          <div className="u-actions-8">
            <button type="button" onClick={() => { setShowEdit(false); setEditTarget(null) }} className="u-btn-outline-sm">{t('common.cancel')}</button>
            <Button onClick={() => update({id: editTarget.id, ...editForm})} loading={updating} disabled={!editForm.name || updating}>{t('subcontractors.save_changes')}</Button>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
