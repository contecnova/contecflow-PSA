/**
 * AutomationsPage — reglas SI [disparador] [condición] ENTONCES [acciones].
 *
 * Auditoría 2026-11: los disparadores, las acciones y sus parámetros vienen
 * del catálogo del motor (`GET /automations/catalog`). Antes la pantalla
 * ofrecía 64 disparadores y 23 acciones escritos aquí, y el motor conocía 14
 * y 11. «Probar» es una simulación: no ejecuta nada.
 */
import { useId, useMemo, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import './AutomationsPage.css'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDateTime, fmtNumber } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, automationsApi } from '../services/api'
import type { AccionDeRegla, CatalogoDeAutomatizaciones, CondicionDeRegla, PlantillaDeRegla, ReglaDeAutomatizacion, SimulacionDeRegla } from '../services/api/tipos-plataforma'
import { Button, Modal, Spinner, EmptyState, Page, Table, KpiCard, IconButton, StatusBadge } from '../components/ui'
import {
  Bot, FileStack, Plus, Zap, Pause, Play, Settings as SettingsIcon, Search,
  ListChecks, FolderKanban, Wallet, AlertTriangle, Clock, Palmtree, Ticket, Receipt, TrendingUp, FileText,
  CheckCircle2, CalendarClock, Bell, User, Users, Mail, Link2, MessageSquare, RefreshCw, ArrowUp, ListPlus,
  ArrowUpCircle, PenLine, FileCheck, Pencil, Trash2, X, ArrowRight, Check, History, FlaskConical,
} from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { POLL_DEFAULT_MS } from '../constants/timings'

// Solo iconos (lucide): qué disparadores y acciones hay lo dice el catálogo del motor.
// El icono del disparador sale de su familia (task_*, ticket_*…); el de la acción, de su tipo.
const ICONO_POR_FAMILIA: Array<[string, ReactNode]> = [
  ['task_', <ListChecks key="t" size={14} />], ['project_', <FolderKanban key="p" size={14} />],
  ['budget_', <Wallet key="b" size={14} />], ['risk_', <AlertTriangle key="r" size={14} />],
  ['sprint_', <Zap key="s" size={14} />], ['timesheet_', <Clock key="ts" size={14} />],
  ['absence_', <Palmtree key="a" size={14} />], ['ticket_', <Ticket key="tk" size={14} />],
  ['expense_', <Receipt key="e" size={14} />], ['opportunity_', <TrendingUp key="o" size={14} />],
  ['invoice_', <FileText key="i" size={14} />], ['approval_', <CheckCircle2 key="ap" size={14} />],
  ['scheduled', <CalendarClock key="sc" size={14} />],
]
const ICONO_POR_DEFECTO = <SettingsIcon size={14} />
const iconoDisparador = (tipo: string): ReactNode =>
  ICONO_POR_FAMILIA.find(([pref]) => tipo.startsWith(pref))?.[1] ?? ICONO_POR_DEFECTO
const ACTION_ICONS: Record<string, ReactNode> = {
  create_alert: <Bell size={14} />, send_alert: <Bell size={14} />, notify_user: <User size={14} />, assign: <User size={14} />,
  notify_role: <Users size={14} />, send_email: <Mail size={14} />, call_webhook: <Link2 size={14} />, send_webhook: <Link2 size={14} />,
  send_slack_message: <MessageSquare size={14} />, send_teams_message: <MessageSquare size={14} />,
  change_task_status: <RefreshCw size={14} />, change_project_status: <RefreshCw size={14} />, change_ticket_status: <RefreshCw size={14} />,
  change_task_priority: <ArrowUp size={14} />, create_task: <ListPlus size={14} />, escalate_ticket: <ArrowUpCircle size={14} />,
  update_field: <PenLine size={14} />, create_approval: <FileCheck size={14} />,
}

