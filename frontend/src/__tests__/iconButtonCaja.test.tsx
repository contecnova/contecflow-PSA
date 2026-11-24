// IconButton variante="caja" (23-11-2026): estándar de las acciones de solo
// icono en tarjetas, filas y cabeceras (editar, borrar, más, copiar, cerrar).
import fs from 'node:fs'
import path from 'node:path'
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Pencil, Trash2 } from 'lucide-react'
import { IconButton } from '../components/ui'

const CSS = fs.readFileSync(path.resolve(__dirname, '../components/ui/IconButton.css'), 'utf8')
const regla = (selector: string) => {
  const i = CSS.indexOf(`${selector} {`)
  expect(i).toBeGreaterThanOrEqual(0)
  return CSS.slice(i, CSS.indexOf('}', i))
}

describe('IconButton variante="caja"', () => {
  it('lleva el aria-label (y el tooltip) obligatorio', () => {
    render(<IconButton variante="caja" ariaLabel="Editar proveedor"><Pencil /></IconButton>)
    const b = screen.getByRole('button', { name: 'Editar proveedor' })
    expect(b).toHaveAttribute('title', 'Editar proveedor')
    expect(b).toHaveAttribute('type', 'button')
  })

  it('por defecto: caja sm y tono neutro', () => {
    render(<IconButton variante="caja" ariaLabel="Editar"><Pencil /></IconButton>)
    const b = screen.getByRole('button', { name: 'Editar' })
    expect(b.className.split(' ')).toEqual(expect.arrayContaining(['icon-button', 'icon-button--caja', 'icon-button--sm', 'icon-button--neutro']))
  })

  it('tono peligro y tamaño md; las clases propias se suman', () => {
    render(<IconButton variante="caja" tono="peligro" tamano="md" className="mi-sitio" ariaLabel="Borrar"><Trash2 /></IconButton>)
    const b = screen.getByRole('button', { name: 'Borrar' })
    expect(b).toHaveClass('icon-button--peligro', 'icon-button--md', 'mi-sitio')
    expect(b).not.toHaveClass('icon-button--sm')
  })

  it('sin variante sigue siendo el IconButton simple (sin caja)', () => {
    render(<IconButton ariaLabel="Cerrar"><Pencil /></IconButton>)
    expect(screen.getByRole('button', { name: 'Cerrar' }).className).toBe('icon-button')
  })

  it('CSS: cuadrado (ancho = alto = lado), sin estirarse y con el icono a tamaño fijo', () => {
    const caja = regla('.icon-button--caja')
    expect(caja).toMatch(/width: var\(--icon-button-lado\)/)
    expect(caja).toMatch(/height: var\(--icon-button-lado\)/)
    expect(caja).toMatch(/flex: none/)
    expect(caja).toMatch(/align-self: flex-start/)
    expect(caja).toMatch(/padding: 0/)
    expect(regla('.icon-button--caja > svg')).toMatch(/width: var\(--icon-button-icono\)/)
    expect(CSS).toMatch(/\.icon-button--sm \{ --icon-button-lado: var\(--alto-control-sm\); --icon-button-icono: 16px; \}/)
    expect(CSS).toMatch(/\.icon-button--xs \{ --icon-button-lado: var\(--alto-control-xs\); --icon-button-icono: 12px;/)
    expect(CSS).toMatch(/\.icon-button--md \{ --icon-button-lado: var\(--alto-control\); --icon-button-icono: 16px; \}/)
    expect(regla('.ui-acciones')).toMatch(/align-items: flex-start/)
  })
})
