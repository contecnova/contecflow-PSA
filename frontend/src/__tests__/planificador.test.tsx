// Proyectos — planificador, hub y vistas (rev. 173). Paneles del plan, líneas base,
// nivelación, vistas de trabajo y textos en los tres idiomas.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

const { planificacion, lineas, tareas, usuarios, estado } = vi.hoisted(() => ({
  planificacion: {
    plan: vi.fn(), replanificar: vi.fn(), nivelacion: vi.fn(), aplicarNivelacion: vi.fn(),
    vistas: vi.fn(), crearVista: vi.fn(), borrarVista: vi.fn(), carga: vi.fn(),
  },
  lineas: { listar: vi.fn(), crear: vi.fn(), hacerVigente: vi.fn(), comparar: vi.fn(), borrar: vi.fn() },
  tareas: { list: vi.fn(), update: vi.fn() },
  usuarios: { directory: vi.fn() },
  estado: { rol: 'admin' },
}))

vi.mock('../services/api', () => ({
  planificacionApi: planificacion, lineasBaseApi: lineas, tasksApi: tareas, usersApi: usuarios,
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
// 16-11-2026: borrar una línea base y nombrar una vista usan los diálogos del kit
// (useConfirm) en vez de window.confirm/prompt, como en el resto de la app.
vi.mock('../context/ConfirmContext', () => ({
  useConfirm: () => ({ confirmar: vi.fn().mockResolvedValue(true), pedirTexto: vi.fn().mockResolvedValue('Mi vista') }),
}))
vi.mock('../i18n/AppLangContext', () => ({ useAppT: () => (k: string, p?: Record<string, unknown>) => (p ? `${k} ${JSON.stringify(p)}` : k) }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: estado.rol }, hasRole: (...r: string[]) => r.includes(estado.rol) }),
}))

import PanelDelPlan from '../components/planificador/PanelDelPlan'
import PanelDeLineasBase from '../components/planificador/PanelDeLineasBase'
import PanelDeNivelacion from '../components/planificador/PanelDeNivelacion'
import VistasDeTrabajo from '../components/planificador/VistasDeTrabajo'
import es from '../i18n/langs/es.mjs'
import en from '../i18n/langs/en.mjs'
import zh from '../i18n/langs/zh.mjs'

const envolver = (n: ReactNode) => render(
  <MemoryRouter>
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{n}</QueryClientProvider>
  </MemoryRouter>,
)

const NODO = {
  id: 't1', code: 'TSK-1', title: 'Diseño', status: 'todo', assignee_id: null, duration_days: 3,
  start_date: '2026-11-02', due_date: '2026-11-04', early_start: '2026-11-02', early_finish: '2026-11-04',
  late_start: '2026-11-02', late_finish: '2026-11-04', total_float: 0, free_float: 0, is_critical: true,
  is_near_critical: false, constraint_type: null, constraint_date: null, baseline_start: null, baseline_end: null, in_cycle: false,
}