// Revisión 2026-11: condiciones en grupo («todas» / «alguna»). La pantalla edita
// un nivel; un grupo anidado que venga de la API se conserva tal cual.
const esGrupo = (c: CondicionDeRegla | null | undefined) => !!c && ('conditions' in c || 'match' in c)
function aGrupo(c: CondicionDeRegla | null | undefined): { match: string; conditions: CondicionDeRegla[] } {
  if (!c) return { match: 'all', conditions: [] }
  if (esGrupo(c)) return { match: c.match || 'all', conditions: c.conditions || [] }
  return { match: 'all', conditions: [c] }
}
const CRON_PLANTILLAS: Array<[string, string]> = [
  ['cron_daily', '0 9 * * *'], ['cron_weekdays', '0 9 * * 1-5'], ['cron_monday', '0 8 * * 1'],
  ['cron_monthly', '0 9 1 * *'], ['cron_hourly', '0 * * * *'],
]

function useCatalog() {
  return useQuery<CatalogoDeAutomatizaciones>({
    queryKey: ['automations-catalog'],
    queryFn: () => automationsApi.catalog().then(r => r.data),
    staleTime: Infinity,
  })
}

function byCategory<T extends { category: string }>(items: T[]): Array<[string, T[]]> {
  const groups = new Map<string, T[]>()
  items.forEach(i => groups.set(i.category, [...(groups.get(i.category) || []), i]))
  return [...groups.entries()]
}

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
      ? <mark key={idx} className="aut-mark">
          {part}
        </mark>
      : <span key={idx}>{part}</span>
  ))
}

