// Licencias y hardware — fase 4: integración (16-11-2026). Autoservicio,
// confirmación de baja, traducción de errores y rutas de la API.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

const { api, http, users } = vi.hoisted(() => {
  const nombres = ['mio', 'opciones', 'pedir', 'devolver', 'dejar', 'averia', 'verActa', 'firmarActa', 'previaDeBaja']
  return {
    api: Object.fromEntries(nombres.map(n => [n, vi.fn()])) as Record<string, ReturnType<typeof vi.fn>>,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
    users: { deactivate: vi.fn() },
  }
})

vi.mock('../services/api/_core', () => ({ default: http }))
vi.mock('../services/api', () => ({ usersApi: users, licensesApi: { list: vi.fn() }, assetsApi: { list: vi.fn() } }))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../i18n/AppLangContext', () => ({
  useAppT: () => (k: string, p?: unknown) => (typeof p === 'string' ? (k.startsWith('almint.err_') ? k : p) : k),
}))

import { almIntegracionApi } from '../services/api/almIntegracion'
import { mensajeDeError } from '../components/alm/almComun'

const t = (k: string, p?: unknown) => (typeof p === 'string' && !k.startsWith('almint.err_') ? p : k)

function envolver(nodo: ReactNode) {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{nodo}</QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('rutas de la API de integración', () => {
  beforeEach(() => Object.values(http).forEach(f => f.mockReset().mockResolvedValue({ data: {} })))

  it('autoservicio, bajas, kits y proyecto van a /alm/integracion', async () => {
    await almIntegracionApi.mio()
    await almIntegracionApi.averia('a1', 'No arranca', 'high')
    await almIntegracionApi.confirmarPropuesta('p1', ['lic:l1'])
    await almIntegracionApi.recursosDelProyecto('pr1', { desde: '2026-11-01T00:00:00+01:00', granularidad: 'auto', tz: 'Europe/Madrid' })
    await almIntegracionApi.recursoDelTicket('t1')
    expect(http.get).toHaveBeenCalledWith('/alm/integracion/mio')
    expect(http.post).toHaveBeenCalledWith('/alm/integracion/mio/asignaciones/a1/averia', { descripcion: 'No arranca', urgencia: 'high' })
    expect(http.post).toHaveBeenCalledWith('/alm/integracion/propuestas/p1/confirmar', { claves: ['lic:l1'] })
    expect(http.get).toHaveBeenCalledWith('/alm/integracion/proyectos/pr1/recursos', { params: { desde: '2026-11-01T00:00:00+01:00', granularidad: 'auto', tz: 'Europe/Madrid' } })
    expect(http.get).toHaveBeenCalledWith('/alm/integracion/tickets/t1/recurso')
  })
})

describe('mensajeDeError', () => {
  const error = (detail: string) => ({ response: { data: { detail } } })
  it('traduce los códigos de la fase 4 y deja pasar el texto libre', () => {
    expect(mensajeDeError(t, error('almint_baja_bloqueada'))).toBe('almint.err_baja_bloqueada')
    expect(mensajeDeError(t, error('Algo concreto'))).toBe('Algo concreto')
    expect(mensajeDeError(t, {})).toBe('almint.err_generico')
  })
})

describe('Mis equipos y licencias', () => {
  beforeEach(() => {
    Object.values(api).forEach(f => f.mockReset())
    vi.spyOn(almIntegracionApi, 'mio').mockResolvedValue({
      licencias: [{ assignment_id: 'as1', license_id: 'l1', name: 'Office E3', status: 'active', mode: 'assignment', from_pool: false }],
      equipos: [{ assignment_id: 'as2', asset_id: 'e1', name: 'Portátil Ana', type: 'laptop', mode: 'loan', valid_to: '2026-11-20',
        overdue: false, averias_abiertas: [], devolucion: null, acta_entrega: null }],
      actas_pendientes: [], peticiones: [], devoluciones: [], historial: [],
    })
    vi.spyOn(almIntegracionApi, 'opciones').mockResolvedValue({ puede_pedir_licencia: true, puede_pedir_equipo: true, licencias: [], tipos_de_equipo: ['laptop'] })
    vi.spyOn(almIntegracionApi, 'averia').mockResolvedValue({ id: 't9', number: 'INC-9', title: '', status: 'new', ticket_type: 'incident' })
  })

  it('pinta lo propio y comunica una avería enlazada al equipo', async () => {
    const { default: MisEquiposPage } = await import('../pages/MisEquiposPage')
    envolver(<MisEquiposPage />)
    expect(await screen.findByText('Portátil Ana')).toBeTruthy()
    expect(screen.getByText('almint.pedir_licencia')).toBeTruthy()
    fireEvent.click(screen.getAllByText('almint.comunicar_averia')[0])
    fireEvent.change(await screen.findByRole('textbox'), { target: { value: 'No arranca' } })
    fireEvent.click(screen.getByText('almint.abrir_ticket'))
    await waitFor(() => expect(almIntegracionApi.averia).toHaveBeenCalledWith('as2', 'No arranca', 'medium'))
  })
})

describe('Confirmar la baja de una persona', () => {
  beforeEach(() => users.deactivate.mockReset().mockResolvedValue({ data: {} }))

  const previa = (politica: 'avisar' | 'confirmar' | 'bloquear') => ({
    user_id: 'u1', user_name: 'Ana', politica, dias_para_liberar: 0,
    licencias: [{ assignment_id: 'a', license_id: 'l', name: 'Office E3', status: 'active' }],
    equipos: [{ assignment_id: 'b', asset_id: 'e', name: 'Portátil', asset_tag: 'T-1', mode: 'assignment', valid_to: null, devolucion_abierta: false }],
    baja_abierta: null,
  })

  it('con «bloquear» no deja desactivar', async () => {
    vi.spyOn(almIntegracionApi, 'previaDeBaja').mockResolvedValue(previa('bloquear'))
    const { default: ConfirmarBajaModal } = await import('../components/alm/ConfirmarBajaModal')
    envolver(<ConfirmarBajaModal userId="u1" nombre="Ana" onClose={() => {}} />)
    expect(await screen.findByText('almint.politica_bloquear')).toBeTruthy()
    const boton = screen.getByText('almint.desactivar').closest('button') as HTMLButtonElement
    expect(boton.disabled).toBe(true)
  })

  it('con «confirmar» pide la casilla y envía la confirmación', async () => {
    vi.spyOn(almIntegracionApi, 'previaDeBaja').mockResolvedValue(previa('confirmar'))
    const { default: ConfirmarBajaModal } = await import('../components/alm/ConfirmarBajaModal')
    envolver(<ConfirmarBajaModal userId="u1" nombre="Ana" onClose={() => {}} />)
    const boton = (await screen.findByText('almint.desactivar')).closest('button') as HTMLButtonElement
    expect(boton.disabled).toBe(true)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(boton)
    await waitFor(() => expect(users.deactivate).toHaveBeenCalledWith('u1', true))
  })
})
