/**
 * Alta y edición de proyecto (incluye `contract_amount`).
 * Troceado de ProjectsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState, useEffect, useMemo, useId } from 'react'
import LeccionesQueAplican from '../../components/lecciones/LeccionesQueAplican'
import { useToast } from '../../context/ToastContext'
import { useInvalidate } from '../../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi } from '../../services/api'
import type { ProjectCreatePayload } from '../../services/api'
import { settingsApi } from '../../services/settingsApi'
import { Button, Modal, ClientSelect, Select, useErroresDeCampo, Input, Textarea } from '../../components/ui'
import { extractErr } from '../../utils/helpers'
import { OpcionesDeCatalogo } from '../../components/catalogos/Catalogo'
import { BILLING_TYPES } from '../../constants/api'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { getFirstIssueByField } from '../../utils/formValidation'
import DateInput from '../../components/ui/DateInput'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { PROJECT_STATUSES, RISK_LEVELS, makeProjectFormSchema } from './compartido'
import type { CambioDeCampo, ProjectSummary, ProjectDetail, ProjectForm } from './compartido'

export function ProjectFormModal({ open, onClose, project = null }: { open: boolean; onClose: () => void; project?: ProjectSummary | null }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const traducir = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { invalidate: _invalidate } = useInvalidate()
  const t = useAppT()
  const isEdit = !!project
  const projectFormSchema = useMemo(() => makeProjectFormSchema(t), [t])

  // Cargar datos completos del proyecto cuando se edita
  const { data: fullProject } = useQuery({
    queryKey: ['project', project?.id],
    queryFn: () => projectsApi.get(project.id).then(r => r.data as ProjectDetail),
    enabled: !!project?.id,
  })

  // Usar fullProject si está disponible (tiene todos los campos), sino el project del prop
  const src: ProjectDetail = fullProject || project

  const [form, setForm] = useState<ProjectForm>({
    name: '', project_type: '', status: 'planning',
    client_name: '', department: '', budget_amount: '', contract_amount: '',
    description: '', risk_level: 'low',
    start_date: '', end_date_planned: '',
    client_id: '', billing_type: '',
    retainer_amount: '', retainer_day: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const campos = useErroresDeCampo()
  const err = (k: string) => errors[k] ?? campos.de(k)

  // Actualizar el form cuando lleguen los datos completos
  useEffect(() => {
    if (src) {
      setForm({
        name: src.name || '',
        project_type: src.project_type || '',
        status: src.status || 'planning',
        client_name: src.client_name || '',
        department: src.department || '',
        budget_amount: src.budget_amount || '',
        contract_amount: src.contract_amount ?? '',
        description: src.description || '',
        risk_level: src.risk_level || 'low',
        start_date: src.start_date?.split('T')[0] || '',
        end_date_planned: src.end_date_planned?.split('T')[0] || '',
        client_id: src.client_id || '',
        billing_type: src.billing_type || '',
        retainer_amount: src.retainer_amount || '',
        retainer_day: src.retainer_day || '',
      })
    }
  }, [src, src?.id, fullProject])

  const { data: departments = [] } = useQuery({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })


  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (data: ProjectForm) => {
      if (isEdit) {
        // En edición: convertir strings vacíos a null para poder borrar valores,
        // pero mantener 0 y false como valores válidos
        const clean = Object.fromEntries(
          Object.entries(data).map(([k, v]) => [k, v === '' ? null : v])
        )
        return projectsApi.update(project.id, clean)
      } else {
        // En creación: filtrar campos vacíos para no enviar nulls innecesarios
        const clean: Partial<ProjectForm> = Object.fromEntries(
          Object.entries(data).filter(([, v]) => v !== '' && v !== null && v !== undefined)
        )
        // `ProjectCreatePayload` sigue a `ProjectCreate`, que admite `status`, `risk_level`,
        // `billing_type` y `retainer_*` (auditoría 2026-11, #25). El formulario guarda los
        // importes como texto: pydantic los convierte a número.
        return projectsApi.create(clean as ProjectCreatePayload)
      }
    },
    onSuccess: (_saved) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      qc.invalidateQueries({ queryKey: ['project'] })
      qc.invalidateQueries({ queryKey: ['dash-projects-health'] })
      qc.invalidateQueries({ queryKey: ['dash-pipeline'] })
      // Sincronización bidireccional: si cambió el cliente, actualizar vista de Clientes
      qc.invalidateQueries({ queryKey: ['clients'] })
      qc.invalidateQueries({ queryKey: ['client-detail'] })
      qc.invalidateQueries({ queryKey: ['client-projects-linked'] })
      qc.invalidateQueries({ queryKey: ['client-projects-available'] })
      // Invalidar el detalle específico del proyecto editado
      if (isEdit && project?.id) {
        qc.invalidateQueries({ queryKey: ['project', project.id] })
      }
      onClose()
    },
    onError: e => { if (!campos.recoger(e)) toast.error(extractErr(e, t('proyectos_ui.error_guardar'))) },
  })

  const set = (k: keyof ProjectForm) => (e: CambioDeCampo) => { campos.limpiar(k); setForm(f => ({ ...f, [k]: e.target.value })) }
  const validateForm = () => {
    const parsed = projectFormSchema.safeParse(form)
    if (parsed.success) {
      setErrors({})
      return true
    }
    setErrors(getFirstIssueByField(parsed.error))
    return false
  }
  return (
    <Modal open={open} onClose={onClose} title={isEdit ? t('proyectos_ui.editar_titulo', { nombre: project.name }) : t('proyectos_ui.nuevo_proyecto')} width={600}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <Input label={t('proyectos_ui.nombre_req')} id={`${idCampo}-nombre`} value={form.name} onChange={set('name')} placeholder={traducir('projects.nombre_del_proyecto')} aria-label={traducir('projects.nombre_del_proyecto')} />
          {err('name') && <div className="u-field-error">{err('name')}</div>}
        </div>
        <div>
          <Select label={t('proyectos_ui.tipo_req')} placeholder={false} id={`${idCampo}-1`} value={form.project_type} onChange={set('project_type')}>
            <option value="">{t('proyectos_ui.seleccionar')}</option>
            <OpcionesDeCatalogo catalogo="project-types" />
          </Select>
          {err('project_type') && <div className="u-field-error">{err('project_type')}</div>}
        </div>
        <div>
          <Select label={t('proyectos_ui.col_estado')} placeholder={false} id={`${idCampo}-2`} value={form.status} onChange={set('status')}>
            {PROJECT_STATUSES.map(o => <option key={o.value} value={o.value}>{t(o.label)}</option>)}
          </Select>
          {err('status') && <div className="u-field-error">{err('status')}</div>}
        </div>
        <div>
          <Select label={t('proyectos_ui.col_riesgo')} placeholder={false} id={`${idCampo}-3`} value={form.risk_level} onChange={set('risk_level')}>
            {RISK_LEVELS.map(o => <option key={o.value} value={o.value}>{t(o.label)}</option>)}
          </Select>
          {err('risk_level') && <div className="u-field-error">{err('risk_level')}</div>}
        </div>
        <div>
          <ClientSelect label={t('proyectos_ui.cliente')}
            id={`${idCampo}-cliente`}
            value={form.client_id}
            onChange={(id, client) => { campos.limpiar('client_id'); setForm(f => ({ ...f, client_id: id, client_name: client ? client.name : '' })) }}
            placeholder={traducir('projects.selecciona_un_cliente')}
          />
          {err('client_id') && <div className="u-field-error">{err('client_id')}</div>}
        </div>
        <div>
          <Select label={t('proyectos_ui.departamento')} placeholder={false} id={`${idCampo}-4`} value={form.department} onChange={set('department')}>
            <option value="">{traducir('projects.no_department')}</option>
            {departments.map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
          </Select>
          {err('department') && <div className="u-field-error">{err('department')}</div>}
        </div>
        <div>
          <Select label={traducir('projects.label_billing')} placeholder={false} id={`${idCampo}-5`} value={form.billing_type} onChange={set('billing_type')}>
            <option value="">{traducir('projects.no_billing')}</option>
            {(BILLING_TYPES as { value: string; label: string }[]).map(o => <option key={o.value} value={o.value}>{etiquetaCodigo(traducir, 'billing_type', o.value, o.label)}</option>)}
          </Select>
          {err('billing_type') && <div className="u-field-error">{err('billing_type')}</div>}
        </div>
        <div>
          <Input label={t('proyectos_ui.presupuesto_moneda', { moneda: fmtMoneda.simbolo })} id={`${idCampo}-presupuesto`} type="number" value={form.budget_amount} onChange={set('budget_amount')} placeholder={t('proyectos_ui.presupuesto_total')} aria-label={t('proyectos_ui.presupuesto_total')} />
          {err('budget_amount') && <div className="u-field-error">{err('budget_amount')}</div>}
        </div>
        <div>
          <Input label={t('proyectos_ui.contrato_moneda', { moneda: fmtMoneda.simbolo })} id={`${idCampo}-contrato`} type="number" min="0" step="0.01" value={form.contract_amount} onChange={set('contract_amount')} placeholder={t('proyectos_ui.contrato_ayuda')} aria-label={t('proyectos_ui.contrato_ayuda')} />
          {err('contract_amount') && <div className="u-field-error">{err('contract_amount')}</div>}
        </div>
        {form.billing_type === 'recurring_retainer' && (
          <>
            <div>
              <Input label={t('proyectos_ui.retainer_moneda', { moneda: fmtMoneda.simbolo })} id={`${idCampo}-retainer`} type="number" value={form.retainer_amount} onChange={set('retainer_amount')} placeholder={t('proyectos_ui.importe_mensual')} aria-label={t('proyectos_ui.importe_mensual')} />
          {err('retainer_amount') && <div className="u-field-error">{err('retainer_amount')}</div>}
            </div>
            <div>
              <Input label={traducir('projects.label_retainer_day')} type="number" min="1" max="28" value={form.retainer_day} onChange={set('retainer_day')} placeholder={traducir('projects.dia_de_corte')} aria-label={traducir('projects.dia_de_corte')} />
              {err('retainer_day') && <div className="u-field-error">{err('retainer_day')}</div>}
            </div>
          </>
        )}
        <div>
          <DateInput label={t('proyectos_ui.fecha_inicio')} id={`${idCampo}-6`} value={form.start_date} onChange={set('start_date')} />
          {err('start_date') && <div className="u-field-error">{err('start_date')}</div>}
        </div>
        <div>
          <DateInput label={t('proyectos_ui.fecha_fin_planificada')} id={`${idCampo}-7`} value={form.end_date_planned} onChange={set('end_date_planned')} />
          {err('end_date_planned') && <div className="u-field-error">{err('end_date_planned')}</div>}
        </div>
        <div className="u-col-full">
          <Textarea label={traducir('projects.label_description')} value={form.description} onChange={set('description')} rows={3} placeholder={traducir('projects.descripcion_del_proyecto')} aria-label={traducir('projects.descripcion_del_proyecto')} />
          {err('description') && <div className="u-field-error">{err('description')}</div>}
        </div>
        {/* Revisión 2026-11: antes de crear, lo que aprendimos en proyectos parecidos. */}
        {!isEdit && (form.client_id || form.project_type) && (
          <div className="u-col-full">
            <LeccionesQueAplican contexto="nuevo_proyecto" campos={{ cliente_id: form.client_id || null, tipo_proyecto: form.project_type || null, nombre: form.name, descripcion: form.description }} />
          </div>
        )}
        <div className="prj-row-3">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => { if (validateForm()) mutate(form) }} disabled={isPending || !form.name || !form.project_type} loading={isPending}>
            {isPending ? t('common.saving') : isEdit ? t('projects.btn_save') : t('projects.btn_create')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
