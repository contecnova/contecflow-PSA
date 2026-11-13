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
import { extractErr, fmtDateTime } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, automationsApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, Page, Table } from '../components/ui'
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
  invoice_sent: '🧾', invoice_paid: '💶', invoice_overdue: '⏰',
  approval_requested: '📝', approval_approved: '✅', approval_rejected: '❌', scheduled: '🗓',
}
const ACTION_ICONS: Record<string, string> = {
  create_alert: '🔔', notify_user: '👤', notify_role: '👥', send_email: '📧', call_webhook: '🔗',
  send_webhook: '🔗', send_slack_message: '💬', send_teams_message: 'Ⓜ', change_task_status: '🔄',
  change_task_priority: '🔺', create_task: '🆕', change_project_status: '📁', escalate_ticket: '↑',
  change_ticket_status: '🎫', send_alert: '🔔', assign: '👤', update_field: '✎', create_approval: '📝',
}

// Revisión 2026-11: condiciones en grupo («todas» / «alguna»). La pantalla edita
// un nivel; un grupo anidado que venga de la API se conserva tal cual.
type Condicion = { field?: string; operator?: string; value?: string; match?: string; conditions?: Condicion[] }
const esGrupo = (c: Condicion | null | undefined) => !!c && ('conditions' in c || 'match' in c)
function aGrupo(c: Condicion | null | undefined): { match: string; conditions: Condicion[] } {
  if (!c) return { match: 'all', conditions: [] }
  if (esGrupo(c)) return { match: c.match || 'all', conditions: c.conditions || [] }
  return { match: 'all', conditions: [c] }
}
const CRON_PLANTILLAS: Array<[string, string]> = [
  ['cron_daily', '0 9 * * *'], ['cron_weekdays', '0 9 * * 1-5'], ['cron_monday', '0 8 * * 1'],
  ['cron_monthly', '0 9 1 * *'], ['cron_hourly', '0 * * * *'],
]

type AccionRegla = { type: string; params?: Record<string, string> }
/** Regla tal como la devuelve `GET /automations`. */
interface ReglaAutomatizacion {
  id: string
  name: string
  description?: string | null
  project_id?: string | null
  project_name?: string | null
  is_global?: boolean
  is_active: boolean
  trigger_type: string
  trigger_conditions?: Condicion | null
  actions: AccionRegla[]
  schedule_cron?: string | null
  run_count?: number
  last_run_at?: string | null
  next_run_at?: string | null
  last_error?: string | null
}
interface PlantillaRegla {
  id: string
  name: string
  trigger_type: string
  trigger_conditions?: Condicion | null
  actions: AccionRegla[]
}
interface EjecucionRegla {
  executed_at: string
  success: boolean
  actions_taken?: Array<{ action: string; ok?: boolean; error?: string }>
}
interface ResultadoPrueba {
  enabled?: boolean
  scan?: boolean
  results?: Array<{ action: string; ok: boolean; would?: string; error?: string }>
}

