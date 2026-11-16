// Periodo libre en informes (16-11-2026): utils/periodo, usePeriodo (URL como
// fuente de verdad) y SelectorDePeriodo (accesos, personalizado, granularidad
// no admitida desactivada, comparar).
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, renderHook, act } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

vi.mock('../i18n/AppLangContext', () => ({
  useAppLang: () => ({ t: (k: string) => k, lang: 'es' }),
  useAppT: () => (k: string) => k,
}))
vi.mock('../services/api/periodo', () => ({
  periodoApi: { limites: () => Promise.resolve({ max_dias: 1830, max_puntos: { hour: 744, day: 1100, week: 530, month: 240 }, auto_max_puntos: 120, granularidades: [] }) },
}))

import { usePeriodo } from '../hooks/usePeriodo'
import SelectorDePeriodo from '../components/ui/SelectorDePeriodo'
import {
  aUrl, deUrl, fechasDe, paramsDeApi, rangoDe, resolverGranularidad, validarPeriodo, formatearTramo,
  LIMITES_POR_DEFECTO, SIN_HORA, SOLO_MES, type ValorPeriodo,
} from '../utils/periodo'

const AHORA = new Date(2026, 10, 16, 10, 30) // 16-11-2026 10:30 local
const V = (o: Partial<ValorPeriodo>): ValorPeriodo => ({ preset: '30d', granularidad: 'auto', comparar: false, ...o })

describe('utils/periodo', () => {
  it('los accesos móviles van como days (clave estable) y los de calendario solo con desde', () => {
    expect(paramsDeApi(V({ preset: '7d' }), AHORA)).toMatchObject({ days: 7, granularidad: 'auto' })
    expect(paramsDeApi(V({ preset: '24h' }), AHORA).days).toBe(1)
    const mes = paramsDeApi(V({ preset: 'mes' }), AHORA)
    expect(mes.desde?.startsWith('2026-11-01T00:00:00')).toBe(true)
    expect(mes.hasta).toBeUndefined()
    expect(paramsDeApi(V({ preset: 'prox90d' }), AHORA).days).toBe(90)
  })

  it('rango de trimestre, año y horizonte futuro', () => {
    expect(rangoDe(V({ preset: 'trimestre' }), AHORA).desde).toEqual(new Date(2026, 9, 1))
    expect(rangoDe(V({ preset: 'anio' }), AHORA).desde).toEqual(new Date(2026, 0, 1))
    const f = rangoDe(V({ preset: 'prox30d' }), AHORA)
    expect(f.desde).toEqual(AHORA)
    expect((f.hasta.getTime() - f.desde.getTime()) / 86400000).toBe(30)
  })

  it('fechas inclusivas para APIs por día', () => {
    const v = V({ preset: 'custom', desde: new Date(2026, 10, 1).toISOString(), hasta: new Date(2026, 10, 4).toISOString() })
    expect(fechasDe(v, AHORA)).toEqual({ desde: '2026-11-01', hasta: '2026-11-03' })
  })

  it('auto igual que el backend; las no admitidas no se eligen', () => {
    const d = (n: number) => new Date(AHORA.getTime() - n * 86400000)
    expect(resolverGranularidad(d(1), AHORA, 'auto', ['hour', 'day', 'week', 'month'])).toBe('hour')
    expect(resolverGranularidad(d(30), AHORA, 'auto', ['hour', 'day', 'week', 'month'])).toBe('day')
    expect(resolverGranularidad(d(365), AHORA, 'auto', ['hour', 'day', 'week', 'month'])).toBe('week')
    expect(resolverGranularidad(d(1), AHORA, 'auto', SIN_HORA)).toBe('day')
    expect(resolverGranularidad(d(1), AHORA, 'hour', SOLO_MES)).toBe('month')
  })

  it('valida como la API: desde > hasta, rango máximo y demasiados puntos', () => {
    const custom = (a: Date, b: Date, g: ValorPeriodo['granularidad'] = 'auto') =>
      V({ preset: 'custom', desde: a.toISOString(), hasta: b.toISOString(), granularidad: g })
    expect(validarPeriodo(custom(AHORA, new Date(2026, 0, 1)), SIN_HORA)).toEqual({ codigo: 'desde_mayor_que_hasta' })
    expect(validarPeriodo(custom(new Date(2015, 0, 1), AHORA), SIN_HORA, LIMITES_POR_DEFECTO, AHORA)?.codigo).toBe('rango_excedido')
    expect(validarPeriodo(custom(new Date(2026, 0, 1), AHORA, 'hour'), ['hour', 'day'], LIMITES_POR_DEFECTO, AHORA)?.codigo).toBe('demasiados_puntos')
  })

  it('URL: ida y vuelta, sin tocar otros parámetros y vacía en el valor por defecto', () => {
    const defecto = V({})
    const sp = new URLSearchParams('tab=x')
    const v = V({ preset: 'custom', desde: '2026-11-01T00:00:00+01:00', hasta: '2026-11-02T00:00:00+01:00', granularidad: 'hour', comparar: true })
    const out = aUrl(sp, v, defecto, 'a_')
    expect(out.get('tab')).toBe('x')
    expect(deUrl(out, defecto, 'a_')).toEqual(v)
    expect(aUrl(sp, defecto, defecto).toString()).toBe('tab=x')
  })

  it('formato del eje según granularidad, con el formateador de la app', () => {
    expect(formatearTramo('2026-11-16T08:00', 'hour')).toMatch(/08:00/)
    expect(formatearTramo('2026-11-01T00:00:00+01:00', 'month')).toMatch(/2026/)
  })
})

