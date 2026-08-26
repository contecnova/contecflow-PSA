import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, tasksApi, risksApi } from '../services/api'
import { Spinner, LoadBar as LoadBarRaw } from '../components/ui'
import { fmtDate, fmtCurrency, TYPE_LABELS } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { ChevronLeft, FolderOpen, Users, CheckSquare, AlertTriangle, BarChart2, ExternalLink, Edit2, X, Check, Sparkles } from 'lucide-react'
import SmartScheduleModal from '../components/SmartScheduleModal'
import { useAppT } from '../i18n/AppLangContext'

// LoadBar's inferred props are all-required; expose a loose signature for callers.
const LoadBar = LoadBarRaw as (props: { value: number; max?: number; height?: number; label?: string; color?: string }) => JSX.Element

// ── Loose project / task / member / risk shapes (API slices are narrowly typed) ──
 
type Project = { [k: string]: any; id: string; name?: string; status?: string }
 
type Task = { [k: string]: any; id?: string; status?: string; title?: string; assignee_name?: string; due_date?: string }
 
type Member = { [k: string]: any; id?: string; user_id?: string; full_name?: string; name?: string; role?: string; project_role?: string; allocation_pct?: number | null }
 
type Risk = { [k: string]: any; id?: string; title?: string; description?: string; impact?: string; severity?: string; status?: string }

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
      <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', fontWeight: 500 }}>{value}</div>
    </div>
  )
}

