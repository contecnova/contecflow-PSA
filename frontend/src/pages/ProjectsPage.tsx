import { useState, useEffect, useMemo, useId } from 'react'
import LeccionesQueAplican from '../components/lecciones/LeccionesQueAplican'
import type { CSSProperties, ComponentProps } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, usersApi, portalApi, templatesApi, taskDependenciesApi, tasksApi } from '../services/api'
import type { PlantillaDeProyecto } from '../services/api/tipos-proyectos'
import type { MemberAddPayload, ProjectCreatePayload, ProjectStatus } from '../services/api'
import { settingsApi } from '../services/settingsApi'
import { Badge, LoadBar, Button, Modal, Spinner, EmptyState, ClientSelect, useSort, SortableTH, MarcaExterno, etiquetaDePersona, Pulsable, Select, useErroresDeCampo, Input, Textarea } from '../components/ui'
import ProjectRiskBadge from '../components/ui/ProjectRiskBadge'
import { SkeletonProjects } from '../components/ui/Skeletons'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
// 16-11-2026 (pasada de diseño): fuera los emojis que quedaban (estado del
// desplegable, vacíos de miembros/fases/solicitudes/Gantt, iconos de plantilla,
// estimaciones de solicitudes, botón «Editar proyecto»); vacíos con EmptyState.
import {
  FolderOpen, Plus, Search, LayoutGrid, List, Calendar, FileStack,
  Pencil, ArrowRight, ClipboardList, ChevronDown, Users, Lightbulb, Coins, Clock,
  CalendarDays, MessageSquare, Building2, Code2, Wrench, FlaskConical, Home, Layers,
  GanttChartSquare, X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import GanttChart from '../components/GanttChart'
import DocumentsPanel from '../components/DocumentsPanel'
import { fmtDate, fmtCurrency, extractErr} from '../utils/helpers'
import { EtiquetaDeCatalogo, OpcionesDeCatalogo } from '../components/catalogos/Catalogo'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { BILLING_TYPES } from '../constants/api'
import { useAuth } from '../context/AuthContext'
import { useColVisibility } from '../components/ui/ColVisibility'
import { useAppT } from '../i18n/AppLangContext'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'
import { getFirstIssueByField } from '../utils/formValidation'
import { alpha } from '../constants/theme'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { useTono } from '../hooks/useOrgSettings'
import './ProjectsPage.css'
const PROJ_COLS = [
  { id: 'name',     label: 'proyectos_ui.col_proyecto',     width: '2fr',   sortKey: 'name' },
  { id: 'type',     label: 'proyectos_ui.col_tipo',     width: '1fr',   sortKey: 'project_type' },
  { id: 'pm',       label: 'proyectos_ui.col_pm',     width: '1fr',   sortKey: 'pm_name' },
  { id: 'status',   label: 'proyectos_ui.col_estado',     width: '140px', sortKey: 'status' },
  { id: 'budget',   label: 'proyectos_ui.col_presupuesto',  width: '100px', sortKey: 'budget_used_pct' },
  { id: 'progress', label: 'proyectos_ui.col_progreso',     width: '80px',  sortKey: 'progress_pct' },
  { id: 'risk',     label: 'proyectos_ui.col_riesgo',     width: '80px',  sortKey: 'risk_level' },
]

type Traductor = ReturnType<typeof useAppT>
/** Cambio de un campo de texto, select, textarea o DateInput. */
type CambioDeCampo = { target: { value: string } }

/** `ProjectSummary` (app/schemas/projects.py): una fila del listado. `task_count` lo lee la tarjeta aunque el esquema no lo declara. */
type ProjectSummary = {
  id: string
  code: string
  name: string
  status: string
  project_type?: string
  risk_level?: string
  pm_name?: string | null
  client_name?: string | null
  department?: string | null
  budget_amount?: number | null
  total_cost_spent?: number | null
  budget_used_pct?: number | null
  progress_pct?: number | null
  team_size?: number
  task_count?: number
  start_date?: string | null
  end_date_planned?: string | null
}
type ProjectPhase = { id: string; name: string; start_date?: string | null; end_date?: string | null; status?: string }
/** `ProjectOut` (app/schemas/projects.py): el detalle. No trae las tareas: el Gantt por proyecto
 *  las pide aparte a `GET /tasks?project_id=`. */
type ProjectDetail = ProjectSummary & {
  description?: string | null
  client_id?: string | null
  billing_type?: string | null
  retainer_amount?: number | null
  retainer_day?: number | null
  project_manager?: { full_name: string } | null
  phases?: ProjectPhase[]
  tasks_total?: number
  tasks_done?: number
}
type ProjectForm = {
  name: string
  project_type: string
  status: string
  client_name: string
  department: string
  budget_amount: string | number
  description: string
  risk_level: string
  start_date: string
  end_date_planned: string
  client_id: string
  billing_type: string
  retainer_amount: string | number
  retainer_day: string | number
}
/** Al subcontratado le llegan sin correo ni dedicación (`politica_de_visibilidad`, segunda auditoría 2026-11). */
type ProjectMember = { id: string; user_id: string; full_name: string; email?: string; role: string; allocation_pct?: number; avatar_initials?: string; external_company?: string | null }
/** Solicitud de mejora del portal (`/portal/feature-requests/team`). */
type FeatureRequest = {
  id: string
  code?: string
  title: string
  description?: string | null
  business_justification?: string | null
  client_approved?: boolean
  priority?: string
  status: string
  pm_response?: string | null
  estimated_hours?: number | null
  estimated_cost?: number | null
  estimated_delivery_weeks?: number | null
  submitted_at?: string | null
}
type RespondForm = { pm_response: string; estimated_hours: string | number; estimated_cost: string | number; estimated_delivery_weeks: string | number; status: string }
type RespondBody = { pm_response?: string; estimated_hours?: number; estimated_cost?: number; estimated_delivery_weeks?: number; status: string }
// Alta de plantilla (TemplateCreate): las fases y tareas son dicts; el servicio lee
// `estimated_weeks` de cada fase y `estimated_hours` de cada tarea (billing_reports_service/plantillas.py).
type NewTemplatePhase = { name: string; estimated_weeks: number; tasks: Array<{ title: string; estimated_hours: number }> }
type NewTemplate = { name: string; description: string; project_type: string; estimated_weeks: number; estimated_hours?: number; phases: NewTemplatePhase[] }
type InstantiateForm = { name: string; client_id: string; client_name: string; start_date: string; budget_amount: string; pm_id?: string }
type GanttTasks = ComponentProps<typeof GanttChart>['tasks']

// ── Estilos compartidos ───────────────────────────────────────────────────────


const PROJECT_STATUSES = [
  { value: 'planning',  label: 'proyectos_ui.estado_planning' },
  { value: 'active',    label: 'proyectos_ui.estado_active' },
  { value: 'on_hold',   label: 'proyectos_ui.estado_on_hold' },
  { value: 'paused',    label: 'proyectos_ui.estado_paused' },
  { value: 'completed', label: 'proyectos_ui.estado_completed' },
  { value: 'closed',    label: 'proyectos_ui.estado_closed' },
  { value: 'cancelled', label: 'proyectos_ui.estado_cancelled' },
  { value: 'archived',  label: 'proyectos_ui.estado_archived' },
]
// 19-11-2026: los tipos de proyecto salen del catálogo de la empresa (`/settings/project-types`).
const RISK_LEVELS = [
  { value: 'low', label: 'proyectos_ui.riesgo_low' },
  { value: 'medium', label: 'proyectos_ui.riesgo_medium' },
  { value: 'high', label: 'proyectos_ui.riesgo_high' },
  { value: 'critical', label: 'proyectos_ui.riesgo_critical' },
]

function makeProjectFormSchema(t: Traductor) {
  return z.object({
    name: z.string().min(1, t('projects.error_name_required')),
    project_type: z.string().min(1, t('projects.error_type_required')),
    start_date: z.string().optional(),
    end_date_planned: z.string().optional(),
    budget_amount: z.union([z.string(), z.number(), z.null()]).optional(),
    retainer_amount: z.union([z.string(), z.number(), z.null()]).optional(),
    retainer_day: z.union([z.string(), z.number(), z.null()]).optional(),
    billing_type: z.string().optional(),
  }).superRefine((data, ctx) => {
    if (data.start_date && data.end_date_planned && data.end_date_planned < data.start_date) {
      ctx.addIssue({ code: 'custom', path: ['end_date_planned'], message: t('projects.error_date_range') })
    }
    const budget = Number(data.budget_amount || 0)
    if (!Number.isNaN(budget) && budget < 0) {
      ctx.addIssue({ code: 'custom', path: ['budget_amount'], message: t('projects.error_budget_negative') })
    }
    const retainerDay = Number(data.retainer_day || 0)
    if (data.billing_type === 'recurring_retainer' && (retainerDay < 1 || retainerDay > 28)) {
      ctx.addIssue({ code: 'custom', path: ['retainer_day'], message: t('projects.error_retainer_day') })
    }
  })
}

function makeProjectMemberSchema(t: Traductor) {
  return z.object({
    user_id: z.string().trim().min(1, t('projects.error_person_required')),
    role: z.string().trim().min(1, t('projects.error_role_required')),
    allocation_pct: z.coerce.number()
      .min(1, t('projects.error_allocation'))
      .max(100, t('projects.error_allocation')),
    notes: z.string().optional(),
  })
}

function StatusDropdown({ project, onUpdate }: { project: Pick<ProjectSummary, 'status'>; onUpdate: (s: string) => void }) {
  const traducir = useAppT()
  const [open, setOpen] = useState(false)
  const cfg: Record<string, { color: string }> = {
    planning:  { color: 'var(--text-2)' },
    active:    { color: 'var(--accent)' },
    paused:    { color: 'var(--warning)' },
    closed:    { color: 'var(--success)' },
    on_hold:   { color: 'var(--warning)' },
    completed: { color: 'var(--success)' },
    cancelled: { color: 'var(--text-3)' },
    archived:  { color: 'var(--text-3)' },
  }
  const c = cfg[project.status] || cfg.planning
  const etiqueta = PROJECT_STATUSES.find(s => s.value === project.status)

  return (
    <div className="prj-box">
      <Pulsable className="prj-btn-xs" aria-haspopup="listbox" aria-expanded={open} aria-label={traducir('proyectos_ui.cambiar_estado')}
        onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        style={{ '--prj-btn-xs-border': `1px solid ${alpha(c.color, '40')}`, '--prj-btn-xs-background': alpha(c.color, '15'), '--prj-btn-xs-color': c.color } as CSSProperties}
      >
        {etiqueta ? traducir(etiqueta.label) : project.status} <ChevronDown size={11} aria-hidden />
      </Pulsable>
      {open && (
        <>
          <div className="prj-box-2" role="presentation" onMouseDown={e => { e.stopPropagation(); setOpen(false) }} />
          <div className="prj-card-2">
            {PROJECT_STATUSES.map(s => (
              <Pulsable className="prj-btn-base" key={s.value} onClick={e => { e.stopPropagation(); onUpdate(s.value); setOpen(false) }}
                style={{ '--prj-btn-base-background': project.status === s.value ? 'var(--accent-muted)' : 'transparent', '--prj-btn-base-color': project.status === s.value ? 'var(--accent)' : 'var(--text-1)' } as CSSProperties}
              >
                {traducir(s.label)}
              </Pulsable>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function ProjectCard({ project, onClick, onStatusChange, onEdit }: { project: ProjectSummary; onClick: (p: ProjectSummary) => void; onStatusChange: (id: string, s: string) => void; onEdit: (p: ProjectSummary) => void }) {
  const traducir = useAppT()
  const tono = useTono()
  return (
    <div className="ds-card prj-tarjeta"
    >
      <div className="prj-row">
        <Pulsable className="prj-btn-ghost" onClick={() => onClick(project)}>
          <div className="ds-muted prj-text-xs-mono">{project.code}</div>
          <div className="prj-box-3">{project.name}</div>
          {project.pm_name && <div className="ds-muted prj-text">{traducir('proyectos_ui.pm_nombre', { nombre: project.pm_name })}</div>}
          {project.department && <div className="ds-muted">{traducir('proyectos_ui.depto_nombre', { nombre: project.department })}</div>}
          {project.client_name && <div className="ds-muted">{traducir('proyectos_ui.cliente_nombre', { nombre: project.client_name })}</div>}
        </Pulsable>
        <div className="prj-stack">
          <StatusDropdown project={project} onUpdate={status => onStatusChange(project.id, status)} />
          <Badge label={project.risk_level} display={undefined} _color={undefined} />
          <ProjectRiskBadge projectId={project.id} hasData={(project.task_count ?? project.team_size ?? 1) > 0} />
        </div>
      </div>

      <Pulsable className="prj-btn-ghost-2" onClick={() => onClick(project)}>
        <div className="prj-row-muted">
          <span><EtiquetaDeCatalogo catalogo="project-types" clave={project.project_type} /></span>
          <span>{traducir('proyectos_ui.pct_completado', { n: project.progress_pct?.toFixed(0) ?? 0 })}</span>
        </div>
        <LoadBar value={project.progress_pct ?? 0} label={undefined} />
      </Pulsable>

      <div className="prj-row-2">
        <Pulsable className="prj-btn-ghost-3" onClick={() => onClick(project)}>
          <span className="ds-muted">{traducir('proyectos_ui.equipo')} <span className="u-text1">{project.team_size}</span></span>
          {project.budget_amount && (
            <span className="prj-text-mono" style={{ '--prj-text-mono-color': tono('presupuesto', project.budget_used_pct) === 'danger' ? 'var(--danger)' : 'var(--text-2)' } as CSSProperties}>
              {traducir('proyectos_ui.pct_presupuesto', { n: project.budget_used_pct?.toFixed(0) ?? 0 })}
            </span>
          )}
        </Pulsable>
        <div className="u-row-6">
          <Link to={`/projects/${project.id}`} onClick={e => e.stopPropagation()} className="prj-enlace-ver">
            {traducir('proyectos_ui.ver')} <ArrowRight size={11} />
          </Link>
          <Pulsable className="prj-btn-ghost-xs" onClick={e => { e.stopPropagation(); onEdit(project) }}>
            <Pencil size={11} /> {traducir('common.edit')}
          </Pulsable>
        </div>
      </div>
    </div>
  )
}

function ProjectFormModal({ open, onClose, project = null }: { open: boolean; onClose: () => void; project?: ProjectSummary | null }) {
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
    client_name: '', department: '', budget_amount: '',
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
          <label className="prj-ls-2" htmlFor={`${idCampo}-nombre`}>{t('proyectos_ui.nombre_req')}</label>
          <Input id={`${idCampo}-nombre`} value={form.name} onChange={set('name')} placeholder={traducir('projects.nombre_del_proyecto')} aria-label={traducir('projects.nombre_del_proyecto')} inputClassName="prj-fs-2" />
          {err('name') && <div className="u-field-error">{err('name')}</div>}
        </div>
        <div>
          <label className="prj-ls-2" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{t('proyectos_ui.tipo_req')}</label>
          <Select suelto placeholder={false} className="prj-fs-2" id={`${idCampo}-1`} value={form.project_type} onChange={set('project_type')}>
            <option value="">{t('proyectos_ui.seleccionar')}</option>
            <OpcionesDeCatalogo catalogo="project-types" />
          </Select>
          {err('project_type') && <div className="u-field-error">{err('project_type')}</div>}
        </div>
        <div>
          <label className="prj-ls-2" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{t('proyectos_ui.col_estado')}</label>
          <Select suelto placeholder={false} className="prj-fs-2" id={`${idCampo}-2`} value={form.status} onChange={set('status')}>
            {PROJECT_STATUSES.map(o => <option key={o.value} value={o.value}>{t(o.label)}</option>)}
          </Select>
          {err('status') && <div className="u-field-error">{err('status')}</div>}
        </div>
        <div>
          <label className="prj-ls-2" id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`}>{t('proyectos_ui.col_riesgo')}</label>
          <Select suelto placeholder={false} className="prj-fs-2" id={`${idCampo}-3`} value={form.risk_level} onChange={set('risk_level')}>
            {RISK_LEVELS.map(o => <option key={o.value} value={o.value}>{t(o.label)}</option>)}
          </Select>
          {err('risk_level') && <div className="u-field-error">{err('risk_level')}</div>}
        </div>
        <div>
          <label className="prj-ls-2" id={`${idCampo}-etcliente`} htmlFor={`${idCampo}-cliente`}>{t('proyectos_ui.cliente')}</label>
          <ClientSelect
            id={`${idCampo}-cliente`}
            aria-labelledby={`${idCampo}-etcliente`}
            value={form.client_id}
            onChange={(id, client) => { campos.limpiar('client_id'); setForm(f => ({ ...f, client_id: id, client_name: client ? client.name : '' })) }}
            placeholder={traducir('projects.selecciona_un_cliente')}
            className="projects-page-e1"
          />
          {err('client_id') && <div className="u-field-error">{err('client_id')}</div>}
        </div>
        <div>
          <label className="prj-ls-2" id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`}>{t('proyectos_ui.departamento')}</label>
          <Select suelto placeholder={false} className="prj-fs-2" id={`${idCampo}-4`} value={form.department} onChange={set('department')}>
            <option value="">{traducir('projects.no_department')}</option>
            {departments.map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
          </Select>
          {err('department') && <div className="u-field-error">{err('department')}</div>}
        </div>
        <div>
          <label className="prj-ls-2" id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`}>{traducir('projects.label_billing')}</label>
          <Select suelto placeholder={false} className="prj-fs-2" id={`${idCampo}-5`} value={form.billing_type} onChange={set('billing_type')}>
            <option value="">{traducir('projects.no_billing')}</option>
            {(BILLING_TYPES as { value: string; label: string }[]).map(o => <option key={o.value} value={o.value}>{etiquetaCodigo(traducir, 'billing_type', o.value, o.label)}</option>)}
          </Select>
          {err('billing_type') && <div className="u-field-error">{err('billing_type')}</div>}
        </div>
        <div>
          <label className="prj-ls-2" htmlFor={`${idCampo}-presupuesto`}>{t('proyectos_ui.presupuesto_moneda', { moneda: fmtMoneda.simbolo })}</label>
          <Input id={`${idCampo}-presupuesto`} type="number" value={form.budget_amount} onChange={set('budget_amount')} placeholder={t('proyectos_ui.presupuesto_total')} aria-label={t('proyectos_ui.presupuesto_total')} inputClassName="prj-fs-2" />
          {err('budget_amount') && <div className="u-field-error">{err('budget_amount')}</div>}
        </div>
        {form.billing_type === 'recurring_retainer' && (
          <>
            <div>
              <label className="prj-ls-2" htmlFor={`${idCampo}-retainer`}>{t('proyectos_ui.retainer_moneda', { moneda: fmtMoneda.simbolo })}</label>
              <Input id={`${idCampo}-retainer`} type="number" value={form.retainer_amount} onChange={set('retainer_amount')} placeholder={t('proyectos_ui.importe_mensual')} aria-label={t('proyectos_ui.importe_mensual')} inputClassName="prj-fs-2" />
          {err('retainer_amount') && <div className="u-field-error">{err('retainer_amount')}</div>}
            </div>
            <div>
              <label className="prj-ls-2">{traducir('projects.label_retainer_day')}</label>
              <Input type="number" min="1" max="28" value={form.retainer_day} onChange={set('retainer_day')} placeholder={traducir('projects.dia_de_corte')} aria-label={traducir('projects.dia_de_corte')} inputClassName="prj-fs-2" />
              {err('retainer_day') && <div className="u-field-error">{err('retainer_day')}</div>}
            </div>
          </>
        )}
        <div>
          <label className="prj-ls-2" id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`}>{t('proyectos_ui.fecha_inicio')}</label>
          <DateInput id={`${idCampo}-6`} value={form.start_date} onChange={set('start_date')} className="prj-fs-2" />
          {err('start_date') && <div className="u-field-error">{err('start_date')}</div>}
        </div>
        <div>
          <label className="prj-ls-2" id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`}>{t('proyectos_ui.fecha_fin_planificada')}</label>
          <DateInput id={`${idCampo}-7`} value={form.end_date_planned} onChange={set('end_date_planned')} className="prj-fs-2" />
          {err('end_date_planned') && <div className="u-field-error">{err('end_date_planned')}</div>}
        </div>
        <div className="u-col-full">
          <label className="prj-ls-2">{traducir('projects.label_description')}</label>
          <Textarea value={form.description} onChange={set('description')} rows={3} placeholder={traducir('projects.descripcion_del_proyecto')} aria-label={traducir('projects.descripcion_del_proyecto')} inputClassName="prj-fs-2 prj-input" />
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

const MEMBER_ROLES: Record<string, string> = {
  lead: 'proyectos_ui.rol_lead', developer: 'proyectos_ui.rol_developer', designer: 'proyectos_ui.rol_designer',
  qa: 'proyectos_ui.rol_qa', analyst: 'proyectos_ui.rol_analyst', devops: 'proyectos_ui.rol_devops',
  stakeholder: 'proyectos_ui.rol_stakeholder', other: 'proyectos_ui.rol_other',
}

function ProjectDetailModal({ project, detail, open, onClose, onEdit }: { project: ProjectSummary | null; detail: ProjectDetail | undefined; open: boolean; onClose: () => void; onEdit: (p: ProjectSummary) => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('info')
  const [addForm, setAddForm] = useState({ user_id: '', role: 'developer', allocation_pct: 100, notes: '' })
  const projectMemberSchema = useMemo(() => makeProjectMemberSchema(t), [t])
  const addValidation = useFormValidation(projectMemberSchema)
  const [showAdd, setShowAdd] = useState(false)

  const { data: members = [], isLoading: loadingMembers } = useQuery({
    queryKey: ['project-members', project?.id],
    queryFn: () => projectsApi.members(project.id).then(r => r.data as ProjectMember[]),
    enabled: !!project?.id && tab === 'team',
  })
  // Selector de personas: `/users/directory` (ficha mínima) sirve a cualquier rol; `/users` da 403 al subcontratado.
  const { data: allUsers = [] } = useQuery({
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
    enabled: !!project?.id && tab === 'team',
  })

  // ── Feature Requests (tab 'requests') ─────────────────────────
  const [respondingFr, setRespondingFr] = useState<string | null>(null)
  const [respondForm, setRespondForm] = useState<RespondForm>({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' })

  const { data: featureRequests = [], isLoading: loadingFRs } = useQuery({
    queryKey: ['project-feature-requests', project?.id],
    queryFn: () => portalApi.featureRequests({ project_id: project.id }).then((r): FeatureRequest[] => r.data),
    enabled: !!project?.id && tab === 'requests',
  })

  const { mutate: respondFR, isPending: respondingFRPending } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: RespondBody }) => portalApi.respondFeatureRequest(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-feature-requests', project?.id] }); setRespondingFr(null); setRespondForm({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' }) },
    onError: e => toast.error(extractErr(e, traducir('proyectos_ui.error_responder'))),
  })

  const { mutate: addMember, isPending: adding } = useMutation({
    // Sin strictNullChecks, zod marca opcionales todas las claves del tipo inferido;
    // `user_id` y `role` ya los ha exigido el esquema al validar.
    mutationFn: (d: z.infer<ReturnType<typeof makeProjectMemberSchema>>) => projectsApi.addMember(project.id, d as MemberAddPayload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-members', project.id] }); qc.invalidateQueries({ queryKey: ['capacity-board'] }); qc.invalidateQueries({ queryKey: ['forecast-heatmap'] }); qc.invalidateQueries({ queryKey: ['forecast-summary'] }); setShowAdd(false); setAddForm({ user_id: '', role: 'developer', allocation_pct: 100, notes: '' }); addValidation.setErrors({}) },
    onError: e => toast.error(extractErr(e, traducir('proyectos_ui.error_anadir_miembro'))),
  })
  const { mutate: removeMember } = useMutation({
    mutationFn: (memberId: string) => projectsApi.removeMember(project.id, memberId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-members', project.id] }); qc.invalidateQueries({ queryKey: ['capacity-board'] }); qc.invalidateQueries({ queryKey: ['forecast-heatmap'] }); qc.invalidateQueries({ queryKey: ['forecast-summary'] }); },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (!project || !detail) return null

  const TABS = [
    { id: 'info',     label: traducir('proyectos_ui.tab_info') },
    { id: 'team',     label: members.length > 0 ? traducir('proyectos_ui.tab_equipo_n', { n: members.length }) : traducir('proyectos_ui.tab_equipo') },
    { id: 'phases',   label: traducir('proyectos_ui.tab_fases') },
    { id: 'docs',     label: traducir('proyectos_ui.tab_documentos') },
    { id: 'requests', label: featureRequests.length > 0 ? traducir('proyectos_ui.tab_solicitudes_n', { n: featureRequests.length }) : traducir('proyectos_ui.tab_solicitudes') },
  ]

  const memberUserIds = new Set(members.map(m => m.user_id))
  const availableUsers = allUsers.filter(u => !memberUserIds.has(u.id))

  const setAddField = (key: keyof typeof addForm) => (e: CambioDeCampo) => {
    const value = key === 'allocation_pct' ? Number(e.target.value) : e.target.value
    setAddForm(current => ({ ...current, [key]: value }))
    addValidation.clearFieldError(key)
  }

  const submitAddMember = () => {
    const result = addValidation.validateForm(addForm)
    if (!result.success) {
      return
    }
    addMember(result.data)
  }

  return (
    <Modal open={open} onClose={onClose} title={detail.name} width={720}>
      {/* Badges */}
      <div className="prj-row-4">
        <Badge label={detail.status} display={undefined} _color={undefined} /><Badge label={detail.risk_level} display={undefined} _color={undefined} /><Badge label={detail.project_type} display={undefined} _color={undefined} />
      </div>

      {/* Tab bar */}
      <div className="prj-row-5">
        {TABS.map(t => (
          <Pulsable className="prj-btn-xs-2" aria-pressed={tab === t.id} key={t.id} onClick={() => setTab(t.id)}
            style={{ '--prj-btn-xs-2-border': `1px solid ${tab === t.id ? 'var(--accent)' : 'var(--surface-4)'}`, '--prj-btn-xs-2-background': tab === t.id ? 'var(--accent-muted)' : 'transparent', '--prj-btn-xs-2-color': tab === t.id ? 'var(--accent)' : 'var(--text-2)' } as CSSProperties}>
            {t.label}
          </Pulsable>
        ))}
      </div>

      {/* INFO TAB */}
      {tab === 'info' && (
        <>
          {detail.description && <p className="prj-text-muted-md">{detail.description}</p>}
          <div className="prj-grid">
            {[
              { label: traducir('proyectos_ui.codigo'),        value: detail.code },
              { label: traducir('proyectos_ui.col_pm'),            value: detail.project_manager?.full_name || '—' },
              { label: traducir('proyectos_ui.cliente'),       value: detail.client_name || '—' },
              { label: traducir('proyectos_ui.departamento'),  value: detail.department || '—' },
              { label: traducir('proyectos_ui.inicio'),        value: fmtDate(detail.start_date) },
              { label: traducir('proyectos_ui.fin_planificado'),   value: fmtDate(detail.end_date_planned) },
              { label: traducir('proyectos_ui.col_progreso'),      value: `${detail.progress_pct?.toFixed(0) ?? 0}%` },
              { label: traducir('proyectos_ui.tareas'),        value: detail.tasks_total > 0 ? traducir('proyectos_ui.tareas_completadas', { hechas: detail.tasks_done ?? 0, total: detail.tasks_total }) : '—' },
              { label: traducir('proyectos_ui.tab_equipo'),        value: (detail.team_size ?? 0) === 1 ? traducir('proyectos_ui.una_persona') : traducir('proyectos_ui.n_personas', { n: detail.team_size ?? 0 }) },
              { label: traducir('proyectos_ui.col_presupuesto'),   value: detail.budget_amount ? fmtCurrency(detail.budget_amount) : '—' },
              { label: traducir('proyectos_ui.gastado'),       value: detail.total_cost_spent ? fmtCurrency(detail.total_cost_spent) : '—' },
            ].map(({ label, value }) => (
              <div className="prj-card-3" key={label}>
                <div className="prj-text-muted-xs">{label}</div>
                <div className="u-md-600">{value}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* TEAM TAB */}
      {tab === 'team' && (
        <div>
          <div className="u-row-between-mb16">
            <p className="prj-text-muted-base">
              {traducir('projects.personas_asignadas_explicitamente_a_este_proyecto')}
            </p>
            <Button variant={showAdd ? 'secondary' : 'primary'} icon={showAdd ? <X size={14} /> : <Plus size={14} />} onClick={() => setShowAdd(s => !s)}>
              {showAdd ? traducir('proyectos_ui.cancelar_x') : traducir('proyectos_ui.anadir_miembro')}
            </Button>
          </div>

          {/* Formulario añadir */}
          {showAdd && (
            <div className="prj-card-4">
              <div className="prj-grid-2">
                <div>
                  <label className="prj-label-muted-xs" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{traducir('proyectos_ui.persona_req')}</label>
                  <Select suelto placeholder={false} id={`${idCampo}-1`} value={addForm.user_id} onChange={setAddField('user_id')}
                    className={addValidation.inputClass('projects-page-campo', 'user_id')}>
                    <option value="">{traducir('proyectos_ui.seleccionar_persona')}</option>
                    {availableUsers.map(u => <option key={u.id} value={u.id}>{etiquetaDePersona(traducir, u)}{u.job_title ? ` (${u.job_title})` : ''}</option>)}
                  </Select>
                  {addValidation.errors.user_id && <div className="u-field-error">{addValidation.errors.user_id}</div>}
                </div>
                <div>
                  <label className="prj-label-muted-xs" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{traducir('proyectos_ui.rol')}</label>
                  <Select suelto placeholder={false} className="prj-input-2" id={`${idCampo}-2`} value={addForm.role} onChange={setAddField('role')}>
                    {Object.entries(MEMBER_ROLES).map(([k, v]) => <option key={k} value={k}>{traducir(v)}</option>)}
                  </Select>
                </div>
                <div>
                  <label className="prj-label-muted-xs" id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`}>{traducir('proyectos_ui.dedicacion')}</label>
                  <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" min="1" max="100" value={addForm.allocation_pct}
                    onChange={setAddField('allocation_pct')}
                    className={addValidation.inputClass('projects-page-campo', 'allocation_pct')} />
                  {addValidation.errors.allocation_pct && <div className="u-field-error">{addValidation.errors.allocation_pct}</div>}
                </div>
              </div>
              <div className="u-row-end">
                <Button
                  onClick={submitAddMember}
                  disabled={adding}
                >
                  {adding ? traducir('proyectos_ui.anadiendo') : traducir('proyectos_ui.confirmar_asignacion')}
                </Button>
              </div>
            </div>
          )}

          {/* Lista de miembros */}
          {loadingMembers ? <Spinner /> : members.length === 0 ? (
            <EmptyState icon={<Users size={28} />} title={traducir('projects.todavia_no_hay_miembros_asignados')}
              description={traducir('projects.usa_el_boton_anadir_miembro_para_asignar')} />
          ) : (
            <div className="u-stack-8">
              {members.map(m => (
                <div className="prj-row-6" key={m.id}>
                  <div className="prj-row-accent">
                    {m.avatar_initials}
                  </div>
                  <div className="u-flex1">
                    {/* `role` aquí es el papel en el proyecto: la marca sale de `external_company`. */}
                    <div className="u-md-600">{m.full_name} <MarcaExterno persona={{ external_company: m.external_company }} /></div>
                    {m.email && <div className="u-text2-sm">{m.email}</div>}
                  </div>
                  <span className="prj-card-accent">
                    {MEMBER_ROLES[m.role] ? traducir(MEMBER_ROLES[m.role]) : m.role}
                  </span>
                  {typeof m.allocation_pct === 'number' && (
                  <span className="prj-box-4" style={{ '--prj-box-4-color': m.allocation_pct >= 100 ? 'var(--success)' : m.allocation_pct >= 50 ? 'var(--warning)' : 'var(--text-2)' } as CSSProperties}>
                    {m.allocation_pct}%
                  </span>
                  )}
                  <Pulsable className="prj-btn-danger-lg" aria-label={traducir('proyectos_ui.quitar_miembro')} title={traducir('proyectos_ui.quitar_miembro')} onClick={() => { openConfirmGlobal({ message: traducir('proyectos_ui.quitar_miembro_confirm', { nombre: m.full_name }), onConfirm: () => removeMember(m.id), danger: true }) }}>×</Pulsable>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* PHASES TAB */}
      {tab === 'phases' && (
        detail.phases?.length > 0 ? (
          <div>
            {detail.phases.map(ph => (
              <div className="prj-row-7" key={ph.id}>
                <div>
                  <div className="u-600">{ph.name}</div>
                  {(ph.start_date || ph.end_date) && (
                    <div className="u-text2-xs-mt2">
                      {fmtDate(ph.start_date)} → {fmtDate(ph.end_date)}
                    </div>
                  )}
                </div>
                <Badge label={ph.status} display={undefined} _color={undefined} />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={<Layers size={28} />} title={traducir('projects.no_phases')} />
        )
      )}

      {/* DOCS TAB */}
      {tab === 'docs' && (
        <DocumentsPanel projectId={project.id} taskId={undefined} ticketId={undefined} />
      )}

      {/* FEATURE REQUESTS TAB */}
      {tab === 'requests' && (
        <div>
          {loadingFRs ? <Spinner /> : featureRequests.length === 0 ? (
            <EmptyState icon={<Lightbulb size={28} />} title={traducir('projects.no_hay_solicitudes_de_funcionalidad_para_este')}
              description={traducir('projects.los_clientes_pueden_crear_solicitudes_desde_el')} />
          ) : (
            <div className="u-stack-10">
              {featureRequests.map(fr => {
                const statusColors: Record<string, string> = { new: 'var(--accent)', reviewing: 'var(--warning)', estimated: 'var(--orange)', approved: 'var(--success)', rejected: 'var(--danger)', in_development: 'var(--purple)', done: 'var(--success)' }
                const priorityColors: Record<string, string> = { low: 'var(--text-2)', medium: 'var(--accent)', high: 'var(--warning)', critical: 'var(--danger)' }
                const statusLabels: Record<string, string> = { new: traducir('proyectos_ui.sol_new'), reviewing: traducir('proyectos_ui.sol_reviewing'), estimated: traducir('proyectos_ui.sol_estimated'), approved: traducir('proyectos_ui.sol_approved'), rejected: traducir('proyectos_ui.sol_rejected'), in_development: traducir('proyectos_ui.sol_in_development'), done: traducir('proyectos_ui.sol_done') }
                const isResponding = respondingFr === fr.id
                const canRespond = ['new', 'reviewing', 'estimated'].includes(fr.status)
                return (
                  <div className="prj-card-5" key={fr.id} style={{ '--prj-card-5-border': `1px solid ${isResponding ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                    <div className="prj-row-8">
                      <div className="u-flex1-min0">
                        <div className="prj-row-9">
                          <span className="prj-text-muted-xs-strong-mono">{fr.code}</span>
                          <span className="prj-box-5" style={{ '--prj-box-5-border': `1px solid ${alpha(statusColors[fr.status] || 'var(--text-2)', '40')}`, '--prj-box-5-color': statusColors[fr.status] || 'var(--text-2)', '--prj-box-5-background': alpha(statusColors[fr.status] || 'var(--text-2)', '18') } as CSSProperties}>{statusLabels[fr.status] || fr.status}</span>
                          <span className="prj-text-xs prj-text-3" style={{ '--prj-text-3-color': priorityColors[fr.priority] || 'var(--text-2)' } as CSSProperties}>● {fr.priority}</span>
                          {fr.client_approved === true && <span className="prj-text-success-xs">{traducir('projects.cliente_aprobo')}</span>}
                          {fr.client_approved === false && <span className="prj-text-danger-xs">{traducir('projects.cliente_rechazo')}</span>}
                        </div>
                        <div className="prj-text-md-2">{fr.title}</div>
                        <div className="prj-text-muted-sm-2">{fr.description}</div>
                        {fr.business_justification && <div className="prj-text-muted-sm-3">{traducir('projects.justificacion')} {fr.business_justification}</div>}
                        {(fr.estimated_cost != null || fr.estimated_hours != null) && (
                          <div className="prj-row-10">
                            {fr.estimated_cost != null && <span className="u-text2-sm prj-dato-icono"><Coins size={12} aria-hidden /> {fmtCurrency(fr.estimated_cost)}</span>}
                            {fr.estimated_hours != null && <span className="u-text2-sm prj-dato-icono"><Clock size={12} aria-hidden /> {fr.estimated_hours}h</span>}
                            {fr.estimated_delivery_weeks != null && <span className="u-text2-sm prj-dato-icono"><CalendarDays size={12} aria-hidden /> {traducir('proyectos_ui.n_semanas_abrev', { n: fr.estimated_delivery_weeks })}</span>}
                          </div>
                        )}
                        {fr.pm_response && <div className="prj-card-muted prj-dato-icono"><MessageSquare size={12} aria-hidden /> {fr.pm_response}</div>}
                      </div>
                      <div className="prj-stack-2">
                        {canRespond && (
                          <Pulsable className="prj-btn-xs-3" onClick={() => { setRespondingFr(isResponding ? null : fr.id); if (!isResponding) setRespondForm({ pm_response: fr.pm_response || '', estimated_hours: fr.estimated_hours ?? '', estimated_cost: fr.estimated_cost ?? '', estimated_delivery_weeks: fr.estimated_delivery_weeks ?? '', status: fr.status === 'new' ? 'estimated' : fr.status }) }}
                            style={{ '--prj-btn-xs-3-border': `1px solid ${isResponding ? 'var(--accent)' : 'var(--surface-4)'}`, '--prj-btn-xs-3-background': isResponding ? 'var(--accent-muted)' : 'transparent', '--prj-btn-xs-3-color': isResponding ? 'var(--accent)' : 'var(--text-2)' } as CSSProperties}>
                            {isResponding ? traducir('proyectos_ui.cancelar_x') : traducir('proyectos_ui.responder')}
                          </Pulsable>
                        )}
                        <div className="prj-text-muted-xs-2">{fmtDate(fr.submitted_at)}</div>
                      </div>
                    </div>

                    {/* Formulario de respuesta PM */}
                    {isResponding && (
                      <div className="prj-box-6">
                        <div className="prj-text-muted-sm-strong">{traducir('projects.respuesta_del_pm')}</div>
                        <div className="prj-grid-3">
                          <div>
                            <label className="prj-ls" id={`${idCampo}-${fr.id}-etresp828`} htmlFor={`${idCampo}-${fr.id}-resp828`}>{traducir('proyectos_ui.coste_estimado_moneda', { moneda: fmtMoneda.simbolo })}</label>
                            <Input id={`${idCampo}-${fr.id}-resp828`} aria-labelledby={`${idCampo}-${fr.id}-etresp828`} type="number" min="0" value={respondForm.estimated_cost} onChange={e => setRespondForm(f => ({ ...f, estimated_cost: e.target.value }))} placeholder="0" inputClassName="prj-fs" />
                          </div>
                          <div>
                            <label className="prj-ls" id={`${idCampo}-${fr.id}-etresp832`} htmlFor={`${idCampo}-${fr.id}-resp832`}>{traducir('proyectos_ui.horas_estimadas')}</label>
                            <Input id={`${idCampo}-${fr.id}-resp832`} aria-labelledby={`${idCampo}-${fr.id}-etresp832`} type="number" min="0" value={respondForm.estimated_hours} onChange={e => setRespondForm(f => ({ ...f, estimated_hours: e.target.value }))} placeholder="0" inputClassName="prj-fs" />
                          </div>
                          <div>
                            <label className="prj-ls" id={`${idCampo}-${fr.id}-etresp836`} htmlFor={`${idCampo}-${fr.id}-resp836`}>{traducir('proyectos_ui.semanas_entrega')}</label>
                            <Input id={`${idCampo}-${fr.id}-resp836`} aria-labelledby={`${idCampo}-${fr.id}-etresp836`} type="number" min="0" max="104" value={respondForm.estimated_delivery_weeks} onChange={e => setRespondForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} placeholder="0" inputClassName="prj-fs" />
                          </div>
                        </div>
                        <div className="u-mb-10">
                          <label className="prj-ls" id={`${idCampo}-${fr.id}-etresp841`} htmlFor={`${idCampo}-${fr.id}-resp841`}>{traducir('projects.mensaje_al_cliente')}</label>
                          <Textarea id={`${idCampo}-${fr.id}-resp841`} aria-labelledby={`${idCampo}-${fr.id}-etresp841`} rows={3} value={respondForm.pm_response} onChange={e => setRespondForm(f => ({ ...f, pm_response: e.target.value }))} placeholder={traducir('projects.explica_la_estimacion_o_razon_del_rechazo')} inputClassName="prj-fs prj-input" />
                        </div>
                        <div className="u-row-center-10">
                          <label className="prj-label-muted-xs-2" id={`${idCampo}-${fr.id}-etresp845`} htmlFor={`${idCampo}-${fr.id}-resp845`}>{traducir('proyectos_ui.col_estado')}</label>
                          <Select suelto placeholder={false} className="prj-fs prj-input-3" id={`${idCampo}-${fr.id}-resp845`} value={respondForm.status} onChange={e => setRespondForm(f => ({ ...f, status: e.target.value }))}>
                            <option value="estimated">{traducir('proyectos_ui.sol_estimated')}</option>
                            <option value="rejected">{traducir('proyectos_ui.rechazar')}</option>
                            <option value="in_development">{traducir('proyectos_ui.sol_in_development')}</option>
                            <option value="done">{traducir('proyectos_ui.sol_done')}</option>
                          </Select>
                          <div className="u-flex1" />
                          <Button onClick={() => respondFR({ id: fr.id, data: { pm_response: respondForm.pm_response || undefined, estimated_hours: respondForm.estimated_hours !== '' ? Number(respondForm.estimated_hours) : undefined, estimated_cost: respondForm.estimated_cost !== '' ? Number(respondForm.estimated_cost) : undefined, estimated_delivery_weeks: respondForm.estimated_delivery_weeks !== '' ? Number(respondForm.estimated_delivery_weeks) : undefined, status: respondForm.status } })} disabled={respondingFRPending}>
                            {respondingFRPending ? traducir('proyectos_ui.guardando') : traducir('proyectos_ui.guardar_respuesta')}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      <div className="prj-row-11">
        <Button variant="secondary" onClick={onClose}>{traducir('common.close')}</Button>
        <Button onClick={() => { onClose(); onEdit(detail) }} icon={<Pencil size={14} />}>{traducir('proyectos_ui.editar_proyecto')}</Button>
      </div>
    </Modal>
  )
}

// ── Templates Tab ─────────────────────────────────────────────────────────────
 
 
function TemplatesTab() {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [instantiating, setInstantiating] = useState<PlantillaDeProyecto | null>(null)
  const [instForm, setInstForm] = useState<InstantiateForm>({ name:'', client_id:'', client_name:'', start_date: new Date().toISOString().slice(0,10), budget_amount:'' })

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['project-templates'],
    queryFn: () => templatesApi.list().then(r => r.data),
  })
  const { data: users = [] } = useQuery({ queryKey: ['users', 'directory'], queryFn: () => usersApi.directory().then(r => r.data) })
  const pms = users.filter(u => ['admin','pm'].includes(u.role))

  const { mutate: instantiate, isPending: creating } = useMutation({
    mutationFn: ({ tplId, data }: { tplId: string; data: Omit<InstantiateForm, 'budget_amount'> & { budget_amount?: number } }) => templatesApi.instantiate(tplId, data).then(r => r.data),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast.success(traducir('proyectos_ui.proyecto_creado', { codigo: data.project_code, nombre: data.project_name, fases: data.phases_created, tareas: data.tasks_created }))
      setInstantiating(null)
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [newTpl, setNewTpl] = useState<NewTemplate>({ name:'', description:'', project_type:'consulting', estimated_weeks:12, phases:[{name:traducir('proyectos_ui.fase_1'),estimated_weeks:4,tasks:[{title:traducir('proyectos_ui.tarea_inicial'),estimated_hours:8}]}] })

  const { mutate: createTpl, isPending: creatingTpl } = useMutation({
    mutationFn: (d: NewTemplate) => templatesApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-templates'] }); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const TPL_ICONS: Record<string, LucideIcon> = { consulting: Building2, development: Code2, maintenance: Wrench, rd: FlaskConical, internal: Home }

  return (
    <div>
      <div className="prj-row-12">
        <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{traducir('projects.nueva_plantilla')}</Button>
      </div>

      {isLoading ? <Spinner /> : templates.length === 0 ? (
        <EmptyState svgIcon={<ClipboardList size={36} />} title={traducir('projects.sin_plantillas')} description={traducir('proyectos_ui.sin_plantillas_desc')} />
      ) : (
        <div className="prj-grid-4">
          {templates.map(t => (
            <div className="prj-card prj-box-7" key={t.id}>
              <div className="prj-row-13">
                {(() => { const IconoTipo = TPL_ICONS[t.project_type] || ClipboardList; return <IconoTipo size={22} className="prj-icono-plantilla" aria-hidden /> })()}
                <div className="u-flex1">
                  <div className="u-md-700">{t.name}</div>
                  {t.description && <div className="u-text2-sm-mt2">{t.description}</div>}
                </div>
              </div>

              <div className="prj-row-muted-2">
                <span className="prj-dato-icono"><CalendarDays size={12} aria-hidden /> {traducir('proyectos_ui.n_semanas', { n: t.estimated_weeks || '?' })}</span>
                <span className="prj-dato-icono"><Clock size={12} aria-hidden /> {traducir('proyectos_ui.n_horas_estimadas', { n: t.estimated_hours || '?' })}</span>
                <span className="prj-dato-icono"><Layers size={12} aria-hidden /> {traducir('proyectos_ui.n_fases', { n: t.phases?.length || 0 })}</span>
              </div>

              {t.phases?.slice(0,3).map((ph, i) => (
                <div className="prj-box-8" key={ph.id}>
                  <span className="u-text2">{i+1}.</span> <span className="u-text1">{ph.name}</span>
                  <span className="prj-text-muted">{traducir('proyectos_ui.n_semanas_abrev', { n: ph.estimated_weeks ?? '?' })} · {traducir('proyectos_ui.n_tareas', { n: ph.tasks.length })}</span>
                </div>
              ))}
              {(t.phases?.length||0) > 3 && <div className="u-hint">+{t.phases.length-3} {traducir('projects.fases_mas')}</div>}

              <Pulsable className="prj-btn-base-2" onClick={() => { setInstantiating(t); setInstForm({ name:`${t.name} — ${new Date().getFullYear()}`, client_id:'', client_name:'', start_date:new Date().toISOString().slice(0,10), budget_amount:'', pm_id:'' }) }}>
                {traducir('projects.crear_proyecto_desde_esta_plantilla')}
              </Pulsable>
            </div>
          ))}
        </div>
      )}

      {instantiating && (
        <Modal open title={traducir('proyectos_ui.crear_proyecto_titulo', { nombre: instantiating.name })} onClose={() => setInstantiating(null)} width={520}>
          <div className="u-stack-14">
            <div className="prj-card-muted-2">
              {traducir('projects.esta_plantilla_creara')} <strong className="u-text1">{traducir('proyectos_ui.n_fases', { n: instantiating.phases?.length || 0 })}</strong> {traducir('proyectos_ui.y_aproximadamente')} <strong className="u-text1">{traducir('proyectos_ui.n_tareas', { n: instantiating.phases?.reduce((s: number, p) => s + (p.tasks?.length || 0), 0) || 0 })}</strong> {traducir('projects.automaticamente')}
            </div>
            <div><label className="prj-ls" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{traducir('projects.nombre_del_proyecto_2')}</label><Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={instForm.name} onChange={e => setInstForm(f=>({...f,name:e.target.value}))} inputClassName="prj-fs" /></div>
            <div className="u-grid2-14">
              <div><label className="prj-ls" id={`${idCampo}-etcliente`} htmlFor={`${idCampo}-cliente`}>{traducir('proyectos_ui.cliente')}</label><ClientSelect id={`${idCampo}-cliente`} aria-labelledby={`${idCampo}-etcliente`} value={instForm.client_id||''} onChange={(id, c) => setInstForm(f=>({...f, client_id: id, client_name: c ? c.name : ''}))} placeholder={traducir('projects.selecciona_un_cliente')} className="projects-page-e2" /></div>
              <div><label className="prj-ls" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{traducir('projects.label_start_date')}</label><DateInput id={`${idCampo}-2`} value={instForm.start_date} onChange={e => setInstForm(f=>({...f,start_date:e.target.value}))} className="prj-fs" /></div>
              <div><label className="prj-ls" id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`}>{traducir('proyectos_ui.presupuesto_moneda', { moneda: fmtMoneda.simbolo })}</label><Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={instForm.budget_amount} onChange={e => setInstForm(f=>({...f,budget_amount:e.target.value}))} inputClassName="prj-fs" /></div>
              <div><label className="prj-ls" id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`}>{traducir('proyectos_ui.project_manager')}</label>
                <Select suelto placeholder={false} className="prj-fs" id={`${idCampo}-4`} value={instForm.pm_id||''} onChange={e => setInstForm(f=>({...f,pm_id:e.target.value}))}>
                  <option value="">{traducir('projects.sin_asignar')}</option>
                  {pms.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </Select>
              </div>
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setInstantiating(null)}>{traducir('common.cancel')}</Button>
              <Button onClick={() => instantiate({ tplId: instantiating.id, data: { ...instForm, budget_amount: instForm.budget_amount ? +instForm.budget_amount : undefined } })} disabled={creating || !instForm.name}>
                {creating ? traducir('proyectos_ui.creando') : traducir('proyectos_ui.crear_proyecto_btn')}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {showCreate && (
        <Modal open title={traducir('projects.nueva_plantilla_2')} onClose={() => setShowCreate(false)} width={580}>
          <div className="u-stack-14">
            <div><label className="prj-ls" htmlFor={`${idCampo}-nombre`}>{traducir('proyectos_ui.nombre_req')}</label><Input id={`${idCampo}-nombre`} value={newTpl.name} onChange={e => setNewTpl(f=>({...f,name:e.target.value}))} placeholder={traducir('projects.nombre_de_la_plantilla')} aria-label={traducir('projects.nombre_de_la_plantilla')} inputClassName="prj-fs" /></div>
            <div><label className="prj-ls" id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`}>{traducir('projects.label_description')}</label><Textarea id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={newTpl.description||''} onChange={e => setNewTpl(f=>({...f,description:e.target.value}))} rows={2} inputClassName="prj-fs prj-input" /></div>
            <div className="prj-grid-5">
              <div><label className="prj-ls" id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`}>{traducir('proyectos_ui.col_tipo')}</label>
                <Select suelto placeholder={false} className="prj-fs" id={`${idCampo}-6`} value={newTpl.project_type} onChange={e => setNewTpl(f=>({...f,project_type:e.target.value}))}>
                  {['consulting','development','maintenance','rd','internal'].map(t => <option key={t} value={t}>{t}</option>)}
                </Select>
              </div>
              <div><label className="prj-ls" id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`}>{traducir('proyectos_ui.semanas_estimadas')}</label><Input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} type="number" value={newTpl.estimated_weeks} onChange={e => setNewTpl(f=>({...f,estimated_weeks:+e.target.value}))} inputClassName="prj-fs" /></div>
              <div><label className="prj-ls" id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`}>{traducir('proyectos_ui.horas_estimadas')}</label><Input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} type="number" value={newTpl.estimated_hours||''} onChange={e => setNewTpl(f=>({...f,estimated_hours:+e.target.value}))} inputClassName="prj-fs" /></div>
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{traducir('common.cancel')}</Button>
              <Button onClick={() => createTpl(newTpl)} disabled={creatingTpl || !newTpl.name}>{traducir('proyectos_ui.crear_plantilla')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// Wrapper that fetches dependencies and passes them to GanttChart
function GanttWithDeps({ projectId, tasks }: { projectId: string; tasks: GanttTasks }) {
  // Las del Gantt son /tasks/dependencies (predecessor/successor); /task-dependencies es
  // el grafo con metadatos ({nodes, edges}) y aquí daba siempre una lista vacía.
  const { data: deps = [] } = useQuery({
    queryKey: ['task-deps', projectId],
    queryFn: () => taskDependenciesApi.getByProject(projectId).then(r => r.data),
    enabled: !!projectId,
  })
  return <GanttChart mode="project" tasks={tasks} dependencies={deps} />
}


export default function ProjectsPage() {
  const traducir = useAppT()
  const tono = useTono()
  const t = useAppT()
  const { puede } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const search = searchParams.get('search') || ''
  const statusFilter = searchParams.get('status') || ''
  const typeFilter = searchParams.get('type') || ''
  const view = searchParams.get('view') || 'grid'
  const setParam = (k: string, v: string) => setSearchParams((p: URLSearchParams) => { const n = new URLSearchParams(p); v ? n.set(k, v) : n.delete(k); return n }, { replace: true })
  const setSearch = (v: string) => setParam('search', v)
  const setStatusFilter = (v: string) => setParam('status', v)
  const setTypeFilter = (v: string) => setParam('type', v)
  const setView = (v: string) => setParam('view', v)
  const [showCreate, setShowCreate] = useState(false)
  const [editTarget, setEditTarget] = useState<ProjectSummary | null>(null)
  const [selected, setSelected] = useState<ProjectSummary | null>(null)
  const [ganttMode, setGanttMode] = useState('portfolio')  // portfolio | project
  const projCols = useMemo(() => PROJ_COLS.map(c => ({ ...c, label: traducir(c.label) })), [traducir])
  const { visibleCols, colTemplate, ColToggle, visible: visCols } = useColVisibility(projCols, 'projects')

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects', search, statusFilter],
    // `statusFilter` sale de un select: texto que el servidor valida contra `ProjectStatus`.
    queryFn: () => projectsApi.list({ search: search || undefined, status: (statusFilter || undefined) as ProjectStatus }).then(r => r.data as ProjectSummary[]),
  })

  const { data: projectDetail } = useQuery({
    queryKey: ['project', selected?.id],
    queryFn: () => projectsApi.get(selected.id).then(r => r.data as ProjectDetail),
    enabled: !!selected,
  })

  // `ProjectOut` no trae tareas: el Gantt por proyecto las pide a `GET /tasks`.
  const ganttProjectId = view === 'gantt' && ganttMode === 'project' ? selected?.id : undefined
  const { data: ganttTasks = [] } = useQuery({
    queryKey: ['tasks', 'gantt', ganttProjectId],
    queryFn: () => tasksApi.list({ project_id: ganttProjectId }).then(r => r.data),
    enabled: !!ganttProjectId,
  })

  const { mutate: updateStatus } = useMutation({
    // `status` sale de un select con los valores de `ProjectStatus`.
    mutationFn: ({ id, status }: { id: string; status: string }) => projectsApi.update(id, { status: status as ProjectStatus }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const filtered = projects.filter(p => !typeFilter || p.project_type === typeFilter)
  const { sort: projSort, setSort: setProjSort, sortedData: sortedProjects } = useSort(filtered, 'name')

  const stats = {
    total: projects.length,
    active: projects.filter(p => p.status === 'active').length,
    atRisk: projects.filter(p => p.risk_level === 'high' || p.risk_level === 'critical').length,
    overBudget: projects.filter(p => tono('presupuesto', p.budget_used_pct) === 'danger').length,
  }

  return (
    <PageShell>
      <PageHeader
        icon={<FolderOpen size={18} />}
        title={t('nav.projects')}
        subtitle={t('projects.subtitle', { total: stats.total, active: stats.active, atRisk: stats.atRisk })}
        exportTargetSelector='[data-export-table="projects-list"]'
        exportFilePrefix='projects'
        actions={
          <div className="ds-row">
            <div className="ds-segmented" role="group" aria-label={traducir('proyectos_ui.vista')}>
              {[
                { v: 'grid',      label: traducir('proyectos_ui.vista_tarjetas'), icon: LayoutGrid },
                { v: 'list',      label: traducir('proyectos_ui.vista_lista'), icon: List },
                { v: 'gantt',     label: 'Gantt',     icon: Calendar },
                { v: 'templates', label: traducir('proyectos_ui.vista_plantillas'),icon: FileStack },
              ].map(({ v, label, icon: Icon }) => (
                <Pulsable aria-label={label} key={v} aria-pressed={view === v}
                  onClick={() => setView(v)} title={label}>
                  <Icon size={12} />
                </Pulsable>
              ))}
            </div>
            {puede('proyectos.gestionar') && (
              <Button onClick={() => setShowCreate(true)}>
                <Plus size={13} /> {traducir('projects.nuevo_proyecto')}
              </Button>
            )}
          </div>
        }
      />

      {/* Stats strip */}
      <div className="ds-grid-stats prj-text-2">
        {[
          { label: traducir('proyectos_ui.stat_total'), value: stats.total, color: 'var(--text-1)' },
          { label: traducir('proyectos_ui.stat_activos'), value: stats.active, color: 'var(--accent)' },
          { label: traducir('proyectos_ui.stat_en_riesgo'), value: stats.atRisk, color: 'var(--warning)' },
          { label: traducir('proyectos_ui.stat_sobre_presupuesto'), value: stats.overBudget, color: 'var(--danger)' },
        ].map(s => (
          <div key={s.label} className="ds-card prj-box-9">
            <div className="prj-text-2xl-strong prj-text-4" style={{ '--prj-text-4-color': s.color } as CSSProperties}>{s.value}</div>
            <div className="ds-eyebrow">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div className="ds-toolbar prj-text-2">
        <div className="prj-box-10">
          <Search size={14} aria-hidden className="prj-icono-buscar" />
          <Input value={search} onChange={e => setSearch(e.target.value)} aria-label={traducir('projects.buscar_proyecto_por_nombre_o_codigo')} placeholder={traducir('projects.buscar_proyecto_por_nombre_o_codigo')} inputClassName="prj-input-4" />
        </div>
        <Select suelto placeholder={false} aria-label={traducir('proyectos_ui.filtro_estado')} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="prj-input-5">
          <option value="">{traducir('projects.todos_los_estados')}</option>
          {PROJECT_STATUSES.map(s => <option key={s.value} value={s.value}>{traducir(s.label)}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label={traducir('proyectos_ui.filtro_tipo')} value={typeFilter} onChange={e => setTypeFilter(e.target.value)} className="prj-input-5">
          <option value="">{traducir('projects.todos_los_tipos')}</option>
          <OpcionesDeCatalogo catalogo="project-types" />
        </Select>
      </div>

      {isLoading ? (
        <SkeletonProjects />
      ) : filtered.length === 0 && view !== 'templates' ? (
        <EmptyState icon="folder" title={traducir('projects.sin_proyectos')} description={traducir('proyectos_ui.sin_proyectos_desc')} ctaLabel={traducir('proyectos_ui.crear_proyecto')} onCta={() => setShowCreate(true)} />
      ) : view === 'grid' ? (
        <div className="ds-grid-cards">
          {sortedProjects.map(p => (
            <ProjectCard key={p.id} project={p} onClick={setSelected}
              onStatusChange={(id, status) => updateStatus({ id, status })} onEdit={setEditTarget} />
          ))}
        </div>
      ) : view === 'list' ? (
        <div data-export-table="projects-list" className="ds-card prj-box-11">
          <div className="prj-box-12">
          <div className="prj-grid-muted prj-box-13" style={{ '--prj-box-13-grid-template-columns': colTemplate } as CSSProperties}>
            {(visibleCols as typeof PROJ_COLS).map(c => (
              c.id === 'risk'
                ? <div className="prj-row-14" key={c.id}>
                    <SortableTH col={c.sortKey} sort={projSort} onSort={setProjSort}>{c.label}</SortableTH>
                    <ColToggle />
                  </div>
                : <SortableTH key={c.id} col={c.sortKey} sort={projSort} onSort={setProjSort}>{c.label}</SortableTH>
            ))}
          </div>
          {sortedProjects.map(p => (
            <div className="prj-grid-6 prj-box-14" key={p.id}
              style={{ '--prj-box-14-grid-template-columns': colTemplate } as CSSProperties}
              onPointerEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
              onPointerLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              {visCols.includes('name') && (
                <Pulsable className="prj-btn-ghost-4" onClick={() => setSelected(p)}>
                  <div className="u-base-600">{p.name}</div>
                  <div className="u-text2-mono-xs">{p.code}</div>
                </Pulsable>
              )}
              {visCols.includes('type') && <span className="u-text2-sm"><EtiquetaDeCatalogo catalogo="project-types" clave={p.project_type} /></span>}
              {visCols.includes('pm') && <span className="u-sm">{p.pm_name || '—'}</span>}
              {visCols.includes('status') && <StatusDropdown project={p} onUpdate={status => updateStatus({ id: p.id, status })} />}
              {visCols.includes('budget') && <span className="prj-text-sm-mono" style={{ '--prj-text-sm-mono-color': tono('presupuesto', p.budget_used_pct ?? 0) === 'danger' ? 'var(--danger)' : 'var(--text-2)' } as CSSProperties}>{p.budget_used_pct?.toFixed(0) ?? 0}%</span>}
              {visCols.includes('progress') && <span className="u-text2-sm">{p.progress_pct?.toFixed(0) ?? 0}%</span>}
              {visCols.includes('risk') && <Badge label={p.risk_level} display={undefined} _color={undefined} />}
            </div>
          ))}
          </div>
        </div>
      ) : view === 'templates' ? (
        <TemplatesTab />
      ) : null}

      {/* ─── GANTT VIEW ─── */}
      {view === 'gantt' && (
        <div>
          <div className="prj-row-15">
            {[['portfolio', traducir('proyectos_ui.gantt_portfolio')], ['project', traducir('proyectos_ui.gantt_por_proyecto')]].map(([m, label]) => (
              <Pulsable className="prj-btn-xs-4" aria-pressed={ganttMode === m} key={m} onClick={() => setGanttMode(m)}
                style={{ '--prj-btn-xs-4-border': `1px solid ${ganttMode === m ? 'var(--accent)' : 'var(--surface-4)'}`, '--prj-btn-xs-4-background': ganttMode === m ? 'var(--accent-muted)' : 'transparent', '--prj-btn-xs-4-color': ganttMode === m ? 'var(--accent)' : 'var(--text-2)' } as CSSProperties}>
                {label}
              </Pulsable>
            ))}
            {ganttMode === 'project' && (
              <Select suelto placeholder={false} className="prj-input-6" value={selected?.id || ''} onChange={e => { const p = filtered.find(x => x.id === e.target.value); setSelected(p || null) }}>
                <option value="">{traducir('projects.selecciona_un_proyecto')}</option>
                {filtered.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </Select>
            )}
          </div>
          {ganttMode === 'portfolio' && (
            <GanttChart
              mode="portfolio"
              projects={filtered.map(p => ({
                id: p.id, code: p.code, name: p.name, status: p.status,
                start_date: p.start_date, end_date_planned: p.end_date_planned,
                progress_pct: p.progress_pct,
              }))}
            />
          )}
          {ganttMode === 'project' && selected && (
            <GanttWithDeps
              projectId={selected.id}
              tasks={ganttTasks.map(t => ({
                id: t.id, code: t.code, title: t.title,
                status: t.status, priority: t.priority,
                story_points: t.story_points,
                start_date: t.start_date || t.created_at?.slice(0,10),
                due_date: t.due_date,
                progress_pct: t.status === 'done' ? 100 : t.status === 'in_progress' ? 50 : 0,
              }))}
            />
          )}
          {ganttMode === 'project' && !selected && (
            <EmptyState icon={<GanttChartSquare size={28} />} title={traducir('projects.selecciona_un_proyecto_para_ver_su_gantt')} />
          )}
        </div>
      )}


      <ProjectDetailModal project={selected} detail={projectDetail} open={!!selected} onClose={() => setSelected(null)} onEdit={setEditTarget} />
      <ProjectFormModal open={showCreate} onClose={() => setShowCreate(false)} />
      {editTarget && <ProjectFormModal key={editTarget.id} open={!!editTarget} onClose={() => setEditTarget(null)} project={editTarget} />}
    </PageShell>
  )
}