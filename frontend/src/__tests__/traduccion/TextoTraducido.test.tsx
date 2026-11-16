// Traducción en tiempo real (16-11-2026): cómo se pinta un texto con su traducción.
import { vi, describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { MensajeTraducido } from '../../services/api/traduccion'

// t de prueba: la clave y, si las hay, las variables; con respaldo de texto, la clave.
const { tPrueba } = vi.hoisted(() => ({
  tPrueba: (k: string, p?: string | Record<string, unknown>) =>
    (p && typeof p === 'object' ? `${k}:${Object.values(p).join(',')}` : k),
}))
vi.mock('../../i18n/AppLangContext', () => ({ useAppT: () => tPrueba, useAppLang: () => ({ lang: 'es', t: tPrueba }) }))

import TextoTraducido from '../../components/traduccion/TextoTraducido'
import { nombreDeIdioma } from '../../hooks/useTraduccion'

const base: MensajeTraducido = {
  type: 'ticket_comment', id: 'c1', field: 'body', status: 'translated', text: 'La impresora no imprime',
  source_language: 'en', target_language: 'es', origin: 'auto', reason: null,
}
const ingles = nombreDeIdioma('en', 'es')

describe('TextoTraducido', () => {
  it('auto: enseña la traducción con su marca y deja ver el original', () => {
    render(<TextoTraducido original="The printer does not print" traduccion={base} />)
    expect(screen.getByText('La impresora no imprime')).toBeInTheDocument()
    expect(screen.getByText(`traduccion.marca_auto:${ingles}`)).toBeInTheDocument()
    const alternar = screen.getByRole('button', { name: 'traduccion.ver_original' })
    expect(alternar).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(alternar)
    expect(screen.getByText('The printer does not print')).toBeInTheDocument()
    expect(screen.getByText(`traduccion.marca_original:${ingles}`)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'traduccion.ver_traduccion' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('author: enseña lo que escribió el agente y deja ver lo que recibió el cliente', () => {
    render(<TextoTraducido original="Hello, we are on it" traduccion={{ ...base, text: 'Hola, estamos en ello', origin: 'author', source_language: 'es', target_language: 'en' }} />)
    expect(screen.getByText('Hola, estamos en ello')).toBeInTheDocument()
    expect(screen.getByText(`traduccion.marca_autor:${nombreDeIdioma('es', 'es')}`)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'traduccion.ver_enviado' }))
    expect(screen.getByText('Hello, we are on it')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'traduccion.ver_mio' })).toBeInTheDocument()
  })

  it('unavailable: el original con el motivo traducido', () => {
    render(<TextoTraducido original="The printer does not print" traduccion={{ ...base, status: 'unavailable', text: null, reason: 'timeout' }} />)
    expect(screen.getByText('The printer does not print')).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('traduccion.no_disponible:traduccion.motivo.timeout')
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('same_language: solo el original, sin marca ni botón', () => {
    render(<TextoTraducido original="Hola" traduccion={{ ...base, status: 'same_language', text: null }} />)
    expect(screen.getByText('Hola')).toBeInTheDocument()
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.queryByRole('note')).toBeNull()
  })

  it('system: el texto del sistema en el idioma de quien mira, sin marca', () => {
    render(<TextoTraducido original="Ticket created" traduccion={{ ...base, origin: 'system', text: 'Ticket creado' }} />)
    expect(screen.getByText('Ticket creado')).toBeInTheDocument()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('cargando: el original y el aviso de que se está traduciendo', () => {
    render(<TextoTraducido original="Hello" cargando />)
    expect(screen.getByText('Hello')).toBeInTheDocument()
    expect(screen.getByText('traduccion.traduciendo')).toBeInTheDocument()
  })
})
