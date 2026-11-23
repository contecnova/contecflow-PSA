// «¿Olvidaste tu contraseña?» (23-11-2026, docs/seguridad/politicas_de_cuenta.md §3 bis):
// textos del portal en sus 8 idiomas, códigos de error del servidor, textos del
// operador en es/en/zh, la ruta del enlace del correo y la comprobación local de
// la política en la pantalla de nueva contraseña.
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { incumplimiento, type ReglasDeContrasena } from '../pages/portal-client/RecuperarContrasena'
import { PORTAL_TRANSLATIONS } from '../i18n/portalTranslations'
import es from '../i18n/langs/es.mjs'
import en from '../i18n/langs/en.mjs'
import zh from '../i18n/langs/zh.mjs'

const IDIOMAS_DEL_PORTAL = ['es', 'en', 'zh', 'fr', 'de', 'it', 'pt', 'pl']
const CLAVES_DEL_PORTAL = [
  'err_srv.portal_reset_token_no_valido', 'err_srv.portal_recuperacion_demasiadas_solicitudes',
  'portal_recuperar.enlace', 'portal_recuperar.titulo', 'portal_recuperar.enviar', 'portal_recuperar.enviado',
  'portal_restablecer.titulo', 'portal_restablecer.guardar', 'portal_restablecer.hecho', 'portal_restablecer.sin_token',
  'portal_restablecer.regla_longitud', 'portal_restablecer.regla_mayuscula', 'portal_restablecer.regla_especial',
]

const reglas: ReglasDeContrasena = {
  MIN_PASSWORD_LENGTH: 12, PASSWORD_MAX_LENGTH: 64,
  PASSWORD_REQUIRE_UPPERCASE: true, PASSWORD_REQUIRE_LOWERCASE: true,
  PASSWORD_REQUIRE_DIGIT: true, PASSWORD_REQUIRE_SPECIAL: false,
  PASSWORD_BLOCK_COMMON: true, PASSWORD_BLOCK_PERSONAL: true,
}

describe('restablecer contraseña del portal', () => {
  it('tiene los textos en los 8 idiomas', () => {
    const T = PORTAL_TRANSLATIONS as unknown as Record<string, Record<string, string>>
    for (const lang of IDIOMAS_DEL_PORTAL) {
      for (const clave of CLAVES_DEL_PORTAL) expect(T[lang]?.[clave], `${lang} ${clave}`).toBeTruthy()
    }
  })

  it('comprueba la política antes de enviar', () => {
    expect(incumplimiento('Corta1', reglas)).toBe('portal_restablecer.regla_longitud')
    expect(incumplimiento('todo-minusculas-1', reglas)).toBe('portal_restablecer.regla_mayuscula')
    expect(incumplimiento('SinNumerosAqui', reglas)).toBe('portal_restablecer.regla_numero')
    expect(incumplimiento('Valida-Clave-2026', reglas)).toBeNull()
    expect(incumplimiento('1234567', null)).toBe('portal_perfil.minimo_8')
  })

  it('la ruta del enlace del correo existe', () => {
    const app = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(app).toContain('path="/portal/reset-password"')
  })
})

describe('restablecimiento forzado (operador)', () => {
  it('tiene los textos en es/en/zh', () => {
    for (const d of [es, en, zh] as unknown as Array<Record<string, Record<string, string>>>) {
      expect(d.seguridad_cuentas.a_restablecer).toBeTruthy()
      expect(d.seguridad_cuentas.confirmar_restablecer).toContain('{nombre}')
      expect(d.portaluserstab.forzar_restablecimiento).toBeTruthy()
      expect(d.portaluserstab.confirmar_forzar_restablecimiento).toContain('{email}')
    }
  })
})
