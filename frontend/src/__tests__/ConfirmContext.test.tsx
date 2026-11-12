// Auditoría 2026-11 (#29): los confirm()/prompt() nativos se sustituyeron por
// el diálogo de ConfirmContext. Aquí se comprueba la API de promesas.
import { vi, describe, it, expect } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { ConfirmProvider, confirmar, pedirTexto } from '../context/ConfirmContext'

vi.mock('../hooks/useAppT', () => ({
  useAppT: () => ({ t: (k: string) => ({ 'common.cancel': 'Cancelar', 'confirm_modal.default_title': 'Confirmar', 'confirm_modal.danger_title': 'Atención' } as Record<string, string>)[k] ?? k }),
}))

const montar = () => render(<ConfirmProvider><div /></ConfirmProvider>)

describe('ConfirmContext', () => {
  it('confirmar resuelve true al aceptar y false al cancelar', async () => {
    montar()
    let p!: Promise<boolean>
    act(() => { p = confirmar({ message: '¿Borrar?', confirmLabel: 'Borrar', danger: true }) })
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Borrar' }))
    await expect(p).resolves.toBe(true)

    act(() => { p = confirmar({ message: '¿Otra?' }) })
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar' }))
    await expect(p).resolves.toBe(false)
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('Esc cancela', async () => {
    montar()
    let p!: Promise<boolean>
    act(() => { p = confirmar({ message: '¿Seguro?' }) })
    await screen.findByRole('dialog')
    fireEvent.keyDown(document, { key: 'Escape' })
    await expect(p).resolves.toBe(false)
  })

  it('con palabraConfirmacion no deja aceptar hasta teclearla', async () => {
    montar()
    let p!: Promise<boolean>
    act(() => { p = confirmar({ message: 'Irreversible', danger: true, confirmLabel: 'Borrar PII', palabraConfirmacion: 'BORRAR' }) })
    const boton = await screen.findByRole('button', { name: 'Borrar PII' })
    expect(boton).toBeDisabled()
    const campo = screen.getByLabelText('Escribe BORRAR para confirmar')
    fireEvent.change(campo, { target: { value: 'borrar' } })
    expect(boton).toBeDisabled()
    fireEvent.change(campo, { target: { value: 'BORRAR' } })
    expect(boton).not.toBeDisabled()
    fireEvent.click(boton)
    await expect(p).resolves.toBe(true)
  })

  it('pedirTexto devuelve el texto, o null al cancelar; required bloquea el vacío', async () => {
    montar()
    let p!: Promise<string | null>
    act(() => { p = pedirTexto({ message: 'Motivo', label: 'Motivo', required: true, confirmLabel: 'Enviar' }) })
    const boton = await screen.findByRole('button', { name: 'Enviar' })
    expect(boton).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'porque sí' } })
    fireEvent.click(boton)
    await expect(p).resolves.toBe('porque sí')

    act(() => { p = pedirTexto({ message: 'Nota', label: 'Nota' }) })
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar' }))
    await expect(p).resolves.toBeNull()
  })
})
