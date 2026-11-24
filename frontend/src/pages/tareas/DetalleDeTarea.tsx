/**
 * Modal de detalle de una tarea.
 * Troceado de TasksPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState, useEffect, useId } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useInvalidate } from '../../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tasksApi, customFieldsApi, semanticApi, issueTypesApi, usersApi, type PersonaVisible } from '../../services/api'
import { Button, Avatar, Tabs, Drawer, Select, Checkbox, IconButton, useErroresDeCampo, Input, Textarea } from '../../components/ui'
import { Ban, Brain, Building2, CalendarClock, CheckCircle2, Clock, Pencil, Save, Trash2, X } from 'lucide-react'
import { fmtDate, fmtNumber, extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useAuth } from '../../context/AuthContext'
import DocumentsPanel from '../../components/DocumentsPanel'
import AIInlineEditor from '../../components/AIInlineEditor'
import { useAppT } from '../../i18n/AppLangContext'
import ExternalizarTarea from '../../components/proveedores/ExternalizarTarea'
import PanelTicketAPr from '../../components/ticket-a-pr/PanelTicketAPr'
import { asignacionExclusiva } from '../proveedores/logica'
import DateInput from '../../components/ui/DateInput'
import {
  type CustomField,
  type CustomFieldValue,
  type CustomValues,
  ESTILO_EDITOR_DETALLE,
  type IssueType,
  nombreDeComplejidad,
  nombreDeEstado,
  nombreDePrioridadT,
  type SemEffort,
  type SemSuggestion,
  tareas,
  type Task,
  type TaskBody,
  type TaskForm,
  etiquetaDeCampo,
} from './compartido'
import { HistorialDeMovimientos, useWorkflowStatusOptions } from './TarjetasKanban'
import CorregirAsignacion from '../../components/asignacion-ia/CorregirAsignacion'

export function TaskDetailModal({ task, open, onClose }: { task: Task | null; open: boolean; onClose: () => void }) {
  const idCampo = useId()
  const puedeBorrar = useAuth().puede('tareas.gestionar')
  const puedeVerTicketAPr = useAuth().puede('ticket_pr.ver')
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { invalidate: _invalidate } = useInvalidate()
  const [tab, setTab]         = useState('detail')  // detail | comments | docs
  const [isEditing, setIsEditing] = useState(false)
  const [comment, setComment] = useState('')
  const [form, setForm]       = useState<TaskForm | null>(null)
  const [semSuggestion, setSemSuggestion] = useState<SemSuggestion | null>(null)
  const [semEffort, setSemEffort]         = useState<SemEffort | null>(null)
  const [suggesting, setSuggesting]       = useState(false)
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null

  // Reset editing mode and form whenever the task changes or modal opens
  useEffect(() => {
    if (task) {
      setIsEditing(false)
      setForm({
        title:           task.title           || '',
        description:     task.description     || '',
        status:          task.status          || 'todo',
        priority:        task.priority        || 'medium',
        assignee_id:     task.assignee_id     || task.assignee?.id || '',
        supplier_id:     task.supplier_id     || '',
        supplier_work_package_id: task.supplier_work_package_id || '',
        estimated_hours: task.estimated_hours ?? '',
        start_date:      task.start_date      ? task.start_date.split('T')[0] : '',
        due_date:        task.due_date        ? task.due_date.split('T')[0] : '',
        blocked_reason:  task.blocked_reason  || '',
        tags:            task.tags            || '',
        issue_type:      task.issue_type      || '',
      })
    }
  }, [task])

  const { data: users = [] } = useQuery<PersonaVisible[]>({
    // Selector de personas: `/users/directory` sirve a cualquier rol (`/users` da 403 al subcontratado).
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
  })

  const statusOptions = useWorkflowStatusOptions(task?.project_id, t)

  // Auditoría 2026-11: el catálogo de /issue-types no llegaba a las tareas.
  const { data: issueTypes = [] } = useQuery<IssueType[]>({
    queryKey: ['issue-types', task?.project_id],
    queryFn: () => issueTypesApi.list(task.project_id).then(r => r.data),
    enabled: !!task?.project_id,
    retry: false,
  })
  const { data: customFields = [] } = useQuery<CustomField[]>({
    queryKey: ['custom-fields', task?.project_id],
    queryFn: () => customFieldsApi.list(task.project_id).then(r => r.data),
    enabled: !!task?.project_id,
    retry: false,
  })
  const { data: rawCustomValues } = useQuery<CustomFieldValue[]>({
    queryKey: ['custom-field-values', task?.id],
    queryFn: () => customFieldsApi.getValues(task.project_id, task.id).then(r => r.data),
    enabled: !!task?.id && !!task?.project_id,
    retry: false,
  })
  const [customValues, setCustomValues] = useState<CustomValues>({})
  useEffect(() => {
    const map: CustomValues = {}
    ;(rawCustomValues ?? []).forEach(v => { map[v.field_id] = v.value ?? '' })
    setCustomValues(map)
  }, [rawCustomValues])

  const { mutate: saveTask, isPending: saving } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: async ({ taskData, cfValues, cfFields, taskId, projectId }: { taskData: TaskBody; cfValues: CustomValues; cfFields: CustomField[]; taskId: string; projectId: string }) => {
      await tareas.update(taskId, taskData)
      if (cfFields.length > 0) {
        const payload = cfFields.map(f => ({ field_id: f.id, value: cfValues[f.id] ?? null }))
        await customFieldsApi.setValues(projectId, taskId, payload)
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); qc.invalidateQueries({ queryKey: ['dash-my-tasks'] }); qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] }); qc.invalidateQueries({ queryKey: ['cal-tasks'] }); qc.invalidateQueries({ queryKey: ['kanban-board'] }); setIsEditing(false); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('common.error'))) },
  })

  const { mutate: deleteTask, isPending: deleting } = useMutation({
    mutationFn: () => tasksApi.delete(task.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); qc.invalidateQueries({ queryKey: ['dash-my-tasks'] }); qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] }); qc.invalidateQueries({ queryKey: ['cal-tasks'] }); qc.invalidateQueries({ queryKey: ['kanban-board'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('common.error'))),
  })

  const { mutate: addComment, isPending: commenting } = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) => tareas.comment(id, content),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); setComment('') },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const analyzeWithAI = async () => {
    if (!form?.title) return
    setSuggesting(true); setSemSuggestion(null); setSemEffort(null)
    try {
      const [s, e] = await Promise.all([
        semanticApi.suggestTask({ title: form.title, description: form.description }),
        semanticApi.estimateEffort({ title: form.title, description: form.description }),
      ])
      setSemSuggestion(s.data); setSemEffort(e.data)
    } catch (err) { toast.error(extractErr(err, t('common.error'))) } finally { setSuggesting(false) }
  }

  const acceptSuggestion = () => {
    if (semSuggestion?.suggested_user_id) {
      setForm(f => f && asignacionExclusiva(f, 'assignee_id', semSuggestion.suggested_user_id || ''))
      // Persist SemAssignment so the feedback loop has a base row for this task
      semanticApi.recordAssignment({
        item_type: 'task',
        item_id: task.id,
        item_title: form.title || task.title || '',
        suggested_user_id: semSuggestion.suggested_user_id,
        accepted_user_id: semSuggestion.suggested_user_id,
        // 23-11-2026: el veredicto lo pone el servidor (pendiente hasta cerrar o reasignar).
        confidence: semSuggestion.confidence,
        needs_review: semSuggestion.needs_review,
        engine_mode: semSuggestion.engine_mode,
        reasoning: semSuggestion.reasoning,
      }).catch(() => { /* accesorio: registrar la asignación solo alimenta el bucle de feedback; no debe frenar la tarea */ })
    }
    if (semEffort?.base_hours && !form.estimated_hours)
      setForm(f => ({ ...f, estimated_hours: String(semEffort.base_hours) }))
    setSemSuggestion(null); setSemEffort(null)
  }

  const cancelEdit = () => {
    // Revert form to current task values
    setForm({
      title:           task.title           || '',
      description:     task.description     || '',
      status:          task.status          || 'todo',
      priority:        task.priority        || 'medium',
      assignee_id:     task.assignee_id     || task.assignee?.id || '',
      supplier_id:     task.supplier_id     || '',
      supplier_work_package_id: task.supplier_work_package_id || '',
      estimated_hours: task.estimated_hours ?? '',
      start_date:      task.start_date      ? task.start_date.split('T')[0] : '',
      due_date:        task.due_date        ? task.due_date.split('T')[0] : '',
      blocked_reason:  task.blocked_reason  || '',
      tags:            task.tags            || '',
      issue_type:      task.issue_type      || '',
    })
    setSemSuggestion(null); setSemEffort(null)
    setIsEditing(false)
  }

  const set = (k: keyof TaskForm) => (e: { target: { value: string } }) => { campos.limpiar(k); setForm(f => ({ ...f, [k]: e.target.value })) }
  // 19-11-2026: persona o proveedor, excluyentes (422 `proveedor_asignacion_exclusiva` si van los dos).
  const asignar = (k: 'assignee_id' | 'supplier_id' | 'supplier_work_package_id', v: string) => {
    campos.limpiar(k)
    setForm(f => f && asignacionExclusiva(f, k, v))
  }
  if (!open || !task || !form) return null

  return (
    <Drawer onClose={onClose} ariaLabel={task.title || task.code || t('tasks.tarea')} width={520} zIndex={200}>
        {/* Drawer header */}
        <div className="tsk-drawer-head">
          <span className="tsk-drawer-code">{task.code}</span>
          <IconButton variante="caja" onClick={onClose} ariaLabel={t('common.close')} data-cierra-dialogo="">
            <X size={16} />
          </IconButton>
        </div>
        {/* Scrollable body */}
        <div className="tsk-drawer-body">

      {/* Tabs */}
      <div className="tsk-drawer-tabs">
        <Tabs
          items={[
            { id: 'detail',   label: t('tasks.tab_details') },
            { id: 'comments', label: t('tasks.tab_comments'), count: task.comments?.length },
            { id: 'docs',     label: t('tasks.tab_docs') },
            { id: 'history',  label: t('tasks.tab_historial') },
          ]}
          active={tab}
          onChange={setTab}
          ariaLabel={t('tasks.tab_details')}
        />
      </div>

      {/* ── DETALLES / EDITAR ── */}
      {tab === 'detail' && !isEditing && (
        <div className="tsk-tab-panel">
          {/* Title */}
          <div className="tsk-detail-title">{task.title}</div>

          {/* Status + Priority row */}
          <div className="tsk-chips">
            <span className={`tsk-chip tsk-tone-s--${task.status}`}>
              {nombreDeEstado(t, task.status)}
            </span>
            <span className={`tsk-chip tsk-tone-p--${task.priority}`}>
              {nombreDePrioridadT(t, task.priority)}
            </span>
          </div>

          {/* Info grid */}
          <div className="tsk-info-grid">
            <div className="tsk-info">
              <div className="tsk-eyebrow">{t('tasks.assignee')}</div>
              {task.assignee ? (
                <div className="u-row-center-8">
                  <Avatar name={task.assignee.full_name} size={22} />
                  <span className="u-base-600">{task.assignee.full_name}</span>
                  {/* 23-11-2026: la IA eligió mal → persona correcta (aprende el motor) y se reasigna. */}
                  <CorregirAsignacion itemType="task" itemId={task.id} asignadoActual={task.assignee_id || task.assignee.id}
                    onCorregida={async uid => {
                      await tareas.update(task.id, { assignee_id: uid })
                      qc.invalidateQueries({ queryKey: ['tasks'] }); qc.invalidateQueries({ queryKey: ['kanban-board'] })
                    }} />
                </div>
              ) : task.supplier_name ? (
                <span className="u-row-center-8 u-base-600" title={t('proveedores.externalizada_a', { nombre: task.supplier_name })}>
                  <Building2 size={14} aria-hidden />{t('proveedores.externalizada_a', { nombre: task.supplier_name })}
                </span>
              ) : <span className="tsk-base tsk-base--muted">{t('tasks.no_assignee')}</span>}
            </div>
            <div className="tsk-info">
              <div className="tsk-eyebrow">{t('tasks.hours_label')}</div>
              <span className="u-base-600">
                {t('tasks.horas_real', { h: fmtNumber(task.real_hours ?? 0, 1) })}
                {task.estimated_hours ? ` / ${t('tasks.horas_est', { h: fmtNumber(task.estimated_hours, 1) })}` : ''}
              </span>
            </div>
            {task.start_date && (
              <div className="tsk-info">
                <div className="tsk-eyebrow">{t('tasks.start_date_label')}</div>
                <span className="tsk-base">{fmtDate(task.start_date)}</span>
              </div>
            )}
            {task.due_date && (
              <div className="tsk-info">
                <div className="tsk-eyebrow">{t('tasks.due_date')}</div>
                <span className={`tsk-base${new Date(task.due_date) < new Date() && task.status !== 'done' ? ' tsk-base--overdue' : ''}`}>
                  {fmtDate(task.due_date)}
                </span>
              </div>
            )}
          </div>

          {/* Description */}
          {task.description && (
            <div className="tsk-info tsk-info--block">
              <div className="tsk-eyebrow tsk-eyebrow--mb6">{t('common.description')}</div>
              <div className="tsk-description">{task.description}</div>
            </div>
          )}

          {/* Blocked reason */}
          {task.status === 'blocked' && task.blocked_reason && (
            <div className="tsk-blocked">
              <div className="tsk-blocked-title"><Ban size={13} aria-hidden />{t('tasks.blocked_label')}</div>
              <div className="u-text2-base">{task.blocked_reason}</div>
            </div>
          )}

          {/* Tags */}
          {task.tags && (
            <div className="u-mb-14">
              <div className="tsk-eyebrow tsk-eyebrow--mb6">{t('tasks.tags_label')}</div>
              <div className="tsk-tags">
                {String(task.tags).split(',').filter(Boolean).map(tag => (
                  <span key={tag} className="tsk-tag">#{tag.trim()}</span>
                ))}
              </div>
            </div>
          )}

          {/* Custom fields (read-only) */}
          {customFields.length > 0 && (rawCustomValues?.length ?? 0) > 0 && (
            <div className="tsk-cf-block">
              <div className="tsk-eyebrow tsk-eyebrow--mb8">{t('tasks.custom_fields_label')}</div>
              <div className="tsk-cf-grid">
                {customFields.map(f => {
                  const val = customValues[f.id]
                  if (!val && val !== 0) return null
                  return (
                    <div key={f.id} className="tsk-cf">
                      <div className="tsk-cf-name">{f.name}</div>
                      <div className="tsk-cf-value">{String(val)}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Footer actions */}
          <div className="tsk-footer">
            {/* Borrar exige admin o pm en el servidor (revisión 2026-11) */}
            {puedeBorrar ? (
            <Button variant="ghost" className="tsk-borrar" icon={<Trash2 size={14} />} onClick={() => { openConfirmGlobal({ message: t('tasks.confirmar_eliminar'), onConfirm: () => deleteTask(), danger: true }) }} disabled={deleting}>
              {deleting ? t('tasks.deleting') : t('common.delete')}
            </Button>
            ) : <span />}
            <Button icon={<Pencil size={14} />} onClick={() => setIsEditing(true)}>{t('common.edit')}</Button>
          </div>
        </div>
      )}

      {/* ── MODO EDICIÓN ── */}
      {tab === 'detail' && isEditing && (
        <div className="tsk-tab-panel tsk-edit-grid">

          {/* Título */}
          <div className="u-col-full">
            <Input label={t('tasks.title_required')} id={`${idCampo}-1`} value={form.title} onChange={set('title')} />
            {msg('title')}
          </div>

          {/* Estado + Prioridad */}
          <div>
            <Select label={t('common.status')} placeholder={false} id={`${idCampo}-2`} value={form.status} onChange={set('status')}>
              {statusOptions.map(o => (
                <option key={o.value} value={o.value}>{o.icon} {o.label}</option>
              ))}
            </Select>
            {msg('status')}
          </div>
          <div>
            <Select label={t('common.priority')} placeholder={false} id={`${idCampo}-3`} value={form.priority} onChange={set('priority')}>
              <option value="low">{t('tasks.priority_low')}</option>
              <option value="medium">{t('tasks.priority_medium')}</option>
              <option value="high">{t('tasks.priority_high')}</option>
              <option value="critical">{t('tasks.priority_critical')}</option>
            </Select>
            {msg('priority')}
          </div>

          {/* Asignado + botón IA */}
          <div className="u-col-full">
            <div className="tsk-label-row">
              <label id={`${idCampo}-asignado-et`} htmlFor={`${idCampo}-asignado`} className="uiinde-estiloetiqueta">{t('tasks.assignee')}</label>
              <Button size="xs" variant="ghost" icon={<Brain size={13} />} onClick={analyzeWithAI} disabled={!form.title} loading={suggesting}>
                {t('tasks.ai_suggest')}
              </Button>
            </div>
            <Select suelto placeholder={false} id={`${idCampo}-asignado`} value={form.assignee_id} onChange={e => asignar('assignee_id', e.target.value)} className="tsk-input">
              <option value="">{t('tasks.no_assignee')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </Select>
            {msg('assignee_id')}
            {(semSuggestion || semEffort) && !semSuggestion?.error && (
              <div className="tsk-ai" role="status">
                <div>
                  <div className="tsk-ai-title">{t('tasks.ai_analysis')}</div>
                  <div className="tsk-ai-items">
                    {semSuggestion?.suggested_user_name && (
                      <div>
                        <div className="u-text2-2xs">{t('tasks.ai_person_label')}</div>
                        <div className="u-base-700">{semSuggestion.suggested_user_name} <span className="tsk-ai-note">{Math.round((semSuggestion.confidence||0)*100)}%</span></div>
                      </div>
                    )}
                    {semEffort && (
                      <div>
                        <div className="u-text2-2xs">{t('tasks.ai_effort_label')}</div>
                        <div className="tsk-ai-value tsk-ai-value--warning">{fmtNumber(semEffort.base_hours, 1)}h <span className={`tsk-ai-cx tsk-cx--${semEffort.complexity}`}>{nombreDeComplejidad(t, semEffort.complexity)}</span></div>
                      </div>
                    )}
                  </div>
                </div>
                <div className="u-row-6">
                  <Button size="xs" onClick={acceptSuggestion}>{t('tasks.ai_apply')}</Button>
                  <IconButton variante="caja" onClick={() => { setSemSuggestion(null); setSemEffort(null) }} ariaLabel={t('tasks.descartar_sugerencia')}><X size={14} aria-hidden /></IconButton>
                </div>
              </div>
            )}
          </div>

          {/* Externalizar a un proveedor de outsourcing (excluyente con el asignado) */}
          <ExternalizarTarea projectId={task.project_id} supplierId={form.supplier_id} paqueteId={form.supplier_work_package_id}
            nombreActual={task.supplier_name} onChange={asignar} idBase={idCampo} claseEtiqueta="tsk-label" claseControl="tsk-input" error={msg} />

          <div>
            <Select label={t('tasks.issue_type')} placeholder={false} id={`${idCampo}-tipo`} value={form.issue_type} onChange={set('issue_type')}>
              <option value="">—</option>
              {issueTypes.map(it => (
                <option key={it.id} value={it.value}>{it.icon} {it.name}</option>
              ))}
            </Select>
            {msg('issue_type')}
          </div>

          {/* Horas + Fechas */}
          <div>
            <Input label={t('tasks.estimated_hours')} id={`${idCampo}-horas`} type="number" value={form.estimated_hours} onChange={set('estimated_hours')} placeholder={t('tasks.estimated_hours')} min="0" step="0.5" />
            {msg('estimated_hours')}
          </div>
          <div className="tsk-dates">
            <div>
              <DateInput label={t('tasks.date_start')} id={`${idCampo}-4`} value={form.start_date} onChange={set('start_date')} />
              {msg('start_date')}
            </div>
            <div>
              <DateInput label={t('tasks.due_date')} id={`${idCampo}-5`} value={form.due_date} onChange={set('due_date')} />
              {msg('due_date')}
            </div>
          </div>

          {/* Descripción */}
          <div className="u-col-full">
            <label id={`${idCampo}-descripcion-et`} htmlFor={`${idCampo}-descripcion`} className="uiinde-estiloetiqueta">{t('common.description')} <span className="tsk-label-hint">{t('tasks.description_hint')}</span></label>
            <AIInlineEditor inputId={`${idCampo}-descripcion`} value={form.description} onChange={val => set('description')({ target: { value: val } })} rows={4} style={ESTILO_EDITOR_DETALLE} />
            {msg('description')}
          </div>

          {/* Motivo bloqueo */}
          {form.status === 'blocked' && (
            <div className="u-col-full">
              <Input label={t('tasks.blocked_reason')} id={`${idCampo}-6`} value={form.blocked_reason} onChange={set('blocked_reason')} placeholder={t('tasks.blocked_reason_placeholder')} />
              {msg('blocked_reason')}
            </div>
          )}

          {/* Tags */}
          <div className="u-col-full">
            <Input label={t('tasks.tags_label')} id={`${idCampo}-7`} value={form.tags} onChange={set('tags')} placeholder={t('tasks.tags_placeholder')} />
            {msg('tags')}
          </div>

          {/* Campos personalizados */}
          {customFields.length > 0 && (
            <div className="tsk-span-full-top">
              <div className="tsk-label tsk-label--mb10">{t('tasks.custom_fields_label')}</div>
              <div className="u-grid2-12">
                {customFields.map(f => (
                  <div key={f.id} className={(f.field_type === 'text' || f.field_type === 'url') ? 'u-col-full' : undefined}>
                    {/* 24-11-2026 (campos al kit): la etiqueta es la prop `label` del control del kit. */}
                    {f.field_type === 'select' ? (
                      <Select label={etiquetaDeCampo(f)} placeholder={false} value={customValues[f.id] ?? ''} onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))}>
                        <option value="">{t('tasks.select_option')}</option>
                        {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                      </Select>
                    ) : f.field_type === 'boolean' ? (
                      <Checkbox label={etiquetaDeCampo(f)} checked={customValues[f.id] === 'true'} onChange={m => setCustomValues(v => ({ ...v, [f.id]: m ? 'true' : 'false' }))} />
                    ) : f.field_type === 'date' ? (
                      <DateInput label={etiquetaDeCampo(f)}
                        value={String(customValues[f.id] ?? '')}
                        onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))}
                      />
                    ) : (
                      <Input label={etiquetaDeCampo(f)}
                        type={f.field_type === 'number' ? 'number' : f.field_type === 'url' ? 'url' : 'text'}
                        value={customValues[f.id] ?? ''}
                        onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Info solo lectura */}
          <div className="tsk-readonly">
            <span><Clock size={13} aria-hidden />{t('tasks.real_hours')}: <strong className="u-text1">{fmtNumber(task.real_hours ?? 0, 1)}h</strong></span>
            <span><CalendarClock size={13} aria-hidden />{t('tasks.created_label')}: <strong className="u-text1">{fmtDate(task.created_at)}</strong></span>
            {task.completed_at && <span><CheckCircle2 size={13} aria-hidden />{t('tasks.completed_label')}: <strong className="u-success">{fmtDate(task.completed_at)}</strong></span>}
          </div>

          {/* Acciones edición */}
          <div className="tsk-edit-actions">
            {/* Borrar exige admin o pm en el servidor (revisión 2026-11) */}
            {puedeBorrar ? (
            <Button variant="ghost" className="tsk-borrar" icon={<Trash2 size={14} />} onClick={() => { openConfirmGlobal({ message: t('tasks.confirmar_eliminar'), onConfirm: () => deleteTask(), danger: true }) }} disabled={deleting}>
              {deleting ? t('tasks.deleting') : t('common.delete')}
            </Button>
            ) : <span />}
            <div className="u-row-8">
              <Button variant="secondary" onClick={cancelEdit}>{t('common.cancel')}</Button>
              <Button icon={<Save size={14} />} onClick={() => saveTask({ taskData: { ...form, issue_type: form.issue_type || null }, cfValues: customValues, cfFields: customFields, taskId: task.id, projectId: task.project_id })} disabled={!form.title} loading={saving}>
                {saving ? t('common.saving') : t('tasks.save_changes')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── HISTORIAL de movimientos (revisión 2026-11: lo enseñaba la pantalla Kanban) ── */}
      {tab === 'history' && <HistorialDeMovimientos taskId={task.id} />}

      {/* ── COMENTARIOS ── */}
      {tab === 'comments' && (
        <div className="tsk-tab-panel">
          {(!task.comments || task.comments.length === 0) ? (
            <p className="tsk-empty-comments">{t('tasks.no_comments')}</p>
          ) : (
            <div className="tsk-comments">
              {task.comments.map(c => (
                <div key={c.id} className="u-row-10">
                  <Avatar name={c.author?.full_name || '?'} size={28} />
                  <div className="tsk-comment">
                    <div className="u-text2-xs-mb4">
                      <strong className="u-text1">{c.author?.full_name}</strong> · {fmtDate(c.created_at)}
                    </div>
                    <div className="tsk-comment-body">{c.content}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="u-row-8">
            <Textarea aria-label={t('tasks.add_comment')} value={comment} onChange={e => setComment(e.target.value)}
              placeholder={t('tasks.add_comment')}
              rows={2}
              inputClassName="tsk-comment-input"
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && comment) addComment({ id: task.id, content: comment }) }}
            />
            <Button onClick={() => addComment({ id: task.id, content: comment })} disabled={!comment || commenting}>{t('tasks.send_comment')}</Button>
          </div>
          <div className="u-hint">{t('tasks.send_hint')}</div>
        </div>
      )}

      {/* ── DOCUMENTOS ── */}
      {tab === 'docs' && (
        <div className="tsk-tab-panel">
          <DocumentsPanel taskId={task.id} />
        </div>
      )}

      {/* «Del ticket al PR» (migración 203): agente de código que propone el arreglo como PR. */}
      {tab === 'detail' && !isEditing && puedeVerTicketAPr && (
        <div className="tsk-tab-panel">
          <PanelTicketAPr tipo="task" id={task.id} />
        </div>
      )}
        </div>
    </Drawer>
  )
}
