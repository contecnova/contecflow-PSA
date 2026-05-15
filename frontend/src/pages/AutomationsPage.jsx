/**
 * AutomationsPage — Visual no-code rule builder + Workflows multi-paso + RPA
 * SI [trigger] [condiciones] ENTONCES [acciones]
 */
import { useId, useMemo, useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, automationsApi, autoWorkflowsApi, workflowsLegacyApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, Tabs, Page } from '../components/ui'
import {
  Bot, FileStack, Plus, Zap, Pause, Play, Settings as SettingsIcon, Search,
} from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'



// ── Triggers — exhaustive catalog ────────────────────────────────────────────
// Todas las categorías y labels se traducen en tiempo de renderizado usando t() y claves de traducción.
const TRIGGERS = {
  task_status_changed:      { icon: '🔄', category: 'tasks' },
  task_created:             { icon: '🆕', category: 'tasks' },
  task_deleted:             { icon: '🗑️', category: 'tasks' },
  task_assigned:            { icon: '👤', category: 'tasks' },
  task_unassigned:          { icon: '👤', category: 'tasks' },
  task_completed:           { icon: '✅', category: 'tasks' },
  task_overdue:             { icon: '⏰', category: 'tasks' },
  task_deadline_approaching:{ icon: '📅', category: 'tasks' },
  task_priority_changed:    { icon: '🔺', category: 'tasks' },
  task_blocked:             { icon: '🚫', category: 'tasks' },
  task_comment_added:       { icon: '💬', category: 'tasks' },
  task_moved_to_sprint:     { icon: '⚡', category: 'tasks' },
  project_status_changed:   { icon: '📁', category: 'projects' },
  project_created:          { icon: '🆕', category: 'projects' },
  project_deadline_approaching: { icon: '📅', category: 'projects' },
  budget_threshold:         { icon: '💰', category: 'projects' },
  budget_overspent:         { icon: '🚨', category: 'projects' },
  risk_score_high:          { icon: '⚠️', category: 'projects' },
  risk_created:             { icon: '⚠️', category: 'projects' },
  phase_completed:          { icon: '🏁', category: 'projects' },
  deliverable_overdue:      { icon: '📦', category: 'projects' },
  change_request_created:   { icon: '⇄',  category: 'projects' },
  member_added:             { icon: '➕', category: 'projects' },
  member_removed:           { icon: '➖', category: 'projects' },
  sprint_started:           { icon: '⚡', category: 'sprints' },
  sprint_ended:             { icon: '🏁', category: 'sprints' },
  sprint_goal_missed:       { icon: '❌', category: 'sprints' },
  sprint_capacity_exceeded: { icon: '📈', category: 'sprints' },
  timesheet_not_submitted:  { icon: '📋', category: 'time' },
  timesheet_submitted:      { icon: '✅', category: 'time' },
  timesheet_rejected:       { icon: '❌', category: 'time' },
  overtime_detected:        { icon: '⏱', category: 'time' },
  imputation_lockout_warning:{ icon: '🔒', category: 'time' },
  date_reached:             { icon: '📅', category: 'time' },
  end_of_week:              { icon: '📆', category: 'time' },
  end_of_month:             { icon: '📆', category: 'time' },
  absence_requested:        { icon: '🌴', category: 'team' },
  absence_approved:         { icon: '✅', category: 'team' },
  absence_rejected:         { icon: '❌', category: 'team' },
  user_created:             { icon: '👤', category: 'team' },
  capacity_threshold:       { icon: '📈', category: 'team' },
  performance_review_due:   { icon: '🌟', category: 'team' },
  certification_expiring:   { icon: '🎒', category: 'team' },
  okr_deadline_approaching: { icon: '🏆', category: 'team' },
  ticket_created:           { icon: '🎫', category: 'service_desk' },
  ticket_sla_at_risk:       { icon: '🚨', category: 'service_desk' },
  ticket_sla_breached:      { icon: '🔴', category: 'service_desk' },
  ticket_escalated:         { icon: '↑',  category: 'service_desk' },
  ticket_resolved:          { icon: '✅', category: 'service_desk' },
  ticket_reopened:          { icon: '🔄', category: 'service_desk' },
  ticket_no_response:       { icon: '⏰', category: 'service_desk' },
  cmdb_asset_expiring:      { icon: '🖥️', category: 'service_desk' },
  expense_submitted:        { icon: '💸', category: 'finance' },
  expense_approved:         { icon: '✅', category: 'finance' },
  invoice_created:          { icon: '🧾', category: 'finance' },
  invoice_overdue:          { icon: '💳', category: 'finance' },
  contract_expiring:        { icon: '📝', category: 'finance' },
  milestone_reached:        { icon: '◎',  category: 'finance' },
  nps_score_low:            { icon: '⭐', category: 'finance' },
  webhook_received:         { icon: '🔗', category: 'integrations' },
  git_pr_merged:            { icon: '⎇',  category: 'integrations' },
  git_pipeline_failed:      { icon: '❌', category: 'integrations' },
  email_received:           { icon: '📧', category: 'integrations' },
  form_submitted:           { icon: '📝', category: 'integrations' },
  api_event:                { icon: '🔌', category: 'integrations' },
}