// ── Rule card ─────────────────────────────────────────────────────────────────
function RuleCard({ rule, onEdit, onDelete, onTest, onToggle, onHistory, highlightTerm }: { rule: ReglaDeAutomatizacion; onEdit: (r: ReglaDeAutomatizacion) => void; onDelete: (id: string) => void; onTest: (r: ReglaDeAutomatizacion) => void; onToggle: (r: ReglaDeAutomatizacion) => void; onHistory: (r: ReglaDeAutomatizacion) => void; highlightTerm: string }) {
  const t = useAppT()
  const trigger = { icon: iconoDisparador(rule.trigger_type), label: rule.trigger_type }
  const actions = Array.isArray(rule.actions) ? rule.actions : []

  return (
    <div className={rule.is_active ? 'aut-rule' : 'aut-rule aut-rule--paused'}>
      <div className="aut-rule-head">
        <div className="u-flex1-min0">
          <div className="aut-rule-title">
            <span className="aut-rule-icon" aria-hidden="true">{trigger.icon}</span>
            <span className="u-md-700">{highlightText(rule.name, highlightTerm)}</span>
            {rule.is_global && <StatusBadge kind="accent" caps={false}>{t('automations.global_badge')}</StatusBadge>}
            {rule.project_name && <span className="u-text2-xs">· {highlightText(rule.project_name, highlightTerm)}</span>}
          </div>
          {rule.description && <div className="aut-rule-desc">{highlightText(rule.description, highlightTerm)}</div>}
        </div>
        <div className="aut-rule-actions">
          <Button size="sm" variant="secondary" icon={rule.is_active ? <Pause size={14} /> : <Play size={14} />}
            title={t(rule.is_active ? 'automations.pause_rule_aria' : 'automations.activate_rule_aria', { name: rule.name })} onClick={() => onToggle(rule)}>
            {rule.is_active ? t('automations.pause_btn') : t('automations.activate_btn')}
          </Button>
          <Button size="sm" variant="secondary" icon={<FlaskConical size={14} />} title={`${t('automations.try_btn')} ${rule.name}`} onClick={() => onTest(rule)}>
            {t('automations.try_btn')}
          </Button>
          <Button size="sm" variant="ghost" icon={<History size={14} />} title={`${t('automations.history_btn')} ${rule.name}`} onClick={() => onHistory(rule)}>
            {t('automations.history_btn')}
          </Button>
          <IconButton ariaLabel={`${t('common.edit')} ${rule.name}`} title={t('common.edit')} onClick={() => onEdit(rule)}>
            <Pencil size={14} aria-hidden="true" />
          </IconButton>
          <IconButton ariaLabel={`${t('common.delete')} ${rule.name}`} title={t('common.delete')} onClick={() => { openConfirmGlobal({ message: t('common.are_you_sure'), onConfirm: () => onDelete(rule.id), danger: true }) }}>
            <Trash2 size={14} aria-hidden="true" />
          </IconButton>
        </div>
      </div>

      {/* Visual rule display */}
      <div className="aut-flow">
        <div className="aut-chip aut-chip--if">
          <span className="aut-chip-kw">{t('automations.si_label')} </span>
          <span className="u-text1 aut-icono-texto">{trigger.icon} {highlightText(t('automations.trig_' + rule.trigger_type, trigger.label), highlightTerm)}</span>
          {rule.schedule_cron && <span className="u-text2"> · <code>{rule.schedule_cron}</code></span>}
          {rule.trigger_conditions && aGrupo(rule.trigger_conditions).conditions.map((c: CondicionDeRegla, i: number) => (
            <span key={i} className="u-text2">
              {i === 0 ? ' · ' : ` ${t(aGrupo(rule.trigger_conditions).match === 'any' ? 'automations.or_lbl' : 'automations.and_lbl')} `}
              {esGrupo(c) ? `(${t('automations.nested_group')})` : <>{c.field} {t('automations.op_' + c.operator)} <strong className="u-text1">{c.value}</strong></>}
            </span>
          ))}
        </div>
        <span className="aut-arrow" aria-hidden="true"><ArrowRight size={16} /></span>
        <div className="u-wrap-6">
          {actions.map((a, i) => {
            const aCfg = { icon: ACTION_ICONS[a.type] ?? ICONO_POR_DEFECTO, label: a.type }
            return (
              <div key={i} className="aut-chip aut-chip--then">
                <span className="aut-chip-kw">{t('automations.entonces_label')} </span>
                <span className="u-text1 aut-icono-texto">{aCfg.icon} {highlightText(t('automations.act_' + a.type, aCfg.label), highlightTerm)}</span>
                {a.params?.message && <span className="u-text2"> · &quot;{a.params.message.slice(0, 40)}&quot;</span>}
              </div>
            )
          })}
        </div>
      </div>

      <div className="aut-rule-meta">
        <span className="aut-icono-texto"><Zap size={12} aria-hidden="true" /> {rule.run_count || 0} {t('automations.executions')}</span>
        {rule.last_run_at && <span>{t('automations.last_exec')}: {fmtDateTime(rule.last_run_at)}</span>}
        {rule.next_run_at && rule.is_active && <span className="aut-icono-texto"><CalendarClock size={12} aria-hidden="true" /> {t('automations.next_run')}: {fmtDateTime(rule.next_run_at)}</span>}
        {rule.last_error && <span className="u-danger aut-icono-texto"><AlertTriangle size={12} aria-hidden="true" /> {rule.last_error.slice(0, 60)}</span>}
      </div>
    </div>
  )
}

