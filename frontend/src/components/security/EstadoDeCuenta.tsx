/**
 * Estado de la cuenta (23-11-2026, docs/seguridad/politicas_de_cuenta.md).
 *
 * `/auth/me` trae `account_security`. Con la contraseña caducada o con cambio
 * obligatorio, la API solo deja cambiarla (403 `contrasena_cambio_obligatorio`):
 * aquí se pinta SOLO el formulario de cambio. Con el MFA obligatorio vencido
 * (`mfa_enrollment_required`), solo la configuración del MFA. Durante la gracia
 * del MFA o cerca de la caducidad, una banda de aviso.
 */
import { lazy, Suspense, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Lock, Trash2 } from 'lucide-react'
import { Button, Card, IconButton, Input, Section, Spinner } from '../ui'
import { seguridadApi } from '../../services/api/seguridadDeCuentas'
import { useAuth, type User } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr, fmtDate, fmtDateTime } from '../../utils/helpers'
import '../../pages/settings-sections/SeguridadDeCuentasSection.css'

const MFAPage = lazy(() => import('../../pages/MFAPage'))

export interface EstadoDeSeguridad {
  password_change_required?: boolean
  password_expired?: boolean
  password_expires_in_days?: number | null
  password_expiry_warning?: boolean
  mfa_required?: boolean
  mfa_enrollment_required?: boolean
  mfa_grace_until?: string | null
}

export const estadoDe = (user: User | null): EstadoDeSeguridad => (user?.account_security as EstadoDeSeguridad) ?? {}

function CambioDeContrasenaObligatorio() {
  const { t } = useAppLang()
  const { user, setUser, logout } = useAuth()
  const toast = useToast()
  const politica = useQuery({ queryKey: ['politica-de-contrasena'], queryFn: seguridadApi.politicaDeContrasena })
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [repetida, setRepetida] = useState('')
  const [codigo, setCodigo] = useState('')
  const [enviando, setEnviando] = useState(false)
  const conTotp = Boolean(user?.mfa_enabled)
  const e = estadoDe(user)
  const p = politica.data
  const enviar = async () => {
    setEnviando(true)
    try {
      await seguridadApi.cambiarContrasena({ current_password: actual, new_password: nueva, mfa_code: codigo || undefined })
      const me = await seguridadApi.yo()
      toast.success(t('seguridad_cuentas.contrasena_cambiada'))
      setUser(me)
    } catch (err) {
      toast.error(extractErr(err, t('seguridad_cuentas.err_accion')))
    } finally { setEnviando(false) }
  }
  return (
    <main className="segc-obligatorio">
      <div className="segc-obligatorio__caja">
        <Card>
          <Section title={<><Lock size={16} aria-hidden /> {t('seguridad_cuentas.cambio_obligatorio_titulo')}</>}
            subtitle={e.password_expired ? t('seguridad_cuentas.contrasena_caducada_d') : t('seguridad_cuentas.cambio_obligatorio_d')}>
            {p && (
              <ul className="segc-reglas">
                <li>{t('seguridad_cuentas.regla_longitud', { min: p.MIN_PASSWORD_LENGTH, max: p.PASSWORD_MAX_LENGTH })}</li>
                {p.PASSWORD_BLOCK_COMMON && <li>{t('seguridad_cuentas.regla_comunes')}</li>}
                {p.PASSWORD_BLOCK_PERSONAL && <li>{t('seguridad_cuentas.regla_personales')}</li>}
                {p.PASSWORD_HISTORY_COUNT > 0 && <li>{t('seguridad_cuentas.regla_historial', { n: p.PASSWORD_HISTORY_COUNT })}</li>}
                {(p.PASSWORD_REQUIRE_UPPERCASE || p.PASSWORD_REQUIRE_LOWERCASE || p.PASSWORD_REQUIRE_DIGIT || p.PASSWORD_REQUIRE_SPECIAL)
                  && <li>{t('seguridad_cuentas.regla_composicion')}</li>}
              </ul>
            )}
            <Input label={t('seguridad_cuentas.contrasena_actual')} type="password" autoComplete="current-password"
              value={actual} onChange={ev => setActual(ev.target.value)} />
            <Input label={t('seguridad_cuentas.contrasena_nueva')} type="password" autoComplete="new-password"
              value={nueva} onChange={ev => setNueva(ev.target.value)} />
            <Input label={t('seguridad_cuentas.contrasena_repetir')} type="password" autoComplete="new-password"
              value={repetida} onChange={ev => setRepetida(ev.target.value)}
              error={repetida && repetida !== nueva ? t('seguridad_cuentas.no_coinciden') : undefined} />
            {conTotp && (
              <Input label={t('seguridad_cuentas.codigo_mfa')} inputMode="numeric" maxLength={6} value={codigo}
                onChange={ev => setCodigo(ev.target.value.replace(/\D/g, '').slice(0, 6))} />
            )}
            <div className="segc-acciones">
              <Button loading={enviando} disabled={!actual || !nueva || nueva !== repetida || (conTotp && codigo.length !== 6)}
                onClick={enviar}>{t('seguridad_cuentas.cambiar_contrasena')}</Button>
              <Button variant="ghost" onClick={logout}>{t('seguridad_cuentas.salir')}</Button>
            </div>
          </Section>
        </Card>
      </div>
    </main>
  )
}

