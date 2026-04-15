import { useState, useEffect } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi, usersApi } from '../services/api'
import { settingsApi } from '../services/settingsApi'
import { Badge, LoadBar, Button, Modal, Spinner, EmptyState, ClientSelect, useSort, SortableTH } from '../components/ui'
import { SkeletonProjects } from '../components/ui/Skeletons'
import PageHeader from '../components/layout/PageHeader'
import { FolderOpen } from 'lucide-react'
import GanttChart from '../components/GanttChart'
import DocumentsPanel from '../components/DocumentsPanel'
import { fmtDate, fmtCurrency, TYPE_LABELS, extractErr} from '../utils/helpers'
import { BILLING_TYPES } from '../constants/api'
import { useAuth } from '../context/AuthContext'
import { useColVisibility } from '../components/ui/ColVisibility'
import { useAppT } from '../i18n/AppLangContext'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'

const PROJ_COLS = [
  { id: 'name',     label: 'Proyecto',     width: '2fr',   sortKey: 'name' },
  { id: 'type',     label: 'Tipo',         width: '1fr',   sortKey: 'project_type' },
  { id: 'pm',       label: 'PM',           width: '1fr',   sortKey: 'pm_name' },
  { id: 'status',   label: 'Estado',       width: '140px', sortKey: 'status' },
  { id: 'budget',   label: 'Presupuesto',  width: '100px', sortKey: 'budget_used_pct' },
  { id: 'progress', label: 'Progreso',     width: '80px',  sortKey: 'progress_pct' },
  { id: 'risk',     label: 'Riesgo',       width: '80px',  sortKey: 'risk_level' },
]

// ── Estilos compartidos ───────────────────────────────────────────────────────
const card = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }
const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const PROJECT_STATUSES = [
  { value: 'planning',  label: '📋 Planificación' },
  { value: 'active',    label: '🟢 Activo' },
  { value: 'on_hold',   label: '⏳ En espera' },
  { value: 'paused',    label: '⏸ Pausado' },
  { value: 'completed', label: '🏁 Completado' },
  { value: 'closed',    label: '✅ Cerrado' },
  { value: 'cancelled', label: '❌ Cancelado' },
  { value: 'archived',  label: '📦 Archivado' },
]
const PROJECT_TYPES = Object.entries(TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))
const RISK_LEVELS = [
  { value: 'low', label: '🟢 Bajo' },
  { value: 'medium', label: '🟡 Medio' },
  { value: 'high', label: '🔴 Alto' },
  { value: 'critical', label: '🚨 Crítico' },
]

const projectFormSchema = z.object({
  name: z.string().min(1, 'El nombre es obligatorio'),
  project_type: z.string().min(1, 'El tipo es obligatorio'),
  start_date: z.string().optional(),
  end_date_planned: z.string().optional(),
  budget_amount: z.union([z.string(), z.number(), z.null()]).optional(),
  retainer_amount: z.union([z.string(), z.number(), z.null()]).optional(),
  retainer_day: z.union([z.string(), z.number(), z.null()]).optional(),
  billing_type: z.string().optional(),
}).superRefine((data, ctx) => {
  if (data.start_date && data.end_date_planned && data.end_date_planned < data.start_date) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['end_date_planned'],
      message: 'La fecha de fin no puede ser anterior a la de inicio',
    })
  }

  const budget = Number(data.budget_amount || 0)
  if (!Number.isNaN(budget) && budget < 0) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['budget_amount'],
      message: 'El presupuesto no puede ser negativo',
    })
  }

  const retainerDay = Number(data.retainer_day || 0)
  if (data.billing_type === 'recurring_retainer' && (retainerDay < 1 || retainerDay > 28)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['retainer_day'],
      message: 'El dia de retainer debe estar entre 1 y 28',
    })
  }
})

const projectMemberSchema = z.object({
  user_id: z.string().trim().min(1, 'La persona es obligatoria'),
  role: z.string().trim().min(1, 'El rol es obligatorio'),
  allocation_pct: z.coerce.number().min(1, 'La dedicacion debe ser al menos 1%').max(100, 'La dedicacion no puede superar el 100%'),
  notes: z.string().optional(),
})

