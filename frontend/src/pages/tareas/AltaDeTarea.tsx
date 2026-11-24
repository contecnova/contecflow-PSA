/**
 * Modal de creación de tarea.
 * Troceado de TasksPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState, useId } from 'react'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { customFieldsApi, semanticApi, usersApi, type ProjectListItem, type PersonaVisible } from '../../services/api'
import { Button, Modal, Select, Checkbox, IconButton, useErroresDeCampo, Input } from '../../components/ui'
import { Brain, X } from 'lucide-react'
import { fmtNumber, extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import AIInlineEditor from '../../components/AIInlineEditor'
import { useAppT } from '../../i18n/AppLangContext'
import ExternalizarTarea from '../../components/proveedores/ExternalizarTarea'
import { asignacionExclusiva } from '../proveedores/logica'
import DateInput from '../../components/ui/DateInput'
import {
  type CustomField,
  type CustomValues,
  ESTILO_EDITOR_ALTA,
  etiquetaDeCampo,
  type NewTaskForm,
  nombreDeComplejidad,
  type SemEffort,
  type SemSuggestion,
  tareas,
  type TaskBody,
} from './compartido'
import { useWorkflowStatusOptions } from './TarjetasKanban'

export function CreateTaskModal({ open, onClose, projects }: { open: boolean; onClose: () => void; projects: ProjectListItem[] }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: users = [] } = useQuery<PersonaVisible[]>({
    // Selector de personas: `/users/directory` sirve a cualquier rol (`/users` da 403 al subcontratado).
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
  })
  const [form, setForm] = useState<NewTaskForm>({
    title: '', project_id: '', status: 'todo', priority: 'medium',
    estimated_hours: '', start_date: '', due_date: '', description: '', assignee_id: '', supplier_id: '', supplier_work_package_id: '',
  })
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const [semSuggestion, setSemSuggestion] = useState<SemSuggestion | null>(null)
  const [semEffort, setSemEffort] = useState<SemEffort | null>(null)
  const [suggesting, setSuggesting] = useState(false)
  const [pendingSuggestion, setPendingSuggestion] = useState<SemSuggestion | null>(null)
  const [customValues, setCustomValues] = useState<CustomValues>({})

  const { data: customFields = [] } = useQuery<CustomField[]>({
    queryKey: ['custom-fields', form.project_id],
    queryFn: () => customFieldsApi.list(form.project_id).then(r => r.data),
    enabled: !!form.project_id,
    retry: false,
  })

  const statusOptions = useWorkflowStatusOptions(form.project_id, t)

  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: async ({ taskData, cfValues, cfFields }: { taskData: TaskBody; cfValues: CustomValues; cfFields: CustomField[] }) => {
      const res = await tareas.create(taskData)
      const task = res.data
      if (cfFields.length > 0 && task?.id) {
        const payload = cfFields.map(f => ({ field_id: f.id, value: cfValues[f.id] ?? null }))
        await customFieldsApi.setValues(task.project_id, task.id, payload)
      }
      return task
    },
    onSuccess: newTask => {
      if (pendingSuggestion?.suggested_user_id && newTask?.id) {
        semanticApi.recordAssignment({
          item_type: 'task',
          item_id: newTask.id,
          item_title: newTask.title || '',
          suggested_user_id: pendingSuggestion.suggested_user_id,
          // 23-11-2026: la persona con la que se creó de verdad; si no es la sugerida,
          // el servidor la registra como rechazada; si lo es, queda pendiente hasta cerrar.
          accepted_user_id: newTask.assignee_id || null,
          confidence: pendingSuggestion.confidence,
          needs_review: pendingSuggestion.needs_review,
          engine_mode: pendingSuggestion.engine_mode,
          reasoning: pendingSuggestion.reasoning,
        }).catch(() => { /* accesorio: registrar la asignación solo alimenta el bucle de feedback; no debe frenar la tarea */ })
      }
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-my-tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] })
      qc.invalidateQueries({ queryKey: ['cal-tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban-board'] })
      onClose()
      setForm({ title: '', project_id: '', status: 'todo', priority: 'medium', estimated_hours: '', start_date: '', due_date: '', description: '', assignee_id: '', supplier_id: '', supplier_work_package_id: '' })
      setCustomValues({})
      setSemSuggestion(null); setSemEffort(null); setPendingSuggestion(null)
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  const set = (k: keyof NewTaskForm) => (e: { target: { value: string } }) => { campos.limpiar(k); setForm(f => ({ ...f, [k]: e.target.value })) }
  // 19-11-2026: persona o proveedor, excluyentes; cambiar de proyecto vacía el proveedor (sus paquetes son del proyecto).
  const asignar = (k: 'assignee_id' | 'supplier_id' | 'supplier_work_package_id', v: string) => {
    campos.limpiar(k)
    setForm(f => asignacionExclusiva(f, k, v))
  }

  const analyzeWithAI = async () => {
    if (!form.title) return
    setSuggesting(true)
    setSemSuggestion(null); setSemEffort(null)
    try {
      const [sugRes, effortRes] = await Promise.all([
        semanticApi.suggestTask({ title: form.title, description: form.description, project_id: form.project_id || undefined }),
        semanticApi.estimateEffort({ title: form.title, description: form.description }),
      ])
      setSemSuggestion(sugRes.data)
      setSemEffort(effortRes.data)
    } catch (e) { setSemSuggestion({ error: extractErr(e, t('common.error')) }) }
    finally { setSuggesting(false) }
  }

  const acceptSuggestion = () => {
    if (semSuggestion?.suggested_user_id) {
      setForm(f => asignacionExclusiva(f, 'assignee_id', semSuggestion.suggested_user_id || ''))
      // Store suggestion so we can persist SemAssignment once the task is created (task.id is known)
      setPendingSuggestion({ ...semSuggestion })
    }
    if (semEffort?.base_hours && !form.estimated_hours)
      setForm(f => ({ ...f, estimated_hours: String(semEffort.base_hours) }))
    setSemSuggestion(null); setSemEffort(null)
  }

  return (
    <Modal open={open} onClose={onClose} title={t('tasks.new_task')} width={580}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <Input label={t('tasks.title_required')} id={`${idCampo}-1`} value={form.title} onChange={set('title')} placeholder={t('tasks.task_title')} />
          {msg('title')}
        </div>
        <div className="u-col-full">
          <Select label={t('tasks.project_required')} placeholder={false} id={`${idCampo}-2`} value={form.project_id} onChange={e => { campos.limpiar('project_id'); setForm(f => ({ ...f, project_id: e.target.value, supplier_id: '', supplier_work_package_id: '' })) }}>
            <option value="">{t('tasks.select_project_option')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </Select>
          {msg('project_id')}
        </div>
        <div>
          <Select label={t('common.status')} placeholder={false} id={`${idCampo}-3`} value={form.status} onChange={set('status')}>
            {statusOptions.map(o => (
              <option key={o.value} value={o.value}>{o.icon} {o.label}</option>
            ))}
          </Select>
          {msg('status')}
        </div>
        <div>
          <Select label={t('common.priority')} placeholder={false} id={`${idCampo}-4`} value={form.priority} onChange={set('priority')}>
            <option value="low">{t('tasks.priority_low')}</option>
            <option value="medium">{t('tasks.priority_medium')}</option>
            <option value="high">{t('tasks.priority_high')}</option>
            <option value="critical">{t('tasks.priority_critical')}</option>
          </Select>
          {msg('priority')}
        </div>
        {/* Asignación + estimación con IA */}
        <div className="u-col-full">
          <div className="tsk-label-row tsk-label-row--lg">
            <label id={`${idCampo}-asignado-et`} htmlFor={`${idCampo}-asignado`} className="uiinde-estiloetiqueta">{t('tasks.assignee')}</label>
            <Button size="xs" variant="ghost" icon={<Brain size={13} />} onClick={analyzeWithAI} disabled={!form.title} loading={suggesting}>
              {t('tasks.ai_analyze')}
            </Button>
          </div>
          <Select suelto placeholder={false} id={`${idCampo}-asignado`} value={form.assignee_id} onChange={e => asignar('assignee_id', e.target.value)} className="tsk-input tsk-input--lg">
            <option value="">{t('tasks.no_assignee')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>
          {msg('assignee_id')}
        </div>
        {/* Externalizar a un proveedor de outsourcing (excluyente con el asignado) */}
        <ExternalizarTarea projectId={form.project_id} supplierId={form.supplier_id} paqueteId={form.supplier_work_package_id}
          onChange={asignar} idBase={idCampo} claseEtiqueta="tsk-label tsk-label--lg" claseControl="tsk-input tsk-input--lg" error={msg} />
        {/* Banner de sugerencia IA */}
        {(semSuggestion || semEffort) && !semSuggestion?.error && (
          <div className="tsk-ai tsk-ai--modal" role="status">
            <div className="u-flex1">
              <div className="tsk-ai-title">{t('tasks.ai_analysis')}</div>
              <div className="tsk-ai-items">
                {semSuggestion?.suggested_user_name && (
                  <div>
                    <div className="u-text2-2xs">{t('tasks.ai_person_label')}</div>
                    <div className="tsk-ai-value">
                      {semSuggestion.suggested_user_name}
                      <span className="tsk-ai-note">
                        {Math.round((semSuggestion.confidence||0)*100)}%
                      </span>
                    </div>
                  </div>
                )}
                {semEffort && (
                  <div>
                    <div className="u-text2-2xs">{t('tasks.ai_effort_label')}</div>
                    <div className="tsk-ai-value tsk-ai-value--warning">
                      {fmtNumber(semEffort.base_hours, 1)}h
                      <span className={`tsk-ai-cx tsk-cx--${semEffort.complexity}`}>
                        {nombreDeComplejidad(t, semEffort.complexity)}
                      </span>
                    </div>
                  </div>
                )}
              </div>
              {semSuggestion?.reasoning && <div className="tsk-ai-reason">{semSuggestion.reasoning}</div>}
            </div>
            <div className="u-row-6">
              <Button size="sm" onClick={acceptSuggestion}>{t('tasks.ai_apply')}</Button>
              <IconButton variante="caja" onClick={() => { setSemSuggestion(null); setSemEffort(null) }} ariaLabel={t('tasks.descartar_sugerencia')}><X size={14} aria-hidden /></IconButton>
            </div>
          </div>
        )}
        <div>
          <Input label={t('tasks.estimated_hours')} id={`${idCampo}-horas`} type="number" min="0" step="0.5" value={form.estimated_hours} onChange={set('estimated_hours')} placeholder={t('tasks.estimated_hours')} />
          {msg('estimated_hours')}
        </div>
        <div>
          <DateInput label={t('tasks.date_start')} id={`${idCampo}-5`} value={form.start_date} onChange={set('start_date')} />
          {msg('start_date')}
        </div>
        <div>
          <DateInput label={t('tasks.due_date')} id={`${idCampo}-6`} value={form.due_date} onChange={set('due_date')} />
          {msg('due_date')}
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-descripcion-et`} htmlFor={`${idCampo}-descripcion`} className="uiinde-estiloetiqueta">{t('common.description')} <span className="tsk-label-hint">{t('tasks.description_hint')}</span></label>
          <AIInlineEditor inputId={`${idCampo}-descripcion`} value={form.description} onChange={val => set('description')({ target: { value: val } })} rows={3} placeholder={t('common.description')} style={ESTILO_EDITOR_ALTA} />
          {msg('description')}
        </div>
        {/* Campos personalizados del proyecto */}
        {customFields.length > 0 && (
          <div className="tsk-span-full-top">
            <div className="tsk-label tsk-label--lg tsk-label--mb10">{t('tasks.custom_fields_label')}</div>
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
        <div className="tsk-modal-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate({ taskData: form, cfValues: customValues, cfFields: customFields })} disabled={isPending || !form.title || !form.project_id} loading={isPending}>
            {isPending ? t('tasks.creating') : t('tasks.create_task_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
