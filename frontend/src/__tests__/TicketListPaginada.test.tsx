// Auditoría 2026-11: «Mi cola» se quedaba en 25 tickets y «Todos» en 100, con
// la búsqueda limitada a esos 100. Ahora se pagina en el servidor.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const tickets = vi.fn()
const queue = vi.fn()
vi.mock('../services/api', () => ({
  sdRoutingApi: { tickets: (...a: unknown[]) => tickets(...a), queue: (...a: unknown[]) => queue(...a) },
  sdGroupsApi: {}, sdSlaPoliciesApi: {}, usersApi: {},
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../i18n/AppLangContext', () => ({ useAppT: () => (k: string) => k, useAppLang: () => ({ lang: 'en', t: (k: string) => k }) }))

import { TicketList } from '../pages/service-desk/QueueAndRoutingSections'

const pagina = (n: number) => Array.from({ length: 50 }, (_, i) => ({
  id: `${n}-${i}`, number: `INC-${n}-${i}`, title: `Ticket ${n}-${i}`, status: 'new', priority: 'p3_medium',
}))

const pintar = (queueOnly = false) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <TicketList queueOnly={queueOnly} onSelect={() => {}} />
  </QueryClientProvider>,
)

describe('TicketList', () => {
  beforeEach(() => {
    tickets.mockReset().mockImplementation((p: { page: number }) =>
      Promise.resolve({ data: pagina(p.page), meta: { total: 130 } }))
    queue.mockReset().mockImplementation((p: { page: number }) =>
      Promise.resolve({ data: pagina(p.page), meta: { total: 60 } }))
  })

  it('«Todos» enseña el total y pide la página siguiente', async () => {
    pintar()
    expect(await screen.findByText('130 tickets')).toBeTruthy()
    fireEvent.click(screen.getByText('2'))
    await waitFor(() => expect(tickets).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, page_size: 50 })))
  })

  it('«Todos» manda la búsqueda al servidor', async () => {
    pintar()
    await screen.findByText('130 tickets')
    fireEvent.change(screen.getByLabelText('service_desk.search_tickets'), { target: { value: 'impresora' } })
    await waitFor(() => expect(tickets).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'impresora', page: 1 })))
  })

  it('«Mi cola» pasa de 25 y pagina', async () => {
    pintar(true)
    expect(await screen.findByText('60 tickets')).toBeTruthy()
    expect(queue).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 50 }))
  })
})
