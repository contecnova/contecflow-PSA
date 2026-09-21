/**
 * SprintsPage — Full Scrum sprint management
 * Views: Backlog | Sprint Activo | Velocity histórico
 */
import { useState, useEffect } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, projectSprintsApi, tasksApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { RefreshCw } from 'lucide-react'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, ReferenceLine } from 'recharts'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'

type Task = {
  [k: string]: unknown
  id: string
  code?: string
  title?: string
  status?: string
  priority?: string
  story_points?: number
  assignee_name?: string
}
type Sprint = {
  [k: string]: unknown
  id: string
  name?: string
  number?: number
  status?: string
  goal?: string
  tasks?: Task[]
  went_well?: string
  to_improve?: string
  action_items?: string
  days_remaining: number | null
  start_date?: string
  end_date?: string
  planned_points?: number
  completed_points?: number
  task_count?: number
  velocity?: number
}
type RetroInsights = {
  metrics?: {
    completion_rate_pct: number
    velocity_ratio_pct: number
    blocked: number
    carryover: number
  }
  went_well?: string[]
  improve?: string[]
  actions?: { text: string }[]
  risks?: string[]
}

const _STATUS_CFG = {
  planning:  { label: 'Planificación', color: 'var(--purple)', bg: 'var(--purple-bg)' },
  active:    { label: 'Activo',        color: 'var(--accent)', bg: 'var(--accent-glow)' },
  completed: { label: 'Completado',    color: 'var(--success)', bg: 'var(--success-bg)' },
  cancelled: { label: 'Cancelado',     color: 'var(--text-2)', bg: 'rgba(122,138,170,0.13)' },
}

