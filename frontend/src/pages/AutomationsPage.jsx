/**
 * AutomationsPage — Visual no-code rule builder + Workflows multi-paso + RPA
 * SI [trigger] [condiciones] ENTONCES [acciones]
 */
import { useId, useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { Bot } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'




import {
  AUTOMATION_TRIGGERS as TRIGGERS,
  AUTOMATION_ACTIONS as ACTIONS,
  AUTOMATION_OPERATORS as OPERATORS,
  AUTOMATION_ACTION_PARAMS as ACTION_PARAMS
} from '../constants/api'

// Derived category lists (referenced by both RuleModal and WorkflowModal)
const TRIGGER_CATEGORIES = [...new Set(Object.values(TRIGGERS).map(t => t.category))]
const ACTION_CATEGORIES  = [...new Set(Object.values(ACTIONS).map(a => a.category))]

const card = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }
const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

// ── Rule card ─────────────────────────────────────────────────────────────────
function RuleCard({ rule, onEdit, onDelete, onTest, onToggle }) {
  const t = useAppT()
  const trigger = TRIGGERS[rule.trigger_type] || { label: rule.trigger_type, icon: '⚙️' }
  const actions = Array.isArray(rule.actions) ? rule.actions : []

  return (
    <div style={{ background: 'var(--surface-2)', border: `1px solid ${rule.is_active ? 'var(--surface-4)' : 'var(--danger-border)'}`, borderRadius: 12, padding: '16px 20px', opacity: rule.is_active ? 1 : 0.6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4 }}>
            <span style={{ fontSize: 16 }}>{trigger.icon}</span>
            <span style={{ fontSize: 14, fontWeight: 700 }}>{rule.name}</span>
            {rule.is_global && <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 4, background: 'var(--purple-bg)', color: 'var(--purple)' }}>GLOBAL</span>}
            {rule.project_name && <span style={{ fontSize: 11, color: 'var(--text-2)' }}>· {rule.project_name}</span>}
          </div>
          {rule.description && <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 8 }}>{rule.description}</div>}
        </div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0, marginLeft: 12 }}>
          <button aria-pressed={rule.is_active} aria-label={`${rule.is_active ? t('automations.pause_btn') : t('automations.activate_btn')} ${rule.name}`} onClick={() => onToggle(rule)}
            style={{ background: rule.is_active ? 'var(--warning-bg)' : 'var(--success-bg)', border: `1px solid ${rule.is_active ? 'rgba(245,158,11,0.25)' : 'rgba(52,211,153,0.25)'}`, borderRadius: 6, padding: '4px 10px', color: rule.is_active ? 'var(--warning)' : 'var(--success)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
            {rule.is_active ? t('automations.pause_btn') : t('automations.activate_btn')}
          </button>
          <button aria-label={`${t('automations.try_btn')} ${rule.name}`} onClick={() => onTest(rule)}
            style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff40', borderRadius: 6, padding: '4px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
            {t('automations.try_btn')}
          </button>
          <button aria-label={`${t('common.edit')} ${rule.name}`} onClick={() => onEdit(rule)}
            style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏</button>
          <button aria-label={`${t('common.delete')} ${rule.name}`} onClick={() => { openConfirmGlobal({ message: t('common.are_you_sure'), onConfirm: () => onDelete(rule.id), danger: true }) }}
            style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
        </div>
      </div>

      {/* Visual rule display */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ background: 'var(--purple-bg)', border: '1px solid #7c3aed40', borderRadius: 8, padding: '6px 12px', fontSize: 12 }}>
          <span style={{ color: 'var(--purple)', fontWeight: 700 }}>{t('automations.si_label')} </span>
          <span style={{ color: 'var(--text-1)' }}>{trigger.icon} {t('automations.trig_' + rule.trigger_type, trigger.label)}</span>
          {rule.trigger_conditions && (
            <span style={{ color: 'var(--text-2)' }}>
              {' '}· {rule.trigger_conditions.field} {t('automations.op_' + rule.trigger_conditions.operator, rule.trigger_conditions.operator)} <strong style={{ color: 'var(--text-1)' }}>{rule.trigger_conditions.value}</strong>
            </span>
          )}
        </div>
        <span style={{ fontSize: 18, color: 'var(--text-3)' }}>→</span>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {actions.map((a, i) => {
            const aCfg = ACTIONS[a.type] || { label: a.type, icon: '⚙️' }
            return (
              <div key={i} style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 8, padding: '6px 12px', fontSize: 12 }}>
                <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{t('automations.entonces_label')}</span>
                <span style={{ color: 'var(--text-1)' }}>{aCfg.icon} {t('automations.act_' + a.type, aCfg.label)}</span>
                {a.params?.message && <span style={{ color: 'var(--text-2)' }}> · &quot;{a.params.message.slice(0, 40)}&quot;</span>}
              </div>
            )
          })}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16, marginTop: 10, fontSize: 11, color: 'var(--text-3)' }}>
        <span>⚡ {rule.run_count || 0} {t('automations.executions')}</span>
        {rule.last_run_at && <span>{t('automations.last_exec')}: {rule.last_run_at}</span>}
        {rule.last_error && <span style={{ color: 'var(--danger)' }}>⚠ {rule.last_error.slice(0, 60)}</span>}
      </div>
    </div>
  )
}

