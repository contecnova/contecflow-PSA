/**
 * KanbanAdvancedPage v2 — Production-quality Kanban
 *
 * vs v1: real card drag-and-drop (native mouse events) ·
 *   inline filter bar (priority / assignee / search / sprint) ·
 *   swimlanes rendered in board (group by assignee/epic/priority) ·
 *   quick-add per column · WIP utilization gauge · keyboard shortcuts ·
 *   card subtask count badge · assignee avatar · overdue indicator
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import type {} from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { tasksApi, projectsApi, sprintsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { LayoutGrid, History, X } from 'lucide-react'
import { Button, Spinner, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

// ── Constants ────────────────────────────────────────────────────────────────

type Translator = (k: string) => string

type Task = {
  [k: string]: unknown
  id: string
  status: string
  title?: string
  code?: string
  priority?: string
  due_date?: string
  assignee_id?: string
  assignee_name?: string
  assignee?: { username?: string; full_name?: string }
  assignee_name_full?: string
  subtask_count?: number
  done_subtask_count?: number
  story_points?: number
  sprint_id?: string
  epic_id?: string
  epic_name?: string
}

type Column = { id: string; label: string; color: string }

function getDefaultColumns(t: Translator): Column[] {
  return [
    { id: 'backlog',     label: t('kanban.col_backlog'),       color: 'var(--text-3)' },
    { id: 'todo',        label: t('kanban.col_todo'),          color: 'var(--accent)' },
    { id: 'in_progress', label: t('kanban.col_in_progress'),   color: '#4f8ef7' },
    { id: 'in_review',   label: t('kanban.col_in_review'),     color: '#f59e0b' },
    { id: 'done',        label: t('kanban.col_done'),          color: '#34d399' },
  ]
}

const PRIORITY_COLORS: Record<string, string> = { critical: '#f87171', high: 'var(--orange)', medium: '#f59e0b', low: '#34d399', none: 'var(--text-3)' }
function getPriorityLabels(t: Translator): Record<string, string> {
  return {
    critical: t('kanban.priority_critical'),
    high: t('kanban.priority_high'),
    medium: t('kanban.priority_medium'),
    low: t('kanban.priority_low'),
    none: t('kanban.priority_none'),
  }
}

function getPriority(t: Task): string { return t.priority || 'none' }
function getAssigneeLabel(t: Task): string {
  return (
    t?.assignee?.username ||
    t?.assignee?.full_name ||
    t?.assignee_name ||
    t?.assignee_id ||
    'Sin asignar'
  )
}
function fmtDate(s: string | undefined): string { return s ? s.slice(0, 10) : '' }
function isOverdue(t: Task): boolean {
  if (!t.due_date) return false
  if (['done', 'closed', 'cancelled'].includes(t.status)) return false
  return new Date(t.due_date) < new Date()
}

// ── WIP gauge ────────────────────────────────────────────────────────────────

function WipGauge({ count, limit }: { count: number; limit: number | undefined }) {
  if (!limit) return null
  const ratio = Math.min(count / limit, 1)
  const color  = ratio >= 1 ? '#f87171' : ratio > 0.75 ? '#f59e0b' : '#34d399'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
      <div style={{ flex: 1, height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.08)' }}>
        <div style={{ width: `${ratio * 100}%`, height: '100%', borderRadius: 2, background: color, transition: 'width 0.3s' }} />
      </div>
      <span style={{ fontSize: "var(--text-2xs)", color, fontWeight: 600 }}>{count}/{limit}</span>
    </div>
  )
}

// ── Kanban Card ───────────────────────────────────────────────────────────────

function KanbanCard({ task, onDragStart, onClick, priorityLabels }: {
  task: Task
  onDragStart: (e: React.MouseEvent, task: Task, onDragStarted: () => void) => void
  onClick: () => void
  priorityLabels: Record<string, string>
}) {
  const overdue    = isOverdue(task)
  const priColor   = PRIORITY_COLORS[getPriority(task)]
  const subtasks   = (task.subtask_count as number) || 0
  const done_sub   = (task.done_subtask_count as number) || 0
  const wasDragged = useRef(false)

  return (
    <div
      onMouseDown={e => {
        if (e.button !== 0) return
        wasDragged.current = false
        onDragStart(e, task, () => { wasDragged.current = true })
      }}
      onClick={() => { if (!wasDragged.current) onClick() }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } }}
      style={{
        background: 'var(--surface-2)',
        border: `1px solid ${overdue ? 'rgba(248,113,113,0.4)' : 'var(--surface-4)'}`,
        borderLeft: `3px solid ${priColor}`,
        borderRadius: 8,
        padding: '10px 12px',
        cursor: 'grab',
        userSelect: 'none',
        marginBottom: 8,
        transition: 'box-shadow 0.15s, border-color 0.15s',
      }}
      onMouseEnter={e => e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.25)'}
      onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}
    >
      {/* Title row */}
      <div style={{ fontSize: "var(--text-base)", color: overdue ? 'var(--danger)' : 'var(--text-1)', lineHeight: 1.4, marginBottom: 6 }}>
        {task.title}
      </div>

      {/* Meta row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        {/* Priority badge */}
        <span style={{
          fontSize: "var(--text-3xs)", fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em',
          color: priColor, background: priColor + '22', borderRadius: 4, padding: '2px 5px',
        }}>
          {priorityLabels[getPriority(task)]}
        </span>

        {/* Story points */}
        {(task.story_points ?? 0) > 0 && (
          <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', background: 'var(--surface-4)', borderRadius: 4, padding: '1px 5px' }}>
            {task.story_points}p
          </span>
        )}

        {/* Subtask badge */}
        {subtasks > 0 && (
          <span style={{ fontSize: "var(--text-2xs)", color: done_sub === subtasks ? '#34d399' : 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 2 }}>
            ⊞ {done_sub}/{subtasks}
          </span>
        )}

        {/* Due date */}
        {task.due_date && (
          <span style={{ fontSize: "var(--text-2xs)", color: overdue ? '#f87171' : 'var(--text-3)', marginLeft: 'auto' }}>
            {overdue ? '⚠ ' : ''}{fmtDate(task.due_date)}
          </span>
        )}

        {/* Assignee avatar */}
        {task.assignee_name && (
          <div style={{
            width: 20, height: 20, borderRadius: '50%',
            background: 'var(--accent-glow)', border: '1px solid var(--accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: "var(--text-3xs)", fontWeight: 700, color: 'var(--accent)', flexShrink: 0,
            marginLeft: task.due_date ? 4 : 'auto',
          }}>
            {task.assignee_name.slice(0, 1).toUpperCase()}
          </div>
        )}
      </div>

      {/* Code label */}
      {task.code && (
        <div style={{ fontSize: "var(--text-3xs)", color: 'var(--text-4)', marginTop: 5 }}>{task.code}</div>
      )}
    </div>
  )
}

