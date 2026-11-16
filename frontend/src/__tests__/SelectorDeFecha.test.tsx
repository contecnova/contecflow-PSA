// Selector de fecha propio del kit (16-11-2026): formato por idioma (sale del
// formateador de la app, no del navegador), máscara y validación al escribir,
// teclado del calendario (patrón grid), mín/máx, rango y zona horaria.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, act } from '@testing-library/react'
import { useState } from 'react'

let idioma = 'es'
vi.mock('../i18n/AppLangContext', () => ({
  useAppLang: () => ({ t: (k: string) => k, lang: idioma }),
  useAppT: () => (k: string) => k,
}))

import { CampoFecha, CampoRangoDeFechas } from '../components/ui/SelectorDeFecha'
import DateInput from '../components/ui/DateInput'
import {
  enmascarar, instanteEnZona, isoEnZona, leerTexto, paredEnZona, patronDeFecha, primerDiaDeSemana,
  rejillaDelMes, textoDe,
} from '../utils/fechas'

beforeEach(() => { idioma = 'es' })

describe('utils/fechas: formato por idioma', () => {
  it('es escribe dd/mm/aaaa, en mm/dd/yyyy y zh aaaa年m月d日', () => {
    const p = { y: 2026, m: 3, d: 5, h: 0, mi: 0 }
    expect(textoDe(p, 'fecha', patronDeFecha('es'))).toBe('05/03/2026')
    expect(textoDe(p, 'fecha', patronDeFecha('en'))).toBe('03/05/2026')
    expect(textoDe(p, 'fecha', patronDeFecha('zh'))).toBe('2026年3月5日')
    expect(patronDeFecha('es').marcador).toBe('dd/mm/aaaa')
  })

  it('la máscara pone los separadores del idioma al teclear y deja borrar', () => {
    const es = patronDeFecha('es')
    expect(enmascarar('1611', 'fecha', es)).toBe('16/11')
    expect(enmascarar('16112026', 'fecha', es)).toBe('16/11/2026')
    expect(enmascarar('16/', 'fecha', es)).toBe('16')
    expect(enmascarar('161120260830', 'fechaHora', es)).toBe('16/11/2026 08:30')
    expect(enmascarar('20261116', 'fecha', patronDeFecha('zh'))).toBe('2026年11月16')
    expect(enmascarar('0830', 'hora', es)).toBe('08:30')
  })

  it('valida al leer: fechas imposibles y horas fuera de rango son null', () => {
    const es = patronDeFecha('es')
    expect(leerTexto('31/02/2026', 'fecha', es)).toBeNull()
    expect(leerTexto('29/02/2028', 'fecha', es)).toMatchObject({ y: 2028, m: 2, d: 29 })
    expect(leerTexto('16/11/2026 24:00', 'fechaHora', es)).toBeNull()
    expect(leerTexto('2026年1月5日', 'fecha', patronDeFecha('zh'))).toMatchObject({ y: 2026, m: 1, d: 5 })
  })

  it('primer día de la semana según idioma y rejilla de 6 semanas', () => {
    expect(primerDiaDeSemana('es')).toBe(1)
    expect(primerDiaDeSemana('en')).toBe(0)
    const rej = rejillaDelMes(2026, 11, 1)
    expect(rej).toHaveLength(6)
    expect(rej[0][0]).toMatchObject({ y: 2026, m: 10, d: 26 }) // lunes anterior al 1 de noviembre (domingo)
  })

  it('convierte entre zonas (incluido el cambio de hora)', () => {
    const i = instanteEnZona({ y: 2026, m: 11, d: 16, h: 8, mi: 0 }, 'Europe/Madrid')
    expect(i.toISOString()).toBe('2026-11-16T07:00:00.000Z')
    expect(isoEnZona(i, 'Europe/Madrid')).toBe('2026-11-16T08:00:00+01:00')
    expect(paredEnZona(new Date('2026-07-01T22:30:00Z'), 'Europe/Madrid')).toMatchObject({ d: 2, h: 0, mi: 30 })
    expect(isoEnZona(new Date('2026-11-16T07:00:00Z'), 'Asia/Shanghai')).toBe('2026-11-16T15:00:00+08:00')
  })
})

function Controlado(props: { inicial?: string; onCambio?: (v: string) => void; modo?: 'fecha' | 'fechaHora' | 'hora'; min?: string; max?: string; zona?: string }) {
  const [v, setV] = useState(props.inicial ?? '')
  return <CampoFecha aria-label="fecha" value={v} modo={props.modo} min={props.min} max={props.max} zona={props.zona}
    onChange={x => { setV(x); props.onCambio?.(x) }} />
}

