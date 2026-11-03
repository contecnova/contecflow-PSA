/**
 * AutomationsPage — reglas SI [disparador] [condición] ENTONCES [acciones].
 *
 * Auditoría 2026-11: los disparadores, las acciones y sus parámetros vienen
 * del catálogo del motor (`GET /automations/catalog`). Antes la pantalla
 * ofrecía 64 disparadores y 23 acciones escritos aquí, y el motor conocía 14
 * y 11. «Probar» es una simulación: no ejecuta nada.
 */
import { useId, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, automationsApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, Page } from '../components/ui'
import {
  Bot, FileStack, Plus, Zap, Pause, Play, Settings as SettingsIcon, Search,
} from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

// Solo iconos: qué disparadores y acciones hay lo dice el catálogo del motor.
const TRIGGER_ICONS: Record<string, string> = {
  task_created: '🆕', task_status_changed: '🔄', task_assigned: '👤', task_completed: '✅',
  task_blocked: '🚫', task_overdue: '⏰', task_deadline_approaching: '📅',
  project_created: '🆕', project_status_changed: '📁', budget_threshold: '💰', risk_score_high: '⚠️',
  sprint_started: '⚡', sprint_ended: '🏁',
  timesheet_submitted: '✅', timesheet_rejected: '❌', timesheet_not_submitted: '📋',
  absence_requested: '🌴', absence_approved: '✅', absence_rejected: '❌',
  ticket_created: '🎫', ticket_resolved: '✅', ticket_reopened: '🔄', ticket_escalated: '↑',
  ticket_sla_at_risk: '🚨', ticket_sla_breached: '🔴',
  expense_submitted: '💸', expense_approved: '✅', expense_rejected: '❌', opportunity_stage_changed: '📈',
}
const ACTION_ICONS: Record<string, string> = {
  create_alert: '🔔', notify_user: '👤', notify_role: '👥', send_email: '📧', call_webhook: '🔗',
  send_webhook: '🔗', send_slack_message: '💬', send_teams_message: 'Ⓜ', change_task_status: '🔄',
  change_task_priority: '🔺', create_task: '🆕', change_project_status: '📁', escalate_ticket: '↑',
  change_ticket_status: '🎫', send_alert: '🔔',
}

type ParamDef = { key: string; type: string; options?: string[] | null; required?: boolean }
type Catalog = {
  triggers: Array<{ type: string; category: string; fields: string[]; scan?: boolean }>
  actions: Array<{ type: string; category: string; params: ParamDef[] }>
  operators: string[]
}

function useCatalog() {
  return useQuery<Catalog>({
    queryKey: ['automations-catalog'],
    queryFn: () => automationsApi.catalog().then(r => r.data as Catalog),
    staleTime: Infinity,
  })
}

function byCategory<T extends { category: string }>(items: T[]): Array<[string, T[]]> {
  const groups = new Map<string, T[]>()
  items.forEach(i => groups.set(i.category, [...(groups.get(i.category) || []), i]))
  return [...groups.entries()]
}

const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

