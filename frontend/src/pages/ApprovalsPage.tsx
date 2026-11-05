import type { CSSProperties } from 'react'
import { useId, useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalsApi } from '../services/api'
import _api, { usersApi } from '../services/api'
import { settingsApi } from '../services/settingsApi'
import {
  CheckCircle, CheckCircle2, Info, Trash2,
  Clock as ClockIcon, Users, BarChart3, Sparkles, Layers,
} from 'lucide-react'
import { Button, Modal, EmptyState, Tabs, Page } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { UserSelect } from '../components/ui/EntitySelect'

const inp: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
const lbl: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }
const panel: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }

type EntityConfig = { label: string; icon: string; color: string }
const entityLabels = (t: (k: string) => string): Record<string, EntityConfig> => ({
  document:      { label: 'Document',       icon: '📄', color: 'var(--accent)' },
  timesheet:     { label: t('approvals.entity_timesheet'),      icon: '🕐', color: 'var(--accent)' },
  expense:       { label: t('approvals.entity_expense'),        icon: '💶', color: 'var(--warning)' },
  change_request:{ label: t('approvals.entity_change_request'), icon: '🔄', color: 'var(--purple)' },
  milestone:     { label: t('approvals.entity_milestone'),      icon: '◎', color: 'var(--success)' },
  purchase:      { label: t('approvals.entity_purchase'),       icon: '🛒', color: 'var(--danger)' },
  // v2 entity types
  invoice:       { label: 'Factura',        icon: '🧾', color: 'var(--warning)' },
  contract:      { label: 'Contrato',       icon: '📝', color: 'var(--purple)' },
  budget:        { label: 'Presupuesto',    icon: '💰', color: 'var(--success)' },
  leave:         { label: 'Ausencia',       icon: '🏖️', color: 'var(--accent)' },
  deliverable:   { label: 'Entregable',     icon: '📦', color: 'var(--text-2)' },
  proposal:      { label: 'Propuesta',      icon: '📋', color: 'var(--purple)' },
  subcontractor: { label: 'Subcontratista', icon: '🤝', color: 'var(--warning)' },
  scope_change:  { label: 'Cambio Alcance', icon: '🔀', color: 'var(--danger)' },
  hire:          { label: 'Contratación',   icon: '👤', color: 'var(--success)' },
  price_change:  { label: 'Cambio Precio',  icon: '💲', color: 'var(--danger)' },
  // Revisión 2026-11: escritura de un agente externo con MCP_WRITE_MODE=approval
  mcp_action:    { label: t('approvals.entity_mcp_action'), icon: '🔌', color: 'var(--purple)' },
})

const approverTypeLabels = (t: (k: string) => string): Record<string, string> => ({
  user: t('approvals.approver_user'),
  role: t('approvals.approver_role'),
  manager: t('approvals.approver_manager'),
  any_in_department: t('approvals.approver_any_department'),
  group: 'Grupo de aprobadores',
})

const ROLES = ['admin', 'pm', 'team_lead', 'hr', 'developer', 'designer', 'finance']