function StatusDropdown({ project, onUpdate }) {
  const [open, setOpen] = useState(false)
  const cfg = {
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
          background: `${c.color}15`, border: `1px solid ${c.color}40`,
          borderRadius: 20, padding: '3px 10px', cursor: 'pointer',
          fontSize: 11, fontWeight: 700, color: c.color, fontFamily: 'inherit',
          textTransform: 'uppercase', letterSpacing: '0.06em',
        }}
      >
        {c.icon} {project.status} ▾
      </button>
      {open && (
        <>
          <div onClick={e => { e.stopPropagation(); setOpen(false) }}
            style={{ position: 'fixed', inset: 0, zIndex: 10 }} />
          <div style={{
            position: 'absolute', top: '110%', left: 0, zIndex: 20,
            background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 10,
            padding: 6, minWidth: 160, boxShadow: '0 8px 24px #00000060',
          }}>
            {PROJECT_STATUSES.map(s => (
              <button key={s.value} onClick={e => { e.stopPropagation(); onUpdate(s.value); setOpen(false) }}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  background: project.status === s.value ? 'var(--accent-muted)' : 'transparent',
                  border: 'none', borderRadius: 6, padding: '8px 12px',
                  color: project.status === s.value ? 'var(--accent)' : 'var(--text-1)',
                  fontSize: 13, cursor: 'pointer', fontFamily: 'inherit',
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

function ProjectCard({ project, onClick, onStatusChange, onEdit }) {
  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12,
      padding: '20px 24px', transition: 'all 0.2s', position: 'relative',
    }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div style={{ cursor: 'pointer', flex: 1 }} onClick={() => onClick(project)}>
          <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4, fontFamily: "'Space Mono', monospace" }}>{project.code}</div>
          <div style={{ fontSize: 15, fontWeight: 700 }}>{project.name}</div>
          {project.pm_name && <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 2 }}>PM: {project.pm_name}</div>}
          {project.department && <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 1 }}>Depto: {project.department}</div>}
          {project.client_name && <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 1 }}>Cliente: {project.client_name}</div>}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
          <StatusDropdown project={project} onUpdate={(status) => onStatusChange(project.id, status)} />
          <Badge label={project.risk_level} />
        </div>
      </div>

      <div style={{ marginBottom: 12, cursor: 'pointer' }} onClick={() => onClick(project)}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 12, color: 'var(--text-2)' }}>
          <span>{TYPE_LABELS[project.project_type] || project.project_type}</span>
          <span>{project.progress_pct?.toFixed(0) ?? 0}% completado</span>
        </div>
        <LoadBar value={project.progress_pct ?? 0} />
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12 }}>
        <div style={{ cursor: 'pointer', display: 'flex', gap: 16 }} onClick={() => onClick(project)}>
          <span style={{ color: 'var(--text-2)' }}>Equipo: <span style={{ color: 'var(--text-1)' }}>{project.team_size}</span></span>
          {project.budget_amount && (
            <span style={{ color: project.budget_used_pct > 90 ? 'var(--danger)' : 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>
              {project.budget_used_pct?.toFixed(0) ?? 0}% presupuesto
            </span>
          )}
        </div>
        <button onClick={e => { e.stopPropagation(); onEdit(project) }}
          style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
          ✏️ Editar
        </button>
      </div>
    </div>
  )
}

