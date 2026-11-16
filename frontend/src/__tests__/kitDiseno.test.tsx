// Pasada de diseño 16-11-2026: el kit común impone el estándar visual aunque
// quien lo llame pase restos antiguos (emojis, "+ " en el texto, variantes de
// pestañas o botones que ya no existen).
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Folder } from 'lucide-react'
import { Button, EmptyState, KpiCard, Tabs } from '../components/ui'

const PICTOGRAMA = /\p{Extended_Pictographic}/u

describe('kit: estándar de diseño', () => {
  it('EmptyState ignora un emoji como icono y pinta un icono svg', () => {
    const { container } = render(<EmptyState icon="📋" title="Vacío" />)
    expect(container.textContent).not.toMatch(PICTOGRAMA)
    expect(container.querySelector('.empty-state-icon svg')).not.toBeNull()
  })

  it('EmptyState respeta un icono lucide', () => {
    const { container } = render(<EmptyState icon={<Folder data-testid="ico" size={28} />} title="Vacío" />)
    expect(screen.getByTestId('ico')).toBeTruthy()
    expect(container.querySelector('.empty-state-title')?.textContent).toBe('Vacío')
  })

  it('KpiCard: cifra y etiqueta en versalitas, sin emoji como icono', () => {
    const { container } = render(<KpiCard icon="💰" label="Total" value={12} />)
    expect(container.textContent).not.toMatch(PICTOGRAMA)
    expect(container.querySelector('.ds-eyebrow')?.textContent).toBe('Total')
    expect(container.querySelector('.ui-kpi__valor')?.textContent).toBe('12')
  })

  it('KpiCard con onClick es un botón', () => {
    const onClick = vi.fn()
    render(<KpiCard label="Abiertas" value={3} onClick={onClick} ariaLabel="Ver abiertas" />)
    fireEvent.click(screen.getByRole('button', { name: 'Ver abiertas' }))
    expect(onClick).toHaveBeenCalled()
  })

  it('Button convierte "+ Nuevo" en icono + texto y quita emojis', () => {
    const { container, rerender } = render(<Button>+ Nuevo cliente</Button>)
    expect(container.textContent).toBe('Nuevo cliente')
    expect(container.querySelector('svg')).not.toBeNull()
    rerender(<Button>🔄 Refrescar</Button>)
    expect(container.textContent).toBe('Refrescar')
  })

  it('Button reenvía aria-label y data-*', () => {
    render(<Button aria-label="Cerrar panel" data-tour="cerrar">x</Button>)
    const b = screen.getByRole('button', { name: 'Cerrar panel' })
    expect(b.getAttribute('data-tour')).toBe('cerrar')
  })

  it('Button subtle se pinta como secondary', () => {
    const { container } = render(<Button variant="subtle">Auto</Button>)
    expect(container.querySelector('.ui-btn--secondary')).not.toBeNull()
  })

  it('Tabs: siempre pastilla md y sin emojis en las etiquetas', () => {
    const { container } = render(
      <Tabs variant="underline" size="lg" active="a" onChange={() => {}}
        items={[{ id: 'a', label: '📋 Lista' }, { id: 'b', label: 'Mapa' }]} />,
    )
    expect(container.querySelector('.uitabs--pill')).not.toBeNull()
    expect(container.querySelector('.uitabs--underline')).toBeNull()
    expect(container.querySelectorAll('.uitabs-row-2--md').length).toBe(2)
    expect(container.textContent).toBe('ListaMapa')
  })
})
