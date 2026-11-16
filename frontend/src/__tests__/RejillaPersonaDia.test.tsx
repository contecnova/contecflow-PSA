import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import RejillaPersonaDia, { columnasDeDias, columnasDeSemanas, isoLocal, NavegadorDeMes } from '../components/ui/RejillaPersonaDia'

vi.mock('../i18n/AppLangContext', () => ({
  useAppLang: () => ({ t: (k: string) => k, lang: 'es' }),
  useAppT: () => (k: string) => k,
}))

const filas = [{ id: 'u1', nombre: 'Ana Pérez', sub: 'Dev' }, { id: 'u2', nombre: 'Luis Gil' }]

describe('RejillaPersonaDia', () => {
  it('columnasDeDias: un día por columna, fin de semana y festivo atenuados, hoy marcado', () => {
    const cols = columnasDeDias('2026-11-13', '2026-11-16', { festivos: new Map([['2026-11-13', 'Fiesta']]) })
    expect(cols.map(c => c.clave)).toEqual(['2026-11-13', '2026-11-14', '2026-11-15', '2026-11-16'])
    expect(cols.map(c => c.atenuada)).toEqual([true, true, true, false]) // festivo, sábado, domingo, lunes
    expect(cols[0].titulo).toContain('Fiesta')
    const hoy = isoLocal(new Date())
    expect(columnasDeDias(hoy, hoy)[0].hoy).toBe(true)
    expect(columnasDeSemanas([hoy]).length).toBe(1)
  })

  it('pinta filas, cabeceras, estados con la leyenda y el detalle accesible', () => {
    render(
      <RejillaPersonaDia titulo="Calendario" cabeceraFilas="Persona" filas={filas}
        columnas={columnasDeDias('2026-11-16', '2026-11-17')}
        celda={(f, c) => (f.id === 'u1' && c.clave === '2026-11-16' ? { estado: 'vac', detalle: 'Ana · Vacaciones', contenido: 'V' } : null)}
        leyenda={[{ clave: 'vac', etiqueta: 'Vacaciones', tono: 'success' }]} />,
    )
    const tabla = screen.getByRole('table')
    expect(within(tabla).getByText('Ana Pérez')).toBeInTheDocument()
    expect(within(tabla).getByRole('columnheader', { name: 'Persona' })).toBeInTheDocument()
    expect(within(tabla).getByText('Ana · Vacaciones')).toBeInTheDocument()
    expect(within(tabla).getByText('V').closest('.rpd-celda')).toHaveClass('rpd-tono--success')
    expect(screen.getByRole('list', { name: 'uikit.leyenda' })).toHaveTextContent('Vacaciones')
  })

  it('celdas pulsables: una sola parada de tabulador y flechas entre celdas', () => {
    const onCelda = vi.fn()
    render(
      <RejillaPersonaDia titulo="T" cabeceraFilas="Persona" filas={filas}
        columnas={columnasDeDias('2026-11-16', '2026-11-17')}
        celda={(f, c) => ({ detalle: `${f.nombre} ${c.clave}` })} onCelda={onCelda} />,
    )
    const botones = screen.getAllByRole('button')
    expect(botones.filter(b => b.tabIndex === 0)).toHaveLength(1)
    const primera = screen.getByRole('button', { name: 'Ana Pérez 2026-11-16' })
    primera.focus()
    fireEvent.keyDown(primera, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Luis Gil 2026-11-16' }))
    fireEvent.click(document.activeElement as HTMLElement)
    expect(onCelda).toHaveBeenCalledWith(filas[1], expect.objectContaining({ clave: '2026-11-16' }))
  })

  it('NavegadorDeMes cambia de mes', () => {
    const onCambiar = vi.fn()
    render(<NavegadorDeMes mes={new Date(2026, 10, 1)} onCambiar={onCambiar} />)
    fireEvent.click(screen.getByRole('button', { name: 'uikit.mes_siguiente' }))
    expect(onCambiar.mock.calls[0][0].getMonth()).toBe(11)
  })
})
