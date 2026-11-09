import { useState, useEffect, useRef, useCallback } from 'react'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tasksApi, projectsApi, customFieldsApi, semanticApi, projectWorkflowsApi, issueTypesApi, sprintsApi, cmdbApi } from '../services/api'
import { Badge as _Badge, Button, Modal, EmptyState, Avatar as _Avatar, useSort, SortableTH, Tabs } from '../components/ui'
import { SkeletonTable } from '../components/ui/Skeletons'
import _VirtualList from '../components/ui/VirtualList'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import {
  CheckSquare, X, Plus, Search, LayoutGrid, List, Loader2, Sparkles,
} from 'lucide-react'
import SmartScheduleModal from '../components/SmartScheduleModal'
import { fmtDate, STATUS_LABELS, PRIORITY_LABELS, extractErr} from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import _DocumentsPanel from '../components/DocumentsPanel'
import _AIInlineEditor from '../components/AIInlineEditor'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'

// Type-relaxed aliases for legacy JS-inferred components (runtime unchanged)
const Badge: any = _Badge
const Avatar: any = _Avatar
const VirtualList: any = _VirtualList
const DocumentsPanel: any = _DocumentsPanel
const AIInlineEditor: any = _AIInlineEditor
const STATUS_LABELS_MAP: Record<string, string> = STATUS_LABELS as any
// Revisión 2026-11: las cabeceras del tablero salían en castellano con la interfaz en
// otro idioma (STATUS_LABELS es una tabla fija); estas son las claves de i18n.
const CLAVE_DE_ESTADO: Record<string, string> = {
  backlog: 'tasks.status_backlog', todo: 'tasks.status_todo', in_progress: 'tasks.status_in_progress',
  in_review: 'tasks.status_review', blocked: 'tasks.status_blocked', done: 'tasks.status_done', cancelled: 'tasks.status_cancelled',
}

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

function onKeyboardActivate(event: React.KeyboardEvent, action: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}


const STATUSES = ['todo', 'in_progress', 'blocked', 'in_review', 'done']
// Tope de tareas que se piden (el máximo del endpoint); si hay más, se avisa.
const TAREAS_MAXIMAS = 500
const _STATUS_ICONS = { todo: '○', in_progress: '◑', blocked: '✕', in_review: '◐', done: '●' }

const PRIORITIES = Object.entries(PRIORITY_LABELS).map(([v, l]) => ({ value: v, label: l }))
const TASK_STATUSES = [
  { value: 'open', label: 'Abiertas' },
  ...STATUSES.map(v => ({ value: v, label: STATUS_LABELS_MAP[v] })),
]

