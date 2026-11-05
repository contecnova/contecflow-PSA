// Revisión 2026-11: con la vista «Kanban» elegida y sin proyecto filtrado, la
// pantalla caía en una lista («Select project · N Task»). El Kanban tiene que
// salir siempre que esté elegido.
import { vi, describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

const { TAREAS, vacio } = vi.hoisted(() => ({ vacio: vi.fn().mockResolvedValue({ data: [] }), TAREAS: [
  { id: 't1', code: 'TSK-1', title: 'Analisis coste', status: 'todo', priority: 'low', project_id: 'p1' },
  { id: 't2', code: 'TSK-2', title: 'API contabilidad', status: 'in_progress', priority: 'high', project_id: 'p2' },
  { id: 't3', code: 'TSK-3', title: 'Pendiente de priorizar', status: 'backlog', priority: 'medium', project_id: 'p1' },
  { id: 't4', code: 'TSK-4', title: 'Cancelada', status: 'cancelled', priority: 'low', project_id: 'p1' },
] }))

vi.mock('../services/api', () => ({
  tasksApi: { list: vi.fn().mockResolvedValue({ data: TAREAS }), kanban: vi.fn(), update: vi.fn(), bulkUpdate: vi.fn() },
  projectsApi: { list: vacio }, customFieldsApi: { list: vacio }, semanticApi: {}, projectWorkflowsApi: {},
  issueTypesApi: { list: vacio }, usersApi: { list: vacio },
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../context/ConfirmContext', () => ({ openConfirmGlobal: vi.fn() }))
vi.mock('../i18n/AppLangContext', () => ({ useAppT: () => (k: string) => k, useAppLang: () => ({ t: (k: string) => k, lang: 'es' }) }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 'u1', role: 'admin' }, hasRole: () => true }) }))
vi.mock('../components/layout/PageHeader', () => ({ default: ({ actions }: { actions: JSX.Element }) => <div>{actions}</div> }))
vi.mock('../components/layout/PageShell', () => ({ default: ({ children }: { children: JSX.Element }) => <div>{children}</div> }))
vi.mock('../components/SmartScheduleModal', () => ({ default: () => null }))

import TasksPage from '../pages/TasksPage'

const pintar = (ruta: string) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[ruta]}><TasksPage /></MemoryRouter>
  </QueryClientProvider>,
)

describe('TasksPage — Kanban sin proyecto', () => {
  it('pinta columnas por estado, no la lista', async () => {
    pintar('/tasks')
    const tarjeta = await screen.findByText('API contabilidad')
    expect(screen.queryByText(/tasks\.select_project/)).toBeNull()
    expect(tarjeta.closest('[aria-label]')?.getAttribute('aria-label')).toContain('API contabilidad')
    // Cada tarea en la columna de su estado; backlog con columna propia; las canceladas fuera.
    expect(screen.getByText('Pendiente de priorizar')).toBeTruthy()
    expect(screen.queryByText('Cancelada')).toBeNull()
    expect(within(document.body).queryAllByRole('row')).toHaveLength(0)
  })

  it('la vista «Lista» sigue siendo una lista', async () => {
    pintar('/tasks?view=list')
    expect(await screen.findByText('API contabilidad')).toBeTruthy()
    expect(screen.queryByText('Pendiente de priorizar')).toBeTruthy()
    expect(screen.getByText('Cancelada')).toBeTruthy()
  })
})
