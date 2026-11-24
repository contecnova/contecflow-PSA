/**
 * «¿Olvidaste tu contraseña?» del portal de clientes (23-11-2026).
 *
 * - `OlvideMiContrasena`: el formulario del login del portal (correo → enlace).
 *   La respuesta es la misma exista o no la cuenta (el servidor no lo revela).
 * - `PortalRestablecerContrasenaPage` (`/portal/reset-password?token=…&lang=…`):
 *   nueva contraseña con las reglas de la empresa (`/portal/auth/password/policy`)
 *   y los errores del servidor traducidos (`err_srv.*`). Al guardar, el servidor
 *   cierra todas las sesiones del portal del cliente.
 *
 * Servidor: `app/api/v1/endpoints/client_portal_password.py`. Textos en los 8
 * idiomas del portal (`portal_recuperar.*`, `portal_restablecer.*`).
 */
import { useEffect, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { KeyRound, Mail } from 'lucide-react'
import { CLIENT_API, LangContext, TextosDeInterfazDelPortal, codigoDeAccesoDelPortal, useErrorDelPortal, useLang } from './portalClientContext'
import { PortalBanner, PortalButton, PortalCard, PortalField, PortalInput, PortalSection } from './PortalUI'
import { idiomaInicialDelPortal } from '../../i18n/portalTranslations'
import './CambioDeContrasenaObligatorio.css'

/** Reglas de la política que enseña la pantalla (mismas claves que el servidor). */
export interface ReglasDeContrasena {
  MIN_PASSWORD_LENGTH: number; PASSWORD_MAX_LENGTH: number
  PASSWORD_REQUIRE_UPPERCASE: boolean; PASSWORD_REQUIRE_LOWERCASE: boolean
  PASSWORD_REQUIRE_DIGIT: boolean; PASSWORD_REQUIRE_SPECIAL: boolean
  PASSWORD_BLOCK_COMMON: boolean; PASSWORD_BLOCK_PERSONAL: boolean
  /** Migración 208: la cuenta es de una empresa; la pantalla la nombra. */
  organization_name?: string | null
}

/** Primer incumplimiento local de `reglas` (clave de texto), o null. El servidor valida igual. */
export function incumplimiento(clave: string, reglas: ReglasDeContrasena | null): string | null {
  if (!reglas) return clave.length < 8 ? 'portal_perfil.minimo_8' : null
  if (clave.length < reglas.MIN_PASSWORD_LENGTH || clave.length > reglas.PASSWORD_MAX_LENGTH) return 'portal_restablecer.regla_longitud'
  if (reglas.PASSWORD_REQUIRE_UPPERCASE && !/[A-Z]/.test(clave)) return 'portal_restablecer.regla_mayuscula'
  if (reglas.PASSWORD_REQUIRE_LOWERCASE && !/[a-z]/.test(clave)) return 'portal_restablecer.regla_minuscula'
  if (reglas.PASSWORD_REQUIRE_DIGIT && !/\d/.test(clave)) return 'portal_restablecer.regla_numero'
  if (reglas.PASSWORD_REQUIRE_SPECIAL && !/[^A-Za-z0-9]/.test(clave)) return 'portal_restablecer.regla_especial'
  return null
}

// ── Formulario del login ─────────────────────────────────────────────────────
export function OlvideMiContrasena({ onVolver }: { onVolver: () => void }) {
  const traducir = useLang()
  const errorDe = useErrorDelPortal()
  const [email, setEmail] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [enviado, setEnviado] = useState(false)
  const [aviso, setAviso] = useState('')

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setAviso(''); setEnviando(true)
    try {
      // Migración 208: con código de acceso, solo esa empresa; si no, un enlace por empresa.
      await CLIENT_API.post('/portal/auth/password/forgot', { email: email.trim(), organization_code: codigoDeAccesoDelPortal() })
      setEnviado(true)
    } catch (err) {
      setAviso(errorDe(err, traducir('portal_recuperar.error')))
    } finally { setEnviando(false) }
  }

  return (
    <form onSubmit={enviar} className="u-stack-14" noValidate>
      <h2 className="poclco-box-10">{traducir('portal_recuperar.titulo')}</h2>
      <p className="poclco-box-11">{traducir('portal_recuperar.explicacion')}</p>
      {enviado ? (
        <>
          <PortalBanner tone="success" icon={<Mail size={16} />} title={traducir('portal_recuperar.enviado')} />
          <p className="u-text2-sm">{traducir('portal_recuperar.varias_empresas')}</p>
        </>
      ) : (
        <>
          <PortalField label={traducir('login_email')} required>
            <PortalInput type="email" autoComplete="email" value={email} autoFocus maxLength={254}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
              placeholder={traducir('login_email_placeholder')} />
          </PortalField>
          {aviso && <PortalBanner tone="danger" title={aviso} />}
          <PortalButton type="submit" icon={<Mail size={13} />} loading={enviando} disabled={!email.trim()}>
            {traducir('portal_recuperar.enviar')}
          </PortalButton>
        </>
      )}
      <PortalButton variant="ghost" onClick={onVolver}>{traducir('portal_recuperar.volver')}</PortalButton>
    </form>
  )
}

// ── Pantalla del enlace ──────────────────────────────────────────────────────
function idiomaInicial(): string {
  // Incidencia 5 (23-11-2026): URL > usuario/empresa recordados > navegador > inglés.
  return idiomaInicialDelPortal()
}