function TaskKanbanCard({ task, onTaskClick, onTaskDragStart }: { task: any; onTaskClick: (t: any) => void; onTaskDragStart?: (e: any, task: any, onStarted: () => void) => void }) {
  const wasDragged = useRef(false)
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${task.title} — ${STATUS_LABELS_MAP[task.status] || task.status}`}
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
          <span style={{ fontSize: "var(--text-xs)", color: (task.real_hours ?? 0) > (task.estimated_hours ?? 0) ? 'var(--danger)' : 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>
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

/** Cambios de estado de la tarea, con quién, cuándo y el motivo al reabrir. */
function HistorialDeMovimientos({ taskId }: { taskId: string }) {
  const t = useAppT()
  const { data = [], isLoading } = useQuery<any[]>({
    queryKey: ['task-movement-log', taskId],
    queryFn: () => tasksApi.movementLog(taskId).then((r: any) => r.data?.items ?? r.data ?? []),
  })
  if (isLoading) return <Loader2 size={14} style={{ animation: 'spin 0.7s linear infinite' }} />
  if (!data.length) return <p style={{ color: 'var(--text-2)', fontSize: 'var(--text-base)' }}>{t('tasks.historial_vacio')}</p>
  return (
    <ol style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {data.map((m: any) => (
        <li key={m.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--surface-4)', fontSize: 'var(--text-sm)' }}>
          <strong>{m.from_status ? t(CLAVE_DE_ESTADO[m.from_status] || m.from_status) : '—'} → {t(CLAVE_DE_ESTADO[m.to_status] || m.to_status)}</strong>
          <span style={{ color: 'var(--text-3)' }}> · {m.moved_by?.full_name || '—'} · {fmtDate(m.moved_at)}</span>
          {m.reason && <div style={{ color: 'var(--text-2)', marginTop: 2 }}>{t('tasks.historial_motivo', { motivo: m.reason })}</div>}
        </li>
      ))}
    </ol>
  )
}

/** Alta rápida al pie de una columna (revisión 2026-11, traída de la pantalla Kanban). */
function AltaRapida({ onCrear }: { onCrear: (titulo: string) => Promise<unknown> }) {
  const t = useAppT()
  const [abierta, setAbierta] = useState(false)
  const [titulo, setTitulo] = useState('')
  const enviar = async () => {
    if (!titulo.trim()) return
    await onCrear(titulo.trim()); setTitulo(''); setAbierta(false)
  }
  if (!abierta) return (
    <button type="button" onClick={() => setAbierta(true)}
      style={{ width: '100%', marginTop: 8, padding: '8px 10px', border: '1px dashed var(--surface-5)', borderRadius: 8, background: 'transparent', color: 'var(--text-3)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-sm)', textAlign: 'left' }}>
      + {t('tasks.kanban_alta_rapida')}
    </button>
  )
  return (
    <input autoFocus value={titulo} placeholder={t('tasks.kanban_alta_titulo')} aria-label={t('tasks.kanban_alta_titulo')}
      onChange={e => setTitulo(e.target.value)} onBlur={() => !titulo && setAbierta(false)}
      onKeyDown={e => { if (e.key === 'Enter') enviar(); if (e.key === 'Escape') { setAbierta(false); setTitulo('') } }}
      className="ds-input" style={{ marginTop: 8, width: '100%', boxSizing: 'border-box' }} />
  )
}

function KanbanColumn({ status, tasks, onTaskClick, onTaskDragStart, onColumnEnter, onColumnLeave, dragOver, wipLimit, onSetWip, onCrear }: { status: string; tasks: any[]; onTaskClick: (t: any) => void; onTaskDragStart?: any; onColumnEnter?: any; onColumnLeave?: any; dragOver?: boolean; wipLimit?: number | null; onSetWip?: (n: number | null) => void; onCrear?: (titulo: string) => Promise<unknown> }) {
  const t = useAppT()
  const pasado = !!wipLimit && tasks.length > wipLimit
  const colors: Record<string, string> = { backlog: 'var(--text-3)', todo: 'var(--text-2)', in_progress: 'var(--accent)', blocked: 'var(--danger)', in_review: 'var(--warning)', done: 'var(--success)' }
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
          {CLAVE_DE_ESTADO[status] ? t(CLAVE_DE_ESTADO[status]) : STATUS_LABELS_MAP[status]}
        </span>
        <span title={wipLimit ? t('tasks.kanban_wip_titulo', { n: wipLimit }) : undefined}
          style={{ marginLeft: 'auto', fontSize: "var(--text-xs)", background: pasado ? 'var(--danger-bg)' : 'var(--surface-4)', color: pasado ? 'var(--danger)' : 'var(--text-2)', borderRadius: 10, padding: '1px 7px', fontWeight: pasado ? 700 : 400 }}>
          {tasks.length}{wipLimit ? ` / ${wipLimit}` : ''}
        </span>
        {onSetWip && (
          <button type="button" aria-label={t('tasks.kanban_wip_editar')} title={t('tasks.kanban_wip_editar')}
            onClick={() => {
              const v = window.prompt(t('tasks.kanban_wip_pregunta'), wipLimit ? String(wipLimit) : '')
              if (v === null) return
              const n = parseInt(v, 10)
              onSetWip(Number.isFinite(n) && n > 0 ? n : null)
            }}
            style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 'var(--text-2xs)', padding: 0, fontFamily: 'inherit' }}>WIP</button>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {tasks.map((task: any) => (
          <TaskKanbanCard
            key={task.id}
            task={task}
            onTaskClick={onTaskClick}
            onTaskDragStart={onTaskDragStart}
          />
        ))}
      </div>
      {onCrear && <AltaRapida onCrear={onCrear} />}
    </div>
  )
}

function useWorkflowStatusOptions(projectId: any, t: any) {
  const { data } = useQuery<any>({
    queryKey: ['project-workflow', projectId],
    queryFn: () => projectWorkflowsApi.get(projectId).then(r => r.data).catch(() => null),
    enabled: !!projectId,
    staleTime: 60000,
    retry: false,
  })
  if ((data?.states?.length ?? 0) > 0) {
    return data.states
      .slice()
      .sort((a: any, b: any) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
      .map((s: any) => ({ value: s.value, icon: s.icon || '○', label: s.name }))
  }
  return [
    { value: 'backlog',     icon: '○', label: t('tasks.status_backlog')     },
    { value: 'todo',        icon: '○', label: t('tasks.status_todo')        },
    { value: 'in_progress', icon: '◑', label: t('tasks.status_in_progress') },
    { value: 'in_review',   icon: '◐', label: t('tasks.status_review')      },
    { value: 'blocked',     icon: '✕', label: t('tasks.status_blocked')     },
    { value: 'done',        icon: '●', label: t('tasks.status_done')        },
    { value: 'cancelled',   icon: '✕', label: t('tasks.status_cancelled')   },
  ]
}

function TaskDetailModal({ task, open, onClose }: { task: any; open: boolean; onClose: () => void }) {
  const puedeBorrar = useAuth().hasRole('admin', 'pm')
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { invalidate: _invalidate } = useInvalidate()
  const [tab, setTab]         = useState('detail')  // detail | comments | docs
  const [isEditing, setIsEditing] = useState(false)
  const [comment, setComment] = useState('')
  const [form, setForm]       = useState<any>(null)
  const [semSuggestion, setSemSuggestion] = useState<any>(null)
  const [semEffort, setSemEffort]         = useState<any>(null)
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
        issue_type:      task.issue_type      || '',
      })
    }
  }, [task])

  const { data: users = [] } = useQuery<any[]>({
    queryKey: ['users'],
    queryFn: () => import('../services/api').then(m => m.usersApi.list().then(r => r.data)),
  })

  const statusOptions = useWorkflowStatusOptions(task?.project_id, t)

  // Auditoría 2026-11: el catálogo de /issue-types no llegaba a las tareas.
  const { data: issueTypes = [] } = useQuery<any[]>({
    queryKey: ['issue-types', task?.project_id],
    queryFn: () => issueTypesApi.list(task.project_id).then(r => (Array.isArray(r.data) ? r.data : [])).catch(() => []),
    enabled: !!task?.project_id,
    retry: false,
  })
  const { data: customFields = [] } = useQuery<any[]>({
    queryKey: ['custom-fields', task?.project_id],
    queryFn: () => customFieldsApi.list(task.project_id).then(r => r.data).catch(() => []),
    enabled: !!task?.project_id,
    retry: false,
  })
  const { data: rawCustomValues } = useQuery<any[]>({
    queryKey: ['custom-field-values', task?.id],
    queryFn: () => customFieldsApi.getValues(task.project_id, task.id).then(r => r.data).catch(() => []),
    enabled: !!task?.id && !!task?.project_id,
    retry: false,
  })
  const [customValues, setCustomValues] = useState<Record<string, any>>({})
  useEffect(() => {
    const map: Record<string, any> = {}
    ;(rawCustomValues ?? []).forEach((v: any) => { map[v.field_id] = v.value ?? '' })
    setCustomValues(map)
  }, [rawCustomValues])

  const { mutate: saveTask, isPending: saving } = useMutation({
    mutationFn: async ({ taskData, cfValues, cfFields, taskId, projectId }: any) => {
      await tasksApi.update(taskId, taskData)
      if (cfFields.length > 0) {
        const payload = cfFields.map((f: any) => ({ field_id: f.id, value: cfValues[f.id] ?? null }))
        await customFieldsApi.setValues(projectId, taskId, payload)
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); qc.invalidateQueries({ queryKey: ['dash-my-tasks'] }); qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] }); qc.invalidateQueries({ queryKey: ['cal-tasks'] }); qc.invalidateQueries({ queryKey: ['kanban-board'] }); setIsEditing(false); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('common.error'))),
  })

  const { mutate: deleteTask, isPending: deleting } = useMutation({
    mutationFn: () => tasksApi.delete(task.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); qc.invalidateQueries({ queryKey: ['dash-my-tasks'] }); qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] }); qc.invalidateQueries({ queryKey: ['cal-tasks'] }); qc.invalidateQueries({ queryKey: ['kanban-board'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('common.error'))),
  })

  const { mutate: addComment, isPending: commenting } = useMutation({
    mutationFn: ({ id, content }: any) => tasksApi.comment(id, { content } as any),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); setComment('') },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
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
      setForm((f: any) => ({ ...f, assignee_id: semSuggestion.suggested_user_id }))
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
      setForm((f: any) => ({ ...f, estimated_hours: String(semEffort.base_hours) }))
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
      issue_type:      task.issue_type      || '',
    })
    setSemSuggestion(null); setSemEffort(null)
    setIsEditing(false)
  }

  const set = (k: string) => (e: any) => setForm((f: any) => ({ ...f, [k]: e.target.value }))
  const fs: CSSProperties  = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties  = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }
  const COMPLEXITY_COLORS: Record<string, string> = { simple: 'var(--success)', medium: 'var(--warning)', complex: 'var(--danger)' }
  const STATUS_LABEL_MAP: Record<string, string> = { backlog: t('tasks.status_backlog'), todo: t('tasks.status_todo'), in_progress: t('tasks.status_in_progress'), in_review: t('tasks.status_review'), blocked: t('tasks.status_blocked'), done: t('tasks.status_done'), cancelled: t('tasks.status_cancelled') }
  const PRIORITY_COLOR: Record<string, string>   = { critical: 'var(--danger)', high: 'var(--warning)', medium: 'var(--accent)', low: 'var(--text-2)' }
  const STATUS_COLOR: Record<string, string>     = { done: 'var(--success)', blocked: 'var(--danger)', in_progress: 'var(--accent)', in_review: 'var(--warning)', todo: 'var(--text-2)', backlog: 'var(--text-3)', cancelled: 'var(--text-3)' }
  const bodyPad = '20px 20px 24px'
  const tabPanelStyle: CSSProperties = { paddingTop: 8 }

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
          { id: 'history',  label: t('tasks.tab_historial') },
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
              background: alpha(STATUS_COLOR[task.status], '20'), color: STATUS_COLOR[task.status] }}>
              {STATUS_LABEL_MAP[task.status] || task.status}
            </span>
            <span style={{ fontSize: "var(--text-sm)", padding: '3px 12px', borderRadius: 20, fontWeight: 700,
              background: alpha(PRIORITY_COLOR[task.priority], '20'), color: PRIORITY_COLOR[task.priority] }}>
              {(PRIORITY_LABELS as any)[task.priority] || task.priority}
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
          {customFields.length > 0 && (rawCustomValues?.length ?? 0) > 0 && (
            <div style={{ marginBottom: 14, borderTop: '1px solid var(--surface-4)', paddingTop: 14 }}>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>{t('tasks.custom_fields_label')}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                {customFields.map((f: any) => {
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
            {/* Borrar exige admin o pm en el servidor (revisión 2026-11) */}
            {puedeBorrar ? (
            <button onClick={() => { openConfirmGlobal({ message: `${t('common.are_you_sure')} ${t('common.delete')}?`, onConfirm: () => deleteTask(), danger: true }) }} disabled={deleting}
              style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--danger-border)', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
              {deleting ? t('tasks.deleting') : `🗑 ${t('common.delete')}`}
            </button>
            ) : <span />}
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
              {statusOptions.map((o: any) => (
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
              {users.map((u: any) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
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

          <div>
            <label style={ls} htmlFor="task-issue-type">{t('tasks.issue_type')}</label>
            <select id="task-issue-type" value={form.issue_type} onChange={set('issue_type')} style={fs}>
              <option value="">—</option>
              {issueTypes.filter((it: any) => it.is_active !== false).map((it: any) => (
                <option key={it.id} value={it.value}>{it.icon} {it.name}</option>
              ))}
            </select>
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
            <AIInlineEditor value={form.description} onChange={(val: any) => set('description')({ target: { value: val } })} rows={4} style={{ ...fs, resize: 'vertical', lineHeight: 1.6 }} />
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
                {customFields.map((f: any) => (
                  <div key={f.id} style={(f.field_type === 'text' || f.field_type === 'url') ? { gridColumn: '1/-1' } : {}}>
                    <label style={ls}>{f.name}{f.is_required ? ' *' : ''}</label>
                    {f.field_type === 'select' ? (
                      <select value={customValues[f.id] ?? ''} onChange={e => setCustomValues((v: any) => ({ ...v, [f.id]: e.target.value }))} style={fs}>
                        <option value="">{t('tasks.select_option')}</option>
                        {(f.options || []).map((o: any) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : f.field_type === 'boolean' ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 4 }}>
                        <input type="checkbox" checked={customValues[f.id] === 'true'} onChange={e => setCustomValues((v: any) => ({ ...v, [f.id]: e.target.checked ? 'true' : 'false' }))} style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
                        <span style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{customValues[f.id] === 'true' ? t('common.yes') : t('common.no')}</span>
                      </div>
                    ) : (
                      <input
                        type={f.field_type === 'number' ? 'number' : f.field_type === 'date' ? 'date' : f.field_type === 'url' ? 'url' : 'text'}
                        value={customValues[f.id] ?? ''}
                        onChange={e => setCustomValues((v: any) => ({ ...v, [f.id]: e.target.value }))}
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
            {/* Borrar exige admin o pm en el servidor (revisión 2026-11) */}
            {puedeBorrar ? (
            <button onClick={() => { openConfirmGlobal({ message: `${t('common.are_you_sure')} ${t('common.delete')}?`, onConfirm: () => deleteTask(), danger: true }) }} disabled={deleting}
              style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--danger-border)', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
              {deleting ? t('tasks.deleting') : `🗑 ${t('common.delete')}`}
            </button>
            ) : <span />}
            <div style={{ display: 'flex', gap: 8 }}>
              <Button variant="secondary" onClick={cancelEdit}>{t('common.cancel')}</Button>
              <Button onClick={() => saveTask({ taskData: { ...form, issue_type: form.issue_type || null }, cfValues: customValues, cfFields: customFields, taskId: task.id, projectId: task.project_id })} disabled={saving || !form.title}>
                {saving ? t('common.saving') : `💾 ${t('tasks.save_changes')}`}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── HISTORIAL de movimientos (revisión 2026-11: lo enseñaba la pantalla Kanban) ── */}
      {tab === 'history' && <HistorialDeMovimientos taskId={task.id} />}

      {/* ── COMENTARIOS ── */}
      {tab === 'comments' && (
        <div style={tabPanelStyle}>
          {(!task.comments || task.comments.length === 0) ? (
            <p style={{ color: 'var(--text-2)', fontSize: "var(--text-base)", marginBottom: 16 }}>{t('tasks.no_comments')}</p>
          ) : (
            <div style={{ marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {task.comments.map((c: any) => (
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
  const traducir = useAppT()
  const t = useAppT()
  const { hasRole } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  // ── Kanban drag-and-drop state ────────────────────────────────────────────
  const dragTask      = useRef<any>(null)
  const ghostRef      = useRef<any>(null)
  const dropTargetRef = useRef<any>(null)
  const [dropTarget, setDropTarget] = useState<any>(null)

  const cleanupGhost = useCallback(() => {
    if (ghostRef.current) { ghostRef.current.remove(); ghostRef.current = null }
  }, [])

  const { mutate: moveTaskStatus } = useMutation({
    mutationFn: ({ id, status, move_reason }: any) =>
      tasksApi.update(id, { status, ...(move_reason ? { move_reason } : {}) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban-board'] })
    },
    onError: (e: unknown) => toast.error((e as any)?.response?.data?.detail || 'Error al mover tarea'),
  })

  const requestMoveTask = useCallback((id: any, fromStatus: any, toStatus: any) => {
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

  const handleTaskDragStart = useCallback((e: any, task: any, onDragStarted: () => void) => {
    const startX = e.clientX
    const startY = e.clientY
    let dragging = false

    const onMove = (ev: any) => {
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
        } as any)
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
    // `requestMoveTask` se invoca dentro de onUp y no estaba declarada
    // (auditoría 2026-08, P1-6): los listeners capturaban una versión antigua
    // del callback, así que un arrastre podía mover la tarea con estado viejo.
  }, [cleanupGhost, requestMoveTask])

  const handleColumnEnter = useCallback((status: any) => {
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
  const sprintFilter   = searchParams.get('sprint') || ''
  const carriles       = searchParams.get('lanes') || ''
  const setTaskParam = (k: string, v: string) => setSearchParams(p => { const n = new URLSearchParams(p); v ? n.set(k, v) : n.delete(k); return n }, { replace: true })
  const setView           = (v: string) => setTaskParam('view', v === 'kanban' ? '' : v)
  const setProjectFilter  = (v: string) => setTaskParam('project_id', v)
  const setStatusFilter   = (v: string) => setTaskParam('status', v)
  const setSearch         = (v: string) => setTaskParam('search', v)
  const setPriorityFilter = (v: string) => setTaskParam('priority', v)
  const setAssigneeFilter = (v: string) => setTaskParam('assignee', v)
  const setSprintFilter   = (v: string) => setTaskParam('sprint', v)
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
  const [selectedTask, setSelectedTask] = useState<any>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [smartScheduleOpen, setSmartScheduleOpen] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())  // bulk selection
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

  const { data: projects = [] } = useQuery<any[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  // Revisión 2026-11: tablero y lista enseñan LAS MISMAS tareas (la misma consulta
  // y los mismos filtros). Antes el tablero con proyecto usaba otro endpoint que
  // ignoraba persona, vencidas y «mías», y la lista se cortaba en 50 sin avisar.
  const { data: tasksData, isLoading } = useQuery<{ items: any[]; total: number }>({
    queryKey: ['tasks', view, projectFilter, statusFilter, search, priorityFilter, assigneeFilter, overdueOnly, mineOnly, sprintFilter],
    queryFn: () => {
      const effectiveStatus = statusFilter === 'open'
        ? 'backlog,todo,in_progress,blocked,in_review'
        : (statusFilter || undefined)
      return tasksApi.list({
        project_id: projectFilter || undefined,
        status: view === 'kanban' ? undefined : effectiveStatus,
        search: search || undefined,
        priority: priorityFilter || undefined,
        assignee_id: assigneeFilter || undefined,
        overdue_only: overdueOnly || undefined,
        assigned_to_me: mineOnly || undefined,
        sprint_id: (projectFilter && sprintFilter) || undefined,
        page_size: TAREAS_MAXIMAS,
      } as any).then((r: any) => {
        const d: any = r.data
        const items = Array.isArray(d) ? d : (d?.items ?? [])
        const total = Number(r.headers?.['x-total-count'] ?? d?.total ?? items.length)
        return { items, total }
      })
    },
    placeholderData: (prev: any) => prev,
  })

  const projectOptions = projects.map((p: any) => ({ value: p.id, label: `${p.code} — ${p.name}` }))

  const flatTasks: any[] = tasksData?.items ?? []
  const cortadas = (tasksData?.total ?? 0) > flatTasks.length

  const { sort: taskSort, setSort: setTaskSort, sortedData: sortedTasks } = useSort(flatTasks, 'title')

  // Revisión 2026-11: sin proyecto el Kanban caía en una lista. Ahora agrupa por
  // estado las mismas tareas que mostraría la lista (con sus filtros).
  const agrupar = (lista: any[]) => lista.reduce((a: any, task: any) => {
    if (task.status !== 'cancelled') (a[task.status] = a[task.status] || []).push(task)
    return a
  }, STATUSES.reduce((a: any, s) => ({ ...a, [s]: [] }), {}))
  const kanbanColumns: any = agrupar(flatTasks)

  // ── Tablero: sprint, carriles y límites WIP (revisión 2026-11) ───────────────
  // Venían de la pantalla «Kanban» (/kanban-advanced), que enseñaba las mismas
  // tareas por estado; ahora es una sola. Carriles y WIP se guardan por proyecto
  // (`/cmdb/kanban/{proyecto}`): antes los límites vivían en memoria y se perdían.
  const puedeConfigurar = hasRole('admin', 'pm')
  const { data: sprintsDelProyecto = [] } = useQuery<any[]>({
    queryKey: ['sprints', projectFilter], enabled: !!projectFilter,
    queryFn: () => sprintsApi.list(projectFilter).then((r: any) => r.data?.items ?? r.data ?? []),
  })
  const { data: tablero } = useQuery<any>({
    queryKey: ['kanban-config', projectFilter], enabled: !!projectFilter,
    queryFn: () => cmdbApi.kanbanConfig(projectFilter).then((r: any) => r.data),
  })
  const carril = carriles || (projectFilter && tablero?.swimlane_by) || 'none'
  const limiteWip = (status: string): number | null =>
    (tablero?.columns || []).find((c: any) => c.status === status)?.wip_limit ?? null
  const guardarCarril = async (v: string) => {
    setTaskParam('lanes', v === 'none' ? '' : v)
    if (projectFilter && puedeConfigurar) {
      try { await cmdbApi.saveKanbanConfig(projectFilter, { swimlane_by: v }); qc.invalidateQueries({ queryKey: ['kanban-config', projectFilter] }) }
      catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
    }
  }
  const guardarWip = async (status: string, n: number | null) => {
    try {
      if (!tablero?.configured) await cmdbApi.saveKanbanConfig(projectFilter, { swimlane_by: carril })
      const col = (tablero?.columns || []).find((c: any) => c.status === status)
      if (col) await cmdbApi.updateKanbanColumn(col.id, { status, wip_limit: n })
      else await cmdbApi.addKanbanColumn(projectFilter, { status, wip_limit: n })
      qc.invalidateQueries({ queryKey: ['kanban-config', projectFilter] })
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
  const crearEnColumna = (status: string) => async (titulo: string) => {
    try {
      await tasksApi.create({ title: titulo, status, project_id: projectFilter } as any)
      qc.invalidateQueries({ queryKey: ['tasks'] })
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
  const nombreDePrioridad = (p: string) => PRIORITIES.find(x => x.value === p)?.label || p
  const filasDelTablero: { id: string; titulo: string | null; tareas: any[] }[] = (() => {
    if (carril === 'assignee') {
      const g: Record<string, { id: string; titulo: string; tareas: any[] }> = {}
      for (const task of flatTasks) {
        const k = task.assignee_id || '__sin'
        g[k] = g[k] || { id: k, titulo: task.assignee?.full_name || t('tasks.no_assignee'), tareas: [] }
        g[k].tareas.push(task)
      }
      return Object.values(g).sort((a, b) => a.titulo.localeCompare(b.titulo))
    }
    if (carril === 'priority') {
      return ['critical', 'high', 'medium', 'low']
        .map(p => ({ id: p, titulo: nombreDePrioridad(p), tareas: flatTasks.filter((x: any) => x.priority === p) }))
        .filter(f => f.tareas.length)
    }
    return [{ id: 'todas', titulo: null, tareas: flatTasks }]
  })()
  const buscador = useRef<HTMLInputElement | null>(null)
  useEffect(() => {
    const alPulsar = (e: KeyboardEvent) => {
      const dentro = (e.target as HTMLElement)?.closest?.('input, textarea, select, [contenteditable=true]')
      if (e.key === '/' && !dentro) { e.preventDefault(); buscador.current?.focus() }
    }
    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  }, [])
  // El servidor devuelve «backlog»; antes no tenía columna y esas tareas no se veían.
  const kanbanStatuses = (kanbanColumns.backlog?.length ? ['backlog'] : []).concat(STATUSES)

  // ── Bulk operations ──────────────────────────────────────────────────────
  const { data: allUsers = [] } = useQuery<any[]>({
    queryKey: ['users'],
    queryFn: () => import('../services/api').then(m => m.usersApi.list().then(r => r.data)),
    staleTime: 120000,
  })

  const { mutate: bulkMutate, isPending: bulkPending } = useMutation({
    mutationFn: (payload: any) => tasksApi.bulkUpdate(payload),
    onSuccess: (res: any) => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-my-tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] })
      qc.invalidateQueries({ queryKey: ['cal-tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban-board'] })
      const data: any = res.data
      const n = data?.updated ?? 0
      const s = data?.skipped?.length ?? 0
      toast.success(`${n} tarea${n !== 1 ? 's' : ''} actualizad${n !== 1 ? 'as' : 'a'}${s > 0 ? ` · ${s} omitid${s !== 1 ? 'as' : 'a'}` : ''}`)
      setSelected(new Set())
      setBulkStatus(''); setBulkAssignee(''); setBulkPriority('')
    },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error en actualización masiva')),
  })

  const toggleSelect = (id: string) => setSelected(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })
  const toggleAll = () => setSelected(prev =>
    prev.size === flatTasks.length ? new Set<string>() : new Set<string>(flatTasks.map((t: any) => t.id))
  )
  const applyBulk = () => {
    if (selected.size === 0) return
    const payload: any = { task_ids: [...selected] }
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
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', width: isMobile ? '100%' : 'auto' }}>
            <div className="ds-segmented" role="group" aria-label="Vista">
              <button type="button" onClick={() => setView('kanban')} aria-pressed={view === 'kanban'}>
                <LayoutGrid size={12} /> Kanban
              </button>
              <button type="button" onClick={() => setView('list')} aria-pressed={view === 'list'}>
                <List size={12} /> Lista
              </button>
            </div>
            {hasRole('admin', 'pm', 'team_lead') && (
              <Button onClick={() => setShowCreate(true)}>
                <Plus size={13} /> {t('tasks.new_task')}
              </Button>
            )}
            {/* I27: Auto-planificar. Aplicar las fechas (bulk-dates) exige admin o pm. */}
            {hasRole('admin', 'pm') && (
              <Button
                variant="subtle"
                onClick={() => setSmartScheduleOpen(true)}
                title={traducir('tasks.sugerir_fechas_para_tareas_sin_planificar_usando')}
              >
                <Sparkles size={13} /> Auto-planificar
              </Button>
            )}
          </div>
        }
      />

      {/* Quick filter pills */}
      {quickFilterPills.length > 0 && (
        <div className="ds-row-wrap" style={{ marginBottom: 'var(--space-3)' }}>
          {quickFilterPills.map((pill: any) => (
            <span key={pill.key} className="ds-pill ds-pill--accent">
              {pill.label}
              <button type="button" onClick={pill.onClear} aria-label={`Quitar filtro ${pill.label}`}
                style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0, display: 'inline-flex', alignItems: 'center' }}>
                <X size={11} />
              </button>
            </span>
          ))}
          <button type="button" onClick={clearQuickFilters} className="ds-pill"
            style={{ cursor: 'pointer', fontFamily: 'inherit' }}>
            {traducir('tasks.limpiar_filtros_rapidos')}
          </button>
        </div>
      )}

      {/* Filters toolbar */}
      <div className="ds-toolbar" style={{ marginBottom: 'var(--space-5)' }}>
        <div style={{ position: 'relative', flex: '2 1 240px', minWidth: 200 }}>
          <Search size={14} aria-hidden style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-3)', pointerEvents: 'none',
          }} />
          <input ref={buscador} value={search} onChange={e => setSearch(e.target.value)}
            placeholder={t('tasks.search_placeholder')} aria-keyshortcuts="/"
            className="ds-input"
            style={{ paddingLeft: 32 }} />
        </div>
        <select value={projectFilter} onChange={e => setProjectFilter(e.target.value)}
          className="ds-input" style={{ flex: '1 1 180px', minWidth: 160 }}>
          <option value="">{t('tasks.all_projects')}</option>
          {projectOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}
          className="ds-input" style={{ width: 'auto', minWidth: 140, color: priorityFilter ? 'var(--warning)' : 'var(--text-1)' }}>
          <option value="">{t('tasks.filter_priority')}</option>
          {PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <select value={assigneeFilter} onChange={e => setAssigneeFilter(e.target.value)}
          className="ds-input" style={{ width: 'auto', minWidth: 140, color: assigneeFilter ? 'var(--accent)' : 'var(--text-1)' }}>
          <option value="">{t('tasks.all_assignees')}</option>
          {allUsers.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
        </select>
        {projectFilter && sprintsDelProyecto.length > 0 && (
          <select aria-label={t('tasks.kanban_sprint')} value={sprintFilter} onChange={e => setSprintFilter(e.target.value)}
            className="ds-input" style={{ width: 'auto', minWidth: 140, color: sprintFilter ? 'var(--accent)' : 'var(--text-1)' }}>
            <option value="">{t('tasks.kanban_todos_los_sprints')}</option>
            {sprintsDelProyecto.map((sp: any) => <option key={sp.id} value={sp.id}>{sp.name}</option>)}
          </select>
        )}
        {view === 'kanban' && (
          <select aria-label={t('tasks.kanban_carriles')} value={carril} onChange={e => guardarCarril(e.target.value)}
            className="ds-input" style={{ width: 'auto', minWidth: 140 }}>
            <option value="none">{t('tasks.kanban_sin_carriles')}</option>
            <option value="assignee">{t('tasks.kanban_carril_persona')}</option>
            <option value="priority">{t('tasks.kanban_carril_prioridad')}</option>
          </select>
        )}
        {view === 'list' && (
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="ds-input" style={{ width: 'auto', minWidth: 140 }}>
            <option value="">{t('tasks.filter_status')}</option>
            {TASK_STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        )}
      </div>

      {/* ── Bulk Action Bar ─────────────────────────────────────────────── */}
      {selected.size > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
          padding: '8px 14px', marginBottom: 'var(--space-3)',
          background: 'var(--accent-muted)',
          border: '1px solid var(--accent-border)',
          borderRadius: 'var(--radius-md)',
          flexWrap: 'wrap',
        }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--accent)', whiteSpace: 'nowrap' }}>
            <CheckSquare size={13} /> {selected.size} {t('tasks.selected')}
          </span>
          <div style={{ width: 1, height: 20, background: 'var(--surface-4)' }} />
          <select value={bulkStatus} onChange={e => setBulkStatus(e.target.value)}
            className="ds-input" style={{ width: 'auto', padding: '6px 10px' }}>
            <option value="">{t('tasks.bulk_status_ph')}</option>
            <option value="todo">{t('tasks.status_todo')}</option>
            <option value="in_progress">{t('tasks.status_in_progress')}</option>
            <option value="in_review">{t('tasks.status_review')}</option>
            <option value="blocked">{t('tasks.status_blocked')}</option>
            <option value="done">{t('tasks.status_done')}</option>
          </select>
          <select value={bulkPriority} onChange={e => setBulkPriority(e.target.value)}
            className="ds-input" style={{ width: 'auto', padding: '6px 10px' }}>
            <option value="">{t('tasks.bulk_priority_ph')}</option>
            <option value="low">{t('tasks.priority_low')}</option>
            <option value="medium">{t('tasks.priority_medium')}</option>
            <option value="high">{t('tasks.priority_high')}</option>
            <option value="critical">{t('tasks.priority_critical')}</option>
          </select>
          <select value={bulkAssignee} onChange={e => setBulkAssignee(e.target.value)}
            className="ds-input" style={{ width: 'auto', padding: '6px 10px' }}>
            <option value="">{t('tasks.bulk_assignee_ph')}</option>
            {allUsers.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
          <Button size="sm" onClick={applyBulk}
            disabled={bulkPending || (!bulkStatus && !bulkPriority && !bulkAssignee)}>
            {bulkPending
              ? <><Loader2 size={12} style={{ animation: 'spin 0.7s linear infinite' }} /> Aplicando…</>
              : t('tasks.bulk_apply')}
          </Button>
          <Button size="sm" variant="secondary"
            onClick={() => { setSelected(new Set()); setBulkStatus(''); setBulkPriority(''); setBulkAssignee('') }}>
            {t('common.cancel')}
          </Button>
        </div>
      )}

      {cortadas && (
        <div role="status" style={{ marginBottom: 'var(--space-3)', fontSize: 'var(--text-sm)', color: 'var(--warning)' }}>
          {t('tasks.mostrando_de', { n: flatTasks.length, total: tasksData?.total ?? 0 })}
        </div>
      )}
      {isLoading ? (
        <SkeletonTable rows={10} />
      ) : view === 'kanban' ? (
        flatTasks.length === 0 && !projectFilter ? (
          <EmptyState icon="tasks" title={t('tasks.no_tasks')} description={t('tasks.col_task')} ctaLabel={t('tasks.new_task')} onCta={() => setShowCreate(true)} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            {filasDelTablero.map(fila => {
              const columnas = agrupar(fila.tareas)
              return (
                <section key={fila.id} aria-label={fila.titulo || undefined}>
                  {fila.titulo && (
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-2)', margin: '0 4px 6px' }}>
                      {fila.titulo} <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>· {fila.tareas.length}</span>
                    </div>
                  )}
                  <div style={{ display: 'flex', flexDirection: isCompact ? 'column' : 'row', gap: 12, overflowX: isCompact ? 'visible' : 'auto', paddingBottom: 8 }}>
                    {kanbanStatuses.map(status => (
                      <KanbanColumn
                        key={status}
                        status={status}
                        tasks={columnas[status] || []}
                        onTaskClick={setSelectedTask}
                        onTaskDragStart={handleTaskDragStart}
                        onColumnEnter={() => handleColumnEnter(status)}
                        onColumnLeave={handleColumnLeave}
                        dragOver={dropTarget === status}
                        wipLimit={fila.titulo ? null : limiteWip(status)}
                        onSetWip={projectFilter && puedeConfigurar && !fila.titulo ? (n => guardarWip(status, n)) : undefined}
                        onCrear={projectFilter && !fila.titulo ? crearEnColumna(status) : undefined}
                      />
                    ))}
                  </div>
                </section>
              )
            })}
          </div>
        )
      ) : (
        flatTasks.length === 0 ? (
          <EmptyState icon="search" title={t('common.no_results')} description={t('tasks.filter_status')} />
        ) : isCompact ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {sortedTasks.map((task) => {
              const proj = projects.find(p => p.id === task.project_id)
              return (
                <div key={task.id}
                  onClick={() => setSelectedTask(task)}
                  onKeyDown={e => onKeyboardActivate(e, () => setSelectedTask(task))}
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
                      checked={selected.has(task.id)}
                      onChange={() => toggleSelect(task.id)}
                      onClick={e => e.stopPropagation()}
                      style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
                    />
                    <div style={{ fontSize: "var(--text-base)", fontWeight: 700, flex: 1 }}>{task.title}</div>
                    <Badge label={task.priority} />
                  </div>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                    <span>{task.code}</span>
                    <span>{proj ? proj.code : t('tasks.no_project')}</span>
                    <span>{task.assignee?.full_name || t('tasks.no_assignee')}</span>
                    <span>{task.estimated_hours ? `${task.estimated_hours}h est.` : t('tasks.no_estimate')}</span>
                    <span>{task.real_hours?.toFixed(1) ?? 0}h real</span>
                  </div>
                  <div style={{ marginTop: 8 }}>
                    <Badge label={task.status} />
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div data-export-table="tasks-list" className="ds-card" style={{ padding: 0, overflow: 'hidden' }}>
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
              renderRow={(t: any) => (
                <div
                  onClick={() => setSelectedTask(t)}
                  onKeyDown={e => onKeyboardActivate(e, () => setSelectedTask(t))}
                  role="button"
                  tabIndex={0}
                  style={{ display: 'grid', gridTemplateColumns: '28px 2.5fr 1.5fr 1fr 80px 80px 100px 100px', gap: 16, padding: '14px 20px', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', cursor: 'pointer', transition: 'background 0.1s', alignItems: 'center', background: selected.has(t.id) ? 'var(--accent-muted)' : 'transparent' }}
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
      <SmartScheduleModal
        open={smartScheduleOpen}
        onClose={() => setSmartScheduleOpen(false)}
        projectId={projectFilter || null}
        projectName={projects?.find(p => p.id === projectFilter)?.name}
      />
    </PageShell>
  )
}

function CreateTaskModal({ open, onClose, projects }: { open: boolean; onClose: () => void; projects: any[] }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: users = [] } = useQuery<any[]>({
    queryKey: ['users'],
    queryFn: () => import('../services/api').then(m => m.usersApi.list().then(r => r.data)),
  })
  const [form, setForm] = useState<any>({
    title: '', project_id: '', status: 'todo', priority: 'medium',
    estimated_hours: '', start_date: '', due_date: '', description: '', assignee_id: '',
  })
  const [semSuggestion, setSemSuggestion] = useState<any>(null)
  const [semEffort, setSemEffort] = useState<any>(null)
  const [suggesting, setSuggesting] = useState(false)
  const [pendingSuggestion, setPendingSuggestion] = useState<any>(null)
  const [customValues, setCustomValues] = useState<Record<string, any>>({})

  const { data: customFields = [] } = useQuery<any[]>({
    queryKey: ['custom-fields', form.project_id],
    queryFn: () => customFieldsApi.list(form.project_id).then(r => r.data).catch(() => []),
    enabled: !!form.project_id,
    retry: false,
  })

  const statusOptions = useWorkflowStatusOptions(form.project_id, t)

  const { mutate, isPending } = useMutation({
    mutationFn: async ({ taskData, cfValues, cfFields }: any) => {
      const res = await tasksApi.create(taskData)
      const task = res.data
      if (cfFields.length > 0 && task?.id) {
        const payload = cfFields.map((f: any) => ({ field_id: f.id, value: cfValues[f.id] ?? null }))
        await customFieldsApi.setValues(task.project_id, task.id, payload)
      }
      return task
    },
    onSuccess: (newTask: any) => {
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
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-my-tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] })
      qc.invalidateQueries({ queryKey: ['cal-tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban-board'] })
      onClose()
      setForm({ title: '', project_id: '', status: 'todo', priority: 'medium', estimated_hours: '', start_date: '', due_date: '', description: '', assignee_id: '' })
      setCustomValues({})
      setSemSuggestion(null); setSemEffort(null); setPendingSuggestion(null)
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const set = (k: string) => (e: any) => setForm((f: any) => ({ ...f, [k]: e.target.value }))
  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }

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
    } catch (e) { setSemSuggestion({ error: (e as any)?.response?.data?.detail || 'Error' }) }
    finally { setSuggesting(false) }
  }

  const acceptSuggestion = () => {
    if (semSuggestion?.suggested_user_id) {
      setForm((f: any) => ({ ...f, assignee_id: semSuggestion.suggested_user_id }))
      // Store suggestion so we can persist SemAssignment once the task is created (task.id is known)
      setPendingSuggestion({ ...semSuggestion })
    }
    if (semEffort?.base_hours && !form.estimated_hours)
      setForm((f: any) => ({ ...f, estimated_hours: String(semEffort.base_hours) }))
    setSemSuggestion(null); setSemEffort(null)
  }

  const COMPLEXITY_COLORS: Record<string, string> = { simple: 'var(--success)', medium: 'var(--warning)', complex: 'var(--danger)' }

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
            {projects.map((p: any) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>{t('common.status')}</label>
          <select value={form.status} onChange={set('status')} style={fs}>
            {statusOptions.map((o: any) => (
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
            {users.map((u: any) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
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
          <AIInlineEditor value={form.description} onChange={(val: any) => set('description')({ target: { value: val } })} rows={3} placeholder={t('common.description')} style={{ ...fs, resize: 'vertical' }} />
        </div>
        {/* Campos personalizados del proyecto */}
        {customFields.length > 0 && (
          <div style={{ gridColumn: '1/-1', borderTop: '1px solid var(--surface-4)', paddingTop: 14 }}>
            <label style={{ ...ls, marginBottom: 10 }}>{t('tasks.custom_fields_label')}</label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {customFields.map((f: any) => (
                <div key={f.id} style={(f.field_type === 'text' || f.field_type === 'url') ? { gridColumn: '1/-1' } : {}}>
                  <label style={ls}>{f.name}{f.is_required ? ' *' : ''}</label>
                  {f.field_type === 'select' ? (
                    <select value={customValues[f.id] ?? ''} onChange={e => setCustomValues((v: any) => ({ ...v, [f.id]: e.target.value }))} style={fs}>
                      <option value="">{t('tasks.select_option')}</option>
                      {(f.options || []).map((o: any) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : f.field_type === 'boolean' ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 4 }}>
                      <input type="checkbox" checked={customValues[f.id] === 'true'} onChange={e => setCustomValues((v: any) => ({ ...v, [f.id]: e.target.checked ? 'true' : 'false' }))} style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
                      <span style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{customValues[f.id] === 'true' ? t('common.yes') : t('common.no')}</span>
                    </div>
                  ) : (
                    <input
                      type={f.field_type === 'number' ? 'number' : f.field_type === 'date' ? 'date' : f.field_type === 'url' ? 'url' : 'text'}
                      value={customValues[f.id] ?? ''}
                      onChange={e => setCustomValues((v: any) => ({ ...v, [f.id]: e.target.value }))}
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