describe('Planificador', () => {
  beforeEach(() => {
    estado.rol = 'admin'
    Object.values(planificacion).forEach(f => f.mockReset())
    Object.values(lineas).forEach(f => f.mockReset())
    tareas.list.mockResolvedValue({ data: [] })
    usuarios.directory.mockResolvedValue({ data: [{ id: 'u1', full_name: 'Ana' }] })
  })

  it('pinta el camino crítico, el aviso de ciclo y replanifica', async () => {
    planificacion.plan.mockResolvedValue({
      project_id: 'p1', project_start: '2026-11-02', project_finish: '2026-11-04', deadline: '2026-11-03',
      finish_vs_deadline_days: 1, project_duration_days: 3, critical_path: ['TSK-1'], cycle: ['x'],
      nodes: [NODO], links: [], calendar: { workdays: [1, 2, 3, 4, 5], hours_per_day: 8, holidays: [] },
    })
    planificacion.replanificar.mockResolvedValue({ moved: [], total_moved: 0 })
    envolver(<PanelDelPlan projectId="p1" />)
    expect(await screen.findByText('planificador.camino_critico')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('planificador.ciclo_detectado')
    fireEvent.click(screen.getByText('planificador.replanificar'))
    await waitFor(() => expect(planificacion.replanificar).toHaveBeenCalledWith('p1'))
  })

  it('un empleado no ve «Replanificar»', async () => {
    estado.rol = 'employee'
    planificacion.plan.mockResolvedValue({
      project_id: 'p1', project_start: null, project_finish: '2026-11-04', deadline: null, finish_vs_deadline_days: null,
      project_duration_days: 3, critical_path: [], cycle: [], nodes: [NODO], links: [], calendar: null,
    })
    envolver(<PanelDelPlan projectId="p1" />)
    await screen.findByText('planificador.col_holgura_total')
    expect(screen.queryByText('planificador.replanificar')).toBeNull()
  })

  it('congela una línea base y la marca vigente', async () => {
    lineas.listar.mockResolvedValue([{ id: 'b1', name: 'Inicial', description: null, baseline_date: '2026-11-01',
      total_tasks: 2, completed_tasks: 0, total_hours: 10, budget_at_freeze: null, is_initial: true, is_current: false, created_at: null }])
    lineas.crear.mockResolvedValue({})
    lineas.hacerVigente.mockResolvedValue({})
    envolver(<PanelDeLineasBase projectId="p1" />)
    fireEvent.change(await screen.findByLabelText('planificador.nombre_linea_base'), { target: { value: 'Sprint 2' } })
    fireEvent.click(screen.getByText('planificador.congelar_plan'))
    await waitFor(() => expect(lineas.crear).toHaveBeenCalledWith('p1', { name: 'Sprint 2', make_current: undefined }))
    fireEvent.click(screen.getByText('planificador.usar_como_vigente'))
    await waitFor(() => expect(lineas.hacerVigente).toHaveBeenCalledWith('p1', 'b1'))
  })

  it('la nivelación aplica solo las tareas marcadas', async () => {
    planificacion.nivelacion.mockResolvedValue({
      project_id: 'p1', moves: [{ task_id: 't2', code: 'TSK-2', title: 'Corta', assignee_id: 'u1', old_start: '2026-11-02',
        old_due: '2026-11-02', new_start: '2026-11-09', new_due: '2026-11-09', delay_days: 5, max_delay_days: 7 }],
      overallocations_before: [{ user_id: 'u1', date: '2026-11-02', hours: 16, capacity: 8 }], overallocations_after: [],
      overallocated_hours_before: 8, overallocated_hours_after: 0, skipped_without_estimate: 0,
    })
    planificacion.aplicarNivelacion.mockResolvedValue({ total_applied: 1 })
    envolver(<PanelDeNivelacion projectId="p1" />)
    fireEvent.click(await screen.findByLabelText('Corta'))
    fireEvent.click(screen.getByText(/planificador.aplicar_marcadas/))
    await waitFor(() => expect(planificacion.aplicarNivelacion).toHaveBeenCalledWith('p1', ['t2']))
  })

  it('la tabla editable guarda el cambio de estado', async () => {
    planificacion.vistas.mockResolvedValue([])
    tareas.list.mockResolvedValue({ data: [{ id: 't1', code: 'TSK-1', title: 'Diseño', status: 'todo', priority: 'medium',
      assignee_id: null, estimated_hours: 8, progress_pct: null, start_date: '2026-11-02', due_date: '2026-11-04',
      is_critical: true, total_float_days: 0 }] })
    tareas.update.mockResolvedValue({ data: {} })
    envolver(<VistasDeTrabajo projectId="p1" />)
    // 16-11-2026: la celda muestra el estado y se edita en el sitio al pulsarla.
    fireEvent.click(await screen.findByRole('button', { name: /editar_celda.*columna_status/ }))
    const select = await screen.findByRole('combobox', { name: 'planificador.columna_status' })
    fireEvent.change(select, { target: { value: 'in_progress' } })
    await waitFor(() => expect(tareas.update).toHaveBeenCalledWith('t1', { status: 'in_progress' }))
  })
})

describe('Textos de la revisión 173', () => {
  it('los tres idiomas tienen las mismas claves de planificador y cartera', () => {
    for (const ns of ['planificador', 'cartera'] as const) {
      const base = Object.keys((es as Record<string, Record<string, string>>)[ns]).sort()
      expect(Object.keys((en as Record<string, Record<string, string>>)[ns]).sort()).toEqual(base)
      expect(Object.keys((zh as Record<string, Record<string, string>>)[ns]).sort()).toEqual(base)
    }
  })

  it('sin emojis ni textos que empiecen por «+ »', () => {
    const emoji = /\p{Extended_Pictographic}/u
    for (const lang of [es, en, zh] as Record<string, Record<string, string>>[]) {
      for (const v of [...Object.values(lang.planificador), ...Object.values(lang.cartera)]) {
        expect(emoji.test(v)).toBe(false)
        expect(v.startsWith('+ ')).toBe(false)
      }
    }
  })
})