function ProjectFormModal({ open, onClose, project = null }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { _invalidate } = useInvalidate()
  const isEdit = !!project

  // Cargar datos completos del proyecto cuando se edita
  const { data: fullProject } = useQuery({
    queryKey: ['project', project?.id],
    queryFn: () => projectsApi.get(project.id).then(r => r.data),
    enabled: !!project?.id,
  })

  // Usar fullProject si está disponible (tiene todos los campos), sino el project del prop
  const src = fullProject || project

  const [form, setForm] = useState({
    name: '', project_type: '', status: 'planning',
    client_name: '', department: '', budget_amount: '',
    description: '', risk_level: 'low',
    start_date: '', end_date_planned: '',
    client_id: '', billing_type: '',
    retainer_amount: '', retainer_day: '',
  })
  const [errors, setErrors] = useState({})

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src?.id, fullProject])

  const { data: departments = [] } = useQuery({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })


  const { mutate, isPending } = useMutation({
    mutationFn: (data) => {
      if (isEdit) {
        // En edición: convertir strings vacíos a null para poder borrar valores,
        // pero mantener 0 y false como valores válidos
        const clean = Object.fromEntries(
          Object.entries(data).map(([k, v]) => [k, v === '' ? null : v])
        )
        return projectsApi.update(project.id, clean)
      } else {
        // En creación: filtrar campos vacíos para no enviar nulls innecesarios
        const clean = Object.fromEntries(
          Object.entries(data).filter(([, v]) => v !== '' && v !== null && v !== undefined)
        )
        return projectsApi.create(clean)
      }
    },
    onSuccess: (_saved) => {
      qc.invalidateQueries(['projects'])
      qc.invalidateQueries(['project'])
      qc.invalidateQueries(['dash-projects-health'])
      qc.invalidateQueries(['dash-pipeline'])
      // Sincronización bidireccional: si cambió el cliente, actualizar vista de Clientes
      qc.invalidateQueries(['clients'])
      qc.invalidateQueries(['client-detail'])
      qc.invalidateQueries(['client-projects-linked'])
      qc.invalidateQueries(['client-projects-available'])
      // Invalidar el detalle específico del proyecto editado
      if (isEdit && project?.id) {
        qc.invalidateQueries(['project', project.id])
      }
      onClose()
    },
    onError: e => toast.error(extractErr(e, 'Error al guardar el proyecto')),
  })

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))
  const validateForm = () => {
    const parsed = projectFormSchema.safeParse(form)
    if (parsed.success) {
      setErrors({})
      return true
    }
    const nextErrors = {}
    parsed.error.issues.forEach(issue => {
      const key = issue.path?.[0]
      if (key && !nextErrors[key]) nextErrors[key] = issue.message
    })
    setErrors(nextErrors)
    return false
  }
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: 14, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? `Editar — ${project.name}` : 'Nuevo Proyecto'} width={600}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={ls}>Nombre *</label>
          <input value={form.name} onChange={set('name')} style={fs} placeholder="Nombre del proyecto" />
          {errors.name && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{errors.name}</div>}
        </div>
        <div>
          <label style={ls}>Tipo *</label>
          <select value={form.project_type} onChange={set('project_type')} style={fs}>
            <option value="">Seleccionar...</option>
            {PROJECT_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          {errors.project_type && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{errors.project_type}</div>}
        </div>
        <div>
          <label style={ls}>Estado</label>
          <select value={form.status} onChange={set('status')} style={fs}>
            {PROJECT_STATUSES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Riesgo</label>
          <select value={form.risk_level} onChange={set('risk_level')} style={fs}>
            {RISK_LEVELS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Cliente</label>
          <ClientSelect
            value={form.client_id}
            onChange={(id, client) => setForm(f => ({ ...f, client_id: id, client_name: client ? client.name : '' }))}
            placeholder="— Sin cliente asignado —"
            style={fs}
          />
        </div>
        <div>
          <label style={ls}>Departamento</label>
          <select value={form.department} onChange={set('department')} style={fs}>
            <option value="">Sin departamento</option>
            {departments.map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Tipo de facturación</label>
          <select value={form.billing_type} onChange={set('billing_type')} style={fs}>
            <option value="">Sin especificar</option>
            {BILLING_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Presupuesto (€)</label>
          <input type="number" value={form.budget_amount} onChange={set('budget_amount')} style={fs} placeholder="0" />
          {errors.budget_amount && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{errors.budget_amount}</div>}
        </div>
        {form.billing_type === 'recurring_retainer' && (
          <>
            <div>
              <label style={ls}>Importe retainer (€/mes)</label>
              <input type="number" value={form.retainer_amount} onChange={set('retainer_amount')} style={fs} placeholder="0" />
            </div>
            <div>
              <label style={ls}>Día del mes (1-28)</label>
              <input type="number" min="1" max="28" value={form.retainer_day} onChange={set('retainer_day')} style={fs} placeholder="1" />
              {errors.retainer_day && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{errors.retainer_day}</div>}
            </div>
          </>
        )}
        <div>
          <label style={ls}>Fecha inicio</label>
          <input type="date" value={form.start_date} onChange={set('start_date')} style={fs} />
        </div>
        <div>
          <label style={ls}>Fecha fin planificada</label>
          <input type="date" value={form.end_date_planned} onChange={set('end_date_planned')} style={fs} />
          {errors.end_date_planned && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{errors.end_date_planned}</div>}
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={ls}>Descripción</label>
          <textarea value={form.description} onChange={set('description')} rows={3}
            style={{ ...fs, resize: 'vertical' }} placeholder="Descripción del proyecto..." />
        </div>
        <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => { if (validateForm()) mutate(form) }} disabled={isPending || !form.name || !form.project_type} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Crear proyecto'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

const MEMBER_ROLES = {
  lead:'🎯 Tech Lead', developer:'💻 Desarrollador', designer:'🎨 Diseñador',
  qa:'🧪 QA', analyst:'📋 Analista', devops:'⚙️ DevOps',
  stakeholder:'👔 Stakeholder', other:'👤 Otro',
}

function ProjectDetailModal({ project, detail, open, onClose, onEdit }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('info')
  const [addForm, setAddForm] = useState({ user_id: '', role: 'developer', allocation_pct: 100, notes: '' })
  const addValidation = useFormValidation(projectMemberSchema)
  const [showAdd, setShowAdd] = useState(false)

  const { data: members = [], isLoading: loadingMembers } = useQuery({
    queryKey: ['project-members', project?.id],
    queryFn: () => api.get(`/projects/${project.id}/members`).then(r => r.data),
    enabled: !!project?.id && tab === 'team',
  })
  const { data: allUsersRaw = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
    enabled: !!project?.id && tab === 'team',
  })
  const allUsers = Array.isArray(allUsersRaw) ? allUsersRaw : []

  const { mutate: addMember, isPending: adding } = useMutation({
    mutationFn: d => api.post(`/projects/${project.id}/members`, d),
    onSuccess: () => { qc.invalidateQueries(['project-members', project.id]); qc.invalidateQueries(['capacity-board']); qc.invalidateQueries(['forecast-heatmap']); qc.invalidateQueries(['forecast-summary']); setShowAdd(false); setAddForm({ user_id: '', role: 'developer', allocation_pct: 100, notes: '' }); addValidation.setErrors({}) },
    onError: e => toast.error(extractErr(e, 'Error al añadir miembro')),
  })
  const { mutate: removeMember } = useMutation({
    mutationFn: memberId => api.delete(`/projects/${project.id}/members/${memberId}`),
    onSuccess: () => { qc.invalidateQueries(['project-members', project.id]); qc.invalidateQueries(['capacity-board']); qc.invalidateQueries(['forecast-heatmap']); qc.invalidateQueries(['forecast-summary']); },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  if (!project || !detail) return null

  const TABS = [
    { id: 'info',  label: 'ℹ️ Info' },
    { id: 'team',  label: `👥 Equipo${members.length > 0 ? ` (${members.length})` : ''}` },
    { id: 'phases',label: '📅 Fases' },
    { id: 'docs',  label: '📄 Documentos' },
  ]

  const memberUserIds = new Set(members.map(m => m.user_id))
  const availableUsers = allUsers.filter(u => !memberUserIds.has(u.id))

  const setAddField = (key) => (e) => {
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
        <Badge label={detail.status} /><Badge label={detail.risk_level} /><Badge label={detail.project_type} />
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20, borderBottom: '1px solid #1e2d45', paddingBottom: 12 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${tab === t.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: tab === t.id ? 'var(--accent-muted)' : 'transparent', color: tab === t.id ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* INFO TAB */}
      {tab === 'info' && (
        <>
          {detail.description && <p style={{ color: 'var(--text-2)', fontSize: 14, marginBottom: 20, lineHeight: 1.6 }}>{detail.description}</p>}
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
                <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>{value}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* TEAM TAB */}
      {tab === 'team' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <p style={{ color: 'var(--text-2)', fontSize: 13, margin: 0 }}>
              Personas asignadas explícitamente a este proyecto.
            </p>
            <Button onClick={() => setShowAdd(s => !s)}>
              {showAdd ? '× Cancelar' : '+ Añadir miembro'}
            </Button>
          </div>

          {/* Formulario añadir */}
          {showAdd && (
            <div style={{ background: 'var(--surface-1)', border: '1px solid #1e2d45', borderRadius: 10, padding: 16, marginBottom: 16 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 80px', gap: 10, marginBottom: 10 }}>
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-2)', display: 'block', marginBottom: 4 }}>PERSONA *</label>
                  <select value={addForm.user_id} onChange={setAddField('user_id')}
                    style={addValidation.inputStyle({ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 10px', color: 'var(--text-1)', fontSize: 13, width: '100%', fontFamily: 'inherit' }, 'user_id')}>
                    <option value="">Seleccionar persona...</option>
                    {availableUsers.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>)}
                  </select>
                  {addValidation.errors.user_id && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{addValidation.errors.user_id}</div>}
                </div>
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-2)', display: 'block', marginBottom: 4 }}>ROL</label>
                  <select value={addForm.role} onChange={setAddField('role')}
                    style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 10px', color: 'var(--text-1)', fontSize: 13, width: '100%', fontFamily: 'inherit' }}>
                    {Object.entries(MEMBER_ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-2)', display: 'block', marginBottom: 4 }}>% DEDIC.</label>
                  <input type="number" min="1" max="100" value={addForm.allocation_pct}
                    onChange={setAddField('allocation_pct')}
                    style={addValidation.inputStyle({ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 10px', color: 'var(--text-1)', fontSize: 13, width: '100%', fontFamily: 'inherit' }, 'allocation_pct')} />
                  {addValidation.errors.allocation_pct && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{addValidation.errors.allocation_pct}</div>}
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
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
              <div style={{ fontSize: 32, marginBottom: 10 }}>👥</div>
              <div style={{ fontSize: 14 }}>Todavía no hay miembros asignados</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>Usa el botón &quot;Añadir miembro&quot; para asignar personas al proyecto</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {members.map(m => (
                <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: 'var(--surface-1)', border: '1px solid #1a2640', borderRadius: 10 }}>
                  <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'linear-gradient(135deg, #00d4ff30, #7c3aed30)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, flexShrink: 0, color: 'var(--accent)' }}>
                    {m.avatar_initials}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>{m.full_name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{m.email}</div>
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--accent)', background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 6, padding: '3px 9px' }}>
                    {MEMBER_ROLES[m.role] || m.role}
                  </span>
                  <span style={{ fontSize: 12, color: m.allocation_pct >= 100 ? 'var(--success)' : m.allocation_pct >= 50 ? 'var(--warning)' : 'var(--text-2)', fontWeight: 700, minWidth: 38, textAlign: 'right' }}>
                    {m.allocation_pct}%
                  </span>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar a ${m.full_name} del equipo?`, onConfirm: () => removeMember(m.id), danger: true }) }}
                    style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 16, padding: '0 4px', lineHeight: 1 }}>×</button>
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
              <div key={ph.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: 'var(--surface-1)', border: '1px solid #1a2640', borderRadius: 10, marginBottom: 8, fontSize: 13 }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{ph.name}</div>
                  {(ph.start_date || ph.end_date) && (
                    <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>
                      {fmtDate(ph.start_date)} → {fmtDate(ph.end_date)}
                    </div>
                  )}
                </div>
                <Badge label={ph.status} />
              </div>
            ))}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-2)' }}>
            <div style={{ fontSize: 32, marginBottom: 10 }}>📅</div>
            <div>No hay fases definidas en este proyecto</div>
          </div>
        )
      )}

      {/* DOCS TAB */}
      {tab === 'docs' && (
        <DocumentsPanel projectId={project.id} />
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20, paddingTop: 16, borderTop: '1px solid #1e2d45' }}>
        <Button variant="secondary" onClick={onClose}>Cerrar</Button>
        <Button onClick={() => { onClose(); onEdit(detail) }} icon="✏️">Editar proyecto</Button>
      </div>
    </Modal>
  )
}

// ── Templates Tab ─────────────────────────────────────────────────────────────
// eslint-disable-next-line no-unused-vars
function TemplatesTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [instantiating, setInstantiating] = useState(null)
  const [instForm, setInstForm] = useState({ name:'', client_id:'', client_name:'', start_date: new Date().toISOString().slice(0,10), budget_amount:'' })

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['project-templates'],
    queryFn: () => api.get('/templates').then(r => r.data),
  })
  const { data: usersRaw = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const users = Array.isArray(usersRaw) ? usersRaw : []
  const pms = users.filter(u => ['admin','pm'].includes(u.role))

  const { mutate: instantiate, isPending: creating } = useMutation({
    mutationFn: ({ tplId, data }) => api.post(`/templates/${tplId}/instantiate`, data).then(r => r.data),
    onSuccess: (data) => {
      qc.invalidateQueries(['projects'])
      toast.success(`✓ Proyecto creado: ${data.project_code} — ${data.project_name}\\n${data.phases_created} fases · ${data.tasks_created} tareas`)
      setInstantiating(null)
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const [newTpl, setNewTpl] = useState({ name:'', description:'', project_type:'consulting', estimated_weeks:12, phases:[{name:'Fase 1',duration_weeks:4,tasks:[{title:'Tarea inicial',estimated_hours:8,priority:'medium'}]}] })

  const { mutate: createTpl, isPending: creatingTpl } = useMutation({
    mutationFn: d => api.post('/templates', d),
    onSuccess: () => { qc.invalidateQueries(['project-templates']); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const TPL_ICONS = { consulting:'🏢', development:'💻', maintenance:'🔧', rd:'🔬', internal:'🏠' }

  return (
    <div>
      <div style={{display:'flex',justifyContent:'flex-end',marginBottom:16}}>
        <Button onClick={() => setShowCreate(true)}>+ Nueva plantilla</Button>
      </div>

      {isLoading ? <Spinner /> : templates.length === 0 ? (
        <EmptyState icon="📋" title="Sin plantillas" description="Crea plantillas de proyecto para acelerar la creación de nuevos proyectos" />
      ) : (
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(320px,1fr))',gap:16}}>
          {templates.map(t => (
            <div key={t.id} style={{...card,padding:'18px 22px'}}>
              <div style={{display:'flex',gap:10,alignItems:'flex-start',marginBottom:12}}>
                <span style={{fontSize:24}}>{TPL_ICONS[t.project_type]||'📋'}</span>
                <div style={{flex:1}}>
                  <div style={{fontSize:14,fontWeight:700}}>{t.name}</div>
                  {t.description && <div style={{fontSize:12,color:'var(--text-2)',marginTop:2}}>{t.description}</div>}
                </div>
              </div>

              <div style={{display:'flex',gap:16,fontSize:12,color:'var(--text-2)',marginBottom:14}}>
                <span>📅 {t.estimated_weeks||'?'} semanas</span>
                <span>⏱ {t.estimated_hours||'?'}h estimadas</span>
                <span>📁 {t.phases?.length||0} fases</span>
              </div>

              {t.phases?.slice(0,3).map((ph,i) => (
                <div key={ph.id} style={{padding:'4px 0',borderBottom:'1px solid #1e2d4515',fontSize:12}}>
                  <span style={{color:'var(--text-2)'}}>{i+1}.</span> <span style={{color:'var(--text-1)'}}>{ph.name}</span>
                  <span style={{color:'var(--text-3)',marginLeft:8}}>{ph.duration_weeks}w · {ph.tasks?.length||0} tareas</span>
                </div>
              ))}
              {(t.phases?.length||0) > 3 && <div style={{fontSize:11,color:'var(--text-3)',marginTop:4}}>+{t.phases.length-3} fases más</div>}

              <button onClick={() => { setInstantiating(t); setInstForm({ name:`${t.name} — ${new Date().getFullYear()}`, client_id:'', client_name:'', start_date:new Date().toISOString().slice(0,10), budget_amount:'', pm_id:'' }) }}
                style={{marginTop:14,width:'100%',background:'linear-gradient(135deg,#00d4ff,#7c3aed)',border:'none',borderRadius:8,padding:'9px',color:'#fff',cursor:'pointer',fontFamily:'inherit',fontWeight:700,fontSize:13}}>
                ▶ Crear proyecto desde esta plantilla
              </button>
            </div>
          ))}
        </div>
      )}

      {instantiating && (
        <Modal open title={`Crear proyecto — ${instantiating.name}`} onClose={() => setInstantiating(null)} width={520}>
          <div style={{display:'flex',flexDirection:'column',gap:14}}>
            <div style={{background:'var(--accent-muted)',border:'1px solid #00d4ff30',borderRadius:8,padding:'10px 14px',fontSize:12,color:'var(--text-2)'}}>
              Esta plantilla creará <strong style={{color:'var(--text-1)'}}>{instantiating.phases?.length||0} fases</strong> y aproximadamente <strong style={{color:'var(--text-1)'}}>{instantiating.phases?.reduce((s,p)=>s+(p.tasks?.length||0),0)||0} tareas</strong> automáticamente.
            </div>
            <div><label style={ls}>Nombre del proyecto *</label><input value={instForm.name} onChange={e => setInstForm(f=>({...f,name:e.target.value}))} style={fs} /></div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:14}}>
              <div><label style={ls}>Cliente</label><ClientSelect value={instForm.client_id||''} onChange={(id, c) => setInstForm(f=>({...f, client_id: id, client_name: c ? c.name : ''}))} placeholder="— Sin cliente —" style={fs} /></div>
              <div><label style={ls}>Fecha de inicio</label><input type="date" value={instForm.start_date} onChange={e => setInstForm(f=>({...f,start_date:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Presupuesto €</label><input type="number" value={instForm.budget_amount} onChange={e => setInstForm(f=>({...f,budget_amount:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Project Manager</label>
                <select value={instForm.pm_id||''} onChange={e => setInstForm(f=>({...f,pm_id:e.target.value}))} style={fs}>
                  <option value="">Sin asignar</option>
                  {pms.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </select>
              </div>
            </div>
            <div style={{display:'flex',justifyContent:'flex-end',gap:10}}>
              <Button variant="secondary" onClick={() => setInstantiating(null)}>Cancelar</Button>
              <Button onClick={() => instantiate({ tplId: instantiating.id, data: { ...instForm, budget_amount: instForm.budget_amount ? +instForm.budget_amount : undefined } })} disabled={creating || !instForm.name}>
                {creating ? 'Creando...' : '▶ Crear proyecto'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {showCreate && (
        <Modal open title="Nueva plantilla de proyecto" onClose={() => setShowCreate(false)} width={580}>
          <div style={{display:'flex',flexDirection:'column',gap:14}}>
            <div><label style={ls}>Nombre *</label><input value={newTpl.name} onChange={e => setNewTpl(f=>({...f,name:e.target.value}))} style={fs} placeholder="Ej: Implementación ERP" /></div>
            <div><label style={ls}>Descripción</label><textarea value={newTpl.description||''} onChange={e => setNewTpl(f=>({...f,description:e.target.value}))} rows={2} style={{...fs,resize:'vertical'}} /></div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:10}}>
              <div><label style={ls}>Tipo</label>
                <select value={newTpl.project_type} onChange={e => setNewTpl(f=>({...f,project_type:e.target.value}))} style={fs}>
                  {['consulting','development','maintenance','rd','internal'].map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div><label style={ls}>Semanas estimadas</label><input type="number" value={newTpl.estimated_weeks} onChange={e => setNewTpl(f=>({...f,estimated_weeks:+e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Horas estimadas</label><input type="number" value={newTpl.estimated_hours||''} onChange={e => setNewTpl(f=>({...f,estimated_hours:+e.target.value}))} style={fs} /></div>
            </div>
            <div style={{display:'flex',justifyContent:'flex-end',gap:10}}>
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
function GanttWithDeps({ projectId, tasks }) {
  const { data: depsRaw = [] } = useQuery({
    queryKey: ['task-deps', projectId],
    queryFn: () => api.get(`/dependencies/${projectId}`).then(r => r.data),
    enabled: !!projectId,
  })
  const deps = Array.isArray(depsRaw) ? depsRaw : []
  return <GanttChart mode="project" tasks={tasks} dependencies={deps} />
}


export default function ProjectsPage() {
  const t = useAppT()
  const { hasRole } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [view, setView] = useState('grid')
  const [showCreate, setShowCreate] = useState(false)
  const [editTarget, setEditTarget] = useState(null)
  const [selected, setSelected] = useState(null)
  const [ganttMode, setGanttMode] = useState('portfolio')  // portfolio | project
  const { visibleCols, colTemplate, ColToggle, visible: visCols } = useColVisibility(PROJ_COLS, 'projects')

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects', search, statusFilter],
    queryFn: () => projectsApi.list({ search: search || undefined, status: statusFilter || undefined }).then(r => r.data),
  })

  const { data: projectDetail } = useQuery({
    queryKey: ['project', selected?.id],
    queryFn: () => projectsApi.get(selected.id).then(r => r.data),
    enabled: !!selected,
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }) => projectsApi.update(id, { status }),
    onSuccess: () => qc.invalidateQueries(['projects']),
    onError: e => toast.error(extractErr(e, 'Error')),
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
    <div className="p-4 sm:p-6 lg:p-8">
      <PageHeader
        icon={<FolderOpen size={18} />}
        title={t('projects.title')}
        subtitle={`${stats.total} proyectos · ${stats.active} activos · ${stats.atRisk} en riesgo`}
        actions={
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
            <div className="w-full sm:w-auto" style={{ display: 'flex', background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, overflow: 'hidden' }}>
              {[['grid', '⊞'], ['list', '☰'], ['gantt', '📅'], ['templates', '📋']].map(([v, icon]) => (
                <button key={v} onClick={() => setView(v)}
                  style={{ padding: '7px 14px', background: view === v ? 'var(--accent-muted)' : 'transparent', border: 'none', color: view === v ? 'var(--accent)' : 'var(--text-2)', fontSize: 14, cursor: 'pointer', fontFamily: 'inherit' }}>
                  {icon}
                </button>
              ))}
            </div>
            {hasRole('admin', 'pm') && (
              <Button onClick={() => setShowCreate(true)} icon="＋">Nuevo proyecto</Button>
            )}
          </div>
        }
      />

      {/* Stats strip */}
      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: 'Total', value: stats.total, color: 'var(--text-2)' },
          { label: 'Activos', value: stats.active, color: 'var(--accent)' },
          { label: 'En riesgo', value: stats.atRisk, color: 'var(--warning)' },
          { label: '>90% presupuesto', value: stats.overBudget, color: 'var(--danger)' },
        ].map(s => (
          <div key={s.label} style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 10, padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 22, fontWeight: 800, fontFamily: "'Space Mono', monospace", color: s.color }}>{s.value}</span>
            <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="🔍 Buscar por nombre o código..."
          className="sm:col-span-2"
          style={{ minWidth: 0, background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit' }}
        />
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="w-full"
          style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
          <option value="">Todos los estados</option>
          {PROJECT_STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
          className="w-full"
          style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
          <option value="">Todos los tipos</option>
          {PROJECT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
      </div>

      {isLoading ? (
        <SkeletonProjects />
      ) : filtered.length === 0 ? (
        <EmptyState icon="folder" title="Sin proyectos" description="Crea tu primer proyecto para empezar a gestionar tu equipo, tareas y entregas." ctaLabel="Nuevo proyecto" onCta={() => setShowCreate(true)} />
      ) : view === 'grid' ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {sortedProjects.map(p => (
            <ProjectCard key={p.id} project={p} onClick={setSelected}
              onStatusChange={(id, status) => updateStatus({ id, status })} onEdit={setEditTarget} />
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto" style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }}>
          <div style={{ minWidth: 920 }}>
          <div style={{ display: 'grid', gridTemplateColumns: colTemplate, gap: 16, padding: '10px 20px', borderBottom: '1px solid #1e2d45', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
            {visibleCols.map(c => (
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
              style={{ display: 'grid', gridTemplateColumns: colTemplate, gap: 16, padding: '14px 20px', borderBottom: '1px solid #1e2d4530', alignItems: 'center', transition: 'background 0.15s' }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              {visCols.includes('name') && (
                <div style={{ cursor: 'pointer' }} onClick={() => setSelected(p)}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>{p.code}</div>
                </div>
              )}
              {visCols.includes('type') && <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{TYPE_LABELS[p.project_type] || p.project_type}</span>}
              {visCols.includes('pm') && <span style={{ fontSize: 12 }}>{p.pm_name || '—'}</span>}
              {visCols.includes('status') && <StatusDropdown project={p} onUpdate={(status) => updateStatus({ id: p.id, status })} />}
              {visCols.includes('budget') && <span style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: p.budget_used_pct > 90 ? 'var(--danger)' : 'var(--text-2)' }}>{p.budget_used_pct?.toFixed(0) ?? 0}%</span>}
              {visCols.includes('progress') && <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{p.progress_pct?.toFixed(0) ?? 0}%</span>}
              {visCols.includes('risk') && <Badge label={p.risk_level} />}
            </div>
          ))}
          </div>
        </div>
      )}

      {/* ─── GANTT VIEW ─── */}
      {view === 'gantt' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 20, alignItems: 'center' }}>
            {[['portfolio','📊 Portfolio (todos)'],['project','📁 Por proyecto']].map(([m, label]) => (
              <button key={m} onClick={() => setGanttMode(m)}
                style={{ padding: '7px 16px', borderRadius: 8, border: `1px solid ${ganttMode === m ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: ganttMode === m ? 'var(--accent-muted)' : 'transparent', color: ganttMode === m ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
                {label}
              </button>
            ))}
            {ganttMode === 'project' && (
              <select value={selected?.id || ''} onChange={e => { const p = filtered.find(x => x.id === e.target.value); setSelected(p || null) }}
                style={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit' }}>
                <option value="">Selecciona un proyecto...</option>
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
          {ganttMode === 'project' && selected && projectDetail && (
            <GanttWithDeps
              projectId={selected.id}
              tasks={(projectDetail.tasks || []).map(t => ({
                id: t.id, code: t.code, title: t.title,
                status: t.status, priority: t.priority,
                story_points: t.story_points,
                start_date: t.created_at?.slice(0,10),
                due_date: t.due_date,
                progress_pct: t.status === 'done' ? 100 : t.status === 'in_progress' ? 50 : 0,
              }))}
            />
          )}
          {ganttMode === 'project' && !selected && (
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-3)' }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>📅</div>
              <div style={{ fontSize: 14 }}>Selecciona un proyecto para ver su Gantt</div>
            </div>
          )}
        </div>
      )}


      <ProjectDetailModal project={selected} detail={projectDetail} open={!!selected} onClose={() => setSelected(null)} onEdit={setEditTarget} />
      <ProjectFormModal open={showCreate} onClose={() => setShowCreate(false)} />
      {editTarget && <ProjectFormModal key={editTarget.id} open={!!editTarget} onClose={() => setEditTarget(null)} project={editTarget} />}
    </div>
  )
}