// ── Rule editor modal ─────────────────────────────────────────────────────────
function RuleModal({ rule, onClose }: { rule?: ReglaDeAutomatizacion; onClose: () => void }) {
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
    actions: rule?.actions || [{ type: 'create_alert', params: { message: '', severity: 'warning' } }] as AccionDeRegla[],
  })
  const [hasCondition, setHasCondition] = useState(!!rule?.trigger_conditions)
  const inicial = aGrupo(rule?.trigger_conditions)
  const [match, setMatch] = useState(inicial.match)
  const [condiciones, setCondiciones] = useState<CondicionDeRegla[]>(
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
            <label id={`${idPrefix}-name-et`} htmlFor={`${idPrefix}-name`} className="aut-label">{t('automations.rule_name_lbl')}</label>
            <input id={`${idPrefix}-name`} aria-labelledby={`${idPrefix}-name-et`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="aut-input" placeholder={t('automations.rule_name_lbl')} />
          </div>
          <div>
            <label id={`${idPrefix}-description-et`} htmlFor={`${idPrefix}-description`} className="aut-label">{t('automations.description')}</label>
            <input id={`${idPrefix}-description`} aria-labelledby={`${idPrefix}-description-et`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} className="aut-input" />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-project`} className="aut-label">{t('automations.project_lbl')}</label>
            <select id={`${idPrefix}-project`} value={form.project_id} onChange={e => setForm(f => ({ ...f, project_id: e.target.value, is_global: !e.target.value }))} className="aut-input">
              <option value="">{t('automations.project_global')}</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
          </div>
        </div>

        {/* TRIGGER */}
        <div className="aut-section aut-section--if">
          <div className="aut-section-title">
            {t('automations.si_label')}
          </div>
          <div className="aut-section-body">
            <div>
              <label htmlFor={`${idPrefix}-trigger`} className="aut-label">{t('automations.trigger_lbl')}</label>
              <select id={`${idPrefix}-trigger`} value={form.trigger_type} onChange={e => setForm(f => ({ ...f, trigger_type: e.target.value }))} className="aut-input">
                {byCategory(triggerDefs).map(([cat, defs]) => (
                  <optgroup key={cat} label={t('automations.cat_' + cat, cat)}>
                    {defs.map(d => (
                      <option key={d.type} value={d.type}>{t('automations.trig_' + d.type, d.type)}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {catalogError && <div role="alert" className="u-field-error">{t('automations.catalog_unavailable')}</div>}
              {isScan && <div className="u-hint">{t('automations.simulation_scan')}</div>}
            </div>

            {/* Condition */}
            <div>
              <label id={`${idPrefix}-has-condition-et`} htmlFor={`${idPrefix}-has-condition`} className="aut-check">
                <input id={`${idPrefix}-has-condition`} aria-labelledby={`${idPrefix}-has-condition-et`} type="checkbox" checked={hasCondition} onChange={e => setHasCondition(e.target.checked)} />
                {t('automations.add_condition')}
              </label>
            </div>
            {isSchedule && (
              <div className="aut-box aut-box--grid2">
                <div>
                  <label id={`${idPrefix}-cron-et`} htmlFor={`${idPrefix}-cron`} className="aut-label">{t('automations.cron_lbl')}</label>
                  <input id={`${idPrefix}-cron`} aria-labelledby={`${idPrefix}-cron-et`} value={cron} onChange={e => setCron(e.target.value)} className="aut-input aut-input--mono" placeholder="0 9 * * 1-5" />
                </div>
                <div>
                  <label htmlFor={`${idPrefix}-cron-preset`} className="aut-label">{t('automations.cron_preset')}</label>
                  <select id={`${idPrefix}-cron-preset`} value={CRON_PLANTILLAS.find(([, c]) => c === cron.trim())?.[1] ?? ''} onChange={e => e.target.value && setCron(e.target.value)} className="aut-input">
                    <option value="">{t('automations.select_lbl')}</option>
                    {CRON_PLANTILLAS.map(([k, c]) => <option key={c} value={c}>{t('automations.' + k)}</option>)}
                  </select>
                </div>
                <div className="aut-box-help">{t('automations.cron_help')}</div>
              </div>
            )}
            {hasCondition && (
              <div className="aut-box aut-box--stack">
                {condiciones.length > 1 && (
                  <div role="radiogroup" aria-label={t('automations.match_lbl')} className="aut-match">
                    {(['all', 'any'] as const).map(m => (
                      <label key={m} className="aut-match-opt">
                        <input type="radio" aria-label={t('automations.match_' + m)} name={`${idPrefix}-match`} checked={match === m} onChange={() => setMatch(m)} />
                        {t('automations.match_' + m)}
                      </label>
                    ))}
                  </div>
                )}
                {condiciones.map((c, i) => esGrupo(c) ? (
                  <div key={i} className="u-text3-sm">({t('automations.nested_group')})</div>
                ) : (
                  <div key={i} className="aut-cond-row">
                    <div>
                      <label htmlFor={`${idPrefix}-condition-field-${i}`} className="aut-label">{t('automations.field_lbl')}</label>
                      <select id={`${idPrefix}-condition-field-${i}`} value={c.field || ''} onChange={e => cambiarCondicion(i, 'field', e.target.value)} className="aut-input">
                        <option value="">{t('automations.select_lbl')}</option>
                        {fields.map((f: string) => <option key={f} value={f}>{f}</option>)}
                      </select>
                    </div>
                    <div>
                      <label htmlFor={`${idPrefix}-condition-operator-${i}`} className="aut-label">{t('automations.operator_lbl')}</label>
                      <select id={`${idPrefix}-condition-operator-${i}`} value={c.operator || 'equals'} onChange={e => cambiarCondicion(i, 'operator', e.target.value)} className="aut-input">
                        {(catalog?.operators ?? []).map(o => <option key={o} value={o}>{t('automations.op_' + o, o)}</option>)}
                      </select>
                    </div>
                    <div>
                      <label id={`${idPrefix}-condition-value-${i}-et`} htmlFor={`${idPrefix}-condition-value-${i}`} className="aut-label">{t('automations.value_lbl')}</label>
                      <input id={`${idPrefix}-condition-value-${i}`} aria-labelledby={`${idPrefix}-condition-value-${i}-et`} value={c.value || ''} onChange={e => cambiarCondicion(i, 'value', e.target.value)} className="aut-input" placeholder={t('automations.value_lbl')} />
                    </div>
                    <IconButton ariaLabel={t('automations.remove_condition')} disabled={condiciones.length === 1}
                      onClick={() => setCondiciones(cs => cs.filter((_, j) => j !== i))}>
                      <X size={14} aria-hidden="true" />
                    </IconButton>
                  </div>
                ))}
                <div>
                  <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={() => setCondiciones(cs => [...cs, { field: '', operator: 'equals', value: '' }])}>
                    {t('automations.add_condition_row')}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ACTIONS */}
        <div className="aut-section aut-section--then">
          <div className="aut-section-title">
            {t('automations.entonces_label')}
          </div>
          {form.actions.map((action, i) => {
            const paramDefs = actionDefs.find(d => d.type === action.type)?.params ?? []
            return (
              <div key={i} className="aut-action">
                <div className={paramDefs.length > 0 ? 'aut-action-head aut-action-head--params' : 'aut-action-head'}>
                  <div>
                    <label htmlFor={`${idPrefix}-action-${i}`} className="aut-label">{t('automations.action_lbl')} {i + 1}</label>
                    <select id={`${idPrefix}-action-${i}`} value={action.type} onChange={e => updateAction(i, 'type', e.target.value)} className="aut-input">
                      {byCategory(actionDefs).map(([cat, defs]) => (
                        <optgroup key={cat} label={t('automations.cat_' + cat, cat)}>
                          {defs.map(d => (
                            <option key={d.type} value={d.type}>{t('automations.act_' + d.type, d.type)}</option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </div>
                  {form.actions.length > 1 && (
                    <IconButton ariaLabel={t('automations.delete_action_aria', { n: i + 1 })} onClick={() => removeAction(i)} className="aut-icon-end">
                      <X size={14} aria-hidden="true" />
                    </IconButton>
                  )}
                </div>
                {paramDefs.length > 0 && (
                  <div className="aut-params" style={{ '--aut-cols': Math.min(paramDefs.length, 3) } as CSSProperties}>
                    {paramDefs.map(param => (
                      <div key={param.key}>
                        <label htmlFor={`${idPrefix}-action-${i}-${param.key}`} className="aut-label">{t('automations.param_' + param.key, param.key)}{param.required ? ' *' : ''}</label>
                        {param.type === 'select' ? (
                          <select id={`${idPrefix}-action-${i}-${param.key}`} value={action.params?.[param.key] || ''} onChange={e => updateAction(i, param.key, e.target.value)} className="aut-input">
                            <option value="">{t('automations.select_lbl')}</option>
                            {param.options?.map((o: string) => <option key={o} value={o}>{t('automations.opt_' + o.replace('.', '_'), o)}</option>)}
                          </select>
                        ) : (
                          <input id={`${idPrefix}-action-${i}-${param.key}`} aria-label={t('automations.param_' + param.key, param.key)} type={param.type === 'number' ? 'number' : 'text'} value={action.params?.[param.key] || ''} onChange={e => updateAction(i, param.key, e.target.value)} className="aut-input" placeholder={t('automations.param_' + param.key, param.key)} />
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
          <div>
            <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={addAction}>
              {t('automations.add_action')}
            </Button>
          </div>
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
function ExecutionsModal({ rule, onClose }: { rule: ReglaDeAutomatizacion; onClose: () => void }) {
  const t = useAppT()
  const { data = [], isLoading } = useQuery({
    queryKey: ['automation_executions', rule.id],
    queryFn: () => automationsApi.executions(rule.id).then(r => r.data),
    enabled: !!rule?.id,
  })
  return (
    <Modal open title={`${t('automations.executions_title')} — ${rule.name}`} onClose={onClose} width={700}>
      <div className="aut-exec-body">
        {isLoading ? <Spinner /> : data.length === 0 ? (
          <EmptyState icon={<History size={28} />} title={t('automations.no_executions')} />
        ) : (
          <Table
            data={data}
            columns={[
              { key: 'executed_at', label: t('automations.exec_date'), render: (v) => fmtDateTime(v as string | null | undefined) },
              { key: 'success', label: t('automations.exec_status'), render: (_v, exec) => (
                <span className={exec.success ? 'u-success' : 'u-danger'}>
                  {exec.success ? t('automations.exec_status_success') : t('automations.exec_status_error')}
                </span>
              ) },
              { key: 'actions_taken', label: t('automations.exec_result'), render: (_v, exec) => (
                <div className="u-xs">
                  {(exec.actions_taken || []).map((a, i) => (
                    <div key={i} className={`aut-icono-texto ${a.ok === false ? 'u-danger' : 'u-success'}`}>{a.ok === false ? <X size={12} aria-hidden="true" /> : <Check size={12} aria-hidden="true" />} <span className="u-text1">{t('automations.act_' + a.action, a.action)}{a.error ? `: ${a.error}` : ''}</span></div>
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
  const [editing, setEditing] = useState<ReglaDeAutomatizacion | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [execHistory, setExecHistory] = useState<ReglaDeAutomatizacion | null>(null)
  const [filterActive, setFilterActive] = useState<boolean | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [testResult, setTestResult] = useState<SimulacionDeRegla | null>(null)

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['automations'],
    queryFn: () => automationsApi.list().then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })

  const { data: templates = [] } = useQuery({
    queryKey: ['auto-templates'],
    queryFn: () => automationsApi.templates().then(r => r.data),
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
    mutationFn: (id: string) => automationsApi.test(id).then(r => r.data),
    onSuccess: (data) => setTestResult(data),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: createFromTemplate } = useMutation({
    mutationFn: (tpl: PlantillaDeRegla) => automationsApi.create({
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
        <div className="aut-header-actions">
          <Button variant="secondary" icon={<FileStack size={14} />} onClick={() => setShowTemplates(true)}>
            {t('automations.templates_btn')}
          </Button>
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>
            {t('automations.new_rule_btn')}
          </Button>
        </div>
      }
    >
      <div>
      {/* Stats */}
      <div className="ds-grid-stats aut-mb">
        <KpiCard icon={<Zap size={16} />} label={t('automations.stats_active')} value={fmtNumber(active, 0)} accent />
        <KpiCard icon={<Pause size={16} />} label={t('automations.stats_paused')} value={fmtNumber(rules.length - active, 0)} />
        <KpiCard icon={<Play size={16} />} label={t('automations.stats_total_exec')} value={fmtNumber(rules.reduce((s, r) => s + (r.run_count || 0), 0), 0)} />
        <KpiCard icon={<SettingsIcon size={16} />} label={t('automations.stats_total_rules')} value={fmtNumber(rules.length, 0)} />
      </div>

      {/* Filters */}
      <div className="ds-toolbar aut-mb">
        <div className="aut-search">
          <Search size={14} aria-hidden className="aut-search-icon" />
          <input
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder={t('automations.search_placeholder')}
            aria-label={t('automations.search_aria')}
            className="ds-input"
          />
        </div>
        <select aria-label={t('automations.filter_status_aria')} className="ds-input aut-filtro-estado"
          value={filterActive === null ? 'all' : filterActive ? 'active' : 'paused'}
          onChange={e => setFilterActive(e.target.value === 'all' ? null : e.target.value === 'active')}>
          <option value="all">{t('automations.filter_all')}</option>
          <option value="active">{t('automations.filter_active')}</option>
          <option value="paused">{t('automations.filter_paused')}</option>
        </select>
      </div>

      {/* Rules list */}
      {isLoading ? <Spinner /> : searched.length === 0 ? (
        <div className="ds-card">
          <EmptyState
            icon={<Bot size={28} />}
            title={t('automations.no_rules_title')}
            description={t('automations.no_rules_desc')}
            action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('automations.new_rule_btn')}</Button>}
          />
        </div>
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
          <div className="aut-test">
            <div className="aut-test-note">{t('automations.simulation_note')}</div>
            {testResult.enabled === false && <div role="alert" className="aut-test-note aut-test-note--warn">{t('automations.simulation_off')}</div>}
            {testResult.scan && <div className="aut-test-note aut-test-note--muted">{t('automations.simulation_scan')}</div>}
            <div className="aut-test-list">
              {(testResult.results || []).map((r, i) => (
                <div key={i} className={r.ok ? 'aut-test-row aut-icono-texto' : 'aut-test-row aut-test-row--ko aut-icono-texto'}>
                  {r.ok ? <Check size={13} aria-hidden="true" /> : <X size={13} aria-hidden="true" />} <span>{t('automations.act_' + r.action, r.action)}: {r.ok ? r.would : r.error}</span>
                </div>
              ))}
            </div>
            <div className="aut-test-foot">
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
              const trigger = { icon: iconoDisparador(tpl.trigger_type), label: tpl.trigger_type }
              return (
                <div key={tpl.id} className="aut-tpl">
                  <div className="aut-tpl-name">{tpl.name}</div>
                  <div className="aut-tpl-trigger aut-icono-texto">
                    {trigger.icon} {t('automations.trig_' + tpl.trigger_type, trigger.label)}
                    {tpl.trigger_conditions && ` · ${tpl.trigger_conditions.field} ${t('automations.op_' + tpl.trigger_conditions.operator, tpl.trigger_conditions.operator)} ${tpl.trigger_conditions.value}`}
                  </div>
                  <div className="aut-tpl-actions">
                    {tpl.actions.map((a, i) => {
                      const aCfg = { icon: ACTION_ICONS[a.type] ?? ICONO_POR_DEFECTO, label: a.type }
                      return <span key={i} className="aut-tpl-action aut-icono-texto">{aCfg.icon} {t('automations.act_' + a.type, aCfg.label)}</span>
                    })}
                  </div>
                  <Button size="sm" variant="secondary" title={t('automations.use_template_aria', { name: tpl.name })} onClick={() => createFromTemplate(tpl)}>
                    {t('automations.use_template_btn')}
                  </Button>
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