// ── Retrospective modal (v25 AI insights) ────────────────────────────────────
function RetroModal({ sprint, projectId, onClose }: { sprint: Sprint; projectId: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const [manualNotes, setManualNotes] = useState('')

  const { data: retro, isLoading } = useQuery<{ computed_insights?: RetroInsights; saved_notes?: { manual_notes?: string } }>({
    queryKey: ['retro', sprint.id],
    queryFn: () => projectSprintsApi.retrospective(projectId, sprint.id).then(r => r.data),
    ...({ onSuccess: (d: { saved_notes?: { manual_notes?: string } }) => { if (d.saved_notes?.manual_notes) setManualNotes(d.saved_notes.manual_notes) } } as object),
  })

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: (notes: string) => projectSprintsApi.saveRetrospective(projectId, sprint.id, { manual_notes: notes }),
    onSuccess: () => { toast.success('Notas guardadas'); onClose() },
    onError: () => toast.error('Error al guardar'),
  })

  const ins = retro?.computed_insights
  const m = ins?.metrics

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Metrics row */}
      {m && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
          {[
            { label: 'Completitud', value: `${m.completion_rate_pct}%`, color: m.completion_rate_pct >= 80 ? 'var(--success)' : 'var(--warning)' },
            { label: 'Velocity ratio', value: `${m.velocity_ratio_pct}%`, color: m.velocity_ratio_pct >= 85 ? 'var(--accent)' : 'var(--warning)' },
            { label: 'Bloqueadas', value: m.blocked, color: m.blocked > 0 ? 'var(--danger)' : 'var(--success)' },
            { label: 'Carryover', value: m.carryover, color: m.carryover > 0 ? 'var(--warning)' : 'var(--success)' },
          ].map(s => (
            <div key={s.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '10px 12px', textAlign: 'center' }}>
              <div style={{ fontSize: "var(--text-xl)", fontWeight: 800, fontFamily: 'var(--font-mono)', color: s.color }}>{s.value}</div>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 3, textTransform: 'uppercase' }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {isLoading ? (
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '24px 0' }}><Spinner /><span style={{ color: 'var(--text-2)', fontSize: "var(--text-base)" }}>{t('sprints.analizando_datos_del_sprint')}</span></div>
      ) : ins && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {/* Went well */}
          <div style={{ background: 'rgba(74,222,128,0.06)', border: '1px solid rgba(74,222,128,0.2)', borderRadius: 10, padding: '12px 14px' }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--success)', textTransform: 'uppercase', marginBottom: 8 }}>{t('sprints.que_fue_bien')}</div>
            {ins.went_well?.map((item, i) => (
              <div key={i} style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 5, display: 'flex', gap: 7 }}>
                <span style={{ color: 'var(--success)', flexShrink: 0 }}>→</span>{item}
              </div>
            ))}
          </div>
          {/* To improve */}
          <div style={{ background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.2)', borderRadius: 10, padding: '12px 14px' }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--warning)', textTransform: 'uppercase', marginBottom: 8 }}>↑ A mejorar</div>
            {ins.improve?.map((item, i) => (
              <div key={i} style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 5, display: 'flex', gap: 7 }}>
                <span style={{ color: 'var(--warning)', flexShrink: 0 }}>→</span>{item}
              </div>
            ))}
          </div>
          {/* Actions */}
          {(ins.actions?.length ?? 0) > 0 && (
            <div style={{ background: 'rgba(79,142,247,0.06)', border: '1px solid rgba(79,142,247,0.2)', borderRadius: 10, padding: '12px 14px' }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--accent)', textTransform: 'uppercase', marginBottom: 8 }}>→ Acciones propuestas</div>
              {ins.actions?.map((a, i) => (
                <div key={i} style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 5, display: 'flex', gap: 7 }}>
                  <span style={{ color: 'var(--accent)', flexShrink: 0 }}>○</span>{a.text}
                </div>
              ))}
            </div>
          )}
          {/* Risks */}
          {(ins.risks?.length ?? 0) > 0 && (
            <div style={{ background: 'rgba(248,113,113,0.06)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: 10, padding: '12px 14px' }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--danger)', textTransform: 'uppercase', marginBottom: 8 }}>{t('sprints.senales_de_riesgo')}</div>
              {ins.risks?.map((r, i) => (
                <div key={i} style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 5, display: 'flex', gap: 7 }}>
                  <span style={{ color: 'var(--danger)', flexShrink: 0 }}>!</span>{r}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Manual notes */}
      <div>
        <label style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>{t('sprints.notas_del_equipo')}</label>
        <textarea
          value={manualNotes}
          onChange={e => setManualNotes(e.target.value)}
          rows={3}
          placeholder={t('sprints.escribe_notas_para_el_equipo')}
          style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box' }}
        />
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onClose}>Cerrar</Button>
        <Button onClick={() => save(manualNotes)} disabled={saving}>{saving ? 'Guardando...' : 'Guardar notas'}</Button>
      </div>
    </div>
  )
}
const PRIORITY_COLOR: Record<string, string> = { low: 'var(--text-3)', medium: 'var(--warning)', high: 'var(--warning)', critical: 'var(--danger)' }
const TASK_STATUS_CFG: Record<string, { label: string; color: string }> = {
  todo:        { label: 'Por hacer',   color: 'var(--text-3)' },
  in_progress: { label: 'En progreso', color: 'var(--accent)' },
  in_review:   { label: 'En revisión', color: 'var(--purple)' },
  done:        { label: 'Hecho',       color: 'var(--success)' },
  blocked:     { label: 'Bloqueado',   color: 'var(--danger)' },
}

const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

