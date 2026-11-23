/**
 * TasksPage — tareas: tablero, lista y vistas del planificador.
 *
 * 16-11-2026: el selector de vista sale de la cabecera a una barra <Tabs>
 * (antes control segmentado dentro de las acciones); "Auto-planificar" con
 * Button secondary (antes variante azul clara `subtle`) e iconos por prop;
 * vacíos con icono lucide y descripción correcta (antes decía solo "Tarea" y
 * "Estado"); emojis de tarjetas, prioridades y botones del panel (📅🕐✅🗑✏️💾🧠⏳
 * 🟢🟡🔴🚨) cambiados por iconos lucide o quitados; pestañas del panel sin
 * estilo en línea.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { pedirTexto } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sprintsApi, cmdbApi, usersApi, type PersonaVisible } from '../services/api'
import { Buscador, Button, EmptyState, useSort, Tabs, Select, Chip, BarraDeFiltros } from '../components/ui'
import { SkeletonTable } from '../components/ui/Skeletons'
import VistasDeTrabajo, { VISTAS_DE_TRABAJO, type FiltrosDeVistas, type VistaDeTrabajo } from '../components/planificador/VistasDeTrabajo'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CheckSquare, LayoutGrid, List, Plus, Sparkles } from 'lucide-react'
import SmartScheduleModal from '../components/SmartScheduleModal'
import { extractErr } from '../utils/helpers'
import { COLUMNAS_DE_TABLERO } from '../constants/catalogos'
import { useCatalogo } from '../hooks/useCatalogo'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { STALE_REFERENCE_DATA_MS } from '../constants/timings'
import { useListaDeProyectos } from '../hooks/useListas'
import { type BulkBody, type BulkResult, ESTADOS_ABIERTOS, ICONO_DE_VISTA, type KanbanConfig, nombreDeEstado, nombreDePrioridadT, PRIORIDADES, type Sprint, tareas, TAREAS_MAXIMAS, type Task } from './tareas/compartido'
import { KanbanColumn } from './tareas/TarjetasKanban'
import { TaskDetailModal } from './tareas/DetalleDeTarea'
import { CreateTaskModal } from './tareas/AltaDeTarea'
import { BarraAccionesMasivas } from './tareas/BarraAccionesMasivas'
import { ListaDeTareas } from './tareas/ListaDeTareas'
import './TasksPage.css'

export default function TasksPage() {
  const traducir = useAppT()
  const estadosDeTarea = useCatalogo('task-statuses')
  const STATUSES = estadosDeTarea.valores.length
    ? estadosDeTarea.valores.map(v => v.value).filter(v => v !== 'backlog' && v !== 'cancelled')
    : COLUMNAS_DE_TABLERO
  const t = useAppT()
  const { puede } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  // ── Kanban drag-and-drop state ────────────────────────────────────────────
  const dragTask      = useRef<Task | null>(null)
  const ghostRef      = useRef<HTMLDivElement | null>(null)
  const dropTargetRef = useRef<string | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)

  const cleanupGhost = useCallback(() => {
    if (ghostRef.current) { ghostRef.current.remove(); ghostRef.current = null }
  }, [])

  const { mutate: moveTaskStatus } = useMutation({
    mutationFn: ({ id, status, move_reason }: { id: string; status: string; move_reason?: string }) =>
      tareas.update(id, { status, ...(move_reason ? { move_reason } : {}) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban-board'] })
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('tasks.error_mover'))),
  })

  const requestMoveTask = useCallback(async (id: string, fromStatus: string, toStatus: string) => {
    if (fromStatus === toStatus) return
    let move_reason
    if (fromStatus === 'done' || fromStatus === 'cancelled') {
      move_reason = await pedirTexto({
        title: t('tasks.mover_cerrada_titulo'),
        message: t('tasks.mover_cerrada_mensaje', { estado: nombreDeEstado(t, fromStatus) }),
        label: t('tasks.motivo'),
        multiline: true,
        confirmLabel: t('tasks.mover'),
      })
      if (move_reason === null) return
      move_reason = move_reason.trim() || undefined
    }
    moveTaskStatus({ id, status: toStatus, move_reason })
  }, [moveTaskStatus, t])

  const handleTaskDragStart = useCallback((e: React.MouseEvent, task: Task, onDragStarted: () => void) => {
    const startX = e.clientX
    const startY = e.clientY
    let dragging = false

    const onMove = (ev: MouseEvent) => {
      if (!dragging) {
        const dx = ev.clientX - startX
        const dy = ev.clientY - startY
        if (Math.sqrt(dx * dx + dy * dy) < 5) return
        dragging = true
        dragTask.current = task
        onDragStarted()
        const ghost = document.createElement('div')
        ghost.textContent = task.title
        ghost.className = 'tsk-drag-ghost'
        ghost.style.left = ev.clientX + 12 + 'px'
        ghost.style.top  = ev.clientY + 12 + 'px'
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

  const handleColumnEnter = useCallback((status: string) => {
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
    mineOnly ? { key: 'mine', label: t('tasks.filtro_mis_tareas'), onClear: () => setTaskParam('mine', '') } : null,
    overdueOnly ? { key: 'overdue', label: t('tasks.filtro_vencidas'), onClear: () => setTaskParam('overdue', '') } : null,
    statusFilter === 'open' ? { key: 'open', label: t('tasks.filtro_estado_abiertas'), onClear: () => setTaskParam('status', '') } : null,
  ].filter(Boolean)
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)
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

  const { data: projects = [] } = useListaDeProyectos()

  // Revisión 2026-11: tablero y lista enseñan LAS MISMAS tareas (la misma consulta
  // y los mismos filtros). Antes el tablero con proyecto usaba otro endpoint que
  // ignoraba persona, vencidas y «mías», y la lista se cortaba en 50 sin avisar.
  const { data: tasksData, isLoading } = useQuery<{ items: Task[]; total: number }>({
    queryKey: ['tasks', view, projectFilter, statusFilter, search, priorityFilter, assigneeFilter, overdueOnly, mineOnly, sprintFilter],
    queryFn: () => {
      const effectiveStatus = statusFilter === 'open'
        ? ESTADOS_ABIERTOS
        : (statusFilter || undefined)
      return tareas.list({
        project_id: projectFilter || undefined,
        status: view === 'kanban' ? undefined : effectiveStatus,
        search: search || undefined,
        priority: priorityFilter || undefined,
        assignee_id: assigneeFilter || undefined,
        overdue_only: overdueOnly || undefined,
        assigned_to_me: mineOnly || undefined,
        sprint_id: (projectFilter && sprintFilter) || undefined,
        page_size: TAREAS_MAXIMAS,
      }).then(r => {
        const d = r.data as Task[] | { items?: Task[]; total?: number }
        const items = Array.isArray(d) ? d : (d?.items ?? [])
        const total = Number(r.headers?.['x-total-count'] ?? (Array.isArray(d) ? undefined : d?.total) ?? items.length)
        return { items, total }
      })
    },
    placeholderData: prev => prev,
  })

  const projectOptions = projects.map(p => ({ value: p.id, label: `${p.code} — ${p.name}` }))

  const flatTasks: Task[] = tasksData?.items ?? []
  const cortadas = (tasksData?.total ?? 0) > flatTasks.length

  const { sort: taskSort, setSort: setTaskSort, sortedData: sortedTasks } = useSort(flatTasks, 'title')

  // Revisión 2026-11: sin proyecto el Kanban caía en una lista. Ahora agrupa por
  // estado las mismas tareas que mostraría la lista (con sus filtros).
  const agrupar = (lista: Task[]) => lista.reduce<Record<string, Task[]>>((a, task) => {
    if (task.status !== 'cancelled') (a[task.status] = a[task.status] || []).push(task)
    return a
  }, STATUSES.reduce<Record<string, Task[]>>((a, s) => ({ ...a, [s]: [] }), {}))
  const kanbanColumns = agrupar(flatTasks)

  // ── Tablero: sprint, carriles y límites WIP (revisión 2026-11) ───────────────
  // Venían de la pantalla «Kanban» (/kanban-advanced), que enseñaba las mismas
  // tareas por estado; ahora es una sola. Carriles y WIP se guardan por proyecto
  // (`/cmdb/kanban/{proyecto}`): antes los límites vivían en memoria y se perdían.
  const puedeConfigurar = puede('tareas.gestionar')
  const { data: sprintsDelProyecto = [] } = useQuery<Sprint[]>({
    queryKey: ['sprints', projectFilter], enabled: !!projectFilter,
    queryFn: () => sprintsApi.list(projectFilter).then(r => r.data ?? []),
  })
  const { data: tablero } = useQuery<KanbanConfig>({
    queryKey: ['kanban-config', projectFilter], enabled: !!projectFilter,
    queryFn: () => cmdbApi.kanbanConfig(projectFilter).then(r => r.data),
  })
  const carril = carriles || (projectFilter && tablero?.swimlane_by) || 'none'
  const limiteWip = (status: string): number | null =>
    (tablero?.columns || []).find(c => c.status === status)?.wip_limit ?? null
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
      const col = (tablero?.columns || []).find(c => c.status === status)
      if (col) await cmdbApi.updateKanbanColumn(col.id, { status, wip_limit: n })
      else await cmdbApi.addKanbanColumn(projectFilter, { status, wip_limit: n })
      qc.invalidateQueries({ queryKey: ['kanban-config', projectFilter] })
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
  const crearEnColumna = (status: string) => async (titulo: string) => {
    try {
      await tareas.create({ title: titulo, status, project_id: projectFilter })
      qc.invalidateQueries({ queryKey: ['tasks'] })
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
    const filasDelTablero: { id: string; titulo: string | null; tareas: Task[] }[] = (() => {
    if (carril === 'assignee') {
      const g: Record<string, { id: string; titulo: string; tareas: Task[] }> = {}
      for (const task of flatTasks) {
        const k = task.assignee_id || '__sin'
        g[k] = g[k] || { id: k, titulo: task.assignee?.full_name || t('tasks.no_assignee'), tareas: [] }
        g[k].tareas.push(task)
      }
      return Object.values(g).sort((a, b) => a.titulo.localeCompare(b.titulo))
    }
    if (carril === 'priority') {
      return ['critical', 'high', 'medium', 'low']
        .map(p => ({ id: p, titulo: nombreDePrioridadT(t, p), tareas: flatTasks.filter(x => x.priority === p) }))
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
  const { data: allUsers = [] } = useQuery<PersonaVisible[]>({
    // Selector de personas: `/users/directory` sirve a cualquier rol (`/users` da 403 al subcontratado).
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
    staleTime: STALE_REFERENCE_DATA_MS,
  })

  const { mutate: bulkMutate, isPending: bulkPending } = useMutation({
    mutationFn: (payload: BulkBody) => tareas.bulkUpdate(payload),
    onSuccess: res => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-my-tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] })
      qc.invalidateQueries({ queryKey: ['cal-tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban-board'] })
      const data: BulkResult = res.data
      const n = data?.updated ?? 0
      const s = data?.skipped?.length ?? 0
      toast.success(t(n === 1 ? 'tasks.bulk_actualizada_1' : 'tasks.bulk_actualizadas', { n })
        + (s > 0 ? ` · ${t(s === 1 ? 'tasks.bulk_omitida_1' : 'tasks.bulk_omitidas', { n: s })}` : ''))
      setSelected(new Set())
      setBulkStatus(''); setBulkAssignee(''); setBulkPriority('')
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('tasks.bulk_error'))),
  })

  const toggleSelect = (id: string) => setSelected(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })
  const toggleAll = () => setSelected(prev =>
    prev.size === flatTasks.length ? new Set<string>() : new Set<string>(flatTasks.map(t => t.id))
  )
  const applyBulk = () => {
    if (selected.size === 0) return
    const payload: BulkBody = { task_ids: [...selected] }
    if (bulkStatus)   payload.status = bulkStatus
    if (bulkAssignee) payload.assignee_id = bulkAssignee
    if (bulkPriority) payload.priority = bulkPriority
    if (!payload.status && !payload.assignee_id && !payload.priority) {
      toast.error(t('tasks.bulk_sin_campos'))
      return
    }
    bulkMutate(payload)
  }

  // ── Barra de filtros única ───────────────────────────────────────────────
  const esVistaDeTrabajo = (VISTAS_DE_TRABAJO as readonly string[]).includes(view)
  // La carga por persona solo depende del proyecto: el resto de filtros no se enseña.
  const soloProyecto = view === 'workload'
  const filtrosDeVistas: FiltrosDeVistas = {
    status: (statusFilter === 'open' ? ESTADOS_ABIERTOS : statusFilter) || undefined,
    search: search || undefined,
    priority: (priorityFilter || undefined) as FiltrosDeVistas['priority'],
    assignee_id: assigneeFilter || undefined,
    overdue_only: overdueOnly || undefined,
    assigned_to_me: mineOnly || undefined,
    sprint_id: (projectFilter && sprintFilter) || undefined,
  }
  const aplicarFiltrosDeVista = ({ status, assignee }: { status?: string; assignee?: string }) => setSearchParams(p => {
    const n = new URLSearchParams(p)
    const estado = status === ESTADOS_ABIERTOS ? 'open' : status
    estado ? n.set('status', estado) : n.delete('status')
    assignee ? n.set('assignee', assignee) : n.delete('assignee')
    return n
  }, { replace: true })
  const controlesDeFiltro = (
    <>
      {!soloProyecto && (
        <Buscador className="tsk-search" aria-label={t('tasks.search_placeholder')} ref={buscador} value={search} onChange={setSearch} placeholder={t('tasks.search_placeholder')} aria-keyshortcuts="/" />
      )}
      <Select suelto placeholder={false} aria-label={t('tasks.all_projects')} value={projectFilter} onChange={e => setProjectFilter(e.target.value)}
        className="tsk-filter--project">
        <option value="">{t('tasks.all_projects')}</option>
        {projectOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </Select>
      {!soloProyecto && (
        <>
          <Select suelto placeholder={false} aria-label={t('tasks.filter_priority')} value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}
            className={`tsk-filter${priorityFilter ? ' tsk-filter--accent' : ''}`}>
            <option value="">{t('tasks.filter_priority')}</option>
            {PRIORIDADES.map(p => <option key={p} value={p}>{nombreDePrioridadT(t, p)}</option>)}
          </Select>
          <Select suelto placeholder={false} aria-label={t('tasks.all_assignees')} value={assigneeFilter} onChange={e => setAssigneeFilter(e.target.value)}
            className={`tsk-filter${assigneeFilter ? ' tsk-filter--accent' : ''}`}>
            <option value="">{t('tasks.all_assignees')}</option>
            {allUsers.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>
          {projectFilter && sprintsDelProyecto.length > 0 && (
            <Select suelto placeholder={false} aria-label={t('tasks.kanban_sprint')} value={sprintFilter} onChange={e => setSprintFilter(e.target.value)}
              className={`tsk-filter${sprintFilter ? ' tsk-filter--accent' : ''}`}>
              <option value="">{t('tasks.kanban_todos_los_sprints')}</option>
              {sprintsDelProyecto.map(sp => <option key={sp.id} value={sp.id}>{sp.name}</option>)}
            </Select>
          )}
        </>
      )}
      {view === 'kanban' && (
        <Select suelto placeholder={false} aria-label={t('tasks.kanban_carriles')} value={carril} onChange={e => guardarCarril(e.target.value)}
          className="tsk-filter">
          <option value="none">{t('tasks.kanban_sin_carriles')}</option>
          <option value="assignee">{t('tasks.kanban_carril_persona')}</option>
          <option value="priority">{t('tasks.kanban_carril_prioridad')}</option>
        </Select>
      )}
      {(view === 'list' || (esVistaDeTrabajo && !soloProyecto)) && (
        <Select suelto placeholder={false} aria-label={t('tasks.filter_status')} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="tsk-filter">
          <option value="">{t('tasks.filter_status')}</option>
          <option value="open">{t('tasks.estado_abiertas')}</option>
          {STATUSES.map(v => <option key={v} value={v}>{nombreDeEstado(t, v)}</option>)}
        </Select>
      )}
    </>
  )

  return (
    <PageShell>
      <PageHeader
        icon={<CheckSquare size={18} />}
        title={t('tasks.title')}
        subtitle={t('tasks.subtitle')}
        exportTargetSelector='[data-export-table="tasks-list"]'
        exportFilePrefix='tasks'
        actions={
          <div className={`tsk-header-actions${isMobile ? ' tsk-header-actions--full' : ''}`}>
            {/* I27: Auto-planificar. Aplicar las fechas (bulk-dates) exige admin o pm. */}
            {puede('tareas.gestionar') && (
              <Button
                variant="secondary"
                icon={<Sparkles size={14} />}
                onClick={() => setSmartScheduleOpen(true)}
                title={traducir('tasks.sugerir_fechas_para_tareas_sin_planificar_usando')}
              >
                {t('tasks.auto_planificar')}
              </Button>
            )}
            {puede('tareas.crear') && (
              <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>
                {t('tasks.new_task')}
              </Button>
            )}
          </div>
        }
      />

      {/* Vista: tablero, lista y (rev. 173) tabla editable, línea temporal, calendario y carga por persona */}
      <div className="tsk-views">
        <Tabs
          ariaLabel={t('tasks.vista')}
          active={view}
          onChange={setView}
          items={[
            { id: 'kanban', label: t('tasks.vista_kanban'), icon: <LayoutGrid size={14} /> },
            { id: 'list', label: t('tasks.vista_lista'), icon: <List size={14} /> },
            ...VISTAS_DE_TRABAJO.map(v => ({ id: v, label: t(`planificador.vista_${v}`), icon: ICONO_DE_VISTA[v] })),
          ]}
        />
      </div>

      {/* Quick filter pills */}
      {quickFilterPills.length > 0 && (
        <div className="ds-row-wrap tsk-pills">
          {quickFilterPills.map(pill => (
            <Chip key={pill.key} activo onQuitar={pill.onClear}>{pill.label}</Chip>
          ))}
          <Button variant="link" size="sm" onClick={clearQuickFilters}>
            {traducir('tasks.limpiar_filtros_rapidos')}
          </Button>
        </div>
      )}

      {/* Una sola barra de filtros (17-11-2026): en tablero y lista es la de la
          página; en las vistas de trabajo, estos mismos controles encabezan la
          barra de VistasDeTrabajo (columnas y vistas guardadas). Los filtros
          viven en la URL. */}
      {!esVistaDeTrabajo && (
        <BarraDeFiltros className="tsk-toolbar">
          {controlesDeFiltro}
        </BarraDeFiltros>
      )}

      {/* ── Bulk Action Bar ─────────────────────────────────────────────── */}
      {selected.size > 0 && (
        <BarraAccionesMasivas
          cantidad={selected.size}
          estado={bulkStatus} onEstado={setBulkStatus}
          prioridad={bulkPriority} onPrioridad={setBulkPriority}
          responsable={bulkAssignee} onResponsable={setBulkAssignee}
          usuarios={allUsers}
          onAplicar={applyBulk}
          aplicando={bulkPending}
          onCancelar={() => { setSelected(new Set()); setBulkStatus(''); setBulkPriority(''); setBulkAssignee('') }}
        />
      )}

      {cortadas && (
        <div role="status" className="tsk-truncated">
          {t('tasks.mostrando_de', { n: flatTasks.length, total: tasksData?.total ?? 0 })}
        </div>
      )}
      {esVistaDeTrabajo ? (
        <VistasDeTrabajo projectId={projectFilter || undefined} vista={view as VistaDeTrabajo} onVista={setView}
          filtros={filtrosDeVistas} filtrosDePagina={controlesDeFiltro} onFiltros={aplicarFiltrosDeVista} />
      ) : isLoading ? (
        <SkeletonTable rows={10} />
      ) : view === 'kanban' ? (
        flatTasks.length === 0 && !projectFilter ? (
          <EmptyState
            icon={<CheckSquare size={28} />}
            title={t('tasks.no_tasks')}
            description={puede('tareas.crear') ? t('tasks.vacio_desc_crear') : t('tasks.vacio_desc')}
            action={puede('tareas.crear') ? <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('tasks.new_task')}</Button> : undefined}
          />
        ) : (
          <div className="tsk-board">
            {filasDelTablero.map(fila => {
              const columnas = agrupar(fila.tareas)
              return (
                <section key={fila.id} aria-label={fila.titulo || undefined}>
                  {fila.titulo && (
                    <div className="tsk-lane-title">
                      {fila.titulo} <span className="tsk-lane-count">· {fila.tareas.length}</span>
                    </div>
                  )}
                  <div className={`tsk-lane${isCompact ? ' tsk-lane--compact' : ''}`}>
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
        <ListaDeTareas
          tareas={flatTasks} ordenadas={sortedTasks} compacta={isCompact} proyectos={projects}
          seleccion={selected} onAlternar={toggleSelect} onAlternarTodas={toggleAll}
          orden={taskSort} onOrden={setTaskSort} onAbrir={setSelectedTask}
        />
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