// Todas las categorías y labels se traducen en tiempo de renderizado usando t() y claves de traducción.
const ACTIONS = {
  create_alert:           { icon: '🔔', category: 'notifications' },
  notify_role:            { icon: '👥', category: 'notifications' },
  notify_user:            { icon: '👤', category: 'notifications' },
  send_email:             { icon: '📧', category: 'notifications' },
  send_webhook:           { icon: '🔗', category: 'integrations' },
  send_teams_message:     { icon: 'Ⓜ',  category: 'integrations' },
  send_slack_message:     { icon: '💬', category: 'integrations' },
  create_jira_issue:      { icon: '🔵', category: 'integrations' },
  change_task_status:     { icon: '🔄', category: 'tasks' },
  change_task_priority:   { icon: '🔺', category: 'tasks' },
  assign_task:            { icon: '👤', category: 'tasks' },
  create_task:            { icon: '🆕', category: 'tasks' },
  change_project_status:  { icon: '📁', category: 'projects' },
  escalate_ticket:        { icon: '↑',  category: 'service_desk' },
  change_ticket_status:   { icon: '🎫', category: 'service_desk' },
  assign_ticket:          { icon: '👤', category: 'service_desk' },
  approve_expense:        { icon: '💸', category: 'finance' },
  rpa_power_automate:     { icon: '🔵', category: 'rpa' },
  rpa_uipath:             { icon: '🤖', category: 'rpa' },
  rpa_zapier:             { icon: '⚡', category: 'rpa' },
  rpa_make:               { icon: '🔧', category: 'rpa' },
  rpa_n8n:                { icon: '🔀', category: 'rpa' },
  rpa_custom_http:        { icon: '🌐', category: 'rpa' },
}

// All operator labels are now translated at render time using t() and translation keys.
const OPERATORS = [
  { value: 'equals' },
  { value: 'not_equals' },
  { value: 'greater_than' },
  { value: 'less_than' },
  { value: 'contains' },
]

const TRIGGER_FIELDS = {
  task_status_changed:    ['status', 'priority', 'project_id'],
  budget_threshold:       ['budget_pct', 'project_id'],
  risk_score_high:        ['risk_score', 'project_id'],
  ticket_created:         ['priority', 'ticket_type', 'support_level'],
  project_status_changed: ['status'],
}