// ── Task card ──────────────────────────────────────────────────────────────────
function TaskCard({ task, onStatusChange, onMoveToBacklog, compact = false }: { task: Task; onStatusChange?: (taskId: string, status: string) => void; onMoveToBacklog?: (taskId: string) => void; compact?: boolean }) {
  const t = useAppT()
  const [showMenu, setShowMenu] = useState(false)
  const cfg = TASK_STATUS_CFG[task.status || ''] || { label: task.status, color: 'var(--text-2)' }
  const pColor = PRIORITY_COLOR[task.priority || ''] || 'var(--text-2)'

  return (
    <div style={{ background: 'var(--surface-2)', border: `1px solid ${cfg.color}30`, borderRadius: 10, padding: compact ? '8px 12px' : '12px 14px', cursor: 'pointer', position: 'relative' }}
      onPointerEnter={e => e.currentTarget.style.borderColor = cfg.color + '60'}
      onPointerLeave={e => e.currentTarget.style.borderColor = cfg.color + '30'}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginBottom: 3 }}>{task.code}</div>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 600, lineHeight: 1.3, color: 'var(--text-1)' }}>{task.title}</div>
        </div>
        <button onClick={e => { e.stopPropagation(); setShowMenu(m => !m) }}
          style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', padding: '0 4px', fontSize: "var(--text-lg)", marginLeft: 8 }}>⋯</button>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, padding: '2px 6px', borderRadius: 4, background: pColor + '20', color: pColor }}>{task.priority}</span>
        {(task.story_points ?? 0) > 0 && <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, background: 'var(--surface-4)', color: 'var(--text-2)' }}>{task.story_points} pts</span>}
        {task.assignee_name && <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>👤 {task.assignee_name.split(' ')[0]}</span>}
      </div>

      {showMenu && (
        <div style={{ position: 'absolute', top: 0, right: 0, background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8, zIndex: 10, minWidth: 160, boxShadow: '0 8px 24px #00000060' }}>
          <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', padding: '4px 8px', marginBottom: 4, textTransform: 'uppercase' }}>Cambiar estado</div>
          {Object.entries(TASK_STATUS_CFG).map(([status, { label, color }]) => (
            <button key={status} onClick={() => { onStatusChange?.(task.id, status); setShowMenu(false) }}
              style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 8px', background: task.status === status ? color + '20' : 'transparent', border: 'none', borderRadius: 6, color: task.status === status ? color : 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
              {label}
            </button>
          ))}
          {onMoveToBacklog && (
            <>
              <div style={{ height: 1, background: 'var(--surface-4)', margin: '6px 0' }} />
              <button onClick={() => openConfirmGlobal({ message: '¿Mover esta tarea al backlog?', onConfirm: () => { onMoveToBacklog(task.id); setShowMenu(false) }, danger: true })}
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 8px', background: 'transparent', border: 'none', borderRadius: 6, color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                {t('sprints.mover_al_backlog')}
              </button>
            </>
          )}
          <button onClick={() => setShowMenu(false)}
            style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 8px', background: 'transparent', border: 'none', borderRadius: 6, color: 'var(--text-3)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
            Cerrar
          </button>
        </div>
      )}
    </div>
  )
}