type ParamDef = { key: string; type: string; options?: string[] | null; required?: boolean }
type Catalog = {
  triggers: Array<{ type: string; category: string; fields: string[]; scan?: boolean; schedule?: boolean }>
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

function escapeRegExp(value: string) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function highlightText(text: string | null | undefined, term: string) {
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
function RuleCard({ rule, onEdit, onDelete, onTest, onToggle, onHistory, highlightTerm }: { rule: ReglaAutomatizacion; onEdit: (r: ReglaAutomatizacion) => void; onDelete: (id: string) => void; onTest: (r: ReglaAutomatizacion) => void; onToggle: (r: ReglaAutomatizacion) => void; onHistory: (r: ReglaAutomatizacion) => void; highlightTerm: string }) {
  const t = useAppT()
  const trigger = { icon: TRIGGER_ICONS[rule.trigger_type] || '⚙️', label: rule.trigger_type }
  const actions = Array.isArray(rule.actions) ? rule.actions : []

  return (
    <div style={{ background: 'var(--surface-2)', border: `1px solid ${rule.is_active ? 'var(--surface-4)' : 'var(--danger-border)'}`, borderRadius: 12, padding: '16px 20px', opacity: rule.is_active ? 1 : 0.6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div className="u-flex1">
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4 }}>
            <span style={{ fontSize: "var(--text-lg)" }}>{trigger.icon}</span>
            <span className="u-md-700">{highlightText(rule.name, highlightTerm)}</span>
            {rule.is_global && <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, padding: '1px 6px', borderRadius: 4, background: 'var(--purple-bg)', color: 'var(--purple)' }}>GLOBAL</span>}
            {rule.project_name && <span className="u-text2-xs">· {highlightText(rule.project_name, highlightTerm)}</span>}
          </div>
          {rule.description && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 8 }}>{highlightText(rule.description, highlightTerm)}</div>}
        </div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0, marginLeft: 12 }}>
          <button aria-pressed={rule.is_active} aria-label={`${rule.is_active ? t('automations.pause_btn') : t('automations.activate_btn')} ${rule.name}`} onClick={() => onToggle(rule)}
            style={{ background: rule.is_active ? 'var(--warning-bg)' : 'var(--success-bg)', border: `1px solid ${rule.is_active ? 'rgba(245,158,11,0.25)' : 'rgba(52,211,153,0.25)'}`, borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: rule.is_active ? 'var(--warning)' : 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
            {rule.is_active ? t('automations.pause_btn') : t('automations.activate_btn')}
          </button>
          <button aria-label={`${t('automations.try_btn')} ${rule.name}`} onClick={() => onTest(rule)}
            style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border-strong)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
            {t('automations.try_btn')}
          </button>
          <button aria-label={`${t('automations.history_btn')} ${rule.name}`} onClick={() => onHistory(rule)}
            style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
            {t('automations.history_btn')}
          </button>
          <button aria-label={`${t('common.edit')} ${rule.name}`} onClick={() => onEdit(rule)}
            style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏</button>
          <button aria-label={`${t('common.delete')} ${rule.name}`} onClick={() => { openConfirmGlobal({ message: t('common.are_you_sure'), onConfirm: () => onDelete(rule.id), danger: true }) }}
            style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
        </div>
      </div>

      {/* Visual rule display */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ background: 'var(--purple-bg)', border: '1px solid var(--purple-border-strong)', borderRadius: 8, padding: '6px 12px', fontSize: "var(--text-sm)" }}>
          <span style={{ color: 'var(--purple)', fontWeight: 700 }}>{t('automations.si_label')} </span>
          <span className="u-text1">{trigger.icon} {highlightText(t('automations.trig_' + rule.trigger_type, trigger.label), highlightTerm)}</span>
          {rule.schedule_cron && <span className="u-text2"> · <code>{rule.schedule_cron}</code></span>}
          {rule.trigger_conditions && aGrupo(rule.trigger_conditions).conditions.map((c: Condicion, i: number) => (
            <span key={i} className="u-text2">
              {i === 0 ? ' · ' : ` ${t(aGrupo(rule.trigger_conditions).match === 'any' ? 'automations.or_lbl' : 'automations.and_lbl')} `}
              {esGrupo(c) ? `(${t('automations.nested_group')})` : <>{c.field} {t('automations.op_' + c.operator)} <strong className="u-text1">{c.value}</strong></>}
            </span>
          ))}
        </div>
        <span style={{ fontSize: "var(--text-lg-em)", color: 'var(--text-3)' }}>→</span>
        <div className="u-wrap-6">
          {actions.map((a, i) => {
            const aCfg = { icon: ACTION_ICONS[a.type] || '⚙️', label: a.type }
            return (
              <div key={i} style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 8, padding: '6px 12px', fontSize: "var(--text-sm)" }}>
                <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{t('automations.entonces_label')}</span>
                <span className="u-text1">{aCfg.icon} {highlightText(t('automations.act_' + a.type, aCfg.label), highlightTerm)}</span>
                {a.params?.message && <span className="u-text2"> · &quot;{a.params.message.slice(0, 40)}&quot;</span>}
              </div>
            )
          })}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16, marginTop: 10, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
        <span>⚡ {rule.run_count || 0} {t('automations.executions')}</span>
        {rule.last_run_at && <span>{t('automations.last_exec')}: {rule.last_run_at}</span>}
        {rule.next_run_at && rule.is_active && <span>🗓 {t('automations.next_run')}: {fmtDateTime(rule.next_run_at)}</span>}
        {rule.last_error && <span className="u-danger">⚠ {rule.last_error.slice(0, 60)}</span>}
      </div>
    </div>
  )
}