// All param labels are now translated at render time using t() and translation keys.
const ACTION_PARAMS = {
  create_alert:         [{ key: 'message', type: 'text' }, { key: 'severity', type: 'select', options: ['info','warning','critical'] }],
  notify_role:          [{ key: 'role', type: 'select', options: ['admin','pm','employee','hr','team_lead'] }, { key: 'message', type: 'text' }, { key: 'severity', type: 'select', options: ['info','warning','critical'] }],
  notify_user:          [{ key: 'message', type: 'text' }],
  send_email:           [{ key: 'to_role', type: 'select', options: ['admin','pm','employee','hr'] }, { key: 'subject', type: 'text' }, { key: 'body', type: 'text' }],
  send_webhook:         [{ key: 'url', type: 'text' }, { key: 'payload_template', type: 'text' }],
  send_teams_message:   [{ key: 'teams_webhook_url', type: 'text' }, { key: 'message', type: 'text' }],
  send_slack_message:   [{ key: 'slack_webhook_url', type: 'text' }, { key: 'channel', type: 'text' }, { key: 'message', type: 'text' }],
  create_jira_issue:    [{ key: 'jira_project_key', type: 'text' }, { key: 'issue_type', type: 'select', options: ['Bug','Task','Story','Epic'] }, { key: 'summary', type: 'text' }],
  change_task_status:   [{ key: 'status', type: 'select', options: ['todo','in_progress','in_review','done','blocked'] }],
  change_task_priority: [{ key: 'priority', type: 'select', options: ['critical','high','medium','low'] }],
  assign_task:          [{ key: 'assign_to_role', type: 'select', options: ['pm','team_lead','employee'] }],
  create_task:          [{ key: 'task_title', type: 'text' }, { key: 'priority', type: 'select', options: ['critical','high','medium','low'] }, { key: 'assign_to_role', type: 'select', options: ['pm','team_lead','employee'] }],
  change_project_status:[{ key: 'status', type: 'select', options: ['active','on_hold','completed','cancelled'] }],
  escalate_ticket:      [{ key: 'to_level', type: 'select', options: ['l2','l3'] }],
  change_ticket_status: [{ key: 'status', type: 'select', options: ['assigned','in_progress','resolved','closed'] }],
  assign_ticket:        [{ key: 'to_role', type: 'select', options: ['l1','l2','l3'] }],
  approve_expense:      [{ key: 'decision', type: 'select', options: ['approved','rejected'] }, { key: 'comment', type: 'text' }],
  rpa_power_automate:   [{ key: 'flow_url', type: 'text' }, { key: 'payload', type: 'text' }],
  rpa_uipath:           [{ key: 'orchestrator_url', type: 'text' }, { key: 'process_key', type: 'text' }, { key: 'robot_name', type: 'text' }],
  rpa_zapier:           [{ key: 'zap_webhook_url', type: 'text' }, { key: 'payload', type: 'text' }],
  rpa_make:             [{ key: 'make_webhook_url', type: 'text' }, { key: 'payload', type: 'text' }],
  rpa_n8n:              [{ key: 'n8n_webhook_url', type: 'text' }, { key: 'payload', type: 'text' }],
  rpa_custom_http:      [{ key: 'url', type: 'text' }, { key: 'method', type: 'select', options: ['POST','GET','PUT','PATCH'] }, { key: 'headers', type: 'text' }, { key: 'body', type: 'text' }],
}

// Derived category lists (referenced by both RuleModal and WorkflowModal)
const TRIGGER_CATEGORIES = [...new Set(Object.values(TRIGGERS).map(t => t.category))]
const ACTION_CATEGORIES  = [...new Set(Object.values(ACTIONS).map(a => a.category))]

const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

function escapeRegExp(value) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function highlightText(text, term) {
  const value = String(text || '')
  const q = String(term || '').trim()
  if (!q || !value) return value
  const re = new RegExp(`(${escapeRegExp(q)})`, 'ig')
  return value.split(re).map((part, idx) => (
    part.toLowerCase() === q.toLowerCase()
      ? <mark
          key={idx}
          style={{
            background: 'var(--accent-muted)',
            color: 'var(--accent)',
            border: '1px solid var(--accent-border)',
            padding: '0 3px',
            borderRadius: 4,
            fontWeight: 700,
          }}
        >
          {part}
        </mark>
      : <span key={idx}>{part}</span>
  ))
}

