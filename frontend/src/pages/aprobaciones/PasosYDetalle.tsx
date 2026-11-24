/**
 * Modal de paso y detalle de un flujo de aprobación.
 * Troceado de ApprovalsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import CondicionesDelFlujo from '../../components/aprobaciones/CondicionesDelFlujo'
import { CondicionDePaso } from '../../components/aprobaciones/CondicionesSimples'
import { Suspense, useId, useState } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalsApi } from '../../services/api'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { settingsApi } from '../../services/settingsApi'
import { Trash2, Layers, Workflow, ArrowLeft, FolderOpen, Pencil, Check, Plus } from 'lucide-react'
import {
  Button,
  Modal,
  EmptyState,
  IconButton,
  StatusBadge,
  Pulsable,
  Select,
  Checkbox,
  useErroresDeCampo,
  Input,
} from '../../components/ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useRolesReales } from '../../hooks/useRolesReales'
import {
  type ApprovalGroup,
  type ApprovalStep,
  type ApprovalWorkflow,
  approverTypeLabels,
  CATEGORIAS_DE_DOCUMENTO,
  color,
  COLORES_DE_PASO,
  type CondicionesDeDisparo,
  DisenadorDeFlujo,
  entityLabels,
  ICONO_ENTIDAD_DESCONOCIDA,
} from './compartido'

// ── Modal de paso ─────────────────────────────────────────────────────────────
function StepModal({ workflowId, step, onClose }: { workflowId: string; step: ApprovalStep | null; onClose: () => void }) {
  const t = useAppT()
  // 19-11-2026: roles reales del backend (`GET /auth/roles`); la lista local tenía roles inexistentes.
  const roles = useRolesReales({ soloInternos: true })
  const idPrefix = useId()
  const toast = useToast()
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

  // 23-11-2026 (04 A8): lista compartida de personas.
  const { data: users = [] } = useListaDeUsuarios()

  const { data: groups = [] } = useQuery<ApprovalGroup[]>({
    queryKey: ['approval-groups'],
    queryFn: () => approvalsApi.listGroups().then(r => r.data),
  })
  const { data: depts = [] } = useQuery({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (d: typeof form) => isEdit
      ? approvalsApi.updateStep(workflowId, step.id, d)
      : approvalsApi.addStep(workflowId, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] })
      toast.success(isEdit ? t('approvals.step_updated') : t('approvals.step_added'))
      onClose()
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('approvals.error_generic'))) },
  })
  const id = (k: string) => `${idPrefix}-${k}`

  return (
    <Modal open title={isEdit ? t('approvals.step_modal_edit_title') : t('approvals.step_modal_new_title')} onClose={onClose} width={560}>
      <div className="apv-rejilla-2">
        <div>
          <label htmlFor={id('name')} className="apv-label">{t('approvals.step_name_required')}</label>
          <Input id={id('name')} value={form.name} onChange={e => { campos.limpiar('name'); setForm(f => ({ ...f, name: e.target.value })) }} placeholder={t('approvals.step_name_placeholder')} inputClassName="apv-input" />{msg('name')}
        </div>
        <div>
          <label htmlFor={id('order')} className="apv-label">{t('approvals.order')}</label>
          <Input id={id('order')} type="number" value={form.step_order} onChange={e => { campos.limpiar('step_order'); setForm(f => ({ ...f, step_order: +e.target.value })) }} min="1" max="10" inputClassName="apv-input" />{msg('step_order')}
        </div>
        <div className="u-col-full">
          <label htmlFor={id('approver-type')} className="apv-label">{t('approvals.approver_type')}</label>
          <Select suelto placeholder={false} id={id('approver-type')} value={form.approver_type} onChange={e => { campos.limpiar('approver_type'); setForm(f => ({ ...f, approver_type: e.target.value })) }} className="apv-input">
            {Object.entries(approverTypeLabels(t)).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>{msg('approver_type')}
        </div>

        {form.approver_type === 'role' && (
          <div className="u-col-full">
            <label htmlFor={id('approver-role')} className="apv-label">{t('approvals.required_role')}</label>
            <Select suelto placeholder={false} id={id('approver-role')} value={form.approver_role} onChange={e => { campos.limpiar('approver_role'); setForm(f => ({ ...f, approver_role: e.target.value })) }} className="apv-input">
              <option value="">{t('approvals.select_role')}</option>
              {roles.map(r => <option key={r.id} value={r.id}>{r.etiqueta}</option>)}
            </Select>{msg('approver_role')}
          </div>
        )}

        {form.approver_type === 'user' && (
          <div className="u-col-full">
            <label htmlFor={id('approver-user')} className="apv-label">{t('approvals.approver_user_label')}</label>
            <Select suelto placeholder={false} id={id('approver-user')} value={form.approver_user_id} onChange={e => { campos.limpiar('approver_user_id'); setForm(f => ({ ...f, approver_user_id: e.target.value })) }} className="apv-input">
              <option value="">{t('approvals.select_user')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>)}
            </Select>{msg('approver_user_id')}
          </div>
        )}

        {form.approver_type === 'any_in_department' && (
          <div className="u-col-full">
            <label htmlFor={id('approver-department')} className="apv-label">{t('approvals.department')}</label>
            <Select suelto placeholder={false} id={id('approver-department')} value={form.approver_department} onChange={e => { campos.limpiar('approver_department'); setForm(f => ({ ...f, approver_department: e.target.value })) }} className="apv-input">
              <option value="">{t('approvals.sin_departamento')}</option>
              {depts.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
            </Select>{msg('approver_department')}
          </div>
        )}

        <div>
          <label htmlFor={id('timeout-hours')} className="apv-label">{t('approvals.timeout_hours')}</label>
          <Input id={id('timeout-hours')} type="number" value={form.timeout_hours} onChange={e => { campos.limpiar('timeout_hours'); setForm(f => ({ ...f, timeout_hours: +e.target.value })) }} min="1" inputClassName="apv-input" />{msg('timeout_hours')}
        </div>
        <div>
          <label htmlFor={id('on-timeout')} className="apv-label">{t('approvals.on_timeout')}</label>
          <Select suelto placeholder={false} id={id('on-timeout')} value={form.on_timeout} onChange={e => { campos.limpiar('on_timeout'); setForm(f => ({ ...f, on_timeout: e.target.value })) }} className="apv-input">
            <option value="escalate">{t('approvals.timeout_escalate')}</option>
            <option value="auto_approve">{t('approvals.timeout_auto_approve')}</option>
            <option value="reject">{t('approvals.timeout_reject')}</option>
          </Select>{msg('on_timeout')}
        </div>
        <div className="u-col-full">
          <label htmlFor={id('is-optional')} className="apv-check">
            <Checkbox id={id('is-optional')} checked={form.is_optional} onChange={(_, e) => setForm(f => ({ ...f, is_optional: e.target.checked }))} />
            {t('approvals.optional_step_label')}
          </label>
        </div>

        {form.approver_type === 'group' && (
          <div className="u-col-full">
            <label htmlFor={id('group')} className="apv-label">{t('approvals.grupo_de_aprobadores')}</label>
            <Select suelto placeholder={false} id={id('group')} value={form.approver_group_id} onChange={e => { campos.limpiar('approver_group_id'); setForm(f => ({ ...f, approver_group_id: e.target.value })) }} className="apv-input">
              <option value="">{t('approvals.seleccionar_grupo')}</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </Select>{msg('approver_group_id')}
          </div>
        )}

        <div className="u-col-full">
          <label htmlFor={id('quorum')} className="apv-check">
            <Checkbox id={id('quorum')} checked={form.parallel_quorum} onChange={(_, e) => setForm(f => ({ ...f, parallel_quorum: e.target.checked }))} />
            {t('approvals.quorum_paralelo_varios_aprobadores_simultaneos')}
          </label>
        </div>

        {form.parallel_quorum && (
          <div>
            <label htmlFor={id('req-approvals')} className="apv-label">{t('approvals.aprobaciones_requeridas')}</label>
            <Input id={id('req-approvals')} type="number" min="1" value={form.required_approvals} onChange={e => { campos.limpiar('required_approvals'); setForm(f => ({ ...f, required_approvals: +e.target.value })) }} inputClassName="apv-input" />{msg('required_approvals')}
          </div>
        )}

        <div>
          <label htmlFor={id('reminder')} className="apv-label">{t('approvals.recordatorio_horas')}</label>
          <Input id={id('reminder')} type="number" min="1" value={form.reminder_hours} onChange={e => { campos.limpiar('reminder_hours'); setForm(f => ({ ...f, reminder_hours: e.target.value ? +e.target.value : '' })) }} placeholder={t('approvals.recordatorio_ejemplo')} inputClassName="apv-input" />{msg('reminder_hours')}
        </div>

        <div className="u-col-full">
          <label htmlFor={id('adjunto')} className="apv-check">
            <Checkbox id={id('adjunto')} checked={form.requires_attachment} onChange={(_, e) => setForm(f => ({ ...f, requires_attachment: e.target.checked }))} />
            {t('approvals.requiere_adjunto_obligatorio_para_aprobar')}
          </label>
        </div>

        <fieldset className="ds-grupo-opciones u-col-full apr-regla">
          <legend className="apv-label">{t('approvals.condicion_de_paso')}</legend>
          <CondicionDePaso raw={form.step_condition} onChange={raw => { campos.limpiar('step_condition'); setForm(f => ({ ...f, step_condition: raw })) }} />
          <p className="apv-ayuda">{t('approvals.si_se_define_este_paso_solo_se')}</p>
        </fieldset>
      </div>
      <div className="u-actions-8">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => mutate(form)} loading={isPending} disabled={!form.name || isPending}>
          {isEdit ? t('approvals.save_step') : t('approvals.add_step')}
        </Button>
      </div>
    </Modal>
  )
}

// ── Detalle de flujo ──────────────────────────────────────────────────────────
export function WorkflowDetail({ workflowId, onBack }: { workflowId: string; onBack: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showStep, setShowStep] = useState(false)
  const [editStep, setEditStep] = useState<ApprovalStep | null>(null)

  const { data: wf } = useQuery<ApprovalWorkflow>({
    queryKey: ['approval-workflow', workflowId],
    queryFn: () => approvalsApi.getWorkflow(workflowId).then(r => r.data),
  })

  const { mutate: delStep } = useMutation({
    mutationFn: (sid: string) => approvalsApi.deleteStep(workflowId, sid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] }); toast.success(t('approvals.step_deleted')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const { mutate: toggleActive } = useMutation({
    mutationFn: (val: boolean) => approvalsApi.updateWorkflow(workflowId, { is_active: val }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] }),
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const { mutate: updateCategory } = useMutation({
    mutationFn: (cat: string) => approvalsApi.updateWorkflow(workflowId, {
      trigger_conditions: cat ? JSON.stringify({ category: cat }) : '{}'
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] }); toast.success(t('approvals.categoria_actualizada')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const [editingCategory, setEditingCategory] = useState(false)
  const [disenar, setDisenar] = useState(false)

  if (!wf) return null
  if (disenar) {
    return <Suspense fallback={null}><DisenadorDeFlujo workflowId={workflowId} onCerrar={() => setDisenar(false)} /></Suspense>
  }
  const steps = [...(wf.steps || [])].sort((a, b) => a.step_order - b.step_order)
  const entity = entityLabels(t)[wf.entity_type] || { label: wf.entity_type, icon: ICONO_ENTIDAD_DESCONOCIDA, color: 'var(--text-2)' }

  let parsedConditions: CondicionesDeDisparo = {}
  try { parsedConditions = JSON.parse(wf.trigger_conditions || '{}') } catch (_) { /* accesorio: condiciones guardadas ilegibles; se muestra el flujo sin condiciones en vez de romper la ficha */ }
  const configuredCategory = parsedConditions.category || ''
  const categoria = (c: string) => t(`approvals.doc_cat_${c}`, c)

  return (
    <div>
      {wf.entity_type !== 'document' && (
        <CondicionesDelFlujo workflowId={workflowId} entityType={wf.entity_type} actuales={parsedConditions}
          onGuardado={() => qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] })} />
      )}
      <div className="apv-detalle-cabecera">
        <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={onBack}>{t('approvals.back')}</Button>
        <div className="u-flex1-min0">
          <div className="apv-detalle-titulo">{wf.name}</div>
          <div className="u-text2-sm">
            <span className="apv-color apv-icono-texto" style={color(entity.color)}>{entity.icon} {entity.label}</span>
            {wf.is_default && <StatusBadge kind="accent" caps={false} className="apv-separado">{t('approvals.default_badge')}</StatusBadge>}
            {!wf.is_active && <StatusBadge kind="danger" caps={false} className="apv-separado">{t('approvals.inactive_badge')}</StatusBadge>}
            {wf.entity_type === 'document' && (
              <span className="apv-separado">
                {editingCategory ? (
                  <Select suelto placeholder={false}
                    autoFocus
                    aria-label={t('approvals.cambiar_categoria_del_documento')}
                    value={configuredCategory}
                    onBlur={e => { updateCategory(e.target.value); setEditingCategory(false) }}
                    onChange={e => { updateCategory(e.target.value); setEditingCategory(false) }}
                    className="apv-categoria-select"
                  >
                    <option value="">{t('approvals.doc_cat_todos')}</option>
                    {CATEGORIAS_DE_DOCUMENTO.map(c => <option key={c} value={c}>{categoria(c)}</option>)}
                  </Select>
                ) : (
                  <Pulsable type="button" title={t('approvals.cambiar_categoria_del_documento')} onClick={() => setEditingCategory(true)}
                    className={`apv-categoria${configuredCategory ? ' apv-categoria--puesta' : ''}`}>
                    <FolderOpen size={13} aria-hidden /> {configuredCategory ? categoria(configuredCategory) : t('approvals.todos_los_documentos')} <Pencil size={12} aria-hidden />
                  </Pulsable>
                )}
              </span>
            )}
          </div>
        </div>
        <Button variant="secondary" icon={<Workflow size={14} />} onClick={() => setDisenar(true)}>{t('pol.disenar_graficamente')}</Button>
        <Button variant="secondary" onClick={() => toggleActive(!wf.is_active)}>
          {wf.is_active ? t('approvals.deactivate') : t('approvals.activate')}
        </Button>
        <Button icon={<Plus size={14} />} onClick={() => setShowStep(true)}>{t('approvals.add_step')}</Button>
      </div>

      {steps.length === 0 ? (
        <div className="ds-card">
          <EmptyState icon={<Layers size={28} />} title={t('approvals.no_steps_defined')} description={t('approvals.no_steps_description')}
            action={<Button icon={<Plus size={14} />} onClick={() => setShowStep(true)}>{t('approvals.add_step')}</Button>} />
        </div>
      ) : (
        <ol className="apv-pasos" aria-label={t('approvals.pasos_de_aprobacion')}>
          {steps.map((step, i) => (
            <li key={step.id} className="apv-paso" style={color(COLORES_DE_PASO[i % COLORES_DE_PASO.length])}>
              <div className="apv-paso__eje" aria-hidden>
                <div className="apv-paso__numero">{step.step_order}</div>
                {i < steps.length - 1 && <div className="apv-paso__linea" />}
              </div>
              <div className="ds-card apv-paso__tarjeta">
                <div className="apv-paso__cabecera">
                  <div>
                    <div className="apv-paso__nombre">{step.name}</div>
                    <div className="u-text2-sm">
                      {approverTypeLabels(t)[step.approver_type]}
                      {step.approver_role && ` · ${t('approvals.role_prefix')}: ${step.approver_role}`}
                      {step.approver_user_name && ` · ${step.approver_user_name}`}
                      {step.approver_department && ` · ${t('approvals.dept_prefix')}: ${step.approver_department}`}
                    </div>
                    <div className="u-hint">
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
                  <div className="u-row-6">
                    <IconButton variante="caja" ariaLabel={t('approvals.edit_step_aria', { name: step.name })} onClick={() => setEditStep(step)}><Pencil size={14} aria-hidden /></IconButton>
                    <IconButton variante="caja" tono="peligro" ariaLabel={t('approvals.delete_step_aria', { name: step.name })}
                      onClick={() => openConfirmGlobal({ message: t('approvals.delete_step_confirm', { name: step.name }), onConfirm: () => delStep(step.id), danger: true })}><Trash2 size={14} aria-hidden /></IconButton>
                  </div>
                </div>
              </div>
            </li>
          ))}

          {/* Resultado final */}
          <li className="apv-paso">
            <div className="apv-paso__eje" aria-hidden><div className="apv-paso__numero apv-paso__numero--fin"><Check size={14} /></div></div>
            <div className="ds-card apv-paso__tarjeta apv-paso__tarjeta--fin">
              <div className="apv-paso__fin">{t('approvals.approved_auto_title')}</div>
              <div className="u-text2-xs-mt2">{t('approvals.approved_auto_desc')}</div>
            </div>
          </li>
        </ol>
      )}

      {(showStep || editStep) && (
        <StepModal workflowId={workflowId} step={editStep} onClose={() => { setShowStep(false); setEditStep(null) }} />
      )}
    </div>
  )
}