// ── Modal de paso ─────────────────────────────────────────────────────────────
function StepModal({ workflowId, step, onClose }: { workflowId: any; step: any; onClose: () => void }) {
  const traducir = useAppT()
  const t = useAppT()
  const idPrefix = useId()
  const toast = useToast()
  const _invalidate = useInvalidate()
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
    // v2 enterprise
    approver_group_id:   step?.approver_group_id   || '',
    parallel_quorum:     step?.parallel_quorum     || false,
    required_approvals:  step?.required_approvals  || 1,
    step_condition:      step?.step_condition      || '',
    requires_attachment: step?.requires_attachment || false,
    reminder_hours:      step?.reminder_hours      || '',
  })

  const { data: users = [] } = useQuery<any[]>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })

  const { data: groups = [] } = useQuery<any[]>({
    queryKey: ['approval-groups'],
    queryFn: () => approvalsApi.listGroups().then(r => r.data),
  })
  const { data: depts = [] } = useQuery<any[]>({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: (d: any) => isEdit
      ? approvalsApi.updateStep(workflowId, step.id, d)
      : approvalsApi.addStep(workflowId, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] })
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
            <select id={`${idPrefix}-approver-department`} value={form.approver_department} onChange={e => setForm(f=>({...f,approver_department:e.target.value}))} style={inp}>
              <option value="">{traducir('approvals.sin_departamento')}</option>
              {depts.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
            </select>
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

        {/* ── v2 enterprise fields ── */}
        {form.approver_type === 'group' && (
          <div style={{ gridColumn: '1/-1' }}>
            <label htmlFor={`${idPrefix}-group`} style={lbl}>{traducir('approvals.grupo_de_aprobadores')}</label>
            <select id={`${idPrefix}-group`} value={form.approver_group_id} onChange={e => setForm(f=>({...f,approver_group_id:e.target.value}))} style={inp}>
              <option value="">— Seleccionar grupo —</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
        )}

        <div style={{ gridColumn: '1/-1' }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>
            <input type="checkbox" checked={form.parallel_quorum} onChange={e => setForm(f=>({...f,parallel_quorum:e.target.checked}))} style={{ accentColor: 'var(--accent)' }} />
            {traducir('approvals.quorum_paralelo_varios_aprobadores_simultaneos')}
          </label>
        </div>

        {form.parallel_quorum && (
          <div>
            <label htmlFor={`${idPrefix}-req-approvals`} style={lbl}>Aprobaciones requeridas</label>
            <input id={`${idPrefix}-req-approvals`} type="number" min="1" value={form.required_approvals}
              onChange={e => setForm(f=>({...f,required_approvals:+e.target.value}))} style={inp} />
          </div>
        )}

        <div>
          <label htmlFor={`${idPrefix}-reminder`} style={lbl}>Recordatorio (horas, opcional)</label>
          <input id={`${idPrefix}-reminder`} type="number" min="1" value={form.reminder_hours}
            onChange={e => setForm(f=>({...f,reminder_hours:e.target.value ? +e.target.value : ''}))} style={inp} placeholder="p.e. 24" />
        </div>

        <div style={{ gridColumn: '1/-1' }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>
            <input type="checkbox" checked={form.requires_attachment} onChange={e => setForm(f=>({...f,requires_attachment:e.target.checked}))} style={{ accentColor: 'var(--accent)' }} />
            {traducir('approvals.requiere_adjunto_obligatorio_para_aprobar')}
          </label>
        </div>

        <div style={{ gridColumn: '1/-1' }}>
          <label htmlFor={`${idPrefix}-condition`} style={lbl}>{traducir('approvals.condicion_de_paso_json_opcional')}</label>
          <textarea id={`${idPrefix}-condition`} value={form.step_condition} rows={2}
            onChange={e => setForm(f=>({...f,step_condition:e.target.value}))}
            style={{...inp, resize:'vertical', fontFamily:'monospace', fontSize:'var(--text-xs)'}}
            placeholder='{"amount_gt": 5000, "department": "finance"}' />
          <p style={{ fontSize:'var(--text-xs)', color:'var(--text-3)', margin:'2px 0 0' }}>
            {traducir('approvals.si_se_define_este_paso_solo_se')}
          </p>
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
function WorkflowDetail({ workflowId, onBack }: { workflowId: any; onBack: () => void }) {
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showStep, setShowStep] = useState(false)
  const [editStep, setEditStep] = useState<any>(null)

  const { data: wf } = useQuery<any>({
    queryKey: ['approval-workflow', workflowId],
    queryFn: () => approvalsApi.getWorkflow(workflowId).then(r => r.data),
  })

  const { mutate: delStep } = useMutation({
    mutationFn: (sid: any) => approvalsApi.deleteStep(workflowId, sid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] }); toast.success(t('approvals.step_deleted')) },

    onError: e => toast.error(extractErr(e, t('approvals.error_generic')))
  })

  const { mutate: toggleActive } = useMutation({
    mutationFn: (val: any) => approvalsApi.updateWorkflow(workflowId, { is_active: val }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] }),
    onError: e => toast.error(extractErr(e, t('approvals.error_generic')))
  })

  const { mutate: updateCategory } = useMutation({
    mutationFn: (cat: any) => approvalsApi.updateWorkflow(workflowId, {
      trigger_conditions: cat ? JSON.stringify({ category: cat }) : '{}'
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] }); toast.success('Categoría actualizada') },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic')))
  })

  const [editingCategory, setEditingCategory] = useState(false)

  if (!wf) return null
  const steps = [...(wf.steps || [])].sort((a: any, b: any) => a.step_order - b.step_order)
  const entity = entityLabels(t)[wf.entity_type] || { label: wf.entity_type, icon: '○', color: 'var(--text-2)' }

  let parsedConditions: any = {}
  try { parsedConditions = JSON.parse(wf.trigger_conditions || '{}') } catch (_) {}
  const configuredCategory = parsedConditions.category || ''

  const DOC_CATEGORIES = [
    { value: '', label: '— Fallback (todos los documentos) —' },
    { value: 'contract', label: 'Contrato' },
    { value: 'deliverable', label: 'Entregable' },
    { value: 'proposal', label: 'Propuesta' },
    { value: 'sop', label: 'SOP / Procedimiento' },
    { value: 'requirements', label: 'Requisitos' },
    { value: 'meeting_notes', label: 'Actas de reunión' },
    { value: 'legal', label: 'Legal' },
    { value: 'other', label: 'Otro' },
  ]

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
            {wf.entity_type === 'document' && (
              <span style={{ marginLeft: 8 }}>
                {editingCategory ? (
                  <select
                    autoFocus
                    defaultValue={configuredCategory}
                    onBlur={e => { updateCategory(e.target.value); setEditingCategory(false) }}
                    onChange={e => { updateCategory(e.target.value); setEditingCategory(false) }}
                    style={{ fontSize: 'var(--text-2xs)', padding: '1px 4px', borderRadius: 4, border: '1px solid var(--surface-4)', background: 'var(--surface-2)', color: 'var(--text-1)', cursor: 'pointer' }}
                  >
                    {DOC_CATEGORIES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                ) : (
                  <button
                    title={traducir('approvals.cambiar_categoria_del_documento')}
                    onClick={() => setEditingCategory(true)}
                    style={{ fontSize: 'var(--text-2xs)', padding: '1px 6px', borderRadius: 4, background: configuredCategory ? 'var(--purple-bg, #ede9fe)' : 'var(--surface-3)', color: configuredCategory ? 'var(--purple, #7c3aed)' : 'var(--text-3)', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
                  >
                    {configuredCategory ? `📂 ${DOC_CATEGORIES.find(o => o.value === configuredCategory)?.label || configuredCategory}` : '📂 Todos los documentos'} ✏️
                  </button>
                )}
              </span>
            )}
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
        <EmptyState svgIcon={<Layers size={36} />} title={t('approvals.no_steps_defined')} description={t('approvals.no_steps_description')} />
      ) : (
        <div style={{ position: 'relative' }}>
          {steps.map((step, i) => {
            const color = ['var(--accent)', 'var(--success)', 'var(--warning)', 'var(--purple)', 'var(--danger)'][i % 5]
            return (
              <div key={step.id} style={{ display: 'flex', gap: 16, marginBottom: 6 }}>
                {/* Línea vertical */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 40, flexShrink: 0 }}>
                  <div style={{ width: 36, height: 36, borderRadius: '50%', background: alpha(color, '20'), border: `2px solid ${color}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-md)", fontWeight: 800, color, flexShrink: 0 }}>
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

// ── Fuera de la oficina (revisión 2026-11) ───────────────────────────────────
// Mientras dura, los avisos de mis aprobaciones llegan también al delegado y
// este puede decidir los pasos que me tocarían.
function FueraDeLaOficina() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useQuery<{ delegate_id?: string | null; away_from?: string | null; away_until?: string | null }>({
    queryKey: ['approvals-ooo'], queryFn: () => approvalsApi.getOutOfOffice().then(r => r.data),
  })
  const [form, setForm] = useState<{ delegate_id: string; away_from: string; away_until: string } | null>(null)
  const actual = form ?? { delegate_id: data?.delegate_id ?? '', away_from: data?.away_from ?? '', away_until: data?.away_until ?? '' }
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: (d: typeof actual) => approvalsApi.setOutOfOffice({ delegate_id: d.delegate_id || null, away_from: d.away_from || null, away_until: d.away_until || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approvals-ooo'] }); setForm(null); toast.success('Guardado') },
    onError: e => toast.error(extractErr(e, 'No se pudo guardar')),
  })
  const campo: CSSProperties = { padding: '6px 10px', borderRadius: 8, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', color: 'var(--text-1)', fontFamily: 'inherit' }
  return (
    <details className="ds-card" style={{ padding: '10px 14px' }} open={Boolean(data?.delegate_id)}>
      <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: 'var(--text-sm)' }}>
        Fuera de la oficina{data?.delegate_id ? ` · delegado hasta el ${data.away_until}` : ''}
      </summary>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'end', marginTop: 10 }}>
        <div style={{ minWidth: 220 }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 4 }}>Delegar en</div>
          <UserSelect value={actual.delegate_id} onChange={id => setForm({ ...actual, delegate_id: id })} placeholder="Elige a quién" />
        </div>
        <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Desde<br />
          <input type="date" value={actual.away_from} onChange={e => setForm({ ...actual, away_from: e.target.value })} style={campo} /></label>
        <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Hasta<br />
          <input type="date" value={actual.away_until} onChange={e => setForm({ ...actual, away_until: e.target.value })} style={campo} /></label>
        <Button size="sm" disabled={isPending || !actual.delegate_id || !actual.away_from || !actual.away_until} onClick={() => guardar(actual)}>Guardar</Button>
        {data?.delegate_id && <Button size="sm" variant="secondary" disabled={isPending} onClick={() => guardar({ delegate_id: '', away_from: '', away_until: '' })}>Quitar</Button>}
      </div>
    </details>
  )
}

// ── Tab de mis solicitudes pendientes ─────────────────────────────────────────
function MyPendingTab() {
  const t = useAppT()
  const { user, loading } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedIds, setSelectedIds] = useState<Set<any>>(new Set())
  const [entityFilter, setEntityFilter] = useState('all')
  const [sortMode, setSortMode] = useState('oldest') // oldest | newest

  const { data: pending = [], isLoading } = useQuery<any[]>({
    queryKey: ['approvals-pending-me'],
    queryFn: () => approvalsApi.pendingMyAction().then(r => r.data),
    refetchInterval: 30000,
    enabled: !loading && !!user,
  })

  const { mutate: decide, isPending: deciding } = useMutation({
    mutationFn: ({ id, decision, note }: { id: any; decision: string; note?: string }) => approvalsApi.decide(id, { decision, note }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approvals-pending-me'] })
      // Cascade to the affected entity caches (approval could be for timesheets, expenses, or absences)
      qc.invalidateQueries({ queryKey: ['timesheets-pending'] })
      qc.invalidateQueries({ queryKey: ['timesheets-mine'] })
      qc.invalidateQueries({ queryKey: ['expenses-pending'] })
      qc.invalidateQueries({ queryKey: ['expenses-my'] })
      qc.invalidateQueries({ queryKey: ['absences-pending'] })
      qc.invalidateQueries({ queryKey: ['team-absences'] })
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
      qc.invalidateQueries({ queryKey: ['approvals-pending-me'] })
      qc.invalidateQueries({ queryKey: ['timesheets-pending'] })
      qc.invalidateQueries({ queryKey: ['timesheets-mine'] })
      qc.invalidateQueries({ queryKey: ['expenses-pending'] })
      qc.invalidateQueries({ queryKey: ['expenses-my'] })
      qc.invalidateQueries({ queryKey: ['absences-pending'] })
      qc.invalidateQueries({ queryKey: ['team-absences'] })
    } catch (e) {
      toast.error(extractErr(e, t('approvals.bulk_approval_error')))
    } finally {
      setBulkApproving(false)
    }
  }

  const toggleSelect = (id: any) => setSelectedIds(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const toggleAll = () => setSelectedIds(prev =>
    prev.size === queue.length ? new Set() : new Set(queue.map((r: any) => r.id))
  )

  const queue = pending
    .filter((r: any) => entityFilter === 'all' ? true : r.entity_type === entityFilter)
    .sort((a: any, b: any) => {
      const ta = new Date(a.created_at || 0).getTime()
      const tb = new Date(b.created_at || 0).getTime()
      return sortMode === 'oldest' ? ta - tb : tb - ta
    })

  const statsByEntity: Record<string, number> = pending.reduce((acc: Record<string, number>, r: any) => {
    acc[r.entity_type] = (acc[r.entity_type] || 0) + 1
    return acc
  }, {})

  if (isLoading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-2)' }}>{t('approvals.loading')}</div>

  if (pending.length === 0) return (
    <div className="ds-empty">
      <CheckCircle2 size={36} className="ds-empty__icon" style={{ color: 'var(--success)' }} />
      <div className="ds-empty__title">{t('approvals.no_pending_title')}</div>
      <div className="ds-empty__desc">{t('approvals.no_pending_desc')}</div>
    </div>
  )

  return (
    <div className="ds-stack-lg">
      <FueraDeLaOficina />
      {/* Mini KPI strip */}
      <div className="ds-grid-stats">
        <div className="ds-card" style={{ padding: '12px 14px', gap: 4 }}>
          <div className="ds-eyebrow">{t('approvals.total_pending')}</div>
          <div style={{ fontSize: 'var(--text-xl-em)', fontWeight: 800, color: 'var(--warning)', lineHeight: 1.1 }}>{pending.length}</div>
        </div>
        {Object.entries(statsByEntity).slice(0, 3).map(([k, count]) => {
          const entity = entityLabels(t)[k] || { label: k, icon: '○', color: 'var(--text-2)' }
          return (
            <div key={k} className="ds-card" style={{ padding: '12px 14px', gap: 4 }}>
              <div className="ds-eyebrow">{entity.icon} {entity.label}</div>
              <div style={{ fontSize: 'var(--text-xl-em)', fontWeight: 800, color: entity.color, lineHeight: 1.1 }}>{count}</div>
            </div>
          )
        })}
      </div>

      {/* Filters */}
      <div className="ds-toolbar">
        <select aria-label={t('approvals.filter_by_entity')} value={entityFilter}
          onChange={e => setEntityFilter(e.target.value)}
          className="ds-input" style={{ width: 'auto', minWidth: 200 }}>
          <option value="all">{t('approvals.all_entities')}</option>
          {Object.entries(entityLabels(t)).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <select aria-label={t('approvals.sort_requests')} value={sortMode}
          onChange={e => setSortMode(e.target.value)}
          className="ds-input" style={{ width: 'auto', minWidth: 200 }}>
          <option value="oldest">{t('approvals.sort_oldest')}</option>
          <option value="newest">{t('approvals.sort_newest')}</option>
        </select>
      </div>

      <div className="ds-row-between">
        <label htmlFor="approvals-select-all" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: 'var(--text-base)', color: 'var(--text-2)', cursor: 'pointer' }}>
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
      <div data-export-table="approvals-export" className="ds-stack-sm">
        {queue.map((req: any) => {
          const entity = entityLabels(t)[req.entity_type] || { label: req.entity_type, icon: '○', color: 'var(--text-2)' }
          const ageHours = Math.max(0, Math.floor((Date.now() - new Date(req.created_at || Date.now()).getTime()) / 3600000))
          const isUrgent = ageHours >= 24
          return (
            <div key={req.id} className="ds-card" style={{
              background: selectedIds.has(req.id) ? 'var(--surface-3)' : 'var(--surface-2)',
              borderColor: selectedIds.has(req.id) ? 'var(--accent)' : isUrgent ? 'var(--warning-border)' : 'var(--surface-4)',
              padding: '16px 20px', gap: 0,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 'var(--space-3)' }}>
                <input
                  type="checkbox"
                  aria-label={t('approvals.select_request_aria', { name: req.entity_summary || req.entity_id })}
                  checked={selectedIds.has(req.id)}
                  onChange={() => toggleSelect(req.id)}
                  style={{ width: 15, height: 15, marginTop: 4, cursor: 'pointer', flexShrink: 0, accentColor: 'var(--accent)' }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ds-row-wrap" style={{ marginBottom: 6 }}>
                    <span className="ds-pill" style={{
                      background: alpha(entity.color, '20'), color: entity.color,
                      borderColor: alpha(entity.color, '40'),
                    }}>
                      {entity.icon} {entity.label}
                    </span>
                    {req.step_name && (
                      <span className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                        {t('approvals.step_n', { order: req.step_order })}: {req.step_name}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 4 }}>
                    {req.entity_summary || req.entity_id}
                  </div>
                  <div className="ds-muted">
                    {t('approvals.request_by')}: {req.requester_name} · {req.created_at}
                  </div>
                  {isUrgent && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--text-xs)', color: 'var(--warning)', marginTop: 4, fontWeight: 700 }}>
                      <ClockIcon size={11} />
                      {t('approvals.pending_since', { hours: ageHours })}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 'var(--space-2)', flexShrink: 0 }}>
                  <Button size="sm" variant="danger"
                    aria-label={t('approvals.reject_request_aria', { name: req.entity_summary || req.entity_id })}
                    onClick={() => decide({ id: req.id, decision: 'rejected', note: '' })}
                    disabled={deciding}>
                    {t('approvals.reject_action')}
                  </Button>
                  <Button size="sm"
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
    </div>
  )
}

function WorkflowTemplatesTab() {
  const traducir = useAppT()
  const toast = useToast()
  const idPrefix = useId()
  const qc = useQueryClient()
  const [showCreateScratch, setShowCreateScratch] = useState(false)
  const [scratch, setScratch] = useState({
    name: '',
    description: '',
    entity_type: 'document',
    is_default: false,
    document_category: '',
    steps: [
      {
        name: 'Aprobacion inicial',
        approver_type: 'role',
        approver_role: 'pm',
        approver_department: '',
        timeout_hours: 48,
        on_timeout: 'escalate',
        is_optional: false,
      },
    ],
  })

  const { data: templates = [], isLoading } = useQuery<any[]>({
    queryKey: ['approval-workflow-templates'],
    queryFn: () => approvalsApi.listTemplates().then(r => r.data || []),
  })
  const { data: depts = [] } = useQuery<any[]>({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })
  const { mutate: createFromTemplate, isPending } = useMutation({
    mutationFn: (payload: any) => approvalsApi.createFromTemplate(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      toast.success('Flujo creado desde plantilla')
    },
    onError: e => toast.error(extractErr(e, 'Error creando flujo desde plantilla')),
  })

  const { mutate: createScratchWorkflow, isPending: isCreatingScratch } = useMutation({
    mutationFn: async (payload: any) => {
      const triggerConditions = payload.entity_type === 'document' && payload.document_category
        ? JSON.stringify({ category: payload.document_category })
        : '{}'

      const created = await approvalsApi.createWorkflow({
        name: payload.name,
        description: payload.description || null,
        entity_type: payload.entity_type,
        is_default: !!payload.is_default,
        trigger_conditions: triggerConditions,
      })

      const workflowId = created?.data?.id
      const normalizedSteps = (payload.steps || [])
        .filter((s: any) => (s.name || '').trim())
        .map((s: any, idx: number) => ({
          step_order: idx + 1,
          name: s.name.trim(),
          approver_type: s.approver_type,
          approver_role: s.approver_type === 'role' ? (s.approver_role || null) : null,
          approver_department: s.approver_type === 'any_in_department' ? (s.approver_department || null) : null,
          timeout_hours: Number(s.timeout_hours || 48),
          on_timeout: s.on_timeout || 'escalate',
          is_optional: !!s.is_optional,
        }))

      for (const step of normalizedSteps) {
        await approvalsApi.addStep(workflowId, step)
      }

      return created
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      setShowCreateScratch(false)
      setScratch({
        name: '',
        description: '',
        entity_type: 'document',
        is_default: false,
        document_category: '',
        steps: [
          {
            name: 'Aprobacion inicial',
            approver_type: 'role',
            approver_role: 'pm',
            approver_department: '',
            timeout_hours: 48,
            on_timeout: 'escalate',
            is_optional: false,
          },
        ],
      })
      toast.success('Flujo creado desde cero')
    },
    onError: e => toast.error(extractErr(e, 'Error creando flujo desde cero')),
  })

  const addScratchStep = () => {
    setScratch(s => ({
      ...s,
      steps: [
        ...s.steps,
        {
          name: `Paso ${s.steps.length + 1}`,
          approver_type: 'role',
          approver_role: 'pm',
          approver_department: '',
          timeout_hours: 48,
          on_timeout: 'escalate',
          is_optional: false,
        },
      ],
    }))
  }

  const updateScratchStep = (index: number, field: string, value: any) => {
    setScratch(s => ({
      ...s,
      steps: s.steps.map((step, idx) => (idx === index ? { ...step, [field]: value } : step)),
    }))
  }

  const removeScratchStep = (index: number) => {
    setScratch(s => ({
      ...s,
      steps: s.steps.filter((_, idx) => idx !== index),
    }))
  }

  const canCreateScratch = (scratch.name || '').trim().length > 0 && (scratch.steps || []).some((s: any) => (s.name || '').trim().length > 0)

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Button onClick={() => setShowCreateScratch(true)}>Crear desde cero</Button>
      </div>

      {isLoading && <div style={{ textAlign: 'center', padding: 30, color: 'var(--text-2)' }}>Cargando plantillas...</div>}

      {!isLoading && !templates.length && (
        <EmptyState svgIcon={<Sparkles size={36} />} title={traducir('approvals.sin_plantillas')} description="No hay plantillas disponibles" />
      )}

      {!isLoading && templates.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
          {templates.map((tpl: any) => (
            <div key={tpl.id} style={{ ...panel, padding: '14px 16px' }}>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 800, marginBottom: 6 }}>{tpl.name}</div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 8 }}>{tpl.description || 'Plantilla de flujo lista para usar.'}</div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 8 }}>Entidad: {tpl.entity_type} · Pasos: {(tpl.steps || []).length}</div>
              <Button size="sm" onClick={() => createFromTemplate({ template_id: tpl.id })} loading={isPending}>Usar plantilla</Button>
            </div>
          ))}
        </div>
      )}

      {showCreateScratch && (
        <Modal open title="Crear flujo desde cero" onClose={() => setShowCreateScratch(false)} width={760}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <div>
              <label htmlFor={`${idPrefix}-scratch-name`} style={lbl}>Nombre</label>
              <input id={`${idPrefix}-scratch-name`} value={scratch.name} onChange={e => setScratch(s => ({ ...s, name: e.target.value }))} style={inp} placeholder="Ej: Aprobacion legal express" />
            </div>
            <div>
              <label htmlFor={`${idPrefix}-scratch-entity`} style={lbl}>Entidad</label>
              <select id={`${idPrefix}-scratch-entity`} value={scratch.entity_type} onChange={e => setScratch(s => ({ ...s, entity_type: e.target.value }))} style={inp}>
                {Object.entries(entityLabels(() => '')).map(([k, v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
              </select>
            </div>
            {scratch.entity_type === 'document' && (
              <div style={{ gridColumn: '1/-1' }}>
                <label htmlFor={`${idPrefix}-scratch-category`} style={lbl}>Categoria documento (opcional)</label>
                <input id={`${idPrefix}-scratch-category`} value={scratch.document_category} onChange={e => setScratch(s => ({ ...s, document_category: e.target.value }))} style={inp} placeholder="legal, deliverable, proposal..." />
              </div>
            )}
            <div style={{ gridColumn: '1/-1' }}>
              <label htmlFor={`${idPrefix}-scratch-description`} style={lbl}>Descripcion</label>
              <input id={`${idPrefix}-scratch-description`} value={scratch.description} onChange={e => setScratch(s => ({ ...s, description: e.target.value }))} style={inp} placeholder="Flujo creado manualmente desde plantillas" />
            </div>
            <label htmlFor={`${idPrefix}-scratch-default`} style={{ gridColumn: '1/-1', display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>
              <input id={`${idPrefix}-scratch-default`} type="checkbox" checked={scratch.is_default} onChange={e => setScratch(s => ({ ...s, is_default: e.target.checked }))} style={{ accentColor: 'var(--accent)' }} />
              {traducir('approvals.marcar_como_flujo_por_defecto')}
            </label>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{traducir('approvals.pasos_de_aprobacion')}</div>
            <button onClick={addScratchStep} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '6px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: 'var(--text-xs)' }}>+ Anadir paso</button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 330, overflowY: 'auto', paddingRight: 4 }}>
            {scratch.steps.map((step, idx) => (
              <div key={`${idx}-${step.name}`} style={{ border: '1px solid var(--surface-4)', borderRadius: 10, padding: 10, background: 'var(--surface-3)' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 0.7fr 0.9fr auto', gap: 8, alignItems: 'end' }}>
                  <div>
                    <label htmlFor={`${idPrefix}-step-name-${idx}`} style={lbl}>Paso {idx + 1}</label>
                    <input id={`${idPrefix}-step-name-${idx}`} value={step.name} onChange={e => updateScratchStep(idx, 'name', e.target.value)} style={inp} placeholder={traducir('approvals.nombre_del_paso')} />
                  </div>
                  <div>
                    <label htmlFor={`${idPrefix}-step-type-${idx}`} style={lbl}>Aprobador</label>
                    <select id={`${idPrefix}-step-type-${idx}`} value={step.approver_type} onChange={e => updateScratchStep(idx, 'approver_type', e.target.value)} style={inp}>
                      <option value="role">Rol</option>
                      <option value="manager">Manager</option>
                      <option value="any_in_department">Departamento</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor={`${idPrefix}-step-timeout-${idx}`} style={lbl}>Timeout(h)</label>
                    <input id={`${idPrefix}-step-timeout-${idx}`} type="number" min="1" value={step.timeout_hours} onChange={e => updateScratchStep(idx, 'timeout_hours', e.target.value)} style={inp} />
                  </div>
                  <div>
                    <label htmlFor={`${idPrefix}-step-ontimeout-${idx}`} style={lbl}>On timeout</label>
                    <select id={`${idPrefix}-step-ontimeout-${idx}`} value={step.on_timeout} onChange={e => updateScratchStep(idx, 'on_timeout', e.target.value)} style={inp}>
                      <option value="escalate">Escalar</option>
                      <option value="auto_approve">Auto aprobar</option>
                      <option value="reject">Rechazar</option>
                    </select>
                  </div>
                  <button onClick={() => removeScratchStep(idx)} disabled={scratch.steps.length === 1} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px', color: 'var(--danger)', cursor: scratch.steps.length === 1 ? 'not-allowed' : 'pointer', opacity: scratch.steps.length === 1 ? 0.5 : 1 }}>Eliminar</button>
                </div>

                {step.approver_type === 'role' && (
                  <div style={{ marginTop: 8 }}>
                    <label htmlFor={`${idPrefix}-step-role-${idx}`} style={lbl}>Rol requerido</label>
                    <select id={`${idPrefix}-step-role-${idx}`} value={step.approver_role || ''} onChange={e => updateScratchStep(idx, 'approver_role', e.target.value)} style={inp}>
                      <option value="">Seleccionar rol...</option>
                      {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </div>
                )}

                {step.approver_type === 'any_in_department' && (
                  <div style={{ marginTop: 8 }}>
                    <label htmlFor={`${idPrefix}-step-dept-${idx}`} style={lbl}>Departamento</label>
                    <select id={`${idPrefix}-step-dept-${idx}`} value={step.approver_department || ''} onChange={e => updateScratchStep(idx, 'approver_department', e.target.value)} style={inp}>
                      <option value="">{traducir('approvals.sin_departamento')}</option>
                      {depts.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
                    </select>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 14 }}>
            <button onClick={() => setShowCreateScratch(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 14px', color: 'var(--text-2)', cursor: 'pointer' }}>Cancelar</button>
            <Button onClick={() => createScratchWorkflow(scratch)} loading={isCreatingScratch} disabled={!canCreateScratch}>Crear flujo</Button>
          </div>
        </Modal>
      )}
    </>
  )
}

function WorkflowSimulatorTab() {
  const traducir = useAppT()
  const [entityType, setEntityType] = useState('document')
  const [category, setCategory] = useState('')
  const [department, setDepartment] = useState('')
  const [amount, setAmount] = useState('')
  const [requestedByUserId, setRequestedByUserId] = useState('')
  const [result, setResult] = useState<any>(null)
  const toast = useToast()
  const { data: depts = [] } = useQuery<any[]>({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })

  const { mutate: simulate, isPending } = useMutation({
    mutationFn: (payload: any) => approvalsApi.simulate(payload),
    onSuccess: (res) => setResult(res.data),
    onError: e => toast.error(extractErr(e, 'Error simulando flujo')),
  })

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12 }}>
      <div style={{ ...panel, padding: '14px 16px' }}>
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>{traducir('approvals.simula_antes_de_publicar_para_validar_ruta')}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(180px,1fr))', gap: 10 }}>
          <div>
            <label style={lbl}>Entity Type</label>
            <select value={entityType} onChange={e => setEntityType(e.target.value)} style={inp}>
              <option value="document">document</option>
              <option value="expense">expense</option>
              <option value="timesheet">timesheet</option>
              <option value="milestone">milestone</option>
              <option value="purchase">purchase</option>
            </select>
          </div>
          <div>
            <label style={lbl}>Category</label>
            <input value={category} onChange={e => setCategory(e.target.value)} style={inp} placeholder="legal, deliverable..." />
          </div>
          <div>
            <label style={lbl}>Department</label>
            <select value={department} onChange={e => setDepartment(e.target.value)} style={inp}>
              <option value="">{traducir('approvals.sin_departamento')}</option>
              {depts.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>Amount</label>
            <input value={amount} onChange={e => setAmount(e.target.value)} style={inp} type="number" placeholder="1000" />
          </div>
          <div style={{ gridColumn: 'span 2' }}>
            <label style={lbl}>Requested by user id (opcional)</label>
            <input value={requestedByUserId} onChange={e => setRequestedByUserId(e.target.value)} style={inp} placeholder={traducir('approvals.uuid_del_solicitante')} />
          </div>
        </div>
        <div style={{ marginTop: 10 }}>
          <Button onClick={() => simulate({ entity_type: entityType, context: { category, department, amount: amount ? Number(amount) : undefined, requested_by_user_id: requestedByUserId || undefined } })} loading={isPending}>Simular flujo</Button>
        </div>
      </div>

      {result && (
        <div style={{ ...panel, padding: '14px 16px' }}>
          {!result.matched ? (
            <div style={{ color: 'var(--warning)', fontWeight: 700 }}>{traducir('approvals.sin_coincidencia')} {result.reason}</div>
          ) : (
            <>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 800, marginBottom: 6 }}>Flujo seleccionado: {result.workflow?.name}</div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 8 }}>SLA estimado total: {result.estimated_total_timeout_hours}h</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {(result.route || []).map((step: any) => (
                  <div key={step.step_order} style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px', background: 'var(--surface-3)' }}>
                    <div style={{ fontSize: "var(--text-sm)", fontWeight: 700 }}>Paso {step.step_order}: {step.step_name}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>Aprobador: {step.resolved_approver || 'No resoluble'} · Timeout: {step.timeout_hours}h · On timeout: {step.on_timeout}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function exportBottlenecksCSV(items: any[], recommendations: any[], days: number, workflowFilterName: string | null) {
  const header = ['Workflow', 'Paso', 'Step name', 'Decisiones', 'Avg h', 'Reject %', 'Pending', 'SLA risk %', 'Score']
  const rows = items.map((it: any) => [
    it.workflow_name,
    it.step_order,
    it.step_name,
    it.decisions_total,
    it.avg_decision_time_hours,
    it.rejection_rate_pct,
    it.pending_count,
    it.sla_risk_pct,
    it.bottleneck_score,
  ])

  const recHeader = ['Priority', 'Title', 'Action', 'Why']
  const recRows = recommendations.map((r: any) => [r.priority, r.title, r.action, r.why])

  const escape = (v: any) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const toCSV = (hdr: any[], data: any[]) => [hdr, ...data].map((r: any) => r.map(escape).join(',')).join('\n')

  const label = workflowFilterName ? `Workflow: ${workflowFilterName}` : 'Todos los flujos'
  const content = [
    `# Bottleneck Analytics — ${label} — últimos ${days} días`,
    '',
    '## Pasos por score de cuello de botella',
    toCSV(header, rows),
    '',
    '## Recomendaciones automáticas',
    toCSV(recHeader, recRows),
  ].join('\n')

  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `bottlenecks_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function WorkflowBottlenecksTab() {
  const traducir = useAppT()
  const [days, setDays] = useState(90)
  const [workflowFilter, setWorkflowFilter] = useState('')

  const { data: workflowsData = [] } = useQuery<any[]>({
    queryKey: ['approval-workflows'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
  })

  const params = { days, ...(workflowFilter ? { workflow_id: workflowFilter } : {}) }
  const { data, isLoading, refetch, isFetching } = useQuery<any>({
    queryKey: ['approval-bottlenecks', days, workflowFilter],
    queryFn: () => approvalsApi.bottlenecks(params).then(r => r.data),
  })

  const items: any[] = data?.items || []
  const summary = data?.summary || {
    steps_analyzed: items.length,
    critical_steps: items.filter((it: any) => it.sla_risk_pct >= 80 || it.pending_count >= 3 || it.rejection_rate_pct >= 25).length,
    pending_total: items.reduce((acc: number, it: any) => acc + (it.pending_count || 0), 0),
    avg_decision_time_hours: items.length ? Number((items.reduce((acc: number, it: any) => acc + (it.avg_decision_time_hours || 0), 0) / items.length).toFixed(2)) : 0,
  }
  const topWorkflows: any[] = data?.top_workflows || []
  const weeklyTrend: any[] = data?.weekly_trend || []
  const recommendations: any[] = data?.recommendations || []

  const selectedWorkflowName = workflowFilter
    ? (workflowsData.find(w => w.id === workflowFilter)?.name || workflowFilter)
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ ...panel, padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>Ventana</span>
        <select value={String(days)} onChange={e => setDays(Number(e.target.value))} style={{ ...inp, width: 130 }}>
          <option value="30">30 dias</option>
          <option value="60">60 dias</option>
          <option value="90">90 dias</option>
          <option value="180">180 dias</option>
        </select>
        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>Flujo</span>
        <select value={workflowFilter} onChange={e => setWorkflowFilter(e.target.value)} style={{ ...inp, width: 200 }}>
          <option value="">{traducir('approvals.todos_los_flujos')}</option>
          {workflowsData.map(w => (
            <option key={w.id} value={w.id}>{w.name}</option>
          ))}
        </select>
        <Button size="sm" onClick={() => refetch()} loading={isFetching}>Actualizar</Button>
        {items.length > 0 && (
          <Button size="sm" variant="ghost" onClick={() => exportBottlenecksCSV(items, recommendations, days, selectedWorkflowName)}>
            Export CSV
          </Button>
        )}
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 28, color: 'var(--text-2)' }}>{traducir('approvals.cargando_cuellos_de_botella')}</div>
      ) : items.length === 0 ? (
        <EmptyState svgIcon={<BarChart3 size={36} />} title={traducir('approvals.sin_datos_suficientes')} description="No hay decisiones historicas para calcular cuellos de botella." />
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
            {[
              { label: 'Steps analyzed', value: summary.steps_analyzed, color: 'var(--accent)' },
              { label: 'Critical steps', value: summary.critical_steps, color: 'var(--danger)' },
              { label: 'Pending total', value: summary.pending_total, color: 'var(--warning)' },
              { label: 'Avg decision (h)', value: summary.avg_decision_time_hours, color: 'var(--text-1)' },
            ].map(k => (
              <div key={k.label} style={{ ...panel, padding: '12px 14px' }}>
                <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, color: k.color, fontFamily: 'var(--font-mono)' }}>{k.value}</div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k.label}</div>
              </div>
            ))}
          </div>

          {(topWorkflows.length > 0 || weeklyTrend.length > 0) && (
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 10 }}>
              <div style={{ ...panel, padding: '12px 14px' }}>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Top workflows at risk</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {topWorkflows.map((wf, idx) => (
                    <div key={wf.workflow_id || idx} style={{ display: 'grid', gridTemplateColumns: '1fr auto auto auto', gap: 8, alignItems: 'center', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px', background: 'var(--surface-3)' }}>
                      <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{wf.workflow_name}</span>
                      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>Score {wf.avg_bottleneck_score}</span>
                      <span style={{ fontSize: 'var(--text-xs)', color: wf.max_sla_risk_pct >= 80 ? 'var(--danger)' : wf.max_sla_risk_pct >= 50 ? 'var(--warning)' : 'var(--success)' }}>SLA {wf.max_sla_risk_pct}%</span>
                      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--warning)' }}>Pend {wf.pending_total}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ ...panel, padding: '12px 14px' }}>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Weekly rejection trend</div>
                {weeklyTrend.length === 0 ? (
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{traducir('approvals.sin_tendencia_semanal_disponible')}</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {weeklyTrend.slice(-8).map(row => (
                      <div key={row.week} style={{ display: 'grid', gridTemplateColumns: '90px 1fr 52px', gap: 8, alignItems: 'center' }}>
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{row.week}</span>
                        <div style={{ height: 8, borderRadius: 999, background: 'var(--surface-4)', overflow: 'hidden' }}>
                          <div style={{ width: `${Math.min(100, row.rejection_rate_pct)}%`, height: '100%', background: row.rejection_rate_pct >= 25 ? 'var(--danger)' : row.rejection_rate_pct >= 10 ? 'var(--warning)' : 'var(--success)' }} />
                        </div>
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>{row.rejection_rate_pct}%</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {recommendations.length > 0 && (
            <div style={{ ...panel, padding: '12px 14px' }}>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Recommended actions</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {recommendations.map((rec, idx) => (
                  <div key={`${rec.title}-${idx}`} style={{ border: '1px solid var(--surface-4)', borderRadius: 8, background: 'var(--surface-3)', padding: '10px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 'var(--text-xs)', color: rec.priority === 'high' ? 'var(--danger)' : 'var(--warning)', textTransform: 'uppercase', fontWeight: 700 }}>{rec.priority}</span>
                      <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{rec.title}</span>
                    </div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', marginTop: 4 }}>{rec.action}</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>{rec.why}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ ...panel, padding: 0, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 70px 90px 90px 90px 90px 90px', gap: 8, padding: '10px 12px', borderBottom: '1px solid var(--surface-4)', fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              <span>Paso</span>
              <span>Decis.</span>
              <span>Avg h</span>
              <span>Reject %</span>
              <span>Pending</span>
              <span>SLA risk</span>
              <span>Score</span>
            </div>
            {items.slice(0, 30).map((it) => (
              <div key={`${it.workflow_id}-${it.step_order}`} style={{ display: 'grid', gridTemplateColumns: '1.5fr 70px 90px 90px 90px 90px 90px', gap: 8, padding: '10px 12px', borderBottom: '1px solid var(--surface-4)', alignItems: 'center' }}>
                <div>
                  <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{it.workflow_name}</div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Paso {it.step_order}: {it.step_name}</div>
                </div>
                <span style={{ fontSize: 'var(--text-sm)' }}>{it.decisions_total}</span>
                <span style={{ fontSize: 'var(--text-sm)' }}>{it.avg_decision_time_hours}</span>
                <span style={{ fontSize: 'var(--text-sm)', color: it.rejection_rate_pct >= 20 ? 'var(--danger)' : 'var(--text-2)' }}>{it.rejection_rate_pct}%</span>
                <span style={{ fontSize: 'var(--text-sm)', color: it.pending_count > 0 ? 'var(--warning)' : 'var(--text-2)' }}>{it.pending_count}</span>
                <span style={{ fontSize: 'var(--text-sm)', color: it.sla_risk_pct >= 80 ? 'var(--danger)' : it.sla_risk_pct >= 50 ? 'var(--warning)' : 'var(--success)' }}>{it.sla_risk_pct}%</span>
                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{it.bottleneck_score}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Grupos de aprobadores ─────────────────────────────────────────────────────
function ApprovalGroupsTab() {
  const traducir = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { data: groups = [], isLoading } = useQuery<any[]>({
    queryKey: ['approval-groups'],
    queryFn: () => approvalsApi.listGroups().then(r => r.data),
  })
  const { data: users = [] } = useQuery<any[]>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })
  const [showCreate, setShowCreate] = useState(false)
  const [editGroup, setEditGroup] = useState<any>(null)
  const [form, setForm] = useState<{ name: string; description: string; member_ids: any[] }>({ name: '', description: '', member_ids: [] })

  const { mutate: save, isPending } = useMutation({
    mutationFn: (d: any) => editGroup ? approvalsApi.updateGroup(editGroup.id, d) : approvalsApi.createGroup(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-groups'] }); setShowCreate(false); setEditGroup(null); setForm({ name: '', description: '', member_ids: [] }); toast.success(editGroup ? 'Grupo actualizado' : 'Grupo creado') },
    onError: e => toast.error(extractErr(e, 'Error guardando grupo')),
  })
  const { mutate: del } = useMutation({
    mutationFn: approvalsApi.deleteGroup,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-groups'] }); toast.success('Grupo eliminado') },
    onError: e => toast.error(extractErr(e, 'Error eliminando grupo')),
  })

  const openEdit = (g: any) => {
    setEditGroup(g)
    const members = (() => { try { return JSON.parse(g.member_ids || '[]') } catch { return [] } })()
    setForm({ name: g.name, description: g.description || '', member_ids: members })
    setShowCreate(true)
  }

  const toggleMember = (uid: any) => setForm(f => ({
    ...f,
    member_ids: f.member_ids.includes(uid) ? f.member_ids.filter((x: any) => x !== uid) : [...f.member_ids, uid],
  }))

  if (isLoading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-2)' }}>Cargando grupos…</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button onClick={() => { setEditGroup(null); setForm({ name: '', description: '', member_ids: [] }); setShowCreate(true) }}>{traducir('approvals.nuevo_grupo')}</Button>
      </div>
      {groups.length === 0 ? (
        <EmptyState svgIcon={<Users size={36} />} title={traducir('approvals.sin_grupos')} description="Crea grupos de aprobadores para asignarlos a pasos de flujo." />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
          {groups.map(g => {
            const members = (() => { try { return JSON.parse(g.member_ids || '[]') } catch { return [] } })()
            return (
              <div key={g.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '16px 18px' }}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>👥 {g.name}</div>
                {g.description && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', marginBottom: 8 }}>{g.description}</div>}
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{members.length} miembro{members.length !== 1 ? 's' : ''}</div>
                <div style={{ display: 'flex', gap: 6, marginTop: 10, justifyContent: 'flex-end' }}>
                  <button onClick={() => openEdit(g)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: 'var(--text-xs)' }}>Editar</button>
                  <button onClick={() => openConfirmGlobal({ message: `¿Eliminar grupo "${g.name}"?`, onConfirm: () => del(g.id), danger: true })} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 'var(--text-xs)' }}>🗑</button>
                </div>
              </div>
            )
          })}
        </div>
      )}
      {showCreate && (
        <Modal open title={editGroup ? 'Editar grupo' : 'Nuevo grupo de aprobadores'} onClose={() => { setShowCreate(false); setEditGroup(null) }} width={480}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={lbl}>Nombre *</label>
              <input value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={inp} placeholder={traducir('approvals.ej_comite_financiero')} />
            </div>
            <div>
              <label style={lbl}>{traducir('approvals.description')}</label>
              <input value={form.description} onChange={e => setForm(f=>({...f,description:e.target.value}))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Miembros</label>
              <div style={{ maxHeight: 200, overflowY: 'auto', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8 }}>
                {users.map(u => (
                  <label key={u.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 0', cursor: 'pointer', fontSize: 'var(--text-sm)' }}>
                    <input type="checkbox" checked={form.member_ids.includes(u.id)} onChange={() => toggleMember(u.id)} style={{ accentColor: 'var(--accent)' }} />
                    {u.full_name} <span style={{ color: 'var(--text-3)', fontSize: 'var(--text-xs)' }}>({u.role})</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => { setShowCreate(false); setEditGroup(null) }} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => save(form)} loading={isPending} disabled={!form.name || isPending}>Guardar</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Carga de aprobadores ──────────────────────────────────────────────────────
function ApproverLoadTab() {
  const traducir = useAppT()
  const [days, setDays] = useState(90)
  const { data, isLoading } = useQuery<any>({
    queryKey: ['approver-load', days],
    queryFn: () => approvalsApi.approverLoad({ days }).then(r => r.data),
  })

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16 }}>
        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{traducir('approvals.periodo')}</span>
        {[30, 60, 90, 180].map(d => (
          <button key={d} onClick={() => setDays(d)}
            style={{ background: days === d ? 'var(--accent)' : 'var(--surface-3)', border: 'none', borderRadius: 6, padding: '4px 12px', color: days === d ? '#fff' : 'var(--text-2)', cursor: 'pointer', fontSize: 'var(--text-xs)' }}>
            {d}d
          </button>
        ))}
      </div>
      {isLoading ? (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-2)' }}>{traducir('approvals.cargando_carga_de_aprobadores')}</div>
      ) : !data ? null : (
        <>
          {(data.overloaded_approvers || []).length > 0 && (
            <div style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger)', borderRadius: 10, padding: '12px 16px', marginBottom: 16 }}>
              <strong style={{ color: 'var(--danger)' }}>⚠ Aprobadores sobrecargados:</strong>
              <span style={{ marginLeft: 8, fontSize: 'var(--text-sm)', color: 'var(--text-1)' }}>{data.overloaded_approvers.join(', ')}</span>
            </div>
          )}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--surface-4)' }}>
                  {['Aprobador', 'Pendientes', 'Tiempo Resp. (h)', 'Tasa Rechazo', 'Score Carga', ''].map(h => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-2)', fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data.load || []).map((row: any) => (
                  <tr key={row.user_id} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 600 }}>{row.user_name}</td>
                    <td style={{ padding: '10px 12px' }}>{row.pending_count}</td>
                    <td style={{ padding: '10px 12px' }}>{row.avg_response_hours != null ? row.avg_response_hours.toFixed(1) : '—'}</td>
                    <td style={{ padding: '10px 12px' }}>{row.rejection_rate != null ? (row.rejection_rate * 100).toFixed(0) + '%' : '—'}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: row.load_score > 7 ? 'var(--danger)' : row.load_score > 4 ? 'var(--warning)' : 'var(--success)' }}>
                        {row.load_score?.toFixed(1) || '—'}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      {row.load_score > 7 && <span style={{ fontSize: 'var(--text-xs)', padding: '2px 8px', borderRadius: 4, background: 'var(--danger-bg)', color: 'var(--danger)', fontWeight: 700 }}>Sobrecargado</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

// ── Matriz de aprobación ──────────────────────────────────────────────────────
function ApprovalMatrixTab({ workflows = [] }: { workflows?: any[] }) {
  const traducir = useAppT()
  const t = useAppT()
  const entityMap = entityLabels(t)
  const entityTypes = Object.keys(entityMap)
  // Collect all unique workflow names (across entity types)
  const allWorkflowNames = [...new Set(workflows.map((w: any) => w.name))]

  return (
    <div>
      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', marginBottom: 16 }}>
        {traducir('approvals.vista_de_que_flujos_estan_activos_por')}
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 'var(--text-xs)', minWidth: 600 }}>
          <thead>
            <tr>
              <th style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-2)', fontWeight: 600, minWidth: 130 }}>Entidad</th>
              {allWorkflowNames.map(name => (
                <th key={name} style={{ padding: '8px 10px', textAlign: 'center', color: 'var(--text-2)', fontWeight: 600, minWidth: 100 }}>{name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entityTypes.map(et => {
              const cfg = entityMap[et]
              return (
                <tr key={et} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                  <td style={{ padding: '8px 12px', fontWeight: 600 }}>
                    {cfg.icon} {cfg.label}
                  </td>
                  {allWorkflowNames.map(name => {
                    const wf = workflows.find(w => w.entity_type === et && w.name === name)
                    if (!wf) return <td key={name} style={{ padding: '8px 10px', textAlign: 'center', color: 'var(--text-3)' }}>—</td>
                    const bg = wf.is_default ? 'var(--success)' : wf.is_active ? 'var(--accent)' : 'var(--surface-4)'
                    const color = wf.is_active ? '#fff' : 'var(--text-3)'
                    return (
                      <td key={name} style={{ padding: '8px 10px', textAlign: 'center' }}>
                        <span style={{ background: bg, color, borderRadius: 4, padding: '2px 8px', fontWeight: 600 }}>
                          {wf.is_default ? 'Default' : wf.is_active ? 'Activo' : 'Inactivo'}
                        </span>
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
interface ApprovalsPageProps {
  mode?: string
}

export default function ApprovalsPage({ mode = 'inbox' }: ApprovalsPageProps): JSX.Element {
  const traducir = useAppT()
  const createIdPrefix = useId()
  const t = useAppT()
  const { user, loading } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const isConfigMode = mode === 'config'
  const [tab, setTab]           = useState(isConfigMode ? 'workflows' : 'pending')
  const [selected, setSelected] = useState<any>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', entity_type: 'timesheet', is_default: false, document_category: '', chain_on_approval_workflow_id: '', sla_block_on_breach: false, auto_approval_rules: '' })
  const canQueryProtected = !loading && !!user

  const { data: workflows = [], isLoading } = useQuery<any[]>({
    queryKey: ['approval-workflows'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
    enabled: canQueryProtected && tab === 'workflows',
  })

  const { data: stats } = useQuery<any>({
    queryKey: ['approval-stats'],
    queryFn: () => approvalsApi.stats().then(r => r.data),
    enabled: canQueryProtected && tab === 'workflows',
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: approvalsApi.createWorkflow,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      setShowCreate(false)
      setSelected(res.data.id)
      toast.success(t('approvals.workflow_created'))
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const { mutate: del } = useMutation({
    mutationFn: approvalsApi.deleteWorkflow,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-workflows'] }); toast.success(t('approvals.workflow_deleted')) },

    onError: e => toast.error(extractErr(e, t('approvals.error_generic')))
  })

  const runValidate = async (e: any, workflowId: any) => {
    e.stopPropagation()
    try {
      const res = await approvalsApi.validateWorkflow(workflowId)
      if (res.data?.valid) {
        toast.success('Flujo valido y listo para publicar')
      } else {
        toast.error(`Flujo no valido: ${(res.data?.issues || []).join(' | ') || 'revisar configuracion'}`)
      }
    } catch (err) {
      toast.error(extractErr(err, 'Error validando flujo'))
    }
  }

  const runPublish = async (e: any, workflowId: any) => {
    e.stopPropagation()
    try {
      await approvalsApi.publishWorkflow(workflowId)
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      toast.success('Flujo publicado')
    } catch (err) {
      toast.error(extractErr(err, 'Error publicando flujo'))
    }
  }

  const runClone = async (e: any, workflowId: any) => {
    e.stopPropagation()
    try {
      await approvalsApi.cloneVersion(workflowId, {})
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      toast.success('Nueva version clonada')
    } catch (err) {
      toast.error(extractErr(err, 'Error clonando flujo'))
    }
  }

  if (selected) return <WorkflowDetail workflowId={selected} onBack={() => setSelected(null)} />

  return (
    <Page
      icon={<CheckCircle size={18} />}
      title={isConfigMode ? t('approvals.page_title_config') : t('approvals.page_title_inbox')}
      subtitle={isConfigMode ? t('approvals.page_subtitle_config') : t('approvals.page_subtitle_inbox')}
    >
      <div className="ds-card--inset" style={{
        display: 'flex', alignItems: 'flex-start', gap: 'var(--space-2)',
      }}>
        <Info size={14} aria-hidden style={{ color: 'var(--accent)', flexShrink: 0, marginTop: 2 }} />
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
          {isConfigMode ? t('approvals.info_config') : t('approvals.info_inbox')}
        </div>
      </div>

      {/* KPIs */}
      {stats && tab === 'workflows' && (
        <div className="ds-grid-stats">
          {[
            { label: t('approvals.pending'),  value: stats.pending,  color: 'var(--warning)' },
            { label: t('approvals.approved'), value: stats.approved, color: 'var(--success)' },
            { label: t('approvals.rejected'), value: stats.rejected, color: 'var(--danger)'  },
            { label: t('approvals.active_flows'), value: workflows.filter(w => w.is_active).length, color: 'var(--accent)' },
          ].map(k => (
            <div key={k.label} className="ds-card" style={{ padding: '14px 16px', textAlign: 'center', gap: 4 }}>
              <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, color: k.color, fontFamily: 'var(--font-mono)', lineHeight: 1.1 }}>{k.value}</div>
              <div className="ds-eyebrow">{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <Tabs
        items={
          isConfigMode
            ? [
              { id: 'workflows',   label: t('approvals.tab_workflows') },
              { id: 'templates',   label: 'Templates' },
              { id: 'simulator',   label: 'Simulator' },
              { id: 'bottlenecks', label: 'Bottlenecks' },
              { id: 'groups',      label: 'Grupos' },
              { id: 'load',        label: 'Carga' },
              { id: 'matrix',      label: 'Matriz' },
            ]
            : [{ id: 'pending', label: t('approvals.my_pending') }]
        }
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
            <EmptyState svgIcon={<CheckCircle2 size={36} />} title={t('approvals.no_workflows')}
              description={t('approvals.workflows_description')} />
          ) : (
            <div data-export-table="approvals-export" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
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
                        background: 'var(--surface-2)', border: `1px solid ${wf.is_active ? alpha(cfg.color, '30') : 'var(--surface-4)'}`,
                        borderRadius: 12, padding: '16px 20px', cursor: 'pointer',
                        opacity: wf.is_active ? 1 : 0.6,
                        transition: 'border-color 0.15s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.borderColor = alpha(cfg.color, '60')}
                      onMouseLeave={e => e.currentTarget.style.borderColor = wf.is_active ? alpha(cfg.color, '30') : 'var(--surface-4)'}
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
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6, flexWrap: 'wrap' }}>
                        <button onClick={(e) => runValidate(e, wf.id)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>Validar</button>
                        <button onClick={(e) => runPublish(e, wf.id)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 10px', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>Publicar</button>
                        <button onClick={(e) => runClone(e, wf.id)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>Clonar v</button>
                        <button aria-label={t('approvals.workflow_delete_aria', { name: wf.name })}
                          onClick={e => { e.stopPropagation(); openConfirmGlobal({ message: t('approvals.workflow_delete_confirm', { name: wf.name }), onConfirm: () => del(wf.id), danger: true }) }}
                          style={{
                            background: 'transparent', border: '1px solid var(--surface-4)',
                            borderRadius: 'var(--radius-sm)', padding: '4px 8px',
                            color: 'var(--danger)', cursor: 'pointer',
                            display: 'inline-flex', alignItems: 'center',
                          }}>
                          <Trash2 size={12} />
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

      {tab === 'templates' && isConfigMode && <WorkflowTemplatesTab />}
      {tab === 'simulator' && isConfigMode && <WorkflowSimulatorTab />}
      {tab === 'bottlenecks' && isConfigMode && <WorkflowBottlenecksTab />}
      {tab === 'groups' && isConfigMode && <ApprovalGroupsTab />}
      {tab === 'load' && isConfigMode && <ApproverLoadTab />}
      {tab === 'matrix' && isConfigMode && <ApprovalMatrixTab workflows={workflows} />}

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
            {form.entity_type === 'document' && (
              <div>
                <label htmlFor={`${createIdPrefix}-doc-category`} style={lbl}>{traducir('approvals.categoria_del_documento')}</label>
                <select id={`${createIdPrefix}-doc-category`} value={form.document_category} onChange={e => setForm(f=>({...f,document_category:e.target.value}))} style={inp}>
                  <option value="">{traducir('approvals.fallback_aplica_a_todos_los_documentos')}</option>
                  <option value="contract">Contrato</option>
                  <option value="deliverable">Entregable</option>
                  <option value="proposal">Propuesta</option>
                  <option value="sop">SOP / Procedimiento</option>
                  <option value="requirements">Requisitos</option>
                  <option value="meeting_notes">{traducir('approvals.actas_de_reunion')}</option>
                  <option value="legal">Legal</option>
                  <option value="other">Otro</option>
                </select>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', marginTop: 4 }}>{traducir('approvals.si_no_se_especifica_categoria_este_flujo')}</div>
              </div>
            )}
            <div>
              <label htmlFor={`${createIdPrefix}-description`} style={lbl}>{t('approvals.description')}</label>
              <input id={`${createIdPrefix}-description`} value={form.description} onChange={e => setForm(f=>({...f,description:e.target.value}))} style={inp} placeholder={t('approvals.description_placeholder')} />
            </div>
            <label htmlFor={`${createIdPrefix}-is-default`} style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>
              <input id={`${createIdPrefix}-is-default`} type="checkbox" checked={form.is_default} onChange={e => setForm(f=>({...f,is_default:e.target.checked}))} style={{ accentColor: 'var(--accent)' }} />
              {t('approvals.default_flow_label')}
            </label>
            {/* v2 enterprise */}
            <div>
              <label htmlFor={`${createIdPrefix}-chain`} style={lbl}>{traducir('approvals.encadenar_con_flujo_al_aprobar_opcional')}</label>
              <select id={`${createIdPrefix}-chain`} value={form.chain_on_approval_workflow_id}
                onChange={e => setForm(f=>({...f,chain_on_approval_workflow_id:e.target.value}))} style={inp}>
                <option value="">{traducir('approvals.sin_encadenamiento')}</option>
                {workflows.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </div>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>
              <input type="checkbox" checked={form.sla_block_on_breach} onChange={e => setForm(f=>({...f,sla_block_on_breach:e.target.checked}))} style={{ accentColor: 'var(--accent)' }} />
              {traducir('approvals.bloquear_entidad_si_se_supera_el_sla')}
            </label>
            <div>
              <label htmlFor={`${createIdPrefix}-auto-rules`} style={lbl}>{traducir('approvals.reglas_de_auto_aprobacion_json_opcional')}</label>
              <textarea id={`${createIdPrefix}-auto-rules`} value={form.auto_approval_rules} rows={2}
                onChange={e => setForm(f=>({...f,auto_approval_rules:e.target.value}))}
                style={{...inp, resize:'vertical', fontFamily:'monospace', fontSize:'var(--text-xs)'}}
                placeholder='[{"condition":"amount_lt","value":100,"action":"auto_approve"}]' />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowCreate(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>{t('common.cancel')}</button>
            <Button onClick={() => {
              const { document_category, ...rest } = form
              const trigger_conditions = (form.entity_type === 'document' && document_category)
                ? JSON.stringify({ category: document_category })
                : '{}'
              create({ ...rest, trigger_conditions })
            }} loading={creating} disabled={!form.name || creating}>{t('approvals.create_workflow')}</Button>
          </div>
        </Modal>
      )}
    </Page>
  )
}
