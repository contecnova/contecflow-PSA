/**
 * GanttPage — delegated to GanttChart v2 component.
 * Keeps all data-fetching / mutate / project-filter logic;
 * drops the old 26px-column custom grid.
 */
import { useState, useCallback, useMemo } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Button, Spinner, EmptyState } from '../components/ui'
import { useInvalidate } from '../hooks/useInvalidate'
import { useAppT } from '../i18n/AppLangContext'
import GanttChart from '../components/GanttChart'

export default function GanttPage() {
  const t            = useAppT()
  const toast         = useToast()
  const _qc           = useQueryClient()
  const { invalidate } = useInvalidate()

  const [projectId, setProjectId] = useState('')
  const [filter, setFilter]       = useState('')
  const [showBaseline, setShowBaseline] = useState(false)

  // ── data ────────────────────────────────────────────────────────────────────
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn:  () => projectsApi.list().then(r => r.data),
  })

  const { data: rawTasks = [], isLoading } = useQuery({
    queryKey: ['gantt-tasks', projectId],
    queryFn:  () => {
      const params = { page_size: 300, ...(projectId ? { project_id: projectId } : {}) }
      return api.get('/tasks', { params })
        .then(r => Array.isArray(r.data) ? r.data : (r.data?.items || []))
    },
    staleTime: 15000,
  })

  const { data: dependencies = [] } = useQuery({
    queryKey: ['task-deps', projectId],
    queryFn: () =>
      projectId
        ? api.get(`/task-dependencies/${projectId}`)
            .then(r => (Array.isArray(r.data.edges) ? r.data.edges : []))
            .catch(() => [])
        : Promise.resolve([]),
    staleTime: 30000,
  })

  // Optimistic local overrides for in-flight drags
  const [localDates, setLocalDates] = useState({})

  const tasks = useMemo(() => {
    const filtered = filter
      ? rawTasks.filter(t => t.title?.toLowerCase().includes(filter.toLowerCase()))
      : rawTasks
    return filtered.map(t => ({
      ...t,
      start_date: localDates[t.id]?.start_date ?? t.start_date,
      due_date:   localDates[t.id]?.due_date   ?? t.due_date,
    }))
  }, [rawTasks, localDates, filter])

  // ── mutations ───────────────────────────────────────────────────────────────
  const { mutate: saveDates } = useMutation({
    mutationFn: updates => api.post('/tasks/bulk-dates', { updates }),
    onSuccess:  () => { invalidate('tasks'); setLocalDates({}); toast.success(t('gantt.dates_saved')) },
    onError:    (e) => { setLocalDates({}); toast.error(e?.response?.data?.detail || t('gantt.error_save')) },
  })

  const { mutate: createDep } = useMutation({
    mutationFn: dep => api.post('/task-dependencies', {
      from_task_id: dep.predecessor_id,
      to_task_id: dep.successor_id,
      dep_type: dep.dependency_type || 'blocks',
      lag_days: dep.lag_days || 0,
    }),
    onSuccess:  () => { invalidate('task-deps'); toast.success(t('gantt.dependency_created')) },
    onError:    (e) => toast.error(e?.response?.data?.detail || t('gantt.error_create_dependency')),
  })

  // ── handlers ────────────────────────────────────────────────────────────────
  const handleTaskUpdate = useCallback(({ id, start, end }) => {
    setLocalDates(prev => ({ ...prev, [id]: { start_date: start, due_date: end } }))
    saveDates([{ id, start_date: start, due_date: end }])
  }, [saveDates])

  const handleDepCreate = useCallback(({ predecessor_id, successor_id }) => {
    createDep({ predecessor_id, successor_id, dependency_type: 'FS' })
  }, [createDep])

  const hasDates = tasks.some(t => t.start_date || t.due_date)

  // ── render ───────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 52px)', background: 'var(--surface-0)' }}>
      <div style={{ padding: '16px 24px 12px', flexShrink: 0 }}>
        <PageHeader
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
                  fontSize: 12, outline: 'none', width: 150, fontFamily: 'var(--font-sans)',
                }}
              />
              <select
                value={projectId}
                onChange={e => setProjectId(e.target.value)}
                style={{
                  background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                  borderRadius: 8, padding: '6px 12px', color: 'var(--text-1)',
                  fontSize: 12, outline: 'none', fontFamily: 'var(--font-sans)',
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
            </div>
          }
        />
      </div>

      {isLoading ? (
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <Spinner size={32} />
        </div>
      ) : !hasDates ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <EmptyState
            icon="📅"
            title={rawTasks.length === 0 ? t('gantt.no_tasks') : t('gantt.no_dates')}
            description={rawTasks.length === 0
              ? t('gantt.no_tasks_desc')
              : t('gantt.no_dates_desc', { count: rawTasks.length })
            }
          />
        </div>
      ) : (
        <div style={{ flex: 1, overflow: 'auto', padding: '0 24px 24px' }}>
          <GanttChart
            tasks={tasks}
            projects={projects}
            mode="project"
            onTaskUpdate={handleTaskUpdate}
            onDepCreate={handleDepCreate}
            showBaseline={showBaseline}
            dependencies={dependencies}
          />
        </div>
      )}
    </div>
  )
}