function NuevaContrasena() {
  const traducir = useLang()
  const errorDe = useErrorDelPortal()
  // Se lee una vez: justo después se quita de la barra de direcciones.
  const [token] = useState(() => new URLSearchParams(window.location.search).get('token') || '')
  const [reglas, setReglas] = useState<ReglasDeContrasena | null>(null)
  const [tokenMalo, setTokenMalo] = useState(!token)
  const [form, setForm] = useState({ nueva: '', repetida: '' })
  const [aviso, setAviso] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [hecho, setHecho] = useState(false)

  useEffect(() => {
    if (!token) return
    CLIENT_API.post('/portal/auth/password/policy', { token })
      .then(r => setReglas(r.data as ReglasDeContrasena))
      .catch(() => setTokenMalo(true))
  }, [token])

  // Quita el token de la barra de direcciones (historial, capturas, referer).
  useEffect(() => {
    if (token) window.history.replaceState(null, '', window.location.pathname)
  }, [token])

  const irAlAcceso = () => { window.location.href = '/portal' }

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setAviso('')
    if (form.nueva !== form.repetida) { setAviso(traducir('portal_perfil.contrasenas_no_coinciden')); return }
    const falla = incumplimiento(form.nueva, reglas)
    if (falla) {
      setAviso(traducir(falla, { min: reglas?.MIN_PASSWORD_LENGTH, max: reglas?.PASSWORD_MAX_LENGTH }))
      return
    }
    setEnviando(true)
    try {
      await CLIENT_API.post('/portal/auth/password/reset', { token, new_password: form.nueva })
      setHecho(true)
    } catch (err) {
      setAviso(errorDe(err, traducir('portal_perfil.error_contrasena')))
    } finally { setEnviando(false) }
  }
  const campo = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  if (hecho) {
    return (
      <PortalCard>
        <PortalSection title={traducir('portal_restablecer.titulo')}>
          <PortalBanner tone="success" title={traducir('portal_restablecer.hecho')} />
          <div className="pcl-row-5">
            <PortalButton onClick={irAlAcceso}>{traducir('portal_restablecer.ir_al_acceso')}</PortalButton>
          </div>
        </PortalSection>
      </PortalCard>
    )
  }
  if (tokenMalo) {
    return (
      <PortalCard>
        <PortalSection title={traducir('portal_restablecer.titulo')}>
          <PortalBanner tone="danger" title={traducir('portal_restablecer.sin_token')} />
          <div className="pcl-row-5">
            <PortalButton onClick={irAlAcceso}>{traducir('portal_restablecer.pedir_otro')}</PortalButton>
          </div>
        </PortalSection>
      </PortalCard>
    )
  }
  return (
    <PortalCard>
      <PortalSection title={traducir('portal_restablecer.titulo')} hint={traducir('portal_restablecer.explicacion')}>
        {reglas?.organization_name && (
          <p className="u-text2-sm">{traducir('portal_restablecer.empresa', { empresa: reglas.organization_name })}</p>
        )}
        {reglas && (
          <div className="u-text2-sm">
            <p>{traducir('portal_restablecer.reglas')}</p>
            <ul>
              <li>{traducir('portal_restablecer.regla_longitud', { min: reglas.MIN_PASSWORD_LENGTH, max: reglas.PASSWORD_MAX_LENGTH })}</li>
              {reglas.PASSWORD_REQUIRE_UPPERCASE && <li>{traducir('portal_restablecer.regla_mayuscula')}</li>}
              {reglas.PASSWORD_REQUIRE_LOWERCASE && <li>{traducir('portal_restablecer.regla_minuscula')}</li>}
              {reglas.PASSWORD_REQUIRE_DIGIT && <li>{traducir('portal_restablecer.regla_numero')}</li>}
              {reglas.PASSWORD_REQUIRE_SPECIAL && <li>{traducir('portal_restablecer.regla_especial')}</li>}
              {reglas.PASSWORD_BLOCK_COMMON && <li>{traducir('portal_restablecer.regla_comunes')}</li>}
              {reglas.PASSWORD_BLOCK_PERSONAL && <li>{traducir('portal_restablecer.regla_personales')}</li>}
            </ul>
          </div>
        )}
        <form className="u-stack-12" onSubmit={enviar}>
          <PortalField label={traducir('portalcliente.nueva_contrasena')} required>
            <PortalInput type="password" autoComplete="new-password" value={form.nueva} onChange={campo('nueva')} autoFocus />
          </PortalField>
          <PortalField label={traducir('portalcliente.confirmar_nueva_contrasena')} required>
            <PortalInput type="password" autoComplete="new-password" value={form.repetida} onChange={campo('repetida')} />
          </PortalField>
          {aviso && <PortalBanner tone="danger" title={aviso} />}
          <div className="pcl-row-5">
            <PortalButton type="submit" icon={<KeyRound size={13} />} loading={enviando} disabled={!form.nueva || !form.repetida}>
              {traducir('portal_restablecer.guardar')}
            </PortalButton>
            <PortalButton variant="ghost" onClick={irAlAcceso}>{traducir('portal_restablecer.ir_al_acceso')}</PortalButton>
          </div>
        </form>
      </PortalSection>
    </PortalCard>
  )
}

export default function PortalRestablecerContrasenaPage() {
  const [lang] = useState(idiomaInicial)
  return (
    <LangContext.Provider value={lang}>
      <TextosDeInterfazDelPortal>
        <main className="u-stack-12 pcco-marco">
          <NuevaContrasena />
        </main>
      </TextosDeInterfazDelPortal>
    </LangContext.Provider>
  )
}
