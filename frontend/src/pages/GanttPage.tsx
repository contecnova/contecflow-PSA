/**
 * GanttPage — delegated to GanttChart v2 component.
 * Keeps all data-fetching / mutate / project-filter logic;
 * drops the old 26px-column custom grid.
 */
import { useState, useCallback, useMemo } from 'react'
import type { ComponentProps } from 'react'
import { useToast } from '../context/ToastContext'
import type { ToastMessage } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tasksApi, taskDependenciesApi, projectsApi, aiCopilotApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { BarChart2 } from 'lucide-react'
import { Button, Spinner, EmptyState } from '../components/ui'
import { useInvalidate } from '../hooks/useInvalidate'
import { useAppT } from '../i18n/AppLangContext'
import GanttChart from '../components/GanttChart'
import { useAuth } from '../context/AuthContext'
import SmartScheduleModal from '../components/SmartScheduleModal'
import { Sparkles } from 'lucide-react'

interface ProjectItem {
  id: string | number
  code?: string
  name?: string
}

interface TaskItem {
  id: string | number
  title?: string
  project_id?: string | number
  created_at?: string
  start_date?: string
  due_date?: string
  [key: string]: unknown
}

interface DateOverride {
  start_date?: string
  due_date?: string
}

interface AiSuggestion {
  task_id?: string | number
  severity?: string
  type?: string
  message?: string
  suggestions?: string[]
}

interface DependencyItem {
  [key: string]: unknown
}