// ── Rule editor modal ─────────────────────────────────────────────────────────
function RuleModal({ rule, onClose }) {
  const t = useAppT()
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!rule
  const [form, setForm] = useState({
    name: rule?.name || '',
    description: rule?.description || '',
    project_id: rule?.project_id || '',
    is_global: rule?.is_global ?? false,
    trigger_type: rule?.trigger_type || 'task_status_changed',
    trigger_conditions: rule?.trigger_conditions || null,
    actions: rule?.actions || [{ type: 'create_alert', params: { message: '', severity: 'warning' } }],
  })
  const [hasCondition, setHasCondition] = useState(!!rule?.trigger_conditions)
  const [condition, setCondition] = useState(rule?.trigger_conditions || { field: '', operator: 'equals', value: '' })

  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data) })
  const projects = Array.isArray(projRaw) ? projRaw : []

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? api.patch(`/automations/${rule.id}`, d) : api.post('/automations', d),
    onSuccess: () => { qc.invalidateQueries(['automations']); onClose() },
    onError: e => toast.error(extractErr(e, t('common.error'))),
  })

  const addAction = () => setForm(f => ({ ...f, actions: [...f.actions, { type: 'create_alert', params: { message: '', severity: 'info' } }] }))
  const removeAction = i => setForm(f => ({ ...f, actions: f.actions.filter((_, idx) => idx !== i) }))
  const updateAction = (i, field, value) => setForm(f => {
    const actions = [...f.actions]
    if (field === 'type') actions[i] = { type: value, params: {} }
    else {
      actions[i] = { ...actions[i], params: { ...actions[i].params, [field]: value } }
    }
    return { ...f, actions }
  })

  const fields = TRIGGER_FIELDS[form.trigger_type] || []

  const handleSave = () => {
    const payload = {
      ...form,
      trigger_conditions: hasCondition && condition.field ? condition : null,
    }
    mutate(payload)
  }

  return (
    <Modal open title={isEdit ? t('automations.edit_rule_title') : t('automations.new_rule_title')} onClose={onClose} width={680}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Basic info */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div style={{ gridColumn: '1/-1' }}>
            <label htmlFor={`${idPrefix}-name`} style={ls}>{t('automations.rule_name_lbl')}</label>
            <input id={`${idPrefix}-name`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={fs} placeholder={t('automations.rule_name_lbl')} />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-description`} style={ls}>{t('automations.description')}</label>
            <input id={`${idPrefix}-description`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={fs} />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-project`} style={ls}>{t('automations.project_lbl')}</label>
            <select id={`${idPrefix}-project`} value={form.project_id} onChange={e => setForm(f => ({ ...f, project_id: e.target.value, is_global: !e.target.value }))} style={fs}>
              <option value="">{t('automations.project_global')}</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
          </div>
        </div>

        {/* TRIGGER */}
        <div style={{ background: 'var(--purple-bg)', border: '1px solid #7c3aed30', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--purple)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {t('automations.si_label')}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 10 }}>
            <div>
              <label htmlFor={`${idPrefix}-trigger`} style={ls}>{t('automations.trigger_lbl')}</label>
              <select id={`${idPrefix}-trigger`} value={form.trigger_type} onChange={e => setForm(f => ({ ...f, trigger_type: e.target.value }))} style={fs}>
                {TRIGGER_CATEGORIES.map(cat => (
                  <optgroup key={cat} label={t('automations.cat_' + cat.toLowerCase().replace(/ /g, '_'), cat)}>
                    {Object.entries(TRIGGERS).filter(([, v]) => v.category === cat).map(([k, v]) => (
                      <option key={k} value={k}>{v.icon} {t('automations.trig_' + k, v.label)}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>

            {/* Condition */}
            <div>
              <label htmlFor={`${idPrefix}-has-condition`} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: 'var(--text-2)' }}>
                <input id={`${idPrefix}-has-condition`} type="checkbox" checked={hasCondition} onChange={e => setHasCondition(e.target.checked)} />
                {t('automations.add_condition')}
              </label>
            </div>
            {hasCondition && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, padding: '10px 14px', background: 'var(--surface-3)', borderRadius: 8 }}>
                <div>
                  <label htmlFor={`${idPrefix}-condition-field`} style={ls}>{t('automations.field_lbl')}</label>
                  <select id={`${idPrefix}-condition-field`} value={condition.field} onChange={e => setCondition(c => ({ ...c, field: e.target.value }))} style={fs}>
                    <option value="">{t('automations.select_lbl')}</option>
                    {fields.map(f => <option key={f} value={f}>{f}</option>)}
                    <option value="budget_pct">budget_pct (%)</option>
                    <option value="risk_score">risk_score</option>
                    <option value="priority">priority</option>
                    <option value="status">status</option>
                  </select>
                </div>
                <div>
                  <label htmlFor={`${idPrefix}-condition-operator`} style={ls}>{t('automations.operator_lbl')}</label>
                  <select id={`${idPrefix}-condition-operator`} value={condition.operator} onChange={e => setCondition(c => ({ ...c, operator: e.target.value }))} style={fs}>
                    {OPERATORS.map(o => <option key={o.value} value={o.value}>{t('automations.op_' + o.value, o.label)}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor={`${idPrefix}-condition-value`} style={ls}>{t('automations.value_lbl')}</label>
                  <input id={`${idPrefix}-condition-value`} value={condition.value} onChange={e => setCondition(c => ({ ...c, value: e.target.value }))} style={fs} placeholder={t('automations.value_lbl')} />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ACTIONS */}
        <div style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {t('automations.entonces_label')}
          </div>
          {form.actions.map((action, i) => {
            const paramDefs = ACTION_PARAMS[action.type] || []
            return (
              <div key={i} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 14px', marginBottom: 10, position: 'relative' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 10, marginBottom: paramDefs.length > 0 ? 10 : 0 }}>
                  <div>
                    <label style={ls}>{t('automations.action_lbl')} {i + 1}</label>
                    <select value={action.type} onChange={e => updateAction(i, 'type', e.target.value)} style={fs}>
                      {ACTION_CATEGORIES.map(cat => (
                        <optgroup key={cat} label={t('automations.cat_' + cat.toLowerCase().replace(/ /g, '_'), cat)}>
                          {Object.entries(ACTIONS).filter(([,v]) => v.category === cat).map(([k, v]) => (
                            <option key={k} value={k}>{v.icon} {t('automations.act_' + k, v.label)}</option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </div>
                  {form.actions.length > 1 && (
                    <button aria-label={`${t('common.delete')} ${i + 1}`} onClick={() => removeAction(i)}
                      style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 16, alignSelf: 'flex-end', paddingBottom: 8 }}>×</button>
                  )}
                </div>
                {paramDefs.length > 0 && (
                  <div style={{ display: 'grid', gridTemplateColumns: paramDefs.length > 1 ? `repeat(${Math.min(paramDefs.length, 3)}, 1fr)` : '1fr', gap: 10 }}>
                    {paramDefs.map(param => (
                      <div key={param.key}>
                        <label style={ls}>{t('automations.param_' + param.key, param.label)}</label>
                        {param.type === 'select' ? (
                          <select value={action.params?.[param.key] || ''} onChange={e => updateAction(i, param.key, e.target.value)} style={fs}>
                            <option value="">{t('automations.select_lbl')}</option>
                            {param.options.map(o => <option key={o} value={o}>{o}</option>)}
                          </select>
                        ) : (
                          <input value={action.params?.[param.key] || ''} onChange={e => updateAction(i, param.key, e.target.value)} style={fs} placeholder={t('automations.param_' + param.key, param.label)} />
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
          <button aria-label={t('automations.add_action')} onClick={addAction}
            style={{ background: 'transparent', border: '1px dashed #00d4ff40', borderRadius: 8, padding: '7px 16px', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', width: '100%' }}>
            {t('automations.add_action')}
          </button>
        </div>

        {/* Save */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} loading={isPending} disabled={isPending || !form.name || form.actions.length === 0}>
            {isPending ? t('common.saving') : isEdit ? t('automations.save_rule_btn') : t('automations.create_rule_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Executions modal ──────────────────────────────────────────────────────────
function ExecutionsModal({ rule, onClose }) {
  const t = useAppT()
  const { data, isLoading } = useQuery({
    queryKey: ['automation_executions', rule.id],
    queryFn: () => api.get(`/automations/${rule.id}/executions`).then(r => r.data),
    enabled: !!rule?.id,
  })
  return (
    <Modal open title={t('automations.executions_title')} onClose={onClose} width={700}>
      <div style={{ minHeight: 200 }}>
        {isLoading ? <Spinner /> : (
          <table className="table">
            <thead>
              <tr>
                <th>{t('automations.exec_date')}</th>
                <th>{t('automations.exec_status')}</th>
                <th>{t('automations.exec_result')}</th>
              </tr>
            </thead>
            <tbody>
              {data?.map(exec => (
                <tr key={exec.id}>
                  <td>{formatDate(exec.created_at)}</td>
                  <td>{t('automations.exec_status_' + exec.status, exec.status)}</td>
                  <td>{exec.result}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Modal>
  )
}

// ── WorkflowModal (create + edit) ─────────────────────────────────────────────
const STEP_ICONS = { action:'⚡', condition:'🔀', wait:'⏱', webhook:'🔗', notify:'🔔', rpa:'🤖' }

function StepConfig({ step, onChange }) {
  const t = useAppT()
  const paramDefs = ACTION_PARAMS[step.type] || []
  return (
    <div style={{ display: 'grid', gridTemplateColumns: paramDefs.length > 1 ? `repeat(${Math.min(paramDefs.length, 3)}, 1fr)` : '1fr', gap: 10 }}>
      {paramDefs.map(param => (
        <div key={param.key}>
          <label style={ls}>{t('automations.param_' + param.key, param.label)}</label>
          {param.type === 'select' ? (
            <select value={step.params?.[param.key] || ''} onChange={e => onChange(param.key, e.target.value)} style={fs}>
              <option value="">{t('automations.select_lbl')}</option>
              {param.options.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : (
            <input value={step.params?.[param.key] || ''} onChange={e => onChange(param.key, e.target.value)} style={fs} placeholder={t('automations.param_' + param.key, param.label)} />
          )}
        </div>
      ))}
    </div>
  )
}

function WorkflowModal({ workflow, onClose }) {
  const t = useAppT()
  const isEdit = !!workflow
  const [form, setForm] = useState({
    name: workflow?.name || '',
    description: workflow?.description || '',
    steps: workflow?.steps || [{ type: 'create_alert', params: { message: '', severity: 'warning' } }],
  })
  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? api.patch(`/workflows/${workflow.id}`, d) : api.post('/workflows', d),
    onSuccess: onClose,
    onError: e => alert(extractErr(e, t('common.error'))),
  })
  const addStep = () => setForm(f => ({ ...f, steps: [...f.steps, { type: 'create_alert', params: { message: '', severity: 'info' } }] }))
  const removeStep = i => setForm(f => ({ ...f, steps: f.steps.filter((_, idx) => idx !== i) }))
  const updateStep = (i, field, value) => setForm(f => {
    const steps = [...f.steps]
    if (field === 'type') steps[i] = { type: value, params: {} }
    else {
      steps[i] = { ...steps[i], params: { ...steps[i].params, [field]: value } }
    }
    return { ...f, steps }
  })
  const handleSave = () => mutate(form)
  return (
    <Modal open title={isEdit ? t('automations.edit_workflow_title') : t('automations.new_workflow_title')} onClose={onClose} width={680}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div style={{ gridColumn: '1/-1' }}>
            <label style={ls}>{t('automations.workflow_name_lbl')}</label>
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={fs} placeholder={t('automations.workflow_name_lbl')} />
          </div>
          <div>
            <label style={ls}>{t('automations.description')}</label>
            <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={fs} />
          </div>
        </div>
        <div style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {t('automations.steps_label')}
          </div>
          {form.steps.map((step, i) => (
            <div key={i} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 14px', marginBottom: 10, position: 'relative' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 10, marginBottom: 10 }}>
                <div>
                  <label style={ls}>{t('automations.step_lbl')} {i + 1}</label>
                  <select value={step.type} onChange={e => updateStep(i, 'type', e.target.value)} style={fs}>
                    {ACTION_CATEGORIES.map(cat => (
                      <optgroup key={cat} label={t('automations.cat_' + cat.toLowerCase().replace(/ /g, '_'), cat)}>
                        {Object.entries(ACTIONS).filter(([,v]) => v.category === cat).map(([k, v]) => (
                          <option key={k} value={k}>{v.icon} {t('automations.act_' + k, v.label)}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </div>
                {form.steps.length > 1 && (
                  <button aria-label={`${t('common.delete')} ${i + 1}`} onClick={() => removeStep(i)}
                    style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 16, alignSelf: 'flex-end', paddingBottom: 8 }}>×</button>
                )}
              </div>
              <StepConfig step={step} onChange={(field, value) => updateStep(i, field, value)} />
            </div>
          ))}
          <button aria-label={t('automations.add_step')} onClick={addStep}
            style={{ background: 'transparent', border: '1px dashed #00d4ff40', borderRadius: 8, padding: '7px 16px', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', width: '100%' }}>
            {t('automations.add_step')}
          </button>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} loading={isPending} disabled={isPending || !form.name || form.steps.length === 0}>
            {isPending ? t('common.saving') : isEdit ? t('automations.save_workflow_btn') : t('automations.create_workflow_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Workflows Tab ─────────────────────────────────────────────────────────────
function WorkflowsTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingWf, setEditingWf] = useState(null)

  const { data: workflows = [], isLoading } = useQuery({
    queryKey: ['workflows'],
    queryFn: () => api.get('/automation-workflows').then(r => r.data),
  })

  const { mutate: update } = useMutation({
    mutationFn: ({ id, data }) => api.patch(`/automation-workflows/${id}`, data),
    onSuccess: () => qc.invalidateQueries(['workflows']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/automation-workflows/${id}`),
    onSuccess: () => qc.invalidateQueries(['workflows']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const STATUS_CFG = { draft:{ label:'Borrador', color:'var(--text-2)' }, active:{ label:'Activo', color:'var(--success)' }, paused:{ label:'Pausado', color:'var(--warning)' }, archived:{ label:'Archivado', color:'var(--text-3)' } }

  return (
    <div>
      <div style={{ background: 'var(--purple-bg)', border: '1px solid #7c3aed30', borderRadius: 10, padding: '14px 18px', marginBottom: 20, fontSize: 13 }}>
        <div style={{ fontWeight: 700, color: 'var(--purple)', marginBottom: 4 }}>⚡ {t('automations.workflows_rpa_title')}</div>
        <div style={{ color: 'var(--text-2)' }}>
          {t('automations.workflows_rpa_desc', {
            strong: (chunks) => <strong style={{ color: 'var(--text-1)' }}>{chunks}</strong>,
            em: (chunks) => <em>{chunks}</em>,
          })}
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button onClick={() => setShowModal(true)}>+ {t('automations.new_workflow_btn')}</Button>
      </div>

      {isLoading ? <Spinner /> : workflows.length === 0 ? (
        <EmptyState icon="⚡" title={t('automations.no_workflows_title')} description={t('automations.no_workflows_desc')} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {workflows.map(wf => {
            const cfg = STATUS_CFG[wf.status] || { label: wf.status, color: 'var(--text-2)' }
            const triggerCfg = TRIGGERS[wf.trigger_type] || { icon: '⚙️', label: wf.trigger_type }
            return (
              <div key={wf.id} style={{ ...card, padding: '18px 22px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4 }}>
                      <span style={{ fontSize: 15, fontWeight: 700 }}>{wf.name}</span>
                      <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: cfg.color + '20', color: cfg.color }}>{t('automations.status_' + wf.status, cfg.label)}</span>
                      {wf.is_global && <span style={{ fontSize: 10, padding: '2px 6px', background: 'var(--purple-bg)', color: 'var(--purple)', borderRadius: 4 }}>GLOBAL</span>}
                    </div>
                    {wf.description && <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{wf.description}</div>}
                    <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
                      {triggerCfg.icon} {triggerCfg.label} · {wf.steps?.length || 0} pasos · {wf.run_count || 0} ejecuciones
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button aria-pressed={wf.status === 'active'} aria-label={`${wf.status === 'active' ? t('automations.pause_workflow_btn') : t('automations.activate_workflow_btn')} ${wf.name}`} onClick={() => update({ id: wf.id, data: { status: wf.status === 'active' ? 'paused' : 'active' } })}
                      style={{ background: wf.status === 'active' ? 'var(--warning-bg)' : 'var(--success-bg)', border: `1px solid ${wf.status === 'active' ? 'rgba(245,158,11,0.25)' : 'rgba(52,211,153,0.25)'}`, borderRadius: 6, padding: '4px 10px', color: wf.status === 'active' ? 'var(--warning)' : 'var(--success)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
                      {wf.status === 'active' ? '⏸ ' + t('automations.pause_workflow_btn') : '▶ ' + t('automations.activate_workflow_btn')}
                    </button>
                    <button aria-label={`${t('automations.edit_workflow_btn')} ${wf.name}`} onClick={() => setEditingWf(wf)}
                      style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏ {t('automations.edit_workflow_btn')}</button>
                    <button aria-label={`${t('automations.delete_workflow_btn')} ${wf.name}`} onClick={() => { openConfirmGlobal({ message: t('automations.delete_workflow_confirm'), onConfirm: () => del(wf.id), danger: true }) }}
                      style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                  </div>
                </div>

                {/* Steps visual */}
                <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
                  {wf.steps?.map((s, i) => (
                    <div key={s.id || i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <div style={{ background: 'var(--surface-4)', borderRadius: 6, padding: '4px 10px', fontSize: 12, color: 'var(--text-1)' }}>
                        {STEP_ICONS[s.step_type] || '⚡'} {s.name || s.step_type}
                      </div>
                      {i < wf.steps.length - 1 && <span style={{ color: 'var(--text-3)', fontSize: 14 }}>→</span>}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {showModal && <WorkflowModal onClose={() => setShowModal(false)} />}
      {editingWf && <WorkflowModal workflow={editingWf} onClose={() => setEditingWf(null)} />}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AutomationsPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('rules')  // rules | workflows
  const [editing, setEditing] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [execHistory, setExecHistory] = useState(null)
  const [filterActive, setFilterActive] = useState(null)
  const [testResult, setTestResult] = useState(null)

  const { data: raw = [], isLoading } = useQuery({
    queryKey: ['automations'],
    queryFn: () => api.get('/automations').then(r => r.data),
    refetchInterval: 60000,
  })
  const rules = Array.isArray(raw) ? raw : []

  const { data: templates = [] } = useQuery({
    queryKey: ['auto-templates'],
    queryFn: () => api.get('/automations/templates/list').then(r => r.data),
    enabled: showTemplates,
  })

  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/automations/${id}`),
    onSuccess: () => qc.invalidateQueries(['automations']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }) => api.patch(`/automations/${id}`, { is_active: active }),
    onSuccess: () => qc.invalidateQueries(['automations']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: test } = useMutation({
    mutationFn: id => api.post(`/automations/${id}/test`).then(r => r.data),
    onSuccess: (data) => setTestResult(data),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: createFromTemplate } = useMutation({
    mutationFn: tpl => api.post('/automations', {
      name: tpl.name,
      trigger_type: tpl.trigger_type,
      trigger_conditions: tpl.trigger_conditions,
      actions: tpl.actions,
      is_global: true,
    }),
    onSuccess: () => { qc.invalidateQueries(['automations']); setShowTemplates(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const filtered = filterActive === null ? rules : rules.filter(r => r.is_active === filterActive)
  const active = rules.filter(r => r.is_active).length

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<Bot size={18} />}
        title={t('automations.title')}
        subtitle={t('automations.subtitle')}
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setShowTemplates(true)}
              style={{ background: 'transparent', border: '1px solid #7c3aed40', borderRadius: 8, padding: '9px 16px', color: 'var(--purple)', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit', fontWeight: 600 }}>
              📋 {t('automations.templates_btn')}
            </button>
            <Button onClick={() => setShowCreate(true)}>＋ {t('automations.new_rule_btn')}</Button>
          </div>
        }
      />

      {/* Tab selector */}
      <div role="tablist" aria-label={t('automations.sections_aria_lbl')} style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {[
          ['rules', '⚙️ ' + t('automations.rules_tab')],
          ['workflows', '⚡ ' + t('automations.workflows_tab')],
        ].map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} aria-controls={`automations-panel-${id}`} id={`automations-tab-${id}`} onClick={() => setTab(id)}
            style={{ padding: '8px 16px', borderRadius: 8, border: `1px solid ${tab === id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: tab === id ? 'var(--accent-muted)' : 'transparent', color: tab === id ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'workflows' && <div id="automations-panel-workflows" role="tabpanel" aria-labelledby="automations-tab-workflows"><WorkflowsTab /></div>}

      {tab === 'rules' && <div id="automations-panel-rules" role="tabpanel" aria-labelledby="automations-tab-rules">
      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
        {[
          { label: t('automations.stats_active'), value: active, color: 'var(--accent)', icon: '⚡' },
          { label: t('automations.stats_paused'), value: rules.length - active, color: 'var(--text-2)', icon: '⏸' },
          { label: t('automations.stats_total_exec'), value: rules.reduce((s, r) => s + (r.run_count || 0), 0), color: 'var(--success)', icon: '▷' },
          { label: t('automations.stats_total_rules'), value: rules.length, color: 'var(--purple)', icon: '⚙️' },
        ].map(({ label, value, color, icon }) => (
          <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, padding: '14px 18px' }}>
            <div style={{ fontSize: 20, marginBottom: 6 }}>{icon}</div>
            <div style={{ fontSize: 24, fontWeight: 800, color }}>{value}</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {[
          [null, t('automations.filter_all')],
          [true, t('automations.filter_active')],
          [false, t('automations.filter_paused')],
        ].map(([val, label]) => (
          <button key={String(val)} aria-pressed={filterActive === val} onClick={() => setFilterActive(val)}
            style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${filterActive === val ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: filterActive === val ? 'var(--accent-muted)' : 'transparent', color: filterActive === val ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {/* Rules list */}
      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState
          icon="⚙️"
          title={t('automations.no_rules_title')}
          description={t('automations.no_rules_desc')}
          action={<Button onClick={() => setShowTemplates(true)}>{t('automations.view_templates_btn')}</Button>}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {filtered.map(rule => (
            <RuleCard key={rule.id} rule={rule}
              onEdit={r => setEditing(r)}
              onDelete={id => del(id)}
              onTest={r => test(r.id)}
              onToggle={r => toggle({ id: r.id, active: !r.is_active })}
            />
          ))}
        </div>
      )}

      {/* Modals */}
      {showCreate && <RuleModal onClose={() => setShowCreate(false)} />}
      {editing && <RuleModal rule={editing} onClose={() => setEditing(null)} />}
      {execHistory && <ExecutionsModal rule={execHistory} onClose={() => setExecHistory(null)} />}

      {/* Test result */}
      {testResult && (
        <Modal open title={t('automations.test_result_title')} onClose={() => setTestResult(null)} width={500}>
          <div style={{ padding: 4 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--success)', marginBottom: 12 }}>✓ {t('automations.test_rule_success')}</div>
            <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: 14 }}>
              {(testResult.results || []).map((r, i) => (
                <div key={i} style={{ fontSize: 12, padding: '4px 0', borderBottom: '1px solid #1e2d4530', color: r.ok ? 'var(--success)' : 'var(--danger)' }}>
                  {r.ok ? '✓' : '✗'} {r.action}: {r.ok ? t('automations.executed') : r.error}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 14 }}>
              <Button onClick={() => setTestResult(null)}>{t('common.close')}</Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Templates modal */}
      {showTemplates && (
        <Modal open title={t('automations.templates_title')} onClose={() => setShowTemplates(false)} width={680}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {templates.map(tpl => {
              const trigger = TRIGGERS[tpl.trigger_type] || { icon: '⚙️', label: tpl.trigger_type }
              return (
                <div key={tpl.id} style={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 10, padding: '14px 16px' }}>
                  <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{tpl.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 10 }}>
                    {trigger.icon} {trigger.label}
                    {tpl.trigger_conditions && ` · ${tpl.trigger_conditions.field} ${tpl.trigger_conditions.operator} ${tpl.trigger_conditions.value}`}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                    {tpl.actions.map((a, i) => (
                      <span key={i} style={{ fontSize: 11, padding: '2px 7px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)' }}>{aCfg.icon} {aCfg.label}</span>
                    ))}
                  </div>
                  <button aria-label={`Usar plantilla ${tpl.name}`} onClick={() => createFromTemplate(tpl)}
                    style={{ background: 'linear-gradient(135deg,#00d4ff,#7c3aed)', border: 'none', borderRadius: 6, padding: '6px 14px', color: '#fff', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 600, width: '100%' }}>
                    Usar esta plantilla
                  </button>
                </div>
              )
            })}
          </div>
        </Modal>
      )}
      </div>
      }
    </div>
  )
}