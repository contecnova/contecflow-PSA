// Migración al kit (16-11-2026, fase 1): piezas nuevas del kit.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { useState } from 'react'
import {
  Badge, BarraDeFiltros, Button, Checkbox, Chip, GrupoDeOpciones, Pulsable, Segmentado, Select, Switch, Tabla,
  type ColumnaTabla,
} from '../components/ui'

type Fila = { id: string; nombre: string; horas: number }
const FILAS: Fila[] = [
  { id: 'a', nombre: 'Beta', horas: 5 },
  { id: 'b', nombre: 'Alfa', horas: 12 },
]
const COLS: Array<ColumnaTabla<Fila>> = [
  { key: 'nombre', label: 'Nombre', sortable: true },
  { key: 'horas', label: 'Horas', alinear: 'derecha', sortable: true, pie: 17 },
]
const nombres = () => screen.getAllByRole('row').slice(1, 3).map(r => within(r).getAllByRole('cell')[0].textContent)

describe('Tabla', () => {
  it('lleva el estilo contecflow-table, ordena y pinta el pie', () => {
    const { container } = render(<Tabla columnas={COLS} filas={FILAS} etiqueta="Datos" />)
    expect(container.querySelector('table.contecflow-table')).not.toBeNull()
    expect(nombres()).toEqual(['Beta', 'Alfa'])
    fireEvent.click(screen.getByRole('button', { name: /Nombre/ }))
    expect(nombres()).toEqual(['Alfa', 'Beta'])
    expect(screen.getByRole('columnheader', { name: /Nombre/ }).getAttribute('aria-sort')).toBe('ascending')
    expect(container.querySelector('tfoot')?.textContent).toContain('17')
  })

  it('fila clicable con ratón y teclado', () => {
    const onFila = vi.fn()
    render(<Tabla columnas={COLS} filas={FILAS} onFila={onFila} />)
    const fila = screen.getAllByRole('row')[1]
    fireEvent.click(within(fila).getByText('Beta'))
    fireEvent.keyDown(fila, { key: 'Enter' })
    expect(onFila).toHaveBeenCalledTimes(2)
  })

  it('selección con casillas (todas y una)', () => {
    function Prueba() {
      const [sel, setSel] = useState<Array<string | number>>([])
      return <Tabla columnas={COLS} filas={FILAS} seleccion={sel} onSeleccion={setSel} />
    }
    render(<Prueba />)
    const casillas = screen.getAllByRole('checkbox') as HTMLInputElement[]
    fireEvent.click(casillas[1])
    expect(casillas[1].checked).toBe(true)
    expect(casillas[0].indeterminate).toBe(true)
    fireEvent.click(casillas[0])
    expect(casillas.every(c => c.checked)).toBe(true)
  })

  it('celda editable en el sitio: clic abre, Intro guarda', () => {
    const onGuardar = vi.fn()
    const cols: Array<ColumnaTabla<Fila>> = [{ key: 'nombre', label: 'Nombre', editar: { tipo: 'texto', valor: f => f.nombre, onGuardar } }]
    render(<Tabla columnas={cols} filas={[FILAS[0]]} />)
    fireEvent.click(screen.getByRole('button', { name: /Beta/ }))
    const campo = screen.getByRole('textbox', { name: 'Nombre' })
    fireEvent.change(campo, { target: { value: 'Gamma' } })
    fireEvent.keyDown(campo, { key: 'Enter' })
    expect(onGuardar).toHaveBeenCalledWith(FILAS[0], 'Gamma')
  })

  it('vacío y carga', () => {
    const { rerender } = render(<Tabla columnas={COLS} filas={[]} vacio={{ titulo: 'Nada aún' }} />)
    expect(screen.getByText('Nada aún')).toBeTruthy()
    rerender(<Tabla columnas={COLS} filas={[]} cargando />)
    expect(screen.getByRole('status')).toBeTruthy()
  })
})

describe('controles del kit', () => {
  it('Select suelto: solo el control, con hijos', () => {
    const { container } = render(
      <Select suelto aria-label="Estado" value="b" onChange={() => {}} placeholder={false}>
        <option value="a">A</option><option value="b">B</option>
      </Select>,
    )
    expect(container.firstElementChild?.tagName).toBe('SELECT')
    expect((screen.getByRole('combobox', { name: 'Estado' }) as HTMLSelectElement).value).toBe('b')
  })

  it('Checkbox y Switch avisan del nuevo estado', () => {
    const onC = vi.fn()
    const onS = vi.fn()
    render(<><Checkbox checked={false} onChange={onC} label="Facturable" /><Switch checked onChange={onS} label="Activo" /></>)
    fireEvent.click(screen.getByLabelText('Facturable'))
    expect(onC.mock.calls[0][0]).toBe(true)
    const sw = screen.getByRole('switch', { name: 'Activo' })
    fireEvent.click(sw)
    expect(onS.mock.calls[0][0]).toBe(false)
  })

  it('GrupoDeOpciones radio y checkbox', () => {
    const onR = vi.fn()
    const onC = vi.fn()
    const ops = [{ valor: 'x', titulo: 'Equis' }, { valor: 'y', titulo: 'Ye' }]
    const { container } = render(<>
      <GrupoDeOpciones leyenda="Modo" opciones={ops} valor="x" onChange={onR} />
      <GrupoDeOpciones tipo="checkbox" leyenda="Canales" opciones={ops} valor={['x']} onChange={onC} />
    </>)
    expect(container.querySelectorAll('fieldset.ds-grupo-opciones')).toHaveLength(2)
    fireEvent.click(screen.getByRole('radio', { name: 'Ye' }))
    expect(onR).toHaveBeenCalledWith('y')
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'Ye' })[0])
    expect(onC).toHaveBeenCalledWith(['x', 'y'])
  })

  it('BarraDeFiltros, Chip, Segmentado, Pulsable y Button link', () => {
    const onChip = vi.fn()
    const onQuitar = vi.fn()
    const onSeg = vi.fn()
    const { container } = render(
      <BarraDeFiltros aria-label="Filtros de tareas" acciones={<Button variant="link">Limpiar</Button>}>
        <Chip activo onClick={onChip} onQuitar={onQuitar}>Abiertas</Chip>
        <Segmentado aria-label="Vista" valor="a" onChange={onSeg} opciones={[{ valor: 'a', etiqueta: 'Lista' }, { valor: 'b', etiqueta: 'Mapa' }]} />
        <Pulsable className="mi-tarjeta">Tarjeta</Pulsable>
      </BarraDeFiltros>,
    )
    expect(screen.getByRole('group', { name: 'Filtros de tareas' }).classList.contains('ds-toolbar')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Abiertas' }))
    expect(onChip).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Abiertas' }).getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: /Quitar.*Abiertas/ }))
    expect(onQuitar).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Mapa' }))
    expect(onSeg).toHaveBeenCalledWith('b')
    expect(container.querySelector('.ui-btn--link')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Tarjeta' }).className).toBe('ui-pulsable mi-tarjeta')
  })

  it('Badge es la pastilla del kit con tono', () => {
    const { container } = render(<><Badge label="approved" /><Badge tono="warning">Pendiente</Badge></>)
    expect(container.querySelector('.ds-pill--success')).not.toBeNull()
    expect(container.querySelector('.ds-pill--warning')?.textContent).toBe('Pendiente')
  })
})
