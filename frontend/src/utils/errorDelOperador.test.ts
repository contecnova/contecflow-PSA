import { describe, it, expect } from 'vitest'
import { textoDeErrorDelOperador } from './errorDelOperador'

/**
 * Errores con código del operador (19-11-2026): `no_encontrado` con
 * `params.que` traduce también la entidad (`err_srv.que_<entidad>`).
 */
describe('textoDeErrorDelOperador', () => {
  const noEncontrado = { response: { data: { detail: 'Épica no encontrada', code: 'no_encontrado', params: { que: 'epica' } } } }

  it('traduce el código y la entidad en en y zh, y en es por defecto', async () => {
    const { loadLanguage } = await import('../i18n/appTranslations.ts')
    await loadLanguage('en')
    await loadLanguage('zh')
    try {
      localStorage.setItem('contecflow_operator_lang', 'en')
      expect(textoDeErrorDelOperador(noEncontrado)).toBe('Not found: Epic')
      localStorage.setItem('contecflow_operator_lang', 'zh')
      expect(textoDeErrorDelOperador(noEncontrado)).toBe('未找到：史诗')
      localStorage.setItem('contecflow_operator_lang', 'es')
      expect(textoDeErrorDelOperador(noEncontrado)).toBe('No se encuentra: Épica')
    } finally {
      localStorage.setItem('contecflow_operator_lang', 'es')
    }
  })

  it('un código desconocido devuelve null (se enseña el detail)', () => {
    expect(textoDeErrorDelOperador({ response: { data: { detail: 'x', code: 'no_existe_este_codigo' } } })).toBeNull()
  })

  it('un dato que no es entidad se pinta tal cual', () => {
    const e = { response: { data: { code: 'valor_no_valido', params: { valor: 'zz' } } } }
    expect(textoDeErrorDelOperador(e)).toBe('Valor no válido: zz')
  })
})
