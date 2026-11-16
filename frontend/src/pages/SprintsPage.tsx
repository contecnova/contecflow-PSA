/**
 * SprintsPage — Full Scrum sprint management
 * Views: Backlog | Sprint Activo | Velocity histórico
 *
 * 16-11-2026: "Nuevo sprint" en la cabecera con icono (antes en el cuerpo con
 * "+" de texto); selector de proyecto en una Card y vistas con <Tabs> (antes
 * botones a mano con emojis); sprints en Card; KPIs con KpiCard (antes cifras
 * propias con emoji); vacíos con EmptyState e icono lucide (antes ⚡📊✅ y una
 * caja discontinua); botones del kit con iconos lucide; estado con StatusBadge.
 */
import { useState, useEffect, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, projectSprintsApi, tasksApi } from '../services/api'
import type { SprintDelProyecto, TareaDeSprint } from '../services/api/tipos-proyectos'
import { Button, Card, EmptyState, KpiCard, Modal, Section, Spinner, Tabs } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle, ArrowRight, BarChart2, CheckCircle2, ClipboardList, Columns3, FolderKanban, Gauge, Inbox, ListTodo, MessageSquareText, MoreHorizontal, Play, Plus, RefreshCw, Target, User } from 'lucide-react'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, ReferenceLine } from 'recharts'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import './SprintsPage.css'
import DateInput from '../components/ui/DateInput'
import { TOOLTIP_SUPERFICIE_3_REDONDO_SM, TOOLTIP_SUPERFICIE_3_REDONDO_XS } from '../constants/estilosGrafico'

// sprint_service.serialize_task / serialize_sprint y raci_service.get_sprint_retrospective.
type Task = TareaDeSprint
type Sprint = SprintDelProyecto

const colorVar = (name: '--spr-c' | '--spr-p', color: string) => ({ [name]: color } as CSSProperties)

