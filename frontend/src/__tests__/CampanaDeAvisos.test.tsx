// Campana de avisos de la barra superior (16-11-2026).
//
// Caso del usuario: en /inbox se veía «1 sin leer» y la campana salía sin
// número. La causa real: la campana pedía `/enterprise/notifications/unread-count`
// y el backend en marcha (sin reiniciar) respondía 404; el contador caía a 0 y,
// como la pestaña Notificaciones comparte la clave, también perdía su «1».
// Ahora, ante un 404, se usa el `unread_count` de la lista (el cálculo de la
// bandeja) y campana, pestaña y bandeja cuentan lo mismo (avisos + alertas).
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

const h = vi.hoisted(() => ({
  http: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
  alerts: { list: vi.fn(), read: vi.fn() },
  mentions: { mentions: vi.fn() },
  ws: { oyente: null as null | ((m: unknown) => void), enVivo: false },
  veAlertas: false,
}))

vi.mock('../services/api/_core', () => ({ default: h.http, alertsApi: h.alerts }))
vi.mock('../services/api', () => ({ default: h.http, alertsApi: h.alerts, mentionsApi: h.mentions }))
vi.mock('../hooks/useAvisosEnVivo', () => ({
  default: (_activo: boolean, cb?: (m: unknown) => void) => { h.ws.oyente = cb ?? null; return h.ws.enVivo },
}))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1' }, loading: false, hasRole: () => h.veAlertas }),
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }) }))
vi.mock('../i18n/AppLangContext', () => {
  const t = (k: string, v?: { n?: number }) => (v && v.n !== undefined ? `${k}|${v.n}` : k)
  return { useAppLang: () => ({ t }), useAppT: () => t }
})

import CampanaDeAvisos from '../components/layout/CampanaDeAvisos'
import NotificationsPage from '../pages/NotificationsPage'
import useNotificationBadges from '../hooks/useNotificationBadges'
import { textoDelContador } from '../components/avisos/BandejaDesplegable'

const no404 = () => Promise.reject({ response: { status: 404 } })

/** Respuestas del servidor: avisos (lista), contador (o 404) y alertas. */
function servidor({ avisos = [] as Array<Record<string, unknown>>, contador = undefined as number | 'sin-endpoint' | undefined, alertas = [] as Array<Record<string, unknown>> } = {}) {
  const sinLeer = avisos.filter(a => !a.is_read).length
  h.http.get.mockImplementation((url: string) => {
    if (url === '/enterprise/notifications/unread-count') {
      return contador === 'sin-endpoint' ? no404() : Promise.resolve({ data: { unread_count: contador ?? sinLeer } })
    }
    if (url === '/enterprise/notifications') return Promise.resolve({ data: { notifications: avisos, unread_count: sinLeer } })
    if (url === '/approvals/requests/pending-my-action') return Promise.resolve({ data: [] })
    return Promise.resolve({ data: {} })
  })
  h.alerts.list.mockResolvedValue({ data: alertas })
}

function Donde() {
  const l = useLocation()
  return <div data-testid="ruta">{l.pathname + l.search}</div>
}

function envolver(nodo: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={['/inicio']}>
      <QueryClientProvider client={qc}>{nodo}<Donde /></QueryClientProvider>
    </MemoryRouter>,
  )
}

const campana = () => screen.getByRole('button', { name: /campana\.(titulo|sin_leer)/ })

const AVISO = { id: 'n1', type: 'ticket_replied', title: 'Respuesta en INC-0001', body: 'El agente ha contestado',
  is_read: false, created_at: '2026-11-16 09:00', created_at_iso: '2026-11-16T09:00:00+00:00', action_url: '/service-desk?ticket=t1' }

beforeEach(() => {
  Object.values(h.http).forEach(f => f.mockReset().mockResolvedValue({ data: {} }))
  Object.values(h.alerts).forEach(f => f.mockReset().mockResolvedValue({ data: [] }))
  h.mentions.mentions.mockReset().mockResolvedValue({ data: [] })
  h.ws.oyente = null
  h.ws.enVivo = false
  h.veAlertas = false
})

