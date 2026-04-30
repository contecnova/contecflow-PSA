import { useId, useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalsApi } from '../services/api'
import _api, { usersApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CheckCircle } from 'lucide-react'
import { Button, Modal, EmptyState, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

const inp = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
const lbl = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }
const panel = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }

const entityLabels = (t) => ({
  timesheet: { label: t('approvals.entity_timesheet'), icon: '🕐', color: 'var(--accent)' },
  expense: { label: t('approvals.entity_expense'), icon: '💶', color: 'var(--warning)' },
  change_request: { label: t('approvals.entity_change_request'), icon: '🔄', color: 'var(--purple)' },
  milestone: { label: t('approvals.entity_milestone'), icon: '◎', color: 'var(--success)' },
  purchase: { label: t('approvals.entity_purchase'), icon: '🛒', color: 'var(--danger)' },
})

const approverTypeLabels = (t) => ({
  user: t('approvals.approver_user'),
  role: t('approvals.approver_role'),
  manager: t('approvals.approver_manager'),
  any_in_department: t('approvals.approver_any_department'),
})

const ROLES = ['admin', 'pm', 'team_lead', 'hr', 'developer', 'designer', 'finance']

// ── Modal de paso ─────────────────────────────────────────────────────────────
function StepModal({ workflowId, step, onClose }) {
  const t = useAppT()
  const idPrefix = useId()
  const toast = useToast()
  const { _invalidate } = useInvalidate()
  const qc = useQueryClient()
  const isEdit = !!step?.id
  const [form, setForm] = useState({
    step_order:          step?.step_order          || 1,
    name:                step?.name                || '',
    approver_type:       step?.approver_type       || 'role',
    approver_role:       step?.approver_role       || '',
    approver_user_id:    step?.approver_user_id    || '',
    approver_department: step?.approver_department || '',
    is_optional:         step?.is_optional         || false,
    timeout_hours:       step?.timeout_hours       || 72,
    on_timeout:          step?.on_timeout          || 'escalate',
  })

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit
      ? approvalsApi.updateStep(workflowId, step.id, d)
      : approvalsApi.addStep(workflowId, d),
    onSuccess: () => {
      qc.invalidateQueries(['approval-workflow', workflowId])
      toast.success(isEdit ? t('approvals.step_updated') : t('approvals.step_added'))
      onClose()
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  return (
    <Modal open title={isEdit ? t('approvals.step_modal_edit_title') : t('approvals.step_modal_new_title')} onClose={onClose} width={520}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        <div>
          <label htmlFor={`${idPrefix}-name`} style={lbl}>{t('approvals.step_name_required')}</label>
          <input id={`${idPrefix}-name`} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={inp} placeholder={t('approvals.step_name_placeholder')} />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-order`} style={lbl}>{t('approvals.order')}</label>
          <input id={`${idPrefix}-order`} type="number" value={form.step_order} onChange={e => setForm(f=>({...f,step_order:+e.target.value}))} style={inp} min="1" max="10" />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label htmlFor={`${idPrefix}-approver-type`} style={lbl}>{t('approvals.approver_type')}</label>
          <select id={`${idPrefix}-approver-type`} value={form.approver_type} onChange={e => setForm(f=>({...f,approver_type:e.target.value}))} style={inp}>
            {Object.entries(approverTypeLabels(t)).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>

        {form.approver_type === 'role' && (
          <div style={{ gridColumn: '1/-1' }}>
            <label htmlFor={`${idPrefix}-approver-role`} style={lbl}>{t('approvals.required_role')}</label>
            <select id={`${idPrefix}-approver-role`} value={form.approver_role} onChange={e => setForm(f=>({...f,approver_role:e.target.value}))} style={inp}>
              <option value="">{t('approvals.select_role')}</option>
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        )}

        {form.approver_type === 'user' && (
          <div style={{ gridColumn: '1/-1' }}>
            <label htmlFor={`${idPrefix}-approver-user`} style={lbl}>{t('approvals.approver_user_label')}</label>
            <select id={`${idPrefix}-approver-user`} value={form.approver_user_id} onChange={e => setForm(f=>({...f,approver_user_id:e.target.value}))} style={inp}>
              <option value="">{t('approvals.select_user')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>)}
            </select>
          </div>
        )}

        {form.approver_type === 'any_in_department' && (
          <div style={{ gridColumn: '1/-1' }}>
            <label htmlFor={`${idPrefix}-approver-department`} style={lbl}>{t('approvals.department')}</label>
            <input id={`${idPrefix}-approver-department`} value={form.approver_department} onChange={e => setForm(f=>({...f,approver_department:e.target.value}))} style={inp} placeholder={t('approvals.department_placeholder')} />
          </div>
        )}

        <div>
          <label htmlFor={`${idPrefix}-timeout-hours`} style={lbl}>{t('approvals.timeout_hours')}</label>
          <input id={`${idPrefix}-timeout-hours`} type="number" value={form.timeout_hours} onChange={e => setForm(f=>({...f,timeout_hours:+e.target.value}))} style={inp} min="1" />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-on-timeout`} style={lbl}>{t('approvals.on_timeout')}</label>
          <select id={`${idPrefix}-on-timeout`} value={form.on_timeout} onChange={e => setForm(f=>({...f,on_timeout:e.target.value}))} style={inp}>
            <option value="escalate">{t('approvals.timeout_escalate')}</option>
            <option value="auto_approve">{t('approvals.timeout_auto_approve')}</option>
            <option value="reject">{t('approvals.timeout_reject')}</option>
          </select>
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label htmlFor={`${idPrefix}-is-optional`} style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>
            <input id={`${idPrefix}-is-optional`} type="checkbox" checked={form.is_optional} onChange={e => setForm(f=>({...f,is_optional:e.target.checked}))} style={{ accentColor: 'var(--accent)' }} />
            {t('approvals.optional_step_label')}
          </label>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>{t('common.cancel')}</button>
        <Button onClick={() => mutate(form)} loading={isPending} disabled={!form.name || isPending}>
          {isEdit ? t('approvals.save_step') : t('approvals.add_step')}
        </Button>
      </div>
    </Modal>
  )
}

