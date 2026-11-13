import { useState, useEffect, useMemo, useId } from 'react'
import LeccionesQueAplican from '../components/lecciones/LeccionesQueAplican'
import type { CSSProperties, ComponentProps } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, usersApi, portalApi, templatesApi, dependenciesApi, tasksApi } from '../services/api'
import type { MemberAddPayload, ProjectCreatePayload, ProjectStatus } from '../services/api'
import { settingsApi } from '../services/settingsApi'
import { Badge, LoadBar, Button, Modal, Spinner, EmptyState, ClientSelect, useSort, SortableTH } from '../components/ui'
import ProjectRiskBadge from '../components/ui/ProjectRiskBadge'
import { SkeletonProjects } from '../components/ui/Skeletons'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import {
  FolderOpen, Plus, Search, LayoutGrid, List, Calendar, FileStack,
  Pencil, ArrowRight, ClipboardList,
} from 'lucide-react'
import GanttChart from '../components/GanttChart'
import DocumentsPanel from '../components/DocumentsPanel'
import { fmtDate, fmtCurrency, TYPE_LABELS, extractErr} from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { BILLING_TYPES } from '../constants/api'
import { useAuth } from '../context/AuthContext'
import { useColVisibility } from '../components/ui/ColVisibility'
import { useAppT } from '../i18n/AppLangContext'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'
import { alpha } from '../constants/theme'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
const PROJ_COLS = [
  { id: 'name',     label: 'Proyecto',     width: '2fr',   sortKey: 'name' },
  { id: 'type',     label: 'Tipo',         width: '1fr',   sortKey: 'project_type' },
  { id: 'pm',       label: 'PM',           width: '1fr',   sortKey: 'pm_name' },
  { id: 'status',   label: 'Estado',       width: '140px', sortKey: 'status' },
  { id: 'budget',   label: 'Presupuesto',  width: '100px', sortKey: 'budget_used_pct' },
  { id: 'progress', label: 'Progreso',     width: '80px',  sortKey: 'progress_pct' },
  { id: 'risk',     label: 'Riesgo',       width: '80px',  sortKey: 'risk_level' },
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
type ProjectMember = { id: string; user_id: string; full_name: string; email?: string; role: string; allocation_pct: number; avatar_initials?: string }
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
type TemplateTask = { title: string; estimated_hours: number; priority: string }
type TemplatePhase = { id?: string; name: string; duration_weeks: number; tasks?: TemplateTask[] }
type ProjectTemplate = { id: string; name: string; description?: string | null; project_type: string; estimated_weeks?: number | null; estimated_hours?: number | null; phases?: TemplatePhase[] }
type NewTemplate = { name: string; description: string; project_type: string; estimated_weeks: number; estimated_hours?: number; phases: TemplatePhase[] }
type InstantiateForm = { name: string; client_id: string; client_name: string; start_date: string; budget_amount: string; pm_id?: string }
type InstantiateResult = { project_code: string; project_name: string; phases_created: number; tasks_created: number }
type GanttTasks = ComponentProps<typeof GanttChart>['tasks']
type GanttDeps = ComponentProps<typeof GanttChart>['dependencies']

// ── Estilos compartidos ───────────────────────────────────────────────────────
const card: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const PROJECT_STATUSES = [
  { value: 'planning',  label: 'Planificación' },
  { value: 'active',    label: 'Activo' },
  { value: 'on_hold',   label: '⏳ En espera' },
  { value: 'paused',    label: '⏸ Pausado' },
  { value: 'completed', label: 'Completado' },
  { value: 'closed',    label: 'Cerrado' },
  { value: 'cancelled', label: 'Cancelado' },
  { value: 'archived',  label: 'Archivado' },
]
const PROJECT_TYPES = Object.entries(TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))
const RISK_LEVELS = [
  { value: 'low', label: 'Bajo' },
  { value: 'medium', label: 'Medio' },
  { value: 'high', label: 'Alto' },
  { value: 'critical', label: 'Crítico' },
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
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['end_date_planned'], message: t('projects.error_date_range') })
    }
    const budget = Number(data.budget_amount || 0)
    if (!Number.isNaN(budget) && budget < 0) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['budget_amount'], message: t('projects.error_budget_negative') })
    }
    const retainerDay = Number(data.retainer_day || 0)
    if (data.billing_type === 'recurring_retainer' && (retainerDay < 1 || retainerDay > 28)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['retainer_day'], message: t('projects.error_retainer_day') })
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
  const [open, setOpen] = useState(false)
  const cfg: Record<string, { color: string; icon: string }> = {
    planning:  { color: 'var(--text-2)', icon: '📋' },
    active:    { color: 'var(--accent)', icon: '🟢' },
    paused:    { color: 'var(--warning)', icon: '⏸' },
    closed:    { color: 'var(--success)', icon: '✅' },
    on_hold:   { color: 'var(--warning)', icon: '⏳' },
    completed: { color: 'var(--success)', icon: '🏁' },
    cancelled: { color: 'var(--text-3)', icon: '❌' },
    archived:  { color: 'var(--text-4)', icon: '📦' },
  }
  const c = cfg[project.status] || cfg.planning

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        style={{
          display: 'flex', alignItems: 'center', gap: 5,
          background: alpha(c.color, '15'), border: `1px solid ${alpha(c.color, '40')}`,
          borderRadius: 20, padding: '3px 10px', cursor: 'pointer',
          fontSize: "var(--text-xs)", fontWeight: 700, color: c.color, fontFamily: 'inherit',
          textTransform: 'uppercase', letterSpacing: '0.06em',
        }}
      >
        {c.icon} {project.status} ▾
      </button>
      {open && (
        <>
          <div role="presentation" onMouseDown={e => { e.stopPropagation(); setOpen(false) }}
            style={{ position: 'fixed', inset: 0, zIndex: 10 }} />
          <div style={{
            position: 'absolute', top: '110%', left: 0, zIndex: 20,
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)',
            padding: 6, minWidth: 160, boxShadow: '0 8px 24px #00000060',
          }}>
            {PROJECT_STATUSES.map(s => (
              <button key={s.value} onClick={e => { e.stopPropagation(); onUpdate(s.value); setOpen(false) }}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  background: project.status === s.value ? 'var(--accent-muted)' : 'transparent',
                  border: 'none', borderRadius: 'var(--radius-sm)', padding: '8px 12px',
                  color: project.status === s.value ? 'var(--accent)' : 'var(--text-1)',
                  fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                {s.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function ProjectCard({ project, onClick, onStatusChange, onEdit }: { project: ProjectSummary; onClick: (p: ProjectSummary) => void; onStatusChange: (id: string, s: string) => void; onEdit: (p: ProjectSummary) => void }) {
  return (
    <div className="ds-card"
      onPointerEnter={e => e.currentTarget.style.borderColor = 'var(--accent-border)'}
      onPointerLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 'var(--space-3)' }}>
        <button type="button" style={{ cursor: 'pointer', flex: 1, minWidth: 0, background: 'transparent', border: 'none', textAlign: 'left', padding: 0, fontFamily: 'inherit' }} onClick={() => onClick(project)}>
          <div className="ds-muted" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>{project.code}</div>
          <div style={{ fontSize: 'var(--text-md-em)', fontWeight: 700, color: 'var(--text-1)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{project.name}</div>
          {project.pm_name && <div className="ds-muted" style={{ marginTop: 2 }}>PM: {project.pm_name}</div>}
          {project.department && <div className="ds-muted">Depto: {project.department}</div>}
          {project.client_name && <div className="ds-muted">Cliente: {project.client_name}</div>}
        </button>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6, flexShrink: 0 }}>
          <StatusDropdown project={project} onUpdate={status => onStatusChange(project.id, status)} />
          <Badge label={project.risk_level} display={undefined} _color={undefined} />
          <ProjectRiskBadge projectId={project.id} hasData={(project.task_count ?? project.team_size ?? 1) > 0} />
        </div>
      </div>

      <button type="button" style={{ cursor: 'pointer', width: '100%', background: 'transparent', border: 'none', textAlign: 'left', padding: 0, fontFamily: 'inherit' }} onClick={() => onClick(project)}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
          <span>{TYPE_LABELS[project.project_type] || project.project_type}</span>
          <span>{project.progress_pct?.toFixed(0) ?? 0}% completado</span>
        </div>
        <LoadBar value={project.progress_pct ?? 0} label={undefined} />
      </button>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-sm)' }}>
        <button type="button" style={{ cursor: 'pointer', display: 'flex', gap: 'var(--space-4)', background: 'transparent', border: 'none', padding: 0, fontFamily: 'inherit' }} onClick={() => onClick(project)}>
          <span className="ds-muted">Equipo: <span className="u-text1">{project.team_size}</span></span>
          {project.budget_amount && (
            <span style={{ color: project.budget_used_pct > 90 ? 'var(--danger)' : 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>
              {project.budget_used_pct?.toFixed(0) ?? 0}% presupuesto
            </span>
          )}
        </button>
        <div className="u-row-6">
          <Link to={`/projects/${project.id}`} onClick={e => e.stopPropagation()}
            style={{
              background: 'var(--accent-muted)', border: '1px solid var(--accent-border-soft)',
              borderRadius: 'var(--radius-sm)', padding: '4px 10px',
              color: 'var(--accent)', fontSize: 'var(--text-xs)', fontWeight: 600,
              textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4,
            }}>
            Ver <ArrowRight size={11} />
          </Link>
          <button onClick={e => { e.stopPropagation(); onEdit(project) }}
            style={{
              background: 'transparent', border: '1px solid var(--surface-4)',
              borderRadius: 'var(--radius-sm)', padding: '4px 10px',
              color: 'var(--text-2)', cursor: 'pointer',
              fontSize: 'var(--text-xs)', fontFamily: 'inherit',
              display: 'inline-flex', alignItems: 'center', gap: 4,
            }}>
            <Pencil size={11} /> Editar
          </button>
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
    onError: e => toast.error(extractErr(e, 'Error al guardar el proyecto')),
  })

  const set = (k: keyof ProjectForm) => (e: CambioDeCampo) => setForm(f => ({ ...f, [k]: e.target.value }))
  const validateForm = () => {
    const parsed = projectFormSchema.safeParse(form)
    if (parsed.success) {
      setErrors({})
      return true
    }
    const nextErrors: Record<string, string> = {}
    parsed.error.issues.forEach(issue => {
      const key = issue.path?.[0]
      if (key && !nextErrors[key]) nextErrors[key] = issue.message
    })
    setErrors(nextErrors)
    return false
  }
  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? `Editar — ${project.name}` : 'Nuevo Proyecto'} width={600}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label htmlFor={`${idCampo}-nombre`} style={ls}>Nombre *</label>
          <input id={`${idCampo}-nombre`} value={form.name} onChange={set('name')} style={fs} placeholder={traducir('projects.nombre_del_proyecto')} aria-label={traducir('projects.nombre_del_proyecto')} />
          {errors.name && <div className="u-field-error">{errors.name}</div>}
        </div>
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Tipo *</label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.project_type} onChange={set('project_type')} style={fs}>
            <option value="">Seleccionar...</option>
            {PROJECT_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          {errors.project_type && <div className="u-field-error">{errors.project_type}</div>}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Estado</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.status} onChange={set('status')} style={fs}>
            {PROJECT_STATUSES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Riesgo</label>
          <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.risk_level} onChange={set('risk_level')} style={fs}>
            {RISK_LEVELS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-etcliente`} htmlFor={`${idCampo}-cliente`} style={ls}>Cliente</label>
          <ClientSelect
            id={`${idCampo}-cliente`}
            aria-labelledby={`${idCampo}-etcliente`}
            value={form.client_id}
            onChange={(id, client) => setForm(f => ({ ...f, client_id: id, client_name: client ? client.name : '' }))}
            placeholder={traducir('projects.selecciona_un_cliente')}
            style={fs}
          />
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>Departamento</label>
          <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.department} onChange={set('department')} style={fs}>
            <option value="">{traducir('projects.no_department')}</option>
            {departments.map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>{traducir('projects.label_billing')}</label>
          <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.billing_type} onChange={set('billing_type')} style={fs}>
            <option value="">{traducir('projects.no_billing')}</option>
            {(BILLING_TYPES as { value: string; label: string }[]).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Presupuesto ({fmtMoneda.simbolo})</label>
          <input type="number" value={form.budget_amount} onChange={set('budget_amount')} style={fs} placeholder="Presupuesto total" aria-label="Presupuesto total" />
          {errors.budget_amount && <div className="u-field-error">{errors.budget_amount}</div>}
        </div>
        {form.billing_type === 'recurring_retainer' && (
          <>
            <div>
              <label style={ls}>Importe retainer ({fmtMoneda.simbolo}/mes)</label>
              <input type="number" value={form.retainer_amount} onChange={set('retainer_amount')} style={fs} placeholder="Importe mensual" aria-label="Importe mensual" />
            </div>
            <div>
              <label style={ls}>{traducir('projects.label_retainer_day')}</label>
              <input type="number" min="1" max="28" value={form.retainer_day} onChange={set('retainer_day')} style={fs} placeholder={traducir('projects.dia_de_corte')} aria-label={traducir('projects.dia_de_corte')} />
              {errors.retainer_day && <div className="u-field-error">{errors.retainer_day}</div>}
            </div>
          </>
        )}
        <div>
          <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>Fecha inicio</label>
          <DateInput id={`${idCampo}-6`} value={form.start_date} onChange={set('start_date')} style={fs} />
        </div>
        <div>
          <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={ls}>Fecha fin planificada</label>
          <DateInput id={`${idCampo}-7`} value={form.end_date_planned} onChange={set('end_date_planned')} style={fs} />
          {errors.end_date_planned && <div className="u-field-error">{errors.end_date_planned}</div>}
        </div>
        <div className="u-col-full">
          <label style={ls}>{traducir('projects.label_description')}</label>
          <textarea value={form.description} onChange={set('description')} rows={3}
            style={{ ...fs, resize: 'vertical' }} placeholder={traducir('projects.descripcion_del_proyecto')} aria-label={traducir('projects.descripcion_del_proyecto')} />
        </div>
        {/* Revisión 2026-11: antes de crear, lo que aprendimos en proyectos parecidos. */}
        {!isEdit && (form.client_id || form.project_type) && (
          <div className="u-col-full">
            <LeccionesQueAplican contexto="nuevo_proyecto" campos={{ cliente_id: form.client_id || null, tipo_proyecto: form.project_type || null, nombre: form.name, descripcion: form.description }} />
          </div>
        )}
        <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
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
  lead:'🎯 Tech Lead', developer:'💻 Desarrollador', designer:'🎨 Diseñador',
  qa:'🧪 QA', analyst:'📋 Analista', devops:'⚙️ DevOps',
  stakeholder:'👔 Stakeholder', other:'👤 Otro',
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
  const { data: allUsersRaw = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
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
    onError: e => toast.error(extractErr(e, 'Error al responder')),
  })
  const allUsers = Array.isArray(allUsersRaw) ? allUsersRaw : []

  const { mutate: addMember, isPending: adding } = useMutation({
    // Sin strictNullChecks, zod marca opcionales todas las claves del tipo inferido;
    // `user_id` y `role` ya los ha exigido el esquema al validar.
    mutationFn: (d: z.infer<ReturnType<typeof makeProjectMemberSchema>>) => projectsApi.addMember(project.id, d as MemberAddPayload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-members', project.id] }); qc.invalidateQueries({ queryKey: ['capacity-board'] }); qc.invalidateQueries({ queryKey: ['forecast-heatmap'] }); qc.invalidateQueries({ queryKey: ['forecast-summary'] }); setShowAdd(false); setAddForm({ user_id: '', role: 'developer', allocation_pct: 100, notes: '' }); addValidation.setErrors({}) },
    onError: e => toast.error(extractErr(e, 'Error al añadir miembro')),
  })
  const { mutate: removeMember } = useMutation({
    mutationFn: (memberId: string) => projectsApi.removeMember(project.id, memberId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-members', project.id] }); qc.invalidateQueries({ queryKey: ['capacity-board'] }); qc.invalidateQueries({ queryKey: ['forecast-heatmap'] }); qc.invalidateQueries({ queryKey: ['forecast-summary'] }); },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (!project || !detail) return null

  const TABS = [
    { id: 'info',     label: 'ℹ️ Info' },
    { id: 'team',     label: `Equipo${members.length > 0 ? ` (${members.length})` : ''}` },
    { id: 'phases',   label: 'Fases' },
    { id: 'docs',     label: 'Documentos' },
    { id: 'requests', label: `💡 Solicitudes${featureRequests.length > 0 ? ` (${featureRequests.length})` : ''}` },
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
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <Badge label={detail.status} display={undefined} _color={undefined} /><Badge label={detail.risk_level} display={undefined} _color={undefined} /><Badge label={detail.project_type} display={undefined} _color={undefined} />
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20, borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '5px 14px', borderRadius: 'var(--radius-sm)', border: `1px solid ${tab === t.id ? 'var(--accent)' : 'var(--surface-4)'}`, background: tab === t.id ? 'var(--accent-muted)' : 'transparent', color: tab === t.id ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* INFO TAB */}
      {tab === 'info' && (
        <>
          {detail.description && <p style={{ color: 'var(--text-2)', fontSize: "var(--text-md)", marginBottom: 20, lineHeight: 1.6 }}>{detail.description}</p>}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 8 }}>
            {[
              { label: 'Código',        value: detail.code },
              { label: 'PM',            value: detail.project_manager?.full_name || '—' },
              { label: 'Cliente',       value: detail.client_name || '—' },
              { label: 'Departamento',  value: detail.department || '—' },
              { label: 'Inicio',        value: fmtDate(detail.start_date) },
              { label: 'Fin planif.',   value: fmtDate(detail.end_date_planned) },
              { label: 'Progreso',      value: `${detail.progress_pct?.toFixed(0) ?? 0}%` },
              { label: 'Tareas',        value: detail.tasks_total > 0 ? `${detail.tasks_done ?? 0} / ${detail.tasks_total} completadas` : '—' },
              { label: 'Equipo',        value: `${detail.team_size ?? 0} persona${(detail.team_size ?? 0) !== 1 ? 's' : ''}` },
              { label: 'Presupuesto',   value: detail.budget_amount ? fmtCurrency(detail.budget_amount) : '—' },
              { label: 'Gastado',       value: detail.total_cost_spent ? fmtCurrency(detail.total_cost_spent) : '—' },
            ].map(({ label, value }) => (
              <div key={label} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 16px' }}>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
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
            <p style={{ color: 'var(--text-2)', fontSize: "var(--text-base)", margin: 0 }}>
              {traducir('projects.personas_asignadas_explicitamente_a_este_proyecto')}
            </p>
            <Button onClick={() => setShowAdd(s => !s)}>
              {showAdd ? '× Cancelar' : '+ Añadir miembro'}
            </Button>
          </div>

          {/* Formulario añadir */}
          {showAdd && (
            <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 16, marginBottom: 16 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 80px', gap: 10, marginBottom: 10 }}>
                <div>
                  <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', display: 'block', marginBottom: 4 }}>PERSONA *</label>
                  <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={addForm.user_id} onChange={setAddField('user_id')}
                    style={addValidation.inputStyle({ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", width: '100%', fontFamily: 'inherit' }, 'user_id')}>
                    <option value="">Seleccionar persona...</option>
                    {availableUsers.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>)}
                  </select>
                  {addValidation.errors.user_id && <div className="u-field-error">{addValidation.errors.user_id}</div>}
                </div>
                <div>
                  <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', display: 'block', marginBottom: 4 }}>ROL</label>
                  <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={addForm.role} onChange={setAddField('role')}
                    style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", width: '100%', fontFamily: 'inherit' }}>
                    {Object.entries(MEMBER_ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
                <div>
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', display: 'block', marginBottom: 4 }}>% DEDIC.</label>
                  <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" min="1" max="100" value={addForm.allocation_pct}
                    onChange={setAddField('allocation_pct')}
                    style={addValidation.inputStyle({ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", width: '100%', fontFamily: 'inherit' }, 'allocation_pct')} />
                  {addValidation.errors.allocation_pct && <div className="u-field-error">{addValidation.errors.allocation_pct}</div>}
                </div>
              </div>
              <div className="u-row-end">
                <Button
                  onClick={submitAddMember}
                  disabled={adding}
                >
                  {adding ? 'Añadiendo...' : 'Confirmar asignación'}
                </Button>
              </div>
            </div>
          )}

          {/* Lista de miembros */}
          {loadingMembers ? <Spinner /> : members.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-2)' }}>
              <div style={{ fontSize: "var(--text-3xl-em)", marginBottom: 10 }}>👥</div>
              <div style={{ fontSize: "var(--text-md)" }}>{traducir('projects.todavia_no_hay_miembros_asignados')}</div>
              <div style={{ fontSize: "var(--text-sm)", marginTop: 4 }}>{traducir('projects.usa_el_boton_anadir_miembro_para_asignar')}</div>
            </div>
          ) : (
            <div className="u-stack-8">
              {members.map(m => (
                <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)' }}>
                  <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'linear-gradient(135deg, var(--accent-border), var(--purple-border))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-base)", fontWeight: 700, flexShrink: 0, color: 'var(--accent)' }}>
                    {m.avatar_initials}
                  </div>
                  <div className="u-flex1">
                    <div className="u-md-600">{m.full_name}</div>
                    <div className="u-text2-sm">{m.email}</div>
                  </div>
                  <span style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 'var(--radius-sm)', padding: '3px 9px' }}>
                    {MEMBER_ROLES[m.role] || m.role}
                  </span>
                  <span style={{ fontSize: "var(--text-sm)", color: m.allocation_pct >= 100 ? 'var(--success)' : m.allocation_pct >= 50 ? 'var(--warning)' : 'var(--text-2)', fontWeight: 700, minWidth: 38, textAlign: 'right' }}>
                    {m.allocation_pct}%
                  </span>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar a ${m.full_name} del equipo?`, onConfirm: () => removeMember(m.id), danger: true }) }}
                    style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-lg)", padding: '0 4px', lineHeight: 1 }}>×</button>
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
              <div key={ph.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', marginBottom: 8, fontSize: "var(--text-base)" }}>
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
          <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-2)' }}>
            <div style={{ fontSize: "var(--text-3xl-em)", marginBottom: 10 }}>📅</div>
            <div>{traducir('projects.no_phases')}</div>
          </div>
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
            <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-2)' }}>
              <div style={{ fontSize: "var(--text-3xl-em)", marginBottom: 10 }}>💡</div>
              <div style={{ fontSize: "var(--text-md)" }}>{traducir('projects.no_hay_solicitudes_de_funcionalidad_para_este')}</div>
              <div style={{ fontSize: "var(--text-sm)", marginTop: 4, color: 'var(--text-3)' }}>{traducir('projects.los_clientes_pueden_crear_solicitudes_desde_el')}</div>
            </div>
          ) : (
            <div className="u-stack-10">
              {featureRequests.map(fr => {
                const statusColors: Record<string, string> = { new: 'var(--accent)', reviewing: 'var(--warning)', estimated: 'var(--orange)', approved: 'var(--success)', rejected: 'var(--danger)', in_development: 'var(--purple)', done: 'var(--success)' }
                const priorityColors: Record<string, string> = { low: 'var(--text-2)', medium: 'var(--accent)', high: 'var(--warning)', critical: 'var(--danger)' }
                const statusLabels: Record<string, string> = { new: 'Nueva', reviewing: 'Revisando', estimated: 'Estimada', approved: 'Aprobada', rejected: 'Rechazada', in_development: 'En desarrollo', done: 'Completada' }
                const isResponding = respondingFr === fr.id
                const canRespond = ['new', 'reviewing', 'estimated'].includes(fr.status)
                return (
                  <div key={fr.id} style={{ background: 'var(--surface-1)', border: `1px solid ${isResponding ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                      <div className="u-flex1-min0">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                          <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{fr.code}</span>
                          <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: statusColors[fr.status] || 'var(--text-2)', background: alpha(statusColors[fr.status] || 'var(--text-2)', '18'), border: `1px solid ${alpha(statusColors[fr.status] || 'var(--text-2)', '40')}`, borderRadius: 5, padding: '2px 7px' }}>{statusLabels[fr.status] || fr.status}</span>
                          <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: priorityColors[fr.priority] || 'var(--text-2)' }}>● {fr.priority}</span>
                          {fr.client_approved === true && <span style={{ fontSize: "var(--text-xs)", color: 'var(--success)' }}>{traducir('projects.cliente_aprobo')}</span>}
                          {fr.client_approved === false && <span style={{ fontSize: "var(--text-xs)", color: 'var(--danger)' }}>{traducir('projects.cliente_rechazo')}</span>}
                        </div>
                        <div style={{ fontSize: "var(--text-md)", fontWeight: 600, marginBottom: 4 }}>{fr.title}</div>
                        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5 }}>{fr.description}</div>
                        {fr.business_justification && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginTop: 4, fontStyle: 'italic' }}>{traducir('projects.justificacion')} {fr.business_justification}</div>}
                        {(fr.estimated_cost != null || fr.estimated_hours != null) && (
                          <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
                            {fr.estimated_cost != null && <span className="u-text2-sm">💶 {fmtCurrency(fr.estimated_cost)}</span>}
                            {fr.estimated_hours != null && <span className="u-text2-sm">⏱ {fr.estimated_hours}h</span>}
                            {fr.estimated_delivery_weeks != null && <span className="u-text2-sm">📅 {fr.estimated_delivery_weeks} sem.</span>}
                          </div>
                        )}
                        {fr.pm_response && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 6, padding: '6px 10px', background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)', borderLeft: '3px solid var(--accent-glow)' }}>💬 {fr.pm_response}</div>}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0 }}>
                        {canRespond && (
                          <button onClick={() => { setRespondingFr(isResponding ? null : fr.id); if (!isResponding) setRespondForm({ pm_response: fr.pm_response || '', estimated_hours: fr.estimated_hours ?? '', estimated_cost: fr.estimated_cost ?? '', estimated_delivery_weeks: fr.estimated_delivery_weeks ?? '', status: fr.status === 'new' ? 'estimated' : fr.status }) }}
                            style={{ fontSize: "var(--text-xs)", padding: '5px 12px', borderRadius: 7, border: `1px solid ${isResponding ? 'var(--accent)' : 'var(--surface-4)'}`, background: isResponding ? 'var(--accent-muted)' : 'transparent', color: isResponding ? 'var(--accent)' : 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>
                            {isResponding ? '× Cancelar' : '✏️ Responder'}
                          </button>
                        )}
                        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', textAlign: 'right' }}>{fmtDate(fr.submitted_at)}</div>
                      </div>
                    </div>

                    {/* Formulario de respuesta PM */}
                    {isResponding && (
                      <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--surface-4)' }}>
                        <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>{traducir('projects.respuesta_del_pm')}</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 10 }}>
                          <div>
                            <label id={`${idCampo}-${fr.id}-etresp828`} htmlFor={`${idCampo}-${fr.id}-resp828`} style={{ ...ls }}>Coste estimado ({fmtMoneda.simbolo})</label>
                            <input id={`${idCampo}-${fr.id}-resp828`} aria-labelledby={`${idCampo}-${fr.id}-etresp828`} type="number" min="0" value={respondForm.estimated_cost} onChange={e => setRespondForm(f => ({ ...f, estimated_cost: e.target.value }))} style={{ ...fs }} placeholder="0" />
                          </div>
                          <div>
                            <label id={`${idCampo}-${fr.id}-etresp832`} htmlFor={`${idCampo}-${fr.id}-resp832`} style={{ ...ls }}>Horas estimadas</label>
                            <input id={`${idCampo}-${fr.id}-resp832`} aria-labelledby={`${idCampo}-${fr.id}-etresp832`} type="number" min="0" value={respondForm.estimated_hours} onChange={e => setRespondForm(f => ({ ...f, estimated_hours: e.target.value }))} style={{ ...fs }} placeholder="0" />
                          </div>
                          <div>
                            <label id={`${idCampo}-${fr.id}-etresp836`} htmlFor={`${idCampo}-${fr.id}-resp836`} style={{ ...ls }}>Semanas entrega</label>
                            <input id={`${idCampo}-${fr.id}-resp836`} aria-labelledby={`${idCampo}-${fr.id}-etresp836`} type="number" min="0" max="104" value={respondForm.estimated_delivery_weeks} onChange={e => setRespondForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} style={{ ...fs }} placeholder="0" />
                          </div>
                        </div>
                        <div className="u-mb-10">
                          <label id={`${idCampo}-${fr.id}-etresp841`} htmlFor={`${idCampo}-${fr.id}-resp841`} style={{ ...ls }}>{traducir('projects.mensaje_al_cliente')}</label>
                          <textarea id={`${idCampo}-${fr.id}-resp841`} aria-labelledby={`${idCampo}-${fr.id}-etresp841`} rows={3} value={respondForm.pm_response} onChange={e => setRespondForm(f => ({ ...f, pm_response: e.target.value }))} style={{ ...fs, resize: 'vertical' }} placeholder={traducir('projects.explica_la_estimacion_o_razon_del_rechazo')} />
                        </div>
                        <div className="u-row-center-10">
                          <label id={`${idCampo}-${fr.id}-etresp845`} htmlFor={`${idCampo}-${fr.id}-resp845`} style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>Estado</label>
                          <select id={`${idCampo}-${fr.id}-resp845`} aria-labelledby={`${idCampo}-${fr.id}-etresp845`} value={respondForm.status} onChange={e => setRespondForm(f => ({ ...f, status: e.target.value }))} style={{ ...fs, width: 'auto' }}>
                            <option value="estimated">Estimada</option>
                            <option value="approved">Aprobar</option>
                            <option value="rejected">Rechazar</option>
                            <option value="in_development">En desarrollo</option>
                            <option value="done">Completada</option>
                          </select>
                          <div className="u-flex1" />
                          <Button onClick={() => respondFR({ id: fr.id, data: { pm_response: respondForm.pm_response || undefined, estimated_hours: respondForm.estimated_hours !== '' ? Number(respondForm.estimated_hours) : undefined, estimated_cost: respondForm.estimated_cost !== '' ? Number(respondForm.estimated_cost) : undefined, estimated_delivery_weeks: respondForm.estimated_delivery_weeks !== '' ? Number(respondForm.estimated_delivery_weeks) : undefined, status: respondForm.status } })} disabled={respondingFRPending}>
                            {respondingFRPending ? 'Guardando...' : 'Guardar respuesta'}
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

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--surface-4)' }}>
        <Button variant="secondary" onClick={onClose}>Cerrar</Button>
        <Button onClick={() => { onClose(); onEdit(detail) }} icon="✏️">Editar proyecto</Button>
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
  const [instantiating, setInstantiating] = useState<ProjectTemplate | null>(null)
  const [instForm, setInstForm] = useState<InstantiateForm>({ name:'', client_id:'', client_name:'', start_date: new Date().toISOString().slice(0,10), budget_amount:'' })

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['project-templates'],
    queryFn: () => templatesApi.list().then((r): ProjectTemplate[] => r.data),
  })
  const { data: usersRaw = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const users = Array.isArray(usersRaw) ? usersRaw : []
  const pms = users.filter(u => ['admin','pm'].includes(u.role))

  const { mutate: instantiate, isPending: creating } = useMutation({
    mutationFn: ({ tplId, data }: { tplId: string; data: Omit<InstantiateForm, 'budget_amount'> & { budget_amount?: number } }) => templatesApi.instantiate(tplId, data).then((r): InstantiateResult => r.data),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast.success(`✓ Proyecto creado: ${data.project_code} — ${data.project_name}\\n${data.phases_created} fases · ${data.tasks_created} tareas`)
      setInstantiating(null)
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [newTpl, setNewTpl] = useState<NewTemplate>({ name:'', description:'', project_type:'consulting', estimated_weeks:12, phases:[{name:'Fase 1',duration_weeks:4,tasks:[{title:'Tarea inicial',estimated_hours:8,priority:'medium'}]}] })

  const { mutate: createTpl, isPending: creatingTpl } = useMutation({
    mutationFn: (d: NewTemplate) => templatesApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-templates'] }); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const TPL_ICONS: Record<string, string> = { consulting:'🏢', development:'💻', maintenance:'🔧', rd:'🔬', internal:'🏠' }

  return (
    <div>
      <div style={{display:'flex',justifyContent:'flex-end',marginBottom:16}}>
        <Button onClick={() => setShowCreate(true)}>{traducir('projects.nueva_plantilla')}</Button>
      </div>

      {isLoading ? <Spinner /> : templates.length === 0 ? (
        <EmptyState svgIcon={<ClipboardList size={36} />} title={traducir('projects.sin_plantillas')} description="Crea una plantilla para reutilizar fases y tareas" />
      ) : (
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(320px,1fr))',gap:16}}>
          {templates.map(t => (
            <div key={t.id} style={{...card,padding:'18px 22px'}}>
              <div style={{display:'flex',gap:10,alignItems:'flex-start',marginBottom:12}}>
                <span style={{fontSize: "var(--text-2xl)"}}>{TPL_ICONS[t.project_type]||'📋'}</span>
                <div className="u-flex1">
                  <div className="u-md-700">{t.name}</div>
                  {t.description && <div className="u-text2-sm-mt2">{t.description}</div>}
                </div>
              </div>

              <div style={{display:'flex',gap:16,fontSize: "var(--text-sm)",color:'var(--text-2)',marginBottom:14}}>
                <span>📅 {t.estimated_weeks||'?'} semanas</span>
                <span>⏱ {t.estimated_hours||'?'}h estimadas</span>
                <span>📁 {t.phases?.length||0} fases</span>
              </div>

              {t.phases?.slice(0,3).map((ph, i) => (
                <div key={ph.id} style={{padding:'4px 0',borderBottom:'1px solid color-mix(in srgb, var(--surface-4) 8%, transparent)',fontSize: "var(--text-sm)"}}>
                  <span className="u-text2">{i+1}.</span> <span className="u-text1">{ph.name}</span>
                  <span style={{color:'var(--text-3)',marginLeft:8}}>{ph.duration_weeks}w · {ph.tasks?.length||0} tareas</span>
                </div>
              ))}
              {(t.phases?.length||0) > 3 && <div className="u-hint">+{t.phases.length-3} {traducir('projects.fases_mas')}</div>}

              <button onClick={() => { setInstantiating(t); setInstForm({ name:`${t.name} — ${new Date().getFullYear()}`, client_id:'', client_name:'', start_date:new Date().toISOString().slice(0,10), budget_amount:'', pm_id:'' }) }}
                style={{marginTop:14,width:'100%',background:'linear-gradient(135deg, var(--accent), var(--purple))',border:'none',borderRadius:8,padding:'9px',color:'var(--on-accent-light)',cursor:'pointer',fontFamily:'inherit',fontWeight:700,fontSize: "var(--text-base)"}}>
                {traducir('projects.crear_proyecto_desde_esta_plantilla')}
              </button>
            </div>
          ))}
        </div>
      )}

      {instantiating && (
        <Modal open title={`Crear proyecto — ${instantiating.name}`} onClose={() => setInstantiating(null)} width={520}>
          <div className="u-stack-14">
            <div style={{background:'var(--accent-muted)',border:'1px solid var(--accent-border)',borderRadius:8,padding:'10px 14px',fontSize: "var(--text-sm)",color:'var(--text-2)'}}>
              {traducir('projects.esta_plantilla_creara')} <strong className="u-text1">{instantiating.phases?.length||0} fases</strong> y aproximadamente <strong className="u-text1">{instantiating.phases?.reduce((s: number, p)=>s+(p.tasks?.length||0),0)||0} tareas</strong> {traducir('projects.automaticamente')}
            </div>
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{traducir('projects.nombre_del_proyecto_2')}</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={instForm.name} onChange={e => setInstForm(f=>({...f,name:e.target.value}))} style={fs} /></div>
            <div className="u-grid2-14">
              <div><label id={`${idCampo}-etcliente`} htmlFor={`${idCampo}-cliente`} style={ls}>Cliente</label><ClientSelect id={`${idCampo}-cliente`} aria-labelledby={`${idCampo}-etcliente`} value={instForm.client_id||''} onChange={(id, c) => setInstForm(f=>({...f, client_id: id, client_name: c ? c.name : ''}))} placeholder={traducir('projects.selecciona_un_cliente')} style={fs} /></div>
              <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{traducir('projects.label_start_date')}</label><DateInput id={`${idCampo}-2`} value={instForm.start_date} onChange={e => setInstForm(f=>({...f,start_date:e.target.value}))} style={fs} /></div>
              <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Presupuesto ({fmtMoneda.simbolo})</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={instForm.budget_amount} onChange={e => setInstForm(f=>({...f,budget_amount:e.target.value}))} style={fs} /></div>
              <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>Project Manager</label>
                <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={instForm.pm_id||''} onChange={e => setInstForm(f=>({...f,pm_id:e.target.value}))} style={fs}>
                  <option value="">{traducir('projects.sin_asignar')}</option>
                  {pms.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </select>
              </div>
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setInstantiating(null)}>Cancelar</Button>
              <Button onClick={() => instantiate({ tplId: instantiating.id, data: { ...instForm, budget_amount: instForm.budget_amount ? +instForm.budget_amount : undefined } })} disabled={creating || !instForm.name}>
                {creating ? 'Creando...' : '▶ Crear proyecto'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {showCreate && (
        <Modal open title={traducir('projects.nueva_plantilla_2')} onClose={() => setShowCreate(false)} width={580}>
          <div className="u-stack-14">
            <div><label htmlFor={`${idCampo}-nombre`} style={ls}>Nombre *</label><input id={`${idCampo}-nombre`} value={newTpl.name} onChange={e => setNewTpl(f=>({...f,name:e.target.value}))} style={fs} placeholder={traducir('projects.nombre_de_la_plantilla')} aria-label={traducir('projects.nombre_de_la_plantilla')} /></div>
            <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>{traducir('projects.label_description')}</label><textarea id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={newTpl.description||''} onChange={e => setNewTpl(f=>({...f,description:e.target.value}))} rows={2} style={{...fs,resize:'vertical'}} /></div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:10}}>
              <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>Tipo</label>
                <select id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={newTpl.project_type} onChange={e => setNewTpl(f=>({...f,project_type:e.target.value}))} style={fs}>
                  {['consulting','development','maintenance','rd','internal'].map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={ls}>Semanas estimadas</label><input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} type="number" value={newTpl.estimated_weeks} onChange={e => setNewTpl(f=>({...f,estimated_weeks:+e.target.value}))} style={fs} /></div>
              <div><label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} style={ls}>Horas estimadas</label><input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} type="number" value={newTpl.estimated_hours||''} onChange={e => setNewTpl(f=>({...f,estimated_hours:+e.target.value}))} style={fs} /></div>
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancelar</Button>
              <Button onClick={() => createTpl(newTpl)} disabled={creatingTpl || !newTpl.name}>Crear plantilla</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// Wrapper that fetches dependencies and passes them to GanttChart
function GanttWithDeps({ projectId, tasks }: { projectId: string; tasks: GanttTasks }) {
  const { data: depsRaw = [] } = useQuery<GanttDeps>({
    queryKey: ['task-deps', projectId],
    queryFn: () => projectId ? dependenciesApi.get(projectId).then(r => r.data) : Promise.resolve([]),
    enabled: !!projectId,
  })
  const deps = Array.isArray(depsRaw) ? depsRaw : []
  return <GanttChart mode="project" tasks={tasks} dependencies={deps} />
}


export default function ProjectsPage() {
  const traducir = useAppT()
  const t = useAppT()
  const { hasRole } = useAuth()
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
  const { visibleCols, colTemplate, ColToggle, visible: visCols } = useColVisibility(PROJ_COLS, 'projects')

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects', search, statusFilter],
    // `statusFilter` sale de un <select>: texto que el servidor valida contra `ProjectStatus`.
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
    // `status` sale de un <select> con los valores de `ProjectStatus`.
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
    overBudget: projects.filter(p => p.budget_used_pct > 90).length,
  }

  return (
    <PageShell>
      <PageHeader
        icon={<FolderOpen size={18} />}
        title={t('projects.title')}
        subtitle={t('projects.subtitle', { total: stats.total, active: stats.active, atRisk: stats.atRisk })}
        exportTargetSelector='[data-export-table="projects-list"]'
        exportFilePrefix='projects'
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <div className="ds-segmented" role="group" aria-label="Vista">
              {[
                { v: 'grid',      label: 'Tarjetas',  icon: LayoutGrid },
                { v: 'list',      label: 'Lista',     icon: List },
                { v: 'gantt',     label: 'Gantt',     icon: Calendar },
                { v: 'templates', label: 'Plantillas',icon: FileStack },
              ].map(({ v, label, icon: Icon }) => (
                <button aria-label={label} key={v} type="button" aria-pressed={view === v}
                  onClick={() => setView(v)} title={label}>
                  <Icon size={12} />
                </button>
              ))}
            </div>
            {hasRole('admin', 'pm') && (
              <Button onClick={() => setShowCreate(true)}>
                <Plus size={13} /> {traducir('projects.nuevo_proyecto')}
              </Button>
            )}
          </div>
        }
      />

      {/* Stats strip */}
      <div className="ds-grid-stats" style={{ marginBottom: 'var(--space-5)' }}>
        {[
          { label: 'Total', value: stats.total, color: 'var(--text-1)' },
          { label: 'Activos', value: stats.active, color: 'var(--accent)' },
          { label: 'En riesgo', value: stats.atRisk, color: 'var(--warning)' },
          { label: '>90% presupuesto', value: stats.overBudget, color: 'var(--danger)' },
        ].map(s => (
          <div key={s.label} className="ds-card" style={{ padding: '14px 16px', gap: 4 }}>
            <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: s.color, lineHeight: 1.1 }}>{s.value}</div>
            <div className="ds-eyebrow">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div className="ds-toolbar" style={{ marginBottom: 'var(--space-5)' }}>
        <div style={{ position: 'relative', flex: '2 1 240px', minWidth: 200 }}>
          <Search size={14} aria-hidden style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-3)', pointerEvents: 'none',
          }} />
          <input value={search} onChange={e => setSearch(e.target.value)}
            aria-label={traducir('projects.buscar_proyecto_por_nombre_o_codigo')}
            placeholder={traducir('projects.buscar_proyecto_por_nombre_o_codigo')}
            className="ds-input"
            style={{ paddingLeft: 32 }} />
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="ds-input" style={{ flex: '1 1 160px', minWidth: 140 }}>
          <option value="">{traducir('projects.todos_los_estados')}</option>
          {PROJECT_STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
          className="ds-input" style={{ flex: '1 1 160px', minWidth: 140 }}>
          <option value="">{traducir('projects.todos_los_tipos')}</option>
          {PROJECT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
      </div>

      {isLoading ? (
        <SkeletonProjects />
      ) : filtered.length === 0 && view !== 'templates' ? (
        <EmptyState icon="folder" title={traducir('projects.sin_proyectos')} description="Crea el primer proyecto para empezar a planificar" ctaLabel="Crear proyecto" onCta={() => setShowCreate(true)} />
      ) : view === 'grid' ? (
        <div className="ds-grid-cards">
          {sortedProjects.map(p => (
            <ProjectCard key={p.id} project={p} onClick={setSelected}
              onStatusChange={(id, status) => updateStatus({ id, status })} onEdit={setEditTarget} />
          ))}
        </div>
      ) : view === 'list' ? (
        <div data-export-table="projects-list" className="ds-card" style={{ padding: 0, overflowX: 'auto' }}>
          <div style={{ minWidth: 920 }}>
          <div style={{ display: 'grid', gridTemplateColumns: colTemplate, gap: 16, padding: '10px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
            {(visibleCols as typeof PROJ_COLS).map(c => (
              c.id === 'risk'
                ? <div key={c.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
                    <SortableTH col={c.sortKey} sort={projSort} onSort={setProjSort}>{c.label}</SortableTH>
                    <ColToggle />
                  </div>
                : <SortableTH key={c.id} col={c.sortKey} sort={projSort} onSort={setProjSort}>{c.label}</SortableTH>
            ))}
          </div>
          {sortedProjects.map(p => (
            <div key={p.id}
              style={{ display: 'grid', gridTemplateColumns: colTemplate, gap: 16, padding: '14px 20px', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', alignItems: 'center', transition: 'background 0.15s' }}
              onPointerEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
              onPointerLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              {visCols.includes('name') && (
                <button type="button" style={{ cursor: 'pointer', background: 'transparent', border: 'none', textAlign: 'left', padding: 0, fontFamily: 'inherit' }} onClick={() => setSelected(p)}>
                  <div className="u-base-600">{p.name}</div>
                  <div className="u-text2-mono-xs">{p.code}</div>
                </button>
              )}
              {visCols.includes('type') && <span className="u-text2-sm">{TYPE_LABELS[p.project_type] || p.project_type}</span>}
              {visCols.includes('pm') && <span className="u-sm">{p.pm_name || '—'}</span>}
              {visCols.includes('status') && <StatusDropdown project={p} onUpdate={status => updateStatus({ id: p.id, status })} />}
              {visCols.includes('budget') && <span style={{ fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)', color: (p.budget_used_pct ?? 0) > 90 ? 'var(--danger)' : 'var(--text-2)' }}>{p.budget_used_pct?.toFixed(0) ?? 0}%</span>}
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
          <div style={{ display: 'flex', gap: 8, marginBottom: 20, alignItems: 'center' , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
            {[['portfolio','📊 Portfolio (todos)'],['project','📁 Por proyecto']].map(([m, label]) => (
              <button key={m} onClick={() => setGanttMode(m)}
                style={{ padding: '5px 14px', borderRadius: 'var(--radius-sm)', border: `1px solid ${ganttMode === m ? 'var(--accent)' : 'var(--surface-4)'}`, background: ganttMode === m ? 'var(--accent-muted)' : 'transparent', color: ganttMode === m ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
                {label}
              </button>
            ))}
            {ganttMode === 'project' && (
              <select value={selected?.id || ''} onChange={e => { const p = filtered.find(x => x.id === e.target.value); setSelected(p || null) }}
                style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit' }}>
                <option value="">{traducir('projects.selecciona_un_proyecto')}</option>
                {filtered.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
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
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-3)' }}>
              <div style={{ fontSize: "var(--text-4xl)", marginBottom: 12 }}>📅</div>
              <div style={{ fontSize: "var(--text-md)" }}>{traducir('projects.selecciona_un_proyecto_para_ver_su_gantt')}</div>
            </div>
          )}
        </div>
      )}


      <ProjectDetailModal project={selected} detail={projectDetail} open={!!selected} onClose={() => setSelected(null)} onEdit={setEditTarget} />
      <ProjectFormModal open={showCreate} onClose={() => setShowCreate(false)} />
      {editTarget && <ProjectFormModal key={editTarget.id} open={!!editTarget} onClose={() => setEditTarget(null)} project={editTarget} />}
    </PageShell>
  )
}