function escapeRegExp(value: any) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function highlightText(text: any, term: any) {
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
function RuleCard({ rule, onEdit, onDelete, onTest, onToggle, onHistory, highlightTerm }: { rule: any; onEdit: (r: any) => void; onDelete: (id: any) => void; onTest: (r: any) => void; onToggle: (r: any) => void; onHistory: (r: any) => void; highlightTerm: any }) {
  const t = useAppT()
  const trigger = { icon: TRIGGER_ICONS[rule.trigger_type] || '⚙️', label: rule.trigger_type }
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
          <button aria-label={`${t('automations.history_btn')} ${rule.name}`} onClick={() => onHistory(rule)}
            style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
            {t('automations.history_btn')}
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
          {actions.map((a: any, i: number) => {
            const aCfg = { icon: ACTION_ICONS[a.type] || '⚙️', label: a.type }
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
function RuleModal({ rule, onClose }: { rule?: any; onClose: () => void }) {
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

  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => (r.data as any)?.items ?? r.data ?? []) })
  const projects = Array.isArray(projRaw) ? projRaw : []
  const { data: catalog, isError: catalogError } = useCatalog()
  const triggerDefs = catalog?.triggers ?? []
  const actionDefs = catalog?.actions ?? []

  const { mutate, isPending } = useMutation({
    mutationFn: (d: any) => isEdit ? automationsApi.update(rule.id, d) : automationsApi.create(d as any),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['automations'] }); onClose() },
    onError: e => toast.error(extractErr(e, t('common.error'))),
  })

  const addAction = () => setForm(f => ({ ...f, actions: [...f.actions, { type: 'create_alert', params: { message: '', severity: 'info' } }] }))
  const removeAction = (i: number) => setForm(f => ({ ...f, actions: f.actions.filter((_: any, idx: number) => idx !== i) }))
  const updateAction = (i: number, field: any, value: any) => setForm(f => {
    const actions = [...f.actions]
    if (field === 'type') actions[i] = { type: value, params: {} }
    else {
      actions[i] = { ...actions[i], params: { ...actions[i].params, [field]: value } }
    }
    return { ...f, actions }
  })

  const fields = triggerDefs.find(d => d.type === form.trigger_type)?.fields ?? []
  const isScan = !!triggerDefs.find(d => d.type === form.trigger_type)?.scan

  const handleSave = () => {
    const payload = {
      ...form,
      trigger_conditions: hasCondition && condition.field ? condition : null,
    }
    mutate(payload as any)
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
                {byCategory(triggerDefs).map(([cat, defs]) => (
                  <optgroup key={cat} label={t('automations.cat_' + cat, cat)}>
                    {defs.map(d => (
                      <option key={d.type} value={d.type}>{TRIGGER_ICONS[d.type] || '⚙️'} {t('automations.trig_' + d.type, d.type)}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {catalogError && <div role="alert" style={{ fontSize: 'var(--text-xs)', color: 'var(--danger)', marginTop: 4 }}>{t('automations.catalog_unavailable')}</div>}
              {isScan && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 4 }}>{t('automations.simulation_scan')}</div>}
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
                  <select id={`${idPrefix}-condition-field`} value={condition.field} onChange={e => setCondition((c: any) => ({ ...c, field: e.target.value }))} style={fs}>
                    <option value="">{t('automations.select_lbl')}</option>
                    {fields.map((f: string) => <option key={f} value={f}>{f}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor={`${idPrefix}-condition-operator`} style={ls}>{t('automations.operator_lbl')}</label>
                  <select id={`${idPrefix}-condition-operator`} value={condition.operator} onChange={e => setCondition((c: any) => ({ ...c, operator: e.target.value }))} style={fs}>
                    {(catalog?.operators ?? []).map(o => <option key={o} value={o}>{t('automations.op_' + o, o)}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor={`${idPrefix}-condition-value`} style={ls}>{t('automations.value_lbl')}</label>
                  <input id={`${idPrefix}-condition-value`} value={condition.value} onChange={e => setCondition((c: any) => ({ ...c, value: e.target.value }))} style={fs} placeholder={t('automations.value_lbl')} />
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
          {form.actions.map((action: any, i: number) => {
            const paramDefs = actionDefs.find(d => d.type === action.type)?.params ?? []
            return (
              <div key={i} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 14px', marginBottom: 10, position: 'relative' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 10, marginBottom: paramDefs.length > 0 ? 10 : 0 }}>
                  <div>
                    <label style={ls}>{t('automations.action_lbl')} {i + 1}</label>
                    <select value={action.type} onChange={e => updateAction(i, 'type', e.target.value)} style={fs}>
                      {byCategory(actionDefs).map(([cat, defs]) => (
                        <optgroup key={cat} label={t('automations.cat_' + cat, cat)}>
                          {defs.map(d => (
                            <option key={d.type} value={d.type}>{ACTION_ICONS[d.type] || '⚙️'} {t('automations.act_' + d.type, d.type)}</option>
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
                        <label style={ls}>{t('automations.param_' + param.key, param.key)}{param.required ? ' *' : ''}</label>
                        {param.type === 'select' ? (
                          <select value={action.params?.[param.key] || ''} onChange={e => updateAction(i, param.key, e.target.value)} style={fs}>
                            <option value="">{t('automations.select_lbl')}</option>
                            {param.options?.map((o: string) => <option key={o} value={o}>{o}</option>)}
                          </select>
                        ) : (
                          <input type={param.type === 'number' ? 'number' : 'text'} value={action.params?.[param.key] || ''} onChange={e => updateAction(i, param.key, e.target.value)} style={fs} placeholder={t('automations.param_' + param.key, param.key)} />
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
function ExecutionsModal({ rule, onClose }: { rule: any; onClose: () => void }) {
  const t = useAppT()
  const { data = [], isLoading } = useQuery({
    queryKey: ['automation_executions', rule.id],
    queryFn: () => automationsApi.executions(rule.id).then(r => (Array.isArray(r.data) ? r.data : [])),
    enabled: !!rule?.id,
  })
  return (
    <Modal open title={`${t('automations.executions_title')} — ${rule.name}`} onClose={onClose} width={700}>
      <div style={{ minHeight: 120 }}>
        {isLoading ? <Spinner /> : data.length === 0 ? (
          <div style={{ color: 'var(--text-2)', fontSize: 'var(--text-sm)' }}>{t('automations.no_executions')}</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t('automations.exec_date')}</th>
                <th>{t('automations.exec_status')}</th>
                <th>{t('automations.exec_result')}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((exec: any) => (
                <tr key={exec.id}>
                  <td>{exec.executed_at}</td>
                  <td style={{ color: exec.success ? 'var(--success)' : 'var(--danger)' }}>
                    {exec.success ? t('automations.exec_status_success') : t('automations.exec_status_error')}
                  </td>
                  <td style={{ fontSize: 'var(--text-xs)' }}>
                    {(exec.actions_taken || []).map((a: any, i: number) => (
                      <div key={i}>{a.ok === false ? '✗' : '✓'} {t('automations.act_' + a.action, a.action)}{a.error ? `: ${a.error}` : ''}</div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Modal>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AutomationsPage(): JSX.Element {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [editing, setEditing] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [execHistory, setExecHistory] = useState(null)
  const [filterActive, setFilterActive] = useState<boolean | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [testResult, setTestResult] = useState<any>(null)

  const { data: raw = [], isLoading } = useQuery({
    queryKey: ['automations'],
    queryFn: () => automationsApi.list().then(r => (r.data as any)?.items ?? r.data ?? []),
    refetchInterval: 60000,
  })
  const rules = Array.isArray(raw) ? raw : []

  const { data: templates = [] } = useQuery({
    queryKey: ['auto-templates'],
    queryFn: () => automationsApi.templates().then(r => r.data),
    enabled: showTemplates,
  })

  const { mutate: del } = useMutation({
    mutationFn: (id: any) => automationsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }: { id: any; active: boolean }) => automationsApi.update(id, { is_active: active } as any),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: test } = useMutation({
    mutationFn: (id: any) => automationsApi.test(id).then(r => r.data),
    onSuccess: (data) => setTestResult(data),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: createFromTemplate } = useMutation({
    mutationFn: (tpl: any) => automationsApi.create({
      name: tpl.name,
      trigger_type: tpl.trigger_type,
      trigger_conditions: tpl.trigger_conditions,
      actions: tpl.actions,
      is_global: true,
    } as any),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['automations'] }); setShowTemplates(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const filtered = filterActive === null ? rules : rules.filter((r: any) => r.is_active === filterActive)
  const searched = useMemo(() => {
    const q = searchTerm.trim().toLowerCase()
    if (!q) return filtered
    return filtered.filter((rule: any) => {
      const inActions = (Array.isArray(rule.actions) ? rule.actions : []).some((a: any) =>
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
  const active = rules.filter((r: any) => r.is_active).length

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
      <div>
      {/* Stats */}
      <div className="ds-grid-stats" style={{ marginBottom: 'var(--space-5)' }}>
        {[
          { label: t('automations.stats_active'),      value: active,                                              color: 'var(--accent)',  Icon: Zap },
          { label: t('automations.stats_paused'),      value: rules.length - active,                               color: 'var(--text-2)',  Icon: Pause },
          { label: t('automations.stats_total_exec'),  value: rules.reduce((s: number, r: any) => s + (r.run_count || 0), 0),    color: 'var(--success)', Icon: Play },
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
              onClick={() => setFilterActive(val as boolean | null)}>
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
          {searched.map((rule: any) => (
            <RuleCard key={rule.id} rule={rule}
              onEdit={r => setEditing(r)}
              onDelete={id => del(id)}
              onTest={r => test(r.id)}
              onToggle={r => toggle({ id: r.id, active: !r.is_active })}
              onHistory={r => setExecHistory(r)}
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
        <Modal open title={t('automations.test_rule_success')} onClose={() => setTestResult(null)} width={560}>
          <div style={{ padding: 4 }}>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 12 }}>{t('automations.simulation_note')}</div>
            {testResult.enabled === false && <div role="alert" style={{ fontSize: "var(--text-sm)", color: 'var(--warning)', marginBottom: 12 }}>{t('automations.simulation_off')}</div>}
            {testResult.scan && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginBottom: 12 }}>{t('automations.simulation_scan')}</div>}
            <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: 14 }}>
              {(testResult.results || []).map((r: any, i: number) => (
                <div key={i} style={{ fontSize: "var(--text-sm)", padding: '4px 0', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', color: r.ok ? 'var(--text-1)' : 'var(--danger)' }}>
                  {r.ok ? '✓' : '✗'} {t('automations.act_' + r.action, r.action)}: {r.ok ? r.would : r.error}
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
            {templates.map((tpl: any) => {
              const trigger = { icon: TRIGGER_ICONS[tpl.trigger_type] || '⚙️', label: tpl.trigger_type }
              return (
                <div key={tpl.id} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 16px' }}>
                  <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>{tpl.name}</div>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>
                    {trigger.icon} {t('automations.trig_' + tpl.trigger_type, trigger.label)}
                    {tpl.trigger_conditions && ` · ${tpl.trigger_conditions.field} ${tpl.trigger_conditions.operator} ${tpl.trigger_conditions.value}`}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                    {tpl.actions.map((a: any, i: number) => {
                      const aCfg = { icon: ACTION_ICONS[a.type] || '⚙️', label: a.type }
                      return <span key={i} style={{ fontSize: "var(--text-xs)", padding: '2px 7px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)' }}>{aCfg.icon} {t('automations.act_' + a.type, aCfg.label)}</span>
                    })}
                  </div>
                  <button aria-label={t('automations.use_template_aria', { name: tpl.name })} onClick={() => createFromTemplate(tpl)}
                    style={{ background: 'var(--accent)', border: 'none', borderRadius: 6, padding: '6px 14px', color: 'var(--on-accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600, width: '100%' }}>
                    {t('automations.use_template_btn')}
                  </button>
                </div>
              )
            })}
          </div>
        </Modal>
      )}
      </div>
    </Page>
  )
}