// ── Quick-add inline form ────────────────────────────────────────────────────

function QuickAdd({ status, projectId, onCreated }: { status: string; projectId: string; onCreated: () => void }) {
  const [open, setOpen]   = useState(false)
  const [title, setTitle] = useState('')
  const inputRef          = useRef<HTMLInputElement | null>(null)
  const toast             = useToast()
  const t                 = useAppT()

  useEffect(() => { if (open) inputRef.current?.focus() }, [open])

  const submit = async () => {
    if (!title.trim()) return
    try {
      await tasksApi.create({ title: title.trim(), status, project_id: projectId || undefined } as any)
      setTitle('')
      setOpen(false)
      onCreated()
    } catch (e: unknown) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t('kanban.error_create_task'))
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={{
        width: '100%', textAlign: 'left', padding: '7px 10px',
        background: 'transparent', border: '1px dashed var(--surface-4)',
        borderRadius: 8, color: 'var(--text-3)', fontSize: "var(--text-sm)",
        cursor: 'pointer', fontFamily: 'var(--font-sans)',
      }}>
        + {t('kanban.add_task')}
      </button>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 4 }}>
      <input
        ref={inputRef}
        value={title}
        onChange={e => setTitle(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') { setOpen(false); setTitle('') } }}
        placeholder={t('kanban.add_task_placeholder')}
        style={{
          flex: 1, background: 'var(--surface-3)', border: '1px solid var(--accent)',
          borderRadius: 6, padding: '6px 8px', color: 'var(--text-1)',
          fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'var(--font-sans)',
        }}
      />
      <button onClick={submit} style={{ padding: '0 10px', background: 'var(--accent)', border: 'none', borderRadius: 6, color: '#fff', cursor: 'pointer', fontSize: "var(--text-base)" }}>✓</button>
      <button onClick={() => { setOpen(false); setTitle('') }} style={{ padding: '0 8px', background: 'var(--surface-4)', border: 'none', borderRadius: 6, color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-base)" }}>✕</button>
    </div>
  )
}

// ── Column ───────────────────────────────────────────────────────────────────

type TaskDragStart = (e: React.MouseEvent, task: Task, onDragStarted: () => void) => void

function KanbanColumn({ col, tasks, dragOver, wipLimit, projectId, onTaskDragStart, onColumnEnter, onColumnLeave, onTaskClick, onCreated, priorityLabels }: {
  col: Column
  tasks: Task[]
  dragOver: boolean
  wipLimit: number | undefined
  projectId: string
  onTaskDragStart: TaskDragStart
  onColumnEnter: () => void
  onColumnLeave: () => void
  onTaskClick: (t: Task) => void
  onCreated: () => void
  priorityLabels: Record<string, string>
}) {
  const count = tasks.length
  const over  = dragOver

  return (
    <div
      onPointerEnter={onColumnEnter}
      onPointerLeave={onColumnLeave}
      style={{
        minWidth: 240, maxWidth: 300, flex: '1 1 240px',
        display: 'flex', flexDirection: 'column',
        background: over ? 'rgba(79,142,247,0.06)' : 'var(--surface-1)',
        borderRadius: 12, border: `1px solid ${over ? 'rgba(79,142,247,0.35)' : 'var(--surface-4)'}`,
        padding: 12, transition: 'background 0.15s, border-color 0.15s',
        minHeight: 120,
      }}
    >
      {/* Column header */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <div style={{ width: 9, height: 9, borderRadius: '50%', background: col.color, flexShrink: 0 }} />
          <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-1)', letterSpacing: '.03em', flex: 1 }}>{col.label}</span>
          <span style={{
            fontSize: "var(--text-xs)", fontWeight: 600, color: wipLimit && count >= wipLimit ? '#f87171' : 'var(--text-3)',
            background: 'var(--surface-3)', borderRadius: 10, padding: '1px 7px',
          }}>{count}</span>
        </div>
        <WipGauge count={count} limit={wipLimit} />
      </div>

      {/* Cards */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 40 }}>
        {tasks.map((t: Task) => (
          <KanbanCard key={t.id} task={t} onDragStart={onTaskDragStart} onClick={() => onTaskClick(t)} priorityLabels={priorityLabels} />
        ))}
      </div>

      {/* Quick-add */}
      <div style={{ marginTop: 8 }}>
        <QuickAdd status={col.id} projectId={projectId} onCreated={onCreated} />
      </div>
    </div>
  )
}

