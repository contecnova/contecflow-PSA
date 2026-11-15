import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import { useFormValidation } from '../useFormValidation'

describe('useFormValidation().inputClass', () => {
  const esquema = z.object({ titulo: z.string().min(1, 'obligatorio') })

  it('devuelve la clase base y añade campo-form--error solo al campo con error', () => {
    const { result } = renderHook(() => useFormValidation(esquema))
    expect(result.current.inputClass('campo-form', 'titulo')).toBe('campo-form')
    act(() => { result.current.validateForm({ titulo: '' }) })
    expect(result.current.inputClass('campo-form', 'titulo')).toBe('campo-form campo-form--error')
    expect(result.current.inputClass('campo-form', 'otro')).toBe('campo-form')
    act(() => { result.current.clearFieldError('titulo') })
    expect(result.current.inputClass('campo-form x', 'titulo')).toBe('campo-form x')
  })
})
