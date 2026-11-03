// Diseño 2026-11 (guía, apartado 15): las filas de pestañas hechas a mano en
// las páginas siguen el mismo patrón de teclado que `Tabs` (useTabListKeys).
// Se prueba en Administración del chat, una de las nueve filas convertidas.
import { vi, describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Cualquier llamada a la API devuelve una lista vacía: aquí sólo importan las pestañas.
vi.mock('../services/collaborationApi', () => ({
  collabApi: new Proxy({}, { get: () => () => Promise.resolve([]) }),
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../i18n/AppLangContext', () => ({ useAppT: () => (k: string) => k }))

import ChatAdminPage from '../pages/ChatAdminPage'

const pintar = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <ChatAdminPage />
  </QueryClientProvider>,
)

describe('ChatAdminPage: pestañas con teclado', () => {
  it('sólo la activa en el orden de Tab; flechas, Inicio y Fin seleccionan y mueven el foco', () => {
    pintar()
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(6)
    expect(tabs.map(t => t.tabIndex)).toEqual([0, -1, -1, -1, -1, -1])

    tabs[0].focus()
    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })
    let ahora = screen.getAllByRole('tab')
    expect(ahora[1].getAttribute('aria-selected')).toBe('true')
    expect(document.activeElement).toBe(ahora[1])

    fireEvent.keyDown(ahora[1], { key: 'End' })
    ahora = screen.getAllByRole('tab')
    expect(ahora[5].getAttribute('aria-selected')).toBe('true')

    fireEvent.keyDown(ahora[5], { key: 'ArrowRight' })   // da la vuelta
    ahora = screen.getAllByRole('tab')
    expect(ahora[0].getAttribute('aria-selected')).toBe('true')
    expect(document.activeElement).toBe(ahora[0])
  })
})