export default function GanttPage(): JSX.Element {
  const traducir = useAppT()
  const t            = useAppT()
  const toast         = useToast()
  const _qc           = useQueryClient()
  const { invalidate } = useInvalidate()

  // `?project=` desde la ficha del proyecto (revisión 2026-11: se ignoraba).
  const [projectId, setProjectId] = useState(() => new URLSearchParams(window.location.search).get('project') || '')
  const [filter, setFilter]       = useState('')
  const [showBaseline, setShowBaseline] = useState(false)
  const [smartScheduleOpen, setSmartScheduleOpen] = useState(false)
  // Mover fechas y crear dependencias exige admin o pm en el servidor: para el
  // resto el Gantt es de consulta (revisión 2026-11; antes arrastraban y les daba 403).
  const puedeEditar = useAuth().hasRole('admin', 'pm')

  // ── data ────────────────────────────────────────────────────────────────────
  const { data: projects = [] } = useQuery<ProjectItem[]>({
    queryKey: ['projects'],
    queryFn:  () => projectsApi.list({}).then(r => (r.data as unknown as { items?: ProjectItem[] })?.items ?? (r.data as unknown as ProjectItem[]) ?? []),
  })

  const { data: rawTasks = [], isLoading } = useQuery<TaskItem[]>({
    queryKey: ['gantt-tasks', projectId],
    queryFn:  () => {
      const params = { page_size: 300, ...(projectId ? { project_id: projectId } : {}) }
      return tasksApi.list(params)
          .then(r => Array.isArray(r.data) ? (r.data as unknown as TaskItem[]) : (((r.data as unknown as { items?: TaskItem[] })?.items || []) as TaskItem[]))
    },
    staleTime: 15000,
  })

        const { data: dependencies = [] } = useQuery<DependencyItem[]>({
    queryKey: ['task-deps', projectId],
    queryFn: () =>
      projectId
        ? taskDependenciesApi.getByProject(projectId)
            .then(r => (Array.isArray(r.data) ? (r.data as DependencyItem[]) : []))
            .catch(() => [])
        : Promise.resolve([]),
    staleTime: 30000,
  })

  // Item #47: sugerencias IA (overdue/stalled) por proyecto. Solo cargamos
  // cuando hay project_id seleccionado — sin él la heurística no puede
  // contextualizar y el endpoint requiere proyecto específico.
  const { data: aiSuggestionsResp } = useQuery<{ suggestions?: AiSuggestion[] }>({
    queryKey: ['ai-gantt-suggestions', projectId],
    queryFn: () =>
      projectId
        ? aiCopilotApi.ganttSuggestions(projectId)
            .then(r => r.data)
            .catch(() => ({ suggestions: [] }))
        : Promise.resolve({ suggestions: [] }),
    enabled: !!projectId,
    staleTime: 60000,
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
  const [localDates, setLocalDates] = useState<Record<string | number, DateOverride>>({})

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

  // ── mutations ───────────────────────────────────────────────────────────────
  const { mutate: saveDates } = useMutation({
    mutationFn: (updates: Array<{ id: string | number; start_date?: string; due_date?: string }>) => taskDependenciesApi.bulkDates(updates as unknown as Record<string, unknown>),
    onSuccess:  () => { invalidate('tasks'); setLocalDates({}); toast.success(t('gantt.dates_saved')) },
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
  const handleTaskUpdate = useCallback(({ id, start, end }: { id: string | number; start: string; end: string }) => {
    setLocalDates(prev => ({ ...prev, [id]: { start_date: start, due_date: end } }))
    saveDates([{ id, start_date: start, due_date: end }])
  }, [saveDates])

  const handleDepCreate = useCallback(({ predecessor_id, successor_id }: { predecessor_id: string | number; successor_id: string | number }) => {
    createDep({ predecessor_id, successor_id, dependency_type: 'FS' })
  }, [createDep])

  const hasTasks = tasks.length > 0

  // ── render ───────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 52px)', background: 'var(--surface-0)' }}>
      <div style={{ padding: '16px 24px 12px', flexShrink: 0 }}>
        <PageHeader
        icon={<BarChart2 size={18} />}
          title={t('gantt.title')}
          subtitle={t('gantt.subtitle')}
          actions={
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                placeholder={t('gantt.filter_ph')}
                value={filter}
                onChange={e => setFilter(e.target.value)}
                style={{
                  background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                  borderRadius: 8, padding: '6px 12px', color: 'var(--text-1)',
                  fontSize: "var(--text-sm)", outline: 'none', width: 150, fontFamily: 'var(--font-sans)',
                }}
              />
              <select
                value={projectId}
                onChange={e => setProjectId(e.target.value)}
                style={{
                  background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                  borderRadius: 8, padding: '6px 12px', color: 'var(--text-1)',
                  fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'var(--font-sans)',
                }}
              >
                <option value="">{t('gantt.all_projects')}</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
              <Button
                size="sm"
                variant={showBaseline ? 'primary' : 'subtle'}
                onClick={() => setShowBaseline(b => !b)}
              >
                {t('gantt.baseline')}
              </Button>
              {/* I27: Auto-planificar tareas sin fecha (botón en Gantt) */}
              {puedeEditar && <Button
                size="sm"
                variant="subtle"
                onClick={() => setSmartScheduleOpen(true)}
                title={traducir('gantt.sugerir_fechas_para_tareas_sin_planificar_usando')}
              >
                <Sparkles size={13} style={{ marginRight: 4 }} /> Auto-planificar
              </Button>}
            </div>
          }
          showListExport={false}
        />
      </div>

      {isLoading ? (
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <Spinner size={32} />
        </div>
      ) : !hasTasks ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <EmptyState
            icon="📅"
            title={t('gantt.no_tasks')}
            description={t('gantt.no_tasks_desc')}
          />
        </div>
      ) : (
        <div style={{ flex: 1, overflow: 'auto', padding: '0 24px 24px' }}>
          <GanttChart
            tasks={tasks as unknown as ComponentProps<typeof GanttChart>['tasks']}
            projects={projects as unknown as ComponentProps<typeof GanttChart>['projects']}
            mode="project"
            onTaskUpdate={puedeEditar ? handleTaskUpdate : undefined}
            onDepCreate={puedeEditar ? handleDepCreate : undefined}
            showBaseline={showBaseline}
            dependencies={dependencies as unknown as ComponentProps<typeof GanttChart>['dependencies']}
            aiSuggestions={aiSuggestionsByTask}
          />
        </div>
      )}
      <SmartScheduleModal
        open={smartScheduleOpen}
        onClose={() => setSmartScheduleOpen(false)}
        projectId={projectId || null}
        projectName={projects.find(p => p.id === projectId)?.name}
      />
    </div>
  )
}