// ── Retrospective modal (v25 AI insights) ────────────────────────────────────
function RetroModal({ sprint, projectId, onClose }: { sprint: Sprint; projectId: string; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const [manualNotes, setManualNotes] = useState('')

  const { data: retro, isLoading } = useQuery({
    queryKey: ['retro', sprint.id],
    queryFn: () => projectSprintsApi.retrospective(projectId, sprint.id).then(r => r.data),
  })
  // TanStack Query v5 ya no llama a `onSuccess` en useQuery: las notas guardadas se cargan aquí.
  const notasGuardadas = retro?.saved_notes?.manual_notes
  useEffect(() => { if (notasGuardadas) setManualNotes(notasGuardadas) }, [notasGuardadas])

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: (notes: string) => projectSprintsApi.saveRetrospective(projectId, sprint.id, { manual_notes: notes }),
    onSuccess: () => { toast.success(t('sprints.notas_guardadas')); onClose() },
    onError: () => toast.error(t('sprints.error_guardar')),
  })

  const ins = retro?.computed_insights
  const m = ins?.metrics

  return (
    <div className="u-stack-16">
      {/* Metrics row */}
      {m && (
        <div className="spr-retro-metrics">
          <KpiCard icon={<CheckCircle2 size={16} />} label={t('sprints.completitud')} value={`${m.completion_rate_pct}%`} warning={m.completion_rate_pct < 80} />
          <KpiCard icon={<Gauge size={16} />} label={t('sprints.velocity_ratio')} value={`${m.velocity_ratio_pct}%`} warning={m.velocity_ratio_pct < 85} />
          <KpiCard icon={<AlertTriangle size={16} />} label={t('sprints.bloqueadas')} value={m.blocked} danger={m.blocked > 0} />
          <KpiCard icon={<ArrowRight size={16} />} label={t('sprints.carryover')} value={m.carryover} warning={m.carryover > 0} />
        </div>
      )}

      {isLoading ? (
        <div className="spr-loading"><Spinner /><span className="u-text2-base">{t('sprints.analizando_datos_del_sprint')}</span></div>
      ) : ins && (
        <div className="u-grid2-10">
          {/* Went well */}
          <div className="spr-insight spr-insight--success">
            <div className="spr-insight__title">{t('sprints.que_fue_bien')}</div>
            {ins.went_well?.map((item, i) => (
              <div key={i} className="spr-insight__item">
                <span className="spr-insight__mark" aria-hidden="true">→</span>{item}
              </div>
            ))}
          </div>
          {/* To improve */}
          <div className="spr-insight spr-insight--warning">
            <div className="spr-insight__title">{t('sprints.a_mejorar')}</div>
            {ins.improve?.map((item, i) => (
              <div key={i} className="spr-insight__item">
                <span className="spr-insight__mark" aria-hidden="true">→</span>{item}
              </div>
            ))}
          </div>
          {/* Actions */}
          {(ins.actions?.length ?? 0) > 0 && (
            <div className="spr-insight spr-insight--accent">
              <div className="spr-insight__title">{t('sprints.acciones_propuestas')}</div>
              {ins.actions?.map((a, i) => (
                <div key={i} className="spr-insight__item">
                  <span className="spr-insight__mark" aria-hidden="true">○</span>{a.text}
                </div>
              ))}
            </div>
          )}
          {/* Risks */}
          {(ins.risks?.length ?? 0) > 0 && (
            <div className="spr-insight spr-insight--danger">
              <div className="spr-insight__title">{t('sprints.senales_de_riesgo')}</div>
              {ins.risks?.map((r, i) => (
                <div key={i} className="spr-insight__item">
                  <span className="spr-insight__mark" aria-hidden="true">!</span>{r}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Manual notes */}
      <div>
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="spr-label spr-label--notes">{t('sprints.notas_del_equipo')}</label>
        <textarea id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`}
          value={manualNotes}
          onChange={e => setManualNotes(e.target.value)}
          rows={3}
          placeholder={t('sprints.escribe_notas_para_el_equipo')}
          className="ds-input spr-input spr-textarea"
        />
      </div>

      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('sprints.cerrar')}</Button>
        <Button onClick={() => save(manualNotes)} disabled={saving}>{saving ? t('sprints.guardando') : t('sprints.guardar_notas')}</Button>
      </div>
    </div>
  )
}
const PRIORITY_COLOR: Record<string, string> = { low: 'var(--text-3)', medium: 'var(--warning)', high: 'var(--warning)', critical: 'var(--danger)' }
// `label` es una clave de i18n (bloque `sprints`).
const TASK_STATUS_CFG: Record<string, { label: string; color: string }> = {
  todo:        { label: 'sprints.estado_todo',        color: 'var(--text-3)' },
  in_progress: { label: 'sprints.estado_in_progress', color: 'var(--accent)' },
  in_review:   { label: 'sprints.estado_in_review',   color: 'var(--purple)' },
  done:        { label: 'sprints.estado_done',        color: 'var(--success)' },
  blocked:     { label: 'sprints.estado_blocked',     color: 'var(--danger)' },
}

const fs = 'ds-input spr-input'
const ls = 'spr-label'

// ── Task card ──────────────────────────────────────────────────────────────────
function TaskCard({ task, onStatusChange, onMoveToBacklog, compact = false }: { task: Task; onStatusChange?: (taskId: string, status: string) => void; onMoveToBacklog?: (taskId: string) => void; compact?: boolean }) {
  const t = useAppT()
  const [showMenu, setShowMenu] = useState(false)
  const cfg = TASK_STATUS_CFG[task.status || '']
  const color = cfg?.color || 'var(--text-2)'
  const pColor = PRIORITY_COLOR[task.priority || ''] || 'var(--text-2)'

  return (
    <div className={`spr-task${compact ? ' spr-task--compact' : ''}`} style={{ '--spr-c': color, '--spr-p': pColor } as CSSProperties}>
      <div className="spr-task__head">
        <div className="u-flex1-min0">
          <div className="spr-task__code">{task.code}</div>
          <div className="spr-task__title">{task.title}</div>
        </div>
        <button type="button" onClick={e => { e.stopPropagation(); setShowMenu(m => !m) }} className="spr-task__menu-btn"
          aria-haspopup="menu" aria-expanded={showMenu} aria-label={t('sprints.acciones_tarea', { code: task.code || task.title || '' })}><MoreHorizontal size={16} aria-hidden /></button>
      </div>

      <div className="u-wrap-8">
        <span className="spr-tag">{task.priority ? t('sprints.prioridad_' + task.priority, task.priority) : ''}</span>
        {(task.story_points ?? 0) > 0 && <span className="spr-tag spr-tag--pts">{t('sprints.n_pts', { n: task.story_points ?? 0 })}</span>}
        {task.assignee_name && <span className="spr-task__who"><User size={11} aria-hidden />{task.assignee_name.split(' ')[0]}</span>}
      </div>

      {showMenu && (
        <div className="spr-menu" role="menu">
          <div className="spr-menu__title">{t('sprints.cambiar_estado')}</div>
          {Object.entries(TASK_STATUS_CFG).map(([status, { label, color: c }]) => (
            <button key={status} type="button" role="menuitem" onClick={() => { onStatusChange?.(task.id, status); setShowMenu(false) }}
              className={`spr-menu__item${task.status === status ? ' spr-menu__item--current' : ''}`} style={colorVar('--spr-c', c)}>
              {t(label)}
            </button>
          ))}
          {onMoveToBacklog && (
            <>
              <div className="spr-menu__sep" role="separator" />
              <button type="button" role="menuitem" onClick={() => openConfirmGlobal({ message: t('sprints.confirm_mover_backlog'), onConfirm: () => { onMoveToBacklog(task.id); setShowMenu(false) }, danger: true })}
                className="spr-menu__item spr-menu__item--danger">
                {t('sprints.mover_al_backlog')}
              </button>
            </>
          )}
          <button type="button" role="menuitem" onClick={() => setShowMenu(false)} className="spr-menu__item spr-menu__item--muted">
            {t('sprints.cerrar')}
          </button>
        </div>
      )}
    </div>
  )
}

// ── Sprint Kanban ──────────────────────────────────────────────────────────────
function SprintKanban({ sprint, onStatusChange, onMoveToBacklog }: { sprint: Sprint; onStatusChange?: (taskId: string, status: string) => void; onMoveToBacklog?: (taskId: string) => void }) {
  const t = useAppT()
  const columns = ['todo', 'in_progress', 'in_review', 'done']
  const tasks = sprint.tasks || []

  return (
    <div className="spr-kanban">
      {columns.map(key => {
        const colTasks = tasks.filter((tk: Task) => tk.status === key)
        const cfg = TASK_STATUS_CFG[key]
        return (
          <div key={key}>
            <div className="spr-col__head" style={colorVar('--spr-c', cfg.color)}>
              <span className="spr-col__label">{t(cfg.label)}</span>
              <span className="spr-col__count">{colTasks.length}</span>
            </div>
            <div className="spr-col__list">
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
  const { data, isLoading } = useQuery({
    queryKey: ['burndown', sprintId],
    queryFn: () => projectSprintsApi.burndown(projectId, sprintId).then(r => r.data),
    enabled: !!sprintId,
  })
  if (isLoading) return <Spinner />
  const points = data?.burndown || []
  if (points.length < 2) return <div className="spr-empty-chart">{t('sprints.sin_suficientes_datos_aun')}</div>

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={points} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
        <XAxis dataKey="date" tickFormatter={(d: string) => fmtDate(d)} tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
        <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
        <Tooltip labelFormatter={(d) => fmtDate(String(d))} contentStyle={TOOLTIP_SUPERFICIE_3_REDONDO_XS} />
        <Line type="monotone" dataKey="ideal" stroke="var(--surface-4)" strokeWidth={1.5} strokeDasharray="6 3" dot={false} name={t('sprints.serie_ideal')} />
        <Line type="monotone" dataKey="remaining" stroke="var(--accent)" strokeWidth={2.5} dot={{ r: 3 }} name={t('sprints.serie_restante')} />
      </LineChart>
    </ResponsiveContainer>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
/** Rev. 173: con `projectId` va dentro de la ficha del proyecto, con el proyecto fijo y sin selector. */
export default function SprintsPage({ projectId }: { projectId?: string } = {}) {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  useInvalidate()
  useAuth()
  const [selectedProject, setSelectedProject] = useState(projectId ?? '')
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

  const { data: projRaw = [] } = useQuery<{ id: string; code?: string; name?: string }[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })
  const projects = Array.isArray(projRaw) ? projRaw : []

  const { data: sprints = [], isLoading } = useQuery({
    queryKey: ['sprints', selectedProject],
    queryFn: () => projectSprintsApi.list(selectedProject).then(r => r.data),
    enabled: !!selectedProject,
  })
  const activeSprint = sprints.find((s: Sprint) => s.status === 'active')
  const planningSprints = sprints.filter((s: Sprint) => s.status === 'planning')
  const completedSprints = sprints.filter((s: Sprint) => s.status === 'completed')

  const { data: backlog = [] } = useQuery({
    queryKey: ['backlog', selectedProject],
    queryFn: () => projectSprintsApi.backlog(selectedProject).then(r => r.data),
    enabled: !!selectedProject,
  })

  const { data: velocity } = useQuery({
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
  const sinFecha = t('sprints.sin_fecha')
  const vistas = [
    { id: 'board', label: t('sprints.board'), icon: <Columns3 size={14} /> },
    { id: 'backlog', label: t('sprints.backlog'), icon: <ListTodo size={14} /> },
    { id: 'velocity', label: t('sprints.velocity'), icon: <BarChart2 size={14} /> },
  ]

  return (
    <PageShell>
      <PageHeader
        title={t('sprints.title')}
        subtitle={t('sprints.subtitle')}
        icon={<RefreshCw size={18} />}
        showListExport={Boolean(selectedProject && activeView !== 'velocity')}
        exportFilePrefix='sprints'
        actions={selectedProject ? <Button icon={<Plus size={14} />} onClick={() => setShowCreateSprint(true)}>{t('sprints.nuevo_sprint')}</Button> : undefined}
      />

      <div className="u-stack-16">
      {/* Project selector */}
      {!projectId && (
        <Card className="spr-filtros">
          <select value={selectedProject} onChange={e => { setSelectedProject(e.target.value); setActiveView('board') }}
            className={`${fs} spr-input--project`} aria-label={t('sprints.selecciona_un_proyecto_2')}>
            <option value="">{t('sprints.selecciona_un_proyecto')}</option>
            {projects.map((p: { id: string; code?: string; name?: string }) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </Card>
      )}
      {selectedProject && (
        <Tabs items={vistas} active={activeView} onChange={setActiveView} ariaLabel={t('sprints.title')} />
      )}

      {!selectedProject && (
        <EmptyState icon={<FolderKanban size={28} />} title={t('sprints.selecciona_un_proyecto_2')} description={t('sprints.elige_proyecto_desc')} />
      )}

      {selectedProject && isLoading && <Spinner />}

      {/* BOARD VIEW */}
      {selectedProject && !isLoading && activeView === 'board' && (
        <div className="u-stack-16">
          {/* Active sprint */}
          {activeSprint ? (
            <Card className="spr-active">
              <div className="spr-active__head">
                <div className="u-min0">
                  <div className="spr-active__title-row">
                    <span className="spr-active__title">{t('sprints.sprint_n_nombre', { n: activeSprint.number ?? '', name: activeSprint.name })}</span>
                    <StatusBadge kind="accent">{t('sprints.status_active')}</StatusBadge>
                    {activeSprint.days_remaining !== null && (
                      <span className={`spr-days${activeSprint.days_remaining <= 2 ? ' spr-days--late' : ''}`}>
                        {activeSprint.days_remaining > 0 ? t('sprints.dias_restantes', { n: activeSprint.days_remaining }) : t('sprints.vencido')}
                      </span>
                    )}
                  </div>
                  {activeSprint.goal && <div className="spr-goal"><Target size={14} aria-hidden />{activeSprint.goal}</div>}
                  <div className="spr-meta">
                    {fmtDate(activeSprint.start_date)} → {fmtDate(activeSprint.end_date)} · {t('sprints.pts_planificados_completados', { p: activeSprint.planned_points || 0, c: activeSprint.completed_points || 0 })}
                  </div>
                </div>
                <div className="spr-active__side">
                  <div className="spr-right">
                    <BurndownChart sprintId={activeSprint.id} projectId={selectedProject} />
                  </div>
                  <div className="u-stack-6">
                    <Button icon={<Plus size={14} />} onClick={() => setShowAddTasks(activeSprint.id)}>{t('sprints.anadir_tareas')}</Button>
                    <Button variant="secondary" icon={<MessageSquareText size={14} />} onClick={() => setShowRetro(activeSprint)}>
                      {t('sprints.retro')}
                    </Button>
                    <Button variant="secondary" icon={<CheckCircle2 size={14} />} onClick={() => { openConfirmGlobal({ message: t('sprints.confirm_cerrar_sprint'), onConfirm: () => closeSprint(activeSprint.id), danger: true }) }}>
                      {t('sprints.cerrar_sprint')}
                    </Button>
                  </div>
                </div>
              </div>
              <SprintKanban
                sprint={activeSprint}
                onStatusChange={(taskId, status) => updateTaskStatus({ taskId, status })}
                onMoveToBacklog={(taskId) => removeTask({ sprintId: activeSprint.id, taskId })}
              />
            </Card>
          ) : (
            <EmptyState
              icon={<Play size={28} />}
              title={t('sprints.no_hay_sprint_activo')}
              description={t('sprints.crea_un_sprint_y_pulsa_quot_iniciar')}
              action={planningSprints.length === 0 ? <Button icon={<Plus size={14} />} onClick={() => setShowCreateSprint(true)}>{t('sprints.nuevo_sprint')}</Button> : undefined}
            />
          )}

          {/* Planning sprints */}
          {planningSprints.length > 0 && (
            <Section title={t('sprints.en_planificacion')}>
              <div className="u-stack-10">
              {planningSprints.map(sprint => (
                <Card key={sprint.id} className="spr-planning">
                  <div className="spr-planning__row">
                    <div className="u-min0">
                      <span className="spr-planning__name">{t('sprints.sprint_n_nombre', { n: sprint.number ?? '', name: sprint.name })}</span>
                      {sprint.goal && <div className="spr-goal spr-goal--sm"><Target size={13} aria-hidden />{sprint.goal}</div>}
                      <div className="u-text2-sm-mt2">
                        {sprint.start_date ? fmtDate(sprint.start_date) : sinFecha} → {sprint.end_date ? fmtDate(sprint.end_date) : sinFecha} · {t('sprints.n_tareas_pts', { n: sprint.task_count ?? 0, p: sprint.planned_points || 0 })}
                      </div>
                    </div>
                    <div className="u-row-8">
                      <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={() => setShowAddTasks(sprint.id)}>
                        {t('sprints.mas_tareas')}
                      </Button>
                      {!activeSprint && (
                        <Button size="sm" icon={<Play size={14} />} onClick={() => startSprint(sprint.id)}>
                          {t('sprints.iniciar_sprint')}
                        </Button>
                      )}
                    </div>
                  </div>
                </Card>
              ))}
              </div>
            </Section>
          )}

          {/* Completed sprints summary */}
          {completedSprints.length > 0 && (
            <Section title={t('sprints.completados')}>
              <div className="spr-done-grid">
                {completedSprints.map(s => (
                  <Card key={s.id} className="spr-done">
                    <div className="spr-done__name">{t('sprints.sprint_n_nombre', { n: s.number ?? '', name: s.name })}</div>
                    <div className="u-text2-sm">{fmtDate(s.start_date)} → {fmtDate(s.end_date)}</div>
                    <div className="spr-done__stats">
                      <span className="spr-done__pts"><CheckCircle2 size={13} aria-hidden />{t('sprints.n_pts', { n: s.completed_points || 0 })}</span>
                      <span className="u-text2">{t('sprints.velocidad_valor', { v: s.velocity || '—' })}</span>
                    </div>
                  </Card>
                ))}
              </div>
            </Section>
          )}
        </div>
      )}

      {/* BACKLOG VIEW */}
      {selectedProject && !isLoading && activeView === 'backlog' && (
        <div>
          <div className="spr-backlog-head">
            <div className="spr-backlog-title">{t('sprints.backlog_titulo', { n: backlog.length })}</div>
          </div>
          {backlog.length === 0 ? (
            <EmptyState icon={<Inbox size={28} />} title={t('sprints.backlog_vacio')} description={t('sprints.backlog_vacio_desc')} />
          ) : (
            <div className="u-stack-6">
              {backlog.map(task => {
                const selected = selectedBacklogTasks.includes(task.id)
                const pColor = PRIORITY_COLOR[task.priority || ''] || 'var(--text-3)'
                return (
                  <div key={task.id}
                    onClick={() => setSelectedBacklogTasks(prev => selected ? prev.filter(id => id !== task.id) : [...prev, task.id])}
                    role="checkbox" aria-checked={selected} aria-label={task.title} tabIndex={0}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedBacklogTasks(prev => selected ? prev.filter(id => id !== task.id) : [...prev, task.id]) } }}
                    className={`spr-row${selected ? ' spr-row--selected' : ''}`}>
                    <input type="checkbox" aria-hidden="true" tabIndex={-1} checked={selected} readOnly className="spr-row__check" />
                    <span className="u-text3-mono-xs">{task.code}</span>
                    <span className="spr-row__title">{task.title}</span>
                    <span className="spr-row__prio" style={colorVar('--spr-p', pColor)}>{task.priority ? t('sprints.prioridad_' + task.priority, task.priority) : ''}</span>
                    <span className="spr-row__pts">{t('sprints.n_pts', { n: task.story_points || '—' })}</span>
                    <span className="u-text2-xs">{task.assignee_name || t('sprints.sin_asignar')}</span>
                  </div>
                )
              })}
            </div>
          )}
          {selectedBacklogTasks.length > 0 && planningSprints.length > 0 && (
            <div className="spr-float" role="region" aria-label={t('sprints.n_seleccionadas_tareas', { n: selectedBacklogTasks.length })}>
              <span className="spr-float__count">{t('sprints.n_seleccionadas_tareas', { n: selectedBacklogTasks.length })}</span>
              {planningSprints.map(s => (
                <Button key={s.id} icon={<ArrowRight size={14} />} onClick={() => { addTasksToSprint({ sprintId: s.id, taskIds: selectedBacklogTasks }); setSelectedBacklogTasks([]) }}>
                  {t('sprints.sprint_n', { n: s.number ?? '' })}
                </Button>
              ))}
              <Button variant="secondary" onClick={() => setSelectedBacklogTasks([])}>
                {t('common.cancel')}
              </Button>
            </div>
          )}
        </div>
      )}

      {/* VELOCITY VIEW */}
      {selectedProject && !isLoading && activeView === 'velocity' && (
        <div>
          {!velocity || velocity.sprints?.length === 0 ? (
            <EmptyState icon={<BarChart2 size={28} />} title={t('sprints.sin_datos_de_velocidad')} description={t('sprints.sin_velocidad_desc')} />
          ) : (
            <div className="u-stack-16">
              <div className="ds-grid-stats">
                <KpiCard icon={<Gauge size={16} />} label={t('sprints.velocidad_media')} value={t('sprints.pts_por_sprint', { n: velocity.avg_velocity })} />
                <KpiCard icon={<CheckCircle2 size={16} />} label={t('sprints.sprints_completados')} value={velocity.sprints?.length || 0} />
                <KpiCard icon={<Target size={16} />} label={t('sprints.total_puntos_entregados')} value={velocity.sprints?.reduce((s, x) => s + x.completed, 0) || 0} />
              </div>

              <Card>
                <Section title={t('sprints.velocidad_por_sprint')}>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={velocity.sprints} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                    <XAxis dataKey="sprint" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} />
                    <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} />
                    <Tooltip contentStyle={TOOLTIP_SUPERFICIE_3_REDONDO_SM} />
                    <ReferenceLine y={velocity.avg_velocity} stroke="var(--accent)" strokeDasharray="5 3" label={{ value: t('sprints.serie_media'), fill: 'var(--accent)', fontSize: "var(--text-xs)" }} />
                    <Bar dataKey="planned" fill="var(--surface-4)" radius={[3, 3, 0, 0]} name={t('sprints.serie_planificado')} />
                    <Bar dataKey="completed" fill="var(--accent)" radius={[3, 3, 0, 0]} name={t('sprints.completed')} />
                  </BarChart>
                </ResponsiveContainer>
                </Section>
              </Card>

              {velocity.sprints?.some(s => { const sp = completedSprints.find(x => x.name === s.name); return sp?.went_well || sp?.to_improve }) && (
              <Section title={<span className="spr-titulo"><ClipboardList size={16} aria-hidden />{t('sprints.retrospectivas')}</span>}>
                <div className="u-stack-10">
                {velocity.sprints?.map(s => {
                  const sprint = completedSprints.find(x => x.name === s.name)
                  if (!sprint?.went_well && !sprint?.to_improve) return null
                  return (
                    <Card key={s.sprint} className="spr-retro">
                      <div className="spr-retro__name">{s.sprint} — {s.name}</div>
                      <div className="spr-retro__grid">
                        {sprint?.went_well && <div><div className="spr-retro__h spr-retro__h--success">{t('sprints.que_fue_bien')}</div><div className="u-text2">{sprint.went_well}</div></div>}
                        {sprint?.to_improve && <div><div className="spr-retro__h spr-retro__h--warning">{t('sprints.a_mejorar')}</div><div className="u-text2">{sprint.to_improve}</div></div>}
                        {sprint?.action_items && <div><div className="spr-retro__h spr-retro__h--accent">{t('sprints.acciones')}</div><div className="u-text2">{sprint.action_items}</div></div>}
                      </div>
                    </Card>
                  )
                })}
                </div>
              </Section>
              )}
            </div>
          )}
        </div>
      )}

      {/* Modal: Create Sprint */}
      {showCreateSprint && (
        <Modal open title={t('sprints.nuevo_sprint_2')} onClose={() => setShowCreateSprint(false)} width={500}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={ls}>{t('sprints.nombre_del_sprint')}</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={sprintForm.name} onChange={e => setSprintForm(f => ({ ...f, name: e.target.value }))} className={fs} placeholder={t('sprints.nombre_del_sprint_2')} /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={ls}>{t('sprints.objetivo_del_sprint')}</label><textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={sprintForm.goal} onChange={e => setSprintForm(f => ({ ...f, goal: e.target.value }))} rows={2} className={`${fs} spr-textarea`} placeholder={t('sprints.objetivo_del_sprint_2')} /></div>
            <div className="u-grid2-14">
              <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={ls}>{t('sprints.start_date')}</label><DateInput id={`${idCampo}-3`} value={sprintForm.start_date} onChange={e => setSprintForm(f => ({ ...f, start_date: e.target.value }))} className={fs} /></div>
              <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className={ls}>{t('sprints.end_date')}</label><DateInput id={`${idCampo}-4`} value={sprintForm.end_date} onChange={e => setSprintForm(f => ({ ...f, end_date: e.target.value }))} className={fs} /></div>
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreateSprint(false)}>{t('common.cancel')}</Button>
              <Button onClick={() => createSprint(sprintForm)} disabled={creatingS || !sprintForm.name}>{creatingS ? t('sprints.creando') : t('sprints.crear_sprint')}</Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Modal: Add tasks to sprint */}
      {showAddTasks && (
        <Modal open title={t('sprints.anadir_tareas_al_sprint')} onClose={() => setShowAddTasks(false)} width={600}>
          <div>
            {backlog.length === 0 ? (
              <EmptyState icon={<Inbox size={28} />} title={t('sprints.backlog_vacio')} description={t('sprints.backlog_vacio_modal_desc')} />
            ) : (
              <>
                <div className="spr-pick-hint">{t('sprints.selecciona_las_tareas_del_backlog_para_anadir')}</div>
                <div className="spr-pick-list">
                  {backlog.map(task => {
                    const sel = selectedBacklogTasks.includes(task.id)
                    return (
                      <label key={task.id} className={`spr-row spr-row--modal${sel ? ' spr-row--selected' : ''}`}>
                        <input type="checkbox" aria-label={task.title} checked={sel} onChange={e => setSelectedBacklogTasks(prev => e.target.checked ? [...prev, task.id] : prev.filter(id => id !== task.id))} />
                        <span className="u-text3-mono-xs">{task.code}</span>
                        <span className="u-sm">{task.title}</span>
                        <span className="spr-row__pts spr-row__pts--xs">{t('sprints.n_pt', { n: task.story_points || '—' })}</span>
                        <span className="u-text2-xs">{task.assignee_name?.split(' ')[0] || '—'}</span>
                      </label>
                    )
                  })}
                </div>
                <div className="spr-pick-foot">
                  <span className="u-text2-base" role="status">{t('sprints.n_seleccionadas', { n: selectedBacklogTasks.length })}</span>
                  <div className="u-row-10">
                    <Button variant="secondary" onClick={() => setShowAddTasks(false)}>{t('common.cancel')}</Button>
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
        <Modal open title={t('sprints.retro_titulo', { name: showRetro.name })} onClose={() => setShowRetro(null)} width={680}>
          <RetroModal sprint={showRetro} projectId={selectedProject} onClose={() => setShowRetro(null)} />
        </Modal>
      )}
      </div>
    </PageShell>
  )
}