// ── Sprint Kanban ──────────────────────────────────────────────────────────────
function SprintKanban({ sprint, onStatusChange, onMoveToBacklog }: { sprint: Sprint; onStatusChange?: (taskId: string, status: string) => void; onMoveToBacklog?: (taskId: string) => void }) {
  const columns = [
    { key: 'todo',        label: 'Por hacer' },
    { key: 'in_progress', label: 'En progreso' },
    { key: 'in_review',   label: 'En revisión' },
    { key: 'done',        label: 'Hecho' },
  ]
  const tasks = sprint.tasks || []

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
      {columns.map(col => {
        const colTasks = tasks.filter((t: Task) => t.status === col.key)
        const cfg = TASK_STATUS_CFG[col.key]
        return (
          <div key={col.key}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, padding: '6px 10px', background: cfg.color + '15', borderRadius: 8 }}>
              <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: cfg.color }}>{col.label}</span>
              <span style={{ fontSize: "var(--text-xs)", color: cfg.color }}>{colTasks.length}</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minHeight: 60 }}>
              {colTasks.map(task => (
                <TaskCard key={task.id} task={task} onStatusChange={onStatusChange} onMoveToBacklog={onMoveToBacklog} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Burndown Chart ─────────────────────────────────────────────────────────────
function BurndownChart({ sprintId, projectId }: { sprintId: string; projectId: string }) {
  const t = useAppT()
  const { data, isLoading } = useQuery<{ burndown?: unknown[] }>({
    queryKey: ['burndown', sprintId],
    queryFn: () => projectSprintsApi.burndown(projectId, sprintId).then(r => r.data),
    enabled: !!sprintId,
  })
  if (isLoading) return <Spinner />
  const points = data?.burndown || []
  if (points.length < 2) return <div style={{ textAlign: 'center', color: 'var(--text-3)', padding: 20 }}>{t('sprints.sin_suficientes_datos_aun')}</div>

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={points} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
        <XAxis dataKey="date" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
        <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
        <Tooltip contentStyle={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-xs)" }} />
        <Line type="monotone" dataKey="ideal" stroke="var(--surface-4)" strokeWidth={1.5} strokeDasharray="6 3" dot={false} name="Ideal" />
        <Line type="monotone" dataKey="remaining" stroke="#4f8ef7" strokeWidth={2.5} dot={{ r: 3 }} name="Restante" />
      </LineChart>
    </ResponsiveContainer>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function SprintsPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  useInvalidate()
  useAuth()
  const [selectedProject, setSelectedProject] = useState('')
  const [activeView, setActiveView] = useState('board') // board | backlog | velocity
  const [showCreateSprint, setShowCreateSprint] = useState(false)

  // Atajos de teclado: Ctrl+S = nuevo sprint
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's' && !e.shiftKey) {
        e.preventDefault()
        setShowCreateSprint(true)
      }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])
  const [showAddTasks, setShowAddTasks] = useState<string | false>(false)
  const [showRetro, setShowRetro] = useState<Sprint | null>(null)
  const [sprintForm, setSprintForm] = useState({ name: '', goal: '', start_date: '', end_date: '' })
  const [_retroForm, _setRetroForm] = useState({ went_well: '', to_improve: '', action_items: '' })

  const { data: projRaw = [] } = useQuery<{ id: string; code?: string; name?: string }[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })
  const projects = Array.isArray(projRaw) ? projRaw : []

  const { data: sprintsRaw = [], isLoading } = useQuery<Sprint[]>({
    queryKey: ['sprints', selectedProject],
    queryFn: () => projectSprintsApi.list(selectedProject).then(r => r.data),
    enabled: !!selectedProject,
  })
  const sprints: Sprint[] = Array.isArray(sprintsRaw) ? sprintsRaw : []
  const activeSprint = sprints.find((s: Sprint) => s.status === 'active')
  const planningSprints = sprints.filter((s: Sprint) => s.status === 'planning')
  const completedSprints = sprints.filter((s: Sprint) => s.status === 'completed')

  const { data: backlog = [] } = useQuery<Task[]>({
    queryKey: ['backlog', selectedProject],
    queryFn: () => projectSprintsApi.backlog(selectedProject).then(r => r.data),
    enabled: !!selectedProject,
  })

  const { data: velocity } = useQuery<{ avg_velocity?: number; sprints?: { sprint: string; name: string; planned: number; completed: number }[] }>({
    queryKey: ['velocity', selectedProject],
    queryFn: () => projectSprintsApi.velocity(selectedProject).then(r => r.data),
    enabled: !!selectedProject && activeView === 'velocity',
  })

  const inv = (keys: string[]) => {
    keys.forEach((k: string) => qc.invalidateQueries({ queryKey: [k, selectedProject] }))
    qc.invalidateQueries({ queryKey: ['cal-sprints'] })
    if (keys.includes('sprints') || keys.includes('backlog')) {
      qc.invalidateQueries({ queryKey: ['dash-my-tasks'] })
    }
  }

  const { mutate: createSprint, isPending: creatingS } = useMutation({
    mutationFn: (d: typeof sprintForm) => projectSprintsApi.create(selectedProject, d),
    onSuccess: () => { inv(['sprints']); setShowCreateSprint(false); setSprintForm({ name: '', goal: '', start_date: '', end_date: '' }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: startSprint } = useMutation({
    mutationFn: (id: string) => projectSprintsApi.start(selectedProject, id),
    onSuccess: () => inv(['sprints']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: closeSprint } = useMutation({
    mutationFn: (id: string) => projectSprintsApi.close(selectedProject, id),
    onSuccess: () => inv(['sprints', 'backlog']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: _updateSprint } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: unknown }) => projectSprintsApi.update(selectedProject, id, data),
    onSuccess: () => inv(['sprints']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: addTasksToSprint } = useMutation({
    mutationFn: ({ sprintId, taskIds }: { sprintId: string; taskIds: string[] }) => projectSprintsApi.addTasks(selectedProject, sprintId, taskIds),
    onSuccess: () => { inv(['sprints', 'backlog']); setShowAddTasks(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: removeTask } = useMutation({
    mutationFn: ({ sprintId, taskId }: { sprintId: string; taskId: string }) => projectSprintsApi.removeTask(selectedProject, sprintId, taskId),
    onSuccess: () => inv(['sprints', 'backlog']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: updateTaskStatus } = useMutation({
    mutationFn: ({ taskId, status }: { taskId: string; status: string }) => tasksApi.update(taskId, { status } as Parameters<typeof tasksApi.update>[1]),
    onSuccess: () => inv(['sprints']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [selectedBacklogTasks, setSelectedBacklogTasks] = useState<string[]>([])

  return (
    <PageShell>
      <PageHeader
        title={t('sprints.title')}
        subtitle={t('sprints.subtitle')}
        icon={<RefreshCw size={18} />}
        showListExport={Boolean(selectedProject && activeView !== 'velocity')}
        exportFilePrefix='sprints'
      />

      {/* Project selector */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, alignItems: 'center' }}>
        <select value={selectedProject} onChange={e => { setSelectedProject(e.target.value); setActiveView('board') }}
          style={{ ...fs, width: 300 }}>
          <option value="">{t('sprints.selecciona_un_proyecto')}</option>
          {projects.map((p: { id: string; code?: string; name?: string }) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
        {selectedProject && (
          <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
            {['board','backlog','velocity'].map(v => (
              <button key={v} onClick={() => setActiveView(v)}
                style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${activeView === v ? 'var(--accent)' : 'var(--surface-4)'}`, background: activeView === v ? 'var(--accent-muted)' : 'transparent', color: activeView === v ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
                {v === 'board' ? '🎯 Tablero' : v === 'backlog' ? '📋 Backlog' : '📊 Velocidad'}
              </button>
            ))}
            <Button onClick={() => setShowCreateSprint(true)}>{t('sprints.nuevo_sprint')}</Button>
          </div>
        )}
      </div>

      {!selectedProject && (
        <EmptyState icon="⚡" title={t('sprints.selecciona_un_proyecto_2')} description="Elige un proyecto para gestionar sus sprints" />
      )}

      {selectedProject && isLoading && <Spinner />}

      {/* BOARD VIEW */}
      {selectedProject && !isLoading && activeView === 'board' && (
        <div>
          {/* Active sprint */}
          {activeSprint ? (
            <div style={{ marginBottom: 32 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: "var(--text-lg-em)", fontWeight: 800 }}>Sprint {activeSprint.number} — {activeSprint.name}</span>
                    <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: 'var(--accent-glow)', color: 'var(--accent)' }}>ACTIVO</span>
                    {activeSprint.days_remaining !== null && (
                      <span style={{ fontSize: "var(--text-sm)", color: activeSprint.days_remaining <= 2 ? 'var(--danger)' : 'var(--text-2)' }}>
                        {activeSprint.days_remaining > 0 ? `${activeSprint.days_remaining} días restantes` : '⚠ Vencido'}
                      </span>
                    )}
                  </div>
                  {activeSprint.goal && <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', fontStyle: 'italic' }}>🎯 {activeSprint.goal}</div>}
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>
                    {activeSprint.start_date} → {activeSprint.end_date} · {activeSprint.planned_points || 0} pts planificados · {activeSprint.completed_points || 0} completados
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <div style={{ textAlign: 'right' }}>
                    <BurndownChart sprintId={activeSprint.id} projectId={selectedProject} />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <Button onClick={() => setShowAddTasks(activeSprint.id)}>{t('sprints.anadir_tareas')}</Button>
                    <button onClick={() => setShowRetro(activeSprint)}
                      style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 14px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                      📝 Retro
                    </button>
                    <button onClick={() => { openConfirmGlobal({ message: '¿Cerrar este sprint? Las tareas incompletas volverán al backlog.', onConfirm: () => closeSprint(activeSprint.id), danger: true }) }}
                      style={{ background: 'none', border: '1px solid var(--success-border)', borderRadius: 8, padding: '7px 14px', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                      ✓ Cerrar sprint
                    </button>
                  </div>
                </div>
              </div>
              <SprintKanban
                sprint={activeSprint}
                onStatusChange={(taskId, status) => updateTaskStatus({ taskId, status })}
                onMoveToBacklog={(taskId) => removeTask({ sprintId: activeSprint.id, taskId })}
              />
            </div>
          ) : (
            <div style={{ background: 'var(--surface-2)', border: '1px dashed var(--surface-4)', borderRadius: 12, padding: '24px', marginBottom: 24, textAlign: 'center', color: 'var(--text-3)' }}>
              <div style={{ fontSize: "var(--text-3xl-em)", marginBottom: 8 }}>⚡</div>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-2)', marginBottom: 4 }}>{t('sprints.no_hay_sprint_activo')}</div>
              <div style={{ fontSize: "var(--text-base)" }}>{t('sprints.crea_un_sprint_y_pulsa_quot_iniciar')}</div>
            </div>
          )}

          {/* Planning sprints */}
          {planningSprints.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>{t('sprints.en_planificacion')}</div>
              {planningSprints.map(sprint => (
                <div key={sprint.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '16px 20px', marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <span style={{ fontSize: "var(--text-md-em)", fontWeight: 700 }}>Sprint {sprint.number} — {sprint.name}</span>
                      {sprint.goal && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 2 }}>🎯 {sprint.goal}</div>}
                      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 2 }}>
                        {sprint.start_date || 'Sin fecha'} → {sprint.end_date || 'Sin fecha'} · {sprint.task_count} tareas · {sprint.planned_points || 0} pts
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => setShowAddTasks(sprint.id)}
                        style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '6px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                        + Tareas
                      </button>
                      {!activeSprint && (
                        <button onClick={() => startSprint(sprint.id)}
                          style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border-strong)', borderRadius: 8, padding: '6px 14px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600 }}>
                          ▶ Iniciar sprint
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Completed sprints summary */}
          {completedSprints.length > 0 && (
            <div>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>Completados</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
                {completedSprints.map(s => (
                  <div key={s.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--success-border)', borderRadius: 10, padding: '12px 16px' }}>
                    <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 4 }}>Sprint {s.number} — {s.name}</div>
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{s.start_date} → {s.end_date}</div>
                    <div style={{ display: 'flex', gap: 12, marginTop: 8, fontSize: "var(--text-sm)" }}>
                      <span style={{ color: 'var(--success)' }}>✓ {s.completed_points || 0} pts</span>
                      <span style={{ color: 'var(--text-2)' }}>Velocidad: {s.velocity || '—'}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* BACKLOG VIEW */}
      {selectedProject && !isLoading && activeView === 'backlog' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700 }}>{t('sprints.backlog_del_proyecto')}{backlog.length} {t('sprints.tareas_sin_sprint')}</div>
          </div>
          {backlog.length === 0 ? (
            <EmptyState icon="✅" title="Backlog vacio" description="Todas las tareas estan asignadas a un sprint" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {backlog.map(task => {
                const selected = selectedBacklogTasks.includes(task.id)
                return (
                  <div key={task.id}
                    onClick={() => setSelectedBacklogTasks(prev => selected ? prev.filter(id => id !== task.id) : [...prev, task.id])}
                    role="button" tabIndex={0}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedBacklogTasks(prev => selected ? prev.filter(id => id !== task.id) : [...prev, task.id]) } }}
                    style={{ display: 'grid', gridTemplateColumns: '24px 80px 1fr 80px 80px 120px', gap: 12, padding: '10px 16px', background: selected ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${selected ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, alignItems: 'center', cursor: 'pointer' }}>
                    <input type="checkbox" checked={selected} readOnly style={{ cursor: 'pointer' }} />
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{task.code}</span>
                    <span style={{ fontSize: "var(--text-sm)", fontWeight: 500 }}>{task.title}</span>
                    <span style={{ fontSize: "var(--text-xs)", padding: '2px 6px', borderRadius: 4, background: (PRIORITY_COLOR[task.priority || ''] || 'var(--text-3)') + '20', color: PRIORITY_COLOR[task.priority || ''] || 'var(--text-3)', textAlign: 'center' }}>{task.priority}</span>
                    <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', textAlign: 'center' }}>{task.story_points || '—'} pts</span>
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{task.assignee_name || 'Sin asignar'}</span>
                  </div>
                )
              })}
            </div>
          )}
          {selectedBacklogTasks.length > 0 && planningSprints.length > 0 && (
            <div style={{ position: 'fixed', bottom: 24, right: 24, background: 'var(--surface-2)', border: '1px solid var(--accent-border-strong)', borderRadius: 12, padding: '12px 20px', display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 8px 32px #00000080' }}>
              <span style={{ fontSize: "var(--text-base)", color: 'var(--accent)', fontWeight: 600 }}>{selectedBacklogTasks.length} tareas seleccionadas</span>
              {planningSprints.map(s => (
                <button key={s.id} onClick={() => { addTasksToSprint({ sprintId: s.id, taskIds: selectedBacklogTasks }); setSelectedBacklogTasks([]) }}
                  style={{ background: 'var(--accent)', border: 'none', borderRadius: 8, padding: '8px 16px', color: '#000', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 700, fontSize: "var(--text-base)" }}>
                  → Sprint {s.number}
                </button>
              ))}
              <button onClick={() => setSelectedBacklogTasks([])}
                style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 12px', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: "var(--text-sm)" }}>
                Cancelar
              </button>
            </div>
          )}
        </div>
      )}

      {/* VELOCITY VIEW */}
      {selectedProject && !isLoading && activeView === 'velocity' && (
        <div>
          {!velocity || velocity.sprints?.length === 0 ? (
            <EmptyState icon="📊" title={t('sprints.sin_datos_de_velocidad')} description="Completa sprints para ver la evolucion de la velocidad del equipo" />
          ) : (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 28 }}>
                {[
                  { label: 'Velocidad media', value: `${velocity.avg_velocity} pts/sprint`, color: 'var(--accent)', icon: '⚡' },
                  { label: 'Sprints completados', value: velocity.sprints?.length || 0, color: 'var(--success)', icon: '✓' },
                  { label: 'Total puntos entregados', value: velocity.sprints?.reduce((s, x) => s + x.completed, 0) || 0, color: 'var(--purple)', icon: '🎯' },
                ].map(({ label, value, color, icon }) => (
                  <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '16px 20px' }}>
                    <div style={{ fontSize: "var(--text-xl-em)", marginBottom: 8 }}>{icon}</div>
                    <div style={{ fontSize: "var(--text-2xl-em)", fontWeight: 800, color }}>{value}</div>
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
                  </div>
                ))}
              </div>

              <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 24px' }}>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>{t('sprints.velocidad_por_sprint')}</div>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={velocity.sprints} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                    <XAxis dataKey="sprint" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} />
                    <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} />
                    <Tooltip contentStyle={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-sm)" }} />
                    <ReferenceLine y={velocity.avg_velocity} stroke="#4f8ef7" strokeDasharray="5 3" label={{ value: 'Media', fill: 'var(--accent)', fontSize: "var(--text-xs)" }} />
                    <Bar dataKey="planned" fill="var(--surface-4)" radius={[3, 3, 0, 0]} name="Planificado" />
                    <Bar dataKey="completed" fill="#4f8ef7" radius={[3, 3, 0, 0]} name="Completado" />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div style={{ marginTop: 20 }}>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>Retrospectivas</div>
                {velocity.sprints?.map(s => {
                  const sprint = completedSprints.find(x => x.name === s.name)
                  if (!sprint?.went_well && !sprint?.to_improve) return null
                  return (
                    <div key={s.sprint} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 18px', marginBottom: 10 }}>
                      <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>{s.sprint} — {s.name}</div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14, fontSize: "var(--text-sm)" }}>
                        {sprint?.went_well && <div><div style={{ color: 'var(--success)', fontWeight: 700, marginBottom: 4 }}>{t('sprints.que_fue_bien')}</div><div style={{ color: 'var(--text-2)' }}>{sprint.went_well}</div></div>}
                        {sprint?.to_improve && <div><div style={{ color: 'var(--warning)', fontWeight: 700, marginBottom: 4 }}>↑ A mejorar</div><div style={{ color: 'var(--text-2)' }}>{sprint.to_improve}</div></div>}
                        {sprint?.action_items && <div><div style={{ color: 'var(--accent)', fontWeight: 700, marginBottom: 4 }}>→ Acciones</div><div style={{ color: 'var(--text-2)' }}>{sprint.action_items}</div></div>}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Modal: Create Sprint */}
      {showCreateSprint && (
        <Modal open title={t('sprints.nuevo_sprint_2')} onClose={() => setShowCreateSprint(false)} width={500}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div><label style={ls}>{t('sprints.nombre_del_sprint')}</label><input value={sprintForm.name} onChange={e => setSprintForm(f => ({ ...f, name: e.target.value }))} style={fs} placeholder={t('sprints.nombre_del_sprint_2')} /></div>
            <div><label style={ls}>{t('sprints.objetivo_del_sprint')}</label><textarea value={sprintForm.goal} onChange={e => setSprintForm(f => ({ ...f, goal: e.target.value }))} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder={t('sprints.objetivo_del_sprint_2')} /></div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div><label style={ls}>Fecha inicio</label><input type="date" value={sprintForm.start_date} onChange={e => setSprintForm(f => ({ ...f, start_date: e.target.value }))} style={fs} /></div>
              <div><label style={ls}>Fecha fin</label><input type="date" value={sprintForm.end_date} onChange={e => setSprintForm(f => ({ ...f, end_date: e.target.value }))} style={fs} /></div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <Button variant="secondary" onClick={() => setShowCreateSprint(false)}>Cancelar</Button>
              <Button onClick={() => createSprint(sprintForm)} disabled={creatingS || !sprintForm.name}>{creatingS ? 'Creando...' : 'Crear sprint'}</Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Modal: Add tasks to sprint */}
      {showAddTasks && (
        <Modal open title={t('sprints.anadir_tareas_al_sprint')} onClose={() => setShowAddTasks(false)} width={600}>
          <div>
            {backlog.length === 0 ? (
              <EmptyState icon="✅" title="Backlog vacio" description="No hay tareas disponibles para anadir al sprint" />
            ) : (
              <>
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 14 }}>{t('sprints.selecciona_las_tareas_del_backlog_para_anadir')}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 360, overflowY: 'auto' }}>
                  {backlog.map(task => {
                    const sel = selectedBacklogTasks.includes(task.id)
                    return (
                      <label key={task.id} style={{ display: 'grid', gridTemplateColumns: '24px 80px 1fr 60px 100px', gap: 10, padding: '8px 12px', background: sel ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${sel ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, cursor: 'pointer', alignItems: 'center' }}>
                        <input type="checkbox" checked={sel} onChange={e => setSelectedBacklogTasks(prev => e.target.checked ? [...prev, task.id] : prev.filter(id => id !== task.id))} />
                        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{task.code}</span>
                        <span style={{ fontSize: "var(--text-sm)" }}>{task.title}</span>
                        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', textAlign: 'center' }}>{task.story_points || '—'}pt</span>
                        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{task.assignee_name?.split(' ')[0] || '—'}</span>
                      </label>
                    )
                  })}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
                  <span style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{selectedBacklogTasks.length} seleccionadas</span>
                  <div style={{ display: 'flex', gap: 10 }}>
                    <Button variant="secondary" onClick={() => setShowAddTasks(false)}>Cancelar</Button>
                    <Button onClick={() => { addTasksToSprint({ sprintId: showAddTasks || '', taskIds: selectedBacklogTasks }); setSelectedBacklogTasks([]) }} disabled={selectedBacklogTasks.length === 0}>
                      {t('sprints.anadir_al_sprint')}
                    </Button>
                  </div>
                </div>
              </>
            )}
          </div>
        </Modal>
      )}

      {/* Modal: Retrospective */}
      {showRetro && (
        <Modal open title={`🔍 Retrospectiva — ${showRetro.name}`} onClose={() => setShowRetro(null)} width={680}>
          <RetroModal sprint={showRetro} projectId={selectedProject} onClose={() => setShowRetro(null)} />
        </Modal>
      )}
    </PageShell>
  )
}
