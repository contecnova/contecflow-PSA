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
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import api, { projectsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Button, Spinner, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

// ── Constants ────────────────────────────────────────────────────────────────

function getDefaultColumns(t) {
  return [
    { id: 'backlog',     label: t('kanban.col_backlog'),       color: '#4a5a78' },
    { id: 'todo',        label: t('kanban.col_todo'),          color: '#6366f1' },
    { id: 'in_progress', label: t('kanban.col_in_progress'),   color: '#4f8ef7' },
    { id: 'in_review',   label: t('kanban.col_in_review'),     color: '#f59e0b' },
    { id: 'done',        label: t('kanban.col_done'),          color: '#34d399' },
  ]
}

const PRIORITY_COLORS = { critical: '#f87171', high: '#fb923c', medium: '#f59e0b', low: '#34d399', none: '#4a5a78' }
function getPriorityLabels(t) {
  return {
    critical: t('kanban.priority_critical'),
    high: t('kanban.priority_high'),
    medium: t('kanban.priority_medium'),
    low: t('kanban.priority_low'),
    none: t('kanban.priority_none'),
  }
}

function getPriority(t) { return t.priority || 'none' }
function fmtDate(s) { return s ? s.slice(0, 10) : '' }
function isOverdue(t) {
  if (!t.due_date) return false
  if (['done', 'closed', 'cancelled'].includes(t.status)) return false
  return new Date(t.due_date) < new Date()
}

// ── WIP gauge ────────────────────────────────────────────────────────────────

function WipGauge({ count, limit }) {
  if (!limit) return null
  const ratio = Math.min(count / limit, 1)
  const color  = ratio >= 1 ? '#f87171' : ratio > 0.75 ? '#f59e0b' : '#34d399'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
      <div style={{ flex: 1, height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.08)' }}>
        <div style={{ width: `${ratio * 100}%`, height: '100%', borderRadius: 2, background: color, transition: 'width 0.3s' }} />
      </div>
      <span style={{ fontSize: 10, color, fontWeight: 600 }}>{count}/{limit}</span>
    </div>
  )
}

// ── Kanban Card ───────────────────────────────────────────────────────────────

function KanbanCard({ task, onDragStart, onClick, priorityLabels }) {
  const overdue    = isOverdue(task)
  const priColor   = PRIORITY_COLORS[getPriority(task)]
  const subtasks   = task.subtask_count || 0
  const done_sub   = task.done_subtask_count || 0
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
      <div style={{ fontSize: 13, color: overdue ? '#fca5a5' : 'var(--text-1)', lineHeight: 1.4, marginBottom: 6 }}>
        {task.title}
      </div>

      {/* Meta row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        {/* Priority badge */}
        <span style={{
          fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em',
          color: priColor, background: priColor + '22', borderRadius: 4, padding: '2px 5px',
        }}>
          {priorityLabels[getPriority(task)]}
        </span>

        {/* Story points */}
        {task.story_points > 0 && (
          <span style={{ fontSize: 10, color: 'var(--text-3)', background: 'var(--surface-4)', borderRadius: 4, padding: '1px 5px' }}>
            {task.story_points}p
          </span>
        )}

        {/* Subtask badge */}
        {subtasks > 0 && (
          <span style={{ fontSize: 10, color: done_sub === subtasks ? '#34d399' : 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 2 }}>
            ⊞ {done_sub}/{subtasks}
          </span>
        )}

        {/* Due date */}
        {task.due_date && (
          <span style={{ fontSize: 10, color: overdue ? '#f87171' : 'var(--text-3)', marginLeft: 'auto' }}>
            {overdue ? '⚠ ' : ''}{fmtDate(task.due_date)}
          </span>
        )}

        {/* Assignee avatar */}
        {task.assignee_name && (
          <div style={{
            width: 20, height: 20, borderRadius: '50%',
            background: 'var(--accent-glow)', border: '1px solid var(--accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 9, fontWeight: 700, color: 'var(--accent)', flexShrink: 0,
            marginLeft: task.due_date ? 4 : 'auto',
          }}>
            {task.assignee_name.slice(0, 1).toUpperCase()}
          </div>
        )}
      </div>

      {/* Code label */}
      {task.code && (
        <div style={{ fontSize: 9, color: 'var(--text-4)', marginTop: 5 }}>{task.code}</div>
      )}
    </div>
  )
}

