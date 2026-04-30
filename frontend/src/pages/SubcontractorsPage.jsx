import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { enterpriseSubsApi, projectsApi, skillsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Users } from 'lucide-react'
import { Button, Modal, EmptyState, useSort, SortableTH, ViewToggle } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
const inp = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
const lbl = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }
const panel = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }

const STATUS_COLOR = { received: 'var(--warning)', approved: 'var(--accent)', paid: 'var(--success)', rejected: 'var(--danger)' }
const STATUS_LABEL = {
  received: 'Recibida',
  approved: 'Aprobada',
  paid: 'Pagada',
  rejected: 'Rechazada'
}
const LEVEL_COLOR = { basic: 'var(--text-3)', intermediate: 'var(--accent)', advanced: 'var(--orange)', expert: 'var(--success)' }

function onKeyboardActivate(event, action) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

// ── Worker Modal ──────────────────────────────────────────────────────────────
function WorkerModal({ subId, worker, onClose, onSaved }) {
  const toast = useToast()
  const qc = useQueryClient()
  const isEdit = !!worker
  const [form, setForm] = useState({
    name: worker?.name || '',
    role: worker?.role || '',
    email: worker?.email || '',
    phone: worker?.phone || '',
    cost_rate: worker?.cost_rate || '',
    sell_rate: worker?.sell_rate || '',
    currency: worker?.currency || 'EUR',
    available_from: worker?.available_from || '',
    available_until: worker?.available_until || '',
    notes: worker?.notes || '',
  })
  const [skillForm, setSkillForm] = useState({ skill_id: '', level: 'intermediate', years_experience: '', certified: false, cert_name: '' })
  const [showSkillForm, setShowSkillForm] = useState(false)

  const t = useAppT()
  const { data: skillCatalog = [] } = useQuery({
    queryKey: ['skills-catalog'],
    queryFn: () => skillsApi.catalog().then(r => r.data),
    staleTime: 300000,
  })

  const [credsInfo, setCredsInfo] = useState(null)

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: d => isEdit
      ? enterpriseSubsApi.updateWorker(worker.id, d)
      : enterpriseSubsApi.createWorker(subId, d),
    onSuccess: (res) => {
      qc.invalidateQueries(['sub-workers', subId])
      qc.invalidateQueries({ queryKey: ['users'] })
      onSaved?.()
      if (!isEdit && res.data?.login_username) {
        setCredsInfo({ username: res.data.login_username, password: res.data.temp_password })
      } else {
        onClose()
        toast.success(isEdit ? 'Trabajador actualizado' : 'Trabajador añadido')
      }
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: addSkill, isPending: addingSkill } = useMutation({
    mutationFn: d => enterpriseSubsApi.addWorkerSkill(worker?.id, d),
    onSuccess: () => { qc.invalidateQueries(['sub-workers', subId]); setShowSkillForm(false); setSkillForm({ skill_id: '', level: 'intermediate', years_experience: '', certified: false, cert_name: '' }); toast.success('Skill añadida') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: removeSkill } = useMutation({
    mutationFn: skill_id => enterpriseSubsApi.removeWorkerSkill(worker?.id, skill_id),
    onSuccess: () => { qc.invalidateQueries(['sub-workers', subId]); toast.success('Skill eliminada') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  // group skill catalog by category
  const byCategory = skillCatalog.reduce((acc, s) => {
    const cat = s.category || 'other'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(s)
    return acc
  }, {})

  if (credsInfo) {
    return (
      <Modal open title={t('subcontractors.person_added')} onClose={onClose} width={480}>
        <div style={{ textAlign: 'center', padding: '8px 0 16px' }}>
          <div style={{ fontSize: "var(--text-5xl)", marginBottom: 12 }}>🎉</div>
          <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, marginBottom: 4 }}>{t('subcontractors.person_added')}</div>
          <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 20 }}>{t('subcontractors.person_created_user')}</div>
          <div style={{ background: 'var(--surface-1)', border: '1px solid var(--accent-glow)', borderRadius: 12, padding: '16px 20px', textAlign: 'left', marginBottom: 16 }}>
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{t('subcontractors.username')}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: "var(--text-md)", color: 'var(--accent)', userSelect: 'all' }}>{credsInfo.username}</div>
            </div>
            <div>
              <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{t('subcontractors.temp_password')}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: "var(--text-md)", color: 'var(--warning)', userSelect: 'all' }}>{credsInfo.password}</div>
            </div>
          </div>
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 20 }}>
            {t('subcontractors.creds_warning')}
          </div>
          <Button onClick={onClose} style={{ width: '100%' }}>{t('subcontractors.understood')}</Button>
        </div>
      </Modal>
    )
  }

  return (
    <Modal open title={isEdit ? `${t('subcontractors.edit_person', { name: worker?.name })}` : t('subcontractors.new_person')} onClose={onClose} width={560}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={lbl}>{t('subcontractors.placeholder_name')} *</label>
          <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={inp} placeholder={t('subcontractors.placeholder_name')} />
        </div>
        <div>
          <label style={lbl}>{t('subcontractors.placeholder_role')}</label>
          <input value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} style={inp} placeholder={t('subcontractors.placeholder_role')} />
        </div>
        <div>
          <label style={lbl}>Email</label>
          <input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} style={inp} />
        </div>
        <div>
          <label style={lbl}>{t('subcontractors.cost_rate')}</label>
          <input type="number" value={form.cost_rate} onChange={e => setForm(f => ({ ...f, cost_rate: e.target.value }))} style={inp} min="0" step="0.5" />
        </div>
        <div>
          <label style={lbl}>{t('subcontractors.sell_rate')}</label>
          <input type="number" value={form.sell_rate} onChange={e => setForm(f => ({ ...f, sell_rate: e.target.value }))} style={inp} min="0" step="0.5" />
        </div>
        <div>
          <label style={lbl}>{t('subcontractors.available_from')}</label>
          <input type="date" value={form.available_from} onChange={e => setForm(f => ({ ...f, available_from: e.target.value }))} style={inp} />
        </div>
        <div>
          <label style={lbl}>{t('subcontractors.available_until')}</label>
          <input type="date" value={form.available_until} onChange={e => setForm(f => ({ ...f, available_until: e.target.value }))} style={inp} />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={lbl}>{t('subcontractors.notes')}</label>
          <textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} style={{ ...inp, minHeight: 52, resize: 'vertical' }} />
        </div>
      </div>

      {/* Skills section — only shown in edit mode */}
      {isEdit && (
        <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 14, marginBottom: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>{t('subcontractors.skills')}</div>
            <button onClick={() => setShowSkillForm(s => !s)}
              style={{ fontSize: "var(--text-xs)", padding: '3px 10px', borderRadius: 6, border: '1px solid var(--accent-glow)', background: 'var(--accent-muted)', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit' }}>
              {showSkillForm ? t('subcontractors.cancel_skill') : t('subcontractors.add_skill')}
            </button>
          </div>

          {/* Existing skills */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: showSkillForm ? 12 : 0 }}>
            {(worker.skills || []).map(s => (
              <span key={s.skill_id} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: "var(--text-xs)", padding: '3px 8px', borderRadius: 20,
                background: (LEVEL_COLOR[s.level] || 'var(--text-3)') + '18', color: LEVEL_COLOR[s.level] || 'var(--text-3)', border: `1px solid ${(LEVEL_COLOR[s.level] || 'var(--text-3)')}40` }}>
                {s.skill_name}
                <span style={{ opacity: 0.65, fontSize: "var(--text-2xs)" }}>({s.level})</span>
                {s.certified && <span title={t('subcontractors.certified')}>🏆</span>}
                <button onClick={() => removeSkill(s.skill_id)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', padding: 0, lineHeight: 1, opacity: 0.7, fontSize: "var(--text-xs)" }}>✕</button>
              </span>
            ))}
            {(worker.skills || []).length === 0 && !showSkillForm && (
              <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>{t('subcontractors.no_skills')}</span>
            )}
          </div>

          {/* Add skill form */}
          {showSkillForm && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: '12px', background: 'var(--surface-3)', borderRadius: 8 }}>
              <div style={{ gridColumn: '1/-1' }}>
                <label style={lbl}>{t('subcontractors.add_skill')} *</label>
                <select value={skillForm.skill_id} onChange={e => setSkillForm(f => ({ ...f, skill_id: e.target.value }))} style={inp}>
                  <option value="">{t('subcontractors.select_skill')}</option>
                  {Object.entries(byCategory).map(([cat, skills]) => (
                    <optgroup key={cat} label={cat.charAt(0).toUpperCase() + cat.slice(1)}>
                      {skills.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </optgroup>
                  ))}
                </select>
              </div>
              <div>
                <label style={lbl}>{t('subcontractors.level')}</label>
                <select value={skillForm.level} onChange={e => setSkillForm(f => ({ ...f, level: e.target.value }))} style={inp}>
                  {['basic','intermediate','advanced','expert'].map(l => <option key={l} value={l}>{l}</option>)}
                </select>
              </div>
              <div>
                <label style={lbl}>{t('subcontractors.years_experience')}</label>
                <input type="number" value={skillForm.years_experience} onChange={e => setSkillForm(f => ({ ...f, years_experience: e.target.value }))} style={inp} min="0" step="0.5" />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, gridColumn: '1/-1', paddingTop: 4 }}>
                <input type="checkbox" id="wsCert" checked={skillForm.certified} onChange={e => setSkillForm(f => ({ ...f, certified: e.target.checked }))} />
                <label htmlFor="wsCert" style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', cursor: 'pointer' }}>{t('subcontractors.certified')}</label>
                {skillForm.certified && (
                  <input value={skillForm.cert_name} onChange={e => setSkillForm(f => ({ ...f, cert_name: e.target.value }))} style={{ ...inp, flex: 1 }} placeholder={t('subcontractors.placeholder_cert')} />
                )}
              </div>
              <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end' }}>
                <Button size="sm" onClick={() => addSkill(skillForm)} loading={addingSkill} disabled={!skillForm.skill_id || addingSkill}>{t('subcontractors.assign_skill')}</Button>
              </div>
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
          {isEdit ? t('subcontractors.close') : t('subcontractors.cancel')}
        </button>
        <Button onClick={() => save(form)} loading={saving} disabled={!form.name || saving}>{isEdit ? t('subcontractors.save_changes') : t('subcontractors.add_person')}</Button>
      </div>
    </Modal>
  )
}

