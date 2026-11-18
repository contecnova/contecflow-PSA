import { describe, it, expect } from 'vitest'
import { extractErr, loadColor, statusColor } from './helpers'

describe('helpers', () => {
  it('extractErr normalizes pydantic array errors', () => {
    const err = {
      response: {
        data: {
          detail: [
            { loc: ['body', 'email'], msg: 'field required' },
            { loc: ['body', 'password'], msg: 'too short' },
          ],
        },
      },
    }
    expect(extractErr(err)).toContain('email: field required')
    expect(extractErr(err)).toContain('password: too short')
  })

  it('loadColor marks overload above 100%', () => {
    expect(loadColor(110)).toBe('var(--danger)')
    expect(loadColor(90)).toBe('var(--warning)')
    expect(loadColor(70)).toBe('var(--success)')
  })

  it('statusColor falls back safely for unknown status', () => {
    expect(statusColor('in_progress')).toBe('var(--accent)')
    expect(statusColor('unknown_status')).toBe('var(--text-3)')
  })
})

describe('extractErr: texto genérico en el idioma del operador', () => {
  const sinDetalle = { response: { data: {} } }
  it('sale en en y zh, y en es por defecto', async () => {
    const { loadLanguage } = await import('../i18n/appTranslations.ts')
    const { GENERIC_ERROR_FALLBACK } = await import('../constants/errors')
    await loadLanguage('en')
    await loadLanguage('zh')
    try {
      localStorage.setItem('contecflow_operator_lang', 'en')
      expect(extractErr(sinDetalle)).toBe('Unexpected error')
      expect(extractErr(sinDetalle, GENERIC_ERROR_FALLBACK)).toBe('Unexpected error')
      localStorage.setItem('contecflow_operator_lang', 'zh')
      expect(extractErr(sinDetalle)).toBe('意外错误')
      expect(extractErr(sinDetalle, GENERIC_ERROR_FALLBACK)).toBe('意外错误')
      localStorage.setItem('contecflow_operator_lang', 'es')
      expect(extractErr(sinDetalle)).toBe('Error inesperado')
    } finally {
      localStorage.setItem('contecflow_operator_lang', 'es')
    }
  })
  it('respeta un fallback explícito distinto del genérico', () => {
    expect(extractErr(sinDetalle, 'Otro texto')).toBe('Otro texto')
  })
})
