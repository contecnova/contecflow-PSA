/**
 * GanttPage — delegated to GanttChart v2 component.
 * Keeps all data-fetching / mutate / project-filter logic;
 * drops the old 26px-column custom grid.
 */
import { useState, useCallback, useMemo } from 'react'
import { useToast } from '../context/ToastContext'
import type { ToastMessage } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tasksApi, taskDependenciesApi, projectsApi, aiCopilotApi } from '../services/api'
import type { SugerenciaDelGantt, SugerenciasDelGantt } from '../services/api/tipos-analitica'
import type { CambioDeFechas, DependenciaDeTarea } from '../services/api/tipos-proyectos'
import { BarChart2, CalendarDays } from 'lucide-react'
import { Button, Spinner, EmptyState, Tabs, Page, SearchInput, FilterSelect } from '../components/ui'
import PanelDelPlan from '../components/planificador/PanelDelPlan'
import PanelDeLineasBase from '../components/planificador/PanelDeLineasBase'
import EditorDeDependencias from '../components/planificador/EditorDeDependencias'
import PanelDeNivelacion from '../components/planificador/PanelDeNivelacion'
import { useInvalidate } from '../hooks/useInvalidate'
import { useAppT } from '../i18n/AppLangContext'
import GanttChart from '../components/GanttChart'
import { useAuth } from '../context/AuthContext'
import SmartScheduleModal from '../components/SmartScheduleModal'
import { Sparkles } from 'lucide-react'
import { STALE_DEFAULT_MS, STALE_NEAR_LIVE_MS, STALE_SHORT_MS } from '../constants/timings'
import { SCHEDULE_TASKS_LIST_SIZE } from '../constants/pagination'
import './GanttPage.css'

interface DateOverride {
  start_date?: string
  due_date?: string
}

type AiSuggestion = SugerenciaDelGantt

/** Rev. 173: `projectId` fijo cuando el Gantt va dentro de la ficha del proyecto
 *  (sin selector de proyecto ni cabecera de página). */
