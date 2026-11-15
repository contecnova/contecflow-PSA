import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, tasksApi, risksApi, type ProjectDetail, type ProjectUpdatePayload, type TaskListItem } from '../services/api'
import { Spinner, LoadBar as LoadBarRaw } from '../components/ui'
import { fmtDate, fmtCurrency } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { ChevronLeft, FolderOpen, Users, CheckSquare, AlertTriangle, BarChart2, ExternalLink, Edit2, X, Check, Sparkles, FileText, Lightbulb } from 'lucide-react'
import DocumentosDeFicha from '../components/conectores/DocumentosDeFicha'
import LeccionesDelProyecto from '../components/lecciones/LeccionesDeOrigen'
import SmartScheduleModal from '../components/SmartScheduleModal'
import { useAppT } from '../i18n/AppLangContext'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { alpha } from '../constants/theme'
import DateInput from '../components/ui/DateInput'
import { STALE_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'
import { DEFAULT_PAGE_SIZE } from '../constants/pagination'
import './ProjectDetailPage.css'

// LoadBar's inferred props are all-required; expose a loose signature for callers.
const LoadBar = LoadBarRaw as (props: { value: number; max?: number; height?: number; label?: string; color?: string }) => JSX.Element

// ── Loose project / task / member / risk shapes (API slices are narrowly typed) ──
 
/**
 * `ProjectOut` (app/schemas/projects.py), tal como lo tipa el slice de proyectos.
 * `pm_name` NO viene en `GET /projects/{id}` (ProjectOut trae `project_manager`):
 * la pantalla lo lee igualmente, así que el PM no se muestra nunca. Se declara
 * opcional para no cambiar el comportamiento; ver informe de la auditoría #25.
 */
type Project = ProjectDetail & { pm_name?: string | null }
 
type Task = TaskListItem
 
type Member = { id?: string; user_id?: string; full_name?: string; name?: string; role?: string; project_role?: string; allocation_pct?: number | null }
 
type Risk = { id?: string; title?: string; description?: string; impact?: string; severity?: string; status?: string }

const STATUS_COLOR_MAP: Record<string, string> = {
  planning:  'var(--text-2)',
  active:    'var(--accent)',
  on_hold:   'var(--warning)',
  paused:    'var(--warning)',
  completed: 'var(--success)',
  closed:    'var(--success)',
  cancelled: 'var(--text-3)',
  archived:  'var(--text-4)',
}

const RISK_COLOR: Record<string, string> = { low: 'var(--success)', medium: 'var(--warning)', high: 'var(--danger)', critical: 'var(--danger)' }

function MetaItem({ label, value }: { label: string; value?: string | number | null }) {
  if (!value) return null
  return (
    <div>
      <div className="pd-text-muted-2xs-strong">{label}</div>
      <div className="pd-text-base">{value}</div>
    </div>
  )
}

function OverviewTab({ project }: { project: Project }) {
  const t = useAppT()
  const budgetPct = project.budget_used_pct ?? 0
  const budgetColor = budgetPct > 90 ? 'var(--danger)' : budgetPct > 70 ? 'var(--warning)' : 'var(--success)'

  return (
    <div className="u-stack-20">
      {/* Progress */}
      <div className="pd-card">
        <div className="pd-row">
          <span className="pd-text">{t('project_detail.project_progress')}</span>
          <span className="pd-text-accent-strong-mono">{(project.progress_pct ?? 0).toFixed(0)}%</span>
        </div>
        <LoadBar value={project.progress_pct ?? 0} />
      </div>

      {/* Metadata grid */}
      <div className="pd-grid">
        <MetaItem label={t('project_detail.meta_type')} value={etiquetaCodigo(t, 'tipo_proyecto', project.project_type)} />
        <MetaItem label={t('project_detail.meta_pm')} value={project.pm_name} />
        <MetaItem label={t('project_detail.meta_client')} value={project.client_name} />
        <MetaItem label={t('project_detail.meta_department')} value={project.department} />
        <MetaItem label={t('project_detail.meta_start')} value={project.start_date ? fmtDate(project.start_date) : null} />
        <MetaItem label={t('project_detail.meta_end_planned')} value={project.end_date_planned ? fmtDate(project.end_date_planned) : null} />
        {project.budget_amount && (
          <MetaItem label={t('project_detail.meta_budget')} value={fmtCurrency(project.budget_amount)} />
        )}
        <MetaItem label={t('project_detail.meta_team')} value={project.team_size ? `${project.team_size} ${t('project_detail.people')}` : null} />
      </div>

      {/* Budget bar */}
      {project.budget_amount && (
        <div className="pd-card">
          <div className="pd-row">
            <span className="pd-text">{t('project_detail.budget_execution')}</span>
            <span className="pd-text-strong-mono pd-text-3" style={{ '--pd-text-3-color': budgetColor } as CSSProperties}>{budgetPct.toFixed(0)}%</span>
          </div>
          <LoadBar value={Math.min(budgetPct, 100)} color={budgetColor} />
          <div className="pd-text-muted-xs">
            {t('project_detail.total')}: {fmtCurrency(project.budget_amount)}
          </div>
        </div>
      )}

      {/* Description */}
      {project.description && (
        <div className="pd-card">
          <div className="pd-text-muted-xs-strong">{t('project_detail.description')}</div>
          <p className="pd-text-base-2">{project.description}</p>
        </div>
      )}

      {/* Quick links */}
      <div className="u-wrap-10">
        {[
          { label: t('project_detail.view_gantt'), to: `/gantt?project=${project.id}`, icon: BarChart2 },
          { label: t('project_detail.view_full_tasks'), to: `/tasks?project_id=${project.id}`, icon: CheckSquare },
        ].map(({ label, to, icon: Icon }) => (
          <Link key={to} to={to} className="pd-enlace-rapido">
            <Icon size={12} />{label} <ExternalLink size={10} />
          </Link>
        ))}
      </div>
    </div>
  )
}

function TasksTab({ projectId }: { projectId?: string }) {
  const t = useAppT()
  const { data, isLoading } = useQuery<Task[]>({
    queryKey: ['project-detail-tasks', projectId],
    queryFn: () => tasksApi.list({ project_id: projectId, page_size: DEFAULT_PAGE_SIZE }).then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })

  const tasks = data || []
  const STATUS_COLOR: Record<string, string> = { todo: 'var(--text-3)', in_progress: 'var(--accent)', done: 'var(--success)', blocked: 'var(--danger)' }

  if (isLoading) return <div className="pd-row-2"><Spinner /></div>

  if (tasks.length === 0) return (
    <div className="pd-state-muted">
      <div className="pd-text-4xl">📋</div>
      <div className="pd-text-muted-md">{t('project_detail.no_tasks')}</div>
      <Link to={`/tasks?project_id=${projectId}`} className="pd-enlace-accion">
        {t('project_detail.create_first_task')}
      </Link>
    </div>
  )

  const open   = tasks.filter(tk => tk.status !== 'done')
  const done   = tasks.filter(tk => tk.status === 'done')

  return (
    <div className="u-stack-12">
      <div className="pd-row-muted">
        <span>{t('project_detail.total')}: <b className="u-text1">{tasks.length}</b></span>
        <span>{t('project_detail.open_tasks')}: <b className="u-accent">{open.length}</b></span>
        <span>{t('project_detail.completed_tasks')}: <b className="u-success">{done.length}</b></span>
      </div>
      {tasks.map(task => (
        <div className="pd-row-3" key={task.id}>
          <div className="pd-box pd-box-8" style={{ '--pd-box-8-background': STATUS_COLOR[task.status || ''] || 'var(--text-3)' } as CSSProperties} />
          <div className="u-flex1-min0">
            <div className="pd-box-2">
              {task.title}
            </div>
            {task.assignee && (
              <div className="u-text3-xs-mt2">→ {task.assignee.full_name}</div>
            )}
          </div>
          {task.due_date && (
            <span className="pd-box-muted">{fmtDate(task.due_date)}</span>
          )}
          <span className="pd-box-3 pd-box-9" style={{ '--pd-box-9-background': alpha(STATUS_COLOR[task.status || ''] || 'var(--text-3)', '18'), '--pd-box-9-color': STATUS_COLOR[task.status || ''] || 'var(--text-3)' } as CSSProperties}>
            {task.status?.replace(/_/g, ' ') || '—'}
          </span>
        </div>
      ))}
    </div>
  )
}

function TeamTab({ projectId }: { projectId?: string }) {
  const t = useAppT()
  const { data: members = [], isLoading } = useQuery<Member[]>({
    queryKey: ['project-detail-team', projectId],
    queryFn: () => projectsApi.team(projectId!).then(r => {
      const d = r.data as Member[] | { members?: Member[]; items?: Member[] }
      return Array.isArray(d) ? d : (d?.members || d?.items || [])
    }),
    staleTime: STALE_DEFAULT_MS,
  })

  if (isLoading) return <div className="pd-row-2"><Spinner /></div>

  if (members.length === 0) return (
    <div className="pd-state-muted">
      <div className="pd-text-4xl">👥</div>
      <div className="pd-text-muted-md">{t('project_detail.no_members')}</div>
      <Link to="/resources" className="pd-enlace-accion">
        {t('project_detail.manage_resources')}
      </Link>
    </div>
  )

  return (
    <div className="u-stack-8">
      {members.map((m, i) => (
        <div className="pd-row-3" key={m.id || m.user_id || i}>
          <div className="pd-row-accent">
            {(m.full_name || m.name || '?').charAt(0).toUpperCase()}
          </div>
          <div className="u-flex1">
            <div className="u-text1-base-600">{m.full_name || m.name || '—'}</div>
            {(m.role || m.project_role) && (
              <div className="pd-text-muted-xs-2">{m.role || m.project_role}</div>
            )}
          </div>
          {m.allocation_pct != null && (
            <span className="pd-text-accent-sm-strong-mono">
              {m.allocation_pct}%
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

function RisksTab({ projectId }: { projectId?: string }) {
  const t = useAppT()
  const { data: risks = [], isLoading } = useQuery<Risk[]>({
    queryKey: ['project-detail-risks', projectId],
    // Auditoria 2026-11 (#39): el endpoint devuelve `{risks, summary}`; se leia
    // como lista o `{items}` y la pestana de riesgos salia siempre vacia.
    queryFn: () => risksApi.list<Risk>(projectId, undefined).then(r => r.data?.risks ?? []),
    staleTime: STALE_DEFAULT_MS,
  })

  if (isLoading) return <div className="pd-row-2"><Spinner /></div>

  if (risks.length === 0) return (
    <div className="pd-state-muted">
      <div className="pd-text-4xl">✅</div>
      <div className="pd-text-muted-md">{t('project_detail.no_risks')}</div>
      <Link to="/risks" className="pd-enlace-accion">
        {t('project_detail.view_risk_mgmt')}
      </Link>
    </div>
  )

  const IMPACT_COLOR: Record<string, string> = { low: 'var(--success)', medium: 'var(--warning)', high: 'var(--danger)', critical: 'var(--danger)' }

  return (
    <div className="u-stack-8">
      {risks.map((risk, i) => {
        const impColor = IMPACT_COLOR[risk.impact || risk.severity || ''] || 'var(--text-3)'
        return (
          <div className="pd-card-2" key={risk.id || i} style={{ '--pd-card-2-border': `1px solid ${alpha(impColor, '30')}`, '--pd-card-2-border-left': `3px solid ${impColor}` } as CSSProperties}>
            <div className="pd-row-4">
              <div>
                <div className="pd-text-base-3">
                  {risk.title || risk.description}
                </div>
                {risk.description && risk.title && (
                  <div className="pd-text-muted-sm">{risk.description}</div>
                )}
              </div>
              <div className="pd-row-5">
                {(risk.impact || risk.severity) && (
                  <span className="pd-box-4 pd-box-10" style={{ '--pd-box-10-background': alpha(impColor, '18'), '--pd-box-10-color': impColor } as CSSProperties}>
                    {risk.impact || risk.severity}
                  </span>
                )}
                {risk.status && (
                  <span className="pd-card-muted">
                    {risk.status}
                  </span>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

type EditProjectFormState = {
  name: string
  description: string
  status: string
  end_date_planned: string
  budget_amount: number | string
}

function EditProjectForm({ project, onSave, onCancel, isPending }: {
  project: Project
  onSave: (form: EditProjectFormState) => void
  onCancel: () => void
  isPending: boolean
}) {
  const idCampo = useId()
  const t = useAppT()
  const STATUS_CFG = {
    planning:  { color: STATUS_COLOR_MAP.planning,  label: t('project_detail.status_planning') },
    active:    { color: STATUS_COLOR_MAP.active,    label: t('project_detail.status_active') },
    on_hold:   { color: STATUS_COLOR_MAP.on_hold,   label: t('project_detail.status_on_hold') },
    paused:    { color: STATUS_COLOR_MAP.paused,    label: t('project_detail.status_paused') },
    completed: { color: STATUS_COLOR_MAP.completed, label: t('project_detail.status_completed') },
    closed:    { color: STATUS_COLOR_MAP.closed,    label: t('project_detail.status_closed') },
    cancelled: { color: STATUS_COLOR_MAP.cancelled, label: t('project_detail.status_cancelled') },
    archived:  { color: STATUS_COLOR_MAP.archived,  label: t('project_detail.status_archived') },
  }
  // `budget_amount` arranca con el número del proyecto y pasa a texto al editarlo.
  const [form, setForm] = useState<EditProjectFormState>({
    name: project.name || '',
    description: project.description || '',
    status: project.status || 'active',
    end_date_planned: project.end_date_planned?.slice(0, 10) || '',
    budget_amount: project.budget_amount ?? '',
  })
  const set = (k: keyof EditProjectFormState, v: string) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="pd-stack">
      <div>
        <label className="pd-label-style" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{t('project_detail.project_name_label')}</label>
        <input className="pd-input-style" id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => set('name', e.target.value)}
          onFocus={e => e.target.style.borderColor = 'var(--accent)'}
          onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} />
      </div>
      <div>
        <label className="pd-label-style" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{t('project_detail.status_label')}</label>
        <select className="pd-input-style pd-input" id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.status} onChange={e => set('status', e.target.value)}>
          {Object.entries(STATUS_CFG).map(([v, cfg]) => (
            <option key={v} value={v}>{cfg.label}</option>
          ))}
        </select>
      </div>
      <div>
        <label className="pd-label-style" id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`}>{t('project_detail.end_date_label')}</label>
        <DateInput id={`${idCampo}-3`} value={form.end_date_planned} onChange={e => set('end_date_planned', e.target.value)} className="pd-input-style"
          onFocus={e => e.target.style.borderColor = 'var(--accent)'}
          onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} />
      </div>
      <div>
        <label className="pd-label-style" id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`}>{t('project_detail.budget_label')}</label>
        <input className="pd-input-style" id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={form.budget_amount} onChange={e => set('budget_amount', e.target.value)}
          onFocus={e => e.target.style.borderColor = 'var(--accent)'}
          onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} />
      </div>
      <div>
        <label className="pd-label-style" id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`}>{t('project_detail.description_label')}</label>
        <textarea className="pd-input-style pd-input-2" id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.description} onChange={e => set('description', e.target.value)} rows={4}
          onFocus={e => e.target.style.borderColor = 'var(--accent)'}
          onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} />
      </div>
      <div className="u-row-8">
        <button className="pd-btn-sm" onClick={() => onSave(form)} disabled={isPending || !form.name.trim()}
          style={{ '--pd-btn-sm-cursor': isPending || !form.name.trim() ? 'not-allowed' : 'pointer', '--pd-btn-sm-opacity': !form.name.trim() ? '0.5' : '1' } as CSSProperties}>
          <Check size={13} />{isPending ? t('project_detail.saving') : t('project_detail.save_changes')}
        </button>
        <button className="pd-btn-ghost-sm" onClick={onCancel}>
          <X size={13} /> {t('project_detail.cancel')}
        </button>
      </div>
    </div>
  )
}

export default function ProjectDetailPage() {
  const t = useAppT()
  const TABS = [
    { id: 'overview',  label: t('project_detail.tab_overview'), icon: FolderOpen },
    { id: 'tasks',     label: t('project_detail.tab_tasks'),    icon: CheckSquare },
    { id: 'team',      label: t('project_detail.tab_team'),     icon: Users },
    { id: 'risks',     label: t('project_detail.tab_risks'),    icon: AlertTriangle },
    { id: 'documents', label: t('project_detail.tab_documents'), icon: FileText },
    { id: 'lessons',   label: t('project_detail.tab_lessons'), icon: Lightbulb },
  ]
  const STATUS_CFG: Record<string, { color: string; label: string }> = {
    planning:  { color: STATUS_COLOR_MAP.planning,  label: t('project_detail.status_planning') },
    active:    { color: STATUS_COLOR_MAP.active,    label: t('project_detail.status_active') },
    on_hold:   { color: STATUS_COLOR_MAP.on_hold,   label: t('project_detail.status_on_hold') },
    paused:    { color: STATUS_COLOR_MAP.paused,    label: t('project_detail.status_paused') },
    completed: { color: STATUS_COLOR_MAP.completed, label: t('project_detail.status_completed') },
    closed:    { color: STATUS_COLOR_MAP.closed,    label: t('project_detail.status_closed') },
    cancelled: { color: STATUS_COLOR_MAP.cancelled, label: t('project_detail.status_cancelled') },
    archived:  { color: STATUS_COLOR_MAP.archived,  label: t('project_detail.status_archived') },
  }
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('overview')
  const [editing, setEditing] = useState(false)
  const [smartScheduleOpen, setSmartScheduleOpen] = useState(false)

  const { data: project, isLoading } = useQuery<Project>({
    queryKey: ['project', id],
    queryFn: () => projectsApi.get(id!).then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })

  const { mutate: updateProject, isPending: saving } = useMutation({
    // El formulario manda `status` y `budget_amount` tal como salen de los inputs (texto).
    mutationFn: (data: EditProjectFormState) => projectsApi.update(id!, data as ProjectUpdatePayload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', id] })
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast.success(t('project_detail.project_updated'))
      setEditing(false)
    },
    onError: () => toast.error(t('project_detail.save_error')),
  })

  if (isLoading) return (
    <div className="pd-row-6">
      <Spinner size={28} />
    </div>
  )

  if (!project) return (
    <div className="pd-state-muted-2">
      <div className="pd-text-5xl">🔍</div>
      <div>{t('project_detail.project_not_found')}</div>
    </div>
  )

  const statusCfg = STATUS_CFG[project.status || ''] || STATUS_CFG.planning
  const riskColor = RISK_COLOR[project.risk_level || ''] || 'var(--text-3)'

  return (
    <div className="pd-stack-2">
      {/* Header — sticky para mantener contexto al scroll */}
      <div className="pd-card-3">
        {/* Back + code */}
        <div className="pd-row-7">
          <button className="pd-btn-sm-2" onClick={() => navigate('/projects')}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-1)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
          >
            <ChevronLeft size={14} /> {t('project_detail.back_projects')}
          </button>
          {project.code && (
            <>
              <span className="pd-text-2">/</span>
              <span className="u-text3-mono-xs">{project.code}</span>
            </>
          )}
        </div>

        {/* Title row */}
        <div className="pd-row-8">
          <div>
            <h1 className="pd-title-xl-em-strong">{project.name}</h1>
            <div className="pd-row-9">
              <span className="pd-box-5" style={{ '--pd-box-5-border': `1px solid ${alpha(statusCfg.color, '40')}`, '--pd-box-5-background': alpha(statusCfg.color, '18'), '--pd-box-5-color': statusCfg.color } as CSSProperties}>
                {statusCfg.label}
              </span>
              {project.risk_level && (
                <span className="pd-box-6" style={{ '--pd-box-6-border': `1px solid ${alpha(riskColor, '35')}`, '--pd-box-6-background': alpha(riskColor, '15'), '--pd-box-6-color': riskColor } as CSSProperties}>
                  {t('project_detail.risk_label')} {project.risk_level}
                </span>
              )}
              {project.pm_name && (
                <span className="u-text2-sm">{t('project_detail.pm_label')}: {project.pm_name}</span>
              )}
              {project.client_name && (
                <span className="u-text2-sm">· {project.client_name}</span>
              )}
            </div>
          </div>
          <div className="pd-row-10">
            {tab === 'overview' && !editing && (
              <button className="pd-btn-sm-3" onClick={() => setEditing(true)}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-glow)'; e.currentTarget.style.color = 'var(--accent)' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.color = 'var(--text-2)' }}
              >
                <Edit2 size={12} /> {t('project_detail.edit_button')}
              </button>
            )}
            <Link to={`/tasks?project_id=${project.id}`} className="pd-enlace-cabecera">
              <CheckSquare size={12} /> {t('project_detail.tab_tasks')}
            </Link>
            <Link to={`/gantt?project=${project.id}`} className="pd-enlace-cabecera pd-enlace-cabecera--acento">
              <BarChart2 size={12} /> Gantt
            </Link>
            {/* H22: shortcut a /contracts-ai con project_id pre-rellenado */}
            <Link to={`/contracts-ai?project_id=${project.id}`} className="pd-enlace-cabecera">
              🤖 {t('project_detail.analyze_contract_ai')}
            </Link>
            {/* I27: Auto-planificar tareas del proyecto */}
            <button className="pd-btn-sm-4"
              onClick={() => setSmartScheduleOpen(true)}
              title={t('project_detail.auto_schedule_tooltip')}
            >
              <Sparkles size={12} /> {t('project_detail.auto_schedule')}
            </button>
          </div>
        </div>

        {/* Tab bar */}
        <div className="pd-row-11">
          {TABS.map(({ id: tid, label, icon: Icon }) => (
            <button className="pd-btn-ghost-base"
              key={tid}
              onClick={() => setTab(tid)}
              style={{ '--pd-btn-ghost-base-border-bottom': `2px solid ${tab === tid ? 'var(--accent)' : 'transparent'}`, '--pd-btn-ghost-base-color': tab === tid ? 'var(--accent)' : 'var(--text-2)', '--pd-btn-ghost-base-font-weight': tab === tid ? '700' : '500' } as CSSProperties}
              onMouseEnter={e => { if (tab !== tid) e.currentTarget.style.color = 'var(--text-1)' }}
              onMouseLeave={e => { if (tab !== tid) e.currentTarget.style.color = 'var(--text-2)' }}
            >
              <Icon size={13} />{label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="pd-box-7">
        {tab === 'overview' && editing
          ? <EditProjectForm project={project} onSave={updateProject} onCancel={() => setEditing(false)} isPending={saving} />
          : tab === 'overview'  ? <OverviewTab project={project} />
          : tab === 'tasks'     ? <TasksTab projectId={id} />
          : tab === 'team'      ? <TeamTab projectId={id} />
          : tab === 'risks'     ? <RisksTab projectId={id} />
          : tab === 'documents' && id ? <DocumentosDeFicha ficha="project" id={id} preguntar />
          : tab === 'lessons' && id ? <LeccionesDelProyecto id={id} cerrado={['completed', 'closed'].includes(String(project?.status))} />
          : null
        }
      </div>
      <SmartScheduleModal
        open={smartScheduleOpen}
        onClose={() => setSmartScheduleOpen(false)}
        projectId={id}
        projectName={project?.name}
      />
    </div>
  )
}
