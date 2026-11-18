/**
 * Reautenticacion antes de cambiar el segundo factor.
 *
 * Auditoria 2026-11 (#21, backend): `POST /auth/mfa/webauthn/register/start` y
 * `POST /auth/mfa/setup` (con el 2FA ya activo) exigen `{password}` o `{code}`
 * (ReautenticacionIn); sin ellos responden 401. Se pide con el dialogo del kit
 * (ConfirmContext.pedirTexto), con el campo de tipo password.
 */
import type { PromptOptions } from '../../context/ConfirmContext'
import type { Reautenticacion } from '../../services/api/auth'
import { traducirSinHook } from '../../i18n/traducirSinHook'

/** Pide la contrasena actual o un codigo de 6 digitos; null si se cancela. */
export async function pedirReautenticacion(
  pedirTexto: (opts: PromptOptions) => Promise<string | null>,
): Promise<Reautenticacion | null> {
  const valor = await pedirTexto({
    title: traducirSinHook('mfa.reauth_titulo'),
    message: traducirSinHook('mfa.reauth_mensaje'),
    label: traducirSinHook('mfa.reauth_etiqueta'),
    inputType: 'password',
    required: true,
    confirmLabel: traducirSinHook('mfa.reauth_continuar'),
  })
  if (valor == null) return null
  const v = valor.trim()
  if (!v) return null
  // El servidor prueba primero la contrasena y luego el codigo; si parece un
  // codigo TOTP (6-8 digitos) se manda tambien como codigo.
  return /^\d{6,8}$/.test(v) ? { password: valor, code: v } : { password: valor }
}

/** El servidor rechazo la contrasena o el codigo (401 en la llamada de inicio). */
export function esFalloDeReautenticacion(e: unknown): boolean {
  return (e as { response?: { status?: number } } | null)?.response?.status === 401
}