// ── Workers Panel ─────────────────────────────────────────────────────────────
function WorkersPanel({ subId }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [editWorker, setEditWorker] = useState(null)
  const [deactivateTarget, setDeactivateTarget] = useState(null)

  const { data: workers = [], isLoading } = useQuery({
    queryKey: ['sub-workers', subId],
    queryFn: () => enterpriseSubsApi.workers(subId).then(r => r.data),
  })

  const { mutate: deactivate } = useMutation({
    mutationFn: id => enterpriseSubsApi.deleteWorker(id),
    onSuccess: () => {
      qc.invalidateQueries(['sub-workers', subId])
      qc.invalidateQueries({ queryKey: ['users'] })
      toast.success('Trabajador desactivado')
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  if (isLoading) return <div style={{ textAlign: 'center', padding: 30, color: 'var(--text-2)' }}>Cargando...</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Button size="sm" onClick={() => setShowCreate(true)}>{t('subcontractors.add_person_btn')}</Button>
      </div>

      {workers.length === 0 ? (
        <EmptyState icon="👤" title={t('subcontractors.empty_people_title')} description={t('subcontractors.empty_people_desc')} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {workers.map(w => (
            <div key={w.id} style={{ ...panel, padding: '14px 18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{w.name}</div>
                    {w.role && <span style={{ fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 20, background: 'var(--accent-muted)', color: 'var(--accent)' }}>{w.role}</span>}
                    {!w.is_active && <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, background: 'var(--danger-bg, var(--danger-border))', color: 'var(--danger)' }}>{t('subcontractors.inactivo')}</span>}
                  </div>
                  {w.email && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>📧 {w.email}</div>}
                  {(w.cost_rate || w.sell_rate) && (
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 8 }}>
                      {w.cost_rate && t('subcontractors.cost', { rate: w.cost_rate })}
                      {w.cost_rate && w.sell_rate && ' · '}
                      {w.sell_rate && t('subcontractors.sell', { rate: w.sell_rate })}
                    </div>
                  )}
                  {/* Skills */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {(w.skills || []).map(s => (
                      <span key={s.skill_id} style={{ fontSize: "var(--text-2xs)", padding: '2px 7px', borderRadius: 20,
                        background: (LEVEL_COLOR[s.level] || 'var(--text-3)') + '18',
                        color: LEVEL_COLOR[s.level] || 'var(--text-3)',
                        border: `1px solid ${(LEVEL_COLOR[s.level] || 'var(--text-3)')}35` }}>
                        {s.skill_name}
                        {s.certified && ' 🏆'}
                      </span>
                    ))}
                    {(w.skills || []).length === 0 && <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-4)' }}>{t('subcontractors.no_skills_short')}</span>}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                  {(w.available_from || w.available_until) && (
                    <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textAlign: 'right', marginRight: 6, alignSelf: 'center' }}>
                      {w.available_from && <div>Desde: {w.available_from}</div>}
                      {w.available_until && <div>Hasta: {w.available_until}</div>}
                    </div>
                  )}
                    <button onClick={() => setEditWorker(w)}
                      style={{ padding: '5px 10px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                      {t('subcontractors.edit')}
                    </button>
                  {w.is_active && (
                    <button onClick={() => setDeactivateTarget(w)}
                      style={{ padding: '5px 10px', borderRadius: 6, border: '1px solid var(--danger-border)', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                      🗑
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && <WorkerModal subId={subId} onClose={() => setShowCreate(false)} onSaved={() => qc.invalidateQueries(['subcontractors'])} />}
      {editWorker && <WorkerModal subId={subId} worker={editWorker} onClose={() => setEditWorker(null)} onSaved={() => qc.invalidateQueries(['subcontractors'])} />}
      {deactivateTarget && (
        <Modal open title="Desactivar trabajador" onClose={() => setDeactivateTarget(null)} width={380}>
          <p style={{ fontSize: "var(--text-md)", color: 'var(--text-1)', marginBottom: 20 }}>
            Se desactivará a <strong>{deactivateTarget.name}</strong> y no podrá iniciar sesión ni ser asignado a tareas.
          </p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Button variant="ghost" onClick={() => setDeactivateTarget(null)}>{t('subcontractors.cancel')}</Button>
            <Button variant="danger" onClick={() => { deactivate(deactivateTarget.id); setDeactivateTarget(null) }}>{t('subcontractors.deactivate')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
function SubDetail({ sub, onBack }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('workers')
  const [showTimelog, setShowTimelog] = useState(false)
  const [showInvoice, setShowInvoice] = useState(false)
  const [showAssign, setShowAssign] = useState(false)
  const [tlForm, setTlForm] = useState({ assignment_id: '', log_date: new Date().toISOString().slice(0,10), hours: 8, description: '', task_reference: '' })
  const [invForm, setInvForm] = useState({ invoice_number: '', issue_date: new Date().toISOString().slice(0,10), due_date: '', amount: '', tax_pct: 21, description: '' })
  const [asgForm, setAsgForm] = useState({ project_id: '', po_number: '', po_amount: '', hours_contracted: '', start_date: '', end_date: '', notes: '' })

  const { data: assignments = [] } = useQuery({
    queryKey: ['sub-assignments', sub.id],
    queryFn: () => enterpriseSubsApi.assignments(sub.id).then(r => r.data),
  })
  const { data: timelogs = [] } = useQuery({
    queryKey: ['sub-timelogs', sub.id],
    queryFn: () => enterpriseSubsApi.timelogs(sub.id).then(r => r.data),
  })
  const { data: invoices = [] } = useQuery({
    queryKey: ['sub-invoices', sub.id],
    queryFn: () => enterpriseSubsApi.invoices(sub.id).then(r => r.data),
  })
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data.filter(p => p.status === 'active')),
  })

  const { mutate: logHours, isPending: logging } = useMutation({
    mutationFn: d => enterpriseSubsApi.createTimelog(sub.id, d),
    onSuccess: () => { qc.invalidateQueries(['sub-timelogs', sub.id]); setShowTimelog(false); toast.success('Horas registradas') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: createInv, isPending: invoicing } = useMutation({
    mutationFn: d => enterpriseSubsApi.createInvoice(sub.id, d),
    onSuccess: () => { qc.invalidateQueries(['sub-invoices', sub.id]); setShowInvoice(false); toast.success('Factura registrada') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: createAssign, isPending: assigning } = useMutation({
    mutationFn: d => enterpriseSubsApi.createAssignment(sub.id, d),
    onSuccess: () => { qc.invalidateQueries(['sub-assignments', sub.id]); setShowAssign(false); toast.success('Asignación creada') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: updateInvStatus } = useMutation({
    mutationFn: ({ id, status }) => enterpriseSubsApi.updateInvoice(sub.id, id, { status }),
    onSuccess: () => qc.invalidateQueries(['sub-invoices', sub.id]),
    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const totalHours    = timelogs.reduce((s, l) => s + l.hours, 0)
  const totalCost     = timelogs.reduce((s, l) => s + (l.cost_amount || 0), 0)
  const pendingAmount = invoices.filter(i => i.status === 'received').reduce((s, i) => s + i.total, 0)

  const tabStyle = active => ({
    padding: '6px 16px', borderRadius: 8, border: 'none', cursor: 'pointer',
    background: active ? 'var(--accent-glow)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text-2)',
    fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: active ? 700 : 400,
  })

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 20 }}>
        <button onClick={onBack} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '6px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>← Volver</button>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800 }}>{sub.name} <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', fontWeight: 400 }}>{sub.code}</span></div>
          {sub.company && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{sub.company} · {sub.email}</div>}
        </div>
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Personas', value: sub.worker_count ?? '—', color: 'var(--purple, var(--purple))' },
          { label: 'Asignaciones', value: assignments.length, color: 'var(--accent)' },
          { label: 'Horas registradas', value: `${totalHours.toFixed(1)}h`, color: 'var(--success)' },
          { label: 'Coste acumulado', value: `${totalCost.toLocaleString('es-ES', {style:'currency',currency:'EUR'})}`, color: 'var(--warning)' },
          { label: 'Facturas pendientes', value: `${pendingAmount.toLocaleString('es-ES', {style:'currency',currency:'EUR'})}`, color: pendingAmount > 0 ? 'var(--danger)' : 'var(--text-2)' },
        ].map(k => (
          <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '12px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, color: k.color, fontFamily: 'var(--font-mono)' }}>{k.value}</div>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 3 }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, background: 'var(--surface-1)', borderRadius: 8, padding: 3, marginBottom: 16, width: 'fit-content' }}>
        {[
          { id: 'workers',     label: `Personas` },
          { id: 'assignments', label: `Asignaciones (${assignments.length})` },
          { id: 'timelogs',    label: `Horas (${timelogs.length})` },
          { id: 'invoices',    label: `Facturas (${invoices.length})` },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={tabStyle(tab === t.id)}>{t.label}</button>
        ))}
      </div>

      {/* Personas (Workers) */}
      {tab === 'workers' && <WorkersPanel subId={sub.id} />}

      {/* Asignaciones */}
      {tab === 'assignments' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
            <Button size="sm" onClick={() => setShowAssign(true)}>+ Nueva asignación</Button>
          </div>
          {assignments.length === 0 ? (
            <EmptyState icon="📋" title={t('subcontractors.empty_assignments_title')} description={t('subcontractors.empty_assignments_desc')} />
          ) : assignments.map(a => (
            <div key={a.id} style={{ ...panel, padding: '14px 18px', marginBottom: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>{a.project_code} — {a.project_name}</div>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 2 }}>
                    {a.po_number && `PO: ${a.po_number}`}
                    {a.po_amount && ` · Techo: ${a.po_amount.toLocaleString('es-ES', {style:'currency',currency:'EUR'})}`}
                    {a.hours_contracted && ` · ${a.hours_contracted}h contratadas`}
                  </div>
                  {a.hours_contracted && (
                    <div style={{ marginTop: 6 }}>
                      <div style={{ height: 6, background: 'var(--surface-4)', borderRadius: 3, overflow: 'hidden', width: 200 }}>
                        <div style={{ height: '100%', width: `${Math.min(a.budget_used_pct || 0, 100)}%`, background: (a.budget_used_pct || 0) > 90 ? 'var(--danger)' : 'var(--success)', borderRadius: 3 }} />
                      </div>
                      <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)', marginTop: 2 }}>{a.hours_logged}h / {a.hours_contracted}h ({a.budget_used_pct || 0}%)</div>
                    </div>
                  )}
                </div>
                <Button size="sm" onClick={() => { setTlForm(f => ({...f, assignment_id: a.id})); setShowTimelog(true) }}>+ Registrar horas</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Timelogs */}
      {tab === 'timelogs' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
            <Button size="sm" onClick={() => setShowTimelog(true)}>+ Registrar horas</Button>
          </div>
          {timelogs.length === 0 ? (
            <EmptyState icon="🕐" title={t('subcontractors.empty_hours_title')} description={t('subcontractors.empty_hours_desc')} />
          ) : (
            <div style={{ ...panel, overflow: 'hidden' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
                    {['Fecha', 'Horas', 'Descripción', 'Ref. tarea', 'Coste', 'Proyecto'].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '10px 14px', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {timelogs.map(l => (
                    <tr key={l.id} style={{ borderBottom: '1px solid var(--surface-1)' }}>
                      <td style={{ padding: '9px 14px', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{l.log_date}</td>
                      <td style={{ padding: '9px 14px', fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>{l.hours}h</td>
                      <td style={{ padding: '9px 14px', fontSize: "var(--text-sm)", color: 'var(--text-1)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.description || '—'}</td>
                      <td style={{ padding: '9px 14px', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{l.task_reference || '—'}</td>
                      <td style={{ padding: '9px 14px', fontSize: "var(--text-sm)", color: 'var(--warning)', fontFamily: 'var(--font-mono)' }}>
                        {l.cost_amount ? l.cost_amount.toLocaleString('es-ES', {style:'currency',currency:'EUR'}) : '—'}
                      </td>
                      <td style={{ padding: '9px 14px', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{l.project_name || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Facturas */}
      {tab === 'invoices' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
            <Button size="sm" onClick={() => setShowInvoice(true)}>+ Registrar factura</Button>
          </div>
          {invoices.length === 0 ? (
            <EmptyState icon="🧾" title={t('subcontractors.empty_invoices_title')} description={t('subcontractors.empty_invoices_desc')} />
          ) : (
            <div style={{ ...panel, overflow: 'hidden' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
                    {['Nº Factura', 'Fecha', 'Importe', 'Total c/IVA', 'Estado', 'Acciones'].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '10px 14px', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {invoices.map(inv => (
                    <tr key={inv.id} style={{ borderBottom: '1px solid var(--surface-1)' }}>
                      <td style={{ padding: '9px 14px', fontSize: "var(--text-sm)", fontWeight: 600 }}>{inv.invoice_number}</td>
                      <td style={{ padding: '9px 14px', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{inv.issue_date}</td>
                      <td style={{ padding: '9px 14px', fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)' }}>{inv.amount.toLocaleString('es-ES', {style:'currency',currency:'EUR'})}</td>
                      <td style={{ padding: '9px 14px', fontSize: "var(--text-base)", fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--warning)' }}>{inv.total.toLocaleString('es-ES', {style:'currency',currency:'EUR'})}</td>
                      <td style={{ padding: '9px 14px' }}>
                        <span style={{ fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 20, background: (STATUS_COLOR[inv.status] || 'var(--text-2)') + '20', color: STATUS_COLOR[inv.status] || 'var(--text-2)', fontWeight: 700 }}>
                          {STATUS_LABEL[inv.status] || inv.status}
                        </span>
                      </td>
                      <td style={{ padding: '9px 14px' }}>
                        <div style={{ display: 'flex', gap: 6 }}>
                          {inv.status === 'received' && (
                            <button onClick={() => updateInvStatus({ id: inv.id, status: 'approved' })} style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>Aprobar</button>
                          )}
                          {inv.status === 'approved' && (
                            <button onClick={() => updateInvStatus({ id: inv.id, status: 'paid' })} style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>Marcar pagada</button>
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
        <Modal open title="Registrar horas" onClose={() => setShowTimelog(false)} width={480}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
            <div>
              <label style={lbl}>Asignación</label>
              <select value={tlForm.assignment_id} onChange={e => setTlForm(f=>({...f,assignment_id:e.target.value}))} style={inp}>
                <option value="">Sin asignación</option>
                {assignments.map(a => <option key={a.id} value={a.id}>{a.project_code} — {a.project_name}</option>)}
              </select>
            </div>
            <div>
              <label style={lbl}>Fecha</label>
              <input type="date" value={tlForm.log_date} onChange={e => setTlForm(f=>({...f,log_date:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Horas *</label>
              <input type="number" value={tlForm.hours} onChange={e => setTlForm(f=>({...f,hours:+e.target.value}))} style={inp} min="0.5" step="0.5" />
            </div>
            <div>
              <label style={lbl}>Referencia tarea</label>
              <input value={tlForm.task_reference} onChange={e => setTlForm(f=>({...f,task_reference:e.target.value}))} style={inp} placeholder="Referencia de tarea" aria-label="Referencia de tarea" />
            </div>
            <div style={{ gridColumn: '1/-1' }}>
              <label style={lbl}>Descripción</label>
              <input value={tlForm.description} onChange={e => setTlForm(f=>({...f,description:e.target.value}))} style={inp} placeholder="Descripcion del parte" aria-label="Descripcion del parte" />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowTimelog(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => logHours(tlForm)} loading={logging} disabled={!tlForm.hours || logging}>Registrar horas</Button>
          </div>
        </Modal>
      )}

      {/* Modal registrar factura */}
      {showInvoice && (
        <Modal open title="Registrar factura" onClose={() => setShowInvoice(false)} width={480}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
            <div>
              <label style={lbl}>Nº Factura *</label>
              <input value={invForm.invoice_number} onChange={e => setInvForm(f=>({...f,invoice_number:e.target.value}))} style={inp} placeholder="Numero de factura" aria-label="Numero de factura" />
            </div>
            <div>
              <label style={lbl}>Fecha emisión</label>
              <input type="date" value={invForm.issue_date} onChange={e => setInvForm(f=>({...f,issue_date:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Importe base (€) *</label>
              <input type="number" value={invForm.amount} onChange={e => setInvForm(f=>({...f,amount:e.target.value}))} style={inp} min="0" step="0.01" />
            </div>
            <div>
              <label style={lbl}>IVA (%)</label>
              <input type="number" value={invForm.tax_pct} onChange={e => setInvForm(f=>({...f,tax_pct:+e.target.value}))} style={inp} min="0" max="30" />
            </div>
            {invForm.amount && (
              <div style={{ gridColumn: '1/-1', background: 'var(--accent-muted)', border: '1px solid var(--accent-border-soft)', borderRadius: 8, padding: '8px 12px', fontSize: "var(--text-sm)", color: 'var(--accent)' }}>
                Total con IVA: <strong>{(+invForm.amount * (1 + invForm.tax_pct/100)).toLocaleString('es-ES', {style:'currency',currency:'EUR'})}</strong>
              </div>
            )}
            <div style={{ gridColumn: '1/-1' }}>
              <label style={lbl}>Descripción</label>
              <input value={invForm.description} onChange={e => setInvForm(f=>({...f,description:e.target.value}))} style={inp} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowInvoice(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => createInv(invForm)} loading={invoicing} disabled={!invForm.invoice_number || !invForm.amount || invoicing}>Registrar factura</Button>
          </div>
        </Modal>
      )}

      {/* Modal nueva asignación */}
      {showAssign && (
        <Modal open title="Nueva asignacion" onClose={() => setShowAssign(false)} width={500}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
            <div style={{ gridColumn: '1/-1' }}>
              <label style={lbl}>Proyecto *</label>
              <select value={asgForm.project_id} onChange={e => setAsgForm(f=>({...f,project_id:e.target.value}))} style={inp}>
                <option value="">Seleccionar...</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
            <div>
              <label style={lbl}>Nº Pedido (PO)</label>
              <input value={asgForm.po_number} onChange={e => setAsgForm(f=>({...f,po_number:e.target.value}))} style={inp} placeholder="Numero de pedido" aria-label="Numero de pedido" />
            </div>
            <div>
              <label style={lbl}>Techo PO (€)</label>
              <input type="number" value={asgForm.po_amount} onChange={e => setAsgForm(f=>({...f,po_amount:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Horas contratadas</label>
              <input type="number" value={asgForm.hours_contracted} onChange={e => setAsgForm(f=>({...f,hours_contracted:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Fecha inicio</label>
              <input type="date" value={asgForm.start_date} onChange={e => setAsgForm(f=>({...f,start_date:e.target.value}))} style={inp} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowAssign(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => createAssign(asgForm)} loading={assigning} disabled={!asgForm.project_id || assigning}>Crear asignación</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function SubcontractorsPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selected, setSelected] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', company: '', email: '', phone: '', country: 'España', currency: 'EUR', vat_number: '', notes: '' })

  const { data: dashboard } = useQuery({
    queryKey: ['sub-dashboard'],
    queryFn: () => enterpriseSubsApi.dashboard().then(r => r.data),
  })
  const { data: subs = [], isLoading } = useQuery({
    queryKey: ['subcontractors'],
    queryFn: () => enterpriseSubsApi.list().then(r => r.data),
  })

  const [showEdit, setShowEdit] = useState(false)
  const [editTarget, setEditTarget] = useState(null)
  const [editForm, setEditForm] = useState({})
  const [view, setView] = useState('grid')
  const { sort: subSort, setSort: setSubSort, sortedData: sortedSubs } = useSort(subs, 'name')

  const { mutate: create, isPending } = useMutation({
    mutationFn: d => enterpriseSubsApi.create(d),
    onSuccess: (res) => {
      qc.invalidateQueries(['subcontractors'])
      setShowCreate(false)
      setForm({ name: '', company: '', email: '', phone: '', country: 'España', currency: 'EUR', vat_number: '', notes: '' })
      setSelected(res.data)
      toast.success('Subcontratista creado')
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: update, isPending: updating } = useMutation({
    mutationFn: ({id, ...d}) => enterpriseSubsApi.update(id, d),
    onSuccess: (_res) => {
      qc.invalidateQueries(['subcontractors'])
      setShowEdit(false)
      setEditTarget(null)
      toast.success('Subcontratista actualizado')
    },
    onError: e => toast.error(extractErr(e, 'Error al actualizar')),
  })
  const { mutate: remove } = useMutation({
    mutationFn: id => enterpriseSubsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries(['subcontractors'])
      qc.invalidateQueries(['sub-dashboard'])
      toast.success('Subcontratista eliminado')
    },
    onError: e => toast.error(extractErr(e, 'Error al eliminar')),
  })

  if (selected) return <SubDetail sub={selected} onBack={() => setSelected(null)} />

  return (
    <PageShell>
      <PageHeader icon={<Users size={18} />} title={t('subcontractors.title')} subtitle={t('subcontractors.subtitle')} />

      {/* KPIs */}
      {dashboard && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
          {[
            { label: 'Activos',           value: dashboard.total_active_subs,       color: 'var(--accent)' },
            { label: 'Horas registradas', value: `${dashboard.total_hours_logged}h`, color: 'var(--success)' },
            { label: 'Facturas pendientes', value: dashboard.pending_invoices,       color: dashboard.pending_invoices > 0 ? 'var(--warning)' : 'var(--text-2)' },
          ].map(k => (
            <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 18px', textAlign: 'center' }}>
              <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, color: k.color, fontFamily: 'var(--font-mono)' }}>{k.value}</div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 3 }}>{k.label}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginBottom: 16, alignItems: 'center' }}>
        <ViewToggle view={view} onChange={setView} />
        <Button onClick={() => setShowCreate(true)}>+ Nuevo subcontratista</Button>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-2)' }}>Cargando...</div>
      ) : subs.length === 0 ? (
        <EmptyState icon="🤝" title="Sin subcontratistas" description="Crea el primer colaborador externo para empezar" />
      ) : view === 'grid' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
          {sortedSubs.map(s => (
            <div key={s.id} onClick={() => setSelected(s)}
              role="button"
              tabIndex={0}
              onKeyDown={e => onKeyboardActivate(e, () => setSelected(s))}
              style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '16px 20px', cursor: 'pointer', transition: 'border-color 0.15s' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{s.name}</div>
                  {s.company && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{s.company}</div>}
                </div>
                <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, background: s.is_active ? 'var(--success-bg)' : 'var(--danger-bg)', color: s.is_active ? 'var(--success)' : 'var(--danger)' }}>
                  {s.is_active ? 'Activo' : 'Inactivo'}
                </span>
              </div>
              {s.email && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>📧 {s.email}</div>}
              <div style={{ marginTop: 8, fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                👥 {s.worker_count || 0} persona{(s.worker_count || 0) !== 1 ? 's' : ''} · {s.assignment_count} asignación{s.assignment_count !== 1 ? 'es' : ''}
              </div>
              <div style={{ marginTop: 10, display: 'flex', gap: 6 }}>
                <button onClick={e => { e.stopPropagation(); setEditTarget(s); setEditForm({ name: s.name, company: s.company||'', email: s.email||'', phone: s.phone||'', country: s.country||'España', currency: s.currency||'EUR', vat_number: s.vat_number||'', notes: s.notes||'' }); setShowEdit(true) }}
                  style={{ flex:1, padding: '4px 0', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
                  ✏ Editar
                </button>
                <button onClick={e => { e.stopPropagation(); openConfirmGlobal({message:`¿Eliminar a "${s.name}"?`,onConfirm:()=>remove(s.id),danger:true}) }}
                  style={{ flex:1, padding: '4px 0', borderRadius: 6, border: '1px solid var(--danger-border, var(--danger-border))', background: 'transparent', color: 'var(--danger)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
                  🗑 Eliminar
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px 100px', gap: 12, padding: '10px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
            <SortableTH col="name" sort={subSort} onSort={setSubSort}>Empresa / Nombre</SortableTH>
            <SortableTH col="code" sort={subSort} onSort={setSubSort}>Código</SortableTH>
            <SortableTH col="email" sort={subSort} onSort={setSubSort}>Email</SortableTH>
            <SortableTH col="worker_count" sort={subSort} onSort={setSubSort}>Personas</SortableTH>
            <SortableTH col="assignment_count" sort={subSort} onSort={setSubSort}>Asignaciones</SortableTH>
            <SortableTH col="is_active" sort={subSort} onSort={setSubSort}>Estado</SortableTH>
            <span>Acciones</span>
          </div>
          {sortedSubs.map(s => (
            <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px 100px', gap: 12, padding: '11px 20px', borderBottom: '1px solid var(--surface-4)30', alignItems: 'center', cursor: 'pointer' }}
              role="button"
              tabIndex={0}
              onKeyDown={e => onKeyboardActivate(e, () => setSelected(s))}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              onClick={() => setSelected(s)}>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{s.name}</div>
                {s.company && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{s.company}</div>}
              </div>
              <span style={{ fontSize: "var(--text-xs)", fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{s.code || '—'}</span>
              <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{s.email || '—'}</span>
              <span style={{ fontSize: "var(--text-sm)" }}>{s.worker_count || 0}</span>
              <span style={{ fontSize: "var(--text-sm)" }}>{s.assignment_count || 0}</span>
              <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: s.is_active ? 'var(--success-bg)' : 'var(--danger-bg)', color: s.is_active ? 'var(--success)' : 'var(--danger)' }}>
                {s.is_active ? 'Activo' : 'Inactivo'}
              </span>
              <div style={{ display: 'flex', gap: 4 }}>
                <button onClick={e => { e.stopPropagation(); setEditTarget(s); setEditForm({ name: s.name, company: s.company||'', email: s.email||'', phone: s.phone||'', country: s.country||'España', currency: s.currency||'EUR', vat_number: s.vat_number||'', notes: s.notes||'' }); setShowEdit(true) }}
                  style={{ padding: '3px 8px', borderRadius: 5, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>✏</button>
                <button onClick={e => { e.stopPropagation(); openConfirmGlobal({message:`¿Eliminar a "${s.name}"?`,onConfirm:()=>remove(s.id),danger:true}) }}
                  style={{ padding: '3px 8px', borderRadius: 5, border: '1px solid var(--danger-border)', background: 'transparent', color: 'var(--danger)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>🗑</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <Modal open title="Nuevo subcontratista" onClose={() => setShowCreate(false)} width={520}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={lbl}>Nombre / Razón social *</label>
              <input value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={inp} placeholder="Nombre o razon social" aria-label="Nombre o razon social" />
            </div>
            <div>
              <label style={lbl}>Empresa (si es persona física)</label>
              <input value={form.company} onChange={e => setForm(f=>({...f,company:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Email</label>
              <input type="email" value={form.email} onChange={e => setForm(f=>({...f,email:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Teléfono</label>
              <input value={form.phone} onChange={e => setForm(f=>({...f,phone:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>NIF / VAT</label>
              <input value={form.vat_number} onChange={e => setForm(f=>({...f,vat_number:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Moneda</label>
              <select value={form.currency} onChange={e => setForm(f=>({...f,currency:e.target.value}))} style={inp}>
                {['EUR','USD','GBP','CHF','MXN'].map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={lbl}>Notas</label>
            <textarea value={form.notes} onChange={e => setForm(f=>({...f,notes:e.target.value}))} style={{ ...inp, minHeight: 60, resize: 'vertical' }} />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowCreate(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => create(form)} loading={isPending} disabled={!form.name || isPending}>Crear subcontratista</Button>
          </div>
        </Modal>
      )}

      {showEdit && editTarget && (
        <Modal open title="Editar subcontratista" onClose={() => { setShowEdit(false); setEditTarget(null) }} width={520}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={lbl}>Nombre / Razón social *</label>
              <input value={editForm.name} onChange={e => setEditForm(f=>({...f,name:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Empresa</label>
              <input value={editForm.company} onChange={e => setEditForm(f=>({...f,company:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Email</label>
              <input type="email" value={editForm.email} onChange={e => setEditForm(f=>({...f,email:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Teléfono</label>
              <input value={editForm.phone} onChange={e => setEditForm(f=>({...f,phone:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>NIF / VAT</label>
              <input value={editForm.vat_number} onChange={e => setEditForm(f=>({...f,vat_number:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Moneda</label>
              <select value={editForm.currency} onChange={e => setEditForm(f=>({...f,currency:e.target.value}))} style={inp}>
                {['EUR','USD','GBP','CHF','MXN'].map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={lbl}>Notas</label>
            <textarea value={editForm.notes} onChange={e => setEditForm(f=>({...f,notes:e.target.value}))} style={{ ...inp, minHeight: 60, resize: 'vertical' }} />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => { setShowEdit(false); setEditTarget(null) }} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => update({id: editTarget.id, ...editForm})} loading={updating} disabled={!editForm.name || updating}>Guardar cambios</Button>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