describe('CampoFecha', () => {
  it('no es un input nativo de fecha y pinta el valor con el formato del idioma', () => {
    render(<Controlado inicial="2026-11-16" />)
    const campo = screen.getByRole('textbox', { name: 'fecha' })
    expect(campo).toHaveAttribute('type', 'text')
    expect(campo).toHaveValue('16/11/2026')
  })

  it('en zh pinta aaaa年m月d日', () => {
    idioma = 'zh'
    render(<Controlado inicial="2026-03-05" />)
    expect(screen.getByRole('textbox', { name: 'fecha' })).toHaveValue('2026年3月5日')
  })

  it('al escribir emite el valor ISO solo cuando está completo y es válido', () => {
    const onCambio = vi.fn()
    render(<Controlado onCambio={onCambio} />)
    const campo = screen.getByRole('textbox', { name: 'fecha' })
    fireEvent.change(campo, { target: { value: '1611' } })
    expect(onCambio).not.toHaveBeenCalled()
    fireEvent.change(campo, { target: { value: '16112026' } })
    expect(onCambio).toHaveBeenLastCalledWith('2026-11-16')
    fireEvent.change(campo, { target: { value: '31022026' } })
    expect(campo).toHaveAttribute('aria-invalid', 'true')
    expect(onCambio).toHaveBeenCalledTimes(1)
  })

  it('respeta mín y máx al escribir', () => {
    const onCambio = vi.fn()
    render(<Controlado onCambio={onCambio} min="2026-11-10" max="2026-11-20" />)
    const campo = screen.getByRole('textbox', { name: 'fecha' })
    fireEvent.change(campo, { target: { value: '01/11/2026' } })
    expect(onCambio).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('fecha.min')
    fireEvent.change(campo, { target: { value: '15/11/2026' } })
    expect(onCambio).toHaveBeenLastCalledWith('2026-11-15')
  })

  it('teclado del calendario: flechas, Re Pág/Av Pág, Inicio/Fin, Intro y Escape', () => {
    const onCambio = vi.fn()
    render(<Controlado inicial="2026-11-16" onCambio={onCambio} />)
    fireEvent.click(screen.getByRole('button', { name: 'fecha.abrir_calendario' }))
    const grid = screen.getByRole('grid')
    const enfocado = () => within(grid).getAllByRole('button').find(b => b.getAttribute('tabindex') === '0')!
    expect(enfocado()).toHaveTextContent('16')
    fireEvent.keyDown(grid, { key: 'ArrowRight' })
    expect(enfocado()).toHaveTextContent('17')
    fireEvent.keyDown(grid, { key: 'ArrowDown' })
    expect(enfocado()).toHaveTextContent('24')
    fireEvent.keyDown(grid, { key: 'Home' }) // lunes en es
    expect(enfocado()).toHaveTextContent('23')
    fireEvent.keyDown(grid, { key: 'End' })
    expect(enfocado()).toHaveTextContent('29')
    fireEvent.keyDown(grid, { key: 'PageDown' })
    expect(enfocado()).toHaveTextContent('29') // 29 de diciembre
    fireEvent.keyDown(grid, { key: 'Enter' })
    expect(onCambio).toHaveBeenLastCalledWith('2026-12-29')
    expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'fecha.abrir_calendario' }))
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('los días fuera de mín/máx salen desactivados y no se eligen', () => {
    const onCambio = vi.fn()
    render(<Controlado inicial="2026-11-16" onCambio={onCambio} min="2026-11-10" max="2026-11-20" />)
    fireEvent.click(screen.getByRole('button', { name: 'fecha.abrir_calendario' }))
    const dia5 = within(screen.getByRole('grid')).getAllByRole('button').find(b => b.textContent === '5' && !b.className.includes('fuera'))!
    expect(dia5).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(dia5)
    expect(onCambio).not.toHaveBeenCalled()
  })

  it('modo hora con selector de horas y minutos', () => {
    const onCambio = vi.fn()
    render(<Controlado modo="hora" inicial="08:30" onCambio={onCambio} />)
    expect(screen.getByRole('textbox', { name: 'fecha' })).toHaveValue('08:30')
    fireEvent.click(screen.getByRole('button', { name: 'fecha.abrir_hora' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'fecha.horas' }), { target: { value: '14' } })
    expect(onCambio).toHaveBeenLastCalledWith('14:30')
  })

  it('con zona edita el instante en esa zona y devuelve ISO con su desfase', () => {
    const onCambio = vi.fn()
    render(<Controlado modo="fechaHora" zona="Asia/Shanghai" inicial="2026-11-16T07:00:00Z" onCambio={onCambio} />)
    const campo = screen.getByRole('textbox', { name: 'fecha' })
    expect(campo).toHaveValue('16/11/2026 15:00')
    fireEvent.change(campo, { target: { value: '16/11/2026 16:30' } })
    expect(onCambio).toHaveBeenLastCalledWith('2026-11-16T16:30:00+08:00')
  })
})

describe('CampoRangoDeFechas y DateInput', () => {
  it('el rango enlaza mín/máx entre desde y hasta', () => {
    const onChange = vi.fn()
    render(<CampoRangoDeFechas desde="2026-11-10" hasta="2026-11-20" onChange={onChange} />)
    const [desde, hasta] = screen.getAllByRole('textbox')
    fireEvent.change(hasta, { target: { value: '05/11/2026' } }) // antes de «desde»: no vale
    expect(onChange).not.toHaveBeenCalled()
    fireEvent.change(desde, { target: { value: '12/11/2026' } })
    expect(onChange).toHaveBeenLastCalledWith({ desde: '2026-11-12', hasta: '2026-11-20' })
  })

  it('DateInput mantiene su API (e.target.value) con el selector propio por dentro', () => {
    const onChange = vi.fn()
    render(<DateInput aria-label="d" name="inicio" value="" onChange={onChange} />)
    const campo = screen.getByRole('textbox', { name: 'd' })
    expect(campo).toHaveAttribute('type', 'text')
    act(() => { fireEvent.change(campo, { target: { value: '01/12/2026' } }) })
    expect(onChange.mock.calls[0][0].target).toMatchObject({ value: '2026-12-01', name: 'inicio' })
  })
})
