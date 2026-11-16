// Campana de avisos del portal de clientes (16-11-2026).
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const h = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn() } }))

vi.mock('../pages/portal-client/portalClientContext', () => ({
  CLIENT_API: h.api,
  useLang: () => (k: string, v?: { n?: number }) => (v && v.n !== undefined ? `${k}|${v.n}` : k),
}))

import CampanaDelPortal, { EVENTO_ABRIR_TICKET } from '../pages/portal-client/CampanaDelPortal'

const AVISOS = [
  { id: 'c1', kind: 'system', title: '[INC-0007] Tienes una respuesta', body: 'Hemos revisado tu caso', is_read: false,
    created_at: '2026-11-16T09:00:00+00:00', payload: { tipo: 'ticket_replied', seccion: 'support', ticket_id: 't7' } },
  { id: 'c2', kind: 'system', title: 'Entrega del sprint', body: 'Ya en preproducción', is_read: true,
    created_at: '2026-11-15T09:00:00+00:00', payload: { tipo: 'mensaje_del_equipo', seccion: 'messages' } },
]

function servidor(contador: number) {
  h.api.get.mockImplementation((url: string) => {
    if (url === '/portal/collaboration/notifications/unread-count') return Promise.resolve({ data: { unread_count: contador } })
    if (url === '/portal/collaboration/notifications') return Promise.resolve({ data: AVISOS })
    return Promise.resolve({ data: {} })
  })
}

function montar(onSection = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={qc}><CampanaDelPortal onSection={onSection} /></QueryClientProvider>)
  return onSection
}

const campana = () => screen.getByRole('button', { name: /portal_avisos\.(titulo|sin_leer)/ })

beforeEach(() => {
  h.api.get.mockReset()
  h.api.post.mockReset().mockResolvedValue({ data: {} })
})

describe('campana del portal', () => {
  it('muestra el número de avisos sin leer del cliente', async () => {
    servidor(1)
    montar()
    await waitFor(() => expect(campana()).toHaveAccessibleName('portal_avisos.sin_leer_uno|1'))
    expect(within(campana()).getByText('1')).toBeInTheDocument()
    // La lista no se pide hasta abrir el panel.
    expect(h.api.get).not.toHaveBeenCalledWith('/portal/collaboration/notifications', expect.anything())
  })

  it('sin avisos no hay número', async () => {
    servidor(0)
    montar()
    await waitFor(() => expect(h.api.get).toHaveBeenCalled())
    expect(campana()).toHaveAccessibleName('portal_avisos.titulo')
  })

  it('un aviso de ticket se marca leído, va a Soporte y abre el ticket', async () => {
    servidor(1)
    const onSection = montar()
    const abiertos: string[] = []
    const oir = (e: Event) => abiertos.push((e as CustomEvent<string>).detail)
    window.addEventListener(EVENTO_ABRIR_TICKET, oir)
    fireEvent.click(await screen.findByRole('button', { name: 'portal_avisos.sin_leer_uno|1' }))
    const panel = await screen.findByRole('dialog', { name: 'portal_avisos.titulo' })
    expect(await within(panel).findByText('portal_avisos.tipo_respuesta')).toBeInTheDocument()
    fireEvent.click(within(panel).getByRole('button', { name: /INC-0007/ }))
    await waitFor(() => expect(h.api.post).toHaveBeenCalledWith('/portal/collaboration/notifications/c1/read'))
    expect(onSection).toHaveBeenCalledWith('support')
    expect(abiertos).toEqual(['t7'])
    expect(new URL(window.location.href).searchParams.get('ticket')).toBe('t7')
    window.removeEventListener(EVENTO_ABRIR_TICKET, oir)
  })

  it('«Ver todas» lleva a la sección de notificaciones y «Marcar todas» las marca', async () => {
    servidor(1)
    const onSection = montar()
    fireEvent.click(await screen.findByRole('button', { name: 'portal_avisos.sin_leer_uno|1' }))
    fireEvent.click(await screen.findByRole('button', { name: /portal_avisos\.marcar_todas/ }))
    await waitFor(() => expect(h.api.post).toHaveBeenCalledWith('/portal/collaboration/notifications/mark-all-read'))
    fireEvent.click(screen.getByRole('button', { name: 'portal_avisos.ver_todas' }))
    expect(onSection).toHaveBeenCalledWith('notifications')
  })
})