export default function GanttPage({ projectId: proyectoFijo }: { projectId?: string } = {}): JSX.Element {
  const traducir = useAppT()
  const t            = useAppT()
  const toast         = useToast()
  const _qc           = useQueryClient()
  const { invalidate } = useInvalidate()

  // `?project=` desde la ficha del proyecto (revisión 2026-11: se ignoraba).
  const [projectIdElegido, setProjectId] = useState(() => new URLSearchParams(window.location.search).get('project') || '')
  const projectId = proyectoFijo ?? projectIdElegido
  const [panel, setPanel] = useState('plan')
  const [filter, setFilter]       = useState('')
  const [showBaseline, setShowBaseline] = useState(false)
  const [smartScheduleOpen, setSmartScheduleOpen] = useState(false)
  // Mover fechas y crear dependencias exige admin o pm en el servidor: para el
  // resto el Gantt es de consulta (revisión 2026-11; antes arrastraban y les daba 403).
  const puedeEditar = useAuth().hasRole('admin', 'pm')

  // ── data ────────────────────────────────────────────────────────────────────
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn:  () => projectsApi.list({}).then(r => r.data),
  })

  const { data: rawTasks = [], isLoading } = useQuery({
    queryKey: ['gantt-tasks', projectId],
    queryFn:  () => {
      const params = { page_size: SCHEDULE_TASKS_LIST_SIZE, ...(projectId ? { project_id: projectId } : {}) }
      return tasksApi.list(params).then(r => r.data)
    },
    staleTime: STALE_NEAR_LIVE_MS,
  })

  const { data: todasLasDependencias = [] } = useQuery({
    queryKey: ['task-deps', projectId],
    queryFn: () =>
      projectId
        ? taskDependenciesApi.getByProject(projectId).then(r => r.data).catch((): DependenciaDeTarea[] => [])
        : Promise.resolve<DependenciaDeTarea[]>([]),
    staleTime: STALE_SHORT_MS,
  })
  // Rev. 173: los vínculos informativos (relacionada, duplicada…) no son flechas del Gantt.
  const dependencies = useMemo(
    () => todasLasDependencias.filter(d => (d.link_type ?? 'schedule') === 'schedule'),
    [todasLasDependencias],
  )

  // Item #47: sugerencias IA (overdue/stalled) por proyecto. Solo cargamos
  // cuando hay project_id seleccionado — sin él la heurística no puede
  // contextualizar y el endpoint requiere proyecto específico.
  const { data: aiSuggestionsResp } = useQuery<Pick<SugerenciasDelGantt, 'suggestions'>>({
    queryKey: ['ai-gantt-suggestions', projectId],
    queryFn: () =>
      projectId
        ? aiCopilotApi.ganttSuggestions(projectId)
            .then(r => r.data)
            .catch(() => ({ suggestions: [] }))
        : Promise.resolve({ suggestions: [] }),
    enabled: !!projectId,
    staleTime: STALE_DEFAULT_MS,
  })

  // Map task_id → suggestion para lookup O(1) en GanttChart.
  const aiSuggestionsByTask = useMemo(() => {
    const out: Record<string, AiSuggestion> = {}
    for (const s of (aiSuggestionsResp?.suggestions || [])) {
      if (s?.task_id) out[String(s.task_id)] = s
    }
    return out
  }, [aiSuggestionsResp])

  // Optimistic local overrides for in-flight drags
  const [localDates, setLocalDates] = useState<Record<string, DateOverride>>({})

  const tasks = useMemo(() => {
    const filtered = filter
      ? rawTasks.filter((t) => String(t.title || '').toLowerCase().includes(filter.toLowerCase()))
      : rawTasks
    return filtered.map(t => ({
      ...t,
      // Fallback to created_at so Gantt still renders rows when explicit dates are missing.
      start_date: localDates[t.id]?.start_date ?? t.start_date ?? t.created_at?.slice(0, 10),
      due_date:   localDates[t.id]?.due_date   ?? t.due_date,
    }))
  }, [rawTasks, localDates, filter])
  // GanttChart pinta filas genéricas (con índice): la copia deja pasar el proyecto tal cual.
  const filasDeProyecto = useMemo(() => projects.map(p => ({ ...p })), [projects])

  // ── mutations ───────────────────────────────────────────────────────────────
  const { mutate: saveDates } = useMutation({
    mutationFn: (updates: CambioDeFechas[]) => taskDependenciesApi.bulkDates(updates),
    onSuccess:  () => { invalidate('tasks'); invalidate('gantt-tasks'); invalidate('plan'); setLocalDates({}); toast.success(t('gantt.dates_saved')) },
    onError:    (e: unknown) => {
      setLocalDates({})
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      toast.error(((detail && String(detail)) || t('gantt.error_save')) as ToastMessage)
    },
  })

  const { mutate: createDep } = useMutation({
    mutationFn: (dep: { predecessor_id: string | number; successor_id: string | number; dependency_type?: string; lag_days?: number }) => taskDependenciesApi.create({
      predecessor_id: dep.predecessor_id,
      successor_id: dep.successor_id,
      dependency_type: dep.dependency_type || 'FS',
      lag_days: dep.lag_days || 0,
    }),
    onSuccess:  () => { invalidate('task-deps'); toast.success(t('gantt.dependency_created')) },
    onError:    (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      toast.error(((detail && String(detail)) || t('gantt.error_create_dependency')) as ToastMessage)
    },
  })

  // ── handlers ────────────────────────────────────────────────────────────────
  const handleTaskUpdate = useCallback(({ id, start, end }: { id: string; start: string; end: string }) => {
    setLocalDates(prev => ({ ...prev, [id]: { start_date: start, due_date: end } }))
    saveDates([{ id, start_date: start, due_date: end }])
  }, [saveDates])

  const handleDepCreate = useCallback(({ predecessor_id, successor_id }: { predecessor_id: string | number; successor_id: string | number }) => {
    createDep({ predecessor_id, successor_id, dependency_type: 'FS' })
  }, [createDep])

  const hasTasks = tasks.length > 0

  // ── render ───────────────────────────────────────────────────────────────────
  const paneles = [
    { id: 'plan', label: t('planificador.pestana_plan') },
    { id: 'dependencias', label: t('planificador.pestana_dependencias') },
    { id: 'lineas', label: t('planificador.pestana_lineas_base') },
    ...(puedeEditar ? [{ id: 'nivelacion', label: t('planificador.pestana_nivelacion') }] : []),
  ]

  // 16-11-2026 (pasada de diseño): los filtros van en una barra bajo la
  // cabecera (no en ella) y la página usa el contenedor estándar.
  const contenido = (
    <>
      <div className="ds-toolbar">
        <SearchInput value={filter} onChange={setFilter} placeholder={t('gantt.filter_ph')} />
        {!proyectoFijo && (
          <FilterSelect
            value={projectId}
            onChange={setProjectId}
            placeholder={t('gantt.all_projects')}
            options={projects.map(p => ({ value: String(p.id), label: `${p.code} — ${p.name}` }))}
          />
        )}
        <Button size="sm" variant={showBaseline ? 'primary' : 'secondary'} onClick={() => setShowBaseline(b => !b)}>
          {t('gantt.baseline')}
        </Button>
      </div>

      {isLoading ? (
        <div className="gantt-row">
          <Spinner size={32} />
        </div>
      ) : !hasTasks ? (
        <EmptyState
          icon={<CalendarDays size={28} />}
          title={t('gantt.no_tasks')}
          description={t('gantt.no_tasks_desc')}
        />
      ) : (
        <div className="gantt-box-2">
          <GanttChart
            tasks={tasks}
            projects={filasDeProyecto}
            mode="project"
            onTaskUpdate={puedeEditar ? handleTaskUpdate : undefined}
            onDepCreate={puedeEditar ? handleDepCreate : undefined}
            showBaseline={showBaseline}
            dependencies={dependencies}
            aiSuggestions={aiSuggestionsByTask}
          />
        </div>
      )}
      {projectId && (
        <div>
          <Tabs items={paneles} active={panel} onChange={setPanel} ariaLabel={t('planificador.pestanas_del_plan')} />
          <div className="gantt-panel">
            {panel === 'plan' && <PanelDelPlan projectId={projectId} />}
            {panel === 'dependencias' && <EditorDeDependencias projectId={projectId} />}
            {panel === 'lineas' && <PanelDeLineasBase projectId={projectId} />}
            {panel === 'nivelacion' && puedeEditar && <PanelDeNivelacion projectId={projectId} />}
          </div>
        </div>
      )}
      <SmartScheduleModal
        open={smartScheduleOpen}
        onClose={() => setSmartScheduleOpen(false)}
        projectId={projectId || null}
        projectName={projects.find(p => p.id === projectId)?.name}
      />
    </>
  )

  if (proyectoFijo) return <div className="gantt-stack">{contenido}</div>

  return (
    <Page
      icon={<BarChart2 size={18} />}
      title={t('nav.gantt')}
      subtitle={t('gantt.subtitle')}
      actions={puedeEditar ? (
        // I27: auto-planificar tareas sin fecha.
        <Button icon={<Sparkles size={14} />} onClick={() => setSmartScheduleOpen(true)}
          title={traducir('gantt.sugerir_fechas_para_tareas_sin_planificar_usando')}>
          {t('pagina_gantt.auto_planificar')}
        </Button>
      ) : undefined}
    >
      {contenido}
    </Page>
  )
}