function OverviewTab({ project }: { project: Project }) {
  const t = useAppT()
  const budgetPct = project.budget_used_pct ?? 0
  const budgetColor = budgetPct > 90 ? 'var(--danger)' : budgetPct > 70 ? 'var(--warning)' : 'var(--success)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Progress */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, fontSize: "var(--text-base)" }}>
          <span style={{ fontWeight: 600, color: 'var(--text-1)' }}>{t('project_detail.project_progress')}</span>
          <span style={{ color: 'var(--accent)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{(project.progress_pct ?? 0).toFixed(0)}%</span>
        </div>
        <LoadBar value={project.progress_pct ?? 0} />
      </div>

      {/* Metadata grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 16, background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 20 }}>
        <MetaItem label={t('project_detail.meta_type')} value={TYPE_LABELS[project.project_type] || project.project_type} />
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
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, fontSize: "var(--text-base)" }}>
            <span style={{ fontWeight: 600, color: 'var(--text-1)' }}>{t('project_detail.budget_execution')}</span>
            <span style={{ color: budgetColor, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{budgetPct.toFixed(0)}%</span>
          </div>
          <LoadBar value={Math.min(budgetPct, 100)} color={budgetColor} />
          <div style={{ marginTop: 8, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
            {t('project_detail.total')}: {fmtCurrency(project.budget_amount)}
          </div>
        </div>
      )}

      {/* Description */}
      {project.description && (
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 20 }}>
          <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>{t('project_detail.description')}</div>
          <p style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', lineHeight: 1.7, margin: 0 }}>{project.description}</p>
        </div>
      )}

      {/* Quick links */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {[
          { label: t('project_detail.view_gantt'), to: `/gantt?project=${project.id}`, icon: BarChart2 },
          { label: t('project_detail.view_full_tasks'), to: `/tasks?project_id=${project.id}`, icon: CheckSquare },
        ].map(({ label, to, icon: Icon }) => (
          <Link key={to} to={to} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '8px 14px', background: 'var(--surface-3)',
            border: '1px solid var(--surface-4)', borderRadius: 8,
            color: 'var(--text-2)', textDecoration: 'none', fontSize: "var(--text-sm)", fontWeight: 600,
            transition: 'all 0.1s',
          }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-glow)'; e.currentTarget.style.color = 'var(--accent)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.color = 'var(--text-2)' }}
          >
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
    queryFn: () => tasksApi.list({ project_id: projectId, page_size: 50 }).then(r => {
      const d = r.data as unknown as Task[] | { items?: Task[] }
      return Array.isArray(d) ? d : (d?.items || [])
    }),
    staleTime: 30_000,
  })

  const tasks = data || []
  const STATUS_COLOR: Record<string, string> = { todo: 'var(--text-3)', in_progress: 'var(--accent)', done: 'var(--success)', blocked: 'var(--danger)' }

  if (isLoading) return <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>

  if (tasks.length === 0) return (
    <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-3)' }}>
      <div style={{ fontSize: "var(--text-4xl)", marginBottom: 12 }}>📋</div>
      <div style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-2)', marginBottom: 8 }}>{t('project_detail.no_tasks')}</div>
      <Link to={`/tasks?project_id=${projectId}`} style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', fontWeight: 600, textDecoration: 'none' }}>
        {t('project_detail.create_first_task')}
      </Link>
    </div>
  )

  const open   = tasks.filter(tk => tk.status !== 'done' && tk.status !== 'closed')
  const done   = tasks.filter(tk => tk.status === 'done' || tk.status === 'closed')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 16, fontSize: "var(--text-sm)", color: 'var(--text-3)', paddingBottom: 4 }}>
        <span>{t('project_detail.total')}: <b style={{ color: 'var(--text-1)' }}>{tasks.length}</b></span>
        <span>{t('project_detail.open_tasks')}: <b style={{ color: 'var(--accent)' }}>{open.length}</b></span>
        <span>{t('project_detail.completed_tasks')}: <b style={{ color: 'var(--success)' }}>{done.length}</b></span>
      </div>
      {tasks.map(task => (
        <div key={task.id} style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 10, padding: '12px 16px',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
            background: STATUS_COLOR[task.status || ''] || 'var(--text-3)',
          }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {task.title}
            </div>
            {task.assignee_name && (
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 2 }}>→ {task.assignee_name}</div>
            )}
          </div>
          {task.due_date && (
            <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', flexShrink: 0 }}>{fmtDate(task.due_date)}</span>
          )}
          <span style={{
            fontSize: "var(--text-2xs)", padding: '2px 7px', borderRadius: 4, flexShrink: 0,
            background: `${STATUS_COLOR[task.status || ''] || 'var(--text-3)'}18`,
            color: STATUS_COLOR[task.status || ''] || 'var(--text-3)', fontWeight: 700,
            textTransform: 'uppercase', letterSpacing: '0.05em',
          }}>
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
    staleTime: 60_000,
  })

  if (isLoading) return <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>

  if (members.length === 0) return (
    <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-3)' }}>
      <div style={{ fontSize: "var(--text-4xl)", marginBottom: 12 }}>👥</div>
      <div style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-2)', marginBottom: 8 }}>{t('project_detail.no_members')}</div>
      <Link to="/resources" style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', fontWeight: 600, textDecoration: 'none' }}>
        {t('project_detail.manage_resources')}
      </Link>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {members.map((m, i) => (
        <div key={m.id || m.user_id || i} style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 10, padding: '12px 16px',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{
            width: 34, height: 34, borderRadius: '50%', flexShrink: 0,
            background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--accent)',
          }}>
            {(m.full_name || m.name || '?').charAt(0).toUpperCase()}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{m.full_name || m.name || '—'}</div>
            {(m.role || m.project_role) && (
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 1 }}>{m.role || m.project_role}</div>
            )}
          </div>
          {m.allocation_pct != null && (
            <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>
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
    queryFn: () => risksApi.list(projectId, undefined).then((r: { data: unknown }) => {
      const d = r.data as Risk[] | { items?: Risk[] }
      return Array.isArray(d) ? d : (d?.items || [])
    }),
    staleTime: 60_000,
  })

  if (isLoading) return <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>

  if (risks.length === 0) return (
    <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-3)' }}>
      <div style={{ fontSize: "var(--text-4xl)", marginBottom: 12 }}>✅</div>
      <div style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-2)', marginBottom: 8 }}>{t('project_detail.no_risks')}</div>
      <Link to="/risks" style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', fontWeight: 600, textDecoration: 'none' }}>
        {t('project_detail.view_risk_mgmt')}
      </Link>
    </div>
  )

  const IMPACT_COLOR: Record<string, string> = { low: 'var(--success)', medium: 'var(--warning)', high: 'var(--danger)', critical: 'var(--danger)' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {risks.map((risk, i) => {
        const impColor = IMPACT_COLOR[risk.impact || risk.severity || ''] || 'var(--text-3)'
        return (
          <div key={risk.id || i} style={{
            background: 'var(--surface-2)', border: `1px solid ${impColor}30`,
            borderLeft: `3px solid ${impColor}`,
            borderRadius: 10, padding: '12px 16px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', marginBottom: 4 }}>
                  {risk.title || risk.description}
                </div>
                {risk.description && risk.title && (
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5 }}>{risk.description}</div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                {(risk.impact || risk.severity) && (
                  <span style={{ fontSize: "var(--text-2xs)", padding: '2px 7px', borderRadius: 4, background: `${impColor}18`, color: impColor, fontWeight: 700, textTransform: 'uppercase' }}>
                    {risk.impact || risk.severity}
                  </span>
                )}
                {risk.status && (
                  <span style={{ fontSize: "var(--text-2xs)", padding: '2px 7px', borderRadius: 4, background: 'var(--surface-4)', color: 'var(--text-2)', fontWeight: 600, textTransform: 'uppercase' }}>
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

function EditProjectForm({ project, onSave, onCancel, isPending }: {
  project: Project
  onSave: (form: Record<string, string>) => void
  onCancel: () => void
  isPending: boolean
}) {
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
  const [form, setForm] = useState<Record<string, string>>({
    name: project.name || '',
    description: project.description || '',
    status: project.status || 'active',
    end_date_planned: project.end_date_planned?.slice(0, 10) || '',
    budget_amount: project.budget_amount ?? '',
  })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))
  const inputStyle: CSSProperties = {
    width: '100%', boxSizing: 'border-box',
    background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)',
    fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit',
  }
  const labelStyle: CSSProperties = { fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 4 }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 600 }}>
      <div>
        <label style={labelStyle}>{t('project_detail.project_name_label')}</label>
        <input value={form.name} onChange={e => set('name', e.target.value)} style={inputStyle}
          onFocus={e => e.target.style.borderColor = 'var(--accent)'}
          onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} />
      </div>
      <div>
        <label style={labelStyle}>{t('project_detail.status_label')}</label>
        <select value={form.status} onChange={e => set('status', e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
          {Object.entries(STATUS_CFG).map(([v, cfg]) => (
            <option key={v} value={v}>{cfg.label}</option>
          ))}
        </select>
      </div>
      <div>
        <label style={labelStyle}>{t('project_detail.end_date_label')}</label>
        <input type="date" value={form.end_date_planned} onChange={e => set('end_date_planned', e.target.value)} style={inputStyle}
          onFocus={e => e.target.style.borderColor = 'var(--accent)'}
          onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} />
      </div>
      <div>
        <label style={labelStyle}>{t('project_detail.budget_label')}</label>
        <input type="number" value={form.budget_amount} onChange={e => set('budget_amount', e.target.value)} style={inputStyle}
          onFocus={e => e.target.style.borderColor = 'var(--accent)'}
          onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} />
      </div>
      <div>
        <label style={labelStyle}>{t('project_detail.description_label')}</label>
        <textarea value={form.description} onChange={e => set('description', e.target.value)} rows={4}
          style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.6 }}
          onFocus={e => e.target.style.borderColor = 'var(--accent)'}
          onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} />
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={() => onSave(form)} disabled={isPending || !form.name.trim()}
          style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '8px 18px', borderRadius: 8, background: 'var(--accent)', border: 'none', color: '#fff', cursor: isPending || !form.name.trim() ? 'not-allowed' : 'pointer', fontSize: "var(--text-sm)", fontWeight: 700, fontFamily: 'inherit', opacity: !form.name.trim() ? 0.5 : 1 }}>
          <Check size={13} />{isPending ? t('project_detail.saving') : t('project_detail.save_changes')}
        </button>
        <button onClick={onCancel} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '8px 14px', borderRadius: 8, background: 'transparent', border: '1px solid var(--surface-4)', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
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
    queryFn: () => projectsApi.get(id!).then(r => r.data as Project),
    staleTime: 30_000,
  })

  const { mutate: updateProject, isPending: saving } = useMutation({
    mutationFn: (data: Record<string, string>) => projectsApi.update(id!, data as Record<string, never>),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', id] })
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast.success(t('project_detail.project_updated'))
      setEditing(false)
    },
    onError: () => toast.error(t('project_detail.save_error')),
  })

  if (isLoading) return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
      <Spinner size={28} />
    </div>
  )

  if (!project) return (
    <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)' }}>
      <div style={{ fontSize: "var(--text-5xl)", marginBottom: 12 }}>🔍</div>
      <div>{t('project_detail.project_not_found')}</div>
    </div>
  )

  const statusCfg = STATUS_CFG[project.status || ''] || STATUS_CFG.planning
  const riskColor = RISK_COLOR[project.risk_level || ''] || 'var(--text-3)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Header — sticky para mantener contexto al scroll */}
      <div style={{
        padding: '16px 28px 0',
        background: 'var(--surface-1)',
        borderBottom: '1px solid var(--surface-4)',
        flexShrink: 0,
        position: 'sticky',
        top: 0,
        zIndex: 'var(--z-sticky)',
        boxShadow: '0 1px 0 var(--surface-4), 0 8px 16px -8px rgba(0,0,0,0.5)',
      }}>
        {/* Back + code */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => navigate('/projects')} style={{
            background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)',
            display: 'flex', alignItems: 'center', gap: 5, fontSize: "var(--text-sm)", fontFamily: 'inherit', padding: 0,
          }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-1)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
          >
            <ChevronLeft size={14} /> {t('project_detail.back_projects')}
          </button>
          {project.code && (
            <>
              <span style={{ color: 'var(--text-4)' }}>/</span>
              <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{project.code}</span>
            </>
          )}
        </div>

        {/* Title row */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 14 }}>
          <div>
            <h1 style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: 'var(--text-1)', margin: '0 0 6px' }}>{project.name}</h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <span style={{
                fontSize: "var(--text-xs)", fontWeight: 700, padding: '3px 10px', borderRadius: 20,
                background: `${statusCfg.color}18`, border: `1px solid ${statusCfg.color}40`,
                color: statusCfg.color, textTransform: 'uppercase', letterSpacing: '0.06em',
              }}>
                {statusCfg.label}
              </span>
              {project.risk_level && (
                <span style={{
                  fontSize: "var(--text-xs)", fontWeight: 700, padding: '3px 10px', borderRadius: 20,
                  background: `${riskColor}15`, border: `1px solid ${riskColor}35`,
                  color: riskColor, textTransform: 'uppercase', letterSpacing: '0.06em',
                }}>
                  {t('project_detail.risk_label')} {project.risk_level}
                </span>
              )}
              {project.pm_name && (
                <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{t('project_detail.pm_label')}: {project.pm_name}</span>
              )}
              {project.client_name && (
                <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>· {project.client_name}</span>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
            {tab === 'overview' && !editing && (
              <button onClick={() => setEditing(true)} style={{
                display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px',
                background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                borderRadius: 8, color: 'var(--text-2)', cursor: 'pointer',
                fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit', transition: 'all 0.1s',
              }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-glow)'; e.currentTarget.style.color = 'var(--accent)' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.color = 'var(--text-2)' }}
              >
                <Edit2 size={12} /> {t('project_detail.edit_button')}
              </button>
            )}
            <Link to={`/tasks?project_id=${project.id}`} style={{
              display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px',
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              borderRadius: 8, color: 'var(--text-2)', textDecoration: 'none',
              fontSize: "var(--text-sm)", fontWeight: 600, transition: 'all 0.1s',
            }}>
              <CheckSquare size={12} /> {t('project_detail.tab_tasks')}
            </Link>
            <Link to={`/gantt?project=${project.id}`} style={{
              display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px',
              background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)',
              borderRadius: 8, color: 'var(--accent)', textDecoration: 'none',
              fontSize: "var(--text-sm)", fontWeight: 600, transition: 'all 0.1s',
            }}>
              <BarChart2 size={12} /> Gantt
            </Link>
            {/* H22: shortcut a /contracts-ai con project_id pre-rellenado */}
            <Link to={`/contracts-ai?project_id=${project.id}`} style={{
              display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px',
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              borderRadius: 8, color: 'var(--text-2)', textDecoration: 'none',
              fontSize: "var(--text-sm)", fontWeight: 600, transition: 'all 0.1s',
            }}>
              🤖 {t('project_detail.analyze_contract_ai')}
            </Link>
            {/* I27: Auto-planificar tareas del proyecto */}
            <button
              onClick={() => setSmartScheduleOpen(true)}
              style={{
                display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px',
                background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                borderRadius: 8, color: 'var(--text-2)', cursor: 'pointer',
                fontSize: "var(--text-sm)", fontWeight: 600,
              }}
              title={t('project_detail.auto_schedule_tooltip')}
            >
              <Sparkles size={12} /> {t('project_detail.auto_schedule')}
            </button>
          </div>
        </div>

        {/* Tab bar */}
        <div style={{ display: 'flex', gap: 0 }}>
          {TABS.map(({ id: tid, label, icon: Icon }) => (
            <button
              key={tid}
              onClick={() => setTab(tid)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '10px 18px', border: 'none', cursor: 'pointer',
                borderBottom: `2px solid ${tab === tid ? 'var(--accent)' : 'transparent'}`,
                marginBottom: -1,
                background: 'transparent',
                color: tab === tid ? 'var(--accent)' : 'var(--text-2)',
                fontSize: "var(--text-base)", fontWeight: tab === tid ? 700 : 500,
                fontFamily: 'inherit', whiteSpace: 'nowrap', transition: 'color 0.1s',
              }}
              onMouseEnter={e => { if (tab !== tid) e.currentTarget.style.color = 'var(--text-1)' }}
              onMouseLeave={e => { if (tab !== tid) e.currentTarget.style.color = 'var(--text-2)' }}
            >
              <Icon size={13} />{label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, padding: 24, maxWidth: 900 }}>
        {tab === 'overview' && editing
          ? <EditProjectForm project={project} onSave={updateProject} onCancel={() => setEditing(false)} isPending={saving} />
          : tab === 'overview'  ? <OverviewTab project={project} />
          : tab === 'tasks'     ? <TasksTab projectId={id} />
          : tab === 'team'      ? <TeamTab projectId={id} />
          : tab === 'risks'     ? <RisksTab projectId={id} />
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
