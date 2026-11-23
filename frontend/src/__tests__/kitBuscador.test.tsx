// 23-11-2026: campos con icono y buscador del kit. La lupa va DENTRO del
// campo (nunca un icono absoluto a mano junto a un Input), oculta al lector,
// con el relleno del texto puesto por el kit; la X vacía y devuelve el foco.
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { Mail } from 'lucide-react'
import { Buscador, FiltrosDeLista, Input, Segmentado } from '../components/ui'

afterEach(() => { vi.useRealTimers() })

describe('Input con icono', () => {
  it('pinta el icono dentro de la caja, aria-hidden, y marca el relleno', () => {
    const { container } = render(<Input aria-label="Correo" value="" onChange={() => {}} icono={<Mail />} />)
    const icono = container.querySelector('.ui-input-caja > .ui-input-caja__icono')
    expect(icono?.getAttribute('aria-hidden')).toBe('true')
    expect(icono?.querySelector('svg')).not.toBeNull()
    expect(screen.getByLabelText('Correo').classList.contains('ui-input--icono-ini')).toBe(true)
  })

  it('sin icono no envuelve el campo', () => {
    const { container } = render(<Input aria-label="Nombre" value="" onChange={() => {}} />)
    expect(container.querySelector('.ui-input-caja')).toBeNull()
  })
})

describe('Buscador', () => {
  it('lleva la lupa, nombre accesible y avisa con el texto', () => {
    const onChange = vi.fn()
    const { container } = render(<Buscador value="" onChange={onChange} placeholder="Buscar clientes" />)
    const campo = screen.getByRole('searchbox', { name: 'Buscar clientes' })
    expect(container.querySelector('.ui-buscador .ui-input-caja__icono svg')).not.toBeNull()
    fireEvent.change(campo, { target: { value: 'acme' } })
    expect(onChange).toHaveBeenCalledWith('acme')
  })

  it('la X solo sale con texto, vacía y devuelve el foco', () => {
    const onChange = vi.fn()
    const { rerender } = render(<Buscador value="" onChange={onChange} aria-label="Buscar" />)
    expect(screen.queryByRole('button')).toBeNull()
    rerender(<Buscador value="acme" onChange={onChange} aria-label="Buscar" />)
    const limpiar = screen.getByRole('button')
    fireEvent.click(limpiar)
    expect(onChange).toHaveBeenLastCalledWith('')
    expect(document.activeElement).toBe(screen.getByRole('searchbox'))
  })

  it('con retardo espera a que se deje de escribir', () => {
    vi.useFakeTimers()
    const onChange = vi.fn()
    render(<Buscador value="" onChange={onChange} retardo={300} aria-label="Buscar" />)
    const campo = screen.getByRole('searchbox')
    fireEvent.change(campo, { target: { value: 'a' } })
    fireEvent.change(campo, { target: { value: 'ab' } })
    expect(onChange).not.toHaveBeenCalled()
    act(() => { vi.advanceTimersByTime(300) })
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('ab')
  })
})

describe('FiltrosDeLista', () => {
  it('buscador a todo el ancho, segmentado y rejilla de desplegables', () => {
    const { container } = render(
      <FiltrosDeLista
        buscador={<Buscador value="" onChange={() => {}} aria-label="Buscar" />}
        segmentado={<Segmentado aria-label="Tipo" valor="" onChange={() => {}} opciones={[{ valor: '', etiqueta: 'Todos' }, { valor: 'a', etiqueta: 'A' }]} />}>
        <span>uno</span>
        <span>dos</span>
      </FiltrosDeLista>,
    )
    const grupo = container.querySelector('.ui-filtros-lista')
    expect(grupo?.getAttribute('role')).toBe('group')
    expect(grupo?.querySelector(':scope > .ui-buscador')).not.toBeNull()
    expect(grupo?.querySelector('.ui-filtros-lista__segmentado > .ds-segmented')).not.toBeNull()
    expect(grupo?.querySelectorAll('.ui-filtros-lista__rejilla > span')).toHaveLength(2)
  })
})