// ── Swimlane row ─────────────────────────────────────────────────────────────

function SwimlaneRow({ label, tasks, columns, dragOverCol, wipLimits, projectId, projectSuffix,
  onTaskDragStart, onColumnEnter, onColumnLeave, onTaskClick, onCreated, priorityLabels }: {
  label: string
  tasks: Task[]
  columns: Column[]
  dragOverCol: string | null
  wipLimits: Record<string, number>
  projectId: string
  projectSuffix: string
  onTaskDragStart: TaskDragStart
  onColumnEnter: (colId: string, swLane: string) => void
  onColumnLeave: () => void
  onTaskClick: (t: Task) => void
  onCreated: () => void
  priorityLabels: Record<string, string>
}) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{
        fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--accent)', textTransform: 'uppercase',
        letterSpacing: '.07em', padding: '6px 0 8px', borderBottom: '1px solid var(--surface-4)', marginBottom: 12,
      }}>
        {label}
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', overflowX: 'auto', paddingBottom: 4 }}>
        {columns.map((col: Column) => (
          <KanbanColumn
            key={col.id}
            col={col}
            tasks={tasks.filter((t: Task) => t.status === col.id)}
            dragOver={dragOverCol === col.id}
            wipLimit={wipLimits[col.id]}
            projectId={projectId}
            onTaskDragStart={onTaskDragStart}
            onColumnEnter={() => onColumnEnter(col.id, label + projectSuffix)}
            onColumnLeave={onColumnLeave}
            onTaskClick={onTaskClick}
            onCreated={onCreated}
            priorityLabels={priorityLabels}
          />
        ))}
      </div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

