// 16-11-2026: el Gantt pinta las fechas del motor de planificación (sin fijar)
// cuando las tareas no tienen start/due, con «Todos los proyectos».
import { vi, describe, it, expect } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { api } = vi.hoisted(() => ({
  api: {
    projectsApi: { list: vi.fn() },
    tasksApi: { list: vi.fn() },
    taskDependenciesApi: { getByProject: vi.fn(), bulkDates: vi.fn(), create: vi.fn() },
    aiCopilotApi: { ganttSuggestions: vi.fn() },
    planificacionApi: { plan: vi.fn(), replanificar: vi.fn() },
  },
}))

vi.mock('../services/api', () => api)
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../hooks/useInvalidate', () => ({ useInvalidate: () => ({ invalidate: vi.fn() }) }))
vi.mock('../i18n/AppLangContext', () => ({
  useAppT: () => (k: string) => k,
  useAppLang: () => ({ t: (k: string) => k, lang: 'es' }),
}))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ puede: () => true }) }))
vi.mock('../components/SmartScheduleModal', () => ({ default: () => null }))

import GanttPage from '../pages/GanttPage'

const nodo = (id: string, es: string, ef: string, critica: boolean) => ({
  id, code: id, title: id, status: 'todo', assignee_id: null, duration_days: 3,
  start_date: null, due_date: null, early_start: es, early_finish: ef, late_start: es, late_finish: ef,
  total_float: critica ? 0 : 2, free_float: 0, is_critical: critica, is_near_critical: false,
  constraint_type: null, constraint_date: null, baseline_start: null, baseline_end: null, in_cycle: false,
})

describe('Gantt con plan calculado', () => {
  it('tareas sin fechas ⇒ barras planificadas (sin fijar)', async () => {
    api.projectsApi.list.mockResolvedValue({ data: [{ id: 'p1', code: 'PRJ-0001', name: 'Uno' }] })
    api.tasksApi.list.mockResolvedValue({ data: [
      { id: 't1', title: 'Diseño', status: 'todo', project_id: 'p1', start_date: null, due_date: null },
      { id: 't2', title: 'Obra', status: 'todo', project_id: 'p1', start_date: null, due_date: null },
    ] })
    api.taskDependenciesApi.getByProject.mockResolvedValue({ data: [] })
    api.planificacionApi.plan.mockResolvedValue({
      project_id: 'p1', nodes: [nodo('t1', '2026-09-17', '2026-09-22', true), nodo('t2', '2026-09-23', '2026-09-30', false)],
      critical_path: ['t1'], cycle: [], links: [],
    })

    const { container } = render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <GanttPage />
        </QueryClientProvider>
      </MemoryRouter>,
    )

    await waitFor(() => expect(container.querySelectorAll('rect[data-planificada="true"]').length).toBe(2))
    expect(api.planificacionApi.plan).toHaveBeenCalledWith('p1')
    expect(container.textContent).not.toContain('ganttchart.sin_fechas_definidas')
  })
})