// ── Quick-add inline form ────────────────────────────────────────────────────

function QuickAdd({ status, projectId, onCreated }) {
  const [open, setOpen]   = useState(false)
  const [title, setTitle] = useState('')
  const inputRef          = useRef(null)
  const toast             = useToast()
  const t                 = useAppT()

  useEffect(() => { if (open) inputRef.current?.focus() }, [open])

  const submit = async () => {
    if (!title.trim()) return
    try {
      await api.post('/tasks', { title: title.trim(), status, project_id: projectId || undefined })
      setTitle('')
      setOpen(false)
      onCreated()
    } catch (e) {
      toast.error(e?.response?.data?.detail || t('kanban.error_create_task'))
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={{
        width: '100%', textAlign: 'left', padding: '7px 10px',
        background: 'transparent', border: '1px dashed var(--surface-4)',
        borderRadius: 8, color: 'var(--text-3)', fontSize: 12,
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
          fontSize: 12, outline: 'none', fontFamily: 'var(--font-sans)',
        }}
      />
      <button onClick={submit} style={{ padding: '0 10px', background: 'var(--accent)', border: 'none', borderRadius: 6, color: '#fff', cursor: 'pointer', fontSize: 13 }}>✓</button>
      <button onClick={() => { setOpen(false); setTitle('') }} style={{ padding: '0 8px', background: 'var(--surface-4)', border: 'none', borderRadius: 6, color: 'var(--text-2)', cursor: 'pointer', fontSize: 13 }}>✕</button>
    </div>
  )
}

// ── Column ───────────────────────────────────────────────────────────────────

function KanbanColumn({ col, tasks, dragOver, wipLimit, projectId, onTaskDragStart, onColumnEnter, onColumnLeave, onTaskClick, onCreated, priorityLabels }) {
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
          <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '.03em', flex: 1 }}>{col.label}</span>
          <span style={{
            fontSize: 11, fontWeight: 600, color: wipLimit && count >= wipLimit ? '#f87171' : 'var(--text-3)',
            background: 'var(--surface-3)', borderRadius: 10, padding: '1px 7px',
          }}>{count}</span>
        </div>
        <WipGauge count={count} limit={wipLimit} />
      </div>

      {/* Cards */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 40 }}>
        {tasks.map(t => (
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
  onTaskDragStart, onColumnEnter, onColumnLeave, onTaskClick, onCreated, priorityLabels }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{
        fontSize: 11, fontWeight: 700, color: 'var(--accent)', textTransform: 'uppercase',
        letterSpacing: '.07em', padding: '6px 0 8px', borderBottom: '1px solid var(--surface-4)', marginBottom: 12,
      }}>
        {label}
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', overflowX: 'auto', paddingBottom: 4 }}>
        {columns.map(col => (
          <KanbanColumn
            key={col.id}
            col={col}
            tasks={tasks.filter(t => t.status === col.id)}
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

export default function KanbanAdvancedPage() {
  const t           = useAppT()
  const toast       = useToast()
  const qc          = useQueryClient()
  const defaultColumns = useMemo(() => getDefaultColumns(t), [t])
  const priorityLabels = useMemo(() => getPriorityLabels(t), [t])

  const [projectId, setProjectId]       = useState('')
  const [search, setSearch]             = useState('')
  const [filterPriority, setFilterPri]  = useState([])
  const [filterAssignee, setFilterAss]  = useState([])
  const [sprintId, setSprintId]         = useState('')
  const [swimlaneBy, setSwimlaneBy]     = useState('none')   // none | assignee | priority | epic
  const [wipLimits, setWipLimits]       = useState({})
  const [showSettings, setShowSettings] = useState(false)
  const searchRef = useRef(null)

  // drag state
  const dragTask       = useRef(null)
  const ghostRef       = useRef(null)
  const dropTargetRef  = useRef(null)  // always-current ref companion to state
  const [dropTarget, setDropTarget] = useState(null)  // { colId, swimlane }

  // ── data ──────────────────────────────────────────────────────────────────
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn:  () => projectsApi.list().then(r => r.data),
  })

  const { data: rawTasks = [], isLoading } = useQuery({
    queryKey: ['kanban-tasks', projectId],
    queryFn:  () => {
      const params = { page_size: 500, ...(projectId ? { project_id: projectId } : {}) }
      return api.get('/tasks', { params })
        .then(r => Array.isArray(r.data) ? r.data : (r.data?.items || []))
    },
    staleTime: 15000,
  })

  const { data: sprints = [] } = useQuery({
    queryKey: ['sprints', projectId],
    queryFn:  () => {
      if (!projectId) return []
      return api.get('/sprints', { params: { project_id: projectId } })
        .then(r => Array.isArray(r.data) ? r.data : (r.data?.items || []))
        .catch(() => [])
    },
    staleTime: 30000,
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }) => api.patch(`/tasks/${id}`, { status }),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['kanban-tasks'] }),
    onError:    (e) => toast.error(e?.response?.data?.detail || t('kanban.error_move_task')),
  })

  // ── Native drag-and-drop ───────────────────────────────────────────────────
  const cleanupGhost = useCallback(() => {
    if (ghostRef.current) {
      ghostRef.current.remove()
      ghostRef.current = null
    }
  }, [])

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────
  useEffect(() => {
    const handler = e => {
      if (e.target.closest('input,textarea,select')) return
      if (e.key === '/' || e.key === 'f') { e.preventDefault(); searchRef.current?.focus() }
      if (e.key === 'Escape') { setDropTarget(null); cleanupGhost() }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [cleanupGhost])

  // ── Filtering ──────────────────────────────────────────────────────────────
  const tasks = useMemo(() => rawTasks.filter(t => {
    if (search && !t.title?.toLowerCase().includes(search.toLowerCase())) return false
    if (filterPriority.length && !filterPriority.includes(getPriority(t))) return false
    if (filterAssignee.length && !filterAssignee.includes(t.assignee_id)) return false
    if (sprintId && t.sprint_id !== sprintId) return false
    return true
  }), [rawTasks, search, filterPriority, filterAssignee, sprintId])

  const assignees = useMemo(() => {
    const seen = new Map()
    for (const t of rawTasks) {
      if (t.assignee_id && !seen.has(t.assignee_id)) seen.set(t.assignee_id, t.assignee_name || t.assignee_id)
    }
    return [...seen.entries()].map(([id, name]) => ({ id, name }))
  }, [rawTasks])

  // ── Swimlane grouping ──────────────────────────────────────────────────────
  const swimlanes = useMemo(() => {
    if (swimlaneBy === 'none') return [{ id: 'all', label: 'all', tasks }]
    if (swimlaneBy === 'assignee') {
      const groups = {}
      for (const t of tasks) {
        const key = t.assignee_id || '__unassigned'
        const lbl = t.assignee_name || 'Sin asignar'
        if (!groups[key]) groups[key] = { id: key, label: lbl, tasks: [] }
        groups[key].tasks.push(t)
      }
      return Object.values(groups)
    }
    if (swimlaneBy === 'priority') {
      const order = ['critical', 'high', 'medium', 'low', 'none']
      const groups = {}
      for (const t of tasks) {
        const key = getPriority(t)
        if (!groups[key]) groups[key] = { id: key, label: priorityLabels[key], tasks: [] }
        groups[key].tasks.push(t)
      }
      return order.filter(k => groups[k]).map(k => groups[k])
    }
    if (swimlaneBy === 'epic') {
      const groups = {}
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

  const handleTaskDragStart = useCallback((e, task, onDragStarted) => {
    const startX = e.clientX
    const startY = e.clientY
    let dragging = false

    const onMove = ev => {
      if (!dragging) {
        const dx = ev.clientX - startX
        const dy = ev.clientY - startY
        if (Math.sqrt(dx * dx + dy * dy) < 5) return
        // Threshold crossed — initialise the real drag
        dragging = true
        dragTask.current = task
        onDragStarted()

        const ghost = document.createElement('div')
        ghost.textContent = task.title
        Object.assign(ghost.style, {
          position: 'fixed', zIndex: 9999, pointerEvents: 'none',
          background: '#0d1424', border: '1px solid #4f8ef7',
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
            updateStatus({ id: dragTask.current.id, status: colId })
          }
        }
      }
      dragTask.current = null
      dropTargetRef.current = null
      setDropTarget(null)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [updateStatus, cleanupGhost])

  const handleColumnEnter = useCallback((colId, swLane) => {
    dropTargetRef.current = { colId, swLane }  // update ref synchronously
    setDropTarget({ colId, swLane })
  }, [])
  const handleColumnLeave = useCallback(() => {
    // don't clear here — let column enter override
  }, [])

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 52px)', background: 'var(--surface-0)' }}>
      {/* Header */}
      <div style={{ padding: '16px 24px 8px', flexShrink: 0 }}>
        <PageHeader
          title={t('kanban.title')}
          subtitle={t('kanban.subtitle')}
          actions={
            <Button size="sm" variant="subtle" onClick={() => setShowSettings(s => !s)}>
              ⚙ {t('kanban.settings_btn')}
            </Button>
          }
        />
      </div>

      {/* Filter bar */}
      <div style={{ padding: '0 24px 12px', display: 'flex', gap: 8, flexWrap: 'wrap', flexShrink: 0, alignItems: 'center' }}>
        <input
          ref={searchRef}
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={t('kanban.search_placeholder')}
          style={{
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 8, padding: '5px 10px', color: 'var(--text-1)',
            fontSize: 12, outline: 'none', width: 160, fontFamily: 'var(--font-sans)',
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
                fontSize: 11, fontFamily: 'var(--font-sans)', fontWeight: active ? 600 : 400,
              }}>
                {priorityLabels[p]}
              </button>
            )
          })}
          {filterPriority.length > 0 && (
            <button onClick={() => setFilterPri([])} style={{ fontSize: 11, color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer' }}>✕</button>
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
              fontSize: 11, fontFamily: 'var(--font-sans)',
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
            fontSize: 12, outline: 'none', fontFamily: 'var(--font-sans)',
          }}>
            <option value="">{t('kanban.all_sprints')}</option>
            {sprints.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}

        {/* Project selector */}
        <select value={projectId} onChange={e => setProjectId(e.target.value)} style={{
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '5px 8px', color: 'var(--text-1)',
          fontSize: 12, outline: 'none', fontFamily: 'var(--font-sans)', marginLeft: 'auto',
        }}>
          <option value="">{t('kanban.all_projects')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>

        {/* Swimlane selector */}
        <select value={swimlaneBy} onChange={e => setSwimlaneBy(e.target.value)} style={{
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '5px 8px', color: 'var(--text-1)',
          fontSize: 12, outline: 'none', fontFamily: 'var(--font-sans)',
        }}>
          <option value="none">{t('kanban.no_swimlanes')}</option>
          <option value="assignee">{t('kanban.swimlane_assignee')}</option>
          <option value="priority">{t('kanban.swimlane_priority')}</option>
          <option value="epic">{t('kanban.swimlane_epic')}</option>
        </select>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div style={{ padding: '12px 24px', background: 'var(--surface-1)', borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', marginBottom: 10 }}>{t('kanban.wip_limits')}</div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {defaultColumns.map(col => (
              <div key={col.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: col.color }} />
                <span style={{ fontSize: 12, color: 'var(--text-2)', width: 90 }}>{col.label}</span>
                <input
                  type="number" min={0} max={50}
                  value={wipLimits[col.id] || ''}
                  placeholder={t('kanban.wip_limit_placeholder')}
                  onChange={e => setWipLimits(prev => ({ ...prev, [col.id]: e.target.value ? parseInt(e.target.value) : 0 }))}
                  style={{
                    width: 50, background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                    borderRadius: 6, padding: '4px 7px', color: 'var(--text-1)',
                    fontSize: 12, outline: 'none', fontFamily: 'var(--font-sans)', textAlign: 'center',
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
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px 24px' }}>
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
                    onTaskClick={t => void t}
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
                dragOverCol={dropTarget?.swimlane === lane.label + projectId ? dropTarget?.colId : null}
                wipLimits={wipLimits}
                projectId={projectId}
                projectSuffix={projectId}
                onTaskDragStart={handleTaskDragStart}
                onColumnEnter={(colId) => handleColumnEnter(colId, lane.label + projectId)}
                onColumnLeave={handleColumnLeave}
                onTaskClick={t => void t}
                onCreated={() => qc.invalidateQueries({ queryKey: ['kanban-tasks'] })}
                priorityLabels={priorityLabels}
              />
            )
          ))}
        </div>
      )}
    </div>
  )
}
