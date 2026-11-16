// Licencias y hardware — fase 2: uso real (16-11-2026). Pestaña «Uso real» del módulo de licencias.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { api, estado } = vi.hoisted(() => {
  const nombres = ['panel', 'licencias', 'licencia', 'equipos', 'conexiones', 'guardarConexion', 'probar', 'sincronizar',
    'sincronizaciones', 'productos', 'mapear', 'recuperaciones', 'simulacion', 'misRecuperaciones', 'conservar', 'decidir',
    'liberar', 'cancelar', 'propuestas', 'decidirAjuste', 'reglas', 'guardarRegla', 'borrarRegla', 'cumplimiento',
    'exportarCumplimiento', 'noControlado', 'detectar', 'alta', 'descartar', 'reabrir']
  return { api: Object.fromEntries(nombres.map(n => [n, vi.fn()])) as Record<string, ReturnType<typeof vi.fn>>,
    estado: { rol: 'admin' } }
})

vi.mock('../services/api/almUso', async () => {
  const real = await vi.importActual<typeof import('../services/api/almUso')>('../services/api/almUso')
  return { ...real, almUsoApi: api }
})
vi.mock('../services/api', () => ({ licensesApi: { list: vi.fn().mockResolvedValue({ data: [] }) } }))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../context/ConfirmContext', () => ({ confirmar: vi.fn().mockResolvedValue(true), pedirTexto: vi.fn().mockResolvedValue('motivo') }))
vi.mock('../i18n/AppLangContext', () => ({ useAppT: () => (k: string) => k }))
vi.mock('../hooks/useOrgSettings', () => ({ useOrgSettings: () => ({ currency: 'EUR' }) }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: estado.rol }, hasRole: (...r: string[]) => r.includes(estado.rol) }),
}))

import UsoRealTab from '../pages/alm/uso/UsoRealTab'
import { codigoDeError } from '../services/api/almUso'

const pintar = () => render(
  <MemoryRouter>
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <UsoRealTab />
    </QueryClientProvider>
  </MemoryRouter>,
)

const PANEL = {
  asignados: 12, en_uso: 7, infrautilizadas: 2, sin_uso: 2, sin_datos: 1, licencias: 3, licencias_sin_datos: 0,
  coste_anual_sin_uso: 720, moneda: 'EUR', fuentes_activas: 0, fuentes_con_error: 0, ultima_lectura: null,
  recuperaciones: { abiertas: 0, pendientes_de_aprobacion: 0, liberadas: 0, ahorro_anual_liberado: 0 }, ahorro_por_ajuste: 0,
}

const CONEXION = {
  clave: 'okta', etiqueta: 'Okta', credencial: 'alm_okta', obligatorias: ['base_url', 'api_token'], fiabilidad: 'media',
  tipo: 'externo', permisos: ['okta.users.read'], aporta: ['evidencias'], opciones: [], conexion_id: null, activa: false,
  fiabilidad_efectiva: 'media', fiabilidad_propia: null, configuracion: {},
  credenciales: [{ clave: 'base_url', etiqueta: 'URL', secreto: false, configurado: false, valor: null },
    { clave: 'api_token', etiqueta: 'Token', secreto: true, configurado: true, valor: null }],
  faltan: ['base_url'], lista: false, ultima_sincronizacion_at: null, ultimo_estado: 'nunca', ultimo_error: null, ultima: null,
}

describe('Uso real de licencias', () => {
  beforeEach(() => {
    estado.rol = 'admin'
    Object.values(api).forEach(f => f.mockReset())
    api.panel.mockResolvedValue(PANEL)
    api.licencias.mockResolvedValue([{ license_id: 'l1', nombre: 'Microsoft 365 E3', metric: 'named_user', estado: 'infrautilizada',
      asignados: 12, total: 15, en_uso: 7, infrautilizadas: 2, sin_uso: 2, sin_datos: 1, uso_sin_asignacion: 1,
      pico_concurrente: null, pico_medido_en: null, ultimo_uso: null, fuente: 'm365', fuentes: ['m365'], medido_en: null }])
    api.conexiones.mockResolvedValue([CONEXION])
    api.productos.mockResolvedValue([])
    api.misRecuperaciones.mockResolvedValue({ items: [], kpis: {} })
  })

  it('un gestor ve los KPIs, el estado vacío útil sin fuentes y la tabla por licencia', async () => {
    pintar()
    expect(await screen.findByText('alm_uso.sin_fuentes_titulo')).toBeTruthy()
    expect(screen.getByText('alm_uso.kpi_coste_sin_uso')).toBeTruthy()
    expect(await screen.findByText('Microsoft 365 E3')).toBeTruthy()
    expect(screen.getByText('12 / 15')).toBeTruthy()
  })

  it('las fuentes solo las ve un administrador', async () => {
    estado.rol = 'pm'
    pintar()
    await screen.findByText('alm_uso.tab_uso')
    expect(screen.queryByText('alm_uso.tab_fuentes')).toBeNull()
  })

  it('quien no gestiona ve solo sus licencias en recuperación', async () => {
    estado.rol = 'employee'
    pintar()
    expect(await screen.findByText('alm_uso.mias_vacio')).toBeTruthy()
    expect(api.panel).not.toHaveBeenCalled()
  })

  it('una fuente sin credenciales completas no se puede activar y el secreto nunca se enseña', async () => {
    pintar()
    fireEvent.click(await screen.findByText('alm_uso.tab_fuentes'))
    const activar = await screen.findByText('alm_uso.activar')
    expect((activar.closest('button') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByText('alm_uso.configurar'))
    const token = await screen.findByPlaceholderText('alm_uso.configurado_sin_cambios')
    expect((token as HTMLInputElement).value).toBe('')
    expect((token as HTMLInputElement).type).toBe('password')
    fireEvent.change(token, { target: { value: 'nuevo' } })
    api.guardarConexion.mockResolvedValue(CONEXION)
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(api.guardarConexion).toHaveBeenCalled())
    expect(api.guardarConexion.mock.calls[0][1].credenciales).toEqual({ api_token: 'nuevo' })
  })
})

describe('codigoDeError', () => {
  it('saca el código estable del detalle del backend', () => {
    expect(codigoDeError({ response: { data: { detail: { code: 'ALM_USAGE_SYNC_RUNNING', message: 'x' } } } }))
      .toEqual({ codigo: 'ALM_USAGE_SYNC_RUNNING', mensaje: 'x' })
    expect(codigoDeError({ response: { data: { detail: 'texto' } } })).toEqual({ codigo: null, mensaje: 'texto' })
  })
})