// ── Rule card ─────────────────────────────────────────────────────────────────
function RuleCard({ rule, onEdit, onDelete, onTest, onToggle, highlightTerm }) {
  const t = useAppT()
  const trigger = TRIGGERS[rule.trigger_type] || { label: rule.trigger_type, icon: '⚙️' }
  const actions = Array.isArray(rule.actions) ? rule.actions : []

  return (
    <div style={{ background: 'var(--surface-2)', border: `1px solid ${rule.is_active ? 'var(--surface-4)' : 'var(--danger-border)'}`, borderRadius: 12, padding: '16px 20px', opacity: rule.is_active ? 1 : 0.6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4 }}>
            <span style={{ fontSize: "var(--text-lg)" }}>{trigger.icon}</span>
            <span style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{highlightText(rule.name, highlightTerm)}</span>
            {rule.is_global && <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, padding: '1px 6px', borderRadius: 4, background: 'var(--purple-bg)', color: 'var(--purple)' }}>GLOBAL</span>}
            {rule.project_name && <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>· {highlightText(rule.project_name, highlightTerm)}</span>}
          </div>
          {rule.description && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 8 }}>{highlightText(rule.description, highlightTerm)}</div>}
        </div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0, marginLeft: 12 }}>
          <button aria-pressed={rule.is_active} aria-label={`${rule.is_active ? t('automations.pause_btn') : t('automations.activate_btn')} ${rule.name}`} onClick={() => onToggle(rule)}
            style={{ background: rule.is_active ? 'var(--warning-bg)' : 'var(--success-bg)', border: `1px solid ${rule.is_active ? 'rgba(245,158,11,0.25)' : 'rgba(52,211,153,0.25)'}`, borderRadius: 6, padding: '4px 10px', color: rule.is_active ? 'var(--warning)' : 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
            {rule.is_active ? t('automations.pause_btn') : t('automations.activate_btn')}
          </button>
          <button aria-label={`${t('automations.try_btn')} ${rule.name}`} onClick={() => onTest(rule)}
            style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border-strong)', borderRadius: 6, padding: '4px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
            {t('automations.try_btn')}
          </button>
          <button aria-label={`${t('common.edit')} ${rule.name}`} onClick={() => onEdit(rule)}
            style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏</button>
          <button aria-label={`${t('common.delete')} ${rule.name}`} onClick={() => { openConfirmGlobal({ message: t('common.are_you_sure'), onConfirm: () => onDelete(rule.id), danger: true }) }}
            style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
        </div>
      </div>

      {/* Visual rule display */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ background: 'var(--purple-bg)', border: '1px solid var(--purple-border-strong)', borderRadius: 8, padding: '6px 12px', fontSize: "var(--text-sm)" }}>
          <span style={{ color: 'var(--purple)', fontWeight: 700 }}>{t('automations.si_label')} </span>
          <span style={{ color: 'var(--text-1)' }}>{trigger.icon} {highlightText(t('automations.trig_' + rule.trigger_type, trigger.label), highlightTerm)}</span>
          {rule.trigger_conditions && (
            <span style={{ color: 'var(--text-2)' }}>
              {' '}· {rule.trigger_conditions.field} {t('automations.op_' + rule.trigger_conditions.operator)} <strong style={{ color: 'var(--text-1)' }}>{rule.trigger_conditions.value}</strong>
            </span>
          )}
        </div>
        <span style={{ fontSize: "var(--text-lg-em)", color: 'var(--text-3)' }}>→</span>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {actions.map((a, i) => {
            const aCfg = ACTIONS[a.type] || { label: a.type, icon: '⚙️' }
            return (
              <div key={i} style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 8, padding: '6px 12px', fontSize: "var(--text-sm)" }}>
                <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{t('automations.entonces_label')}</span>
                <span style={{ color: 'var(--text-1)' }}>{aCfg.icon} {highlightText(t('automations.act_' + a.type, aCfg.label), highlightTerm)}</span>
                {a.params?.message && <span style={{ color: 'var(--text-2)' }}> · &quot;{a.params.message.slice(0, 40)}&quot;</span>}
              </div>
            )
          })}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16, marginTop: 10, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
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

  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data?.items ?? r.data ?? []) })
  const projects = Array.isArray(projRaw) ? projRaw : []

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? automationsApi.update(rule.id, d) : automationsApi.create(d),
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
        <div style={{ background: 'var(--purple-bg)', border: '1px solid var(--purple-border)', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--purple)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
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
              <label htmlFor={`${idPrefix}-has-condition`} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-base)", color: 'var(--text-2)' }}>
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
        <div style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--accent)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
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
                      style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: "var(--text-lg)", alignSelf: 'flex-end', paddingBottom: 8 }}>×</button>
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
            style={{ background: 'transparent', border: '1px dashed var(--accent-border-strong)', borderRadius: 8, padding: '7px 16px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', width: '100%' }}>
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
    queryFn: () => automationsApi.executions(rule.id).then(r => r.data),
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
  const toast = useToast()
  const isEdit = !!workflow
  const [form, setForm] = useState({
    name: workflow?.name || '',
    description: workflow?.description || '',
    steps: workflow?.steps || [{ type: 'create_alert', params: { message: '', severity: 'warning' } }],
  })
  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? workflowsLegacyApi.update(workflow.id, d) : workflowsLegacyApi.create(d),
    onSuccess: onClose,
    onError: e => toast.error(extractErr(e, t('common.error'))),
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
        <div style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--accent)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
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
                    style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: "var(--text-lg)", alignSelf: 'flex-end', paddingBottom: 8 }}>×</button>
                )}
              </div>
              <StepConfig step={step} onChange={(field, value) => updateStep(i, field, value)} />
            </div>
          ))}
          <button aria-label={t('automations.add_step')} onClick={addStep}
            style={{ background: 'transparent', border: '1px dashed var(--accent-border-strong)', borderRadius: 8, padding: '7px 16px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', width: '100%' }}>
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
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingWf, setEditingWf] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')

  const { data: workflows = [], isLoading } = useQuery({
    queryKey: ['workflows'],
    queryFn: () => autoWorkflowsApi.list().then(r => r.data),
  })

  const { mutate: update } = useMutation({
    mutationFn: ({ id, data }) => autoWorkflowsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries(['workflows']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => autoWorkflowsApi.delete(id),
    onSuccess: () => qc.invalidateQueries(['workflows']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const searchedWorkflows = useMemo(() => {
    const q = searchTerm.trim().toLowerCase()
    if (!q) return workflows
    return workflows.filter((wf) => {
      const inSteps = (Array.isArray(wf.steps) ? wf.steps : []).some((s) => (
        String(s?.name || '').toLowerCase().includes(q) ||
        String(s?.step_type || '').toLowerCase().includes(q)
      ))
      return (
        String(wf.name || '').toLowerCase().includes(q) ||
        String(wf.description || '').toLowerCase().includes(q) ||
        String(wf.trigger_type || '').toLowerCase().includes(q) ||
        String(wf.status || '').toLowerCase().includes(q) ||
        inSteps
      )
    })
  }, [workflows, searchTerm])

  const STATUS_CFG = { draft:{ label:'Borrador', color:'var(--text-2)' }, active:{ label:'Activo', color:'var(--success)' }, paused:{ label:'Pausado', color:'var(--warning)' }, archived:{ label:'Archivado', color:'var(--text-3)' } }

  return (
    <div>
      <div style={{ background: 'var(--purple-bg)', border: '1px solid var(--purple-border)', borderRadius: 10, padding: '14px 18px', marginBottom: 20, fontSize: "var(--text-base)" }}>
        <div style={{ fontWeight: 700, color: 'var(--purple)', marginBottom: 4 }}>⚡ {t('automations.workflows_rpa_title')}</div>
        <div style={{ color: 'var(--text-2)' }}>
          {t('automations.workflows_rpa_desc', {
            strong: (chunks) => <strong style={{ color: 'var(--text-1)' }}>{chunks}</strong>,
            em: (chunks) => <em>{chunks}</em>,
          })}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 10, marginBottom: 16 }}>
        <input
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder={t('automations.search_workflows_placeholder', 'Buscar workflows (nombre, trigger, estado, paso...)')}
          aria-label={t('automations.search_workflows_aria', 'Buscar workflows')}
          style={fs}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button onClick={() => setShowModal(true)}>+ {t('automations.new_workflow_btn')}</Button>
        </div>
      </div>

      {isLoading ? <Spinner /> : searchedWorkflows.length === 0 ? (
        <EmptyState svgIcon={<Zap size={36} />} title={t('automations.no_workflows_title')} description={t('automations.no_workflows_desc')} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {searchedWorkflows.map(wf => {
            const cfg = STATUS_CFG[wf.status] || { label: wf.status, color: 'var(--text-2)' }
            const triggerCfg = TRIGGERS[wf.trigger_type] || { icon: '⚙️', label: wf.trigger_type }
            return (
              <div key={wf.id} style={{ ...card, padding: '18px 22px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4 }}>
                      <span style={{ fontSize: "var(--text-md-em)", fontWeight: 700 }}>{highlightText(wf.name, searchTerm)}</span>
                      <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: cfg.color + '20', color: cfg.color }}>{t('automations.status_' + wf.status, cfg.label)}</span>
                      {wf.is_global && <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', background: 'var(--purple-bg)', color: 'var(--purple)', borderRadius: 4 }}>GLOBAL</span>}
                    </div>
                    {wf.description && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{highlightText(wf.description, searchTerm)}</div>}
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginTop: 4 }}>
                      {triggerCfg.icon} {highlightText(triggerCfg.label, searchTerm)} · {wf.steps?.length || 0} pasos · {wf.run_count || 0} ejecuciones
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button aria-pressed={wf.status === 'active'} aria-label={`${wf.status === 'active' ? t('automations.pause_workflow_btn') : t('automations.activate_workflow_btn')} ${wf.name}`} onClick={() => update({ id: wf.id, data: { status: wf.status === 'active' ? 'paused' : 'active' } })}
                      style={{ background: wf.status === 'active' ? 'var(--warning-bg)' : 'var(--success-bg)', border: `1px solid ${wf.status === 'active' ? 'rgba(245,158,11,0.25)' : 'rgba(52,211,153,0.25)'}`, borderRadius: 6, padding: '4px 10px', color: wf.status === 'active' ? 'var(--warning)' : 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                      {wf.status === 'active' ? '⏸ ' + t('automations.pause_workflow_btn') : '▶ ' + t('automations.activate_workflow_btn')}
                    </button>
                    <button aria-label={`${t('automations.edit_workflow_btn')} ${wf.name}`} onClick={() => setEditingWf(wf)}
                      style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏ {t('automations.edit_workflow_btn')}</button>
                    <button aria-label={`${t('automations.delete_workflow_btn')} ${wf.name}`} onClick={() => { openConfirmGlobal({ message: t('automations.delete_workflow_confirm'), onConfirm: () => del(wf.id), danger: true }) }}
                      style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                  </div>
                </div>

                {/* Steps visual */}
                <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
                  {wf.steps?.map((s, i) => (
                    <div key={s.id || i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <div style={{ background: 'var(--surface-4)', borderRadius: 6, padding: '4px 10px', fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>
                        {STEP_ICONS[s.step_type] || '⚡'} {highlightText(s.name || s.step_type, searchTerm)}
                      </div>
                      {i < wf.steps.length - 1 && <span style={{ color: 'var(--text-3)', fontSize: "var(--text-md)" }}>→</span>}
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
  const [searchTerm, setSearchTerm] = useState('')
  const [testResult, setTestResult] = useState(null)

  const { data: raw = [], isLoading } = useQuery({
    queryKey: ['automations'],
    queryFn: () => automationsApi.list().then(r => r.data),
    refetchInterval: 60000,
  })
  const rules = Array.isArray(raw) ? raw : []

  const { data: templates = [] } = useQuery({
    queryKey: ['auto-templates'],
    queryFn: () => automationsApi.templates().then(r => r.data),
    enabled: showTemplates,
  })

  const { mutate: del } = useMutation({
    mutationFn: id => automationsApi.delete(id),
    onSuccess: () => qc.invalidateQueries(['automations']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }) => automationsApi.update(id, { is_active: active }),
    onSuccess: () => qc.invalidateQueries(['automations']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: test } = useMutation({
    mutationFn: id => automationsApi.test(id).then(r => r.data),
    onSuccess: (data) => setTestResult(data),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: createFromTemplate } = useMutation({
    mutationFn: tpl => automationsApi.create({
      name: tpl.name,
      trigger_type: tpl.trigger_type,
      trigger_conditions: tpl.trigger_conditions,
      actions: tpl.actions,
      is_global: true,
    }),
    onSuccess: () => { qc.invalidateQueries(['automations']); setShowTemplates(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const filtered = filterActive === null ? rules : rules.filter(r => r.is_active === filterActive)
  const searched = useMemo(() => {
    const q = searchTerm.trim().toLowerCase()
    if (!q) return filtered
    return filtered.filter((rule) => {
      const inActions = (Array.isArray(rule.actions) ? rule.actions : []).some((a) =>
        String(a?.type || '').toLowerCase().includes(q)
      )
      return (
        String(rule.name || '').toLowerCase().includes(q) ||
        String(rule.description || '').toLowerCase().includes(q) ||
        String(rule.trigger_type || '').toLowerCase().includes(q) ||
        String(rule.project_name || '').toLowerCase().includes(q) ||
        inActions
      )
    })
  }, [filtered, searchTerm])
  const active = rules.filter(r => r.is_active).length

  return (
    <Page
      icon={<Bot size={18} />}
      title={t('automations.title')}
      subtitle={t('automations.subtitle')}
      rightActions={
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <Button variant="secondary" onClick={() => setShowTemplates(true)}>
            <FileStack size={13} /> {t('automations.templates_btn')}
          </Button>
          <Button onClick={() => setShowCreate(true)}>
            <Plus size={13} /> {t('automations.new_rule_btn')}
          </Button>
        </div>
      }
    >
      {/* Tab selector */}
      <Tabs
        items={[
          { id: 'rules',     label: <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><SettingsIcon size={11} /> {t('automations.rules_tab')}</span> },
          { id: 'workflows', label: <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><Zap size={11} /> {t('automations.workflows_tab')}</span> },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel={t('automations.sections_aria_lbl')}
        style={{ marginBottom: 'var(--space-5)' }}
      />

      {tab === 'workflows' && <div id="automations-panel-workflows" role="tabpanel" aria-labelledby="automations-tab-workflows"><WorkflowsTab /></div>}

      {tab === 'rules' && <div id="automations-panel-rules" role="tabpanel" aria-labelledby="automations-tab-rules">
      {/* Stats */}
      <div className="ds-grid-stats" style={{ marginBottom: 'var(--space-5)' }}>
        {[
          { label: t('automations.stats_active'),      value: active,                                              color: 'var(--accent)',  Icon: Zap },
          { label: t('automations.stats_paused'),      value: rules.length - active,                               color: 'var(--text-2)',  Icon: Pause },
          { label: t('automations.stats_total_exec'),  value: rules.reduce((s, r) => s + (r.run_count || 0), 0),    color: 'var(--success)', Icon: Play },
          { label: t('automations.stats_total_rules'), value: rules.length,                                        color: 'var(--purple)',  Icon: SettingsIcon },
        ].map(({ label, value, color, Icon }) => (
          <div key={label} className="ds-card" style={{ padding: '14px 16px', gap: 4 }}>
            <Icon size={16} style={{ color, marginBottom: 2 }} />
            <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, color, lineHeight: 1.1 }}>{value}</div>
            <div className="ds-eyebrow">{label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="ds-toolbar" style={{ marginBottom: 'var(--space-5)' }}>
        <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
          <Search size={14} aria-hidden style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-3)', pointerEvents: 'none',
          }} />
          <input
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder={t('automations.search_placeholder', 'Buscar automatizaciones (nombre, trigger, acción...)')}
            aria-label={t('automations.search_aria', 'Buscar automatizaciones')}
            className="ds-input"
            style={{ paddingLeft: 32 }}
          />
        </div>
        <div className="ds-segmented" role="group" aria-label="Filtro estado">
          {[
            [null,  t('automations.filter_all')],
            [true,  t('automations.filter_active')],
            [false, t('automations.filter_paused')],
          ].map(([val, label]) => (
            <button key={String(val)} type="button"
              aria-pressed={filterActive === val}
              onClick={() => setFilterActive(val)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Rules list */}
      {isLoading ? <Spinner /> : searched.length === 0 ? (
        <EmptyState
          svgIcon={<SettingsIcon size={36} />}
          title={t('automations.no_rules_title')}
          description={t('automations.no_rules_desc')}
          action={<Button onClick={() => setShowTemplates(true)}>{t('automations.view_templates_btn')}</Button>}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {searched.map(rule => (
            <RuleCard key={rule.id} rule={rule}
              onEdit={r => setEditing(r)}
              onDelete={id => del(id)}
              onTest={r => test(r.id)}
              onToggle={r => toggle({ id: r.id, active: !r.is_active })}
              highlightTerm={searchTerm}
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
            <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--success)', marginBottom: 12 }}>✓ {t('automations.test_rule_success')}</div>
            <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: 14 }}>
              {(testResult.results || []).map((r, i) => (
                <div key={i} style={{ fontSize: "var(--text-sm)", padding: '4px 0', borderBottom: '1px solid var(--surface-4)30', color: r.ok ? 'var(--success)' : 'var(--danger)' }}>
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
                <div key={tpl.id} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 16px' }}>
                  <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>{tpl.name}</div>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>
                    {trigger.icon} {t('automations.trig_' + tpl.trigger_type, trigger.label)}
                    {tpl.trigger_conditions && ` · ${tpl.trigger_conditions.field} ${tpl.trigger_conditions.operator} ${tpl.trigger_conditions.value}`}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                    {tpl.actions.map((a, i) => {
                      const aCfg = ACTIONS[a.type] || { icon: '⚙️', label: a.type }
                      return <span key={i} style={{ fontSize: "var(--text-xs)", padding: '2px 7px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)' }}>{aCfg.icon} {t('automations.act_' + a.type, aCfg.label)}</span>
                    })}
                  </div>
                  <button aria-label={t('automations.use_template_aria', { name: tpl.name })} onClick={() => createFromTemplate(tpl)}
                    style={{ background: 'var(--accent)', border: 'none', borderRadius: 6, padding: '6px 14px', color: '#fff', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600, width: '100%' }}>
                    {t('automations.use_template_btn')}
                  </button>
                </div>
              )
            })}
          </div>
        </Modal>
      )}
      </div>
      }
    </Page>
  )
}