function MfaObligatorio() {
  const { t } = useAppLang()
  const { setUser, logout } = useAuth()
  const comprobar = async () => {
    setUser(await seguridadApi.yo())
  }
  return (
    <main className="segc-obligatorio">
      <div className="segc-obligatorio__caja">
        <p className="segc-aviso segc-aviso--peligro" role="alert">{t('seguridad_cuentas.mfa_obligatorio_d')}</p>
        <Suspense fallback={<Spinner />}><MFAPage /></Suspense>
        <div className="segc-acciones">
          <Button onClick={comprobar}>{t('seguridad_cuentas.ya_configurado')}</Button>
          <Button variant="ghost" onClick={logout}>{t('seguridad_cuentas.salir')}</Button>
        </div>
      </div>
    </main>
  )
}

function BandaDeAviso({ e }: { e: EstadoDeSeguridad }) {
  const { t } = useAppLang()
  const [oculta, setOculta] = useState(false)
  if (oculta) return null
  const textos: string[] = []
  if (e.mfa_required && e.mfa_grace_until && !e.mfa_enrollment_required)
    textos.push(t('seguridad_cuentas.banda_mfa', { fecha: fmtDate(e.mfa_grace_until) }))
  if (e.password_expiry_warning && e.password_expires_in_days != null)
    textos.push(t('seguridad_cuentas.banda_caducidad', { n: e.password_expires_in_days }))
  if (!textos.length) return null
  return (
    <div className="segc-banda" role="status">
      <span>{textos.join(' ')}</span>
      {e.mfa_required && e.mfa_grace_until && <Link to="/settings/mfa">{t('seguridad_cuentas.configurar_mfa')}</Link>}
      <Button size="xs" variant="ghost" onClick={() => setOculta(true)}>{t('seguridad_cuentas.ocultar')}</Button>
    </div>
  )
}

/** Envuelve las rutas con sesión: decide si se pinta la app, el cambio obligatorio o el MFA. */
export function GuardaDeSeguridadDeCuenta({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const e = estadoDe(user)
  if (e.password_change_required) return <CambioDeContrasenaObligatorio />
  if (e.mfa_enrollment_required) return <MfaObligatorio />
  return <><BandaDeAviso e={e} />{children}</>
}

/** Mis dispositivos de confianza (en la página de MFA). */
export function DispositivosDeConfianza() {
  const { t } = useAppLang()
  const toast = useToast()
  const q = useQuery({ queryKey: ['mis-dispositivos'], queryFn: seguridadApi.misDispositivos })
  if (!q.data?.length) return null
  const olvidar = async (id: string) => {
    try { await seguridadApi.olvidarDispositivo(id); await q.refetch() }
    catch (err) { toast.error(extractErr(err, t('seguridad_cuentas.err_accion'))) }
  }
  return (
    <Card>
      <Section title={t('seguridad_cuentas.dispositivos')} subtitle={t('seguridad_cuentas.dispositivos_d')}>
        <ul className="segc-reglas">
          {q.data.map(d => (
            <li key={d.id}>
              {d.device_name ?? '—'} · {d.ip_address ?? '—'} · {t('seguridad_cuentas.hasta', { fecha: fmtDateTime(d.expires_at) })}
              {' '}<IconButton variante="caja" tono="peligro" ariaLabel={t('seguridad_cuentas.olvidar')} onClick={() => olvidar(d.id)}><Trash2 size={14} /></IconButton>
            </li>
          ))}
        </ul>
      </Section>
    </Card>
  )
}
