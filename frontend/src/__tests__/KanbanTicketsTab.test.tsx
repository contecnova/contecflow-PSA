// Auditoría 2026-11: el Kanban metía cerrados y cancelados en «Abierto» y,
// al soltar en «Abierto», mandaba `status: "open"`, que no es un estado.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const list = vi.fn()
const update = vi.fn()
vi.mock('../services/api', () => ({
  ticketsApi: { list: (...a: unknown[]) => list(...a), update: (...a: unknown[]) => update(...a) },
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../i18n/AppLangContext', () => ({ useAppT: () => (k: string) => k }))

import KanbanTicketsTab from '../pages/service-desk/KanbanTicketsTab'

const pintar = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <KanbanTicketsTab onSelect={() => {}} />
  </QueryClientProvider>,
)

describe('KanbanTicketsTab', () => {
  beforeEach(() => {
    list.mockReset().mockResolvedValue({ data: [
      { id: 1, number: 'INC-1', title: 'Nuevo', status: 'new' },
      { id: 2, number: 'INC-2', title: 'En curso', status: 'in_progress', assigned_to_id: 'u1' },
    ], meta: { total: 2 } })
    update.mockReset().mockResolvedValue({ data: {} })
  })

  it('pide solo los estados de las columnas y pone los nuevos en Abierto', async () => {
    pintar()
    expect(await screen.findByText('Nuevo')).toBeTruthy()
    const params = list.mock.calls[0][0] as { status: string }
    expect(params.status.split(',')).not.toContain('closed')
    expect(params.status.split(',')).not.toContain('cancelled')
  })

  it('soltar en Abierto manda un estado real', async () => {
    pintar()
    const tarjeta = await screen.findByLabelText('INC-2 En curso')
    fireEvent.dragStart(tarjeta, { dataTransfer: { setData: vi.fn(), effectAllowed: '' } })
    const abierto = screen.getByText('service_desk.status_open').closest('[data-col]') as HTMLElement
    fireEvent.drop(abierto, { dataTransfer: {} })
    await waitFor(() => expect(update).toHaveBeenCalledWith(2, { status: 'assigned' }))
  })
})
