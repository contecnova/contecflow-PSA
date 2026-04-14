import { useState, useEffect } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { tasksApi, projectsApi } from '../services/api'
import { Badge, Button, Modal, EmptyState, Avatar, useSort, SortableTH } from '../components/ui'
import { SkeletonTable } from '../components/ui/Skeletons'
import VirtualList from '../components/ui/VirtualList'
import PageHeader from '../components/layout/PageHeader'
import { CheckSquare } from 'lucide-react'
import { fmtDate, STATUS_LABELS, PRIORITY_LABELS, extractErr} from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import DocumentsPanel from '../components/DocumentsPanel'
import AIInlineEditor from '../components/AIInlineEditor'
import { useAppT } from '../i18n/AppLangContext'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const STATUSES = ['todo', 'in_progress', 'blocked', 'review', 'done']
const _STATUS_ICONS = { todo: '○', in_progress: '◑', blocked: '✕', review: '◐', done: '●' }

const PRIORITIES = Object.entries(PRIORITY_LABELS).map(([v, l]) => ({ value: v, label: l }))
const TASK_STATUSES = STATUSES.map(v => ({ value: v, label: STATUS_LABELS[v] }))

function KanbanColumn({ status, tasks, onTaskClick }) {
  const colors = { todo: 'var(--text-2)', in_progress: 'var(--accent)', blocked: 'var(--danger)', review: 'var(--warning)', done: 'var(--success)' }
  const color = colors[status]
  return (
    <div style={{ minWidth: 240, flex: 1 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, padding: '0 4px' }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
          {STATUS_LABELS[status]}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 11, background: 'var(--surface-4)', color: 'var(--text-2)', borderRadius: 10, padding: '1px 7px' }}>
          {tasks.length}
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {tasks.map(task => (
          <div
            key={task.id}
            onClick={() => onTaskClick(task)}
            style={{
              background: 'var(--surface-2)', border: `1px solid ${task.status === 'blocked' ? 'var(--danger-border)' : 'var(--surface-4)'}`,
              borderRadius: 10, padding: '14px 16px', cursor: 'pointer', transition: 'all 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.borderColor = 'rgba(79,142,247,0.4)'}
            onMouseLeave={e => e.currentTarget.style.borderColor = task.status === 'blocked' ? 'var(--danger-border)' : 'var(--surface-4)'}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, alignItems: 'flex-start' }}>
              <span style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>{task.code}</span>
              <Badge label={task.priority} />
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10, lineHeight: 1.4 }}>{task.title}</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              {task.assignee ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Avatar name={task.assignee.full_name} size={22} />
                  <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{task.assignee.full_name.split(' ')[0]}</span>
                </div>
              ) : <span />}
              {task.estimated_hours && (
                <span style={{ fontSize: 11, color: task.real_hours > task.estimated_hours ? 'var(--danger)' : 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>
                  {task.real_hours?.toFixed(1) ?? 0}h / {task.estimated_hours}h
                </span>
              )}
            </div>
            {task.due_date && (
              <div style={{ marginTop: 8, fontSize: 11, color: new Date(task.due_date) < new Date() && task.status !== 'done' ? 'var(--danger)' : 'var(--text-2)' }}>
                📅 {fmtDate(task.due_date)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function TaskDetailModal({ task, open, onClose }) {
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

  const { data: customFields = [] } = useQuery({
    queryKey: ['custom-fields', task?.project_id],
    queryFn: () => api.get(`/custom-fields/${task.project_id}`).then(r => r.data),
    enabled: !!task?.project_id,
  })
  const { data: rawCustomValues = [] } = useQuery({
    queryKey: ['custom-field-values', task?.id],
    queryFn: () => api.get(`/custom-fields/${task.project_id}/values/${task.id}`).then(r => r.data),
    enabled: !!task?.id && !!task?.project_id,
  })
  const [customValues, setCustomValues] = useState({})
  useEffect(() => {
    const map = {}
    rawCustomValues.forEach(v => { map[v.field_id] = v.value ?? '' })
    setCustomValues(map)
  }, [rawCustomValues])

  const { mutate: saveTask, isPending: saving } = useMutation({
    mutationFn: async ({ taskData, cfValues, cfFields, taskId, projectId }) => {
      await tasksApi.update(taskId, taskData)
      if (cfFields.length > 0) {
        const payload = cfFields.map(f => ({ field_id: f.id, value: cfValues[f.id] ?? null }))
        await api.post(`/custom-fields/${projectId}/values/${taskId}`, payload)
      }
    },
    onSuccess: () => { qc.invalidateQueries(['tasks']); qc.invalidateQueries(['dash-my-tasks']); qc.invalidateQueries(['dash-overdue-tasks']); qc.invalidateQueries(['cal-tasks']); qc.invalidateQueries(['kanban-board']); setIsEditing(false); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  const { mutate: deleteTask, isPending: deleting } = useMutation({
    mutationFn: () => tasksApi.delete(task.id),
    onSuccess: () => { qc.invalidateQueries(['tasks']); qc.invalidateQueries(['dash-my-tasks']); qc.invalidateQueries(['dash-overdue-tasks']); qc.invalidateQueries(['cal-tasks']); qc.invalidateQueries(['kanban-board']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al eliminar')),
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
        api.post('/semantic/suggest/task', { title: form.title, description: form.description }),
        api.post('/semantic/estimate/effort',  { title: form.title, description: form.description }),
      ])
      setSemSuggestion(s.data); setSemEffort(e.data)
    } catch { /* noop */ } finally { setSuggesting(false) }
  }

  const acceptSuggestion = () => {
    if (semSuggestion?.suggested_user_id)
      setForm(f => ({ ...f, assignee_id: semSuggestion.suggested_user_id }))
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
  const fs  = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls  = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }
  const COMPLEXITY_COLORS = { simple: 'var(--success)', medium: 'var(--warning)', complex: 'var(--danger)' }
  const STATUS_LABEL_MAP = { backlog: 'Backlog', todo: 'Pendiente', in_progress: 'En progreso', review: 'Revisión', blocked: 'Bloqueada', done: 'Hecha', cancelled: 'Cancelada' }
  const PRIORITY_COLOR   = { critical: 'var(--danger)', high: 'var(--warning)', medium: 'var(--accent)', low: 'var(--text-2)' }
  const STATUS_COLOR     = { done: 'var(--success)', blocked: 'var(--danger)', in_progress: 'var(--accent)', review: 'var(--warning)', todo: 'var(--text-2)', backlog: 'var(--text-3)', cancelled: 'var(--text-3)' }

  if (!task || !form) return null

  return (
    <Modal open={open} onClose={onClose}
      title={<span style={{ fontFamily: 'monospace', fontSize: 13, color: 'var(--text-2)' }}>{task.code}</span>}
      width={680}>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20, borderBottom: '1px solid #1e2d45', paddingBottom: 10 }}>
        {[['detail','📋 Detalles'],['comments','💬 Comentarios'],['docs','📎 Documentos']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            style={{ padding: '5px 14px', borderRadius: 7, border: `1px solid ${tab===id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: tab===id ? 'var(--accent-muted)' : 'transparent', color: tab===id ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label} {id === 'comments' && task.comments?.length > 0 && `(${task.comments.length})`}
          </button>
        ))}
      </div>

      {/* ── DETALLES / EDITAR ── */}
      {tab === 'detail' && !isEditing && (
        <div>
          {/* Title */}
          <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)', marginBottom: 16, lineHeight: 1.3 }}>{task.title}</div>

          {/* Status + Priority row */}
          <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, padding: '3px 12px', borderRadius: 20, fontWeight: 700,
              background: STATUS_COLOR[task.status] + '20', color: STATUS_COLOR[task.status] }}>
              {STATUS_LABEL_MAP[task.status] || task.status}
            </span>
            <span style={{ fontSize: 12, padding: '3px 12px', borderRadius: 20, fontWeight: 700,
              background: PRIORITY_COLOR[task.priority] + '20', color: PRIORITY_COLOR[task.priority] }}>
              {PRIORITY_LABELS[task.priority] || task.priority}
            </span>
          </div>

          {/* Info grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
            <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Asignado a</div>
              {task.assignee ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Avatar name={task.assignee.full_name} size={22} />
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{task.assignee.full_name}</span>
                </div>
              ) : <span style={{ fontSize: 13, color: 'var(--text-3)' }}>Sin asignar</span>}
            </div>
            <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Horas</div>
              <span style={{ fontSize: 13, fontWeight: 600 }}>
                {task.real_hours?.toFixed(1) ?? 0}h real
                {task.estimated_hours ? ` / ${task.estimated_hours}h est.` : ''}
              </span>
            </div>
            {task.start_date && (
              <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
                <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Inicio</div>
                <span style={{ fontSize: 13 }}>{fmtDate(task.start_date)}</span>
              </div>
            )}
            {task.due_date && (
              <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
                <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Fecha límite</div>
                <span style={{ fontSize: 13, color: new Date(task.due_date) < new Date() && task.status !== 'done' ? 'var(--danger)' : 'var(--text-1)' }}>
                  {fmtDate(task.due_date)}
                </span>
              </div>
            )}
          </div>

          {/* Description */}
          {task.description && (
            <div style={{ marginBottom: 14, background: 'var(--surface-3)', borderRadius: 8, padding: '12px 14px' }}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>Descripción</div>
              <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6, whiteSpace: 'pre-line' }}>{task.description}</div>
            </div>
          )}

          {/* Blocked reason */}
          {task.status === 'blocked' && task.blocked_reason && (
            <div style={{ marginBottom: 14, background: 'var(--danger-bg)', border: '1px solid #ff475730', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--danger)', marginBottom: 4 }}>✕ BLOQUEADA</div>
              <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{task.blocked_reason}</div>
            </div>
          )}

          {/* Tags */}
          {task.tags && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>Etiquetas</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {String(task.tags).split(',').filter(Boolean).map(t => (
                  <span key={t} style={{ fontSize: 11, padding: '2px 9px', borderRadius: 12, background: 'var(--surface-3)', color: 'var(--text-2)' }}>#{t.trim()}</span>
                ))}
              </div>
            </div>
          )}

          {/* Custom fields (read-only) */}
          {customFields.length > 0 && rawCustomValues.length > 0 && (
            <div style={{ marginBottom: 14, borderTop: '1px solid #1e2d45', paddingTop: 14 }}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>Campos personalizados</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                {customFields.map(f => {
                  const val = customValues[f.id]
                  if (!val && val !== 0) return null
                  return (
                    <div key={f.id} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '8px 12px' }}>
                      <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 700, textTransform: 'uppercase', marginBottom: 3 }}>{f.name}</div>
                      <div style={{ fontSize: 13, color: 'var(--text-1)' }}>{String(val)}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Footer actions */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, paddingTop: 14, borderTop: '1px solid #1e2d45' }}>
            <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta tarea?', onConfirm: () => deleteTask(), danger: true }) }} disabled={deleting}
              style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #ff475730', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
              {deleting ? 'Eliminando...' : '🗑 Eliminar'}
            </button>
            <Button onClick={() => setIsEditing(true)}>✏️ Editar</Button>
          </div>
        </div>
      )}

      {/* ── MODO EDICIÓN ── */}
      {tab === 'detail' && isEditing && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>

          {/* Título */}
          <div style={{ gridColumn: '1/-1' }}>
            <label style={ls}>Título *</label>
            <input value={form.title} onChange={set('title')} style={fs} />
          </div>

          {/* Estado + Prioridad */}
          <div>
            <label style={ls}>Estado</label>
            <select value={form.status} onChange={set('status')} style={fs}>
              <option value="backlog">○ Backlog</option>
              <option value="todo">○ Pendiente</option>
              <option value="in_progress">◑ En progreso</option>
              <option value="review">◐ Revisión</option>
              <option value="blocked">✕ Bloqueada</option>
              <option value="done">● Hecha</option>
              <option value="cancelled">✕ Cancelada</option>
            </select>
          </div>
          <div>
            <label style={ls}>Prioridad</label>
            <select value={form.priority} onChange={set('priority')} style={fs}>
              <option value="low">🟢 Baja</option>
              <option value="medium">🟡 Media</option>
              <option value="high">🔴 Alta</option>
              <option value="critical">🚨 Crítica</option>
            </select>
          </div>

          {/* Asignado + botón IA */}
          <div style={{ gridColumn: '1/-1' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <label style={{ ...ls, marginBottom: 0 }}>Asignado a</label>
              <button onClick={analyzeWithAI} disabled={suggesting || !form.title}
                style={{ background: 'transparent', border: '1px solid #7c3aed40', borderRadius: 6, padding: '3px 10px', color: 'var(--purple)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 700 }}>
                {suggesting ? '⏳...' : '🧠 Sugerir con IA'}
              </button>
            </div>
            <select value={form.assignee_id} onChange={set('assignee_id')} style={fs}>
              <option value="">Sin asignar</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </select>
            {(semSuggestion || semEffort) && !semSuggestion?.error && (
              <div style={{ marginTop: 8, padding: '10px 14px', background: 'var(--purple-bg)', border: '1px solid #7c3aed30', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4, fontWeight: 700 }}>🧠 ANÁLISIS IA</div>
                  <div style={{ display: 'flex', gap: 16 }}>
                    {semSuggestion?.suggested_user_name && (
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-2)' }}>Persona sugerida</div>
                        <div style={{ fontSize: 13, fontWeight: 700 }}>{semSuggestion.suggested_user_name} <span style={{ color: 'var(--accent)', fontSize: 11 }}>{Math.round((semSuggestion.confidence||0)*100)}%</span></div>
                      </div>
                    )}
                    {semEffort && (
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-2)' }}>Esfuerzo estimado</div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--warning)' }}>{semEffort.base_hours}h <span style={{ color: COMPLEXITY_COLORS[semEffort.complexity], fontSize: 11 }}>{semEffort.complexity}</span></div>
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={acceptSuggestion} style={{ padding: '4px 10px', borderRadius: 6, background: 'var(--success-bg)', border: '1px solid #00e5a050', color: 'var(--success)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>✓ Aplicar</button>
                  <button onClick={() => { setSemSuggestion(null); setSemEffort(null) }} style={{ padding: '4px 8px', borderRadius: 6, background: 'transparent', border: '1px solid #1e2d45', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>✕</button>
                </div>
              </div>
            )}
          </div>

          {/* Horas + Fechas */}
          <div>
            <label style={ls}>Horas estimadas</label>
            <input type="number" value={form.estimated_hours} onChange={set('estimated_hours')} style={fs} placeholder="0" min="0" step="0.5" />
          </div>
          <div style={{ gridColumn: '1/-1', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={ls}>Fecha inicio</label>
              <input type="date" value={form.start_date} onChange={set('start_date')} style={fs} />
            </div>
            <div>
              <label style={ls}>Fecha límite</label>
              <input type="date" value={form.due_date} onChange={set('due_date')} style={fs} />
            </div>
          </div>

          {/* Descripción */}
          <div style={{ gridColumn: '1/-1' }}>
            <label style={ls}>Descripción <span style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 400 }}>— escribe &apos;/&apos; para comandos IA</span></label>
            <AIInlineEditor value={form.description} onChange={val => set('description')({ target: { value: val } })} rows={4} style={{ ...fs, resize: 'vertical', lineHeight: 1.6 }} />
          </div>

          {/* Motivo bloqueo */}
          {form.status === 'blocked' && (
            <div style={{ gridColumn: '1/-1' }}>
              <label style={ls}>Motivo del bloqueo</label>
              <input value={form.blocked_reason} onChange={set('blocked_reason')} style={fs}
                placeholder="¿Qué está bloqueando esta tarea?" />
            </div>
          )}

          {/* Tags */}
          <div style={{ gridColumn: '1/-1' }}>
            <label style={ls}>Etiquetas (separadas por coma)</label>
            <input value={form.tags} onChange={set('tags')} style={fs} placeholder="frontend, urgente, bug" />
          </div>

          {/* Campos personalizados */}
          {customFields.length > 0 && (
            <div style={{ gridColumn: '1/-1', borderTop: '1px solid #1e2d45', paddingTop: 14 }}>
              <label style={{ ...ls, marginBottom: 10 }}>Campos personalizados</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {customFields.map(f => (
                  <div key={f.id} style={(f.field_type === 'text' || f.field_type === 'url') ? { gridColumn: '1/-1' } : {}}>
                    <label style={ls}>{f.name}{f.is_required ? ' *' : ''}</label>
                    {f.field_type === 'select' ? (
                      <select value={customValues[f.id] ?? ''} onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))} style={fs}>
                        <option value="">Seleccionar...</option>
                        {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : f.field_type === 'boolean' ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 4 }}>
                        <input type="checkbox" checked={customValues[f.id] === 'true'} onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.checked ? 'true' : 'false' }))} style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
                        <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{customValues[f.id] === 'true' ? 'Sí' : 'No'}</span>
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
          <div style={{ gridColumn: '1/-1', display: 'flex', gap: 12, padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8, fontSize: 12, color: 'var(--text-2)' }}>
            <span>🕐 Horas reales: <strong style={{ color: 'var(--text-1)' }}>{task.real_hours?.toFixed(1) ?? 0}h</strong></span>
            <span>📅 Creada: <strong style={{ color: 'var(--text-1)' }}>{fmtDate(task.created_at)}</strong></span>
            {task.completed_at && <span>✅ Completada: <strong style={{ color: 'var(--success)' }}>{fmtDate(task.completed_at)}</strong></span>}
          </div>

          {/* Acciones edición */}
          <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
            <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta tarea?', onConfirm: () => deleteTask(), danger: true }) }} disabled={deleting}
              style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #ff475730', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
              {deleting ? 'Eliminando...' : '🗑 Eliminar'}
            </button>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button variant="secondary" onClick={cancelEdit}>Cancelar</Button>
              <Button onClick={() => saveTask({ taskData: form, cfValues: customValues, cfFields: customFields, taskId: task.id, projectId: task.project_id })} disabled={saving || !form.title}>
                {saving ? 'Guardando...' : '💾 Guardar cambios'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── COMENTARIOS ── */}
      {tab === 'comments' && (
        <div>
          {(!task.comments || task.comments.length === 0) ? (
            <p style={{ color: 'var(--text-2)', fontSize: 13, marginBottom: 16 }}>Sin comentarios todavía.</p>
          ) : (
            <div style={{ marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {task.comments.map(c => (
                <div key={c.id} style={{ display: 'flex', gap: 10 }}>
                  <Avatar name={c.author?.full_name || '?'} size={28} />
                  <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '8px 12px', flex: 1 }}>
                    <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>
                      <strong style={{ color: 'var(--text-1)' }}>{c.author?.full_name}</strong> · {fmtDate(c.created_at)}
                    </div>
                    <div style={{ fontSize: 13, lineHeight: 1.5 }}>{c.content}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <textarea value={comment} onChange={e => setComment(e.target.value)}
              placeholder="Añadir comentario..."
              rows={2}
              style={{ flex: 1, background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', resize: 'none' }}
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && comment) addComment({ id: task.id, content: comment }) }}
            />
            <Button onClick={() => addComment({ id: task.id, content: comment })} disabled={!comment || commenting}>Enviar</Button>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>⌘+Enter para enviar</div>
        </div>
      )}

      {/* ── DOCUMENTOS ── */}
      {tab === 'docs' && (
        <div style={{ marginTop: 4 }}>
          <DocumentsPanel taskId={task.id} />
        </div>
      )}
    </Modal>
  )
}

export default function TasksPage() {
  const t = useAppT()
  const { hasRole } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [view, setView] = useState('kanban')
  const [projectFilter, setProjectFilter] = useState('')
  const [statusFilter, setStatusFilter]   = useState('')
  const [search, setSearch]               = useState('')
  const [priorityFilter, setPriorityFilter]= useState('')
  const [assigneeFilter, setAssigneeFilter]= useState('')
  const [selectedTask, setSelectedTask] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [selected, setSelected] = useState(new Set())  // bulk selection

  // Bulk action state
  const [bulkStatus, setBulkStatus] = useState('')
  const [bulkAssignee, setBulkAssignee] = useState('')
  const [bulkPriority, setBulkPriority] = useState('')

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const { data: tasksData, isLoading } = useQuery({
    queryKey: ['tasks', projectFilter, statusFilter, view, search, priorityFilter, assigneeFilter],
    queryFn: () => {
      if (view === 'kanban' && projectFilter) {
        return tasksApi.kanban(projectFilter).then(r => r.data)
      }
      return tasksApi.list({
        project_id: projectFilter || undefined,
        status: statusFilter || undefined,
        search: search || undefined,
        priority: priorityFilter || undefined,
        assignee_id: assigneeFilter || undefined,
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
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<CheckSquare size={18} />}
        title={t('tasks.title')}
        actions={
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ display: 'flex', background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, overflow: 'hidden' }}>
              {['kanban', 'list'].map(v => (
                <button key={v} onClick={() => setView(v)}
                  style={{
                    padding: '7px 14px', background: view === v ? 'var(--accent-muted)' : 'transparent',
                    border: 'none', color: view === v ? 'var(--accent)' : 'var(--text-2)',
                    fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                  }}>
                  {v === 'kanban' ? '⊞ Kanban' : '☰ Lista'}
                </button>
              ))}
            </div>
            {hasRole('admin', 'pm', 'team_lead') && (
              <Button onClick={() => setShowCreate(true)} icon="＋">Nueva tarea</Button>
            )}
          </div>
        }
      />

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: 2, minWidth: 200 }}>
          <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)', fontSize: 14 }}>🔍</span>
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Buscar tareas..."
            style={{ width: '100%', background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 14px 9px 34px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }} />
        </div>
        <select value={projectFilter} onChange={e => setProjectFilter(e.target.value)}
          style={{ flex: 1, background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
          <option value="">Todos los proyectos</option>
          {projectOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}
          style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 14px', color: priorityFilter ? 'var(--warning)' : 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
          <option value="">Todas las prioridades</option>
          {PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <select value={assigneeFilter} onChange={e => setAssigneeFilter(e.target.value)}
          style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 14px', color: assigneeFilter ? 'var(--accent)' : 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
          <option value="">Todos los asignados</option>
          {allUsers.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
        </select>
        {view === 'list' && (
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
            <option value="">Todos los estados</option>
            {TASK_STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        )}
      </div>

      {/* ── Bulk Action Bar ─────────────────────────────────────────────── */}
      {selected.size > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', marginBottom: 12,
          background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 10,
          flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent)', whiteSpace: 'nowrap' }}>
            ☑ {selected.size} seleccionada{selected.size !== 1 ? 's' : ''}
          </span>
          <div style={{ width: 1, height: 20, background: 'var(--surface-4)' }} />
          <select value={bulkStatus} onChange={e => setBulkStatus(e.target.value)}
            style={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 7, padding: '5px 10px', color: bulkStatus ? 'var(--text-1)' : 'var(--text-2)', fontSize: 12, fontFamily: 'inherit', cursor: 'pointer', outline: 'none' }}>
            <option value="">Estado...</option>
            <option value="todo">○ Pendiente</option>
            <option value="in_progress">◑ En progreso</option>
            <option value="review">◐ Revisión</option>
            <option value="blocked">✕ Bloqueada</option>
            <option value="done">● Hecha</option>
          </select>
          <select value={bulkPriority} onChange={e => setBulkPriority(e.target.value)}
            style={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 7, padding: '5px 10px', color: bulkPriority ? 'var(--text-1)' : 'var(--text-2)', fontSize: 12, fontFamily: 'inherit', cursor: 'pointer', outline: 'none' }}>
            <option value="">Prioridad...</option>
            <option value="low">🟢 Baja</option>
            <option value="medium">🟡 Media</option>
            <option value="high">🔴 Alta</option>
            <option value="critical">🚨 Crítica</option>
          </select>
          <select value={bulkAssignee} onChange={e => setBulkAssignee(e.target.value)}
            style={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 7, padding: '5px 10px', color: bulkAssignee ? 'var(--text-1)' : 'var(--text-2)', fontSize: 12, fontFamily: 'inherit', cursor: 'pointer', outline: 'none' }}>
            <option value="">Asignar a...</option>
            {allUsers.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
          <button onClick={applyBulk} disabled={bulkPending || (!bulkStatus && !bulkPriority && !bulkAssignee)}
            style={{ background: 'var(--accent)', border: 'none', borderRadius: 7, padding: '6px 14px', color: '#000', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', opacity: (!bulkStatus && !bulkPriority && !bulkAssignee) ? 0.5 : 1 }}>
            {bulkPending ? '⏳' : '✓ Aplicar'}
          </button>
          <button onClick={() => { setSelected(new Set()); setBulkStatus(''); setBulkPriority(''); setBulkAssignee('') }}
            style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 7, padding: '5px 10px', color: 'var(--text-2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
            Cancelar
          </button>
        </div>
      )}

      {isLoading ? (
        <SkeletonTable rows={10} />
      ) : view === 'kanban' ? (
        projectFilter ? (
          <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 16 }}>
            {STATUSES.filter(s => s !== 'backlog').map(status => (
              <KanbanColumn
                key={status}
                status={status}
                tasks={(kanbanColumns[status] || []).filter(t =>
                  (!search || t.title?.toLowerCase().includes(search.toLowerCase())) &&
                  (!priorityFilter || t.priority === priorityFilter)
                )}
                onTaskClick={setSelectedTask}
              />
            ))}
          </div>
        ) : (
          // Sin proyecto: mostrar lista de todas las tareas
          flatTasks.length === 0 ? (
            <EmptyState icon="tasks" title="Sin tareas" description="Crea tu primera tarea o importa desde un proyecto existente." ctaLabel="Nueva tarea" onCta={() => setShowCreate(true)} />
          ) : (
            <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ padding: '10px 20px', borderBottom: '1px solid #1e2d45', fontSize: 12, color: 'var(--text-2)' }}>
                💡 Selecciona un proyecto para ver el tablero Kanban · Mostrando {flatTasks.length} tareas
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '28px 2.5fr 1.5fr 1fr 80px 100px 100px', gap: 16, padding: '10px 20px', borderBottom: '1px solid #1e2d45', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
                <input type="checkbox" checked={selected.size === flatTasks.length && flatTasks.length > 0} onChange={toggleAll} style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
                <SortableTH col="title" sort={taskSort} onSort={setTaskSort}>Tarea</SortableTH>
                <SortableTH col="project_id" sort={taskSort} onSort={setTaskSort}>Proyecto</SortableTH>
                <SortableTH col="assignee.full_name" sort={taskSort} onSort={setTaskSort}>Asignado</SortableTH>
                <SortableTH col="estimated_hours" sort={taskSort} onSort={setTaskSort}>Est.</SortableTH>
                <SortableTH col="status" sort={taskSort} onSort={setTaskSort}>Estado</SortableTH>
                <SortableTH col="priority" sort={taskSort} onSort={setTaskSort}>Prioridad</SortableTH>
              </div>
              {sortedTasks.map(t => {
                const proj = projects.find(p => p.id === t.project_id)
                return (
                  <div key={t.id}
                    style={{ display: 'grid', gridTemplateColumns: '28px 2.5fr 1.5fr 1fr 80px 100px 100px', gap: 16, padding: '12px 20px', borderBottom: '1px solid #1e2d4530', cursor: 'pointer', alignItems: 'center', background: selected.has(t.id) ? 'var(--accent-muted)' : 'transparent' }}
                    onMouseEnter={e => { if (!selected.has(t.id)) e.currentTarget.style.background = 'var(--surface-3)' }}
                    onMouseLeave={e => { e.currentTarget.style.background = selected.has(t.id) ? 'var(--accent-muted)' : 'transparent' }}>
                    <input type="checkbox" checked={selected.has(t.id)} onChange={() => toggleSelect(t.id)} onClick={e => e.stopPropagation()} style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
                    <div onClick={() => setSelectedTask(t)}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{t.title}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{t.code}</div>
                    </div>
                    <span onClick={() => setSelectedTask(t)} style={{ fontSize: 12, color: 'var(--text-2)' }}>{proj ? `${proj.code}` : '—'}</span>
                    <span onClick={() => setSelectedTask(t)} style={{ fontSize: 12 }}>{t.assignee?.full_name?.split(' ')[0] || '—'}</span>
                    <span onClick={() => setSelectedTask(t)} style={{ fontSize: 12, color: 'var(--text-2)' }}>{t.estimated_hours ? `${t.estimated_hours}h` : '—'}</span>
                    <span onClick={() => setSelectedTask(t)}><Badge label={t.status} /></span>
                    <span onClick={() => setSelectedTask(t)}><Badge label={t.priority} /></span>
                  </div>
                )
              })}
            </div>
          )
        )
      ) : (
        flatTasks.length === 0 ? (
          <EmptyState icon="search" title="Sin resultados" description="Ninguna tarea coincide con los filtros seleccionados." />
        ) : (
          <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '28px 2.5fr 1.5fr 1fr 80px 80px 100px 100px', gap: 16, padding: '10px 20px', borderBottom: '1px solid #1e2d45', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
              <input type="checkbox" checked={selected.size === flatTasks.length && flatTasks.length > 0} onChange={toggleAll} style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
              <SortableTH col="title" sort={taskSort} onSort={setTaskSort}>Tarea</SortableTH>
              <SortableTH col="project_id" sort={taskSort} onSort={setTaskSort}>Proyecto</SortableTH>
              <SortableTH col="assignee.full_name" sort={taskSort} onSort={setTaskSort}>Asignado</SortableTH>
              <SortableTH col="estimated_hours" sort={taskSort} onSort={setTaskSort}>Est.</SortableTH>
              <SortableTH col="real_hours" sort={taskSort} onSort={setTaskSort}>Real</SortableTH>
              <SortableTH col="status" sort={taskSort} onSort={setTaskSort}>Estado</SortableTH>
              <SortableTH col="priority" sort={taskSort} onSort={setTaskSort}>Prioridad</SortableTH>
            </div>
            <VirtualList
              items={sortedTasks}
              rowHeight={52}
              height={Math.min(flatTasks.length * 52, 600)}
              renderRow={(t) => (
                <div
                  style={{ display: 'grid', gridTemplateColumns: '28px 2.5fr 1.5fr 1fr 80px 80px 100px 100px', gap: 16, padding: '14px 20px', borderBottom: '1px solid #1e2d4530', cursor: 'pointer', transition: 'background 0.1s', alignItems: 'center', background: selected.has(t.id) ? 'var(--accent-muted)' : 'transparent' }}
                  onMouseEnter={e => { if (!selected.has(t.id)) e.currentTarget.style.background = 'var(--surface-3)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = selected.has(t.id) ? 'var(--accent-muted)' : 'transparent' }}
                >
                  <input type="checkbox" checked={selected.has(t.id)} onChange={() => toggleSelect(t.id)} onClick={e => e.stopPropagation()} style={{ cursor: 'pointer', accentColor: 'var(--accent)' }} />
                  <div onClick={() => setSelectedTask(t)}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{t.title}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>{t.code}</div>
                  </div>
                  <span onClick={() => setSelectedTask(t)} style={{ fontSize: 12, color: 'var(--text-2)' }}>
                    {projects.find(p => p.id === t.project_id)?.code || t.project_id?.slice(0,8) || '—'}
                  </span>
                  <span onClick={() => setSelectedTask(t)} style={{ fontSize: 12 }}>{t.assignee?.full_name?.split(' ')[0] || '—'}</span>
                  <span onClick={() => setSelectedTask(t)} style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: 'var(--text-2)' }}>{t.estimated_hours ? `${t.estimated_hours}h` : '—'}</span>
                  <span onClick={() => setSelectedTask(t)} style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: t.real_hours > t.estimated_hours ? 'var(--danger)' : 'var(--text-2)' }}>{t.real_hours?.toFixed(1) ?? 0}h</span>
                  <span onClick={() => setSelectedTask(t)}><Badge label={t.status} /></span>
                  <span onClick={() => setSelectedTask(t)}><Badge label={t.priority} /></span>
                </div>
              )}
            />
          </div>
        )
      )}

      <TaskDetailModal task={selectedTask} open={!!selectedTask} onClose={() => setSelectedTask(null)} />
      <CreateTaskModal open={showCreate} onClose={() => setShowCreate(false)} projects={projects} />
    </div>
  )
}

function CreateTaskModal({ open, onClose, projects }) {
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
  const [customValues, setCustomValues] = useState({})

  const { data: customFields = [] } = useQuery({
    queryKey: ['custom-fields', form.project_id],
    queryFn: () => api.get(`/custom-fields/${form.project_id}`).then(r => r.data),
    enabled: !!form.project_id,
  })

  const { mutate, isPending } = useMutation({
    mutationFn: async ({ taskData, cfValues, cfFields }) => {
      const res = await tasksApi.create(taskData)
      const task = res.data
      if (cfFields.length > 0 && task?.id) {
        const payload = cfFields.map(f => ({ field_id: f.id, value: cfValues[f.id] ?? null }))
        await api.post(`/custom-fields/${task.project_id}/values/${task.id}`, payload)
      }
      return task
    },
    onSuccess: () => {
      qc.invalidateQueries(['tasks'])
      qc.invalidateQueries(['dash-my-tasks'])
      qc.invalidateQueries(['dash-overdue-tasks'])
      qc.invalidateQueries(['cal-tasks'])
      qc.invalidateQueries(['kanban-board'])
      onClose()
      setForm({ title: '', project_id: '', status: 'todo', priority: 'medium', estimated_hours: '', start_date: '', due_date: '', description: '', assignee_id: '' })
      setCustomValues({})
      setSemSuggestion(null); setSemEffort(null)
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: 14, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }

  const analyzeWithAI = async () => {
    if (!form.title) return
    setSuggesting(true)
    setSemSuggestion(null); setSemEffort(null)
    try {
      const [sugRes, effortRes] = await Promise.all([
        api.post('/semantic/suggest/task', { title: form.title, description: form.description, project_id: form.project_id || undefined }),
        api.post('/semantic/estimate/effort',  { title: form.title, description: form.description }),
      ])
      setSemSuggestion(sugRes.data)
      setSemEffort(effortRes.data)
    } catch (e) { setSemSuggestion({ error: e?.response?.data?.detail || 'Error' }) }
    finally { setSuggesting(false) }
  }

  const acceptSuggestion = () => {
    if (semSuggestion?.suggested_user_id)
      setForm(f => ({ ...f, assignee_id: semSuggestion.suggested_user_id }))
    if (semEffort?.base_hours && !form.estimated_hours)
      setForm(f => ({ ...f, estimated_hours: String(semEffort.base_hours) }))
    setSemSuggestion(null); setSemEffort(null)
  }

  const COMPLEXITY_COLORS = { simple: 'var(--success)', medium: 'var(--warning)', complex: 'var(--danger)' }

  return (
    <Modal open={open} onClose={onClose} title="Nueva Tarea" width={580}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={ls}>Título *</label>
          <input value={form.title} onChange={set('title')} style={fs} placeholder="Título de la tarea" />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={ls}>Proyecto *</label>
          <select value={form.project_id} onChange={set('project_id')} style={fs}>
            <option value="">Seleccionar proyecto...</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Estado</label>
          <select value={form.status} onChange={set('status')} style={fs}>
            <option value="todo">○ Pendiente</option>
            <option value="in_progress">◑ En progreso</option>
            <option value="blocked">✕ Bloqueada</option>
            <option value="review">◐ Revisión</option>
            <option value="done">● Hecha</option>
          </select>
        </div>
        <div>
          <label style={ls}>Prioridad</label>
          <select value={form.priority} onChange={set('priority')} style={fs}>
            <option value="low">🟢 Baja</option>
            <option value="medium">🟡 Media</option>
            <option value="high">🔴 Alta</option>
            <option value="critical">🚨 Crítica</option>
          </select>
        </div>
        {/* Asignación + estimación con IA */}
        <div style={{ gridColumn: '1 / -1' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <label style={{ ...ls, marginBottom: 0 }}>Asignado a</label>
            <button onClick={analyzeWithAI} disabled={suggesting || !form.title}
              style={{ background: 'transparent', border: '1px solid #7c3aed40', borderRadius: 6, padding: '3px 12px', color: 'var(--purple)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 700 }}>
              {suggesting ? '⏳...' : '🧠 Analizar con IA'}
            </button>
          </div>
          <select value={form.assignee_id} onChange={set('assignee_id')} style={fs}>
            <option value="">Sin asignar</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        {/* Banner de sugerencia IA */}
        {(semSuggestion || semEffort) && !semSuggestion?.error && (
          <div style={{ gridColumn: '1 / -1', padding: '12px 14px', background: 'var(--purple-bg)', border: '1px solid #7c3aed30', borderRadius: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 6, fontWeight: 700 }}>🧠 ANÁLISIS IA</div>
              <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
                {semSuggestion?.suggested_user_name && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-2)' }}>Persona sugerida</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>
                      {semSuggestion.suggested_user_name}
                      <span style={{ fontSize: 11, color: 'var(--accent)', marginLeft: 6 }}>
                        {Math.round((semSuggestion.confidence||0)*100)}%
                      </span>
                    </div>
                  </div>
                )}
                {semEffort && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-2)' }}>Esfuerzo estimado</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--warning)' }}>
                      {semEffort.base_hours}h
                      <span style={{ fontSize: 11, marginLeft: 6, color: COMPLEXITY_COLORS[semEffort.complexity] }}>
                        {semEffort.complexity}
                      </span>
                    </div>
                  </div>
                )}
              </div>
              {semSuggestion?.reasoning && <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 4 }}>{semSuggestion.reasoning}</div>}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button onClick={acceptSuggestion} style={{ padding: '5px 12px', borderRadius: 6, background: 'var(--success-bg)', border: '1px solid #00e5a050', color: 'var(--success)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>✓ Aplicar</button>
              <button onClick={() => { setSemSuggestion(null); setSemEffort(null) }} style={{ padding: '5px 8px', borderRadius: 6, background: 'transparent', border: '1px solid #1e2d45', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>✕</button>
            </div>
          </div>
        )}
        <div>
          <label style={ls}>Horas estimadas</label>
          <input type="number" value={form.estimated_hours} onChange={set('estimated_hours')} style={fs} placeholder="0" />
        </div>
        <div>
          <label style={ls}>Fecha inicio</label>
          <input type="date" value={form.start_date} onChange={set('start_date')} style={fs} />
        </div>
        <div>
          <label style={ls}>Fecha límite</label>
          <input type="date" value={form.due_date} onChange={set('due_date')} style={fs} />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={ls}>Descripción <span style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 400 }}>— escribe &apos;/&apos; para comandos IA</span></label>
          <AIInlineEditor value={form.description} onChange={val => set('description')({ target: { value: val } })} rows={3} placeholder="Descripción de la tarea..." style={{ ...fs, resize: 'vertical' }} />
        </div>
        {/* Campos personalizados del proyecto */}
        {customFields.length > 0 && (
          <div style={{ gridColumn: '1/-1', borderTop: '1px solid #1e2d45', paddingTop: 14 }}>
            <label style={{ ...ls, marginBottom: 10 }}>Campos personalizados</label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {customFields.map(f => (
                <div key={f.id} style={(f.field_type === 'text' || f.field_type === 'url') ? { gridColumn: '1/-1' } : {}}>
                  <label style={ls}>{f.name}{f.is_required ? ' *' : ''}</label>
                  {f.field_type === 'select' ? (
                    <select value={customValues[f.id] ?? ''} onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))} style={fs}>
                      <option value="">Seleccionar...</option>
                      {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : f.field_type === 'boolean' ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 4 }}>
                      <input type="checkbox" checked={customValues[f.id] === 'true'} onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.checked ? 'true' : 'false' }))} style={{ width: 16, height: 16, accentColor: 'var(--accent)', cursor: 'pointer' }} />
                      <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{customValues[f.id] === 'true' ? 'Sí' : 'No'}</span>
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
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate({ taskData: form, cfValues: customValues, cfFields: customFields })} disabled={isPending || !form.title || !form.project_id} loading={isPending}>
            {isPending ? 'Creando...' : 'Crear tarea'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}