// ── Rule editor modal ─────────────────────────────────────────────────────────
function RuleModal({ rule, onClose }: { rule?: ReglaAutomatizacion; onClose: () => void }) {
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
    actions: rule?.actions || [{ type: 'create_alert', params: { message: '', severity: 'warning' } }] as AccionRegla[],
  })
  const [hasCondition, setHasCondition] = useState(!!rule?.trigger_conditions)
  const inicial = aGrupo(rule?.trigger_conditions)
  const [match, setMatch] = useState(inicial.match)
  const [condiciones, setCondiciones] = useState<Condicion[]>(
    inicial.conditions.length ? inicial.conditions : [{ field: '', operator: 'equals', value: '' }])
  const [cron, setCron] = useState<string>(rule?.schedule_cron || '0 9 * * 1-5')
  const cambiarCondicion = (i: number, campo: string, valor: string) =>
    setCondiciones(cs => cs.map((c, j) => j === i ? { ...c, [campo]: valor } : c))

  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data ?? []) })
  const projects = Array.isArray(projRaw) ? projRaw : []
  const { data: catalog, isError: catalogError } = useCatalog()
  const triggerDefs = catalog?.triggers ?? []
  const actionDefs = catalog?.actions ?? []

  const { mutate, isPending } = useMutation({
    mutationFn: (d: typeof form & { schedule_cron: string | null }) => isEdit ? automationsApi.update(rule.id, d) : automationsApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['automations'] }); onClose() },
    onError: e => toast.error(extractErr(e, t('common.error'))),
  })

  const addAction = () => setForm(f => ({ ...f, actions: [...f.actions, { type: 'create_alert', params: { message: '', severity: 'info' } }] }))
  const removeAction = (i: number) => setForm(f => ({ ...f, actions: f.actions.filter((_, idx) => idx !== i) }))
  const updateAction = (i: number, field: string, value: string) => setForm(f => {
    const actions = [...f.actions]
    if (field === 'type') actions[i] = { type: value, params: {} }
    else {
      actions[i] = { ...actions[i], params: { ...actions[i].params, [field]: value } }
    }
    return { ...f, actions }
  })

  const fields = triggerDefs.find(d => d.type === form.trigger_type)?.fields ?? []
  const isScan = !!triggerDefs.find(d => d.type === form.trigger_type)?.scan
  const isSchedule = !!triggerDefs.find(d => d.type === form.trigger_type)?.schedule

  const handleSave = () => {
    // Las filas a medias no se mandan; una sola condición viaja como antes.
    const validas = condiciones.filter(c => esGrupo(c) || c.field)
    const trigger_conditions = !hasCondition || !validas.length ? null
      : validas.length === 1 && !esGrupo(validas[0]) ? validas[0] : { match, conditions: validas }
    mutate({ ...form, trigger_conditions, schedule_cron: isSchedule ? cron.trim() : null })
  }

  return (
    <Modal open title={isEdit ? t('automations.edit_rule_title') : t('automations.new_rule_title')} onClose={onClose} width={680}>
      <div className="u-stack-16">
        {/* Basic info */}
        <div className="u-grid2-14">
          <div className="u-col-full">
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
        <div style={{ background: 'var(--purple-bg)', border: '1px solid var(--purple-border)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
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
              {catalogError && <div role="alert" className="u-field-error">{t('automations.catalog_unavailable')}</div>}
              {isScan && <div className="u-hint">{t('automations.simulation_scan')}</div>}
            </div>

            {/* Condition */}
            <div>
              <label htmlFor={`${idPrefix}-has-condition`} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-base)", color: 'var(--text-2)' }}>
                <input id={`${idPrefix}-has-condition`} type="checkbox" checked={hasCondition} onChange={e => setHasCondition(e.target.checked)} />
                {t('automations.add_condition')}
              </label>
            </div>
            {isSchedule && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '10px 14px', background: 'var(--surface-3)', borderRadius: 8 }}>
                <div>
                  <label htmlFor={`${idPrefix}-cron`} style={ls}>{t('automations.cron_lbl')}</label>
                  <input id={`${idPrefix}-cron`} value={cron} onChange={e => setCron(e.target.value)} style={{ ...fs, fontFamily: 'var(--font-mono)' }} placeholder="0 9 * * 1-5" />
                </div>
                <div>
                  <label htmlFor={`${idPrefix}-cron-preset`} style={ls}>{t('automations.cron_preset')}</label>
                  <select id={`${idPrefix}-cron-preset`} value={CRON_PLANTILLAS.find(([, c]) => c === cron.trim())?.[1] ?? ''} onChange={e => e.target.value && setCron(e.target.value)} style={fs}>
                    <option value="">{t('automations.select_lbl')}</option>
                    {CRON_PLANTILLAS.map(([k, c]) => <option key={c} value={c}>{t('automations.' + k)}</option>)}
                  </select>
                </div>
                <div style={{ gridColumn: '1/-1', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('automations.cron_help')}</div>
              </div>
            )}
            {hasCondition && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 14px', background: 'var(--surface-3)', borderRadius: 8 }}>
                {condiciones.length > 1 && (
                  <div role="radiogroup" aria-label={t('automations.match_lbl')} style={{ display: 'flex', gap: 14, fontSize: 'var(--text-sm)' }}>
                    {(['all', 'any'] as const).map(m => (
                      <label key={m} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                        <input type="radio" name={`${idPrefix}-match`} checked={match === m} onChange={() => setMatch(m)} />
                        {t('automations.match_' + m)}
                      </label>
                    ))}
                  </div>
                )}
                {condiciones.map((c, i) => esGrupo(c) ? (
                  <div key={i} className="u-text3-sm">({t('automations.nested_group')})</div>
                ) : (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 10, alignItems: 'end' }}>
                    <div>
                      <label htmlFor={`${idPrefix}-condition-field-${i}`} style={ls}>{t('automations.field_lbl')}</label>
                      <select id={`${idPrefix}-condition-field-${i}`} value={c.field || ''} onChange={e => cambiarCondicion(i, 'field', e.target.value)} style={fs}>
                        <option value="">{t('automations.select_lbl')}</option>
                        {fields.map((f: string) => <option key={f} value={f}>{f}</option>)}
                      </select>
                    </div>
                    <div>
                      <label htmlFor={`${idPrefix}-condition-operator-${i}`} style={ls}>{t('automations.operator_lbl')}</label>
                      <select id={`${idPrefix}-condition-operator-${i}`} value={c.operator || 'equals'} onChange={e => cambiarCondicion(i, 'operator', e.target.value)} style={fs}>
                        {(catalog?.operators ?? []).map(o => <option key={o} value={o}>{t('automations.op_' + o, o)}</option>)}
                      </select>
                    </div>
                    <div>
                      <label htmlFor={`${idPrefix}-condition-value-${i}`} style={ls}>{t('automations.value_lbl')}</label>
                      <input id={`${idPrefix}-condition-value-${i}`} value={c.value || ''} onChange={e => cambiarCondicion(i, 'value', e.target.value)} style={fs} placeholder={t('automations.value_lbl')} />
                    </div>
                    <button type="button" aria-label={t('automations.remove_condition')} disabled={condiciones.length === 1}
                      onClick={() => setCondiciones(cs => cs.filter((_, j) => j !== i))}
                      style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: condiciones.length === 1 ? 'default' : 'pointer', fontSize: 'var(--text-lg)', paddingBottom: 8 }}>×</button>
                  </div>
                ))}
                <button type="button" onClick={() => setCondiciones(cs => [...cs, { field: '', operator: 'equals', value: '' }])}
                  style={{ alignSelf: 'flex-start', background: 'transparent', border: '1px dashed var(--purple-border)', borderRadius: 8, padding: '5px 12px', color: 'var(--purple)', cursor: 'pointer', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }}>
                  {t('automations.add_condition_row')}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* ACTIONS */}
        <div style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--accent)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {t('automations.entonces_label')}
          </div>
          {form.actions.map((action, i) => {
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
                            {param.options?.map((o: string) => <option key={o} value={o}>{t('automations.opt_' + o.replace('.', '_'), o)}</option>)}
                          </select>
                        ) : (
                          <input aria-label={t('automations.param_' + param.key, param.key)} type={param.type === 'number' ? 'number' : 'text'} value={action.params?.[param.key] || ''} onChange={e => updateAction(i, param.key, e.target.value)} style={fs} placeholder={t('automations.param_' + param.key, param.key)} />
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
        <div className="u-actions-10">
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
function ExecutionsModal({ rule, onClose }: { rule: ReglaAutomatizacion; onClose: () => void }) {
  const t = useAppT()
  const { data = [], isLoading } = useQuery({
    queryKey: ['automation_executions', rule.id],
    queryFn: () => automationsApi.executions(rule.id).then((r): EjecucionRegla[] => (Array.isArray(r.data) ? r.data : [])),
    enabled: !!rule?.id,
  })
  return (
    <Modal open title={`${t('automations.executions_title')} — ${rule.name}`} onClose={onClose} width={700}>
      <div style={{ minHeight: 120 }}>
        {isLoading ? <Spinner /> : data.length === 0 ? (
          <div className="u-text2-sm">{t('automations.no_executions')}</div>
        ) : (
          <Table
            data={data}
            columns={[
              { key: 'executed_at', label: t('automations.exec_date') },
              { key: 'success', label: t('automations.exec_status'), render: (_v, exec) => (
                <span style={{ color: exec.success ? 'var(--success)' : 'var(--danger)' }}>
                  {exec.success ? t('automations.exec_status_success') : t('automations.exec_status_error')}
                </span>
              ) },
              { key: 'actions_taken', label: t('automations.exec_result'), render: (_v, exec) => (
                <div className="u-xs">
                  {(exec.actions_taken || []).map((a, i) => (
                    <div key={i}>{a.ok === false ? '✗' : '✓'} {t('automations.act_' + a.action, a.action)}{a.error ? `: ${a.error}` : ''}</div>
                  ))}
                </div>
              ) },
            ]}
          />
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
  const [editing, setEditing] = useState<ReglaAutomatizacion | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [execHistory, setExecHistory] = useState<ReglaAutomatizacion | null>(null)
  const [filterActive, setFilterActive] = useState<boolean | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [testResult, setTestResult] = useState<ResultadoPrueba | null>(null)

  const { data: raw = [], isLoading } = useQuery({
    queryKey: ['automations'],
    queryFn: () => automationsApi.list().then((r): ReglaAutomatizacion[] => r.data?.items ?? r.data ?? []),
    refetchInterval: 60000,
  })
  const rules = Array.isArray(raw) ? raw : []

  const { data: templates = [] } = useQuery({
    queryKey: ['auto-templates'],
    queryFn: () => automationsApi.templates().then((r): PlantillaRegla[] => r.data),
    enabled: showTemplates,
  })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => automationsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => automationsApi.update(id, { is_active: active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: test } = useMutation({
    mutationFn: (id: string) => automationsApi.test(id).then((r): ResultadoPrueba => r.data),
    onSuccess: (data) => setTestResult(data),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: createFromTemplate } = useMutation({
    mutationFn: (tpl: PlantillaRegla) => automationsApi.create({
      name: tpl.name,
      trigger_type: tpl.trigger_type,
      trigger_conditions: tpl.trigger_conditions,
      actions: tpl.actions,
      is_global: true,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['automations'] }); setShowTemplates(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const filtered = filterActive === null ? rules : rules.filter(r => r.is_active === filterActive)
  const searched = useMemo(() => {
    const q = searchTerm.trim().toLowerCase()
    if (!q) return filtered
    return filtered.filter(rule => {
      const inActions = (Array.isArray(rule.actions) ? rule.actions : []).some(a =>
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
      <div>
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
        <div className="u-stack-12">
          {searched.map(rule => (
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
              {(testResult.results || []).map((r, i) => (
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
          <div className="u-grid2-12">
            {templates.map(tpl => {
              const trigger = { icon: TRIGGER_ICONS[tpl.trigger_type] || '⚙️', label: tpl.trigger_type }
              return (
                <div key={tpl.id} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
                  <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>{tpl.name}</div>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>
                    {trigger.icon} {t('automations.trig_' + tpl.trigger_type, trigger.label)}
                    {tpl.trigger_conditions && ` · ${tpl.trigger_conditions.field} ${tpl.trigger_conditions.operator} ${tpl.trigger_conditions.value}`}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                    {tpl.actions.map((a, i) => {
                      const aCfg = { icon: ACTION_ICONS[a.type] || '⚙️', label: a.type }
                      return <span key={i} style={{ fontSize: "var(--text-xs)", padding: '2px 7px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)' }}>{aCfg.icon} {t('automations.act_' + a.type, aCfg.label)}</span>
                    })}
                  </div>
                  <button aria-label={t('automations.use_template_aria', { name: tpl.name })} onClick={() => createFromTemplate(tpl)}
                    style={{ background: 'var(--accent)', border: 'none', borderRadius: 'var(--radius-sm)', padding: '6px 14px', color: 'var(--on-accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600, width: '100%' }}>
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