// Izado fuera del componente (auditoría 2026-08, P1-6): se creaba en cada
// render, así que añadirlo a las dependencias del useCallback habría roto la
// memoización en lugar de arreglarla. Es una constante, no estado.
const SENSITIVE_FROM = new Set(['done', 'cancelled'])

export default function KanbanAdvancedPage(): JSX.Element {
  const t           = useAppT()
  const toast       = useToast()
  const qc          = useQueryClient()
  const defaultColumns = useMemo(() => getDefaultColumns(t), [t])
  const priorityLabels = useMemo(() => getPriorityLabels(t), [t])

  const [projectId, setProjectId]       = useState('')
  const [search, setSearch]             = useState('')
  const [filterPriority, setFilterPri]  = useState<string[]>([])
  const [filterAssignee, setFilterAss]  = useState<string[]>([])
  const [sprintId, setSprintId]         = useState('')
  const [swimlaneBy, setSwimlaneBy]     = useState('none')   // none | assignee | priority | epic
  const [wipLimits, setWipLimits]       = useState<Record<string, number>>({})
  const [showSettings, setShowSettings] = useState(false)
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)   // task whose movement log is shown
  const searchRef = useRef<HTMLInputElement | null>(null)

  // drag state
  const dragTask       = useRef<Task | null>(null)
  const ghostRef       = useRef<HTMLDivElement | null>(null)
  const dropTargetRef  = useRef<{ colId: string; swLane: string } | null>(null)  // always-current ref companion to state
  const [dropTarget, setDropTarget] = useState<{ colId: string; swLane: string } | null>(null)  // { colId, swimlane }

  // ── data ──────────────────────────────────────────────────────────────────
  const { data: projects = [] } = useQuery<any[]>({
    queryKey: ['projects'],
    queryFn:  () => projectsApi.list().then(r => r.data),
  })

  const { data: rawTasks = [], isLoading } = useQuery<Task[]>({
    queryKey: ['kanban-tasks', projectId],
    queryFn:  () => tasksApi.list({ page_size: 500, ...(projectId ? { project_id: projectId } : {}) })
      .then(r => Array.isArray(r.data) ? r.data : ((r.data as any)?.items || [])),
    staleTime: 15000,
  })

  const { data: sprints = [] } = useQuery<any[]>({
    queryKey: ['sprints', projectId],
    queryFn:  () => {
      if (!projectId) return []
      return sprintsApi.list(projectId, undefined)
        .then(r => Array.isArray(r.data) ? r.data : ((r.data as any)?.items || []))
        .catch(() => [])
    },
    staleTime: 30000,
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status, move_reason }: { id: string; status: string; move_reason?: string }) =>
      tasksApi.update(id, { status, ...(move_reason ? { move_reason } : {}) } as any),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['kanban-tasks'] }),
    onError:    (e: unknown) => toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t('kanban.error_move_task')),
  })

  const requestStatusChange = useCallback((id: string, fromStatus: string, toStatus: string) => {
    if (fromStatus === toStatus) return
    let move_reason
    if (SENSITIVE_FROM.has(fromStatus)) {
      move_reason = window.prompt(
        `Vas a reabrir/mover una tarea desde "${fromStatus}". Indica el motivo (queda registrado en el log):`,
        ''
      )
      if (move_reason === null) return // user cancelled
      move_reason = move_reason.trim() || undefined
    }
    updateStatus({ id, status: toStatus, move_reason })
  }, [updateStatus])

  // ── Native drag-and-drop ───────────────────────────────────────────────────
  const cleanupGhost = useCallback(() => {
    if (ghostRef.current) {
      ghostRef.current.remove()
      ghostRef.current = null
    }
  }, [])

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest('input,textarea,select')) return
      if (e.key === '/' || e.key === 'f') { e.preventDefault(); searchRef.current?.focus() }
      if (e.key === 'Escape') { setDropTarget(null); cleanupGhost() }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [cleanupGhost])

  // ── Filtering ──────────────────────────────────────────────────────────────
  const tasks = useMemo(() => rawTasks.filter((t: Task) => {
    if (search && !t.title?.toLowerCase().includes(search.toLowerCase())) return false
    if (filterPriority.length && !filterPriority.includes(getPriority(t))) return false
    if (filterAssignee.length && !filterAssignee.includes(t.assignee_id ?? '')) return false
    if (sprintId && t.sprint_id !== sprintId) return false
    return true
  }), [rawTasks, search, filterPriority, filterAssignee, sprintId])

  const assignees = useMemo(() => {
    const seen = new Map()
    for (const t of rawTasks) {
      if (t.assignee_id && !seen.has(t.assignee_id)) seen.set(t.assignee_id, getAssigneeLabel(t))
    }
    return [...seen.entries()].map(([id, name]) => ({ id, name }))
  }, [rawTasks])

  // ── Swimlane grouping ──────────────────────────────────────────────────────
  const swimlanes = useMemo((): { id: string; label: string; tasks: Task[] }[] => {
    if (swimlaneBy === 'none') return [{ id: 'all', label: 'all', tasks }]
    if (swimlaneBy === 'assignee') {
      const groups: Record<string, { id: string; label: string; tasks: Task[] }> = {}
      for (const t of tasks) {
        const key = t.assignee_id || '__unassigned'
        const lbl = t.assignee_id ? getAssigneeLabel(t) : 'Sin asignar'
        if (!groups[key]) groups[key] = { id: key, label: lbl, tasks: [] }
        groups[key].tasks.push(t)
      }
      return Object.values(groups)
    }
    if (swimlaneBy === 'priority') {
      const order = ['critical', 'high', 'medium', 'low', 'none']
      const groups: Record<string, { id: string; label: string; tasks: Task[] }> = {}
      for (const t of tasks) {
        const key = getPriority(t)
        if (!groups[key]) groups[key] = { id: key, label: priorityLabels[key], tasks: [] }
        groups[key].tasks.push(t)
      }
      return order.filter(k => groups[k]).map(k => groups[k])
    }
    if (swimlaneBy === 'epic') {
      const groups: Record<string, { id: string; label: string; tasks: Task[] }> = {}
      for (const t of tasks) {
        const key = t.epic_id || '__none'
        const lbl = t.epic_name || 'Sin épica'
        if (!groups[key]) groups[key] = { id: key, label: lbl, tasks: [] }
        groups[key].tasks.push(t)
      }
      return Object.values(groups)
    }
    return [{ id: 'all', label: 'all', tasks }]
  }, [tasks, swimlaneBy, priorityLabels])

  const handleTaskDragStart = useCallback((e: React.MouseEvent, task: Task, onDragStarted: () => void) => {
    const startX = e.clientX
    const startY = e.clientY
    let dragging = false

    const onMove = (ev: MouseEvent) => {
      if (!dragging) {
        const dx = ev.clientX - startX
        const dy = ev.clientY - startY
        if (Math.sqrt(dx * dx + dy * dy) < 5) return
        // Threshold crossed — initialise the real drag
        dragging = true
        dragTask.current = task
        onDragStarted()

        const ghost = document.createElement('div')
        ghost.textContent = task.title!
        Object.assign(ghost.style, {
          position: 'fixed', zIndex: 'var(--z-drag)', pointerEvents: 'none',
          background: 'var(--surface-1)', border: '1px solid var(--accent)',
          borderRadius: '8px', padding: '8px 12px',
          color: '#e8f0fe', fontSize: '12px', fontFamily: 'var(--font-sans)',
          maxWidth: '220px', boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
          opacity: '0.9',
          left: ev.clientX + 12 + 'px',
          top:  ev.clientY + 12 + 'px',
        })
        document.body.appendChild(ghost)
        ghostRef.current = ghost
      } else {
        if (ghostRef.current) {
          ghostRef.current.style.left = ev.clientX + 12 + 'px'
          ghostRef.current.style.top  = ev.clientY + 12 + 'px'
        }
      }
    }

    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      cleanupGhost()
      if (dragging) {
        // Use ref instead of closure-captured state to always get the latest target
        const target = dropTargetRef.current
        if (dragTask.current && target) {
          const { colId } = target
          if (dragTask.current.status !== colId) {
            requestStatusChange(dragTask.current.id, dragTask.current.status, colId)
          }
        }
      }
      dragTask.current = null
      dropTargetRef.current = null
      setDropTarget(null)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [requestStatusChange, cleanupGhost])

  const handleColumnEnter = useCallback((colId: string, swLane: string) => {
    dropTargetRef.current = { colId, swLane }  // update ref synchronously
    setDropTarget({ colId, swLane })
  }, [])
  const handleColumnLeave = useCallback(() => {
    // don't clear here — let column enter override
  }, [])

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 52px)', background: 'var(--surface-0)', maxWidth: 'var(--page-max-w)', width: '100%' }}>
      {/* Header */}
      <div style={{ padding: '16px 32px 8px', flexShrink: 0 }}>
        <PageHeader
        icon={<LayoutGrid size={18} />}
          title={t('kanban.title')}
          subtitle={t('kanban.subtitle')}
          actions={
            <Button size="sm" variant="subtle" onClick={() => setShowSettings(s => !s)}>
              ⚙ {t('kanban.settings_btn')}
            </Button>
          }
        showListExport={false}
        />
      </div>

      {/* Filter bar */}
      <div style={{ padding: '0 32px 12px', display: 'flex', gap: 8, flexWrap: 'wrap', flexShrink: 0, alignItems: 'center' }}>
        <input
          ref={searchRef}
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={t('kanban.search_placeholder')}
          style={{
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 8, padding: '5px 10px', color: 'var(--text-1)',
            fontSize: "var(--text-sm)", outline: 'none', width: 160, fontFamily: 'var(--font-sans)',
          }}
        />

        {/* Priority chips */}
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          {['critical', 'high', 'medium', 'low'].map(p => {
            const active = filterPriority.includes(p)
            return (
              <button key={p} onClick={() => setFilterPri(prev => active ? prev.filter(x => x !== p) : [...prev, p])} style={{
                padding: '3px 9px', borderRadius: 12, cursor: 'pointer',
                border: `1px solid ${active ? PRIORITY_COLORS[p] : 'var(--surface-4)'}`,
                background: active ? PRIORITY_COLORS[p] + '22' : 'transparent',
                color: active ? PRIORITY_COLORS[p] : 'var(--text-3)',
                fontSize: "var(--text-xs)", fontFamily: 'var(--font-sans)', fontWeight: active ? 600 : 400,
              }}>
                {priorityLabels[p]}
              </button>
            )
          })}
          {filterPriority.length > 0 && (
            <button onClick={() => setFilterPri([])} style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer' }}>✕</button>
          )}
        </div>

        {/* Assignee chips */}
        {assignees.slice(0, 6).map(({ id, name }) => {
          const active = filterAssignee.includes(id)
          return (
            <button key={id} onClick={() => setFilterAss(prev => active ? prev.filter(x => x !== id) : [...prev, id])} style={{
              padding: '3px 8px', borderRadius: 12, cursor: 'pointer',
              border: `1px solid ${active ? 'var(--accent)' : 'var(--surface-4)'}`,
              background: active ? 'var(--accent-muted)' : 'transparent',
              color: active ? 'var(--accent)' : 'var(--text-3)',
              fontSize: "var(--text-xs)", fontFamily: 'var(--font-sans)',
            }}>
              {name.split(' ')[0]}
            </button>
          )
        })}

        {/* Sprint select */}
        {sprints.length > 0 && (
          <select value={sprintId} onChange={e => setSprintId(e.target.value)} style={{
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 8, padding: '5px 8px', color: 'var(--text-1)',
            fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'var(--font-sans)',
          }}>
            <option value="">{t('kanban.all_sprints')}</option>
            {sprints.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}

        {/* Project selector */}
        <select value={projectId} onChange={e => setProjectId(e.target.value)} style={{
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '5px 8px', color: 'var(--text-1)',
          fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'var(--font-sans)', marginLeft: 'auto',
        }}>
          <option value="">{t('kanban.all_projects')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>

        {/* Swimlane selector */}
        <select value={swimlaneBy} onChange={e => setSwimlaneBy(e.target.value)} style={{
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '5px 8px', color: 'var(--text-1)',
          fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'var(--font-sans)',
        }}>
          <option value="none">{t('kanban.no_swimlanes')}</option>
          <option value="assignee">{t('kanban.swimlane_assignee')}</option>
          <option value="priority">{t('kanban.swimlane_priority')}</option>
          <option value="epic">{t('kanban.swimlane_epic')}</option>
        </select>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div style={{ padding: '12px 32px', background: 'var(--surface-1)', borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', marginBottom: 10 }}>{t('kanban.wip_limits')}</div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {defaultColumns.map(col => (
              <div key={col.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: col.color }} />
                <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', width: 90 }}>{col.label}</span>
                <input
                  type="number" min={0} max={50}
                  value={wipLimits[col.id] || ''}
                  placeholder={t('kanban.wip_limit_placeholder')}
                  onChange={e => setWipLimits(prev => ({ ...prev, [col.id]: e.target.value ? parseInt(e.target.value) : 0 }))}
                  style={{
                    width: 50, background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                    borderRadius: 6, padding: '4px 7px', color: 'var(--text-1)',
                    fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'var(--font-sans)', textAlign: 'center',
                  }}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Board */}
      {isLoading ? (
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <Spinner size={32} />
        </div>
      ) : rawTasks.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <EmptyState icon="📋" title={t('kanban.empty_title')} description={t('kanban.empty_desc')} />
        </div>
      ) : (
        <div style={{ flex: 1, overflow: 'auto', padding: '0 32px 24px' }}>
          {swimlanes.map(lane => (
            swimlaneBy === 'none' ? (
              <div key={lane.id} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', paddingTop: 4 }}>
                {defaultColumns.map(col => (
                  <KanbanColumn
                    key={col.id}
                    col={col}
                    tasks={lane.tasks.filter(t => t.status === col.id)}
                    dragOver={dropTarget?.colId === col.id}
                    wipLimit={wipLimits[col.id]}
                    projectId={projectId}
                    onTaskDragStart={handleTaskDragStart}
                    onColumnEnter={() => handleColumnEnter(col.id, 'all')}
                    onColumnLeave={handleColumnLeave}
                    onTaskClick={t => setSelectedTask(t)}
                    onCreated={() => qc.invalidateQueries({ queryKey: ['kanban-tasks'] })}
                    priorityLabels={priorityLabels}
                  />
                ))}
              </div>
            ) : (
              <SwimlaneRow
                key={lane.id}
                label={lane.label}
                tasks={lane.tasks}
                columns={defaultColumns}
                dragOverCol={(dropTarget as any)?.swimlane === lane.label + projectId ? (dropTarget?.colId ?? null) : null}
                wipLimits={wipLimits}
                projectId={projectId}
                projectSuffix={projectId}
                onTaskDragStart={handleTaskDragStart}
                onColumnEnter={(colId) => handleColumnEnter(colId, lane.label + projectId)}
                onColumnLeave={handleColumnLeave}
                onTaskClick={t => setSelectedTask(t)}
                onCreated={() => qc.invalidateQueries({ queryKey: ['kanban-tasks'] })}
                priorityLabels={priorityLabels}
              />
            )
          ))}
        </div>
      )}

      {/* Movement log drawer */}
      {selectedTask && (
        <TaskMovementLogDrawer task={selectedTask} onClose={() => setSelectedTask(null)} />
      )}
    </div>
  )
}

