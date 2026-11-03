// Auditoría 2026-11: la pantalla ofrecía 64 disparadores y 23 acciones escritos
// a mano (el motor conocía 14 y 11), «Probar» ejecutaba las acciones de verdad
// y el historial no se podía abrir. Ahora pinta el catálogo del motor.
import { vi, describe, it, expect } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const regla = {
  id: 'r1', name: 'Avisar vencidas', trigger_type: 'task_overdue', is_active: true, is_global: true,
  actions: [{ type: 'notify_user', params: { message: 'Vencida' } }], run_count: 1,
}
vi.mock('../services/api', () => ({
  projectsApi: { list: () => Promise.resolve({ data: [] }) },
  automationsApi: {
    list: () => Promise.resolve({ data: [regla] }),
    templates: () => Promise.resolve({ data: [] }),
    catalog: () => Promise.resolve({ data: {
      triggers: [{ type: 'task_created', category: 'tasks', fields: ['status'] },
                 { type: 'task_overdue', category: 'tasks', fields: ['days_overdue'], scan: true }],
      actions: [{ type: 'notify_user', category: 'notifications', params: [{ key: 'message', type: 'text', required: true }] }],
      operators: ['equals'],
    } }),
    test: () => Promise.resolve({ data: {
      simulated: true, enabled: true, scan: true,
      results: [{ action: 'notify_user', ok: true, would: 'avisaría a la persona del evento' }],
    } }),
    executions: () => Promise.resolve({ data: [
      { id: 'e1', executed_at: '2026-11-03 10:00', success: false,
        actions_taken: [{ action: 'send_email', ok: false, error: 'SMTP' }] },
    ] }),
    update: vi.fn(), delete: vi.fn(), create: vi.fn(),
  },
}))
vi.mock('../i18n/AppLangContext', () => ({ useAppT: () => (k: string, d?: unknown) => (typeof d === 'string' ? `${k}` : k) }))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ error: vi.fn(), success: vi.fn() }) }))

import AutomationsPage from '../pages/AutomationsPage'

function pinta() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AutomationsPage />
    </QueryClientProvider>,
  )
}

describe('AutomationsPage', () => {
  it('el editor ofrece solo los disparadores del catálogo del motor', async () => {
    pinta()
    fireEvent.click(await screen.findByText('automations.new_rule_btn'))
    const select = await screen.findByLabelText('automations.trigger_lbl') as HTMLSelectElement
    await screen.findByText(/automations.trig_task_overdue/)
    const valores = Array.from(select.options).map(o => o.value)
    expect(valores).toEqual(['task_created', 'task_overdue'])
  })

  it('«Probar» enseña la simulación, no un «ejecutado»', async () => {
    pinta()
    fireEvent.click(await screen.findByLabelText('automations.try_btn Avisar vencidas'))
    expect(await screen.findByText('automations.simulation_note')).toBeTruthy()
    expect(screen.getByText(/avisaría a la persona del evento/)).toBeTruthy()
    expect(screen.queryByText(/automations.executed/)).toBeNull()
  })

  it('el historial se abre y dice qué falló', async () => {
    pinta()
    fireEvent.click(await screen.findByLabelText('automations.history_btn Avisar vencidas'))
    const tabla = await screen.findByRole('table')
    expect(within(tabla).getByText(/SMTP/)).toBeTruthy()
  })
})