function envoltorio(url: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}><MemoryRouter initialEntries={[url]}>{children}</MemoryRouter></QueryClientProvider>
  )
}

describe('usePeriodo', () => {
  it('lee el periodo de la URL y lo escribe al cambiar', () => {
    let ubicacion = ''
    const { result } = renderHook(() => {
      const p = usePeriodo({ defecto: '30d', granularidades: SIN_HORA })
      ubicacion = useLocation().search
      return p
    }, { wrapper: envoltorio('/informe?periodo=7d&granularidad=week') })
    expect(result.current.params).toMatchObject({ days: 7, granularidad: 'week' })
    act(() => result.current.cambiar({ ...result.current.valor, preset: '90d' }))
    expect(ubicacion).toContain('periodo=90d')
    expect(result.current.params.days).toBe(90)
  })

  it('una granularidad no admitida en el enlace cae a auto', () => {
    const { result } = renderHook(() => usePeriodo({ granularidades: SIN_HORA }), { wrapper: envoltorio('/x?granularidad=hour') })
    expect(result.current.valor.granularidad).toBe('auto')
    expect(result.current.granularidad).toBe('day')
  })

  it('params estables entre renders (clave de React Query)', () => {
    const { result, rerender } = renderHook(() => usePeriodo({}), { wrapper: envoltorio('/x?periodo=mes') })
    const antes = result.current.params
    rerender()
    expect(result.current.params).toBe(antes)
  })
})

describe('SelectorDePeriodo', () => {
  it('desactiva y explica la hora cuando el dato es por día', () => {
    render(<SelectorDePeriodo valor={V({})} onChange={() => {}} granularidades={SIN_HORA} />)
    const hora = screen.getByRole('option', { name: /periodo\.g_hour/ })
    expect(hora).toBeDisabled()
    expect(screen.getByText('periodo.hora_no_disponible')).toBeInTheDocument()
  })

  it('accesos rápidos emiten el preset; personalizado pide fechas y se aplica', () => {
    const onChange = vi.fn()
    render(<SelectorDePeriodo valor={V({})} onChange={onChange} granularidades={SIN_HORA} />)
    fireEvent.change(screen.getByRole('combobox', { name: 'periodo.periodo' }), { target: { value: '7d' } })
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ preset: '7d' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'periodo.periodo' }), { target: { value: 'custom' } })
    const [desde, hasta] = screen.getAllByRole('textbox')
    fireEvent.change(desde, { target: { value: '01/11/2026' } })
    fireEvent.change(hasta, { target: { value: '03/11/2026' } })
    fireEvent.click(screen.getByRole('button', { name: 'periodo.aplicar' }))
    const v = onChange.mock.calls.at(-1)![0] as ValorPeriodo
    expect(v.preset).toBe('custom')
    expect(new Date(v.desde!)).toEqual(new Date(2026, 10, 1))
    expect(new Date(v.hasta!)).toEqual(new Date(2026, 10, 4)) // fin incluido → día siguiente
  })

  it('con hora, el personalizado lleva fecha y hora', () => {
    render(<SelectorDePeriodo valor={V({ preset: 'custom', desde: new Date(2026, 10, 1, 8).toISOString(), hasta: new Date(2026, 10, 1, 20).toISOString() })} onChange={() => {}} />)
    expect(screen.getAllByRole('textbox')[0]).toHaveValue('01/11/2026 08:00')
  })

  it('comparar solo donde el informe lo soporta', () => {
    const onChange = vi.fn()
    const { rerender } = render(<SelectorDePeriodo valor={V({})} onChange={onChange} />)
    expect(screen.queryByRole('checkbox')).toBeNull()
    rerender(<SelectorDePeriodo valor={V({})} onChange={onChange} comparable />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'periodo.comparar' }))
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ comparar: true }))
  })
})
