// Rev. 180 (bloque B): pedir una ausencia por horas. Con un tipo que admite
// días y horas aparece el selector de modo; al elegir Horas se pide la franja
// (inicio y fin), que va a la vista previa y a la petición como
// `modo: 'horas', start_time, end_time`; la vista previa pinta las horas, los
// días equivalentes y el saldo en horas con su equivalente en días.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

const { api } = vi.hoisted(() => ({
  api: {
    tipos: vi.fn(), turnos: vi.fn(), documentos: vi.fn(), vistaPrevia: vi.fn(), pedir: vi.fn(), editar: vi.fn(),
    subirDocumento: vi.fn(),
  },
}))

vi.mock('../services/api/ausencias', () => ({ ausenciasApi: api }))
vi.mock('../i18n/AppLangContext', () => ({
  useAppLang: () => ({ t: traducir, lang: 'es', translations: {} }),
  useAppT: () => traducir,
}))
// El selector de personas pide el directorio: aquí no hace falta.
vi.mock('../components/ui/EntitySelect', async importOriginal => ({
  ...(await importOriginal<typeof import('../components/ui/EntitySelect')>()),
  UserSelect: () => null,
}))

function traducir(clave: string, params?: Record<string, unknown>): string {
  return params ? `${clave} ${JSON.stringify(params)}` : clave
}

import FormularioDeAusencia from '../components/ausencias/FormularioDeAusencia'
import { COLOR_DATO_POR_DEFECTO } from '../constants/theme'

const TIPO_BASE = {
  clave: 'x', nombres: {}, color: COLOR_DATO_POR_DEFECTO, icono: 'umbrella', descuenta_saldo: true, saldo: 'bolsa', cupo_anual: null,
  unidad: 'horas', visibilidad: 'equipo', workflow_id: null, requiere_aprobacion: true, requiere_sustituto: false,
  datos_especiales: false, activo: true, orden: 1, de_sistema: false, requisitos: [], retribuido: true, periodo_saldo: 'anual',
  inicio_periodo_mes: 1, arrastre_max: null, arrastre_caduca_meses: null, caduca_meses: null, prorratear_alta: false,
  derecho_tabla_id: null, bolsa: null,
}
const MIXTO = { ...TIPO_BASE, id: 't1', nombre: 'Asuntos propios', modos: ['dias', 'horas'] }
const SOLO_DIAS = { ...TIPO_BASE, id: 't2', nombre: 'Vacaciones', modos: ['dias'], unidad: 'dias', saldo: 'vacaciones' }

const PREVIA = {
  decision: 'review', modo: 'horas', horas: 2, horas_max_dia: 2, horas_fuera_de_horario: 0, redondeo: null,
  negativo_permitido: 0, politicas_que_aplican: [{ politica: 'Permisos por horas', reglas: ['Máximo 4 h al día'] }],
  dias: [{ fecha: '2026-11-16', turno: null, office_id: null, horas: 2, minutos: [[540, 660]] }],
  dias_laborables: 0.25, cantidad: 2, unidad: 'horas', saldo_restante: 38, saldo_restante_horas: 38,
  saldo: {
    saldo: 'bolsa', clave: 't1', tipo_id: 't1', gobierna: null, unidad: 'horas', year: 2026,
    periodo: { clase: 'anual', desde: '2026-01-01', hasta: '2026-12-31', etiqueta: '2026' }, derecho: 0, derecho_origen: 'ninguno',
    arrastre: 0, arrastre_caduca: null, movimientos: 40, disponible: 40, usado: 0, pedido: 0, caducado: 0, restante: 40,
    restante_al_cierre: 40, media_diaria_horas: 8, equivalente: { unidad: 'dias', restante: 5 },
    proximas_caducidades: [{ fecha: '2027-03-31', cantidad: 10, origen: 'bolsa' }], retribuido: true,
  },
  cupos: [], aprobaciones: [], documentos: [], avisos: [], bloqueos: [], lista_de_espera: false, requisitos: [],
  cobertura_restante: null, companeros_ausentes: 0,
}

const envolver = (n: ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{n}</QueryClientProvider>,
)

describe('FormularioDeAusencia por horas', () => {
  beforeEach(() => {
    Object.values(api).forEach(f => f.mockReset())
    api.tipos.mockResolvedValue([MIXTO, SOLO_DIAS])
    api.turnos.mockResolvedValue([])
    api.documentos.mockResolvedValue([])
    api.vistaPrevia.mockResolvedValue(PREVIA)
    api.pedir.mockResolvedValue({ id: 'a1' })
  })

  it('con modos días y horas sale el selector; con uno solo, no', async () => {
    envolver(<FormularioDeAusencia abierto onCerrar={vi.fn()} />)
    const selector = await screen.findByRole('group', { name: 'aus.pedir_por' })
    expect(selector.textContent).toContain('aus.modo_dias')
    expect(selector.textContent).toContain('aus.modo_horas')
    // En días no se pide franja.
    expect(screen.queryByRole('textbox', { name: 'aus.hora_inicio' })).toBeNull()
    // Un tipo solo por días: sin selector.
    fireEvent.click(screen.getByRole('radio', { name: /Vacaciones/ }))
    await waitFor(() => expect(screen.queryByRole('group', { name: 'aus.pedir_por' })).toBeNull())
  })

  it('en Horas pide la franja, la manda a la vista previa y al pedir, y pinta horas y saldo en horas', async () => {
    envolver(<FormularioDeAusencia abierto onCerrar={vi.fn()} />)
    await screen.findByRole('group', { name: 'aus.pedir_por' })
    fireEvent.click(screen.getByRole('button', { name: 'aus.modo_horas' }))
    const inicio = await screen.findByRole('textbox', { name: 'aus.hora_inicio' })
    const fin = screen.getByRole('textbox', { name: 'aus.hora_fin' })
    fireEvent.change(screen.getByRole('textbox', { name: 'aus.desde' }), { target: { value: '16/11/2026' } })
    // Sin franja no hay vista previa: se pide elegir la hora.
    expect(screen.getByText('aus.previa_elige_franja')).toBeTruthy()
    fireEvent.change(inicio, { target: { value: '09:00' } })
    fireEvent.change(fin, { target: { value: '11:00' } })

    await waitFor(() => expect(api.vistaPrevia).toHaveBeenCalledWith(expect.objectContaining({
      absence_type_id: 't1', start_date: '2026-11-16', end_date: '2026-11-16', modo: 'horas', start_time: '09:00', end_time: '11:00',
      half_day_start: false, half_day_end: false, hours: null,
    })), { timeout: 2000 })

    // Horas que cubre y días equivalentes, horas por día, saldo en horas con su equivalente en días, caducidad y reglas.
    const equivalentes = await screen.findByText(/aus\.horas_y_equivalentes/)
    expect(equivalentes.textContent).toContain('"h":"2"')
    expect(screen.getByText('aus.horas_por_dia')).toBeTruthy()
    const saldo = screen.getByText(/aus\.saldo_antes_despues/)
    expect(saldo.textContent).toContain('aus.unidad_horas')
    expect(screen.getByText(/aus\.equivale_a/).textContent).toContain('aus.unidad_dias')
    expect(screen.getByText(/aus\.caduca_el/)).toBeTruthy()
    expect(screen.getByText('Permisos por horas')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'aus.pedir' }))
    await waitFor(() => expect(api.pedir).toHaveBeenCalledWith(expect.objectContaining({
      absence_type_id: 't1', modo: 'horas', start_time: '09:00', end_time: '11:00', hours: null,
    })))
  })
})
