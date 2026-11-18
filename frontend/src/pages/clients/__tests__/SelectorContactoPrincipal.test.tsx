// Empresa frente a contactos: el selector del contacto principal del alta/
// edición de cliente y lo que manda al servidor.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import {
  SelectorContactoPrincipal, datosDeContactoPrincipal, NUEVO_CONTACTO, NUEVO_CONTACTO_VACIO,
} from '../SelectorContactoPrincipal'

vi.mock('../../../i18n/AppLangContext', () => ({
  useAppLang: () => ({ t: (k: string) => k, lang: 'es' }),
  useAppT: () => (k: string) => k,
}))

const CONTACTOS = [
  { id: 'c1', full_name: 'Ana Pérez', email: 'ana@acme.es', job_title: 'CTO' },
  { id: 'c2', full_name: 'Luis Gil', email: null, job_title: null },
]

describe('SelectorContactoPrincipal', () => {
  it('en el alta (sin contactos) enseña directamente los campos del nuevo contacto', () => {
    render(<SelectorContactoPrincipal idBase="x" contactos={[]} valor="" onCambiar={() => undefined}
      nuevo={NUEVO_CONTACTO_VACIO} onCambiarNuevo={() => undefined} />)
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.getByLabelText('clicontactos.email_contacto')).toBeInTheDocument()
    expect(screen.getByLabelText('clicontactos.telefono_contacto')).toBeInTheDocument()
  })

  it('con contactos: lista los existentes más «Nuevo contacto…» y solo despliega los campos al elegirlo', () => {
    const onCambiar = vi.fn()
    const { rerender } = render(<SelectorContactoPrincipal idBase="x" contactos={CONTACTOS} valor="c1" onCambiar={onCambiar}
      nuevo={NUEVO_CONTACTO_VACIO} onCambiarNuevo={() => undefined} />)
    const select = screen.getByRole('combobox') as HTMLSelectElement
    expect(select.value).toBe('c1')
    expect(screen.getByRole('option', { name: 'Ana Pérez · CTO · ana@acme.es' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'clicontactos.nuevo_contacto_opcion' })).toBeInTheDocument()
    expect(screen.queryByLabelText('clicontactos.email_contacto')).not.toBeInTheDocument()

    fireEvent.change(select, { target: { value: NUEVO_CONTACTO } })
    expect(onCambiar).toHaveBeenCalledWith(NUEVO_CONTACTO)
    rerender(<SelectorContactoPrincipal idBase="x" contactos={CONTACTOS} valor={NUEVO_CONTACTO} onCambiar={onCambiar}
      nuevo={NUEVO_CONTACTO_VACIO} onCambiarNuevo={() => undefined} />)
    expect(screen.getByLabelText('clicontactos.email_contacto')).toBeInTheDocument()
  })

  it('pasa los cambios del nuevo contacto y pinta el error de campo', () => {
    const onCambiarNuevo = vi.fn()
    render(<SelectorContactoPrincipal idBase="x" contactos={[]} valor="" onCambiar={() => undefined}
      nuevo={NUEVO_CONTACTO_VACIO} onCambiarNuevo={onCambiarNuevo}
      errorDe={k => (k === 'contact_email' ? 'Email inválido' : undefined)} />)
    fireEvent.change(screen.getByLabelText('clicontactos.nombre_contacto'), { target: { value: 'Eva' } })
    expect(onCambiarNuevo).toHaveBeenCalledWith('contact_name', 'Eva')
    expect(screen.getByText('Email inválido')).toBeInTheDocument()
    expect(screen.getByLabelText('clicontactos.email_contacto')).toHaveAttribute('aria-invalid', 'true')
  })
})

describe('datosDeContactoPrincipal', () => {
  const nuevo = { contact_name: ' Eva ', contact_role: '', contact_email: 'eva@acme.es', contact_phone: '' }
  it('contacto existente → primary_contact_id y nada de contact_*', () => {
    expect(datosDeContactoPrincipal(true, 'c2', nuevo)).toEqual({ primary_contact_id: 'c2' })
  })
  it('sin elección → no cambia el principal', () => {
    expect(datosDeContactoPrincipal(true, '', nuevo)).toEqual({})
  })
  it('nuevo contacto → solo los contact_* escritos, recortados', () => {
    expect(datosDeContactoPrincipal(true, NUEVO_CONTACTO, nuevo)).toEqual({ contact_name: 'Eva', contact_email: 'eva@acme.es' })
    expect(datosDeContactoPrincipal(false, '', nuevo)).toEqual({ contact_name: 'Eva', contact_email: 'eva@acme.es' })
    expect(datosDeContactoPrincipal(false, '', NUEVO_CONTACTO_VACIO)).toEqual({})
  })
})