// ── Movement Log Drawer ───────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  backlog: 'var(--text-3)', todo: 'var(--accent)', in_progress: '#4f8ef7',
  in_review: '#f59e0b', done: '#34d399', cancelled: '#f87171', blocked: '#fb923c',
}

function StatusBadge({ status }: { status: string | undefined }) {
  const color = STATUS_COLORS[status || ''] || 'var(--text-3)'
  return (
    <span style={{
      display: 'inline-block', padding: '1px 8px', borderRadius: 10,
      fontSize: 'var(--text-2xs)', fontWeight: 700, color,
      background: `${color}18`, border: `1px solid ${color}44`,
      textTransform: 'uppercase', letterSpacing: '0.04em',
    }}>{status?.replace('_', ' ')}</span>
  )
}

function TaskMovementLogDrawer({ task, onClose }: { task: Task; onClose: () => void }) {
  const { data: log = [], isLoading } = useQuery<any[]>({
    queryKey: ['task-movement-log', task.id],
    queryFn: () => tasksApi.movementLog(task.id).then(r => (r.data as any)?.items ?? r.data ?? []),
    staleTime: 0,
    retry: false,
  })

  return (
    <div style={{
      position: 'fixed', top: 12, right: 12, width: 380, maxWidth: 'calc(100vw - 24px)', maxHeight: 'calc(100vh - 24px)',
      background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12,
      zIndex: 'var(--z-modal, 1000)', display: 'flex', flexDirection: 'column',
      overflow: 'hidden', boxShadow: '-4px 0 24px rgba(0,0,0,0.35)',
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px', borderBottom: '1px solid var(--surface-4)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <History size={16} color="var(--accent)" />
          <span style={{ fontWeight: 700, fontSize: 'var(--text-base)', color: 'var(--text-1)' }}>Historial</span>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', padding: 4, borderRadius: 4, display: 'flex', alignItems: 'center' }}>
          <X size={16} />
        </button>
      </div>

      {/* Task title */}
      <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{task.code}</div>
        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)', lineHeight: 1.4 }}>{task.title}</div>
      </div>

      {/* Log entries */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 20px' }}>
        {isLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><Spinner /></div>
        ) : log.length === 0 ? (
          <div style={{ color: 'var(--text-3)', fontSize: 'var(--text-sm)', textAlign: 'center', paddingTop: 40 }}>Sin movimientos registrados</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {log.map((entry, i) => (
              <div key={entry.id} style={{ position: 'relative', paddingLeft: 24, paddingBottom: i < log.length - 1 ? 20 : 0 }}>
                {/* Timeline line */}
                {i < log.length - 1 && (
                  <div style={{ position: 'absolute', left: 7, top: 18, bottom: 0, width: 2, background: 'var(--surface-4)' }} />
                )}
                {/* Dot */}
                <div style={{
                  position: 'absolute', left: 2, top: 6, width: 12, height: 12,
                  borderRadius: '50%', background: STATUS_COLORS[entry.to_status] || 'var(--accent)',
                  border: '2px solid var(--surface-1)',
                }} />
                {/* Content */}
                <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
                    {entry.from_status && <StatusBadge status={entry.from_status} />}
                    {entry.from_status && <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>→</span>}
                    <StatusBadge status={entry.to_status} />
                  </div>
                  {entry.reason && (
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', fontStyle: 'italic', marginBottom: 4 }}>
                      &ldquo;{entry.reason}&rdquo;
                    </div>
                  )}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>
                      {entry.moved_by?.username || entry.moved_by?.full_name || 'Sistema'}
                    </span>
                    <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>
                      {new Date(entry.moved_at).toLocaleString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
