import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tasksApi, projectsApi, customFieldsApi, semanticApi, projectWorkflowsApi } from '../services/api'
import { Badge, Button, Modal, EmptyState, Avatar, useSort, SortableTH, Tabs } from '../components/ui'
import { SkeletonTable } from '../components/ui/Skeletons'
import VirtualList from '../components/ui/VirtualList'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CheckSquare, X } from 'lucide-react'
import { fmtDate, STATUS_LABELS, PRIORITY_LABELS, extractErr} from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import DocumentsPanel from '../components/DocumentsPanel'
import AIInlineEditor from '../components/AIInlineEditor'
import { useAppT } from '../i18n/AppLangContext'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

function onKeyboardActivate(event, action) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}


const STATUSES = ['todo', 'in_progress', 'blocked', 'review', 'done']
const _STATUS_ICONS = { todo: '○', in_progress: '◑', blocked: '✕', review: '◐', done: '●' }

const PRIORITIES = Object.entries(PRIORITY_LABELS).map(([v, l]) => ({ value: v, label: l }))
const TASK_STATUSES = [
  { value: 'open', label: 'Abiertas' },
  ...STATUSES.map(v => ({ value: v, label: STATUS_LABELS[v] })),
]

function TaskKanbanCard({ task, onTaskClick, onTaskDragStart }) {
  const wasDragged = useRef(false)
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${task.title} — ${STATUS_LABELS[task.status] || task.status}`}
      onMouseDown={e => {
        if (e.button !== 0) return
        wasDragged.current = false
        onTaskDragStart && onTaskDragStart(e, task, () => { wasDragged.current = true })
      }}
      onClick={() => { if (!wasDragged.current) onTaskClick(task) }}
      onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onTaskClick(task)}
      style={{
        background: 'var(--surface-2)', border: `1px solid ${task.status === 'blocked' ? 'var(--danger-border)' : 'var(--surface-4)'}`,
        borderRadius: 10, padding: '14px 16px', cursor: 'grab', transition: 'all 0.15s', userSelect: 'none',
      }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'rgba(79,142,247,0.4)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = task.status === 'blocked' ? 'var(--danger-border)' : 'var(--surface-4)'}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, alignItems: 'flex-start' }}>
        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{task.code}</span>
        <Badge label={task.priority} />
      </div>
      <div style={{ fontSize: "var(--text-base)", fontWeight: 600, marginBottom: 10, lineHeight: 1.4 }}>{task.title}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        {task.assignee ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Avatar name={task.assignee.full_name} size={22} />
            <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{task.assignee.full_name.split(' ')[0]}</span>
          </div>
        ) : <span />}
        {task.estimated_hours && (
          <span style={{ fontSize: "var(--text-xs)", color: task.real_hours > task.estimated_hours ? 'var(--danger)' : 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>
            {task.real_hours?.toFixed(1) ?? 0}h / {task.estimated_hours}h
          </span>
        )}
      </div>
      {task.due_date && (
        <div style={{ marginTop: 8, fontSize: "var(--text-xs)", color: new Date(task.due_date) < new Date() && task.status !== 'done' ? 'var(--danger)' : 'var(--text-2)' }}>
          📅 {fmtDate(task.due_date)}
        </div>
      )}
    </div>
  )
}

function KanbanColumn({ status, tasks, onTaskClick, onTaskDragStart, onColumnEnter, onColumnLeave, dragOver }) {
  const colors = { todo: 'var(--text-2)', in_progress: 'var(--accent)', blocked: 'var(--danger)', review: 'var(--warning)', done: 'var(--success)' }
  const color = colors[status]
  return (
    <div
      onPointerEnter={onColumnEnter}
      onPointerLeave={onColumnLeave}
      style={{
        minWidth: 240, flex: 1,
        background: dragOver ? 'rgba(79,142,247,0.06)' : 'transparent',
        borderRadius: 12, border: `1px solid ${dragOver ? 'rgba(79,142,247,0.35)' : 'transparent'}`,
        padding: 8, transition: 'background 0.15s, border-color 0.15s',
      }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, padding: '0 4px' }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
          {STATUS_LABELS[status]}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: "var(--text-xs)", background: 'var(--surface-4)', color: 'var(--text-2)', borderRadius: 10, padding: '1px 7px' }}>
          {tasks.length}
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {tasks.map(task => (
          <TaskKanbanCard
            key={task.id}
            task={task}
            onTaskClick={onTaskClick}
            onTaskDragStart={onTaskDragStart}
          />
        ))}
      </div>
    </div>
  )
}

function useWorkflowStatusOptions(projectId, t) {
  const { data } = useQuery({
    queryKey: ['project-workflow', projectId],
    queryFn: () => projectWorkflowsApi.get(projectId).then(r => r.data).catch(() => null),
    enabled: !!projectId,
    staleTime: 60000,
    retry: false,
  })
  if (data?.states?.length > 0) {
    return data.states
      .slice()
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
      .map(s => ({ value: s.value, icon: s.icon || '○', label: s.name }))
  }
  return [
    { value: 'backlog',     icon: '○', label: t('tasks.status_backlog')     },
    { value: 'todo',        icon: '○', label: t('tasks.status_todo')        },
    { value: 'in_progress', icon: '◑', label: t('tasks.status_in_progress') },
    { value: 'review',      icon: '◐', label: t('tasks.status_review')      },
    { value: 'blocked',     icon: '✕', label: t('tasks.status_blocked')     },
    { value: 'done',        icon: '●', label: t('tasks.status_done')        },
    { value: 'cancelled',   icon: '✕', label: t('tasks.status_cancelled')   },
  ]
}

function TaskDetailModal({ task, open, onClose }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { _invalidate } = useInvalidate()
  const [tab, setTab]         = useState('detail')  // detail | comments | docs
  const [isEditing, setIsEditing] = useState(false)
  const [comment, setComment] = useState('')
  const [form, setForm]       = useState(null)
  const [semSuggestion, setSemSuggestion] = useState(null)
  const [semEffort, setSemEffort]         = useState(null)
  const [suggesting, setSuggesting]       = useState(false)

  // Reset editing mode and form whenever the task changes or modal opens
  useEffect(() => {
    if (task) {
      setIsEditing(false)
      setForm({
        title:           task.title           || '',
        description:     task.description     || '',
        status:          task.status          || 'todo',
        priority:        task.priority        || 'medium',
        assignee_id:     task.assignee_id     || task.assignee?.id || '',
        estimated_hours: task.estimated_hours ?? '',
        start_date:      task.start_date      ? task.start_date.split('T')[0] : '',
        due_date:        task.due_date        ? task.due_date.split('T')[0] : '',
        blocked_reason:  task.blocked_reason  || '',
        tags:            task.tags            || '',
      })
    }
  }, [task])

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => import('../services/api').then(m => m.usersApi.list().then(r => r.data)),
  })

  const statusOptions = useWorkflowStatusOptions(task?.project_id, t)

  const { data: customFields = [] } = useQuery({
    queryKey: ['custom-fields', task?.project_id],
    queryFn: () => customFieldsApi.list(task.project_id).then(r => r.data).catch(() => []),
    enabled: !!task?.project_id,
    retry: false,
  })
  const { data: rawCustomValues } = useQuery({
    queryKey: ['custom-field-values', task?.id],
    queryFn: () => customFieldsApi.getValues(task.project_id, task.id).then(r => r.data).catch(() => []),
    enabled: !!task?.id && !!task?.project_id,
    retry: false,
  })
  const [customValues, setCustomValues] = useState({})
  useEffect(() => {
    const map = {}
    ;(rawCustomValues ?? []).forEach(v => { map[v.field_id] = v.value ?? '' })
    setCustomValues(map)
  }, [rawCustomValues])

  const { mutate: saveTask, isPending: saving } = useMutation({
    mutationFn: async ({ taskData, cfValues, cfFields, taskId, projectId }) => {
      await tasksApi.update(taskId, taskData)
      if (cfFields.length > 0) {
        const payload = cfFields.map(f => ({ field_id: f.id, value: cfValues[f.id] ?? null }))
        await customFieldsApi.setValues(projectId, taskId, payload)
      }
    },
    onSuccess: () => { qc.invalidateQueries(['tasks']); qc.invalidateQueries(['dash-my-tasks']); qc.invalidateQueries(['dash-overdue-tasks']); qc.invalidateQueries(['cal-tasks']); qc.invalidateQueries(['kanban-board']); setIsEditing(false); onClose() },
    onError: e => toast.error(extractErr(e, t('common.error'))),
  })

  const { mutate: deleteTask, isPending: deleting } = useMutation({
    mutationFn: () => tasksApi.delete(task.id),
    onSuccess: () => { qc.invalidateQueries(['tasks']); qc.invalidateQueries(['dash-my-tasks']); qc.invalidateQueries(['dash-overdue-tasks']); qc.invalidateQueries(['cal-tasks']); qc.invalidateQueries(['kanban-board']); onClose() },
    onError: e => toast.error(extractErr(e, t('common.error'))),
  })

  const { mutate: addComment, isPending: commenting } = useMutation({
    mutationFn: ({ id, content }) => tasksApi.comment(id, { content }),
    onSuccess: () => { qc.invalidateQueries(['tasks']); setComment('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const analyzeWithAI = async () => {
    if (!form?.title) return
    setSuggesting(true); setSemSuggestion(null); setSemEffort(null)
    try {
      const [s, e] = await Promise.all([
        semanticApi.suggestTask({ title: form.title, description: form.description }),
        semanticApi.estimateEffort({ title: form.title, description: form.description }),
      ])
      setSemSuggestion(s.data); setSemEffort(e.data)
    } catch { /* noop */ } finally { setSuggesting(false) }
  }

  const acceptSuggestion = () => {
    if (semSuggestion?.suggested_user_id) {
      setForm(f => ({ ...f, assignee_id: semSuggestion.suggested_user_id }))
      // Persist SemAssignment so the feedback loop has a base row for this task
      semanticApi.recordAssignment({
        item_type: 'task',
        item_id: task.id,
        item_title: form.title || task.title || '',
        suggested_user_id: semSuggestion.suggested_user_id,
        accepted_user_id: semSuggestion.suggested_user_id,
        was_accepted: true,
        confidence: semSuggestion.confidence,
        needs_review: semSuggestion.needs_review,
        engine_mode: semSuggestion.engine_mode,
        reasoning: semSuggestion.reasoning,
      }).catch(() => { /* non-blocking */ })
    }
    if (semEffort?.base_hours && !form.estimated_hours)
      setForm(f => ({ ...f, estimated_hours: String(semEffort.base_hours) }))
    setSemSuggestion(null); setSemEffort(null)
  }

  const cancelEdit = () => {
    // Revert form to current task values
    setForm({
      title:           task.title           || '',
      description:     task.description     || '',
      status:          task.status          || 'todo',
      priority:        task.priority        || 'medium',
      assignee_id:     task.assignee_id     || task.assignee?.id || '',
      estimated_hours: task.estimated_hours ?? '',
      start_date:      task.start_date      ? task.start_date.split('T')[0] : '',
      due_date:        task.due_date        ? task.due_date.split('T')[0] : '',
      blocked_reason:  task.blocked_reason  || '',
      tags:            task.tags            || '',
    })
    setSemSuggestion(null); setSemEffort(null)
    setIsEditing(false)
  }

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const fs  = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls  = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }
  const COMPLEXITY_COLORS = { simple: 'var(--success)', medium: 'var(--warning)', complex: 'var(--danger)' }
  const STATUS_LABEL_MAP = { backlog: t('tasks.status_backlog'), todo: t('tasks.status_todo'), in_progress: t('tasks.status_in_progress'), review: t('tasks.status_review'), blocked: t('tasks.status_blocked'), done: t('tasks.status_done'), cancelled: t('tasks.status_cancelled') }
  const PRIORITY_COLOR   = { critical: 'var(--danger)', high: 'var(--warning)', medium: 'var(--accent)', low: 'var(--text-2)' }
  const STATUS_COLOR     = { done: 'var(--success)', blocked: 'var(--danger)', in_progress: 'var(--accent)', review: 'var(--warning)', todo: 'var(--text-2)', backlog: 'var(--text-3)', cancelled: 'var(--text-3)' }
  const bodyPad = '20px 20px 24px'
  const tabPanelStyle = { paddingTop: 8 }

  if (!open || !task || !form) return null

  return (
    <>
      <div role="presentation" onMouseDown={onClose}
        style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,0.35)' }} />
      <div role="dialog" aria-modal="true"
        style={{ position: 'fixed', top: 12, right: 12, width: 520, maxWidth: 'calc(100vw - 24px)',
          maxHeight: 'calc(100vh - 24px)',
          background: 'var(--surface-1)', borderLeft: '1px solid var(--surface-4)',
          border: '1px solid var(--surface-4)', borderRadius: 12,
          zIndex: 201, display: 'flex', flexDirection: 'column', overflow: 'hidden',
          boxShadow: '-8px 0 32px rgba(0,0,0,0.4)' }}>
        {/* Drawer header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 20px', borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{task.code}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-3)', display: 'flex', padding: 4, borderRadius: 6 }}>
            <X size={16} />
          </button>
        </div>
        {/* Scrollable body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: bodyPad }}>

      {/* Tabs */}
      <Tabs
        items={[
          { id: 'detail',   label: t('tasks.tab_details') },
          { id: 'comments', label: t('tasks.tab_comments'), count: task.comments?.length },
          { id: 'docs',     label: t('tasks.tab_docs') },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel={t('tasks.tab_details')}
        style={{ marginBottom: 16, paddingBottom: 10, borderBottom: '1px solid var(--surface-4)' }}
      />

      {/* ── DETALLES / EDITAR ── */}
      {tab === 'detail' && !isEditing && (
        <div style={tabPanelStyle}>
          {/* Title */}
          <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, color: 'var(--text-1)', marginBottom: 16, lineHeight: 1.3 }}>{task.title}</div>

          {/* Status + Priority row */}
          <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            <span style={{ fontSize: "var(--text-sm)", padding: '3px 12px', borderRadius: 20, fontWeight: 700,
              background: STATUS_COLOR[task.status] + '20', color: STATUS_COLOR[task.status] }}>
              {STATUS_LABEL_MAP[task.status] || task.status}
            </span>
            <span style={{ fontSize: "var(--text-sm)", padding: '3px 12px', borderRadius: 20, fontWeight: 700,
              background: PRIORITY_COLOR[task.priority] + '20', color: PRIORITY_COLOR[task.priority] }}>
              {PRIORITY_LABELS[task.priority] || task.priority}
            </span>
          </div>

          {/* Info grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
            <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('tasks.assignee')}</div>
              {task.assignee ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Avatar name={task.assignee.full_name} size={22} />
                  <span style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{task.assignee.full_name}</span>
                </div>
              ) : <span style={{ fontSize: "var(--text-base)", color: 'var(--text-3)' }}>{t('tasks.no_assignee')}</span>}
            </div>
            <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('tasks.hours_label')}</div>
              <span style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>
                {task.real_hours?.toFixed(1) ?? 0}h real
                {task.estimated_hours ? ` / ${task.estimated_hours}h est.` : ''}
              </span>
            </div>
            {task.start_date && (
              <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('tasks.start_date_label')}</div>
                <span style={{ fontSize: "var(--text-base)" }}>{fmtDate(task.start_date)}</span>
              </div>
            )}
            {task.due_date && (
              <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{t('tasks.due_date')}</div>
                <span style={{ fontSize: "var(--text-base)", color: new Date(task.due_date) < new Date() && task.status !== 'done' ? 'var(--danger)' : 'var(--text-1)' }}>
                  {fmtDate(task.due_date)}
                </span>
              </div>
            )}
          </div>

          {/* Description */}
          {task.description && (
            <div style={{ marginBottom: 14, background: 'var(--surface-3)', borderRadius: 8, padding: '12px 14px' }}>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>{t('common.description')}</div>
              <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', lineHeight: 1.6, whiteSpace: 'pre-line' }}>{task.description}</div>
            </div>
          )}

          {/* Blocked reason */}
          {task.status === 'blocked' && task.blocked_reason && (
            <div style={{ marginBottom: 14, background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--danger)', marginBottom: 4 }}>✕ {t('tasks.blocked_label')}</div>
              <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{task.blocked_reason}</div>
            </div>
          )}

          {/* Tags */}
          {task.tags && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>{t('tasks.tags_label')}</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {String(task.tags).split(',').filter(Boolean).map(tag => (
                  <span key={tag} style={{ fontSize: "var(--text-xs)", padding: '2px 9px', borderRadius: 12, background: 'var(--surface-3)', color: 'var(--text-2)' }}>#{tag.trim()}</span>
                ))}
              </div>
            </div>
          )}

          {/* Custom fields (read-only) */}
          {customFields.length > 0 && rawCustomValues.length > 0 && (
            <div style={{ marginBottom: 14, borderTop: '1px solid var(--surface-4)', paddingTop: 14 }}>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>{t('tasks.custom_fields_label')}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                {customFields.map(f => {
                  const val = customValues[f.id]
                  if (!val && val !== 0) return null
                  return (
                    <div key={f.id} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '8px 12px' }}>
                      <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', marginBottom: 3 }}>{f.name}</div>
                      <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)' }}>{String(val)}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Footer actions */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, paddingTop: 14, borderTop: '1px solid var(--surface-4)' }}>
            <button onClick={() => { openConfirmGlobal({ message: `${t('common.are_you_sure')} ${t('common.delete')}?`, onConfirm: () => deleteTask(), danger: true }) }} disabled={deleting}
              style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--danger-border)', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
              {deleting ? t('tasks.deleting') : `🗑 ${t('common.delete')}`}
            </button>
            <Button onClick={() => setIsEditing(true)}>✏️ {t('common.edit')}</Button>
          </div>
        </div>
      )}

      {/* ── MODO EDICIÓN ── */}
      {tab === 'detail' && isEditing && (
        <div style={{ ...tabPanelStyle, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>

          {/* Título */}
          <div style={{ gridColumn: '1/-1' }}>
            <label style={ls}>{t('tasks.title_required')}</label>
            <input value={form.title} onChange={set('title')} style={fs} />
          </div>

          {/* Estado + Prioridad */}
          <div>
            <label style={ls}>{t('common.status')}</label>
            <select value={form.status} onChange={set('status')} style={fs}>
              {statusOptions.map(o => (
                <option key={o.value} value={o.value}>{o.icon} {o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={ls}>{t('common.priority')}</label>
            <select value={form.priority} onChange={set('priority')} style={fs}>
              <option value="low">🟢 {t('tasks.priority_low')}</option>
              <option value="medium">🟡 {t('tasks.priority_medium')}</option>
              <option value="high">🔴 {t('tasks.priority_high')}</option>
              <option value="critical">🚨 {t('tasks.priority_critical')}</option>
            </select>
          </div>

          {/* Asignado + botón IA */}
          <div style={{ gridColumn: '1/-1' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <label style={{ ...ls, marginBottom: 0 }}>{t('tasks.assignee')}</label>
              <button onClick={analyzeWithAI} disabled={suggesting || !form.title}
                style={{ background: 'transparent', border: '1px solid var(--purple-border-strong)', borderRadius: 6, padding: '3px 10px', color: 'var(--purple)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit', fontWeight: 700 }}>
                {suggesting ? '⏳...' : `🧠 ${t('tasks.ai_suggest')}`}
              </button>
            </div>
            <select value={form.assignee_id} onChange={set('assignee_id')} style={fs}>
              <option value="">{t('tasks.no_assignee')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </select>
            {(semSuggestion || semEffort) && !semSuggestion?.error && (
              <div style={{ marginTop: 8, padding: '10px 14px', background: 'var(--purple-bg)', border: '1px solid var(--purple-border)', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                <div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4, fontWeight: 700 }}>{t('tasks.ai_analysis')}</div>
                  <div style={{ display: 'flex', gap: 16 }}>
                    {semSuggestion?.suggested_user_name && (
                      <div>
                        <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>{t('tasks.ai_person_label')}</div>
                        <div style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>{semSuggestion.suggested_user_name} <span style={{ color: 'var(--accent)', fontSize: "var(--text-xs)" }}>{Math.round((semSuggestion.confidence||0)*100)}%</span></div>
                      </div>
                    )}
                    {semEffort && (
                      <div>
                        <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>{t('tasks.ai_effort_label')}</div>
                        <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--warning)' }}>{semEffort.base_hours}h <span style={{ color: COMPLEXITY_COLORS[semEffort.complexity], fontSize: "var(--text-xs)" }}>{semEffort.complexity}</span></div>
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={acceptSuggestion} style={{ padding: '4px 10px', borderRadius: 6, background: 'var(--success-bg)', border: '1px solid var(--success-border)', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>{t('tasks.ai_apply')}</button>
                  <button onClick={() => { setSemSuggestion(null); setSemEffort(null) }} style={{ padding: '4px 8px', borderRadius: 6, background: 'transparent', border: '1px solid var(--surface-4)', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>✕</button>
                </div>
              </div>
            )}
          </div>

          {/* Horas + Fechas */}
          <div>
            <label style={ls}>{t('tasks.estimated_hours')}</label>
            <input type="number" value={form.estimated_hours} onChange={set('estimated_hours')} style={fs} placeholder="Horas estimadas" aria-label="Horas estimadas" min="0" step="0.5" />
          </div>
          <div style={{ gridColumn: '1/-1', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={ls}>{t('tasks.date_start')}</label>
              <input type="date" value={form.start_date} onChange={set('start_date')} style={fs} />
            </div>
            <div>
              <label style={ls}>{t('tasks.due_date')}</label>
              <input type="date" value={form.due_date} onChange={set('due_date')} style={fs} />
            </div>
          </div>

          {/* Descripción */}
          <div style={{ gridColumn: '1/-1' }}>
            <label style={ls}>{t('common.description')} <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 400 }}>{t('tasks.description_hint')}</span></label>
            <AIInlineEditor value={form.description} onChange={val => set('description')({ target: { value: val } })} rows={4} style={{ ...fs, resize: 'vertical', lineHeight: 1.6 }} />
          </div>

          {/* Motivo bloqueo */}
          {form.status === 'blocked' && (
            <div style={{ gridColumn: '1/-1' }}>
              <label style={ls}>{t('tasks.blocked_reason')}</label>
              <input value={form.blocked_reason} onChange={set('blocked_reason')} style={fs}
                placeholder={t('tasks.blocked_reason_placeholder')} />
            </div>
          )}

          {/* Tags */}
          <div style={{ gridColumn: '1/-1' }}>
            <label style={ls}>{t('tasks.tags_label')}</label>
            <input value={form.tags} onChange={set('tags')} style={fs} placeholder={t('tasks.tags_placeholder')} />
          </div>

          {/* Campos personalizados */}
          {customFields.length > 0 && (
            <div style={{ gridColumn: '1/-1', borderTop: '1px solid var(--surface-4)', paddingTop: 14 }}>
              <label style={{ ...ls, marginBottom: 10 }}>{t('tasks.custom_fields_label')}</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {customFields.map(f => (
                  <div key={f.id} style={(f.field_type === 'text' || f.field_type === 'url') ? { gridColumn: '1/-1' } : {}}>
                    <label style={ls}>{f.name}{f.is_required ? ' *' : ''}</label>
                    {f.field_type === 'select' ? (
                      <select value={customValues[f.id] ?? ''} onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))} style={fs}>
                        <option value="">{t('tasks.select_option')}</option>
                        {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : f.field_type === 'boolean' ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 4 }}>
                        <input type="checkbox" checked={customValues[f.id] === 'true'} onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.checked ? 'true' : 'false' }))} style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
                        <span style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{customValues[f.id] === 'true' ? t('common.yes') : t('common.no')}</span>
                      </div>
                    ) : (
                      <input
                        type={f.field_type === 'number' ? 'number' : f.field_type === 'date' ? 'date' : f.field_type === 'url' ? 'url' : 'text'}
                        value={customValues[f.id] ?? ''}
                        onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))}
                        style={fs}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Info solo lectura */}
          <div style={{ gridColumn: '1/-1', display: 'flex', gap: 12, padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
            <span>🕐 {t('tasks.real_hours')}: <strong style={{ color: 'var(--text-1)' }}>{task.real_hours?.toFixed(1) ?? 0}h</strong></span>
            <span>📅 {t('tasks.created_label')}: <strong style={{ color: 'var(--text-1)' }}>{fmtDate(task.created_at)}</strong></span>
            {task.completed_at && <span>✅ {t('tasks.completed_label')}: <strong style={{ color: 'var(--success)' }}>{fmtDate(task.completed_at)}</strong></span>}
          </div>

          {/* Acciones edición */}
          <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
            <button onClick={() => { openConfirmGlobal({ message: `${t('common.are_you_sure')} ${t('common.delete')}?`, onConfirm: () => deleteTask(), danger: true }) }} disabled={deleting}
              style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--danger-border)', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
              {deleting ? t('tasks.deleting') : `🗑 ${t('common.delete')}`}
            </button>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button variant="secondary" onClick={cancelEdit}>{t('common.cancel')}</Button>
              <Button onClick={() => saveTask({ taskData: form, cfValues: customValues, cfFields: customFields, taskId: task.id, projectId: task.project_id })} disabled={saving || !form.title}>
                {saving ? t('common.saving') : `💾 ${t('tasks.save_changes')}`}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── COMENTARIOS ── */}
      {tab === 'comments' && (
        <div style={tabPanelStyle}>
          {(!task.comments || task.comments.length === 0) ? (
            <p style={{ color: 'var(--text-2)', fontSize: "var(--text-base)", marginBottom: 16 }}>{t('tasks.no_comments')}</p>
          ) : (
            <div style={{ marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {task.comments.map(c => (
                <div key={c.id} style={{ display: 'flex', gap: 10 }}>
                  <Avatar name={c.author?.full_name || '?'} size={28} />
                  <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '8px 12px', flex: 1 }}>
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>
                      <strong style={{ color: 'var(--text-1)' }}>{c.author?.full_name}</strong> · {fmtDate(c.created_at)}
                    </div>
                    <div style={{ fontSize: "var(--text-base)", lineHeight: 1.5 }}>{c.content}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <textarea value={comment} onChange={e => setComment(e.target.value)}
              placeholder={t('tasks.add_comment')}
              rows={2}
              style={{ flex: 1, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', resize: 'none' }}
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && comment) addComment({ id: task.id, content: comment }) }}
            />
            <Button onClick={() => addComment({ id: task.id, content: comment })} disabled={!comment || commenting}>{t('tasks.send_comment')}</Button>
          </div>
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 4 }}>{t('tasks.send_hint')}</div>
        </div>
      )}

      {/* ── DOCUMENTOS ── */}
      {tab === 'docs' && (
        <div style={{ ...tabPanelStyle, marginTop: 0 }}>
          <DocumentsPanel taskId={task.id} />
        </div>
      )}
        </div>
      </div>
    </>
  )
}

export default function TasksPage() {
  const t = useAppT()
  const { hasRole } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  // ── Kanban drag-and-drop state ────────────────────────────────────────────
  const dragTask      = useRef(null)
  const ghostRef      = useRef(null)
  const dropTargetRef = useRef(null)
  const [dropTarget, setDropTarget] = useState(null)

  const cleanupGhost = useCallback(() => {
    if (ghostRef.current) { ghostRef.current.remove(); ghostRef.current = null }
  }, [])

  const { mutate: moveTaskStatus } = useMutation({
    mutationFn: ({ id, status, move_reason }) =>
      tasksApi.update(id, { status, ...(move_reason ? { move_reason } : {}) }),
    onSuccess: () => {
      qc.invalidateQueries(['tasks'])
      qc.invalidateQueries(['kanban-board'])
    },
    onError: e => toast.error(e?.response?.data?.detail || 'Error al mover tarea'),
  })

  const requestMoveTask = useCallback((id, fromStatus, toStatus) => {
    if (fromStatus === toStatus) return
    let move_reason
    if (fromStatus === 'done' || fromStatus === 'cancelled') {
      move_reason = window.prompt(
        `Vas a reabrir/mover una tarea desde "${fromStatus}". Indica el motivo (queda registrado en el log):`,
        ''
      )
      if (move_reason === null) return
      move_reason = move_reason.trim() || undefined
    }
    moveTaskStatus({ id, status: toStatus, move_reason })
  }, [moveTaskStatus])

  const handleTaskDragStart = useCallback((e, task, onDragStarted) => {
    const startX = e.clientX
    const startY = e.clientY
    let dragging = false

    const onMove = ev => {
      if (!dragging) {
        const dx = ev.clientX - startX
        const dy = ev.clientY - startY
        if (Math.sqrt(dx * dx + dy * dy) < 5) return
        dragging = true
        dragTask.current = task
        onDragStarted()
        const ghost = document.createElement('div')
        ghost.textContent = task.title
        Object.assign(ghost.style, {
          position: 'fixed', zIndex: 'var(--z-drag)', pointerEvents: 'none',
          background: 'var(--surface-1)', border: '1px solid var(--accent)',
          borderRadius: '8px', padding: '8px 12px',
          color: 'var(--text-1)', fontSize: '12px', fontFamily: 'var(--font-sans)',
          maxWidth: '220px', boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
          opacity: '0.9', left: ev.clientX + 12 + 'px', top: ev.clientY + 12 + 'px',
        })
        document.body.appendChild(ghost)
        ghostRef.current = ghost
      } else if (ghostRef.current) {
        ghostRef.current.style.left = ev.clientX + 12 + 'px'
        ghostRef.current.style.top  = ev.clientY + 12 + 'px'
      }
    }

    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      cleanupGhost()
      if (dragging) {
        const target = dropTargetRef.current
        if (dragTask.current && target && dragTask.current.status !== target) {
          requestMoveTask(dragTask.current.id, dragTask.current.status, target)
        }
      }
      dragTask.current = null
      dropTargetRef.current = null
      setDropTarget(null)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [moveTaskStatus, cleanupGhost])

  const handleColumnEnter = useCallback((status) => {
    dropTargetRef.current = status
    setDropTarget(status)
  }, [])
  const handleColumnLeave = useCallback(() => {}, [])
  const [searchParams, setSearchParams] = useSearchParams()
  const view           = searchParams.get('view') || 'kanban'
  const projectFilter  = searchParams.get('project_id') || ''
  const statusFilter   = searchParams.get('status') || ''
  const search         = searchParams.get('search') || ''
  const priorityFilter = searchParams.get('priority') || ''
  const assigneeFilter = searchParams.get('assignee') || ''
  const overdueOnly    = searchParams.get('overdue') === '1'
  const mineOnly       = searchParams.get('mine') === '1'
  const setTaskParam = (k, v) => setSearchParams(p => { const n = new URLSearchParams(p); v ? n.set(k, v) : n.delete(k); return n }, { replace: true })
  const setView           = (v) => setTaskParam('view', v === 'kanban' ? '' : v)
  const setProjectFilter  = (v) => setTaskParam('project_id', v)
  const setStatusFilter   = (v) => setTaskParam('status', v)
  const setSearch         = (v) => setTaskParam('search', v)
  const setPriorityFilter = (v) => setTaskParam('priority', v)
  const setAssigneeFilter = (v) => setTaskParam('assignee', v)
  const clearQuickFilters = () => setSearchParams(p => {
    const n = new URLSearchParams(p)
    n.delete('mine')
    n.delete('overdue')
    if (n.get('status') === 'open') n.delete('status')
    return n
  }, { replace: true })
  const quickFilterPills = [
    mineOnly ? { key: 'mine', label: 'Solo mis tareas', onClear: () => setTaskParam('mine', '') } : null,
    overdueOnly ? { key: 'overdue', label: 'Solo vencidas', onClear: () => setTaskParam('overdue', '') } : null,
    statusFilter === 'open' ? { key: 'open', label: 'Estado: abiertas', onClear: () => setTaskParam('status', '') } : null,
  ].filter(Boolean)
  const [selectedTask, setSelectedTask] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [selected, setSelected] = useState(new Set())  // bulk selection
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth)

  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const isCompact = viewportWidth <= 1024
  const isMobile = viewportWidth <= 768

  // Bulk action state
  const [bulkStatus, setBulkStatus] = useState('')
  const [bulkAssignee, setBulkAssignee] = useState('')
  const [bulkPriority, setBulkPriority] = useState('')

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const { data: tasksData, isLoading } = useQuery({
    queryKey: ['tasks', projectFilter, statusFilter, view, search, priorityFilter, assigneeFilter, overdueOnly, mineOnly],
    queryFn: () => {
      const effectiveStatus = statusFilter === 'open'
        ? 'backlog,todo,in_progress,blocked,in_review,review'
        : (statusFilter || undefined)
      if (view === 'kanban' && projectFilter) {
        return tasksApi.kanban(projectFilter).then(r => r.data)
      }
      return tasksApi.list({
        project_id: projectFilter || undefined,
        status: effectiveStatus,
        search: search || undefined,
        priority: priorityFilter || undefined,
        assignee_id: assigneeFilter || undefined,
        overdue_only: overdueOnly || undefined,
        assigned_to_me: mineOnly || undefined,
      }).then(r => r.data)
    },
    keepPreviousData: true,
  })

  const projectOptions = projects.map(p => ({ value: p.id, label: `${p.code} — ${p.name}` }))

  // flatTasks: en lista y en kanban-sin-proyecto tasksData es array; en kanban-con-proyecto es objeto {status:[]}
  const flatTasks = Array.isArray(tasksData)
    ? tasksData
    : Object.values(tasksData || {}).flat()

  const { sort: taskSort, setSort: setTaskSort, sortedData: sortedTasks } = useSort(flatTasks, 'title')

  const kanbanColumns = view === 'kanban' && tasksData && !Array.isArray(tasksData)
    ? tasksData
    : STATUSES.reduce((a, s) => ({ ...a, [s]: [] }), {})

  // ── Bulk operations ──────────────────────────────────────────────────────
  const { data: allUsers = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => import('../services/api').then(m => m.usersApi.list().then(r => r.data)),
    staleTime: 120000,
  })

  const { mutate: bulkMutate, isPending: bulkPending } = useMutation({
    mutationFn: (payload) => tasksApi.bulkUpdate(payload),
    onSuccess: (res) => {
      qc.invalidateQueries(['tasks'])
      qc.invalidateQueries(['dash-my-tasks'])
      qc.invalidateQueries(['dash-overdue-tasks'])
      qc.invalidateQueries(['cal-tasks'])
      qc.invalidateQueries(['kanban-board'])
      const data = res.data
      const n = data?.updated ?? 0
      const s = data?.skipped?.length ?? 0
      toast.success(`${n} tarea${n !== 1 ? 's' : ''} actualizad${n !== 1 ? 'as' : 'a'}${s > 0 ? ` · ${s} omitid${s !== 1 ? 'as' : 'a'}` : ''}`)
      setSelected(new Set())
      setBulkStatus(''); setBulkAssignee(''); setBulkPriority('')
    },
    onError: e => toast.error(extractErr(e, 'Error en actualización masiva')),
  })

  const toggleSelect = (id) => setSelected(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })
  const toggleAll = () => setSelected(prev =>
    prev.size === flatTasks.length ? new Set() : new Set(flatTasks.map(t => t.id))
  )
  const applyBulk = () => {
    if (selected.size === 0) return
    const payload = { task_ids: [...selected] }
    if (bulkStatus)   payload.status = bulkStatus
    if (bulkAssignee) payload.assignee_id = bulkAssignee
    if (bulkPriority) payload.priority = bulkPriority
    if (!payload.status && !payload.assignee_id && !payload.priority) {
      toast.error('Selecciona al menos un campo a actualizar')
      return
    }
    bulkMutate(payload)
  }

  return (
    <PageShell>
      <PageHeader
        icon={<CheckSquare size={18} />}
        title={t('tasks.title')}
        subtitle={t('tasks.subtitle')}
        exportTargetSelector='[data-export-table="tasks-list"]'
        exportFilePrefix='tasks'
        actions={
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', width: isMobile ? '100%' : 'auto' }}>
            <div style={{ display: 'flex', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, overflow: 'hidden' }}>
              {['kanban', 'list'].map(v => (
                <button key={v} onClick={() => setView(v)}
                  style={{
                    padding: '7px 14px', background: view === v ? 'var(--accent-muted)' : 'transparent',
                    border: 'none', color: view === v ? 'var(--accent)' : 'var(--text-2)',
                    fontSize: "var(--text-sm)", fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                  }}>
                  {v === 'kanban' ? '⊞ Kanban' : '☰ Lista'}
                </button>
              ))}
            </div>
            {hasRole('admin', 'pm', 'team_lead') && (
              <Button onClick={() => setShowCreate(true)} icon="＋">{t('tasks.new_task')}</Button>
            )}
          </div>
        }
      />

      {/* Filters */}
      {quickFilterPills.length > 0 && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          {quickFilterPills.map(pill => (
            <span key={pill.key} style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)',
              color: 'var(--accent)', borderRadius: 999, padding: '4px 10px',
              fontSize: 'var(--text-xs)', fontWeight: 700,
            }}>
              {pill.label}
              <button type="button" onClick={pill.onClear} aria-label={`Quitar filtro ${pill.label}`} style={{
                background: 'transparent', border: 'none', color: 'var(--accent)', cursor: 'pointer',
                fontSize: 'var(--text-sm)', lineHeight: 1, padding: 0,
              }}>×</button>
            </span>
          ))}
          <button type="button" onClick={clearQuickFilters} style={{
            background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 999,
            color: 'var(--text-2)', cursor: 'pointer', fontSize: 'var(--text-xs)',
            fontWeight: 600, padding: '4px 10px', fontFamily: 'inherit',
          }}>
            Limpiar filtros rápidos
          </button>
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: 2, minWidth: 200 }}>
          <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)', fontSize: "var(--text-md)" }}>🔍</span>
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder={t('tasks.search_placeholder')}
            style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 14px 9px 34px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }} />
        </div>
        <select value={projectFilter} onChange={e => setProjectFilter(e.target.value)}
          style={{ flex: 1, minWidth: isMobile ? '100%' : 200, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
          <option value="">{t('tasks.all_projects')}</option>
          {projectOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}
          style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 14px', color: priorityFilter ? 'var(--warning)' : 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
          <option value="">{t('tasks.filter_priority')}</option>
          {PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <select value={assigneeFilter} onChange={e => setAssigneeFilter(e.target.value)}
          style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 14px', color: assigneeFilter ? 'var(--accent)' : 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
          <option value="">{t('tasks.all_assignees')}</option>
          {allUsers.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
        </select>
        {view === 'list' && (
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
            <option value="">{t('tasks.filter_status')}</option>
            {TASK_STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        )}
      </div>

      {/* ── Bulk Action Bar ─────────────────────────────────────────────── */}
      {selected.size > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', marginBottom: 12,
          background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 10,
          flexWrap: 'wrap' }}>
          <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--accent)', whiteSpace: 'nowrap' }}>
            ☑ {selected.size} {t('tasks.selected')}
          </span>
          <div style={{ width: 1, height: 20, background: 'var(--surface-4)' }} />
          <select value={bulkStatus} onChange={e => setBulkStatus(e.target.value)}
            style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '5px 10px', color: bulkStatus ? 'var(--text-1)' : 'var(--text-2)', fontSize: "var(--text-sm)", fontFamily: 'inherit', cursor: 'pointer', outline: 'none' }}>
            <option value="">{t('tasks.bulk_status_ph')}</option>
            <option value="todo">○ {t('tasks.status_todo')}</option>
            <option value="in_progress">◑ {t('tasks.status_in_progress')}</option>
            <option value="review">◐ {t('tasks.status_review')}</option>
            <option value="blocked">✕ {t('tasks.status_blocked')}</option>
            <option value="done">● {t('tasks.status_done')}</option>
          </select>
          <select value={bulkPriority} onChange={e => setBulkPriority(e.target.value)}
            style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '5px 10px', color: bulkPriority ? 'var(--text-1)' : 'var(--text-2)', fontSize: "var(--text-sm)", fontFamily: 'inherit', cursor: 'pointer', outline: 'none' }}>
            <option value="">{t('tasks.bulk_priority_ph')}</option>
            <option value="low">🟢 {t('tasks.priority_low')}</option>
            <option value="medium">🟡 {t('tasks.priority_medium')}</option>
            <option value="high">🔴 {t('tasks.priority_high')}</option>
            <option value="critical">🚨 {t('tasks.priority_critical')}</option>
          </select>
          <select value={bulkAssignee} onChange={e => setBulkAssignee(e.target.value)}
            style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '5px 10px', color: bulkAssignee ? 'var(--text-1)' : 'var(--text-2)', fontSize: "var(--text-sm)", fontFamily: 'inherit', cursor: 'pointer', outline: 'none' }}>
            <option value="">{t('tasks.bulk_assignee_ph')}</option>
            {allUsers.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
          <button onClick={applyBulk} disabled={bulkPending || (!bulkStatus && !bulkPriority && !bulkAssignee)}
            style={{ background: 'var(--accent)', border: 'none', borderRadius: 7, padding: '6px 14px', color: '#000', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', opacity: (!bulkStatus && !bulkPriority && !bulkAssignee) ? 0.5 : 1 }}>
            {bulkPending ? '⏳' : t('tasks.bulk_apply')}
          </button>
          <button onClick={() => { setSelected(new Set()); setBulkStatus(''); setBulkPriority(''); setBulkAssignee('') }}
            style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '5px 10px', color: 'var(--text-2)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {t('common.cancel')}
          </button>
        </div>
      )}

      {isLoading ? (
        <SkeletonTable rows={10} />
      ) : view === 'kanban' ? (
        projectFilter ? (
          <div style={{ display: 'flex', flexDirection: isCompact ? 'column' : 'row', gap: 12, overflowX: isCompact ? 'visible' : 'auto', paddingBottom: 16 }}>
            {STATUSES.filter(s => s !== 'backlog').map(status => (
              <KanbanColumn
                key={status}
                status={status}
                tasks={(kanbanColumns[status] || []).filter(t =>
                  (!search || t.title?.toLowerCase().includes(search.toLowerCase())) &&
                  (!priorityFilter || t.priority === priorityFilter)
                )}
                onTaskClick={setSelectedTask}
                onTaskDragStart={handleTaskDragStart}
                onColumnEnter={() => handleColumnEnter(status)}
                onColumnLeave={handleColumnLeave}
                dragOver={dropTarget === status}
              />
            ))}
          </div>
        ) : (
          // Sin proyecto: mostrar lista de todas las tareas
          flatTasks.length === 0 ? (
            <EmptyState icon="tasks" title={t('tasks.no_tasks')} description={t('tasks.col_task')} ctaLabel={t('tasks.new_task')} onCta={() => setShowCreate(true)} />
          ) : (
            <div data-export-table="tasks-list" style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ padding: '10px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                💡 {t('tasks.select_project')} · {flatTasks.length} {t('tasks.col_task')}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '28px 2.5fr 1.5fr 1fr 80px 100px 100px', gap: 16, padding: '10px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
                <input type="checkbox" checked={selected.size === flatTasks.length && flatTasks.length > 0} onChange={toggleAll} style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
                <SortableTH col="title" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_task')}</SortableTH>
                <SortableTH col="project_id" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_project')}</SortableTH>
                <SortableTH col="assignee.full_name" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_assignee')}</SortableTH>
                <SortableTH col="estimated_hours" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_est')}</SortableTH>
                <SortableTH col="status" sort={taskSort} onSort={setTaskSort}>{t('common.status')}</SortableTH>
                <SortableTH col="priority" sort={taskSort} onSort={setTaskSort}>{t('common.priority')}</SortableTH>
              </div>
              {sortedTasks.map(t => {
                const proj = projects.find(p => p.id === t.project_id)
                return (
                  <div key={t.id}
                    onClick={() => setSelectedTask(t)}
                    onKeyDown={e => onKeyboardActivate(e, () => setSelectedTask(t))}
                    role="button"
                    tabIndex={0}
                    style={{ display: 'grid', gridTemplateColumns: '28px 2.5fr 1.5fr 1fr 80px 100px 100px', gap: 16, padding: '12px 20px', borderBottom: '1px solid var(--surface-4)30', cursor: 'pointer', alignItems: 'center', background: selected.has(t.id) ? 'var(--accent-muted)' : 'transparent' }}
                    onMouseEnter={e => { if (!selected.has(t.id)) e.currentTarget.style.background = 'var(--surface-3)' }}
                    onMouseLeave={e => { e.currentTarget.style.background = selected.has(t.id) ? 'var(--accent-muted)' : 'transparent' }}>
                    <input type="checkbox" checked={selected.has(t.id)} onChange={() => toggleSelect(t.id)} onClick={e => e.stopPropagation()} style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
                    <div>
                      <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{t.title}</div>
                      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{t.code}</div>
                    </div>
                    <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{proj ? `${proj.code}` : '—'}</span>
                    <span style={{ fontSize: "var(--text-sm)" }}>{t.assignee?.full_name?.split(' ')[0] || '—'}</span>
                    <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{t.estimated_hours ? `${t.estimated_hours}h` : '—'}</span>
                    <span><Badge label={t.status} /></span>
                    <span><Badge label={t.priority} /></span>
                  </div>
                )
              })}
            </div>
          )
        )
      ) : (
        flatTasks.length === 0 ? (
          <EmptyState icon="search" title={t('common.no_results')} description={t('tasks.filter_status')} />
        ) : isCompact ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {sortedTasks.map((t) => {
              const proj = projects.find(p => p.id === t.project_id)
              return (
                <div key={t.id}
                  onClick={() => setSelectedTask(t)}
                  onKeyDown={e => onKeyboardActivate(e, () => setSelectedTask(t))}
                  role="button"
                  tabIndex={0}
                  style={{
                    background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10,
                    padding: '12px 14px', cursor: 'pointer',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    <input
                      type="checkbox"
                      checked={selected.has(t.id)}
                      onChange={() => toggleSelect(t.id)}
                      onClick={e => e.stopPropagation()}
                      style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
                    />
                    <div style={{ fontSize: "var(--text-base)", fontWeight: 700, flex: 1 }}>{t.title}</div>
                    <Badge label={t.priority} />
                  </div>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                    <span>{t.code}</span>
                    <span>{proj ? proj.code : t('tasks.no_project')}</span>
                    <span>{t.assignee?.full_name || t('tasks.no_assignee')}</span>
                    <span>{t.estimated_hours ? `${t.estimated_hours}h est.` : t('tasks.no_estimate')}</span>
                    <span>{t.real_hours?.toFixed(1) ?? 0}h real</span>
                  </div>
                  <div style={{ marginTop: 8 }}>
                    <Badge label={t.status} />
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div data-export-table="tasks-list" style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '28px 2.5fr 1.5fr 1fr 80px 80px 100px 100px', gap: 16, padding: '10px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
              <input type="checkbox" checked={selected.size === flatTasks.length && flatTasks.length > 0} onChange={toggleAll} style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
              <SortableTH col="title" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_task')}</SortableTH>
              <SortableTH col="project_id" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_project')}</SortableTH>
              <SortableTH col="assignee.full_name" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_assignee')}</SortableTH>
              <SortableTH col="estimated_hours" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_est')}</SortableTH>
              <SortableTH col="real_hours" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_real')}</SortableTH>
              <SortableTH col="status" sort={taskSort} onSort={setTaskSort}>{t('common.status')}</SortableTH>
              <SortableTH col="priority" sort={taskSort} onSort={setTaskSort}>{t('common.priority')}</SortableTH>
            </div>
            <VirtualList
              items={sortedTasks}
              rowHeight={52}
              height={Math.min(flatTasks.length * 52, 600)}
              renderRow={(t) => (
                <div
                  onClick={() => setSelectedTask(t)}
                  onKeyDown={e => onKeyboardActivate(e, () => setSelectedTask(t))}
                  role="button"
                  tabIndex={0}
                  style={{ display: 'grid', gridTemplateColumns: '28px 2.5fr 1.5fr 1fr 80px 80px 100px 100px', gap: 16, padding: '14px 20px', borderBottom: '1px solid var(--surface-4)30', cursor: 'pointer', transition: 'background 0.1s', alignItems: 'center', background: selected.has(t.id) ? 'var(--accent-muted)' : 'transparent' }}
                  onMouseEnter={e => { if (!selected.has(t.id)) e.currentTarget.style.background = 'var(--surface-3)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = selected.has(t.id) ? 'var(--accent-muted)' : 'transparent' }}
                >
                  <input type="checkbox" checked={selected.has(t.id)} onChange={() => toggleSelect(t.id)} onClick={e => e.stopPropagation()} style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
                  <div>
                    <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{t.title}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{t.code}</div>
                  </div>
                  <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                    {projects.find(p => p.id === t.project_id)?.code || t.project_id?.slice(0,8) || '—'}
                  </span>
                  <span style={{ fontSize: "var(--text-sm)" }}>{t.assignee?.full_name?.split(' ')[0] || '—'}</span>
                  <span style={{ fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{t.estimated_hours ? `${t.estimated_hours}h` : '—'}</span>
                  <span style={{ fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)', color: t.real_hours > t.estimated_hours ? 'var(--danger)' : 'var(--text-2)' }}>{t.real_hours?.toFixed(1) ?? 0}h</span>
                  <span><Badge label={t.status} /></span>
                  <span><Badge label={t.priority} /></span>
                </div>
              )}
            />
          </div>
        )
      )}

      <TaskDetailModal task={selectedTask} open={!!selectedTask} onClose={() => setSelectedTask(null)} />
      <CreateTaskModal open={showCreate} onClose={() => setShowCreate(false)} projects={projects} />
    </PageShell>
  )
}

function CreateTaskModal({ open, onClose, projects }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => import('../services/api').then(m => m.usersApi.list().then(r => r.data)),
  })
  const [form, setForm] = useState({
    title: '', project_id: '', status: 'todo', priority: 'medium',
    estimated_hours: '', start_date: '', due_date: '', description: '', assignee_id: '',
  })
  const [semSuggestion, setSemSuggestion] = useState(null)
  const [semEffort, setSemEffort] = useState(null)
  const [suggesting, setSuggesting] = useState(false)
  const [pendingSuggestion, setPendingSuggestion] = useState(null)
  const [customValues, setCustomValues] = useState({})

  const { data: customFields = [] } = useQuery({
    queryKey: ['custom-fields', form.project_id],
    queryFn: () => customFieldsApi.list(form.project_id).then(r => r.data).catch(() => []),
    enabled: !!form.project_id,
    retry: false,
  })

  const statusOptions = useWorkflowStatusOptions(form.project_id, t)

  const { mutate, isPending } = useMutation({
    mutationFn: async ({ taskData, cfValues, cfFields }) => {
      const res = await tasksApi.create(taskData)
      const task = res.data
      if (cfFields.length > 0 && task?.id) {
        const payload = cfFields.map(f => ({ field_id: f.id, value: cfValues[f.id] ?? null }))
        await customFieldsApi.setValues(task.project_id, task.id, payload)
      }
      return task
    },
    onSuccess: (newTask) => {
      if (pendingSuggestion?.suggested_user_id && newTask?.id) {
        semanticApi.recordAssignment({
          item_type: 'task',
          item_id: newTask.id,
          item_title: newTask.title || '',
          suggested_user_id: pendingSuggestion.suggested_user_id,
          accepted_user_id: pendingSuggestion.suggested_user_id,
          was_accepted: true,
          confidence: pendingSuggestion.confidence,
          needs_review: pendingSuggestion.needs_review,
          engine_mode: pendingSuggestion.engine_mode,
          reasoning: pendingSuggestion.reasoning,
        }).catch(() => { /* non-blocking */ })
      }
      qc.invalidateQueries(['tasks'])
      qc.invalidateQueries(['dash-my-tasks'])
      qc.invalidateQueries(['dash-overdue-tasks'])
      qc.invalidateQueries(['cal-tasks'])
      qc.invalidateQueries(['kanban-board'])
      onClose()
      setForm({ title: '', project_id: '', status: 'todo', priority: 'medium', estimated_hours: '', start_date: '', due_date: '', description: '', assignee_id: '' })
      setCustomValues({})
      setSemSuggestion(null); setSemEffort(null); setPendingSuggestion(null)
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }

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
    } catch (e) { setSemSuggestion({ error: e?.response?.data?.detail || 'Error' }) }
    finally { setSuggesting(false) }
  }

  const acceptSuggestion = () => {
    if (semSuggestion?.suggested_user_id) {
      setForm(f => ({ ...f, assignee_id: semSuggestion.suggested_user_id }))
      // Store suggestion so we can persist SemAssignment once the task is created (task.id is known)
      setPendingSuggestion({ ...semSuggestion })
    }
    if (semEffort?.base_hours && !form.estimated_hours)
      setForm(f => ({ ...f, estimated_hours: String(semEffort.base_hours) }))
    setSemSuggestion(null); setSemEffort(null)
  }

  const COMPLEXITY_COLORS = { simple: 'var(--success)', medium: 'var(--warning)', complex: 'var(--danger)' }

  return (
    <Modal open={open} onClose={onClose} title={t('tasks.new_task')} width={580}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={ls}>{t('tasks.title_required')}</label>
          <input value={form.title} onChange={set('title')} style={fs} placeholder={t('tasks.task_title')} />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={ls}>{t('tasks.project_required')}</label>
          <select value={form.project_id} onChange={set('project_id')} style={fs}>
            <option value="">{t('tasks.select_project_option')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>{t('common.status')}</label>
          <select value={form.status} onChange={set('status')} style={fs}>
            {statusOptions.map(o => (
              <option key={o.value} value={o.value}>{o.icon} {o.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label style={ls}>{t('common.priority')}</label>
          <select value={form.priority} onChange={set('priority')} style={fs}>
            <option value="low">🟢 {t('tasks.priority_low')}</option>
            <option value="medium">🟡 {t('tasks.priority_medium')}</option>
            <option value="high">🔴 {t('tasks.priority_high')}</option>
            <option value="critical">🚨 {t('tasks.priority_critical')}</option>
          </select>
        </div>
        {/* Asignación + estimación con IA */}
        <div style={{ gridColumn: '1 / -1' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <label style={{ ...ls, marginBottom: 0 }}>{t('tasks.assignee')}</label>
            <button onClick={analyzeWithAI} disabled={suggesting || !form.title}
              style={{ background: 'transparent', border: '1px solid var(--purple-border-strong)', borderRadius: 6, padding: '3px 12px', color: 'var(--purple)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit', fontWeight: 700 }}>
              {suggesting ? '⏳...' : `🧠 ${t('tasks.ai_analyze')}`}
            </button>
          </div>
          <select value={form.assignee_id} onChange={set('assignee_id')} style={fs}>
            <option value="">{t('tasks.no_assignee')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        {/* Banner de sugerencia IA */}
        {(semSuggestion || semEffort) && !semSuggestion?.error && (
          <div style={{ gridColumn: '1 / -1', padding: '12px 14px', background: 'var(--purple-bg)', border: '1px solid var(--purple-border)', borderRadius: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 6, fontWeight: 700 }}>{t('tasks.ai_analysis')}</div>
              <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
                {semSuggestion?.suggested_user_name && (
                  <div>
                    <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>{t('tasks.ai_person_label')}</div>
                    <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)' }}>
                      {semSuggestion.suggested_user_name}
                      <span style={{ fontSize: "var(--text-xs)", color: 'var(--accent)', marginLeft: 6 }}>
                        {Math.round((semSuggestion.confidence||0)*100)}%
                      </span>
                    </div>
                  </div>
                )}
                {semEffort && (
                  <div>
                    <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>{t('tasks.ai_effort_label')}</div>
                    <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--warning)' }}>
                      {semEffort.base_hours}h
                      <span style={{ fontSize: "var(--text-xs)", marginLeft: 6, color: COMPLEXITY_COLORS[semEffort.complexity] }}>
                        {semEffort.complexity}
                      </span>
                    </div>
                  </div>
                )}
              </div>
              {semSuggestion?.reasoning && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 4 }}>{semSuggestion.reasoning}</div>}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button onClick={acceptSuggestion} style={{ padding: '5px 12px', borderRadius: 6, background: 'var(--success-bg)', border: '1px solid var(--success-border)', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>{t('tasks.ai_apply')}</button>
              <button onClick={() => { setSemSuggestion(null); setSemEffort(null) }} style={{ padding: '5px 8px', borderRadius: 6, background: 'transparent', border: '1px solid var(--surface-4)', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>✕</button>
            </div>
          </div>
        )}
        <div>
          <label style={ls}>{t('tasks.estimated_hours')}</label>
          <input type="number" value={form.estimated_hours} onChange={set('estimated_hours')} style={fs} placeholder="Horas estimadas" aria-label="Horas estimadas" />
        </div>
        <div>
          <label style={ls}>{t('tasks.date_start')}</label>
          <input type="date" value={form.start_date} onChange={set('start_date')} style={fs} />
        </div>
        <div>
          <label style={ls}>{t('tasks.due_date')}</label>
          <input type="date" value={form.due_date} onChange={set('due_date')} style={fs} />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={ls}>{t('common.description')} <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 400 }}>{t('tasks.description_hint')}</span></label>
          <AIInlineEditor value={form.description} onChange={val => set('description')({ target: { value: val } })} rows={3} placeholder={t('common.description')} style={{ ...fs, resize: 'vertical' }} />
        </div>
        {/* Campos personalizados del proyecto */}
        {customFields.length > 0 && (
          <div style={{ gridColumn: '1/-1', borderTop: '1px solid var(--surface-4)', paddingTop: 14 }}>
            <label style={{ ...ls, marginBottom: 10 }}>{t('tasks.custom_fields_label')}</label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {customFields.map(f => (
                <div key={f.id} style={(f.field_type === 'text' || f.field_type === 'url') ? { gridColumn: '1/-1' } : {}}>
                  <label style={ls}>{f.name}{f.is_required ? ' *' : ''}</label>
                  {f.field_type === 'select' ? (
                    <select value={customValues[f.id] ?? ''} onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))} style={fs}>
                      <option value="">{t('tasks.select_option')}</option>
                      {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : f.field_type === 'boolean' ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 4 }}>
                      <input type="checkbox" checked={customValues[f.id] === 'true'} onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.checked ? 'true' : 'false' }))} style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
                      <span style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{customValues[f.id] === 'true' ? t('common.yes') : t('common.no')}</span>
                    </div>
                  ) : (
                    <input
                      type={f.field_type === 'number' ? 'number' : f.field_type === 'date' ? 'date' : f.field_type === 'url' ? 'url' : 'text'}
                      value={customValues[f.id] ?? ''}
                      onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))}
                      style={fs}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate({ taskData: form, cfValues: customValues, cfFields: customFields })} disabled={isPending || !form.title || !form.project_id} loading={isPending}>
            {isPending ? t('tasks.creating') : t('tasks.create_task_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}