// ── Detalle de flujo ──────────────────────────────────────────────────────────
function WorkflowDetail({ workflowId, onBack }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showStep, setShowStep] = useState(false)
  const [editStep, setEditStep] = useState(null)

  const { data: wf } = useQuery({
    queryKey: ['approval-workflow', workflowId],
    queryFn: () => approvalsApi.getWorkflow(workflowId).then(r => r.data),
  })

  const { mutate: delStep } = useMutation({
    mutationFn: sid => approvalsApi.deleteStep(workflowId, sid),
    onSuccess: () => { qc.invalidateQueries(['approval-workflow', workflowId]); toast.success(t('approvals.step_deleted')) },

    onError: e => toast.error(extractErr(e, t('approvals.error_generic')))
  })

  const { mutate: toggleActive } = useMutation({
    mutationFn: val => approvalsApi.updateWorkflow(workflowId, { is_active: val }),
    onSuccess: () => qc.invalidateQueries(['approval-workflow', workflowId]),
    onError: e => toast.error(extractErr(e, t('approvals.error_generic')))
  })

  if (!wf) return null
  const steps = [...(wf.steps || [])].sort((a, b) => a.step_order - b.step_order)
  const entity = entityLabels(t)[wf.entity_type] || { label: wf.entity_type, icon: '○', color: 'var(--text-2)' }

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 20 }}>
        <button aria-label={t('approvals.back')} onClick={onBack} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '6px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>{t('approvals.back')}</button>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800 }}>{wf.name}</div>
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
            <span style={{ color: entity.color }}>{entity.icon} {entity.label}</span>
            {wf.is_default && <span style={{ marginLeft: 8, fontSize: "var(--text-2xs)", padding: '1px 6px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)' }}>{t('approvals.default_badge')}</span>}
            {!wf.is_active && <span style={{ marginLeft: 8, fontSize: "var(--text-2xs)", padding: '1px 6px', borderRadius: 4, background: 'var(--danger-bg)', color: 'var(--danger)' }}>{t('approvals.inactive_badge')}</span>}
          </div>
        </div>
        <button aria-pressed={wf.is_active} onClick={() => toggleActive(!wf.is_active)} style={{
          background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8,
          padding: '6px 14px', color: wf.is_active ? 'var(--warning)' : 'var(--success)',
          cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit',
        }}>
          {wf.is_active ? t('approvals.deactivate') : t('approvals.activate')}
        </button>
        <Button onClick={() => setShowStep(true)}>{t('approvals.add_step')}</Button>
      </div>

      {steps.length === 0 ? (
        <EmptyState icon="○" title={t('approvals.no_steps_defined')} description={t('approvals.no_steps_description')} />
      ) : (
        <div style={{ position: 'relative' }}>
          {steps.map((step, i) => {
            const color = ['var(--accent)', 'var(--success)', 'var(--warning)', 'var(--purple)', 'var(--danger)'][i % 5]
            return (
              <div key={step.id} style={{ display: 'flex', gap: 16, marginBottom: 6 }}>
                {/* Línea vertical */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 40, flexShrink: 0 }}>
                  <div style={{ width: 36, height: 36, borderRadius: '50%', background: color + '20', border: `2px solid ${color}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-md)", fontWeight: 800, color, flexShrink: 0 }}>
                    {step.step_order}
                  </div>
                  {i < steps.length - 1 && (
                    <div style={{ width: 2, flex: 1, minHeight: 20, background: 'var(--surface-4)', margin: '4px 0' }} />
                  )}
                </div>

                {/* Card del paso */}
                <div style={{ ...panel, padding: '14px 18px', flex: 1, marginBottom: 4 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>{step.name}</div>
                      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                        {approverTypeLabels(t)[step.approver_type]}
                        {step.approver_role && ` · ${t('approvals.role_prefix')}: ${step.approver_role}`}
                        {step.approver_user_name && ` · ${step.approver_user_name}`}
                        {step.approver_department && ` · ${t('approvals.dept_prefix')}: ${step.approver_department}`}
                      </div>
                      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 4 }}>
                        {t('approvals.timeout_summary', {
                          hours: step.timeout_hours,
                          action: step.on_timeout === 'escalate'
                            ? t('approvals.timeout_waiting')
                            : step.on_timeout === 'auto_approve'
                              ? t('approvals.timeout_auto_approve_short')
                              : t('approvals.timeout_auto_reject_short')
                        })}
                        {step.is_optional && ` · ${t('approvals.optional_short')}`}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button aria-label={t('approvals.edit_step_aria', { name: step.name })} onClick={() => setEditStep(step)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>✏️</button>
                      <button aria-label={t('approvals.delete_step_aria', { name: step.name })} onClick={() => { openConfirmGlobal({ message: t('approvals.delete_step_confirm', { name: step.name }), onConfirm: () => delStep(step.id), danger: true }) }} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}

          {/* Resultado final */}
          <div style={{ display: 'flex', gap: 16 }}>
            <div style={{ width: 40, flexShrink: 0, display: 'flex', justifyContent: 'center' }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'var(--success-bg)', border: '2px solid var(--success)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-lg)" }}>✓</div>
            </div>
            <div style={{ ...panel, padding: '12px 18px', flex: 1, borderColor: 'var(--success-border)' }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--success)' }}>{t('approvals.approved_auto_title')}</div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>{t('approvals.approved_auto_desc')}</div>
            </div>
          </div>
        </div>
      )}

      {(showStep || editStep) && (
        <StepModal workflowId={workflowId} step={editStep} onClose={() => { setShowStep(false); setEditStep(null) }} />
      )}
    </div>
  )
}

// ── Tab de mis solicitudes pendientes ─────────────────────────────────────────
function MyPendingTab() {
  const t = useAppT()
  const { user, loading } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [entityFilter, setEntityFilter] = useState('all')
  const [sortMode, setSortMode] = useState('oldest') // oldest | newest

  const { data: pending = [], isLoading } = useQuery({
    queryKey: ['approvals-pending-me'],
    queryFn: () => approvalsApi.pendingMyAction().then(r => r.data),
    refetchInterval: 30000,
    enabled: !loading && !!user,
  })

  const { mutate: decide, isPending: deciding } = useMutation({
    mutationFn: ({ id, decision, note }) => approvalsApi.decide(id, { decision, note }),
    onSuccess: () => {
      qc.invalidateQueries(['approvals-pending-me'])
      // Cascade to the affected entity caches (approval could be for timesheets, expenses, or absences)
      qc.invalidateQueries(['timesheets-pending'])
      qc.invalidateQueries(['timesheets-mine'])
      qc.invalidateQueries(['expenses-pending'])
      qc.invalidateQueries(['expenses-my'])
      qc.invalidateQueries(['absences-pending'])
      qc.invalidateQueries(['team-absences'])
      toast.success(t('approvals.decision_registered'))
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const [bulkApproving, setBulkApproving] = useState(false)

  const handleBulkApprove = async () => {
    if (selectedIds.size === 0) return
    setBulkApproving(true)
    try {
      await Promise.all(Array.from(selectedIds).map(id => approvalsApi.decide(id, { decision: 'approved' })))
      toast.success(t('approvals.approve_selected', { count: selectedIds.size }))
      setSelectedIds(new Set())
      qc.invalidateQueries(['approvals-pending-me'])
      qc.invalidateQueries(['timesheets-pending'])
      qc.invalidateQueries(['timesheets-mine'])
      qc.invalidateQueries(['expenses-pending'])
      qc.invalidateQueries(['expenses-my'])
      qc.invalidateQueries(['absences-pending'])
      qc.invalidateQueries(['team-absences'])
    } catch (e) {
      toast.error(extractErr(e, t('approvals.bulk_approval_error')))
    } finally {
      setBulkApproving(false)
    }
  }

  const toggleSelect = (id) => setSelectedIds(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const toggleAll = () => setSelectedIds(prev =>
    prev.size === queue.length ? new Set() : new Set(queue.map(r => r.id))
  )

  const queue = pending
    .filter(r => entityFilter === 'all' ? true : r.entity_type === entityFilter)
    .sort((a, b) => {
      const ta = new Date(a.created_at || 0).getTime()
      const tb = new Date(b.created_at || 0).getTime()
      return sortMode === 'oldest' ? ta - tb : tb - ta
    })

  const statsByEntity = pending.reduce((acc, r) => {
    acc[r.entity_type] = (acc[r.entity_type] || 0) + 1
    return acc
  }, {})

  if (isLoading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-2)' }}>{t('approvals.loading')}</div>

  if (pending.length === 0) return (
    <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-2)' }}>
      <div style={{ fontSize: "var(--text-5xl)", marginBottom: 12 }}>✅</div>
      <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, marginBottom: 4 }}>{t('approvals.no_pending_title')}</div>
      <div style={{ fontSize: "var(--text-base)" }}>{t('approvals.no_pending_desc')}</div>
    </div>
  )

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10, marginBottom: 14 }}>
        <div style={{ ...panel, padding: '10px 12px' }}>
          <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t('approvals.total_pending')}</div>
          <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: 'var(--warning)' }}>{pending.length}</div>
        </div>
        {Object.entries(statsByEntity).slice(0, 3).map(([k, count]) => {
          const entity = entityLabels(t)[k] || { label: k, icon: '○', color: 'var(--text-2)' }
          return (
            <div key={k} style={{ ...panel, padding: '10px 12px' }}>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{entity.icon} {entity.label}</div>
              <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: entity.color }}>{count}</div>
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <select aria-label={t('approvals.filter_by_entity')} value={entityFilter} onChange={e => setEntityFilter(e.target.value)} style={{ ...inp, width: 220 }}>
          <option value="all">{t('approvals.all_entities')}</option>
          {Object.entries(entityLabels(t)).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <select aria-label={t('approvals.sort_requests')} value={sortMode} onChange={e => setSortMode(e.target.value)} style={{ ...inp, width: 220 }}>
          <option value="oldest">{t('approvals.sort_oldest')}</option>
          <option value="newest">{t('approvals.sort_newest')}</option>
        </select>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <label htmlFor="approvals-select-all" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: "var(--text-base)", color: 'var(--text-2)', cursor: 'pointer' }}>
          <input
            id="approvals-select-all"
            type="checkbox"
            aria-label={t('approvals.select_all_filtered')}
            checked={queue.length > 0 && selectedIds.size === queue.length}
            onChange={toggleAll}
            style={{ width: 15, height: 15, cursor: 'pointer', accentColor: 'var(--accent)' }}
          />
          {selectedIds.size === 0
            ? t('approvals.queue_for_approval', { count: queue.length })
            : t('approvals.selected_of_total', { selected: selectedIds.size, total: queue.length })}
        </label>
        {selectedIds.size > 0 && (
          <Button size="sm" onClick={handleBulkApprove} loading={bulkApproving}>
            {t('approvals.approve_selected', { count: selectedIds.size })}
          </Button>
        )}
      </div>
      {queue.map(req => {
        const entity = entityLabels(t)[req.entity_type] || { label: req.entity_type, icon: '○', color: 'var(--text-2)' }
        const ageHours = Math.max(0, Math.floor((Date.now() - new Date(req.created_at || Date.now()).getTime()) / 3600000))
        const isUrgent = ageHours >= 24
        return (
          <div key={req.id} style={{ background: selectedIds.has(req.id) ? 'var(--surface-3)' : 'var(--surface-2)', border: `1px solid ${selectedIds.has(req.id) ? 'var(--accent)' : isUrgent ? 'rgba(245,158,11,0.35)' : 'var(--surface-4)'}`, borderRadius: 12, padding: '16px 20px', marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <input
                type="checkbox"
                aria-label={t('approvals.select_request_aria', { name: req.entity_summary || req.entity_id })}
                checked={selectedIds.has(req.id)}
                onChange={() => toggleSelect(req.id)}
                style={{ width: 15, height: 15, marginTop: 4, cursor: 'pointer', flexShrink: 0, accentColor: 'var(--accent)' }}
              />
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: "var(--text-sm)", padding: '2px 8px', borderRadius: 20, background: entity.color + '20', color: entity.color, fontWeight: 700 }}>
                    {entity.icon} {entity.label}
                  </span>
                  {req.step_name && (
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{t('approvals.step_n', { order: req.step_order })}: {req.step_name}</span>
                  )}
                </div>
                <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>
                  {req.entity_summary || req.entity_id}
                </div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                  {t('approvals.request_by')}: {req.requester_name} · {req.created_at}
                </div>
                {isUrgent && (
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--warning)', marginTop: 4, fontWeight: 700 }}>
                    {t('approvals.pending_since', { hours: ageHours })}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                <button
                  aria-label={t('approvals.reject_request_aria', { name: req.entity_summary || req.entity_id })}
                  onClick={() => decide({ id: req.id, decision: 'rejected', note: '' })}
                  disabled={deciding}
                  style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 8, padding: '7px 14px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600 }}>
                  {t('approvals.reject_action')}
                </button>
                <Button
                  size="sm"
                  onClick={() => decide({ id: req.id, decision: 'approved' })}
                  loading={deciding}>
                  {t('approvals.approve_action')}
                </Button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function ApprovalsPage() {
  const createIdPrefix = useId()
  const t = useAppT()
  const { user, loading } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab]           = useState('pending')   // pending | workflows | stats
  const [selected, setSelected] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', entity_type: 'timesheet', is_default: false })
  const canQueryProtected = !loading && !!user

  const { data: workflows = [], isLoading } = useQuery({
    queryKey: ['approval-workflows'],
    queryFn: () => approvalsApi.listWorkflows().then(r => r.data),
    enabled: canQueryProtected && tab === 'workflows',
  })

  const { data: stats } = useQuery({
    queryKey: ['approval-stats'],
    queryFn: () => approvalsApi.stats().then(r => r.data),
    enabled: canQueryProtected && tab === 'workflows',
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: approvalsApi.createWorkflow,
    onSuccess: (res) => {
      qc.invalidateQueries(['approval-workflows'])
      setShowCreate(false)
      setSelected(res.data.id)
      toast.success(t('approvals.workflow_created'))
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const { mutate: del } = useMutation({
    mutationFn: approvalsApi.deleteWorkflow,
    onSuccess: () => { qc.invalidateQueries(['approval-workflows']); toast.success(t('approvals.workflow_deleted')) },

    onError: e => toast.error(extractErr(e, t('approvals.error_generic')))
  })

  if (selected) return <WorkflowDetail workflowId={selected} onBack={() => setSelected(null)} />

  return (
    <PageShell>
      <PageHeader icon={<CheckCircle size={18} />} title={t('approvals.title')} subtitle={t('approvals.subtitle')} />

      {/* KPIs */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
          {[
            { label: t('approvals.pending'), value: stats.pending, color: 'var(--warning)' },
            { label: t('approvals.approved'), value: stats.approved, color: 'var(--success)' },
            { label: t('approvals.rejected'), value: stats.rejected, color: 'var(--danger)' },
            { label: t('approvals.active_flows'), value: workflows.filter(w => w.is_active).length, color: 'var(--accent)' },
          ].map(k => (
            <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 18px', textAlign: 'center' }}>
              <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, color: k.color, fontFamily: 'var(--font-mono)' }}>{k.value}</div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 4 }}>{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <Tabs
        items={[
          { id: 'pending',   label: t('approvals.my_pending'), count: stats?.pending },
          { id: 'workflows', label: t('approvals.tab_workflows') },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel={t('approvals.sections_aria')}
        style={{ marginBottom: 20 }}
      />

      {/* Tab pendientes */}
      {tab === 'pending' && <div id="approvals-panel-pending" role="tabpanel" aria-labelledby="approvals-tab-pending"><MyPendingTab /></div>}

      {/* Tab flujos */}
      {tab === 'workflows' && (
        <div id="approvals-panel-workflows" role="tabpanel" aria-labelledby="approvals-tab-workflows">
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
            <Button onClick={() => setShowCreate(true)}>{t('approvals.new_workflow')}</Button>
          </div>

          {isLoading ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-2)' }}>{t('approvals.loading')}</div>
          ) : workflows.length === 0 ? (
            <EmptyState icon="✅" title={t('approvals.no_workflows')}
              description={t('approvals.workflows_description')} />
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
              {Object.entries(entityLabels(t)).map(([entityType, cfg]) => {
                const entityFlows = workflows.filter(w => w.entity_type === entityType)
                if (entityFlows.length === 0 && tab === 'workflows') return null
                return entityFlows.map(wf => {
                  return (
                    <div key={wf.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelected(wf.id)}
                      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(wf.id) } }}
                      aria-label={t('approvals.workflow_open_aria', { name: wf.name })}
                      style={{
                        background: 'var(--surface-2)', border: `1px solid ${wf.is_active ? cfg.color + '30' : 'var(--surface-4)'}`,
                        borderRadius: 12, padding: '16px 20px', cursor: 'pointer',
                        opacity: wf.is_active ? 1 : 0.6,
                        transition: 'border-color 0.15s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.borderColor = cfg.color + '60'}
                      onMouseLeave={e => e.currentTarget.style.borderColor = wf.is_active ? cfg.color + '30' : 'var(--surface-4)'}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <span style={{ fontSize: "var(--text-xl)" }}>{cfg.icon}</span>
                          <div>
                            <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{wf.name}</div>
                            <div style={{ fontSize: "var(--text-xs)", color: cfg.color }}>{cfg.label}</div>
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: 4 }}>
                          {wf.is_default && <span style={{ fontSize: "var(--text-2xs)", padding: '1px 6px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)', fontWeight: 700 }}>{t('approvals.default_badge')}</span>}
                          {!wf.is_active && <span style={{ fontSize: "var(--text-2xs)", padding: '1px 6px', borderRadius: 4, background: 'var(--danger-bg)', color: 'var(--danger)' }}>{t('approvals.inactive_badge')}</span>}
                        </div>
                      </div>
                      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>
                        {t('approvals.steps_count', { count: wf.step_count, suffix: wf.step_count !== 1 ? t('approvals.steps_suffix_plural') : '' })}
                        {wf.description && ` · ${wf.description}`}
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button aria-label={t('approvals.workflow_delete_aria', { name: wf.name })} onClick={e => { e.stopPropagation(); openConfirmGlobal({ message: t('approvals.workflow_delete_confirm', { name: wf.name }), onConfirm:()=>del(wf.id),danger:true}) }}
                          style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>
                          🗑
                        </button>
                      </div>
                    </div>
                  )
                })
              })}
              {workflows.filter(w => !Object.keys(entityLabels(t)).includes(w.entity_type)).map(wf => (
                <div key={wf.id} role="button" tabIndex={0} onClick={() => setSelected(wf.id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(wf.id) } }} aria-label={t('approvals.workflow_open_aria', { name: wf.name })}
                  style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '16px 20px', cursor: 'pointer' }}>
                  <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{wf.name}</div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{wf.entity_type} · {wf.step_count} {t('approvals.steps_word')}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {showCreate && (
        <Modal open title={t('approvals.new_workflow_title')} onClose={() => setShowCreate(false)} width={480}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
            <div>
              <label htmlFor={`${createIdPrefix}-name`} style={lbl}>{t('approvals.name_required')}</label>
              <input id={`${createIdPrefix}-name`} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={inp} placeholder={t('approvals.workflow_name_placeholder')} />
            </div>
            <div>
              <label htmlFor={`${createIdPrefix}-entity-type`} style={lbl}>{t('approvals.entity_type')}</label>
              <select id={`${createIdPrefix}-entity-type`} value={form.entity_type} onChange={e => setForm(f=>({...f,entity_type:e.target.value}))} style={inp}>
                {Object.entries(entityLabels(t)).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor={`${createIdPrefix}-description`} style={lbl}>{t('approvals.description')}</label>
              <input id={`${createIdPrefix}-description`} value={form.description} onChange={e => setForm(f=>({...f,description:e.target.value}))} style={inp} placeholder={t('approvals.description_placeholder')} />
            </div>
            <label htmlFor={`${createIdPrefix}-is-default`} style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>
              <input id={`${createIdPrefix}-is-default`} type="checkbox" checked={form.is_default} onChange={e => setForm(f=>({...f,is_default:e.target.checked}))} style={{ accentColor: 'var(--accent)' }} />
              {t('approvals.default_flow_label')}
            </label>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowCreate(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>{t('common.cancel')}</button>
            <Button onClick={() => create(form)} loading={creating} disabled={!form.name || creating}>{t('approvals.create_workflow')}</Button>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