describe('el caso del usuario: 1 sin leer en la bandeja ⇒ la campana muestra 1', () => {
  it('con el backend sin el endpoint nuevo (404), campana y bandeja dicen 1', async () => {
    servidor({ avisos: [AVISO], contador: 'sin-endpoint' })
    envolver(<><CampanaDeAvisos /><NotificationsPage embedded /></>)
    await waitFor(() => expect(campana()).toHaveAccessibleName('campana.sin_leer_uno|1'))
    expect(within(campana()).getByText('1')).toBeInTheDocument()
    // La bandeja: su cifra «Sin leer» es la misma.
    const kpi = screen.getAllByText('pagina_notif.sin_leer').find(e => e.classList.contains('ds-eyebrow'))!
    expect(within(kpi.closest('.ui-kpi') as HTMLElement).getByText('1')).toBeInTheDocument()
  })

  it('la pestaña Notificaciones de /inbox recupera su contador con el 404', async () => {
    servidor({ avisos: [AVISO], contador: 'sin-endpoint' })
    function Pestaña() { return <span data-testid="pestana">{useNotificationBadges().notifUnreadCount}</span> }
    envolver(<Pestaña />)
    await waitFor(() => expect(screen.getByTestId('pestana')).toHaveTextContent('1'))
  })

  it('con el endpoint nuevo usa el COUNT y no la lista', async () => {
    servidor({ avisos: [AVISO], contador: 1 })
    envolver(<CampanaDeAvisos />)
    await waitFor(() => expect(campana()).toHaveAccessibleName('campana.sin_leer_uno|1'))
    expect(h.http.get).not.toHaveBeenCalledWith('/enterprise/notifications', expect.anything())
  })

  it('las alertas sin leer cuentan igual que en la bandeja (admin/pm/hr)', async () => {
    h.veAlertas = true
    servidor({ contador: 0, alertas: [{ id: 'a1', alert_type: 'sla_breach', title: 'SLA', is_read: false, created_at: '2026-11-16T08:00:00Z' },
      { id: 'a2', alert_type: 'sla_risk', title: 'Leída', is_read: true, created_at: '2026-11-16T07:00:00Z' }] })
    envolver(<CampanaDeAvisos />)
    await waitFor(() => expect(campana()).toHaveAccessibleName('campana.sin_leer_uno|1'))
  })
})

describe('contador', () => {
  it('sin avisos no hay número y el nombre es «Notificaciones»', async () => {
    servidor({ contador: 0 })
    envolver(<CampanaDeAvisos />)
    await waitFor(() => expect(h.http.get).toHaveBeenCalledWith('/enterprise/notifications/unread-count'))
    expect(campana()).toHaveAccessibleName('campana.titulo')
    expect(campana().querySelector('.bandeja-desplegable__contador')).toBeNull()
  })

  it('más de 99 se escribe «99+» y el nombre lleva el número', async () => {
    servidor({ contador: 150 })
    envolver(<CampanaDeAvisos />)
    await waitFor(() => expect(within(campana()).getByText('99+')).toBeInTheDocument())
    expect(campana()).toHaveAccessibleName('campana.sin_leer_otros|150')
    expect(textoDelContador(99)).toBe('99')
  })

  it('un mensaje de avisos por el WebSocket vuelve a pedir el contador', async () => {
    servidor({ contador: 0 })
    envolver(<CampanaDeAvisos />)
    await waitFor(() => expect(h.http.get).toHaveBeenCalledTimes(1))
    servidor({ contador: 2 })
    act(() => h.ws.oyente?.({ type: 'notifications', count: 2 }))
    await waitFor(() => expect(campana()).toHaveAccessibleName('campana.sin_leer_otros|2'))
  })
})

describe('panel', () => {
  it('abre con la lista, sin emojis en el título; Escape cierra y devuelve el foco', async () => {
    servidor({ avisos: [{ ...AVISO, title: '🎉 Contecflow v11 Enterprise activo' }] })
    envolver(<CampanaDeAvisos />)
    await waitFor(() => expect(campana()).toHaveAccessibleName('campana.sin_leer_uno|1'))
    fireEvent.click(campana())
    const panel = await screen.findByRole('dialog', { name: 'campana.titulo' })
    expect(campana()).toHaveAttribute('aria-expanded', 'true')
    expect(await within(panel).findByText('Contecflow v11 Enterprise activo')).toBeInTheDocument()
    expect(within(panel).getByTestId('aviso-no-leido')).toBeInTheDocument()
    expect(document.activeElement).toBe(panel)
    fireEvent.keyDown(panel, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.activeElement).toBe(campana())
  })

  it('pulsar un aviso lo marca leído y lleva a su enlace', async () => {
    servidor({ avisos: [AVISO] })
    envolver(<CampanaDeAvisos />)
    fireEvent.click(await screen.findByRole('button', { name: 'campana.sin_leer_uno|1' }))
    fireEvent.click(await screen.findByRole('button', { name: /Respuesta en INC-0001/ }))
    await waitFor(() => expect(h.http.post).toHaveBeenCalledWith('/enterprise/notifications/n1/read'))
    await waitFor(() => expect(screen.getByTestId('ruta')).toHaveTextContent('/service-desk?ticket=t1'))
  })

  it('«Marcar todas» marca avisos y alertas; «Ver todas» va a la bandeja', async () => {
    h.veAlertas = true
    servidor({ avisos: [AVISO], alertas: [{ id: 'a1', alert_type: 'sla_breach', title: 'SLA', is_read: false, created_at: '2026-11-16T08:00:00Z' }] })
    envolver(<CampanaDeAvisos />)
    fireEvent.click(await screen.findByRole('button', { name: 'campana.sin_leer_otros|2' }))
    fireEvent.click(await screen.findByRole('button', { name: /campana\.marcar_todas/ }))
    await waitFor(() => expect(h.http.post).toHaveBeenCalledWith('/enterprise/notifications/read-all'))
    expect(h.alerts.read).toHaveBeenCalledWith('a1')
    fireEvent.click(screen.getByRole('button', { name: 'campana.ver_todas' }))
    expect(screen.getByTestId('ruta')).toHaveTextContent('/inbox?tab=notifications')
  })
})
